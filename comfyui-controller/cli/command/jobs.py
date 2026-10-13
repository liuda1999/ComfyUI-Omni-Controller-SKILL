"""``comfy jobs`` —— 查看 / 等待 ComfyUI 作业（本地子集）。

对齐官方 comfy-cli 的 ``jobs`` 语义，但只实现**本地**部分（官方版含云端
路由且高达 2700+ 行，深度耦合其渲染器/云框架）：

- ``jobs ls``      —— 列出队列中的 running / pending 作业与最近历史。
- ``jobs status``  —— 查看指定 prompt_id 的状态与产物摘要。
- ``jobs wait``    —— 轮询 /history/{id} 直到该作业完成。
- ``jobs watch``   —— 轮询并实时打印状态变化（不依赖 websocket，便于脚本/无显卡环境）。

数据来源：ComfyUI 的 ``GET /queue`` 与 ``GET /history[/{prompt_id}]``。
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import typer
from rich.console import Console
from rich.table import Table

from cli.command import net

console = Console()
jobs_app = typer.Typer(help="Inspect and wait on ComfyUI jobs.")

_TIMEOUT = 15


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _get_json(url: str) -> dict:
    return net.get_json(url, timeout=_TIMEOUT)


def _unreachable(host: str, port: int, e: Exception) -> None:
    console.print(f"[bold red]Could not reach ComfyUI at {host}:{port}:[/bold red] {e}")
    console.print("[yellow]Run `comfy launch` to start a local server (or pass --host/--port).[/yellow]")


def _job_status(entry: dict) -> str:
    status = entry.get("status") or {}
    if status.get("completed"):
        return status.get("status_str", "completed")
    return "running/pending"


def _summarize_outputs(entry: dict) -> int:
    outputs = entry.get("outputs") or {}
    n = 0
    for node_out in outputs.values():
        if isinstance(node_out, dict):
            for key in ("images", "gifs", "videos", "audio"):
                n += len(node_out.get(key, []) or [])
    return n


def jobs_ls(host: str, port: int, json_output: bool = False) -> None:
    base = _base_url(host, port)
    try:
        queue = _get_json(f"{base}/queue")
        history = _get_json(f"{base}/history")
    except (urllib.error.URLError, OSError, ValueError) as e:
        _unreachable(host, port, e)
        raise typer.Exit(code=1) from e

    running = queue.get("queue_running") or []
    pending = queue.get("queue_pending") or []

    if json_output:
        print(json.dumps(
            {
                "running": [r[1] if len(r) > 1 else r for r in running],
                "pending": [p[1] if len(p) > 1 else p for p in pending],
                "history_ids": list(history.keys()),
            },
            ensure_ascii=False, indent=2))
        return

    console.print(f"[bold]Running:[/bold] {len(running)}  [bold]Pending:[/bold] {len(pending)}")
    if running or pending:
        tbl = Table(show_header=True, header_style="bold")
        tbl.add_column("state")
        tbl.add_column("prompt_id")
        for r in running:
            tbl.add_row("running", str(r[1] if len(r) > 1 else r))
        for p in pending:
            tbl.add_row("pending", str(p[1] if len(p) > 1 else p))
        console.print(tbl)

    if history:
        tbl = Table(title="Recent history", show_header=True, header_style="bold")
        for col in ("prompt_id", "status", "outputs"):
            tbl.add_column(col)
        for pid, entry in list(history.items())[-15:]:
            entry = entry if isinstance(entry, dict) else {}
            tbl.add_row(pid, _job_status(entry), str(_summarize_outputs(entry)))
        console.print(tbl)


def jobs_status(prompt_id: str, host: str, port: int, json_output: bool = False) -> None:
    url = f"{_base_url(host, port)}/history/{urllib.parse.quote(prompt_id)}"
    try:
        history = _get_json(url)
    except (urllib.error.URLError, OSError, ValueError) as e:
        _unreachable(host, port, e)
        raise typer.Exit(code=1) from e

    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        console.print(f"[bold red]No history entry for prompt_id:[/bold red] {prompt_id}")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return

    console.print(f"[bold]prompt_id:[/bold] {prompt_id}")
    console.print(f"[bold]status   :[/bold] {_job_status(entry)}")
    console.print(f"[bold]outputs  :[/bold] {_summarize_outputs(entry)} file(s)")


def jobs_wait(
    prompt_id: str,
    host: str,
    port: int,
    timeout: int = 600,
    interval: float = 1.0,
    json_output: bool = False,
) -> None:
    url = f"{_base_url(host, port)}/history/{urllib.parse.quote(prompt_id)}"
    start = time.time()
    while True:
        try:
            history = _get_json(url)
        except (urllib.error.URLError, OSError, ValueError) as e:
            _unreachable(host, port, e)
            raise typer.Exit(code=1) from e
        entry = history.get(prompt_id)
        if isinstance(entry, dict) and (entry.get("status") or {}).get("completed"):
            status = _job_status(entry)
            if json_output:
                print(json.dumps(entry, ensure_ascii=False, indent=2))
            else:
                console.print(f"[bold green]Job {status}:[/bold green] {prompt_id} "
                              f"({_summarize_outputs(entry)} file(s))")
            if status != "success":
                raise typer.Exit(code=1)
            return
        if time.time() - start > timeout:
            console.print(f"[bold red]Timed out after {timeout}s waiting for {prompt_id}[/bold red]")
            raise typer.Exit(code=1)
        time.sleep(interval)


def jobs_watch(prompt_id: str, host: str, port: int, interval: float = 1.0) -> None:
    url = f"{_base_url(host, port)}/history/{urllib.parse.quote(prompt_id)}"
    last = None
    console.print(f"[dim]Watching {prompt_id} ... (Ctrl-C to stop)[/dim]")
    try:
        while True:
            history = _get_json(url)
            entry = history.get(prompt_id)
            if isinstance(entry, dict):
                st = _job_status(entry)
                if st != last:
                    console.print(f"  [{time.strftime('%H:%M:%S')}] {st}")
                    last = st
                if (entry.get("status") or {}).get("completed"):
                    return
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped watching.[/yellow]")
    except (urllib.error.URLError, OSError, ValueError) as e:
        _unreachable(host, port, e)
        raise typer.Exit(code=1) from e
