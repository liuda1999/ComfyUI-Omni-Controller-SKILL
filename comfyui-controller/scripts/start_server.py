#!/usr/bin/env python3
"""
启动 ComfyUI 服务器 - 增强版
- 详细环境检查
- 启动错误诊断
- 依赖缺失检测
- 详细日志反馈
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def get_comfyui_path():
    path = os.environ.get("COMFYUI_PATH", "")
    if not path:
        raise RuntimeError(
            "COMFYUI_PATH environment variable is not set. "
            "Please set it to your ComfyUI installation directory, e.g.:\n"
            "  Windows: set COMFYUI_PATH=D:\\ComfyUI\n"
            "  Linux/Mac: export COMFYUI_PATH=/home/user/ComfyUI"
        )
    return os.path.expanduser(path)


def log(level, message):
    """输出日志"""
    print(json.dumps({"level": level, "message": message}), flush=True)


def check_python_environment(comfy_path):
    """检查Python环境"""
    results = {
        "ok": True,
        "python_exe": None,
        "version": None,
        "errors": [],
        "warnings": []
    }
    
    system = platform.system()
    candidates = []
    
    if system == "Windows":
        candidates = [
            os.path.join(comfy_path, "python", "python.exe"),
            os.path.join(comfy_path, "venv", "Scripts", "python.exe"),
            os.path.join(comfy_path, "python_embeded", "python.exe"),
        ]
    else:
        candidates = [
            os.path.join(comfy_path, "venv", "bin", "python"),
            os.path.join(comfy_path, "python", "bin", "python"),
        ]
    
    # 也检查系统PATH中的python
    try:
        result = subprocess.run(["python", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            results["warnings"].append(f"系统Python可用: {result.stdout.strip()}")
    except:
        pass
    
    # 检查候选路径
    for candidate in candidates:
        if os.path.isfile(candidate):
            results["python_exe"] = candidate
            try:
                result = subprocess.run(
                    [candidate, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    results["version"] = result.stdout.strip()
                    log("info", f"找到Python: {candidate} ({results['version']})")
                else:
                    results["errors"].append(f"Python测试失败: {result.stderr}")
            except Exception as e:
                results["errors"].append(f"无法运行Python: {e}")
            break
    
    if not results["python_exe"]:
        results["ok"] = False
        results["errors"].append("未找到Python可执行文件，请确认ComfyUI安装完整")
    
    return results


def check_core_files(comfy_path):
    """检查核心文件"""
    results = {
        "ok": True,
        "missing": [],
        "present": []
    }
    
    core_files = [
        "main.py",
        "nodes.py",
        "server.py",
        "folder_paths.py",
    ]
    
    for file in core_files:
        path = os.path.join(comfy_path, file)
        if os.path.isfile(path):
            results["present"].append(file)
        else:
            results["missing"].append(file)
    
    if results["missing"]:
        results["ok"] = False
    
    return results


def check_models(comfy_path):
    """检查模型目录"""
    results = {
        "ok": True,
        "categories": {},
        "warnings": []
    }
    
    models_dir = os.path.join(comfy_path, "models")
    if not os.path.isdir(models_dir):
        results["warnings"].append("models目录不存在")
        return results
    
    expected_categories = [
        "checkpoints", "diffusion_models", "vae", "clip", 
        "text_encoders", "controlnet", "loras", "upscale_models"
    ]
    
    for category in expected_categories:
        category_path = os.path.join(models_dir, category)
        if os.path.isdir(category_path):
            files = [f for f in os.listdir(category_path) 
                     if f.endswith(('.safetensors', '.ckpt', '.pt', '.pth'))]
            results["categories"][category] = len(files)
        else:
            results["categories"][category] = 0
    
    return results


def check_custom_nodes(comfy_path):
    """检查自定义节点"""
    results = {
        "ok": True,
        "installed": [],
        "warnings": []
    }
    
    custom_nodes_dir = os.path.join(comfy_path, "custom_nodes")
    if not os.path.isdir(custom_nodes_dir):
        results["warnings"].append("custom_nodes目录不存在")
        return results
    
    for item in os.listdir(custom_nodes_dir):
        item_path = os.path.join(custom_nodes_dir, item)
        if os.path.isdir(item_path) and not item.startswith("."):
            results["installed"].append(item)
    
    return results


def check_dependencies(python_exe, comfy_path):
    """检查关键Python依赖"""
    results = {
        "ok": True,
        "installed": [],
        "missing": [],
        "warnings": []
    }
    
    key_packages = [
        "torch", "torchvision", "numpy", "PIL"
    ]
    
    for package in key_packages:
        try:
            result = subprocess.run(
                [python_exe, "-c", f"import {package}"],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=comfy_path
            )
            if result.returncode == 0:
                results["installed"].append(package)
            else:
                results["missing"].append(package)
        except Exception as e:
            results["warnings"].append(f"检查 {package} 时出错: {e}")
    
    if results["missing"]:
        results["ok"] = False
    
    return results


def is_server_running(host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """检查服务器是否运行"""
    try:
        urllib.request.urlopen(f"http://{host}:{port}/queue", timeout=2)
        return True
    except Exception:
        return False


def start_with_launcher(launcher_path):
    """使用启动器启动"""
    try:
        log("info", f"正在通过启动器启动: {launcher_path}")
        subprocess.Popen(
            [launcher_path],
            cwd=os.path.dirname(launcher_path),
            creationflags=subprocess.CREATE_NEW_CONSOLE if platform.system() == "Windows" else 0
        )
        return True
    except Exception as e:
        log("error", f"启动器启动失败: {e}")
        return False


def start_direct(python_exe, comfy_path, host, port, listen):
    """直接启动ComfyUI"""
    main_py = os.path.join(comfy_path, "main.py")
    if not os.path.isfile(main_py):
        log("error", f"main.py 不存在: {main_py}")
        return False
    
    listen_host = "0.0.0.0" if listen else host
    cmd = [python_exe, main_py, "--listen", listen_host, "--port", str(port)]
    
    log("info", f"启动命令: {' '.join(cmd)}")
    
    try:
        if platform.system() == "Windows":
            subprocess.Popen(cmd, cwd=comfy_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen(cmd, cwd=comfy_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        log("error", f"直接启动失败: {e}")
        return False


def perform_full_check(comfy_path):
    """执行完整环境检查"""
    log("info", "开始环境检查...")
    
    report = {
        "ok": True,
        "python": check_python_environment(comfy_path),
        "core_files": check_core_files(comfy_path),
        "models": check_models(comfy_path),
        "custom_nodes": check_custom_nodes(comfy_path),
        "dependencies": None,
        "errors": [],
        "warnings": []
    }
    
    # 如果有Python，检查依赖
    if report["python"]["ok"]:
        report["dependencies"] = check_dependencies(
            report["python"]["python_exe"], 
            comfy_path
        )
    
    # 汇总问题
    if not report["python"]["ok"]:
        report["errors"].extend(report["python"]["errors"])
    report["warnings"].extend(report["python"].get("warnings", []))
    
    if not report["core_files"]["ok"]:
        report["errors"].append(f"缺失核心文件: {', '.join(report['core_files']['missing'])}")
    
    report["warnings"].extend(report["models"].get("warnings", []))
    report["warnings"].extend(report["custom_nodes"].get("warnings", []))
    
    if report["dependencies"] and not report["dependencies"]["ok"]:
        report["errors"].append(f"缺失Python依赖: {', '.join(report['dependencies']['missing'])}")
    
    report["ok"] = len(report["errors"]) == 0
    
    return report


def main():
    ap = argparse.ArgumentParser(description="启动 ComfyUI 服务器")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="3198")  # comfyui-cli项目标准端口
    ap.add_argument("--listen", action="store_true", help="监听所有接口")
    ap.add_argument("--check-only", action="store_true", help="仅检查环境")
    ap.add_argument("--verbose", action="store_true", help="详细输出")
    args = ap.parse_args()
    
    comfy_path = get_comfyui_path()
    log("info", f"ComfyUI路径: {comfy_path}")
    
    # 执行完整检查
    check_report = perform_full_check(comfy_path)
    
    if args.check_only:
        print(json.dumps(check_report, indent=2, ensure_ascii=False))
        return
    
    # 如果有严重错误，不继续
    if not check_report["ok"]:
        log("error", "环境检查失败，无法启动服务器")
        for error in check_report["errors"]:
            log("error", f"  - {error}")
        print(json.dumps({
            "ok": False,
            "error": "环境检查失败",
            "details": check_report
        }, indent=2, ensure_ascii=False))
        sys.exit(1)
    
    # 检查是否已在运行
    if is_server_running(args.host, args.port):
        log("info", "服务器已经在运行")
        print(json.dumps({
            "ok": True,
            "message": "服务器已经在运行",
            "url": f"http://{args.host}:{args.port}"
        }))
        return
    
    # 尝试启动
    started = False
    
    # 1. 尝试使用启动器
    launcher_path = os.path.join(comfy_path, "wangyi AI绘世启动器.exe")
    if os.path.isfile(launcher_path):
        log("info", "检测到启动器，尝试通过启动器启动...")
        if start_with_launcher(launcher_path):
            started = True
    
    # 2. 直接启动
    if not started and check_report["python"]["python_exe"]:
        log("info", "尝试直接启动ComfyUI...")
        if start_direct(
            check_report["python"]["python_exe"],
            comfy_path,
            args.host,
            args.port,
            args.listen
        ):
            started = True
    
    if not started:
        log("error", "所有启动方式均失败")
        print(json.dumps({
            "ok": False,
            "error": "无法启动服务器",
            "check_report": check_report
        }, indent=2, ensure_ascii=False))
        sys.exit(1)
    
    # 等待服务器就绪
    log("info", "等待服务器启动...")
    for i in range(60):
        time.sleep(2)
        if is_server_running(args.host, args.port):
            log("info", "服务器启动成功!")
            print(json.dumps({
                "ok": True,
                "message": "服务器已启动",
                "url": f"http://{args.host}:{args.port}",
                "check_report": check_report
            }, indent=2, ensure_ascii=False))
            return
        log("info", f"等待中... ({i+1}/60)")
    
    log("error", "服务器在120秒内未就绪")
    print(json.dumps({
        "ok": False,
        "error": "服务器启动超时",
        "check_report": check_report
    }, indent=2, ensure_ascii=False))
    sys.exit(1)


if __name__ == "__main__":
    main()
