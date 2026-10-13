import os
import subprocess
import sys
import webbrowser
from typing import Annotated

import questionary
import typer
from rich import print as rprint
from rich.console import Console

from cli import constants, env_checker, logging_utils, tracking, ui, utils
from cli.command import code_search, custom_nodes, pr_command
from cli.command import generate as generate_command
from cli.command import install as install_inner
from cli.command import jobs as jobs_command
from cli.command import run as run_inner
from cli.command import setup as setup_command
from cli.command import system as system_command
from cli.command import templates as templates_command
from cli.command import transfer as transfer_command
from cli.command.install import validate_version
from cli.command.launch import launch as launch_command
from cli.command.launch import logs as launch_logs
from cli.command.models import models as models_command
from cli.config_manager import ConfigManager
from cli.constants import GPU_OPTION, CUDAVersion, ROCmVersion
from cli.cuda_detect import DEFAULT_CUDA_TAG, detect_cuda_driver_version, resolve_cuda_wheel
from cli.env_checker import EnvChecker
from cli.resolve_python import resolve_workspace_python
from cli.standalone import StandalonePython
from cli.update import check_for_updates
from cli.uv import DependencyCompiler
from cli.workspace_manager import WorkspaceManager, check_comfy_repo

# 本地 ComfyUI 绝不应经由 HTTP 代理访问。沙箱/企业环境常设置 HTTP_PROXY/HTTPS_PROXY
# 且未设 NO_PROXY，会让 requests/urllib 把 127.0.0.1 也走代理并返回 502。
# 这里把 loopback 加进 NO_PROXY/no_proxy，使全部命令（含 requests 与 urllib）直连本地。
def _ensure_loopback_no_proxy() -> None:
    for key in ("NO_PROXY", "no_proxy"):
        existing = {h.strip() for h in os.environ.get(key, "").split(",") if h.strip()}
        existing |= {"127.0.0.1", "localhost", "::1"}
        os.environ[key] = ",".join(sorted(existing))


_ensure_loopback_no_proxy()

logging_utils.setup_logging()
app = typer.Typer()
workspace_manager = WorkspaceManager()

console = Console()


def main():
    app()


class MutuallyExclusiveValidator:
    def __init__(self):
        self.group = []

    def reset_for_testing(self):
        self.group.clear()

    def validate(self, _ctx: typer.Context, param: typer.CallbackParam, value: str):
        # Add cli option to group if it was called with a value
        if value is not None and param.name not in self.group:
            self.group.append(param.name)
        if len(self.group) > 1:
            raise typer.BadParameter(f"option `{param.name}` is mutually exclusive with option `{self.group.pop()}`")
        return value


g_exclusivity = MutuallyExclusiveValidator()
g_gpu_exclusivity = MutuallyExclusiveValidator()


@app.command(help="Display help for commands")
def help(ctx: typer.Context):
    rprint(ctx.find_root().get_help())
    ctx.exit(0)


@app.callback(invoke_without_command=True)
def entry(
    ctx: typer.Context,
    workspace: Annotated[
        str | None,
        typer.Option(
            show_default=False,
            help="Path to ComfyUI workspace",
            callback=g_exclusivity.validate,
        ),
    ] = None,
    recent: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Execute from recent path",
            callback=g_exclusivity.validate,
        ),
    ] = None,
    here: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Execute from current path",
            callback=g_exclusivity.validate,
        ),
    ] = None,
    skip_prompt: Annotated[
        bool,
        typer.Option(
            show_default=False,
            help="Do not prompt user for input, use default options",
        ),
    ] = False,
    enable_telemetry: Annotated[
        bool,
        typer.Option(
            show_default=False,
            hidden=True,
            help="Enable tracking",
        ),
    ] = False,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Print version and exit",
    ),
):
    if version:
        rprint(ConfigManager().get_cli_version())
        ctx.exit(0)

    workspace_manager.setup_workspace_manager(workspace, here, recent, skip_prompt)

    tracking.prompt_tracking_consent(skip_prompt, default_value=enable_telemetry)

    if ctx.invoked_subcommand is None:
        rprint("[bold yellow]Welcome to Comfy CLI![/bold yellow]: https://github.com/Comfy-Org/comfy-cli")
        rprint(ctx.get_help())
        ctx.exit()

    # TODO: Move this to proper place
    # start_time = time.time()
    # workspace_manager.scan_dir()
    # end_time = time.time()
    #
    # logging_utils.info(f"scan_dir took {end_time - start_time:.2f} seconds to run")


def validate_commit_and_version(commit: str | None, ctx: typer.Context) -> str | None:
    """
    Validate that the commit is not specified unless the version is 'nightly'.
    """
    version = ctx.params.get("version")
    if commit and version != "nightly":
        raise typer.BadParameter("You can only specify the commit if the version is 'nightly'.")
    return commit


def _resolve_cuda(
    gpu: GPU_OPTION | None,
    cuda_version: CUDAVersion | None,
) -> tuple[CUDAVersion | None, str | None]:
    """Resolve the CUDA wheel tag for an NVIDIA install.

    Returns (cuda_version_enum_or_None, cuda_tag_string_or_None).
    When the user passed an explicit --cuda-version, that is used as-is.
    Otherwise auto-detection is attempted.
    """
    if gpu != GPU_OPTION.NVIDIA:
        return cuda_version, None

    if cuda_version is not None:
        tag = f"cu{cuda_version.value.replace('.', '')}"
        rprint(f"[bold]Using explicit CUDA version:[/bold] {cuda_version.value} ({tag})")
        return cuda_version, tag

    drv = detect_cuda_driver_version()
    if drv is not None:
        tag = resolve_cuda_wheel(drv)
        if tag is not None:
            rprint(f"[bold green]Detected CUDA driver version:[/bold green] {drv[0]}.{drv[1]} → using {tag}")
            return None, tag
        rprint(
            f"[bold yellow]Warning:[/bold yellow] CUDA driver {drv[0]}.{drv[1]} is too old for any known PyTorch wheel. "
            f"Falling back to {DEFAULT_CUDA_TAG}. Use `--cuda-version` to override."
        )
        return None, DEFAULT_CUDA_TAG

    rprint(
        f"[bold yellow]Warning:[/bold yellow] Could not detect CUDA driver version. "
        f"Falling back to {DEFAULT_CUDA_TAG}. Use `--cuda-version` to override."
    )
    return None, DEFAULT_CUDA_TAG


@app.command(help="Download and install ComfyUI and ComfyUI-Manager")
@tracking.track_command()
def install(
    url: Annotated[
        str,
        typer.Option(
            show_default=False,
            help="url or local path pointing to the ComfyUI core git repo to be installed. A specific branch can optionally be specified using a setuptools-like syntax, eg https://foo.git@bar",
        ),
    ] = constants.COMFY_GITHUB_URL,
    version: Annotated[
        str,
        typer.Option(
            show_default=False,
            help="Specify version of ComfyUI to install. Default is nightl, which is the latest commit on master branch. Other options include: latest, which is the latest stable release. Or a specific version number, eg. 0.2.0",
            callback=validate_version,
        ),
    ] = "nightly",
    restore: Annotated[
        bool,
        typer.Option(
            show_default=False,
            help="Restore dependencies for installed ComfyUI if not installed",
        ),
    ] = False,
    skip_manager: Annotated[
        bool,
        typer.Option(show_default=False, help="Skip installing the manager component"),
    ] = False,
    skip_torch_or_directml: Annotated[
        bool,
        typer.Option(show_default=False, help="Skip installing PyTorch Or DirectML"),
    ] = False,
    skip_requirement: Annotated[
        bool, typer.Option(show_default=False, help="Skip installing requirements.txt")
    ] = False,
    nvidia: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Install for Nvidia gpu",
            callback=g_gpu_exclusivity.validate,
        ),
    ] = None,
    cuda_version: Annotated[CUDAVersion | None, typer.Option(show_default=False)] = None,
    rocm_version: Annotated[ROCmVersion, typer.Option(show_default=True)] = ROCmVersion.v6_3,
    amd: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Install for AMD gpu",
            callback=g_gpu_exclusivity.validate,
        ),
    ] = None,
    m_series: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Install for Mac M-Series gpu",
            callback=g_gpu_exclusivity.validate,
        ),
    ] = None,
    intel_arc: Annotated[
        bool | None,
        typer.Option(
            hidden=True,
            show_default=False,
            help="Install for Intel Arc gpu",
            callback=g_gpu_exclusivity.validate,
        ),
    ] = None,
    cpu: Annotated[
        bool | None,
        typer.Option(
            show_default=False,
            help="Install for CPU",
            callback=g_gpu_exclusivity.validate,
        ),
    ] = None,
    commit: Annotated[
        str | None, typer.Option(help="Specify commit hash for ComfyUI", callback=validate_commit_and_version)
    ] = None,
    fast_deps: Annotated[
        bool,
        typer.Option(
            "--fast-deps",
            show_default=False,
            help="Use uv instead of pip for dependency resolution (comfy-cli built-in resolver)",
        ),
    ] = False,
    pr: Annotated[
        str | None,
        typer.Option(
            show_default=False,
            help="Install from a specific PR. Supports formats: username:branch, #123, or PR URL",
        ),
    ] = None,
):
    check_for_updates()
    checker = EnvChecker()

    comfy_path, _ = workspace_manager.get_workspace_path()

    is_comfy_installed_at_path, resolved_path = check_comfy_repo(comfy_path)
    if is_comfy_installed_at_path and not restore:
        rprint(f"[bold red]ComfyUI is already installed at the specified path:[/bold red] {comfy_path}\n")
        rprint(
            "[bold yellow]If you want to restore dependencies, add the '--restore' option.[/bold yellow]",
        )
        raise typer.Exit(code=1)

    if resolved_path is not None:
        comfy_path = resolved_path

    if checker.python_version.major < 3 or checker.python_version.minor < 9:
        rprint("[bold red]Python version 3.9 or higher is required to run ComfyUI.[/bold red]")
        rprint(f"You are currently using Python version {env_checker.format_python_version(checker.python_version)}.")
    platform = utils.get_os()

    if pr and (version not in {None, "nightly"} or commit):
        rprint("--pr cannot be used with --version or --commit")
        raise typer.Exit(code=1)

    if cpu:
        rprint("[bold yellow]Installing for CPU[/bold yellow]")
        install_inner.execute(
            url,
            comfy_path,
            restore,
            skip_manager,
            commit=commit,
            version=version,
            gpu=None,
            cuda_version=cuda_version,
            cuda_tag=None,
            rocm_version=rocm_version,
            plat=platform,
            skip_torch_or_directml=skip_torch_or_directml,
            skip_requirement=skip_requirement,
            fast_deps=fast_deps,
            pr=pr,
        )
        rprint(f"ComfyUI is installed at: {comfy_path}")
        return None

    if nvidia and platform == constants.OS.MACOS:
        rprint("[bold red]Nvidia GPU is never on MacOS. What are you smoking? 🤔[/bold red]")
        raise typer.Exit(code=1)

    if platform != constants.OS.MACOS and m_series:
        rprint(f"[bold red]You are on {platform} bruh [/bold red]")

    gpu = None

    if nvidia:
        gpu = GPU_OPTION.NVIDIA
    elif amd:
        gpu = GPU_OPTION.AMD
    elif m_series:
        gpu = GPU_OPTION.MAC_M_SERIES
    elif intel_arc:
        gpu = GPU_OPTION.INTEL_ARC
    else:
        if platform == constants.OS.MACOS:
            gpu = ui.prompt_select_enum(
                "What type of Mac do you have?",
                [GPU_OPTION.MAC_M_SERIES, GPU_OPTION.MAC_INTEL],
            )
        else:
            gpu = ui.prompt_select_enum(
                "What GPU do you have?",
                [GPU_OPTION.NVIDIA, GPU_OPTION.AMD, GPU_OPTION.INTEL_ARC],
            )

    if gpu is None and not cpu:
        rprint(
            "[bold red]No GPU option selected or `--cpu` enabled, use --\\[gpu option] flag (e.g. --nvidia) to pick GPU. use `--cpu` to install for CPU. Exiting...[/bold red]"
        )
        raise typer.Exit(code=1)

    cuda_version, cuda_tag = _resolve_cuda(gpu, cuda_version) if not skip_torch_or_directml else (cuda_version, None)

    install_inner.execute(
        url,
        comfy_path,
        restore,
        skip_manager,
        commit=commit,
        gpu=gpu,
        version=version,
        cuda_version=cuda_version,
        cuda_tag=cuda_tag,
        rocm_version=rocm_version,
        plat=platform,
        skip_torch_or_directml=skip_torch_or_directml,
        skip_requirement=skip_requirement,
        fast_deps=fast_deps,
        pr=pr,
    )

    rprint(f"ComfyUI is installed at: {comfy_path}")


@app.command(help="Update ComfyUI Environment [all|comfy|cli]")
@tracking.track_command()
def update(
    target: str = typer.Argument(
        "comfy",
        help="[all|comfy|cli]",
        autocompletion=utils.create_choice_completer(["all", "comfy", "cli"]),
    ),
):
    if target not in ["all", "comfy", "cli"]:
        typer.echo(
            f"Invalid target: {target}. Allowed targets are 'all', 'comfy', 'cli'.",
            err=True,
        )
        raise typer.Exit(code=1)

    if "cli" == target:
        # 升级 CLI 自身（对齐官方 `comfy update cli`）。本项目未发布 PyPI 包，
        # 优先尝试 PyPI 升级，失败则从本仓库源码强制重装。
        python = sys.executable
        rprint("Updating Comfy CLI ...")
        rc = subprocess.run(
            [python, "-m", "pip", "install", "--upgrade", "comfyui-omni-controller"]
        )
        if rc.returncode != 0:
            src = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            rprint(f"[yellow]PyPI upgrade unavailable, reinstalling from source: {src}[/yellow]")
            subprocess.run([python, "-m", "pip", "install", "--force-reinstall", src], check=True)
        return

    comfy_path = workspace_manager.workspace_path

    if "all" == target:
        custom_nodes.command.execute_cm_cli(["update", "all"])
    else:
        rprint(f"Updating ComfyUI in {comfy_path}...")
        if comfy_path is None:
            rprint("ComfyUI path is not found.")
            raise typer.Exit(code=1)
        os.chdir(comfy_path)
        subprocess.run(["git", "pull"], check=True)
        python = resolve_workspace_python(comfy_path)
        subprocess.run(
            [python, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
        )

    try:
        custom_nodes.command.update_node_id_cache()
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        rprint(f"[yellow]Failed to update node id cache: {e}[/yellow]")


@app.command(
    help=(
        "Run a workflow on the ComfyUI launched by `comfy launch --background`. "
        "Accepts both ComfyUI API format and exported UI workflow JSON; "
        "UI workflows are converted to API format client-side via /object_info."
    )
)
def run(
    workflow: Annotated[
        str,
        typer.Option(
            help=(
                "Path to the workflow JSON file. Both ComfyUI API format and "
                "exported UI format are accepted; UI workflows are converted "
                "to API format client-side."
            )
        ),
    ],
    wait: Annotated[
        bool,
        typer.Option(help="If the command should wait until execution completes."),
    ] = True,
    verbose: Annotated[
        bool,
        typer.Option(help="Enables verbose output of the execution process."),
    ] = False,
    host: Annotated[
        str | None,
        typer.Option(help="The IP/hostname where the ComfyUI instance is running, e.g. 127.0.0.1 or localhost."),
    ] = None,
    port: Annotated[
        int | None,
        typer.Option(help="The port where the ComfyUI instance is running. "
                          "Defaults to $COMFYUI_PORT, else 8188 (ComfyUI upstream default). "
                          "3198 was a single deployment's port, not a standard."),
    ] = None,
    timeout: Annotated[
        int,
        typer.Option(
            help=(
                "Per-event timeout in seconds: bails out if the server is silent "
                "for this long. Also caps HTTP connect, /prompt POST, and websocket "
                "handshake. NOT a wall-clock execution deadline — a workflow that "
                "streams progress events faster than the timeout can run "
                "indefinitely."
            ),
        ),
    ] = 120,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            envvar="COMFY_API_KEY",
            help=(
                "Comfy API key for API Nodes (Partner Nodes). "
                "Embedded in the POST /prompt request body as extra_data.api_key_comfy_org. "
                "For scripting, prefer the COMFY_API_KEY environment variable so the secret "
                "stays out of shell history."
            ),
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help=(
                "Emit NDJSON events to stdout instead of human-readable output. "
                "One JSON object per line, terminated by \\n. See docs/json-output.md "
                "for the event reference and stability contract. In this mode, "
                "--verbose has no effect and Rich progress is suppressed. "
                "Workflow input accepts both API and UI format JSON (UI input "
                "triggers a `converted` event before `queued`). The converted "
                "workflow graph is always emitted as a `prompt_preview` event "
                "before `queued`, so agents have a full audit trail of what "
                "the CLI submitted."
            ),
        ),
    ] = False,
    print_prompt: Annotated[
        bool,
        typer.Option(
            "--print-prompt",
            help=(
                "Print the API-format workflow graph that WOULD be sent to /prompt and exit. "
                "Does not POST and does not execute. For UI-format input the workflow is "
                "converted first (requires a reachable ComfyUI for /object_info); API input "
                "is printed as-is with no server hit. In --json mode emits a `prompt_preview` "
                "event; otherwise pretty-prints to stdout."
            ),
        ),
    ] = False,
):
    # Snapshot kwargs before the body mutates api_key/host/port — analytics should record what user actually supplied.
    _track_props = tracking.filter_command_kwargs(dict(locals()))
    tracking.track_event("execution_start", _track_props, mixpanel_name="run")

    try:
        if api_key:
            api_key = api_key.strip() or None

        config = ConfigManager()

        if host:
            s = host.split(":")
            host = s[0]
            if not port and len(s) == 2:
                port = int(s[1])

        if config.background:
            bg_host, bg_port = config.background[0], config.background[1]
            if not host:
                host = bg_host
            if not port:
                port = bg_port

        if not host:
            host = constants.default_host()
        if not port:
            port = int(constants.default_port())

        run_inner.execute(
            workflow,
            host,
            port,
            wait,
            verbose,
            timeout,
            api_key=api_key,
            json_mode=json_output,
            print_prompt=print_prompt,
        )
    except typer.Exit as e:
        if (e.exit_code or 0) == 0:
            tracking.track_event("execution_success", _track_props)
        else:
            tracking.track_event(
                "execution_error",
                {**_track_props, "error_type": type(e).__name__, "exit_code": e.exit_code},
            )
        raise
    except Exception as e:
        tracking.track_event(
            "execution_error",
            {**_track_props, "error_type": type(e).__name__},
        )
        raise
    else:
        tracking.track_event("execution_success", _track_props)


def validate_comfyui(_env_checker):
    if _env_checker.comfy_repo is None:
        rprint("[bold red]If ComfyUI is not installed, this feature cannot be used.[/bold red]")
        raise typer.Exit(code=1)


@app.command(help="Stop background ComfyUI")
@tracking.track_command()
def stop():
    if constants.CONFIG_KEY_BACKGROUND not in ConfigManager().config["DEFAULT"]:
        rprint("[bold red]No ComfyUI is running in the background.[/bold red]\n")
        raise typer.Exit(code=1)

    bg_info = ConfigManager().background
    if not bg_info:
        rprint("[bold red]No ComfyUI is running in the background.[/bold red]\n")
        raise typer.Exit(code=1)
    is_killed = utils.kill_all(bg_info[2])

    if not is_killed:
        rprint("[bold red]Failed to stop ComfyUI in the background.[/bold red]\n")
    else:
        rprint(f"[bold yellow]Background ComfyUI is stopped.[/bold yellow] ({bg_info[0]}:{bg_info[1]})")

    ConfigManager().remove_background()


@app.command(help="Show the captured ComfyUI log (from `comfy launch --background`, or ComfyUI-Manager's logfile)")
@tracking.track_command()
def logs(
    tail: Annotated[int, typer.Option("--tail", "-n", help="Number of trailing log lines to show")] = 200,
    port: Annotated[
        int | None,
        typer.Option("--port", "-p", help="Show the log for this port instead of auto-resolving"),
    ] = None,
    path: Annotated[str | None, typer.Option("--path", help="Show this specific log file instead of auto-resolving")] = None,
    follow: Annotated[
        bool,
        typer.Option("--follow", "-f", help="Keep printing new lines as they are written (Ctrl+C to stop)"),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit a structured JSON envelope")] = False,
):
    launch_logs(tail=tail, port=port, path=path, follow=follow, json_output=json_output)


@app.command(help="Launch ComfyUI: ?[--background] ?[-- <extra args ...>]")
@tracking.track_command()
def launch(
    extra: list[str] = typer.Argument(None),
    background: Annotated[bool, typer.Option(help="Launch ComfyUI in background")] = False,
    frontend_pr: Annotated[
        str | None,
        typer.Option(
            "--frontend-pr",
            show_default=False,
            help="Use a specific frontend PR. Supports formats: username:branch, #123, or PR URL",
        ),
    ] = None,
):
    launch_command(background, extra, frontend_pr)


@app.command("set-default", help="Set default ComfyUI path")
@tracking.track_command()
def set_default(
    workspace_path: str,
    launch_extras: Annotated[str, typer.Option(help="Specify extra options for launch")] = "",
):
    comfy_path = os.path.abspath(os.path.expanduser(workspace_path))

    if not os.path.exists(comfy_path):
        rprint(
            f"\nPath not found: {comfy_path}.\n",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)

    is_comfy_repo, resolved_path = check_comfy_repo(comfy_path)
    if not is_comfy_repo:
        rprint(
            f"\nSpecified path is not a ComfyUI path: {comfy_path}.\n",
            file=sys.stderr,
        )
        raise typer.Exit(code=1)

    comfy_path = resolved_path

    rprint(f"Specified path is set as default ComfyUI path: {comfy_path} ")
    workspace_manager.set_default_workspace(comfy_path)
    workspace_manager.set_default_launch_extras(launch_extras)


@app.command(help="Show which ComfyUI is selected.")
@tracking.track_command()
def which():
    comfy_path = workspace_manager.workspace_path
    if comfy_path is None:
        rprint(
            "ComfyUI not found, please run 'comfy install', run 'comfy' in a ComfyUI directory, or specify the workspace path with '--workspace'."
        )
        raise typer.Exit(code=1)

    rprint(f"Target ComfyUI path: {comfy_path}")


@app.command(help="Print out current environment variables.")
@tracking.track_command()
def env():
    check_for_updates()
    env_data = EnvChecker().fill_print_table()
    workspace_data = workspace_manager.fill_print_table()
    all_data = env_data + workspace_data
    ui.display_table(
        data=all_data,
        column_names=[":laptop_computer: Environment", "Value"],
        title="Environment Information",
    )


def _resolve_host_port(host: str | None, port: int | None) -> tuple[str, int]:
    """解析目标 ComfyUI 地址。优先级：显式 --host/--port > 后台实例 > 环境变量 > 默认。

    与 `comfy run` 的解析逻辑保持一致，供 system-stats/free/download/upload 复用。
    """
    config = ConfigManager()
    if host:
        s = host.split(":")
        host = s[0]
        if not port and len(s) == 2 and s[1]:
            port = int(s[1])
    if config.background:
        bg_host, bg_port = config.background[0], config.background[1]
        if not host:
            host = bg_host
        if not port:
            port = bg_port
    if not host:
        host = constants.default_host()
    if not port:
        port = int(constants.default_port())
    return host, port


@app.command("system-stats", help="Show ComfyUI device VRAM / system RAM stats")
@tracking.track_command()
def system_stats(
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw /system_stats JSON")] = False,
):
    h, p = _resolve_host_port(host, port)
    system_command.system_stats_execute(h, p, json_output=json_output)


@app.command(help="Free ComfyUI memory: unload models and/or reset the executor cache")
@tracking.track_command()
def free(
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    unload_models: Annotated[bool, typer.Option("--unload-models/--no-unload-models", help="Unload models")] = True,
    free_memory: Annotated[bool, typer.Option("--free-memory", help="Also reset the executor cache")] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit a structured JSON envelope")] = False,
):
    h, p = _resolve_host_port(host, port)
    system_command.free_execute(h, p, unload_models=unload_models, free_memory=free_memory, json_output=json_output)


@app.command(help="Download a run's outputs by prompt id")
@tracking.track_command()
def download(
    prompt_id: Annotated[str, typer.Argument(help="Prompt id returned by `comfy run` / POST /prompt")],
    output: Annotated[str, typer.Option("--output", "-o", help="Output directory")] = ".",
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit a structured JSON result")] = False,
):
    h, p = _resolve_host_port(host, port)
    transfer_command.download_execute(prompt_id, output, h, p, json_output=json_output)


@app.command(help="Upload a file to the ComfyUI server's input directory")
@tracking.track_command()
def upload(
    file: Annotated[str, typer.Argument(help="Local file path to upload")],
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit raw upload JSON")] = False,
):
    h, p = _resolve_host_port(host, port)
    transfer_command.upload_execute(file, h, p, json_output=json_output)


@jobs_command.jobs_app.command("ls", help="List running/pending jobs and recent history")
def jobs_ls(
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit structured JSON")] = False,
):
    h, p = _resolve_host_port(host, port)
    jobs_command.jobs_ls(h, p, json_output=json_output)


@jobs_command.jobs_app.command("status", help="Show the status of a job by prompt id")
def jobs_status(
    prompt_id: Annotated[str, typer.Argument(help="Prompt id")],
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit the full history entry JSON")] = False,
):
    h, p = _resolve_host_port(host, port)
    jobs_command.jobs_status(prompt_id, h, p, json_output=json_output)


@jobs_command.jobs_app.command("wait", help="Block until a job completes")
def jobs_wait(
    prompt_id: Annotated[str, typer.Argument(help="Prompt id")],
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    timeout: Annotated[int, typer.Option(help="Max seconds to wait")] = 600,
    json_output: Annotated[bool, typer.Option("--json", help="Emit the final history entry JSON")] = False,
):
    h, p = _resolve_host_port(host, port)
    jobs_command.jobs_wait(prompt_id, h, p, timeout=timeout, json_output=json_output)


@jobs_command.jobs_app.command("watch", help="Poll and print job status changes")
def jobs_watch(
    prompt_id: Annotated[str, typer.Argument(help="Prompt id")],
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    interval: Annotated[float, typer.Option(help="Poll interval in seconds")] = 1.0,
):
    h, p = _resolve_host_port(host, port)
    jobs_command.jobs_watch(prompt_id, h, p, interval=interval)


templates_app = typer.Typer(help="Browse and run official ComfyUI workflow templates.")


@templates_app.command("ls", help="List gallery templates (name / category / description)")
def templates_ls(
    name: Annotated[str | None, typer.Option("--name", help="Substring match on template name")] = None,
    limit: Annotated[int, typer.Option(help="Limit rows")] = 0,
    refresh: Annotated[bool, typer.Option("--refresh", help="Re-fetch index.json")] = False,
    gallery: Annotated[str | None, typer.Option(show_default=False, help="Path to a local index.json")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit JSON rows")] = False,
):
    templates_command.templates_ls(name_sub=name, limit=limit, refresh=refresh, gallery=gallery, json_output=json_output)


@app.command("run-template", help="Fetch an official template workflow and run it")
def run_template(
    name: Annotated[str, typer.Argument(help="Template name (as shown by `comfy templates ls`)")],
    wait: Annotated[bool, typer.Option(help="Wait until execution completes")] = True,
    verbose: Annotated[bool, typer.Option(help="Verbose execution output")] = False,
    host: Annotated[str | None, typer.Option(help="ComfyUI host, e.g. 127.0.0.1")] = None,
    port: Annotated[int | None, typer.Option(help="ComfyUI port (default $COMFYUI_PORT or 8188)")] = None,
    timeout: Annotated[int, typer.Option(help="Per-event timeout (s)")] = 120,
    json_output: Annotated[bool, typer.Option("--json", help="Emit NDJSON events")] = False,
):
    path = templates_command.fetch_template_workflow(name)
    h, p = _resolve_host_port(host, port)
    run_inner.execute(path, h, p, wait, verbose, timeout, api_key=None, json_mode=json_output, print_prompt=False)


@app.command("setup", help="One-time environment wizard (local): python / workspace / server")
@tracking.track_command()
def setup(
    where: Annotated[str, typer.Option(help="Routing target (local only for this project)")] = "local",
    skip_verify: Annotated[bool, typer.Option("--skip-verify", help="Skip the server reachability probe")] = False,
):
    setup_command.setup_execute(where=where, skip_verify=skip_verify, skip_prompt=False)


@app.command(hidden=True)
@tracking.track_command()
def nodes():
    rprint("\n[bold red] No such command, did you mean 'comfy node' instead?[/bold red]\n")


@app.command(hidden=True)
@tracking.track_command()
def models():
    rprint("\n[bold red] No such command, did you mean 'comfy model' instead?[/bold red]\n")


@app.command(help="Provide feedback on the Comfy CLI tool.")
@tracking.track_command()
def feedback():
    rprint("Feedback Collection for Comfy CLI Tool\n")

    # General Satisfaction
    general_satisfaction_score = ui.prompt_select(
        question="On a scale of 1 to 5, how satisfied are you with the Comfy CLI tool? (1 being very dissatisfied and 5 being very satisfied)",
        choices=["1", "2", "3", "4", "5"],
        force_prompting=True,
    )
    tracking.track_event("feedback_general_satisfaction", {"score": general_satisfaction_score})

    # Usability and User Experience
    usability_satisfaction_score = ui.prompt_select(
        question="On a scale of 1 to 5,  how satisfied are you with the usability and user experience of the Comfy CLI tool? (1 being very dissatisfied and 5 being very satisfied)",
        choices=["1", "2", "3", "4", "5"],
        force_prompting=True,
    )
    tracking.track_event("feedback_usability_satisfaction", {"score": usability_satisfaction_score})

    # Additional Feature-Specific Feedback
    if questionary.confirm("Do you want to provide additional feature-specific feedback on our GitHub page?").ask():
        tracking.track_event("feedback_additional")
        webbrowser.open("https://github.com/Comfy-Org/comfy-cli/issues/new/choose")

    rprint("Thank you for your feedback!")


@app.command(
    hidden=True,
    help="Given an existing installation of comfy core and any custom nodes, installs any needed python dependencies",
)
@tracking.track_command()
def dependency():
    comfy_path, _ = workspace_manager.get_workspace_path()

    python = resolve_workspace_python(comfy_path)
    depComp = DependencyCompiler(cwd=comfy_path, executable=python)
    depComp.compile_deps()
    depComp.install_deps()


@app.command(help="Download a standalone Python interpreter and dependencies based on an existing comfyui workspace")
@tracking.track_command()
def standalone(
    cli_spec: Annotated[
        str,
        typer.Option(
            show_default=False,
            help="setuptools-style requirement specificer pointing to an instance of comfy-cli",
        ),
    ] = "comfy-cli",
    pack_wheels: Annotated[
        bool,
        typer.Option(
            show_default=False,
            help="Pack requirement wheels in archive when creating standalone bundle",
        ),
    ] = False,
    platform: Annotated[
        constants.OS | None,
        typer.Option(
            show_default=False,
            help="Create standalone Python for specified platform",
        ),
    ] = None,
    proc: Annotated[
        constants.PROC | None,
        typer.Option(
            show_default=False,
            help="Create standalone Python for specified processor",
        ),
    ] = None,
    rehydrate: Annotated[
        bool,
        typer.Option(
            show_default=False,
            help="Create standalone Python for CPU",
        ),
    ] = False,
):
    comfy_path, _ = workspace_manager.get_workspace_path()

    platform = utils.get_os() if platform is None else platform
    proc = utils.get_proc() if proc is None else proc

    if rehydrate:
        sty = StandalonePython.FromTarball(fpath="python.tgz")
        sty.rehydrate_comfy_deps(packWheels=pack_wheels)
    else:
        sty = StandalonePython.FromDistro(platform=platform, proc=proc)
        sty.dehydrate_comfy_deps(comfyDir=comfy_path, extraSpecs=[], packWheels=pack_wheels)
        sty.to_tarball()


generate_command.register_with(app)
app.add_typer(models_command.app, name="model", help="Manage models.")
app.add_typer(custom_nodes.app, name="node", help="Manage custom nodes.")
app.add_typer(custom_nodes.manager_app, name="manager", help="Manage ComfyUI-Manager.")

app.add_typer(pr_command.app, name="pr-cache", help="Manage PR cache.")

app.add_typer(jobs_command.jobs_app, name="jobs", help="Inspect and wait on ComfyUI jobs.")
app.add_typer(templates_app, name="templates", help="Browse and run official workflow templates.")

app.add_typer(code_search.app, name="code-search", help="Search code across ComfyUI repositories.")
app.add_typer(code_search.app, name="cs", hidden=True)

app.add_typer(tracking.app, name="tracking", help="Manage analytics tracking settings.")
