#!/usr/bin/env python3
"""检查工作流的缺失节点和模型，并给出补全建议。

用途：
- 在运行工作流前预检，提前发现缺失依赖
- 按 model_family 给出配套模型补全清单（如 Flux2 需要 vae/clip/clip_vision/lora）
- 提示用户是否需要补全

用法：
    python scripts/check_workflow_dependencies.py --workflow path/to/workflow.json
    python scripts/check_workflow_dependencies.py --workflow path/to/workflow.json --fix
    python scripts/check_workflow_dependencies.py --model-family Flux2
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# 服务器地址
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 3198  # comfyui-cli项目标准端口

# 模型类别 -> (节点类型, 参数名) 映射（与 get_available_models.py 一致）
_TYPE_MAP = {
    "checkpoints": ("CheckpointLoaderSimple", "ckpt_name"),
    "loras": ("LoraLoader", "lora_name"),
    "vae": ("VAELoader", "vae_name"),
    "clip": ("CLIPLoader", "clip_name"),
    "clip_vision": ("CLIPVisionLoader", "clip_name"),
    "controlnet": ("ControlNetLoader", "control_net_name"),
    "upscale_models": ("UpscaleModelLoader", "model_name"),
    "unet": ("UNETLoader", "unet_name"),
    "diffusion_models": ("UNETLoader", "unet_name"),
    "text_encoders": ("CLIPLoader", "clip_name"),
}

# 按 model_family 列出完整配套模型清单（用于补全提示）
# 格式: {family: {model_category: [(filename, url, description), ...]}}
_MODEL_FAMILY_BUNDLES = {
    "Flux2": {
        "diffusion_models": [
            ("flux-2-klein-9b-fp8.safetensors",
             "https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/split_files/diffusion_models/flux-2-klein-9b-fp8.safetensors",
             "Flux2-Klein-9B 主模型（fp8 量化）"),
        ],
        "text_encoders": [
            ("qwen_3_8b_fp8mixed.safetensors",
             "https://huggingface.co/Comfy-Org/flux2-klein-9B/resolve/main/split_files/text_encoders/qwen_3_8b_fp8mixed.safetensors",
             "Flux2 配套 CLIP（qwen_3_8b，fp8mixed）"),
        ],
        "vae": [
            ("flux2-vae.safetensors",
             "https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors",
             "Flux2 配套 VAE"),
        ],
    },
    "Wan2.2": {
        "diffusion_models": [
            ("Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors",
             "",
             "Wan2.2 图生视频主模型（LOW fp8，VRAM 占用少）"),
            ("Wan2_2-T2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors",
             "",
             "Wan2.2 文生视频主模型（LOW fp8）"),
        ],
        "text_encoders": [
            ("umt5_xxl_fp8_e4m3fn_scaled.safetensors",
             "",
             "Wan2.2 配套 CLIP（umt5_xxl，fp8）"),
        ],
        "vae": [
            ("Wan2_1_VAE_bf16.safetensors",
             "",
             "Wan2.2 配套 VAE（bf16）"),
        ],
        "clip_vision": [
            ("clip_vision_h.safetensors",
             "",
             "Wan2.2 图生视频配套 CLIP Vision（用于图片条件编码）"),
        ],
    },
    "HunyuanVideo": {
        "diffusion_models": [
            ("hunyuan_video_720p_bf16.safetensors",
             "",
             "HunyuanVideo 主模型（720p bf16）"),
        ],
        "text_encoders": [
            ("llama_3_1_8b_instruct_fp8.safetensors",
             "",
             "HunyuanVideo 配套 CLIP（llama_3_1_8b）"),
        ],
        "vae": [
            ("vae_hunyuan_video.safetensors",
             "",
             "HunyuanVideo 配套 VAE"),
        ],
    },
}


def http_json(url, timeout=30):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_object_info(host=DEFAULT_HOST, port=DEFAULT_PORT):
    """从 ComfyUI 服务器获取 object_info"""
    base = f"http://{host}:{port}"
    try:
        return http_json(f"{base}/object_info", timeout=30), base
    except Exception as e:
        return None, base


def scan_local_models(comfyui_path):
    """扫描本地 models 目录"""
    models = {}
    if not comfyui_path or not os.path.exists(comfyui_path):
        return models
    models_root = os.path.join(comfyui_path, "models")
    if not os.path.exists(models_root):
        return models
    exts = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf")
    for category in os.listdir(models_root):
        cat_dir = os.path.join(models_root, category)
        if not os.path.isdir(cat_dir):
            continue
        models[category] = []
        for root, dirs, files in os.walk(cat_dir):
            for f in files:
                if f.lower().endswith(exts):
                    rel = os.path.relpath(os.path.join(root, f), cat_dir)
                    models[category].append(rel.replace("\\", "/"))
    return models


def extract_workflow_models(ui_wf):
    """从 UI 格式工作流中提取所有引用的模型文件名

    返回: {category: [model_name, ...]}
    """
    # 节点类型 -> (参数名, 类别) 映射
    node_to_model = {
        "CheckpointLoaderSimple": ("ckpt_name", "checkpoints"),
        "UNETLoader": ("unet_name", "diffusion_models"),
        "VAELoader": ("vae_name", "vae"),
        "CLIPLoader": ("clip_name", "text_encoders"),
        "DoubleCLIPLoader": ("clip_name1", "text_encoders"),
        "LoraLoader": ("lora_name", "loras"),
        "LoraLoaderModelOnly": ("lora_name", "loras"),
        "CLIPVisionLoader": ("clip_name", "clip_vision"),
        "ControlNetLoader": ("control_net_name", "controlnet"),
        "UpscaleModelLoader": ("model_name", "upscale_models"),
    }
    result = {}
    for node in ui_wf.get("nodes", []):
        node_type = node.get("type", "")
        if node_type not in node_to_model:
            continue
        param_name, category = node_to_model[node_type]
        # 从 widgets_values 按 widget 顺序取值
        widget_values = node.get("widgets_values", [])
        inputs = node.get("inputs", [])
        widget_idx = 0
        for inp in inputs:
            if "widget" in inp:
                if inp["widget"]["name"] == param_name and widget_idx < len(widget_values):
                    val = widget_values[widget_idx]
                    if isinstance(val, str) and val:
                        result.setdefault(category, []).append(val)
                    break
                widget_idx += 1
    return result


def extract_workflow_nodes(ui_wf):
    """从 UI 格式工作流中提取所有节点类型"""
    return list({n.get("type", "") for n in ui_wf.get("nodes", []) if n.get("type")})


def detect_model_family_from_workflow(ui_wf):
    """从工作流的模型文件名推断 model_family"""
    models = extract_workflow_models(ui_wf)
    all_names = []
    for cat, names in models.items():
        all_names.extend(names)
    for name in all_names:
        name_lower = name.lower()
        if "flux-2" in name_lower or "flux2" in name_lower or "f2k" in name_lower:
            return "Flux2"
        if "wan2_2" in name_lower or "wan2.2" in name_lower or "wan_2.2" in name_lower:
            return "Wan2.2"
        if "hunyuan" in name_lower:
            return "HunyuanVideo"
        if "ltxv" in name_lower or "ltx" in name_lower:
            return "LTX-Video"
        if "sdxl" in name_lower or "sd_xl" in name_lower:
            return "SDXL"
        if "v1-5" in name_lower or "sd15" in name_lower:
            return "SD1.5"
    return None


def check_workflow(workflow_path, comfyui_path=None, host=DEFAULT_HOST, port=DEFAULT_PORT):
    """检查工作流的缺失依赖

    返回: {
        'ok': bool,
        'workflow': path,
        'model_family': str,
        'missing_nodes': [...],
        'missing_models': [...],
        'alternative_models': [...],
        'bundle_suggestion': {...},  # 按 model_family 的完整配套清单
    }
    """
    with open(workflow_path, "r", encoding="utf-8") as f:
        ui_wf = json.load(f)

    node_types = extract_workflow_nodes(ui_wf)
    wf_models = extract_workflow_models(ui_wf)
    model_family = detect_model_family_from_workflow(ui_wf)

    result = {
        "ok": True,
        "workflow": workflow_path,
        "model_family": model_family,
        "node_types": node_types,
        "workflow_models": wf_models,
        "missing_nodes": [],
        "missing_models": [],
        "alternative_models": [],
        "bundle_suggestion": {},
    }

    # 1. 检查节点是否在服务器上可用
    object_info, base = get_object_info(host, port)
    if object_info is None:
        result["ok"] = False
        result["error"] = f"无法连接 ComfyUI 服务器 {base}"
        return result

    for nt in node_types:
        if nt and nt not in object_info:
            result["missing_nodes"].append({
                "node": nt,
                "suggestion": f"需要安装提供 {nt} 的自定义节点包",
            })

    # 2. 检查模型是否在本地存在
    local_models = scan_local_models(comfyui_path) if comfyui_path else None

    if local_models:
        for category, names in wf_models.items():
            local_cat = _resolve_local_category(category, local_models)
            for name in names:
                if local_cat and name not in local_models.get(local_cat, []):
                    # 查找相似模型
                    alt = _find_similar(name, local_models.get(local_cat, []))
                    if alt:
                        result["alternative_models"].append({
                            "original": name,
                            "alternative": alt,
                            "category": category,
                        })
                    else:
                        result["missing_models"].append({
                            "model": name,
                            "category": category,
                            "suggestion": f"需要下载模型: {name}",
                        })

    # 3. 按 model_family 给出配套补全清单
    if model_family and model_family in _MODEL_FAMILY_BUNDLES:
        bundle = _MODEL_FAMILY_BUNDLES[model_family]
        for cat, items in bundle.items():
            local_cat = _resolve_local_category(cat, local_models) if local_models else None
            for filename, url, desc in items:
                already = (local_cat and filename in local_models.get(local_cat, []))
                if not already:
                    result["bundle_suggestion"].setdefault(cat, []).append({
                        "filename": filename,
                        "url": url,
                        "description": desc,
                        "already_present": already,
                    })

    if result["missing_nodes"] or result["missing_models"]:
        result["ok"] = False

    return result


def _resolve_local_category(category, local_models):
    """将工作流类别映射到本地目录名"""
    mapping = {
        "checkpoints": "checkpoints",
        "diffusion_models": "diffusion_models",
        "unet": "diffusion_models",
        "vae": "vae",
        "clip": "text_encoders",
        "text_encoders": "text_encoders",
        "clip_vision": "clip_vision",
        "loras": "loras",
        "controlnet": "controlnet",
        "upscale_models": "upscale_models",
    }
    mapped = mapping.get(category, category)
    # 检查本地实际存在的目录名
    if mapped in local_models:
        return mapped
    # 兼容 unet 目录
    if mapped == "diffusion_models" and "unet" in local_models:
        return "unet"
    return mapped


def _find_similar(requested, available):
    """查找相似模型（同系列优先）"""
    if not available:
        return None
    req_lower = requested.lower()
    # 提取系列关键词（如 wan2_2、flux2、hunyuan）
    for prefix in ["wan2_2", "wan2.2", "flux2", "flux-2", "f2k", "hunyuan", "ltxv", "sdxl", "v1-5"]:
        if prefix in req_lower:
            for m in available:
                if prefix in m.lower() and m != requested:
                    return m
    # 无系列匹配，返回 None
    return None


def print_report(result, fix_mode=False):
    """打印检查报告"""
    print(f"\n{'='*60}")
    print(f"工作流依赖检查报告")
    print(f"{'='*60}")
    print(f"工作流: {result['workflow']}")
    print(f"模型系列: {result.get('model_family') or '未识别'}")
    print(f"节点数: {len(result['node_types'])}")
    print(f"引用模型数: {sum(len(v) for v in result['workflow_models'].values())}")

    # 缺失节点
    if result["missing_nodes"]:
        print(f"\n--- 缺失节点 ({len(result['missing_nodes'])}) ---")
        for m in result["missing_nodes"]:
            print(f"  ✗ {m['node']}: {m['suggestion']}")
    else:
        print(f"\n--- 节点检查 ✓ 全部可用 ---")

    # 缺失模型
    if result["missing_models"]:
        print(f"\n--- 缺失模型 ({len(result['missing_models'])}) ---")
        for m in result["missing_models"]:
            print(f"  ✗ [{m['category']}] {m['model']}")
    else:
        print(f"\n--- 模型检查 ✓ 全部存在 ---")

    # 替代模型
    if result["alternative_models"]:
        print(f"\n--- 可用替代模型 ({len(result['alternative_models'])}) ---")
        for a in result["alternative_models"]:
            print(f"  ↔ [{a['category']}] {a['original']} → {a['alternative']}")

    # 配套补全建议
    if result["bundle_suggestion"]:
        print(f"\n--- {result.get('model_family')} 配套模型补全建议 ---")
        total = 0
        for cat, items in result["bundle_suggestion"].items():
            print(f"\n  [{cat}]")
            for item in items:
                status = "✓ 已存在" if item["already_present"] else "✗ 缺失"
                print(f"    {status} {item['filename']}")
                print(f"           {item['description']}")
                if item["url"]:
                    print(f"           下载: {item['url']}")
                if not item["already_present"]:
                    total += 1
        if total > 0:
            print(f"\n  共 {total} 个配套模型缺失")
            if fix_mode:
                print(f"\n  使用 --fix 参数可自动下载（需配置 download_models.py）")

    # 总结
    if result["ok"]:
        print(f"\n✓ 检查通过，工作流可以运行")
    else:
        print(f"\n✗ 检查未通过，请补全上述缺失依赖")

    return result["ok"]


def check_model_family_bundle(model_family, comfyui_path=None):
    """检查指定 model_family 的完整配套模型"""
    if model_family not in _MODEL_FAMILY_BUNDLES:
        print(f"未知的 model_family: {model_family}")
        print(f"支持的系列: {', '.join(_MODEL_FAMILY_BUNDLES.keys())}")
        return False

    local_models = scan_local_models(comfyui_path) if comfyui_path else None
    bundle = _MODEL_FAMILY_BUNDLES[model_family]

    print(f"\n{'='*60}")
    print(f"{model_family} 配套模型检查")
    print(f"{'='*60}")

    total_missing = 0
    for cat, items in bundle.items():
        local_cat = _resolve_local_category(cat, local_models) if local_models else None
        print(f"\n[{cat}]")
        for filename, url, desc in items:
            already = (local_cat and filename in local_models.get(local_cat, []))
            status = "✓ 已存在" if already else "✗ 缺失"
            print(f"  {status} {filename}")
            print(f"         {desc}")
            if url and not already:
                print(f"         下载: {url}")
            if not already:
                total_missing += 1

    if total_missing == 0:
        print(f"\n✓ {model_family} 配套模型完整")
    else:
        print(f"\n✗ {model_family} 缺少 {total_missing} 个配套模型")

    return total_missing == 0


def main():
    ap = argparse.ArgumentParser(description="检查工作流的缺失节点和模型")
    ap.add_argument("--workflow", help="工作流 JSON 文件路径")
    ap.add_argument("--model-family", help="检查指定 model_family 的配套模型（如 Flux2/Wan2.2/HunyuanVideo）")
    ap.add_argument("--comfyui-path", default=os.environ.get("COMFYUI_PATH"),
                    help="ComfyUI 安装路径（默认读取 COMFYUI_PATH 环境变量）")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--fix", action="store_true", help="自动下载缺失模型（需配置 download_models.py）")
    args = ap.parse_args()

    if args.model_family:
        ok = check_model_family_bundle(args.model_family, args.comfyui_path)
        sys.exit(0 if ok else 1)

    if not args.workflow:
        ap.error("需要指定 --workflow 或 --model-family")

    if not args.comfyui_path:
        print("警告: 未指定 --comfyui-path，将仅检查节点可用性，不检查本地模型")

    result = check_workflow(args.workflow, args.comfyui_path, args.host, args.port)
    ok = print_report(result, fix_mode=args.fix)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()


# ============================================================
# 视频生成专用节点完整性校验（SubTask 2.1 & 2.2）
# ============================================================

# 视频生成专用必需节点清单（lc.txt 六阶段架构）
# 每个节点除主名称外，还列出可能的别名/变体，用于在 /object_info 中匹配；
# 主名称或任意别名命中即视为该节点可用。
VIDEO_REQUIRED_NODES = {
    "WanVideo I2V Sampler (img2vid)": {
        "category": "WanVideoWrapper",
        "install_hint": "ComfyUI-Manager 搜索 WanVideoWrapper (by kijai)",
        "aliases": [
            "WanVideo I2V Sampler (img2vid)",
            "WanVideoI2VSampler",
            "WanVideo Wrapper I2V Sampler",
        ],
    },
    "FaceDetailer": {
        "category": "Impact Pack",
        "install_hint": "ComfyUI-Manager 搜索 ComfyUI-Impact-Pack",
        "aliases": [
            "FaceDetailer",
        ],
    },
    "VHS_VideoCombine": {
        "category": "VideoHelperSuite",
        "install_hint": "ComfyUI-Manager 搜索 ComfyUI-VideoHelperSuite",
        # VideoHelperSuite 注册名与 UI 显示名存在变体，需同时匹配
        "aliases": [
            "VHS_VideoCombine",
            "Video Combine",
        ],
    },
    "RIFE VFI": {
        "category": "Frame Interpolation",
        "install_hint": "ComfyUI-Manager 搜索 ComfyUI-Frame-Interpolation",
        "aliases": [
            "RIFE VFI",
            "RIFEVFI",
        ],
    },
    "Deflicker": {
        "category": "Deflicker",
        "install_hint": "ComfyUI-Manager 搜索 ComfyUI-Deflicker",
        "aliases": [
            "Deflicker",
        ],
    },
}


def check_video_nodes_available(base_url="http://127.0.0.1:3198"):
    """检查视频生成专用节点是否全部可用

    通过 /object_info API 查询所有已注册节点，逐一检查视频必需节点是否存在。
    对每个节点同时检查主名称及其别名/变体，命中任意一个即视为可用。

    Args:
        base_url: ComfyUI 服务器地址，默认 http://127.0.0.1:3198

    Returns:
        dict: {
            "all_available": bool,  # 是否全部可用
            "available": [str],     # 已可用节点列表（主名称）
            "missing": [dict],      # 缺失节点列表 [{name, category, install_hint}]
            "error": str,           # 连接失败时的错误信息（成功时不包含此键）
        }
    """
    result = {
        "all_available": False,
        "available": [],
        "missing": [],
    }

    # 拉取 /object_info（超时 10 秒）
    url = base_url.rstrip("/") + "/object_info"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            object_info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        # 连接失败：全部视为缺失并返回错误信息
        result["error"] = f"无法连接 ComfyUI 服务器 {base_url}: {e}"
        for name, info in VIDEO_REQUIRED_NODES.items():
            result["missing"].append({
                "name": name,
                "category": info["category"],
                "install_hint": info["install_hint"],
            })
        return result

    # 已注册节点名集合
    registered = set(object_info.keys()) if isinstance(object_info, dict) else set()

    # 逐一检查每个必需节点（主名称 + 别名，去重保序）
    for name, info in VIDEO_REQUIRED_NODES.items():
        candidates = [name] + list(info.get("aliases", []))
        seen = set()
        candidates = [c for c in candidates if not (c in seen or seen.add(c))]

        if any(c in registered for c in candidates):
            result["available"].append(name)
        else:
            result["missing"].append({
                "name": name,
                "category": info["category"],
                "install_hint": info["install_hint"],
            })

    result["all_available"] = (len(result["missing"]) == 0)
    return result


def report_missing_video_nodes(check_result):
    """打印缺失节点清单并给出安装提示

    Args:
        check_result: check_video_nodes_available 的返回值

    Returns:
        bool: True 表示全部可用可以继续, False 表示有缺失应阻止执行
    """
    # 连接失败：直接阻止执行
    if "error" in check_result:
        print(f"错误: {check_result['error']}")
        print("无法检查视频节点可用性，请确认 ComfyUI 服务器已启动")
        return False

    missing = check_result.get("missing", [])
    available = check_result.get("available", [])

    if missing:
        print("错误: 缺少以下视频必需节点:")
        for m in missing:
            print(f"  - {m['name']} (来自 {m['category']})")
            print(f"    安装: {m['install_hint']}")
        print("请先安装缺失节点后再执行视频生成任务")
        return False

    # 全部可用：打印确认信息
    print(f"视频节点检查通过: 全部 {len(available)} 个必需节点可用")
    for name in available:
        print(f"  ✓ {name}")
    return True
