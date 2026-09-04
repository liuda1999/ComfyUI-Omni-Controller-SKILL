#!/usr/bin/env python3
"""
深度分析 ComfyUI 工作流结构
- 解析每个节点的功能、参数、连接关系
- 识别用户可配置项
- 检测缺失的模型/节点/依赖
- 提供模型智能匹配建议
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from urllib.parse import unquote

# 添加模块搜索路径以便导入 build_workflow_library
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_workflow_library import build_node_annotations, build_execution_flow, load_object_info

# control_after_generate 标记值
_CONTROL_AFTER_GENERATE_VALUES = {"fixed", "increment", "randomize", "disable"}


def load_workflow(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


def _get_widget_names_from_object_info(node_type, object_info):
    """从 object_info schema 获取有序的 widget 输入名列表"""
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
                    if isinstance(input_type, list) or input_type in ("INT", "FLOAT", "STRING", "COMBO"):
                        widget_names.append(name)
    return widget_names


def analyze_node(node_id, node_data, object_info=None):
    """分析单个节点的详细信息"""
    class_type = node_data.get("class_type", "")
    inputs = node_data.get("inputs", {})

    # 获取节点定义信息（object_info 不可用时使用空字典，相关字段填空字符串）
    node_def = object_info.get(class_type, {}) if object_info else {}
    input_def = node_def.get("input", {})
    required_inputs = input_def.get("required", {})
    optional_inputs = input_def.get("optional", {})
    output_def = node_def.get("output", [])
    output_names = node_def.get("output_name", [])
    output_is_list = node_def.get("output_is_list", [])

    # 分析每个输入参数
    input_analysis = {}
    for inp_name, inp_value in inputs.items():
        inp_def = required_inputs.get(inp_name) or optional_inputs.get(inp_name)
        is_connected = isinstance(inp_value, list) and len(inp_value) == 2

        input_analysis[inp_name] = {
            "value": inp_value,
            "is_connected": is_connected,
            "type": inp_def[0] if isinstance(inp_def, list) and len(inp_def) > 0 else "unknown",
            "config": inp_def[1] if isinstance(inp_def, list) and len(inp_def) > 1 else {},
            "is_required": inp_name in required_inputs
        }

    # 分析输出
    outputs = []
    for i, out_type in enumerate(output_def):
        outputs.append({
            "type": out_type,
            "name": output_names[i] if i < len(output_names) else f"output_{i}",
            "is_list": output_is_list[i] if i < len(output_is_list) else False
        })

    return {
        "node_id": node_id,
        "class_type": class_type,
        "display_name": node_def.get("display_name", class_type),
        "category": node_def.get("category", "unknown"),
        "description": node_def.get("description", ""),
        "inputs": input_analysis,
        "outputs": outputs,
        "python_module": node_def.get("python_module", ""),
        "is_custom_node": not node_def.get("python_module", "").startswith("comfy.")
    }


def find_model_issues(node_analysis, object_info, local_models):
    """检测模型相关问题"""
    issues = []
    suggestions = []

    model_loaders = ["CheckpointLoaderSimple", "UNETLoader", "VAELoader", "CLIPLoader",
                     "ControlNetLoader", "LoraLoader", "UpscaleModelLoader",
                     # WanVideo V18/V19 架构加载器
                     "WanVideoModelLoader", "WanVideoVAELoader", "LoadWanVideoT5TextEncoder",
                     "CLIPVisionLoader", "WanVideoLoraSelect"]

    if node_analysis["class_type"] in model_loaders:
        for inp_name, inp_data in node_analysis["inputs"].items():
            if inp_name.endswith("_name") and not inp_data["is_connected"]:
                model_name = inp_data["value"]
                # 跳过空值/None/非字符串（widget 映射失败或未设置时可能为 None）
                if not isinstance(model_name, str) or not model_name:
                    continue
                model_type = node_analysis["class_type"]

                # 获取服务器上可用的模型列表
                node_def = object_info.get(model_type, {})
                input_def = node_def.get("input", {}).get("required", {})
                inp_config = input_def.get(inp_name, [])
                available_models = []
                if isinstance(inp_config, list) and len(inp_config) > 0:
                    # 兼容两种格式：
                    # 旧: [["model1", "model2"], {config}]
                    # 新(v0.27+): ["COMBO", {"options": ["model1", ...], ...}]
                    first = inp_config[0]
                    if isinstance(first, list):
                        available_models = first
                    elif isinstance(first, str) and len(inp_config) > 1 and isinstance(inp_config[1], dict):
                        options = inp_config[1].get("options", [])
                        if isinstance(options, list):
                            available_models = options

                if model_name not in available_models:
                    issues.append({
                        "type": "model_not_found",
                        "node_id": node_analysis["node_id"],
                        "node_type": model_type,
                        "param_name": inp_name,
                        "requested_model": model_name,
                        "available_models": available_models
                    })

                    # 智能匹配建议
                    match = find_similar_model(model_name, available_models, local_models)
                    if match:
                        suggestions.append({
                            "type": "model_substitution",
                            "original": model_name,
                            "suggested": match,
                            "reason": f"名称相似或同系列模型"
                        })

    return issues, suggestions


def find_similar_model(requested, available, local_models):
    """智能匹配相似模型"""
    if not available:
        return None

    req_lower = requested.lower()
    req_base = re.sub(r'[_\-\.]', '', req_lower)
    req_base = re.sub(r'(fp8|fp16|fp32|bf16|e4m3fn|e5m2|scaled|quantized|v\d+\.\d+|\d+b|q\d+\w*|iq\d+\w*|f16|f32|\.safetensors|\.ckpt|gguf).*$', '', req_base)

    best_match = None
    best_score = 0

    for model in available:
        model_lower = model.lower()
        model_base = re.sub(r'[_\-\.]', '', model_lower)
        model_base = re.sub(r'(fp8|fp16|fp32|bf16|e4m3fn|e5m2|scaled|quantized|v\d+\.\d+|\d+b|q\d+\w*|iq\d+\w*|f16|f32|\.safetensors|\.ckpt|gguf).*$', '', model_base)

        score = 0

        # 完全匹配
        if model_lower == req_lower:
            return model

        # 基础名称匹配
        if req_base == model_base:
            score = 90

        # 包含关系
        if req_base in model_base or model_base in req_base:
            score = max(score, 70)

        # 关键词匹配
        req_keywords = set(re.findall(r'[a-z]+', req_base))
        model_keywords = set(re.findall(r'[a-z]+', model_base))
        common = req_keywords & model_keywords
        if req_keywords:
            keyword_score = len(common) / len(req_keywords) * 60
            score = max(score, keyword_score)

        if score > best_score:
            best_score = score
            best_match = model

    # 也检查本地模型
    for local_model in local_models:
        local_lower = local_model.lower()
        local_base = re.sub(r'[_\-\.]', '', local_lower)
        local_base = re.sub(r'(fp8|fp16|fp32|bf16|e4m3fn|e5m2|scaled|quantized|v\d+\.\d+|\d+b|q\d+\w*|iq\d+\w*|f16|f32|\.safetensors|\.ckpt|gguf).*$', '', local_base)

        if req_base == local_base:
            if local_model in available:
                return local_model

    return best_match if best_score > 50 else None


def _build_link_map(links):
    """从 links 列表构建 link_id -> (source_node, source_slot, target_node, target_slot) 映射"""
    link_map = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            link_map[link[0]] = (link[1], link[2], link[3], link[4])
    return link_map


def analyze_workflow_structure(workflow, object_info=None):
    """分析整个工作流的结构"""
    nodes = workflow.get("nodes", [])
    links = workflow.get("links", [])

    # 构建连接图
    link_map = {}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            link_map[link[0]] = {
                "source_id": str(link[1]),
                "source_slot": link[2],
                "target_id": str(link[3]),
                "target_slot": link[4]
            }

    # 构建节点连接关系
    node_connections = {}
    for node in nodes:
        node_id = str(node.get("id"))
        node_connections[node_id] = {
            "inputs": {},
            "outputs": {}
        }

    for link_id, link_data in link_map.items():
        src_id = link_data["source_id"]
        tgt_id = link_data["target_id"]

        if tgt_id in node_connections:
            node_connections[tgt_id]["inputs"][link_data["target_slot"]] = {
                "from_node": src_id,
                "from_slot": link_data["source_slot"],
                "link_id": link_id
            }

        if src_id in node_connections:
            if link_data["source_slot"] not in node_connections[src_id]["outputs"]:
                node_connections[src_id]["outputs"][link_data["source_slot"]] = []
            node_connections[src_id]["outputs"][link_data["source_slot"]].append({
                "to_node": tgt_id,
                "to_slot": link_data["target_slot"],
                "link_id": link_id
            })

    # 若 object_info 为 None，调用 load_object_info 获取
    if object_info is None:
        object_info = load_object_info()

    # 构建节点注解（display_name/description/category/python_module）
    node_annotations = build_node_annotations(workflow, object_info)

    # 构建执行流程（拓扑排序后的步骤列表）
    execution_flow = build_execution_flow(workflow, node_annotations)

    return {
        "node_connections": node_connections,
        "node_annotations": node_annotations,
        "execution_flow": execution_flow
    }


def get_local_models(comfyui_path):
    """获取本地所有模型文件"""
    models = []
    models_dir = os.path.join(comfyui_path, "models")
    if not os.path.isdir(models_dir):
        return models

    for root, dirs, files in os.walk(models_dir):
        for file in files:
            if file.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin', '.gguf')):
                models.append(file)

    return models


def main():
    ap = argparse.ArgumentParser(description="深度分析 ComfyUI 工作流")
    ap.add_argument("--workflow", required=True, help="工作流文件路径")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="3198")  # comfyui-cli项目标准端口
    default_path = os.path.expanduser(os.environ.get("COMFYUI_PATH", ""))
    ap.add_argument("--comfyui-path", default=default_path,
                    help="ComfyUI 安装路径 (默认从 COMFYUI_PATH 环境变量读取)")
    ap.add_argument("--output", help="分析结果输出路径")
    args = ap.parse_args()

    # 加载数据
    workflow = load_workflow(args.workflow)
    object_info = load_object_info(args.host, args.port)
    local_models = get_local_models(args.comfyui_path)

    if not object_info:
        print(json.dumps({
            "ok": False,
            "error": "无法连接服务器获取节点信息"
        }))
        return

    # 构建 link_map 用于连接查找
    link_map = _build_link_map(workflow.get("links", []))

    # 分析结构（返回 node_connections、node_annotations、execution_flow）
    structure = analyze_workflow_structure(workflow, object_info)
    connections = structure["node_connections"]
    node_annotations = structure["node_annotations"]
    execution_flow = structure["execution_flow"]

    # 分析每个节点
    node_analyses = []
    all_issues = []
    all_suggestions = []

    for node in workflow.get("nodes", []):
        node_id = str(node.get("id"))
        node_type = node.get("type", "")

        # 构建API格式的节点数据
        node_data = {
            "class_type": node_type,
            "inputs": {}
        }

        # 使用 object_info 获取 widget 名称列表，正确映射 widget 值
        widgets_values = node.get("widgets_values", [])
        if not isinstance(widgets_values, list):
            widgets_values = []

        # 过滤 control_after_generate 标记
        filtered_values = _filter_control_values(widgets_values)

        # 从 object_info 获取 widget 名称
        widget_names = _get_widget_names_from_object_info(node_type, object_info)

        # 构建已连接输入名集合
        connected_names = set()
        for inp in node.get("inputs", []):
            if inp.get("link") is not None:
                connected_names.add(inp.get("name", ""))

        # 映射 widget 值到参数名
        for idx, param_name in enumerate(widget_names):
            if param_name in connected_names:
                continue
            if idx >= len(filtered_values):
                break
            node_data["inputs"][param_name] = filtered_values[idx]

        # 添加连接（使用 link_map 而非直接索引 links 列表）
        for inp in node.get("inputs", []):
            link_id = inp.get("link")
            if link_id is not None and link_id in link_map:
                source_node, source_slot, _, _ = link_map[link_id]
                node_data["inputs"][inp.get("name")] = [str(source_node), source_slot]

        analysis = analyze_node(node_id, node_data, object_info)
        analysis["position"] = node.get("pos", [0, 0])
        analysis["size"] = node.get("size", [0, 0])
        analysis["connections"] = connections.get(node_id, {"inputs": {}, "outputs": {}})

        # 检测问题
        issues, suggestions = find_model_issues(analysis, object_info, local_models)
        analysis["issues"] = issues
        analysis["suggestions"] = suggestions
        all_issues.extend(issues)
        all_suggestions.extend(suggestions)

        node_analyses.append(analysis)

    # 构建完整分析报告
    report = {
        "ok": True,
        "workflow_info": {
            "id": workflow.get("id", ""),
            "revision": workflow.get("revision", 0),
            "last_node_id": workflow.get("last_node_id", 0),
            "last_link_id": workflow.get("last_link_id", 0),
            "total_nodes": len(workflow.get("nodes", [])),
            "total_links": len(workflow.get("links", []))
        },
        "nodes": node_analyses,
        "node_annotations": node_annotations,
        "execution_flow": execution_flow,
        "summary": {
            "total_issues": len(all_issues),
            "total_suggestions": len(all_suggestions),
            "issues": all_issues,
            "suggestions": all_suggestions,
            "local_models_found": len(local_models)
        }
    }

    # 输出结果
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
