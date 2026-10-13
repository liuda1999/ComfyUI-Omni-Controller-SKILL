#!/usr/bin/env python3
"""Query ComfyUI server for available models and nodes."""
import argparse
import json
import os
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


# 模型类别 -> (节点类型, 参数名) 映射
# 用于从 object_info 提取对应类别的可用模型列表
_TYPE_MAP = {
    "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
    "loras": ("LoraLoader", "lora_name"),
    "vae": ("VAELoader", "vae_name"),
    "clip": ("CLIPLoader", "clip_name"),
    "controlnet": ("ControlNetLoader", "control_net_name"),
    "upscale_models": ("UpscaleModelLoader", "model_name"),
    "unet": ("UNETLoader", "unet_name"),
    "diffusion_models": ("UNETLoader", "unet_name"),
    "text_encoders": ("CLIPLoader", "clip_name"),
}


def http_json(url, timeout=10):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("COMFYUI_HOST", "127.0.0.1"))
    ap.add_argument("--port", default=DEFAULT_PORT)  
    ap.add_argument("--search", help="Search term for model names")
    ap.add_argument("--type", default="checkpoints", help="Model type: checkpoints, loras, vae, clip, controlnet, upscale_models, unet, diffusion_models")
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}"

    try:
        obj_info = http_json(f"{base}/object_info", timeout=10)

        # 根据 --type 选择对应的节点类型和参数名
        node_type, param_name = _TYPE_MAP.get(args.type, ("CheckpointLoaderSimple", "ckpt_name"))

        models = []
        node_schema = obj_info.get(node_type, {})
        if node_schema:
            inputs = node_schema.get("input", {}).get("required", {})
            param_def = inputs.get(param_name, [])
            if param_def and isinstance(param_def, list) and len(param_def) > 0:
                # ComfyUI 有两种格式：
                # 旧格式: [["model1.safetensors", "model2.safetensors"], {config}]
                # 新格式(v0.27+): ["COMBO", {"options": ["model1.safetensors", ...], ...}]
                first = param_def[0]
                if isinstance(first, list):
                    models = first
                elif isinstance(first, str) and len(param_def) > 1 and isinstance(param_def[1], dict):
                    options = param_def[1].get("options", [])
                    if isinstance(options, list):
                        models = options

        # Filter by search term if provided
        if args.search and models:
            search_lower = args.search.lower()
            models = [m for m in models if search_lower in m.lower()]

        # Prefer fp8 versions
        fp8_models = [m for m in models if "fp8" in m.lower()]

        result = {
            "ok": True,
            "server_url": base,
            "type": args.type,
            "node_type": node_type,
            "param_name": param_name,
            "total_models": len(models),
            "models": models[:50],  # Limit output
            "fp8_models": fp8_models[:20],
            "recommended": fp8_models[0] if fp8_models else (models[0] if models else None)
        }
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({
            "ok": False,
            "error": str(e),
            "server_url": base
        }))


if __name__ == "__main__":
    main()
