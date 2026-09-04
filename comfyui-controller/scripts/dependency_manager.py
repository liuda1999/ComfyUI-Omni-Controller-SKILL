#!/usr/bin/env python3
"""
依赖管理器 - 自动处理缺失的节点、模型、插件
- 检测缺失的自定义节点
- 智能匹配本地可用模型替代
- 尝试下载缺失的模型
- 提供详细的日志反馈
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from urllib.parse import urlparse


# 常见模型下载源
MODEL_SOURCES = {
    "civitai": "https://civitai.com/api/download/models/",
    "huggingface": "https://huggingface.co/",
}

# 模型类别映射到目录
MODEL_CATEGORIES = {
    "checkpoints": ["CheckpointLoaderSimple", "CheckpointLoader"],
    "diffusion_models": ["UNETLoader"],
    "vae": ["VAELoader"],
    "clip": ["CLIPLoader"],
    "text_encoders": ["CLIPLoader", "CLIPTextEncode"],
    "controlnet": ["ControlNetLoader"],
    "loras": ["LoraLoader", "LoraLoaderModelOnly"],
    "upscale_models": ["UpscaleModelLoader", "LatentUpscaleModelLoader"],
}

# control_after_generate 标记值
_CONTROL_AFTER_GENERATE_VALUES = {"fixed", "increment", "randomize", "disable"}


def _is_api_format(workflow):
    """检测工作流是否为 API 格式（dict of dicts with class_type）"""
    if not isinstance(workflow, dict) or "nodes" in workflow:
        return False
    return all(isinstance(v, dict) and "class_type" in v for v in workflow.values())


def _filter_control_values(widgets_values):
    """过滤 widgets_values 中的 control_after_generate 标记"""
    out = []
    i = 0
    while i < len(widgets_values):
        value = widgets_values[i]
        if isinstance(value, str) and value in _CONTROL_AFTER_GENERATE_VALUES:
            i += 1
            continue
        if i + 1 < len(widgets_values) and isinstance(widgets_values[i + 1], str) and widgets_values[i + 1] in _CONTROL_AFTER_GENERATE_VALUES:
            out.append(value)
            i += 2
            continue
        out.append(value)
        i += 1
    return out


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


def scan_local_models(comfyui_path):
    """扫描本地所有模型文件"""
    models = {}
    models_dir = os.path.join(comfyui_path, "models")
    
    if not os.path.isdir(models_dir):
        return models
    
    for category in os.listdir(models_dir):
        category_path = os.path.join(models_dir, category)
        if os.path.isdir(category_path):
            models[category] = []
            for root, dirs, files in os.walk(category_path):
                for file in files:
                    if file.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf')):
                        models[category].append(file)
    
    return models


def get_available_nodes(host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """获取服务器上可用的节点类型"""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/object_info", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return list(data.keys())
    except Exception as e:
        return []


def get_object_info(host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """获取完整的 object_info 字典，用于 widget 映射"""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/object_info", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {}


def _get_widget_names_from_object_info(node_type, object_info):
    """从 object_info schema 获取有序的 widget 输入名列表。

    UI 格式的 nodes[].inputs 只包含连接输入，widget 定义需要从 object_info 获取。
    widget 类型包括：列表（combo 选择）、INT、FLOAT、STRING。
    """
    if not object_info or node_type not in object_info:
        return []

    node_schema = object_info[node_type]
    inputs_def = node_schema.get("input", {})

    widget_names = []
    for section in ("required", "optional"):
        section_inputs = inputs_def.get(section, {})
        if isinstance(section_inputs, dict):
            for name, type_info in section_inputs.items():
                if isinstance(type_info, list) and len(type_info) > 0:
                    input_type = type_info[0]
                    # widget 类型：列表(combo)、INT、FLOAT、STRING
                    if isinstance(input_type, list) or input_type in ("INT", "FLOAT", "STRING"):
                        widget_names.append(name)

    return widget_names


def check_node_availability(node_type, available_nodes):
    """检查节点是否可用"""
    return node_type in available_nodes


def find_model_category(node_type):
    """根据节点类型找到模型类别"""
    for category, node_types in MODEL_CATEGORIES.items():
        if node_type in node_types:
            return category
    return None


def smart_model_match(requested_name, available_models, local_models_by_category):
    """
    智能模型匹配
    - 精确匹配
    - 忽略量化后缀匹配 (fp8, fp16, bf16, e4m3fn等)
    - 同架构不同版本匹配
    - 返回最佳匹配和置信度
    """
    if not requested_name:
        return None, 0
    
    req_lower = requested_name.lower()
    
    # 1. 精确匹配
    if requested_name in available_models:
        return requested_name, 100
    
    # 2. 忽略大小写精确匹配
    for model in available_models:
        if model.lower() == req_lower:
            return model, 95
    
    # 3. 提取基础名称（移除量化后缀）
    # 注意：此正则在 re.sub(r'[_\-\.]', '', req_lower) 之后运行，
    # 所以 Q5_K_M 已变为 q5km，Q8_0 已变为 q80 等
    req_base = re.sub(r'[_\-\.]', '', req_lower)
    req_base = re.sub(r'(fp8|fp16|fp32|bf16|e4m3fn|e5m2|scaled|quantized|v\d+\.\d+|\d+b|q\d+\w*|iq\d+\w*|f16|f32|\.safetensors|\.ckpt|gguf).*$', '', req_base)

    best_match = None
    best_score = 0

    for model in available_models:
        model_lower = model.lower()
        model_base = re.sub(r'[_\-\.]', '', model_lower)
        model_base = re.sub(r'(fp8|fp16|fp32|bf16|e4m3fn|e5m2|scaled|quantized|v\d+\.\d+|\d+b|q\d+\w*|iq\d+\w*|f16|f32|\.safetensors|\.ckpt|gguf).*$', '', model_base)
        
        score = 0
        
        # 基础名称完全匹配
        if req_base == model_base:
            score = 90
        
        # 互相包含
        elif req_base in model_base or model_base in req_base:
            score = 75
        
        # 关键词匹配
        else:
            req_words = set(re.findall(r'[a-z0-9]+', req_base))
            model_words = set(re.findall(r'[a-z0-9]+', model_base))
            if req_words:
                overlap = len(req_words & model_words) / len(req_words)
                score = overlap * 60
        
        if score > best_score:
            best_score = score
            best_match = model
    
    # 4. 检查本地模型（即使不在服务器列表中）
    # 跨类别搜索时降低置信度，避免跨类型自动替换（如 lora 替换到 checkpoint）
    if best_score < 50:
        for category, models in local_models_by_category.items():
            for model in models:
                model_lower = model.lower()
                model_base = re.sub(r'[_\-\.]', '', model_lower)
                model_base = re.sub(r'(fp8|fp16|fp32|bf16|e4m3fn|e5m2|scaled|quantized|v\d+\.\d+|\d+b|q\d+\w*|iq\d+\w*|f16|f32|\.safetensors|\.ckpt|gguf).*$', '', model_base)

                if req_base == model_base:
                    return model, 75  # 跨类别匹配，不触发自动替换（<85）
    
    return (best_match, best_score) if best_score >= 40 else (None, 0)


def analyze_workflow_dependencies(workflow_path, host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """分析工作流的所有依赖"""
    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    comfyui_path = get_comfyui_path()
    object_info = get_object_info(host, port)
    available_nodes = list(object_info.keys()) if object_info else get_available_nodes(host, port)
    local_models = scan_local_models(comfyui_path)

    report = {
        "ok": True,
        "workflow": workflow_path,
        "missing_nodes": [],
        "missing_models": [],
        "model_substitutions": [],
        "local_models_used": [],
        "warnings": [],
        "errors": []
    }

    api_format = _is_api_format(workflow)

    if api_format:
        # API 格式：{node_id: {class_type, inputs: {param: value}}}
        for node_id, node_data in workflow.items():
            node_type = node_data.get("class_type", "")
            inputs = node_data.get("inputs", {})

            # 1. 检查节点是否可用
            if not check_node_availability(node_type, available_nodes):
                report["missing_nodes"].append({
                    "node_id": node_id,
                    "node_type": node_type,
                    "issue": "节点类型在当前环境中不可用，可能需要安装自定义节点包"
                })
                continue

            # 2. 检查模型加载器中的模型（API 格式中参数值直接在 inputs 中）
            for param_name, value in inputs.items():
                if not param_name.endswith("_name"):
                    continue
                if isinstance(value, list):
                    continue  # 连接引用，跳过
                model_name = value
                if not model_name:
                    continue

                category = find_model_category(node_type)
                if not category:
                    continue

                available_in_category = local_models.get(category, [])
                match, confidence = smart_model_match(
                    model_name,
                    available_in_category,
                    local_models
                )

                if match and confidence >= 85:
                    if match != model_name:
                        report["model_substitutions"].append({
                            "node_id": node_id,
                            "node_type": node_type,
                            "param": param_name,
                            "original": model_name,
                            "substituted": match,
                            "confidence": confidence,
                            "reason": "同模型不同量化版本/命名"
                        })
                    else:
                        report["local_models_used"].append({
                            "node_id": node_id,
                            "model": model_name,
                            "category": category
                        })
                elif match and confidence >= 50:
                    report["warnings"].append({
                        "node_id": node_id,
                        "node_type": node_type,
                        "param": param_name,
                        "original": model_name,
                        "suggested": match,
                        "confidence": confidence,
                        "reason": "可能匹配但需确认"
                    })
                else:
                    report["missing_models"].append({
                        "node_id": node_id,
                        "node_type": node_type,
                        "param": param_name,
                        "model_name": model_name,
                        "category": category,
                        "available_in_category": available_in_category[:10]
                    })
    else:
        # UI 格式：{nodes: [...], links: [...]}
        nodes = workflow.get("nodes", [])

        for node in nodes:
            node_type = node.get("type", "")
            node_id = str(node.get("id", "unknown"))

            # 1. 检查节点是否可用
            if not check_node_availability(node_type, available_nodes):
                report["missing_nodes"].append({
                    "node_id": node_id,
                    "node_type": node_type,
                    "issue": "节点类型在当前环境中不可用，可能需要安装自定义节点包"
                })
                continue

            # 2. 检查模型加载器中的模型
            # UI 格式的 widgets_values 按 object_info 中定义的 widget 顺序排列，
            # 但 node["inputs"] 只包含连接输入，不能用于 widget 映射。
            # 必须使用 object_info 获取 widget 名称列表。
            widgets_values = node.get("widgets_values", [])
            if not isinstance(widgets_values, list):
                widgets_values = []

            # 过滤 control_after_generate 标记，避免 widget 值错位
            filtered_values = _filter_control_values(widgets_values)

            # 从 object_info 获取有序的 widget 名称列表
            widget_names = _get_widget_names_from_object_info(node_type, object_info)

            # 映射 widget 值到参数名，检查模型参数
            category = find_model_category(node_type)
            if not category:
                continue

            available_in_category = local_models.get(category, [])

            for idx, param_name in enumerate(widget_names):
                if not param_name.endswith("_name"):
                    continue
                if idx >= len(filtered_values):
                    break
                model_name = filtered_values[idx]
                if not model_name:
                    continue

                # 尝试智能匹配
                match, confidence = smart_model_match(
                    model_name,
                    available_in_category,
                    local_models
                )

                if match and confidence >= 85:
                    # 精确匹配或高置信度匹配
                    if match != model_name:
                        report["model_substitutions"].append({
                            "node_id": node_id,
                            "node_type": node_type,
                            "param": param_name,
                            "original": model_name,
                            "substituted": match,
                            "confidence": confidence,
                            "reason": "同模型不同量化版本/命名"
                        })
                    else:
                        report["local_models_used"].append({
                            "node_id": node_id,
                            "model": model_name,
                            "category": category
                        })
                elif match and confidence >= 50:
                    # 低置信度匹配，需要用户确认
                    report["warnings"].append({
                        "node_id": node_id,
                        "node_type": node_type,
                        "param": param_name,
                        "requested": model_name,
                        "suggested_match": match,
                        "confidence": confidence,
                        "message": f"模型 '{model_name}' 未找到，建议替代: '{match}' (置信度{confidence}%)"
                    })
                else:
                    # 完全未找到
                    report["missing_models"].append({
                        "node_id": node_id,
                        "node_type": node_type,
                        "param": param_name,
                        "model_name": model_name,
                        "category": category,
                        "available_in_category": available_in_category[:10]  # 只显示前10个
                    })
    
    return report


def fix_workflow_models(workflow_path, output_path, substitutions, host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """应用模型替换到工作流"""
    with open(workflow_path, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 构建替换映射
    sub_map = {}
    for sub in substitutions:
        node_id = sub["node_id"]
        param = sub["param"]
        original = sub["original"]
        substituted = sub["substituted"]
        sub_map[(node_id, param)] = substituted

    if _is_api_format(workflow):
        # API 格式：直接修改 inputs 中的参数值
        for node_id, node_data in workflow.items():
            inputs = node_data.get("inputs", {})
            for param_name in list(inputs.keys()):
                key = (node_id, param_name)
                if key in sub_map:
                    inputs[param_name] = sub_map[key]
    else:
        # UI 格式：使用 object_info 获取 widget 名称映射
        object_info = get_object_info(host, port)

        for node in workflow.get("nodes", []):
            node_id = str(node.get("id"))
            node_type = node.get("type", "")
            widgets_values = node.get("widgets_values", [])
            if not isinstance(widgets_values, list):
                continue

            # 从 object_info 获取 widget 名称列表
            widget_names = _get_widget_names_from_object_info(node_type, object_info)
            if not widget_names:
                continue

            # 遍历原 widgets_values，跳过 control_after_generate 标记，
            # 用 widget_names 中对应位置的名称检查是否有替换
            widget_idx = 0
            orig_idx = 0
            while orig_idx < len(widgets_values) and widget_idx < len(widget_names):
                val = widgets_values[orig_idx]

                # 如果当前值是 control 标记，跳过
                if isinstance(val, str) and val in _CONTROL_AFTER_GENERATE_VALUES:
                    orig_idx += 1
                    continue

                # 当前 widget 名称
                param_name = widget_names[widget_idx]
                key = (node_id, param_name)
                if key in sub_map:
                    widgets_values[orig_idx] = sub_map[key]

                widget_idx += 1
                orig_idx += 1

                # 跳过紧跟在当前值后面的 control 标记
                if orig_idx < len(widgets_values) and isinstance(widgets_values[orig_idx], str) and widgets_values[orig_idx] in _CONTROL_AFTER_GENERATE_VALUES:
                    orig_idx += 1

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)

    return output_path


def generate_install_report(report):
    """生成安装报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("ComfyUI 工作流依赖分析报告")
    lines.append("=" * 60)
    
    # 缺失节点
    if report["missing_nodes"]:
        lines.append("\n【缺失的自定义节点】")
        for item in report["missing_nodes"]:
            lines.append(f"  - 节点ID {item['node_id']}: {item['node_type']}")
            lines.append(f"    说明: {item['issue']}")
    
    # 模型替换
    if report["model_substitutions"]:
        lines.append("\n【自动替换的模型】")
        for item in report["model_substitutions"]:
            lines.append(f"  - {item['original']} -> {item['substituted']} ({item['confidence']}%)")
    
    # 警告
    if report["warnings"]:
        lines.append("\n【警告】")
        for item in report["warnings"]:
            lines.append(f"  - {item['message']}")
    
    # 缺失模型
    if report["missing_models"]:
        lines.append("\n【缺失的模型】")
        for item in report["missing_models"]:
            lines.append(f"  - {item['model_name']} (类别: {item['category']})")
            if item['available_in_category']:
                lines.append(f"    该类别可用模型: {', '.join(item['available_in_category'])}")
    
    # 本地模型使用
    if report["local_models_used"]:
        lines.append(f"\n【正常使用的本地模型】({len(report['local_models_used'])}个)")
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="分析并修复工作流依赖")
    ap.add_argument("--workflow", required=True, help="工作流文件路径")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="3198")  # comfyui-cli项目标准端口
    ap.add_argument("--output", help="修复后的工作流输出路径")
    ap.add_argument("--fix", action="store_true", help="自动修复并输出工作流")
    args = ap.parse_args()
    
    # 分析依赖
    report = analyze_workflow_dependencies(args.workflow, args.host, args.port)
    
    # 生成报告
    install_report = generate_install_report(report)
    print(install_report)
    
    # 自动修复
    if args.fix and report["model_substitutions"]:
        output_path = args.output or args.workflow.replace(".json", "_fixed.json")
        fix_workflow_models(args.workflow, output_path, report["model_substitutions"], args.host, args.port)
        print(f"\n已自动修复工作流并保存到: {output_path}")
        report["fixed_workflow"] = output_path
    
    # 输出JSON报告
    print("\n" + json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
