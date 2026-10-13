#!/usr/bin/env python3
"""Check ComfyUI server status, environment, and hardware capabilities."""
import argparse
import json
import os
import platform
import subprocess
import sys
import urllib.request

# 本机 ComfyUI 位于回环地址，必须绕过 HTTP_PROXY/HTTPS_PROXY 环境变量，
# 否则请求会被本地代理拦截并返回 502，表现为"服务不可用"的假故障。
urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({}))
)


# 端口/host 解析优先级（见 SKILL.md 7.1）：命令行参数 > COMFYUI_PORT/COMFYUI_HOST 环境变量 > 默认值。
# 默认值跟随 ComfyUI 官方约定（8188）。3198 是历史单一部署环境的端口，非通用标准；
# 需沿用请显式设置 COMFYUI_PORT=3198。
DEFAULT_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1")
DEFAULT_PORT = os.environ.get("COMFYUI_PORT", "8188")


def http_json(url, timeout=10):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_system_info():
    """Get basic system information."""
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "is_windows": platform.system() == "Windows",
    }
    return info


def get_memory_info():
    """Get system RAM information."""
    try:
        if platform.system() == "Windows":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            mem_status = MEMORYSTATUSEX()
            mem_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            kernel32.GlobalMemoryStatusEx(ctypes.byref(mem_status))
            total_gb = mem_status.ullTotalPhys / (1024 ** 3)
            avail_gb = mem_status.ullAvailPhys / (1024 ** 3)
            return {
                "total_gb": round(total_gb, 2),
                "available_gb": round(avail_gb, 2),
                "sufficient_for_image": total_gb >= 32,
                "sufficient_for_video": total_gb >= 32,
            }
        else:
            # Linux/Mac fallback
            import psutil
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024 ** 3)
            avail_gb = mem.available / (1024 ** 3)
            return {
                "total_gb": round(total_gb, 2),
                "available_gb": round(avail_gb, 2),
                "sufficient_for_image": total_gb >= 32,
                "sufficient_for_video": total_gb >= 32,
            }
    except Exception as e:
        return {"error": str(e), "total_gb": 0, "sufficient_for_image": False, "sufficient_for_video": False}


def get_gpu_info():
    """Get GPU information using nvidia-smi or system queries."""
    gpu_info = {
        "cuda_available": False,
        "devices": [],
        "sufficient_for_image": False,
        "sufficient_for_video": False,
    }
    
    try:
        # Try nvidia-smi first
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", "--format=csv,noheader"],
            capture_output=True, text=True, errors="replace", timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 4:
                    name = parts[0]
                    total_mem = parts[1].replace(" MiB", "").replace(" MB", "").strip()
                    free_mem = parts[2].replace(" MiB", "").replace(" MB", "").strip()
                    used_mem = parts[3].replace(" MiB", "").replace(" MB", "").strip()
                    try:
                        total_gb = int(total_mem) / 1024
                        free_gb = int(free_mem) / 1024
                        used_gb = int(used_mem) / 1024
                        gpu_info["devices"].append({
                            "name": name,
                            "total_vram_gb": round(total_gb, 2),
                            "free_vram_gb": round(free_gb, 2),
                            "used_vram_gb": round(used_gb, 2),
                        })
                        if total_gb >= 8:
                            gpu_info["sufficient_for_image"] = True
                        if total_gb >= 12:
                            gpu_info["sufficient_for_video"] = True
                        gpu_info["cuda_available"] = True
                    except ValueError:
                        pass
    except FileNotFoundError:
        # nvidia-smi not found, try torch
        try:
            import torch
            if torch.cuda.is_available():
                gpu_info["cuda_available"] = True
                for i in range(torch.cuda.device_count()):
                    name = torch.cuda.get_device_name(i)
                    total_mb = torch.cuda.get_device_properties(i).total_memory / (1024 ** 2)
                    total_gb = total_mb / 1024
                    gpu_info["devices"].append({
                        "name": name,
                        "total_vram_gb": round(total_gb, 2),
                        "free_vram_gb": None,
                        "used_vram_gb": None,
                    })
                    if total_gb >= 8:
                        gpu_info["sufficient_for_image"] = True
                    if total_gb >= 12:
                        gpu_info["sufficient_for_video"] = True
        except ImportError:
            pass
    except Exception as e:
        gpu_info["error"] = str(e)
    
    return gpu_info


def detect_comfyui_version(comfyui_path):
    """Detect ComfyUI installation type and version."""
    version_info = {
        "path": comfyui_path,
        "exists": os.path.exists(comfyui_path) if comfyui_path else False,
        "version_type": "unknown",
        "web_url": None,
        "has_embedded_python": False,
        "has_venv": False,
    }
    
    if not comfyui_path or not os.path.exists(comfyui_path):
        return version_info
    
    # 使用官方标准方式检测 ComfyUI 安装（不依赖任何第三方 GUI 启动器，如 wangyi AI绘世启动器.exe 等）
    # Check for embedded Python
    embedded_python = os.path.join(comfyui_path, "python", "python.exe")
    if os.path.exists(embedded_python):
        version_info["has_embedded_python"] = True
    
    # Check for venv (Windows: venv/Scripts/python.exe; Linux/macOS: venv/bin/python)
    venv_candidates = [
        os.path.join(comfyui_path, "venv", "Scripts", "python.exe"),
        os.path.join(comfyui_path, "venv", "bin", "python"),
        os.path.join(comfyui_path, ".venv", "Scripts", "python.exe"),
        os.path.join(comfyui_path, ".venv", "bin", "python"),
    ]
    if any(os.path.exists(p) for p in venv_candidates):
        version_info["has_venv"] = True
    
    # Check for version file
    version_file = os.path.join(comfyui_path, "comfyui_version.py")
    if os.path.exists(version_file):
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                content = f.read()
                if "version" in content.lower():
                    version_info["version_file_content"] = content[:200]
        except Exception:
            pass
    
    # Check for main.py (standard ComfyUI)
    if os.path.exists(os.path.join(comfyui_path, "main.py")):
        if version_info["version_type"] == "unknown":
            version_info["version_type"] = "standard"
            version_info["web_url"] = "https://github.com/comfyanonymous/ComfyUI"
    
    return version_info


def check_capabilities(system_info, memory_info, gpu_info):
    """Determine what the system can do."""
    capabilities = {
        "can_run_local_image": False,
        "can_run_local_video": False,
        "can_run_local_at_all": False,
        "recommendation": "",
        "warnings": [],
    }
    
    # Check RAM
    ram_total = memory_info.get("total_gb", 0)
    if ram_total < 32:
        capabilities["warnings"].append(f"RAM insufficient: {ram_total}GB (minimum 32GB recommended for local rendering)")
    
    # Check GPU
    if not gpu_info.get("cuda_available"):
        capabilities["warnings"].append("No CUDA GPU detected. Local rendering is not possible.")
        capabilities["recommendation"] = "Use remote API server or cloud GPU service."
        return capabilities
    
    has_sufficient_image_vram = gpu_info.get("sufficient_for_image", False)
    has_sufficient_video_vram = gpu_info.get("sufficient_for_video", False)
    has_sufficient_ram = memory_info.get("sufficient_for_image", False)
    
    if has_sufficient_image_vram and has_sufficient_ram:
        capabilities["can_run_local_image"] = True
        capabilities["can_run_local_at_all"] = True
    
    if has_sufficient_video_vram and has_sufficient_ram:
        capabilities["can_run_local_video"] = True
        capabilities["can_run_local_at_all"] = True
    
    if not capabilities["can_run_local_at_all"]:
        capabilities["recommendation"] = "Local hardware insufficient. Use remote API server or upgrade hardware."
    elif not capabilities["can_run_local_video"]:
        capabilities["recommendation"] = "Can run text-to-image locally. For video generation, use remote API or lower resolution."
    else:
        capabilities["recommendation"] = "Local hardware sufficient for both image and video generation."
    
    return capabilities


def summarize_target(system_stats):
    """把目标 ComfyUI 服务器的 /system_stats 摘要成「目标机视角」。

    顶层 `system` / `memory` / `gpu` / `capabilities` 描述的是**运行本脚本的机器**。
    一旦用 --host/--port 指向远程实例，那台机器的能力与目标机可能完全不同
    （典型场景：无 GPU 的调度机驱动远程 GPU 机，本机 cuda_available=false 会让
    人误以为"跑不了视频"）。这里只把目标机**自我上报的事实**摘出来，不臆造任何
    阈值判定，由调用方/使用者自行比对。
    """
    system = system_stats.get("system") or {}
    devices = system_stats.get("devices") or []
    cuda = [d for d in devices if (d.get("type") or "").lower() == "cuda"]
    vram_total = [round((d.get("vram_total") or 0) / 1024 ** 3, 2) for d in cuda]
    vram_free = [round((d.get("vram_free") or 0) / 1024 ** 3, 2) for d in cuda]
    return {
        "note": "以下为 --host/--port 所指服务器的自我上报；顶层 system/memory/gpu 描述的是本机",
        "os": system.get("os"),
        "comfyui_version": system.get("comfyui_version"),
        "ram_total_gb": round((system.get("ram_total") or 0) / 1024 ** 3, 2),
        "ram_free_gb": round((system.get("ram_free") or 0) / 1024 ** 3, 2),
        "gpu_count": len(cuda),
        "gpu_names": [d.get("name") for d in cuda],
        "gpu_vram_total_gb": vram_total,
        "gpu_vram_free_gb": vram_free,
        "max_gpu_vram_total_gb": max(vram_total) if vram_total else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("COMFYUI_HOST", "127.0.0.1"))
    ap.add_argument("--port", default=os.environ.get("COMFYUI_PORT", "8188"))  # ComfyUI 官方默认；历史部署端口 3198 请用 COMFYUI_PORT 显式指定
    ap.add_argument("--comfyui-path", default=os.environ.get("COMFYUI_PATH", ""))
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}"
    
    # Gather all environment info
    result = {
        "ok": False,
        "status": "unknown",
        "server_url": base,
        "system": get_system_info(),
        "memory": get_memory_info(),
        "gpu": get_gpu_info(),
        "comfyui": detect_comfyui_version(args.comfyui_path) if args.comfyui_path else {"path": None, "exists": False},
        "capabilities": {},
        "queue": {},
        "server_stats": {},
    }
    
    # Check capabilities
    result["capabilities"] = check_capabilities(
        result["system"], result["memory"], result["gpu"]
    )
    
    # Try to connect to ComfyUI server
    try:
        queue = http_json(f"{base}/queue", timeout=5)
        system_stats = http_json(f"{base}/system_stats", timeout=5)
        
        result["ok"] = True
        result["status"] = "online"
        result["queue"] = {
            "queue_remaining": queue.get("queue_remaining", 0),
            "queue_running": len(queue.get("queue_running", [])),
            "queue_pending": len(queue.get("queue_pending", [])),
        }
        result["server_stats"] = system_stats
        result["target"] = summarize_target(system_stats)
    except Exception as e:
        result["status"] = "offline"
        result["error"] = str(e)
    
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
