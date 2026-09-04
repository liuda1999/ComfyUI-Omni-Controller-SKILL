#!/usr/bin/env python3
"""Stop the local ComfyUI server.

按 SKILL.md 2.2 节与 EXPERIENCE.md 13.2 节要求:
- `comfy stop` 仅停止 `comfy launch --background` 启动的实例
- 直接 `python main.py` 启动的实例需用 psutil 按命令行匹配终止

实现策略(多级回退,任一可用即终止):
  1. 优先调用 /free + /interrupt 通知 ComfyUI 优雅退出(可选,失败不阻塞)
  2. 用 psutil 按 "main.py" + ComfyUI 路径特征匹配进程(跨平台)
  3. 回退到平台原生命令(Windows: taskkill; POSIX: pgrep/pkill)
  4. 失败时输出诊断信息,提示用户手动停止

支持参数:
  --force       强制终止(KILL 而非 TERM)
  --host/--port 指定 ComfyUI HTTP 端点(用于优雅退出尝试,默认 127.0.0.1:3198)
  --dry-run     仅列出将终止的进程,不实际终止
"""
import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import time

# 项目标准端口(与 start_server.py / run_workflow.py 保持一致)
DEFAULT_PORT = 3198
DEFAULT_HOST = "127.0.0.1"

# ComfyUI 进程的识别规则(多条件组合,避免单一关键词导致误报)
# 必须同时满足:
#   1. 命令行包含 "main.py"(ComfyUI 主入口)
#   2. 命令行包含 python 解释器特征("python" 或 ".exe")
# 这样可避免误杀启动器(StableDiffusionWebUILauncher)和 stop_server.py 自身
PROCESS_MUST_INCLUDE = ["main.py"]
PROCESS_PYTHON_HINTS = ["python", ".exe"]


def _is_comfyui_process(proc_info, psutil_mod, current_pid=None):
    """判断一个进程的命令行是否属于 ComfyUI。

    多条件组合匹配:
    - 必须包含 PROCESS_MUST_INCLUDE 中的所有关键词
    - 必须包含 PROCESS_PYTHON_HINTS 中的任一特征
    - 排除当前进程自身(避免 stop_server.py 误杀自己)

    proc_info: psutil Process 对象
    psutil_mod: 已导入的 psutil 模块(由调用方传入)
    current_pid: 当前进程 PID(用于排除自身)
    """
    try:
        pid = proc_info.pid
        if current_pid is not None and pid == current_pid:
            return False
        cmdline = " ".join(proc_info.cmdline()).lower()
    except (psutil_mod.NoSuchProcess, psutil_mod.AccessDenied, psutil_mod.ZombieProcess):
        return False
    if not cmdline:
        return False
    # 必须包含所有必要关键词
    for kw in PROCESS_MUST_INCLUDE:
        if kw.lower() not in cmdline:
            return False
    # 必须包含 python 特征(排除启动器、批处理脚本等)
    has_python = any(hint.lower() in cmdline for hint in PROCESS_PYTHON_HINTS)
    if not has_python:
        return False
    # 排除自身脚本(命令行含 stop_server)
    if "stop_server" in cmdline:
        return False
    return True


def find_comfyui_processes_via_psutil():
    """用 psutil 查找 ComfyUI 进程(跨平台,首选方案)。

    返回 [(pid, cmdline, name), ...],失败返回空列表。
    """
    try:
        import psutil
    except ImportError:
        return []

    current_pid = os.getpid()
    found = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            info = proc.info
            cmdline_list = info.get("cmdline") or []
            if not cmdline_list:
                continue
            cmdline = " ".join(cmdline_list)
            if _is_comfyui_process(proc, psutil, current_pid):
                found.append((info["pid"], cmdline, info.get("name", "")))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return found


def find_comfyui_processes_via_platform():
    """平台原生方式查找 ComfyUI 进程(psutil 不可用时的回退)。

    Windows: 用 wmic 查询命令行(比 tasklist 信息更全)
    POSIX:   用 pgrep -f main.py
    使用与 psutil 路径相同的多条件匹配规则,保持一致性。
    """
    found = []
    system = platform.system()
    current_pid = os.getpid()
    try:
        if system == "Windows":
            # wmic 返回 CSV: ProcessId,CommandLine
            result = subprocess.run(
                ["wmic", "process", "where", "name='python.exe' or name='pythonw.exe'",
                 "get", "ProcessId,CommandLine", "/format:csv"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout:
                lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
                for ln in lines[1:]:
                    parts = ln.split(",")
                    if len(parts) >= 2:
                        cmdline = parts[0]
                        try:
                            pid = int(parts[-1])
                        except ValueError:
                            continue
                        if pid == current_pid:
                            continue
                        cmdline_lower = cmdline.lower()
                        # 同 psutil 路径的多条件规则
                        if not all(kw.lower() in cmdline_lower for kw in PROCESS_MUST_INCLUDE):
                            continue
                        if not any(h.lower() in cmdline_lower for h in PROCESS_PYTHON_HINTS):
                            continue
                        if "stop_server" in cmdline_lower:
                            continue
                        found.append((pid, cmdline, "python.exe"))
        else:
            result = subprocess.run(
                ["pgrep", "-af", "main.py"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout:
                for ln in result.stdout.strip().splitlines():
                    parts = ln.split(None, 1)
                    if len(parts) == 2:
                        try:
                            pid = int(parts[0])
                        except ValueError:
                            continue
                        if pid == current_pid:
                            continue
                        cmdline = parts[1]
                        cmdline_lower = cmdline.lower()
                        if "stop_server" in cmdline_lower:
                            continue
                        found.append((pid, cmdline, ""))
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return found


def find_comfyui_processes():
    """查找 ComfyUI 进程,多级回退。

    优先 psutil(信息全、跨平台),回退平台原生命令。
    返回 [(pid, cmdline, name), ...]
    """
    # 1. 首选 psutil
    procs = find_comfyui_processes_via_psutil()
    if procs:
        return procs

    # 2. 回退平台原生
    return find_comfyui_processes_via_platform()


def try_graceful_shutdown(host, port, timeout=5):
    """尝试通过 ComfyUI HTTP API 优雅退出(可选,失败不阻塞)。

    ComfyUI 0.27+ 支持 /interrupt 中断当前任务;
    部分版本支持 SIGTERM 自行退出。这里仅做中断尝试,
    真正的进程终止由后续 psutil/taskkill 完成。
    """
    try:
        import urllib.request
        import urllib.error
        # 中断当前任务(如有)
        req = urllib.request.Request(f"http://{host}:{port}/interrupt", method="POST")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def kill_process(pid, force=False):
    """终止指定 PID 的进程。

    Windows: taskkill /T(含子进程),--force 时加 /F
    POSIX:   SIGTERM,--force 时用 SIGKILL
    返回 (success: bool, error: str)
    """
    system = platform.system()
    try:
        if system == "Windows":
            # 修复原代码 bug: 空字符串参数导致 taskkill 报错
            cmd = ["taskkill", "/PID", str(pid), "/T"]
            if force:
                cmd.insert(1, "/F")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                return True, ""
            return False, f"taskkill exit={result.returncode}: {result.stderr.strip()}"
        else:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
            return True, ""
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except ProcessLookupError:
        return False, "process not found"
    except PermissionError:
        return False, "permission denied"
    except Exception as e:
        return False, str(e)


def main():
    ap = argparse.ArgumentParser(description="停止 ComfyUI 服务器(多级回退策略)")
    ap.add_argument("--force", action="store_true",
                    help="强制终止(KILL 而非 TERM)")
    ap.add_argument("--host", default=DEFAULT_HOST,
                    help=f"ComfyUI 主机(默认 {DEFAULT_HOST},用于尝试优雅退出)")
    ap.add_argument("--port", default=str(DEFAULT_PORT),
                    help=f"ComfyUI 端口(默认 {DEFAULT_PORT})")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅列出将终止的进程,不实际终止")
    args = ap.parse_args()

    # Step 1: 尝试优雅中断当前任务(非阻塞)
    if try_graceful_shutdown(args.host, args.port):
        print(json.dumps({"ok": True, "message": "已发送 /interrupt 中断当前任务(如有)"}))
        if not args.force:
            # 非 force 模式给 ComfyUI 一点时间自行退出
            time.sleep(2)

    # Step 2: 查找 ComfyUI 进程
    processes = find_comfyui_processes()
    if not processes:
        print(json.dumps({
            "ok": True,
            "message": "未发现 ComfyUI 进程(可能已停止或以非标准方式启动)",
            "tip": f"如服务仍在 {args.host}:{args.port} 响应,请检查启动方式"
        }))
        return

    # Step 3: 展示将终止的进程
    print(json.dumps({
        "ok": True,
        "message": f"发现 {len(processes)} 个 ComfyUI 进程",
        "processes": [{"pid": p[0], "cmdline": p[1][:200], "name": p[2]} for p in processes],
        "dry_run": args.dry_run,
        "force": args.force
    }, ensure_ascii=False, indent=2))

    if args.dry_run:
        print(json.dumps({"ok": True, "message": "dry-run 模式,未实际终止"}))
        return

    # Step 4: 逐个终止
    killed = []
    failed = []
    for pid, cmdline, name in processes:
        ok, err = kill_process(pid, force=args.force)
        if ok:
            killed.append(pid)
        else:
            failed.append({"pid": pid, "error": err})

    # Step 5: 等待并复验
    if killed and not args.force:
        time.sleep(1)

    result = {
        "ok": len(failed) == 0,
        "killed": killed,
        "failed": failed,
        "message": f"已终止 {len(killed)} 个进程" + (f", {len(failed)} 个失败" if failed else "")
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 如有失败,提示用户
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
