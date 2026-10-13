"""``comfy templates`` —— ComfyUI 官方工作流模板画廊（本地版）。

对齐官方语义：从公共画廊
``https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/``
拉取 ``index.json`` 列出模板，并可取单个模板的工作流 JSON 直接运行。

- ``templates ls [--name SUB] [--limit N] [--refresh]`` —— 列出模板。
- ``run-template <name>`` —— 取模板工作流并交由本地 ``comfy run`` 执行。

说明：官方 1.22 的 templates 还含 provider 过滤、缓存刷新子进程、dot-path
投影等大量云端/渲染器特性；此处只保留本地可用的核心能力。
"""

from __future__ import annotations

import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import typer
from rich.console import Console
from rich.table import Table

console = Console()

GALLERY_URL = (
    "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/index.json"
)
TEMPLATE_URL = (
    "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/{name}.json"
)

_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "comfy-cli", "gallery")
_CACHE_FILE = os.path.join(_CACHE_DIR, "index.json")
_TIMEOUT = 20


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "comfy-cli"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return resp.read()


def _load_index(refresh: bool = False, gallery: str | None = None) -> list:
    if gallery:
        with open(gallery, "r", encoding="utf-8") as fh:
            return json.load(fh)
    if refresh or not os.path.exists(_CACHE_FILE):
        data = _fetch(GALLERY_URL)
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(_CACHE_FILE, "wb") as fh:
            fh.write(data)
    with open(_CACHE_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _flatten(index: list) -> list[dict]:
    rows: list[dict] = []
    for cat in index:
        if not isinstance(cat, dict):
            continue
        category = cat.get("category") or cat.get("name") or ""
        for t in cat.get("templates") or []:
            if isinstance(t, dict):
                rows.append({
                    "name": t.get("name") or "",
                    "category": category,
                    "description": (t.get("description") or "").strip(),
                })
    return rows


def templates_ls(
    name_sub: str | None = None,
    limit: int = 0,
    refresh: bool = False,
    gallery: str | None = None,
    json_output: bool = False,
) -> None:
    try:
        rows = _flatten(_load_index(refresh=refresh, gallery=gallery))
    except (urllib.error.URLError, OSError, ValueError) as e:
        console.print(f"[bold red]Could not fetch templates gallery:[/bold red] {e}")
        console.print("[yellow]Pass --gallery <path> to a local index.json, or check your network.[/yellow]")
        raise typer.Exit(code=1) from e

    if name_sub:
        rows = [r for r in rows if name_sub.lower() in r["name"].lower()]
    if limit:
        rows = rows[:limit]

    if json_output:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return

    tbl = Table(show_header=True, header_style="bold")
    for col in ("name", "category", "description"):
        tbl.add_column(col, overflow="fold")
    for r in rows:
        tbl.add_row(r["name"], r["category"], r["description"][:80])
    console.print(tbl)
    console.print(f"[dim]{len(rows)} template(s)[/dim]")


def fetch_template_workflow(name: str) -> str:
    """取单个模板工作流 JSON，写入临时文件，返回路径。"""
    url = TEMPLATE_URL.format(name=urllib.parse.quote(name, safe=""))
    try:
        data = _fetch(url)
    except (urllib.error.URLError, OSError) as e:
        console.print(f"[bold red]Could not fetch template '{name}':[/bold red] {e}")
        raise typer.Exit(code=1) from e
    fd, path = tempfile.mkstemp(prefix=f"tmpl_{name}_", suffix=".json")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path
