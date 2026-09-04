#!/usr/bin/env python3
"""Check ComfyUI server status, environment, and hardware capabilities."""
import argparse
import json
import os
import platform
import subprocess
import sys
import urllib.request


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
            capture_output=True, text=True, timeout=10
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
        "has_gui_launcher": False,
        "has_embedded_python": False,
        "has_venv": False,
    }
    
    if not comfyui_path or not os.path.exists(comfyui_path):
        return version_info
    
    # Check for 绘世社区版 (HuiShi/Community Edition) - has GUI launcher
    gui_launcher = os.path.join(comfyui_path, "wangyi AI绘世启动器.exe")
    if os.path.exists(gui_launcher):
        version_info["has_gui_launcher"] = True
        version_info["version_type"] = "huishi_community"
        version_info["web_url"] = "https://www.aigodlike.com/"
    
    # Check for 秋叶整合包 (QiuYe/Autumn Leaf Package)
    qiuYe_markers = ["A绘世启动器.exe", "绘世启动器.exe", "A启动器.exe"]
    for marker in qiuYe_markers:
        if os.path.exists(os.path.join(comfyui_path, marker)):
            version_info["version_type"] = "qiuye_package"
            version_info["web_url"] = "https://pan.baidu.com/s/1SKaXQ5hnEEGNoMvm9fyt5A?pwd=n2zn"
            break
    
    # Check for embedded Python
    embedded_python = os.path.join(comfyui_path, "python", "python.exe")
    if os.path.exists(embedded_python):
        version_info["has_embedded_python"] = True
    
    # Check for venv
    venv_python = os.path.join(comfyui_path, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_python):
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
    
    # Check OS
    if not system_info.get("is_windows"):
        capabilities["warnings"].append("Non-Windows system detected. Some features may not work correctly.")
    
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("COMFYUI_HOST", "127.0.0.1"))
    ap.add_argument("--port", default=os.environ.get("COMFYUI_PORT", "3198"))  # comfyui-cli项目标准端口
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
    except Exception as e:
        result["status"] = "offline"
        result["error"] = str(e)
    
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
