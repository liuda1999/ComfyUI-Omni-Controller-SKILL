"""``comfy system-stats`` 与 ``comfy free`` —— ComfyUI 资源管理透传。

原生重实现（对齐官方 comfy-cli 语义，适配本项目 cli/ 旧架构；官方 1.22 版本
依赖其 comfy_client/renderer 框架，无法逐字照搬）：

- ``system-stats``：GET ``/system_stats``，输出各设备 VRAM 与系统内存表。
- ``free``：POST ``/free``，请求卸载模型（unload_models）与/或释放
  executor 缓存（free_memory）。

两者均通过 project 既有方式解析目标地址（--host/--port > 后台实例 >
COMFYUI_HOST/PORT > 默认 127.0.0.1:8188）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from cli.command import net

console = Console()

_TIMEOUT = 10


def _humanize_bytes(n: Any) -> str:
    """把字节数渲染为紧凑可读字符串（如 ``3.5 GiB``）。非数值返回 ``?``。"""
    if not isinstance(n, (int, float)):
        return "?"
    value = float(n)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024.0:
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PiB"


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _unreachable(host: str, port: int, operation: str, e: Exception) -> None:
    console.print(
        f"[bold red]Could not reach ComfyUI at {host}:{port} during {operation}:[/bold red] {e}"
    )
    console.print("[yellow]Run `comfy launch` to start a local server (or pass --host/--port).[/yellow]")


def system_stats_execute(host: str, port: int, json_output: bool = False) -> None:
    """``comfy system-stats`` 的入口。"""
    url = f"{_base_url(host, port)}/system_stats"
    try:
        with net.open_url(url, timeout=_TIMEOUT) as resp:
            stats = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        _unreachable(host, port, "system-stats", e)
        raise typer.Exit(code=1) from e

    if not isinstance(stats, dict):
        console.print("[bold red]ComfyUI returned an unparseable /system_stats response.[/bold red]")
        raise typer.Exit(code=1)

    if json_output:
        # 结构化输出：整包原样打印，便于脚本/智能体消费
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return

    devices = stats.get("devices") or []
    tbl = Table(show_header=True, header_style="bold")
    for col in ("name", "type", "index", "vram_free", "vram_total"):
        tbl.add_column(col)
    for dev in devices:
        if not isinstance(dev, dict):
            continue
        tbl.add_row(
            str(dev.get("name", "?")),
            str(dev.get("type", "?")),
            str(dev.get("index", "?")),
            _humanize_bytes(dev.get("vram_free")),
            _humanize_bytes(dev.get("vram_total")),
        )
    console.print(tbl)

    system = stats.get("system") or {}
    ram_free = _humanize_bytes(system.get("ram_free"))
    ram_total = _humanize_bytes(system.get("ram_total"))
    version = system.get("comfyui_version", "?")
    console.print(f"[dim]RAM: {ram_free} / {ram_total} free — ComfyUI {version}[/dim]")


def free_execute(
    host: str,
    port: int,
    unload_models: bool = True,
    free_memory: bool = False,
    json_output: bool = False,
) -> None:
    """``comfy free`` 的入口。"""
    url = f"{_base_url(host, port)}/free"
    body = json.dumps({"unload_models": unload_models, "free_memory": free_memory}).encode("utf-8")
    try:
        with net.open_url(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST", timeout=_TIMEOUT
        ):
            pass
    except (urllib.error.URLError, OSError) as e:
        _unreachable(host, port, "free", e)
        raise typer.Exit(code=1) from e

    note = (
        "在队列 worker 下次迭代时生效——空闲时立即生效，忙碌时在当前任务之后；不会中断正在运行的任务"
    )
    if json_output:
        print(json.dumps(
            {"requested": {"unload_models": unload_models, "free_memory": free_memory}, "note": note},
            ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]已请求：[/green] unload_models={unload_models}, free_memory={free_memory}")
        console.print(f"[dim]{note}[/dim]")
