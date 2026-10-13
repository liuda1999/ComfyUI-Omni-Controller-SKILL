from __future__ import annotations

import asyncio
import glob
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
from collections import deque

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel

from cli import constants, output, utils
from cli.command.custom_nodes.cm_cli_util import find_cm_cli, resolve_manager_gui_mode
from cli.config_manager import ConfigManager
from cli.env_checker import check_comfy_server_running
from cli.resolve_python import resolve_workspace_python
from cli.update import check_for_updates
from cli.workspace_manager import WorkspaceManager, WorkspaceType

workspace_manager = WorkspaceManager()
console = Console()


def _get_manager_flags() -> list[str]:
    """Get manager flags based on config mode."""
    mode = resolve_manager_gui_mode(not_installed_value=None)

    if mode is None or mode == "disable":
        return []

    # For enable-* modes, verify cm-cli is available
    if not find_cm_cli():
        print(
            "[bold yellow]Warning: ComfyUI-Manager (cm-cli) not found. "
            "Manager flags will not be injected.[/bold yellow]"
        )
        return []

    if mode == "enable-gui":
        return ["--enable-manager"]
    elif mode == "disable-gui":
        return ["--enable-manager", "--disable-manager-ui"]
    elif mode == "enable-legacy-gui":
        return ["--enable-manager", "--enable-manager-legacy-ui"]
    else:
        print(f"[bold yellow]Warning: Unknown manager mode '{mode}'. Falling back to --enable-manager.[/bold yellow]")
        return ["--enable-manager"]  # fallback to default


def launch_comfyui(extra, frontend_pr=None, python=sys.executable):
    reboot_path = None

    new_env = os.environ.copy()

    session_path = os.path.join(ConfigManager().get_config_path(), "tmp", str(uuid.uuid4()))
    new_env["__COMFY_CLI_SESSION__"] = session_path
    new_env["PYTHONENCODING"] = "utf-8"

    # To minimize the possibility of leaving residue in the tmp directory, use files instead of directories.
    reboot_path = os.path.join(session_path + ".reboot")

    extra = extra if extra is not None else []

    # Handle temporary frontend PR
    if frontend_pr:
        from cli.command.install import handle_temporary_frontend_pr

        try:
            frontend_path = handle_temporary_frontend_pr(frontend_pr)
            if frontend_path:
                # Check if --front-end-root is not already specified
                if not any(arg.startswith("--front-end-root") for arg in extra):
                    extra = ["--front-end-root", frontend_path] + extra
        except Exception as e:
            print(f"[bold red]Failed to prepare frontend PR: {e}[/bold red]")
            # Continue with default frontend

    process = None

    if "COMFY_CLI_BACKGROUND" not in os.environ:
        # If not running in background mode, there's no need to use popen. This can prevent the issue of linefeeds occurring with tqdm.
        while True:
            res = subprocess.run([python, "main.py"] + extra, env=new_env, check=False)

            if reboot_path is None:
                print("[bold red]ComfyUI is not installed.[/bold red]\n")
                exit(res.returncode)

            if not os.path.exists(reboot_path):
                exit(res.returncode)

            os.remove(reboot_path)
    else:
        # If running in background mode without using a popen, broken pipe errors may occur when flushing stdout/stderr.
        def redirector_stderr():
            while True:
                if process is not None:
                    line = process.stderr.readline()
                    if not line:  # EOF: process ended
                        break
                    output.emit_raw(line)

        def redirector_stdout():
            while True:
                if process is not None:
                    line = process.stdout.readline()
                    if not line:  # EOF: process ended
                        break
                    output.emit_raw(line)

        threading.Thread(target=redirector_stderr).start()
        threading.Thread(target=redirector_stdout).start()

        try:
            while True:
                if sys.platform == "win32":
                    process = subprocess.Popen(
                        [python, "main.py"] + extra,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=new_env,
                        encoding="utf-8",
                        errors="replace",
                        shell=True,  # win32 only
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # win32 only
                    )
                else:
                    process = subprocess.Popen(
                        [python, "main.py"] + extra,
                        text=True,
                        env=new_env,
                        encoding="utf-8",
                        errors="replace",
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                process.wait()

                if reboot_path is None:
                    print("[bold red]ComfyUI is not installed.[/bold red]\n")
                    os._exit(1)

                if not os.path.exists(reboot_path):
                    os._exit(process.returncode)

                os.remove(reboot_path)
        except KeyboardInterrupt:
            if process is not None:
                os._exit(1)


def launch(
    background: bool = False,
    extra: list[str] | None = None,
    frontend_pr: str | None = None,
):
    check_for_updates()
    resolved_workspace = workspace_manager.workspace_path

    if not resolved_workspace:
        print(
            "\nComfyUI is not available.\nTo install ComfyUI, you can run:\n\n\tcomfy install\n\n",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)

    if (extra is None or len(extra) == 0) and workspace_manager.workspace_type == WorkspaceType.DEFAULT:
        launch_extras = workspace_manager.config_manager.config["DEFAULT"].get(
            constants.CONFIG_KEY_DEFAULT_LAUNCH_EXTRAS, ""
        )

        if launch_extras != "":
            extra = launch_extras.split(" ")

    print(f"\nLaunching ComfyUI from: {resolved_workspace}\n")

    # Update the recent workspace
    workspace_manager.set_recent_workspace(resolved_workspace)

    os.chdir(resolved_workspace)
    python = resolve_workspace_python(resolved_workspace)

    # Inject manager flags based on config mode
    manager_flags = _get_manager_flags()
    if manager_flags:
        extra = (extra or []) + manager_flags

    if background:
        background_launch(extra, frontend_pr)
    else:
        launch_comfyui(extra, frontend_pr, python=python)


def _cli_launch_prefix() -> list[str]:
    """Command prefix that re-invokes this CLI for the background child.

    Prefer the installed ``comfy`` console script (upstream behaviour), but fall
    back to ``[sys.executable, "-m", "cli"]`` so that
    ``python -m cli ... launch --background`` still works when the script
    directory is not on PATH — otherwise the child dies immediately with
    "'comfy' is not recognized" and a cryptic empty error panel.
    """
    exe = shutil.which("comfy")
    if exe:
        return [exe]
    return [sys.executable, "-m", "cli"]


def background_launch(extra, frontend_pr=None):
    config_background = ConfigManager().background
    if config_background is not None and utils.is_running(config_background[2]):
        console.print(
            "[bold red]ComfyUI is already running in background.\nYou cannot start more than one background service.[/bold red]\n"
        )
        raise typer.Exit(code=1)

    port = int(constants.default_port())
    listen = constants.default_host()

    if extra is not None:
        for i in range(len(extra) - 1):
            if extra[i] == "--port":
                port = extra[i + 1]
            if extra[i] == "--listen":
                listen = extra[i + 1]

        if len(extra) > 0:
            extra = ["--"] + extra
    else:
        extra = []

    if check_comfy_server_running(port):
        console.print(
            f"[bold red]The {port} port is already in use. A new ComfyUI server cannot be launched.\n[bold red]\n"
        )
        raise typer.Exit(code=1)

    cmd = [
        *_cli_launch_prefix(),
        f"--workspace={os.path.abspath(os.getcwd())}",
        "launch",
    ]

    # Add frontend PR option if specified
    if frontend_pr:
        cmd.extend(["--frontend-pr", frontend_pr])

    cmd.extend(extra)

    loop = asyncio.get_event_loop()
    log = loop.run_until_complete(launch_and_monitor(cmd, listen, port))

    if log is not None:
        console.print(
            Panel(
                "".join(log),
                title="[bold red]Error log during ComfyUI execution[/bold red]",
                border_style="bright_red",
            )
        )

    console.print("\n[bold red]Execution error: failed to launch ComfyUI[/bold red]\n")
    # NOTE: os.exit(0) doesn't work
    os._exit(1)


async def launch_and_monitor(cmd, listen, port):
    """
    Monitor the process during the background launch.

    ComfyUI's output is redirected straight onto the child's own file descriptors
    pointing at a workspace logfile (``<workspace>/user/comfyui_<port>.log``,
    truncate-on-launch), so every line keeps landing in the file even after this
    monitor exits on the success signal (the child outlives the monitor). The
    monitor tails that same file to detect the "To see the GUI go to:" line,
    which is what makes `comfy logs` able to replay the whole run.

    If a success message is captured, record the background info and exit;
    otherwise, return the log in case of failure.
    """
    logging_flag = False
    log = []

    # NOTE: To prevent encoding error on Windows platform
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    env["COMFY_CLI_BACKGROUND"] = "true"
    # Flush the child's stdout per line so the success marker reaches the logfile
    # promptly instead of sitting in a block buffer (stdout is a file, not a tty).
    env["PYTHONUNBUFFERED"] = "1"

    log_path = background_log_path(port)

    # Truncate-on-launch: each background launch starts a fresh log. The child
    # inherits its own dup of this fd, so writes continue after we (the monitor)
    # close our handle and after we os._exit on success. Failing to create the
    # log (read-only / permission-restricted workspace) is reported cleanly
    # rather than aborting the launch with a raw traceback.
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        logfh = _open_log_for_write(log_path)
    except OSError as e:
        print(f"[bold red]Could not open background log file {log_path}: {e}[/bold red]\n")
        os._exit(1)

    # Record the log path up front so `comfy logs` can surface a crash log even
    # when startup fails before the success marker below (where the running
    # background info is recorded).
    cfg = ConfigManager()
    cfg.config["DEFAULT"][constants.CONFIG_KEY_BACKGROUND_LOG] = log_path
    cfg.write_config()

    try:
        if sys.platform == "win32":
            process = subprocess.Popen(
                cmd,
                stdout=logfh,
                stderr=subprocess.STDOUT,
                env=env,
                shell=True,  # win32 only
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # win32 only
            )
        else:
            process = subprocess.Popen(
                cmd,
                stdout=logfh,
                stderr=subprocess.STDOUT,
                env=env,
            )
    finally:
        # The child holds its own fd now; drop the monitor's copy so tailing sees
        # a stable, child-owned writer.
        logfh.close()

    def _handle(line):
        nonlocal logging_flag
        if "Launching ComfyUI from:" in line:
            logging_flag = True
        if "To see the GUI go to:" in line:
            print(
                f"[bold yellow]ComfyUI is successfully launched in the background.[/bold yellow]\nTo see the GUI go to: http://{listen}:{port}"
            )
            # CONFIG_KEY_BACKGROUND_LOG was already recorded before launch; here
            # we add the running background info now that startup succeeded.
            c = ConfigManager()
            c.config["DEFAULT"][constants.CONFIG_KEY_BACKGROUND] = f"{(listen, port, process.pid)}"
            c.config["DEFAULT"][constants.CONFIG_KEY_BACKGROUND_LOG] = log_path
            c.write_config()

            # NOTE: os.exit(0) doesn't work.
            os._exit(0)
        if logging_flag:
            log.append(line)

    # Tail the logfile the child is writing, reassembling whole lines (a
    # concurrent writer can leave a trailing partial line without a newline).
    with open(log_path, encoding="utf-8", errors="replace") as reader:
        pending = ""
        while True:
            chunk = reader.readline()
            if chunk:
                pending += chunk
                if pending.endswith("\n") or process.poll() is not None:
                    _handle(pending)
                    pending = ""
                # else: partial line — wait for the rest before acting.
            else:
                if process.poll() is not None:
                    if pending:
                        _handle(pending)
                    break
                time.sleep(0.1)

    return log


# ---------------------------------------------------------------------------
# Background log capture and `comfy logs`
# ---------------------------------------------------------------------------

# Caps so `--json` payloads stay bounded even when `--tail` is huge against a
# long-running server's log.
LOGS_MAX_LINES = 2000
LOGS_MAX_BYTES = 256 * 1024

DEFAULT_LOG_PORT = 8188

# ComfyUI-Manager rotates its logfile on startup: `comfyui.log` becomes
# `comfyui.prev.log`, and the previous `.prev` becomes `.prev2`. Those rotations
# are stale by construction, so the glob fallback must never serve one.
_ROTATED_LOG_RE = re.compile(r"\.prev\d*\.log$")

# `<workspace>/user/comfyui_<port>.log` — the suffix carries the port the server
# served, which is what makes a port mismatch detectable after the fact.
_PORTED_LOG_RE = re.compile(r"^comfyui_(\d+)\.log$")


def background_log_path(port, workspace: str | None = None) -> str:
    """Path to the persisted background ComfyUI log for ``port``.

    ``<workspace>/user/comfyui_<port>.log`` — the port disambiguates multiple
    servers sharing one workspace, and truncate-on-launch means a fresh run
    starts a fresh log. ``workspace`` defaults to the resolved workspace (or cwd).
    """
    ws = workspace or workspace_manager.workspace_path or os.getcwd()
    return os.path.join(ws, "user", f"comfyui_{port}.log")


def unsuffixed_log_path(workspace: str) -> str:
    """``<workspace>/user/comfyui.log`` — ComfyUI-Manager's own logfile.

    Manager only appends ``_<port>`` when ``--port`` is in ComfyUI's argv, so a
    server started outside ``comfy launch --background`` (foreground, desktop
    app, no explicit ``--port``) logs here and nowhere else.
    """
    return os.path.join(workspace, "user", "comfyui.log")


def _open_log_for_write(log_path: str):
    """Open ``log_path`` for a truncating write, refusing to follow a symlink.

    ``O_NOFOLLOW`` (where available) plus restrictive permissions keeps a
    pre-planted symlink from redirecting the write elsewhere.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(log_path, flags, 0o600)
    return os.fdopen(fd, "w", encoding="utf-8")


def _path_within(path: str, directory: str) -> bool:
    """True when ``path`` lies inside ``directory``, compared lexically.

    Deliberately does NOT touch the filesystem (no ``realpath``): the caller only
    needs to know whether a *recorded* path claims to belong to the current
    workspace, and that must stay answerable for a file that no longer exists.
    """
    try:
        target = os.path.normcase(os.path.abspath(path))
        root = os.path.normcase(os.path.abspath(directory))
    except (OSError, ValueError):
        return False
    return target == root or target.startswith(root.rstrip(os.sep) + os.sep)


def _newest_globbed_log(pattern: str) -> str | None:
    """Newest-mtime match of ``pattern``, ignoring ComfyUI-Manager's rotations.

    Symlinks are skipped so a planted link cannot make `comfy logs` disclose a
    file outside the workspace.
    """
    directory, filename = os.path.split(pattern)
    newest: str | None = None
    newest_mtime = float("-inf")
    for path in glob.glob(os.path.join(glob.escape(directory), filename)):
        if _ROTATED_LOG_RE.search(os.path.basename(path)):
            continue
        try:
            # lstat, not stat: a symlink must not be resolved to its target here.
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode):
                continue
            mtime = st.st_mtime
        except OSError:
            # Raced away between glob and lstat, or unreadable — not a candidate.
            continue
        if mtime > newest_mtime:
            newest, newest_mtime = path, mtime
    return newest


def candidate_log_paths(port: int | None = None) -> list[tuple[str, str]]:
    """The ordered candidates `comfy logs` considers, existing or not.

    Each entry is ``(path, source)``; the ``fallback_glob`` entry's "path" is a
    glob PATTERN rather than a concrete file. Kept separate from resolution so
    the miss path can report everything that was checked.
    """
    workspace = workspace_manager.workspace_path

    if port is not None:
        if not workspace:
            return []
        return [
            (background_log_path(port, workspace), "explicit_port"),
            (unsuffixed_log_path(workspace), "fallback_unsuffixed"),
        ]

    cfg = ConfigManager()
    recorded = cfg.get(constants.CONFIG_KEY_BACKGROUND_LOG)

    if not workspace:
        # Nothing local to prefer it over, and nothing else to check.
        return [(recorded, "recorded")] if recorded else []

    live_port = cfg.background[1] if cfg.background else None
    derived_port = live_port if live_port is not None else DEFAULT_LOG_PORT
    local: list[tuple[str, str]] = [
        (
            background_log_path(derived_port, workspace),
            "derived_port" if live_port is not None else "default_port",
        ),
        (unsuffixed_log_path(workspace), "fallback_unsuffixed"),
        (os.path.join(workspace, "user", "comfyui_*.log"), "fallback_glob"),
    ]

    if not recorded:
        return local

    # The recorded pointer outranks the workspace-local candidates only when it
    # is still relevant here: either the background server it describes is live,
    # or it names a file inside the current workspace (the crash-log case — the
    # pointer deliberately survives `comfy stop`). Otherwise it points into some
    # OTHER workspace left over from an earlier run, so demote it to last.
    if live_port is not None or _path_within(recorded, workspace):
        return [(recorded, "recorded"), *local]
    return [*local, (recorded, "recorded")]


def resolve_background_log_path(port: int | None = None) -> tuple[str, str] | None:
    """Locate a ComfyUI logfile, returning ``(path, source)`` for the first
    candidate of :func:`candidate_log_paths` that actually exists.

    Returns None when no candidate exists — including the "no workspace resolves
    and nothing was recorded" case, where there is nothing to check at all.
    """
    for path, source in candidate_log_paths(port):
        if source == "fallback_glob":
            match = _newest_globbed_log(path)
            if match:
                return match, source
        elif os.path.isfile(path):
            return path, source
    return None


def read_log_tail(
    path: str,
    n: int,
    *,
    max_lines: int = LOGS_MAX_LINES,
    max_bytes: int = LOGS_MAX_BYTES,
) -> tuple[list[str], bool]:
    """Return ``(lines, truncated)`` — the last ``n`` lines of ``path``.

    Bounded so machine output stays small: at most ``max_lines`` lines and
    ``max_bytes`` bytes (whichever binds first), trimmed from the top.
    """
    n = max(0, n)
    want = min(n, max_lines)

    tail: deque[str] = deque(maxlen=want) if want > 0 else deque(maxlen=0)
    total = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            tail.append(line)
            total += 1

    lines = list(tail)
    truncated = n > max_lines and total > max_lines

    size = sum(len(line.encode("utf-8")) for line in lines)
    while len(lines) > 1 and size > max_bytes:
        size -= len(lines.pop(0).encode("utf-8"))
        truncated = True

    if lines and size > max_bytes:
        lines[-1] = lines[-1].encode("utf-8")[-max_bytes:].decode("utf-8", errors="replace")
        truncated = True

    return lines, truncated


def _served_log_port(path: str) -> int | None:
    """The port encoded in a ``comfyui_<port>.log`` filename, else None."""
    match = _PORTED_LOG_RE.match(os.path.basename(path))
    return int(match.group(1)) if match else None


def _follow_log(log_path: str, tail: int, *, json_output: bool = False, source: str = "", served_port: int | None = None):
    """Print the last ``tail`` lines, then stream new lines until Ctrl+C."""
    with open(log_path, encoding="utf-8", errors="replace") as f:
        buf: deque[str] = deque(maxlen=max(0, tail))
        for line in f:
            buf.append(line)

        if json_output:
            output.emit_json(
                {
                    "ok": True,
                    "path": log_path,
                    "source": source,
                    "served_port": served_port,
                    "follow": True,
                    "initial": [line.rstrip("\n") for line in buf],
                }
            )
        else:
            console.print(f"[dim]{log_path}  (following — Ctrl+C to stop)[/dim]")
            for line in buf:
                output.emit_raw(line)

        try:
            while True:
                line = f.readline()
                if line:
                    if json_output:
                        output.emit_json({"line": line.rstrip("\n")})
                    else:
                        output.emit_raw(line)
                else:
                    time.sleep(0.3)
        except KeyboardInterrupt:
            if not json_output:
                console.print("\n[dim]stopped[/dim]")


def logs(
    tail: int = 200,
    port: int | None = None,
    path: str | None = None,
    follow: bool = False,
    json_output: bool = False,
):
    """Print the tail of a captured ComfyUI log (entry point for `comfy logs`).

    Resolution walks :func:`candidate_log_paths` — the path recorded by
    `comfy launch --background`, the port-derived logfile, ComfyUI-Manager's
    unsuffixed ``user/comfyui.log``, then the newest ``user/comfyui_*.log`` — so
    a server started outside `comfy launch --background` is still readable.
    """
    if path is not None:
        resolved: tuple[str, str] | None = (path, "explicit_path") if os.path.isfile(path) else None
        checked = [path]
    else:
        resolved = resolve_background_log_path(port)
        checked = [p for p, _ in candidate_log_paths(port)]

    if resolved is None:
        message = "No captured ComfyUI log was found."
        if checked:
            message += " Looked for: " + ", ".join(checked)
        if json_output:
            output.emit_json({"ok": False, "error": "no_log_file", "message": message, "checked": checked})
        else:
            console.print(f"[bold red]{message}[/bold red]")
            console.print("[dim]Start ComfyUI with `comfy launch --background` so its output is captured.[/dim]")
        raise typer.Exit(code=1)

    log_path, source = resolved
    served_port = _served_log_port(log_path)

    if follow:
        _follow_log(log_path, tail, json_output=json_output, source=source, served_port=served_port)
        return

    lines, truncated = read_log_tail(log_path, tail)

    if json_output:
        output.emit_json(
            {
                "ok": True,
                "path": log_path,
                "source": source,
                "served_port": served_port,
                "count": len(lines),
                "truncated": truncated,
                "lines": [line.rstrip("\n") for line in lines],
            }
        )
    else:
        console.print(f"[dim]{log_path}  (source: {source}, showing last {len(lines)} lines)[/dim]")
        for line in lines:
            output.emit_raw(line)
