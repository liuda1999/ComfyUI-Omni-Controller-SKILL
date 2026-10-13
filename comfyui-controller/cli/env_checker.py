"""
Module for checking various env and state conditions.
"""

import os
import sys

import requests
from rich.console import Console

from cli import constants
from cli.config_manager import ConfigManager
from cli.utils import singleton

console = Console()


def format_python_version(version_info):
    """
    Formats the Python version string to display the major and minor version numbers.

    If the minor version is greater than 8, the version is displayed in normal text.
    If the minor version is 8 or less, the version is displayed in bold red text to indicate an older version.

    Args:
        version_info (sys.version_info): The Python version information

    Returns:
        str: The formatted Python version string.
    """
    if version_info.major == 3 and version_info.minor > 8:
        return f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    return f"[bold red]{version_info.major}.{version_info.minor}.{version_info.micro}[/bold red]"


def check_comfy_server_running(port=None, host="localhost", timeout: float = 5.0):
    # 端口优先级：显式参数 > COMFYUI_PORT 环境变量 > 8188（ComfyUI 官方默认）
    port = port if port is not None else constants.default_port()
    """
    Checks if the Comfy server is running by making a GET request to the /history endpoint.

    `timeout` bounds the probe so a TCP-reachable but unresponsive server
    (e.g., stuck in a CUDA kernel) doesn't hang the caller.

    Returns:
        bool: True if the Comfy server is running, False otherwise.
    """
    try:
        # 绕过环境代理：本地 ComfyUI 不应经 HTTP(S)_PROXY（否则在有代理的环境里
        # 会被代理拦成 502，误判为"服务未运行"）。
        response = requests.get(
            f"http://{host}:{port}/history",
            timeout=timeout,
            proxies={"http": None, "https": None},
        )
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


@singleton
class EnvChecker:
    """
    Provides an `EnvChecker` class to check the current environment and print information about it.

    - `virtualenv_path`: The path to the current virtualenv, or "Not Used" if not in a virtualenv.
    - `conda_env`: The name of the current conda environment, or "Not Used" if not in a conda environment.
    - `python_version`: The version information for the current Python installation.
    - `currently_in_comfy_repo`: A boolean indicating whether the current directory is part of the Comfy repository.

    The `EnvChecker` class is a singleton that checks the current environment
    and stores information about the Python version, virtualenv path, conda
    environment, and whether the current directory is part of the Comfy
    repository.


    The `print()` method of the `EnvChecker` class displays the collected
    environment information in a formatted table.
    """

    def __init__(self):
        self.virtualenv_path = None
        self.conda_env = None
        self.python_version = sys.version_info
        self.check()

    def is_isolated_env(self):
        return self.virtualenv_path or self.conda_env

    def get_isolated_env(self):
        if self.virtualenv_path:
            return self.virtualenv_path

        if self.conda_env:
            return self.conda_env

        return None

    def check(self):
        self.virtualenv_path = os.environ.get("VIRTUAL_ENV") if os.environ.get("VIRTUAL_ENV") else None
        self.conda_env = os.environ.get("CONDA_DEFAULT_ENV") if os.environ.get("CONDA_DEFAULT_ENV") else None

    def fill_print_table(self):
        data = []
        data.append(("Python Version", format_python_version(sys.version_info)))
        data.append(("Python Executable", sys.executable))
        data.append(
            (
                "Virtualenv Path",
                self.virtualenv_path if self.virtualenv_path else "Not Used",
            )
        )
        data.append(("Conda Env", self.conda_env if self.conda_env else "Not Used"))

        config_data = ConfigManager().get_env_data()
        data.extend(config_data)

        if check_comfy_server_running():
            data.append(
                (
                    "Comfy Server Running",
                    f"[bold green]Yes[/bold green]\nhttp://localhost:{constants.default_port()}",
                )
            )
        else:
            data.append(("Comfy Server Running", "[bold red]No[/bold red]"))

        return data
