#!/usr/bin/env python3
"""
工作流生成器
- 基于工作流资料库查询组件
- 根据用户需求组合生成新工作流
- 自动检测缺失依赖并提供替代方案
"""
import argparse
import json
import os
import random
import sys
import urllib.request

# 引入高级工作流组装相关模块（同目录下）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from advanced_workflow_builder import WorkflowAssembler
from pattern_extractor import load_patterns
from build_workflow_library import load_object_info


def load_library(path=".trae/skills/comfyui-controller/assets/workflow_library.json"):
    """加载工作流资料库"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_available_nodes(host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """获取服务器上可用的节点类型"""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/object_info", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # object_info 是 {node_type: schema} 字典，keys() 即节点类型
            if isinstance(data, dict):
                return list(data.keys())
            return []
    except Exception as e:
        return []


def scan_local_models(comfyui_path=None):
    """扫描本地所有模型文件"""
    if comfyui_path is None:
        comfyui_path = os.path.expanduser(os.environ.get("COMFYUI_PATH", ""))
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
                    if file.endswith(('.safetensors', '.ckpt', '.pt', '.pth', '.bin')):
                        models[category].append(file)
    
    return models


def find_similar_model(requested_name, available_models):
    """查找相似模型"""
    if not requested_name or not available_models:
        return None
    
    req_lower = requested_name.lower()
    best_match = None
    best_score = 0
    
    for model in available_models:
        model_lower = model.lower()
        score = 0
        
        if model_lower == req_lower:
            return model
        
        if req_lower in model_lower or model_lower in req_lower:
            score = 70
        
        # 关键词匹配
        req_words = set(req_lower.replace('_', ' ').replace('-', ' ').split())
        model_words = set(model_lower.replace('_', ' ').replace('-', ' ').split())
        if req_words:
            overlap = len(req_words & model_words) / len(req_words)
            score = max(score, overlap * 60)
        
        if score > best_score:
            best_score = score
            best_match = model
    
    return best_match if best_score > 40 else None


def query_components(library, category=None, node_type=None, model_type=None):
    """查询资料库中的组件"""
    results = {
        'workflows': [],
        'nodes': [],
        'models': [],
        'templates': []
    }
    
    # 按类别筛选工作流
    for name, info in library.get('workflows', {}).items():
        if category and info.get('category') != category:
            continue
        
        results['workflows'].append({
            'name': name,
            'category': info.get('category'),
            'node_count': info.get('node_count'),
            'path': info.get('path')
        })
        
        # 收集节点
        for nt in info.get('node_types', {}).keys():
            if node_type is None or node_type in nt:
                results['nodes'].append({
                    'type': nt,
                    'workflow': name,
                    'count': info['node_types'][nt]['count']
                })
        
        # 收集模型
        for mt, models in info.get('models', {}).items():
            if model_type is None or model_type == mt:
                for model in models:
                    if isinstance(model, str):
                        results['models'].append({
                            'type': mt,
                            'name': model,
                            'workflow': name
                        })
                    elif isinstance(model, dict):
                        results['models'].append({
                            'type': mt,
                            'name': model.get('value', ''),
                            'workflow': name
                        })
        
        # 收集模板
        template = info.get('template', {})
        if template:
            results['templates'].append({
                'name': name,
                'structure': template.get('structure', {}),
                'configurable': list(template.get('configurable', {}).keys())
            })
    
    return results


def generate_workflow(library, task_description, available_nodes=None, local_models=None,
                      target_model_family=None):
    """根据任务描述生成工作流建议。
    target_model_family: 指定大模型系列（如 'SD1.5'/'Flux'/'Wan2.2'），
                        不同系列工作流不能混用。None 时自动推断或忽略系列匹配。
    """

    # 解析任务类型
    task_lower = task_description.lower()

    category = '其他'
    if any(kw in task_lower for kw in ['文生图', '文生图片', 'txt2img', 'text to image', 't2i']):
        category = '文生图'
    elif any(kw in task_lower for kw in ['图生图', 'img2img', 'image to image', 'i2i']):
        category = '图生图'
    elif any(kw in task_lower for kw in ['图生视频', 'img2vid', 'image to video', 'i2v']):
        category = '图生视频'
    elif any(kw in task_lower for kw in ['文生视频', 'txt2vid', 'text to video', 't2v']):
        category = '文生视频'
    elif any(kw in task_lower for kw in ['动作迁移', 'motion', 'animate']):
        category = '动作迁移'
    elif any(kw in task_lower for kw in ['图片编辑', '编辑', 'edit', 'inpaint']):
        category = '图片编辑'
    elif any(kw in task_lower for kw in ['放大', 'upscale', '超分']):
        category = '放大'

    # 从任务描述中识别大模型系列（如 "用Flux生成" / "Wan2.2 视频"）
    if target_model_family is None:
        family_keywords = {
            'SD1.5': ['sd1.5', 'sd15', 'sd 1.5', 'stable diffusion 1.5'],
            'SDXL': ['sdxl', 'sd xl', 'stable diffusion xl'],
            'Flux': ['flux'],
            'Wan2.2': ['wan2.2', 'wan 2.2', 'wan2_2'],
            'HunyuanVideo': ['hunyuan', 'hunyuan video'],
            'LTX-Video': ['ltxv', 'ltx'],
        }
        for fam, keywords in family_keywords.items():
            if any(kw in task_lower for kw in keywords):
                target_model_family = fam
                break

    # 查询相关组件
    components = query_components(library, category=category)

    if not components['workflows']:
        return {
            'ok': False,
            'error': f'未找到类别 "{category}" 的工作流模板',
            'suggestion': '尝试使用其他描述或查看可用类别'
        }

    # 按大模型系列过滤工作流（不同系列不能混用）
    candidate_workflows = components['workflows']
    if target_model_family:
        matched = []
        for wf in candidate_workflows:
            wf_info = library['workflows'].get(wf['name'], {})
            wf_family = wf_info.get('model_family', 'unknown')
            if wf_family == target_model_family:
                matched.append(wf)
        if matched:
            candidate_workflows = matched
        # 若无匹配，保留全部候选并添加警告

    # 选择最匹配的工作流作为基础
    base_workflow = candidate_workflows[0]['name']
    base_info = library['workflows'].get(base_workflow, {})
    base_family = base_info.get('model_family', 'unknown')

    # 构建生成建议
    suggestion = {
        'ok': True,
        'task': task_description,
        'detected_category': category,
        'target_model_family': target_model_family,
        'base_workflow': base_workflow,
        'base_model_family': base_family,
        'family_mismatch': (target_model_family is not None and base_family != target_model_family
                            and base_family != 'unknown'),
        'base_path': base_info.get('path'),
        'suggested_nodes': [],
        'suggested_models': [],
        'missing_dependencies': [],
        'alternative_models': []
    }

    # 分析需要的节点
    required_nodes = list(base_info.get('node_types', {}).keys())

    if available_nodes:
        for node in required_nodes:
            if node not in available_nodes:
                suggestion['missing_dependencies'].append({
                    'type': 'missing_node',
                    'node': node,
                    'suggestion': f'需要安装提供 {node} 的自定义节点包'
                })

    # 分析需要的模型
    models = base_info.get('models', {})
    for model_type, model_list in models.items():
        if model_type == 'other':
            continue

        for model in model_list:
            if isinstance(model, str):
                model_name = model
            else:
                model_name = model.get('value', '')

            suggestion['suggested_models'].append({
                'type': model_type,
                'name': model_name
            })

            # 检查本地是否有
            if local_models:
                category_map = {
                    'checkpoints': 'checkpoints',
                    'unet': 'diffusion_models',
                    'vae': 'vae',
                    'clip': 'clip',
                    'lora': 'loras',
                    'controlnet': 'controlnet',
                    'upscale': 'upscale_models'
                }
                local_category = category_map.get(model_type)

                if local_category and local_category in local_models:
                    if model_name not in local_models[local_category]:
                        # 查找相似模型（同系列优先）
                        alt = find_similar_model(model_name, local_models[local_category])
                        if alt:
                            suggestion['alternative_models'].append({
                                'original': model_name,
                                'alternative': alt,
                                'category': local_category
                            })
                        else:
                            suggestion['missing_dependencies'].append({
                                'type': 'missing_model',
                                'model': model_name,
                                'category': model_type,
                                'suggestion': f'需要下载模型: {model_name}'
                            })

    # 提取可配置参数
    template = base_info.get('template', {})
    configurable = template.get('configurable', {})

    suggestion['configurable_params'] = []
    for key, param in configurable.items():
        suggestion['configurable_params'].append({
            'param': param['param'],
            'type': param['param_type'],
            'default': param['default_value'],
            'description': param['description']
        })

    return suggestion


def _infer_model_family(task_description):
    """从任务描述推断大模型系列（如 SD1.5/SDXL/Flux/Wan2.2）。
    返回匹配到的系列名，无法推断时返回 None。
    """
    task_lower = task_description.lower()
    family_keywords = {
        'SD1.5': ['sd1.5', 'sd15', 'sd 1.5', 'stable diffusion 1.5'],
        'SDXL': ['sdxl', 'sd xl', 'stable diffusion xl'],
        'Flux': ['flux'],
        'Wan2.2': ['wan2.2', 'wan 2.2', 'wan2_2'],
        'HunyuanVideo': ['hunyuan', 'hunyuan video'],
        'LTX-Video': ['ltxv', 'ltx'],
    }
    for fam, keywords in family_keywords.items():
        if any(kw in task_lower for kw in keywords):
            return fam
    return None


def generate_new_workflow_json(library, task_description, params=None, patterns=None,
                                object_info=None, target_model_family=None):
    """生成新的工作流 JSON（ComfyUI UI 格式）。

    基于 WorkflowAssembler 组装完整工作流，返回 ComfyUI UI 格式 JSON 及设计元数据。

    参数:
        library: 工作流资料库字典
        task_description: 任务描述文本
        params: 预留参数，当前未使用
        patterns: 模式库字典；为 None 时加载默认模式库
        object_info: 节点 schema 字典；为 None 时尝试从服务器加载（容错）
        target_model_family: 指定大模型系列；为 None 时从 task_description 推断

    返回:
        成功: {"ok": True, "workflow_json": ..., "design_source": ...,
               "design_notes": ..., "target_model_family": ...,
               "adapter_check": ..., "missing_dependencies": [...]}
        失败: {"ok": False, "error": "..."}
    """
    # 1. 加载默认模式库（若未提供）
    if patterns is None:
        default_patterns_path = os.path.join(
            ".trae", "skills", "comfyui-controller", "assets", "workflow_patterns.json"
        )
        try:
            patterns = load_patterns(default_patterns_path)
        except Exception:
            patterns = {"patterns": [], "warnings": []}

    # 2. 加载 object_info（容错，失败返回 {}）
    if object_info is None:
        try:
            object_info = load_object_info()
        except Exception:
            object_info = {}

    # 3. 推断大模型系列（若未指定）
    if target_model_family is None:
        target_model_family = _infer_model_family(task_description)

    # 4. 构造工作流组装器
    assembler = WorkflowAssembler(
        patterns=patterns,
        target_model_family=target_model_family,
        library=library,
        object_info=object_info,
    )

    # 5. 组装工作流图（异常时返回失败结构）
    try:
        graph = assembler.assemble(task_description)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # 6. 转换为 ComfyUI UI 格式 JSON
    workflow_json = graph.to_web_format()

    # 7. 提取设计元数据
    metadata = getattr(graph, "metadata", {}) or {}

    # 8. 检查缺失依赖（可选）：核对 workflow_json 中节点是否在 object_info 中
    missing_dependencies = []
    if object_info and isinstance(workflow_json, dict):
        for node in workflow_json.get("nodes", []):
            node_type = node.get("type")
            if node_type and node_type not in object_info:
                missing_dependencies.append({
                    "type": "missing_node",
                    "node": node_type,
                    "suggestion": f"需要安装提供 {node_type} 的自定义节点包"
                })

    # 9. 返回完整结构
    return {
        "ok": True,
        "workflow_json": workflow_json,
        "design_source": metadata.get("design_source"),
        "design_notes": metadata.get("design_notes"),
        "target_model_family": metadata.get("target_model_family"),
        "adapter_check": metadata.get("adapter_check"),
        "missing_dependencies": missing_dependencies,
    }


def main():
    ap = argparse.ArgumentParser(description="工作流生成器")
    ap.add_argument("--library", default=".trae/skills/comfyui-controller/assets/workflow_library.json",
                    help="资料库路径")
    ap.add_argument("--task", required=True, help="任务描述，例如：'生成一个文生图工作流'")
    ap.add_argument("--host", default="127.0.0.1", help="ComfyUI服务器地址")
    ap.add_argument("--port", default="3198", help="ComfyUI服务器端口")  # comfyui-cli项目标准端口
    ap.add_argument("--check-deps", action="store_true", help="检查依赖可用性")
    ap.add_argument("--model-family", help="指定大模型系列（如 SD1.5/SDXL/Flux/Wan2.2），不同系列工作流不能混用")
    ap.add_argument("--output", help="输出工作流JSON路径")
    args = ap.parse_args()

    # 加载资料库
    library = load_library(args.library)

    # 获取环境信息
    available_nodes = None
    local_models = None

    if args.check_deps:
        print("正在检查环境依赖...")
        available_nodes = get_available_nodes(args.host, args.port)
        local_models = scan_local_models()
        print(f"  可用节点: {len(available_nodes)}个")
        print(f"  本地模型类别: {list(local_models.keys())}")

    # 生成工作流建议
    print(f"\n根据任务 '{args.task}' 生成工作流建议...")
    if args.model_family:
        print(f"指定大模型系列: {args.model_family}")
    suggestion = generate_workflow(library, args.task, available_nodes, local_models,
                                   target_model_family=args.model_family)
    
    print(json.dumps(suggestion, indent=2, ensure_ascii=False))
    
    # 如果需要输出完整工作流 JSON（ComfyUI UI 格式）
    if args.output:
        print(f"\n生成完整工作流 JSON（ComfyUI UI 格式）...")
        # 透传 --model-family，避免推断错误导致系列混用
        result = generate_new_workflow_json(
            library, args.task,
            target_model_family=args.model_family,
        )
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"工作流已保存: {args.output}")
        if result.get('ok'):
            print(f"  design_source: {result.get('design_source')}")
            print(f"  design_notes: {result.get('design_notes')}")
            print(f"  target_model_family: {result.get('target_model_family')}")
            print(f"  adapter_check: {result.get('adapter_check')}")
            missing = result.get('missing_dependencies', [])
            if missing:
                print(f"  missing_dependencies: {len(missing)} 项")
                for m in missing:
                    print(f"    - {m.get('node')}: {m.get('suggestion')}")
        else:
            print(f"  生成失败: {result.get('error')}")


if __name__ == "__main__":
    main()
