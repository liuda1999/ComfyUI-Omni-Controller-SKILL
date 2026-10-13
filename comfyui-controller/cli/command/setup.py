"""``comfy setup`` —— 一次性环境向导（本地版）。

官方 1.22 的 ``setup`` 是含「本地/云端路由 + OAuth 鉴权 + 安装 agent skills」的
向导；本项目为本地控制器，此处实现**本地子集**：验证 Python、定位工作区、
检查服务是否在运行，并给出下一步指引。

非交互（CI/脚本）：``comfy setup --skip-prompt`` 直接走默认并打印结论。
"""

from __future__ import annotations

import sys

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from cli import constants
from cli.env_checker import EnvChecker, check_comfy_server_running
from cli.workspace_manager import WorkspaceManager

console = Console()


def setup_execute(where: str = "local", skip_verify: bool = False, skip_prompt: bool = False) -> None:
    console.print(
        Panel.fit(
            "[bold]ComfyUI Omni-Controller · Setup[/bold]\n"
            "本地环境向导：验证 Python / 定位工作区 / 检查服务",
            border_style="cyan",
        )
    )

    if where != "local":
        rprint("[yellow]本项目为本地控制器；`--where cloud` 不受支持，已按 local 处理。[/yellow]")

    # 1. Python
    ver = sys.version_info
    ok = ver.major == 3 and ver.minor >= 10
    rprint(f"{'[green]✓[/green]' if ok else '[red]✗[/red]'} Python {ver.major}.{ver.minor}.{ver.micro} "
           f"(需 >=3.10)")

    # 2. Workspace
    wm = WorkspaceManager()
    comfy_path = wm.workspace_path
    if comfy_path:
        rprint(f"[green]✓[/green] Workspace: {comfy_path}")
    else:
        rprint("[yellow]! 未定位到 ComfyUI 工作区。[/yellow]")
        rprint("  - 用 `comfy install` 安装，或")
        rprint("  - 在 ComfyUI 目录下运行，或用 `comfy set-default <path>` / `--workspace <path>` 指定")

    # 3. Server
    if not skip_verify:
        host = constants.default_host()
        port = constants.default_port()
        if check_comfy_server_running(port, host):
            rprint(f"[green]✓[/green] ComfyUI 服务运行中：http://{host}:{port}")
        else:
            rprint(f"[yellow]! ComfyUI 服务未运行（{host}:{port}）。[/yellow]")
            rprint("  启动：`comfy launch`（前台）或 `comfy launch --background`（后台）")

    rprint("\n[bold]下一步：[/bold]")
    rprint("  comfy launch --background     # 后台启动 ComfyUI")
    rprint("  comfy run --workflow <wf.json>  # 运行工作流")
    rprint("  comfy jobs ls                 # 查看作业")
    rprint("  comfy system-stats            # 查看显存/内存")
    rprint("  comfy stop                    # 停止后台实例")

    if comfy_path is None:
        raise typer.Exit(code=1)
