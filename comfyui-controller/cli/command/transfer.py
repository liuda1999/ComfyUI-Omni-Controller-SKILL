"""``comfy download`` 与 ``comfy upload`` —— ComfyUI 文件传输透传。

原生重实现（对齐官方 comfy-cli 语义，适配本项目 cli/ 架构）：

- ``download <prompt_id>``：读取 GET /history/{prompt_id}，将其产物
  （images / gifs / videos）经 /view 下载到本地目录。
- ``upload <file>`：经 POST /upload/image 上传图片到服务器的 input 目录，
  返回服务器端文件名，可被 LoadImage 等节点引用。

仅面向本地 ComfyUI（官方版本的 ``--where cloud`` 属于云子系统，本移植不含）。
"""

from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request

import typer
from rich.console import Console

from cli.command import net

console = Console()

_TIMEOUT = 30
# /history 中可能出现的产物字段（ComfyUI 视类型放入不同键）
_OUTPUT_KEYS = ("images", "gifs", "videos", "audio")


def _base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}"


def _unreachable(host: str, port: int, operation: str, e: Exception) -> None:
    console.print(
        f"[bold red]Could not reach ComfyUI at {host}:{port} during {operation}:[/bold red] {e}"
    )
    console.print("[yellow]Run `comfy launch` to start a local server (or pass --host/--port).[/yellow]")


def _view_url(host: str, port: int, item: dict) -> str:
    params = {
        "filename": item.get("filename", ""),
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
    }
    return f"{_base_url(host, port)}/view?{urllib.parse.urlencode(params)}"


def download_execute(
    prompt_id: str,
    output_dir: str,
    host: str,
    port: int,
    json_output: bool = False,
) -> None:
    """``comfy download`` 的入口。"""
    hist_url = f"{_base_url(host, port)}/history/{urllib.parse.quote(prompt_id)}"
    try:
        with net.open_url(hist_url, timeout=_TIMEOUT) as resp:
            history = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        _unreachable(host, port, "download", e)
        raise typer.Exit(code=1) from e

    entry = history.get(prompt_id)
    if not isinstance(entry, dict):
        console.print(f"[bold red]No history entry for prompt_id:[/bold red] {prompt_id}")
        raise typer.Exit(code=1)

    outputs = entry.get("outputs") or {}
    items: list[dict] = []
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for key in _OUTPUT_KEYS:
            for it in node_out.get(key, []) or []:
                if isinstance(it, dict) and it.get("filename"):
                    items.append(it)

    if not items:
        console.print(f"[yellow]No downloadable outputs found for {prompt_id}.[/yellow]")
        raise typer.Exit(code=1)

    os.makedirs(output_dir, exist_ok=True)
    saved: list[str] = []
    for it in items:
        url = _view_url(host, port, it)
        dest = os.path.join(output_dir, os.path.basename(it.get("filename", "output")))
        try:
            with net.open_url(url, timeout=_TIMEOUT) as resp, open(dest, "wb") as fh:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    fh.write(chunk)
            saved.append(dest)
            if not json_output:
                console.print(f"  [green]saved[/green] {dest}")
        except (urllib.error.URLError, OSError) as e:
            console.print(f"  [red]failed[/red] {it.get('filename')}: {e}")

    if json_output:
        print(json.dumps({"prompt_id": prompt_id, "downloaded": saved}, ensure_ascii=False, indent=2))
    else:
        console.print(f"[bold green]Downloaded {len(saved)} file(s) to {output_dir}[/bold green]")


def _encode_multipart(field_name: str, filename: str, content: bytes) -> tuple[bytes, str]:
    boundary = "----comfyomnicontroller" + os.urandom(8).hex()
    ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="{field_name}"; filename="{os.path.basename(filename)}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {ctype}\r\n\r\n".encode())
    parts.append(content)
    parts.append(b"\r\n")
    # overwrite + subfolder 的常见默认（ComfyUI /upload/image 接受）
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n')
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload_execute(file_path: str, host: str, port: int, json_output: bool = False) -> None:
    """``comfy upload`` 的入口。"""
    if not os.path.isfile(file_path):
        console.print(f"[bold red]File not found:[/bold red] {file_path}")
        raise typer.Exit(code=1)

    with open(file_path, "rb") as fh:
        content = fh.read()
    body, ctype = _encode_multipart("image", file_path, content)

    url = f"{_base_url(host, port)}/upload/image"
    try:
        with net.open_url(url, data=body, headers={"Content-Type": ctype}, method="POST", timeout=_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        _unreachable(host, port, "upload", e)
        raise typer.Exit(code=1) from e

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        name = result.get("name", "")
        sub = result.get("subfolder", "")
        full = f"{sub}/{name}" if sub else name
        console.print(f"[bold green]Uploaded:[/bold green] {full}")
