#!/usr/bin/env python3
"""
工作流生成资料库构建器
- 扫描指定目录及子目录内所有工作流
- 深度分析每个工作流的结构、节点、模型、参数
- 提取可复用的组件模板
- 生成资料库索引供后续查询和生成新工作流
"""
import argparse
import json
import os
import re
import urllib.request
from datetime import datetime
from collections import defaultdict, deque
from pathlib import Path


# control_after_generate 标记值（UI 格式 widgets_values 中会插入）
_CONTROL_AFTER_GENERATE_VALUES = {"fixed", "increment", "randomize", "disable"}


def load_object_info(host="127.0.0.1", port="3198", object_info_path=None):  # comfyui-cli项目标准端口
    """加载 object_info（节点 schema），用于 widget 名称映射。
    优先从本地文件加载，其次从服务器获取。失败时返回空字典。
    """
    if object_info_path and os.path.isfile(object_info_path):
        try:
            with open(object_info_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    try:
        req = urllib.request.Request(f"http://{host}:{port}/object_info", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


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
    """从 object_info schema 获取有序的 widget 输入名列表。
    UI 格式的 node["inputs"] 只包含连接输入，widget 定义必须从 object_info 获取。
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
                    # widget 类型：列表（combo 选择）、INT、FLOAT、STRING
                    if isinstance(input_type, list) or input_type in ("INT", "FLOAT", "STRING"):
                        widget_names.append(name)
    return widget_names


# 大模型系列识别规则（按优先级排序，先匹配的优先）
# 不同大模型系列的工作流不能混用（如 SD1.5 的 LoRA 不能用于 SDXL/Flux/Wan2.2）
_MODEL_FAMILY_RULES = [
    # 视频模型
    ("Wan2.2", ["wan2.2", "wan2_2", "wan21", "wan2.1", "wan2_1", "wananimate", "lightx2v"], "video"),
    ("HunyuanVideo", ["hunyuan", "hyvideo"], "video"),
    ("LTX-Video", ["ltxv", "ltx-video"], "video"),
    ("CogVideoX", ["cogvideo", "cogvideox"], "video"),
    ("Mochi", ["mochi"], "video"),
    ("AnimateDiff", ["animatediff", "anisight"], "video"),
    ("Qwen-VL", ["qwen-vl", "qwen_vl", "qwenvl", "qwen2vl", "qwen2_vl"], "video"),
    # 图像模型
    ("Flux", ["flux", "f2k"], "image"),
    ("SD3", ["sd3", "stable-diffusion-3", "sdxl3"], "image"),
    ("SDXL", ["sdxl", "sd_xl", "stable-diffusion-xl"], "image"),
    ("SD1.5", ["sd1.5", "sd-1", "v1-5", "sd15", "anything-v", "dreamshaper", "chilloutmix",
               "control_v11", "openpose", "canny", "depth", "tile", "ip2p"], "image"),
    ("Pony", ["pony", "ponyxl"], "image"),
    ("Illustrious", ["illustrious", "illus"], "image"),
    ("SAM", ["sam3", "sam2", "sam-", "segment-anything"], "image"),
    # 文本/LLM
    ("LLM", ["llama", "qwen", "mistral", "gemma"], "text"),
]


def detect_model_family(model_name):
    """根据模型文件名识别大模型系列。
    返回 (family, modality) 元组，family 如 'SD1.5'/'Flux'/'Wan2.2'，
    modality 为 'image'/'video'/'text'/'unknown'。无法识别时返回 ('unknown', 'unknown')。
    不同 family 的工作流不能混用。
    """
    if not isinstance(model_name, str) or not model_name:
        return ("unknown", "unknown")
    name_lower = model_name.lower()
    for family, keywords, modality in _MODEL_FAMILY_RULES:
        for kw in keywords:
            if kw in name_lower:
                return (family, modality)
    return ("unknown", "unknown")


def detect_workflow_model_family(workflow, object_info=None):
    """识别工作流所依赖的大模型系列。
    综合考虑 checkpoint/unet/lora/controlnet 等模型，返回主模型系列。
    优先级：checkpoint/unet > lora > controlnet。
    返回 (family, modality, detected_models) 元组。
    """
    detected = []  # [(family, modality, model_name, model_role)]
    nodes = workflow.get('nodes', [])

    for node in nodes:
        node_type = node.get('type', '')
        widgets_values = node.get('widgets_values', [])
        if not isinstance(widgets_values, list):
            widgets_values = []

        # 确定模型角色和 widget 索引
        model_role = None
        model_name = None

        if node_type == 'CheckpointLoaderSimple':
            model_role = 'checkpoint'
            # ckpt_name 是第一个 widget
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type in ('UNETLoader', 'UnetLoaderGGUF'):
            model_role = 'unet'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type in ('LoraLoader', 'LoraLoaderModelOnly'):
            model_role = 'lora'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type == 'ControlNetLoader':
            model_role = 'controlnet'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type == 'VAELoader':
            model_role = 'vae'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        # WanVideo V18/V19 架构加载器
        elif node_type == 'WanVideoModelLoader':
            model_role = 'unet'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type == 'WanVideoVAELoader':
            model_role = 'vae'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type == 'LoadWanVideoT5TextEncoder':
            model_role = 'clip'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]
        elif node_type == 'WanVideoLoraSelect':
            model_role = 'lora'
            if widgets_values and isinstance(widgets_values[0], str):
                model_name = widgets_values[0]

        if model_name:
            family, modality = detect_model_family(model_name)
            if family != 'unknown':
                detected.append((family, modality, model_name, model_role))

    if not detected:
        return ("unknown", "unknown", [])

    # 主模型系列：优先 checkpoint/unet，其次 lora，最后 controlnet
    role_priority = {'checkpoint': 0, 'unet': 0, 'lora': 1, 'controlnet': 2, 'vae': 3, 'clip': 4}
    detected.sort(key=lambda x: role_priority.get(x[3], 9))

    primary_family = detected[0][0]
    primary_modality = detected[0][1]
    return (primary_family, primary_modality, detected)


def get_workflow_files(directory):
    """递归获取所有工作流文件（跳过 archive/ 子目录，避免历史版本污染索引）"""
    workflows = []
    for root, dirs, files in os.walk(directory):
        # 跳过 archive 子目录（旧版本归档，不纳入资料库索引）
        dirs[:] = [d for d in dirs if d != 'archive']
        for file in files:
            if file.endswith('.json') and file != '.index.json':
                workflows.append(os.path.join(root, file))
    return workflows


def load_workflow(path):
    """加载工作流文件"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


def extract_node_types(workflow):
    """提取工作流中所有节点类型"""
    nodes = workflow.get('nodes', [])
    node_types = {}
    
    for node in nodes:
        node_type = node.get('type', '')
        node_id = str(node.get('id', ''))
        
        if node_type not in node_types:
            node_types[node_type] = {
                'count': 0,
                'instances': [],
                'inputs': set(),
                'outputs': set()
            }
        
        node_types[node_type]['count'] += 1
        node_types[node_type]['instances'].append(node_id)
        
        # 收集输入类型
        for inp in node.get('inputs', []):
            if isinstance(inp, dict):
                inp_type = inp.get('type', '')
                if isinstance(inp_type, list):
                    inp_type = tuple(inp_type)
                node_types[node_type]['inputs'].add(inp_type)
        
        # 收集输出类型
        for out in node.get('outputs', []):
            if isinstance(out, dict):
                out_type = out.get('type', '')
                if isinstance(out_type, list):
                    out_type = tuple(out_type)
                node_types[node_type]['outputs'].add(out_type)
    
    # 转换set为list以便JSON序列化
    for nt in node_types.values():
        nt['inputs'] = list(nt['inputs'])
        nt['outputs'] = list(nt['outputs'])
    
    return node_types


def extract_models(workflow):
    """提取工作流中使用的所有模型"""
    models = {
        'checkpoints': [],
        'unet': [],
        'vae': [],
        'clip': [],
        'lora': [],
        'controlnet': [],
        'upscale': [],
        'other': []
    }
    
    nodes = workflow.get('nodes', [])
    
    for node in nodes:
        node_type = node.get('type', '')
        widgets_values = node.get('widgets_values', [])
        
        # 根据节点类型直接判断模型参数位置
        if node_type == 'CheckpointLoaderSimple' and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['checkpoints'].append(widgets_values[0])
        elif node_type == 'UNETLoader' and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['unet'].append(widgets_values[0])
        elif node_type == 'VAELoader' and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['vae'].append(widgets_values[0])
        elif node_type == 'CLIPLoader' and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['clip'].append(widgets_values[0])
        elif node_type in ['LoraLoader', 'LoraLoaderModelOnly'] and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['lora'].append(widgets_values[0])
        elif node_type == 'ControlNetLoader' and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['controlnet'].append(widgets_values[0])
        elif 'Upscale' in node_type and 'Loader' in node_type and len(widgets_values) > 0:
            if isinstance(widgets_values[0], str):
                models['upscale'].append(widgets_values[0])
        else:
            # 对于其他节点，检查widgets_values中是否有模型文件名
            for value in widgets_values:
                if isinstance(value, str) and (
                    value.endswith('.safetensors') or 
                    value.endswith('.ckpt') or 
                    value.endswith('.pt') or
                    value.endswith('.pth')
                ):
                    models['other'].append({
                        'node_type': node_type,
                        'value': value
                    })
    
    # 去重
    for key in models:
        if key != 'other':
            models[key] = list(set(models[key]))
    
    return models


def extract_parameters(workflow, object_info=None):
    """提取工作流中的可配置参数。
    使用 object_info 进行 widget 名称映射（UI 格式 inputs 不含 widget 定义）。
    """
    params = {
        'prompts': {},
        'sampler': {},
        'resolution': {},
        'models': {},
        'other': {}
    }

    nodes = workflow.get('nodes', [])

    for node in nodes:
        node_type = node.get('type', '')
        node_id = str(node.get('id', ''))
        widgets_values = node.get('widgets_values', [])
        if not isinstance(widgets_values, list):
            widgets_values = []
        inputs = node.get('inputs', [])

        # 过滤 control_after_generate 标记
        filtered_values = _filter_control_values(widgets_values)

        # 从 object_info 获取 widget 名称列表
        widget_names = _get_widget_names_from_object_info(node_type, object_info)

        # 构建已连接输入名集合
        connected_names = set()
        for inp in inputs:
            if isinstance(inp, dict) and inp.get('link') is not None:
                connected_names.add(inp.get('name', ''))

        # 构建 widget_name -> value 映射
        widget_map = {}
        for idx, param_name in enumerate(widget_names):
            if param_name in connected_names:
                continue
            if idx >= len(filtered_values):
                break
            widget_map[param_name] = filtered_values[idx]

        # 提取提示词
        if node_type == 'CLIPTextEncode':
            title = node.get('_meta', {}).get('title', '')
            if 'text' in widget_map:
                prompt_type = 'positive' if 'negative' not in title.lower() else 'negative'
                params['prompts'][f"{prompt_type}_{node_id}"] = {
                    'text': widget_map['text'],
                    'node_id': node_id,
                    'title': title
                }

        # 提取采样器参数
        if node_type in ['KSampler', 'SamplerCustom', 'BasicSampler']:
            sampler_params = {}
            for pname in ['seed', 'steps', 'cfg', 'sampler_name', 'scheduler', 'denoise']:
                if pname in widget_map:
                    sampler_params[pname] = widget_map[pname]
            if sampler_params:
                params['sampler'][node_id] = sampler_params

        # 提取分辨率
        if node_type == 'EmptyLatentImage':
            for pname in ['width', 'height', 'batch_size']:
                if pname in widget_map:
                    params['resolution'][pname] = widget_map[pname]

        # 提取模型参数
        if node_type in ['CheckpointLoaderSimple', 'UNETLoader', 'VAELoader', 'CLIPLoader']:
            model_params = {}
            for pname, value in widget_map.items():
                if pname.endswith('_name') or pname in ['type', 'device', 'weight_dtype']:
                    model_params[pname] = value
            if model_params:
                params['models'][node_id] = {
                    'node_type': node_type,
                    'params': model_params
                }

    return params


def extract_connections(workflow):
    """提取节点连接关系"""
    links = workflow.get('links', [])
    connections = []
    
    for link in links:
        if isinstance(link, list) and len(link) >= 4:
            connections.append({
                'link_id': link[0],
                'source_node': link[1],
                'source_slot': link[2],
                'target_node': link[3],
                'target_slot': link[4] if len(link) > 4 else 0
            })
    
    return connections


def analyze_workflow_category(filepath, workflow=None):
    """根据文件路径和工作流内容分析工作流类别。
    优先根据路径关键词判断，路径无匹配时根据节点类型推断。
    """
    # 路径关键词（含常见缩写 t2i/i2i/i2v/t2v）
    categories = {
        '文生图': ['文生图', '文生图片', 'txt2img', 'text2image', 't2i'],
        '图生图': ['图生图', 'img2img', 'image2image', 'i2i'],
        '图生视频': ['图生视频', 'img2vid', 'image2video', 'i2v'],
        '文生视频': ['文生视频', 'txt2vid', 'text2video', 't2v'],
        '动作迁移': ['动作迁移', 'motion', 'animate'],
        '图片编辑': ['图片编辑', '编辑', 'edit', 'inpaint', 'outpaint'],
        '视频编辑': ['视频编辑', 'video_edit'],
        '放大': ['放大', 'upscale', '超分'],
        '基础': ['基础', 'basic', 'default']
    }

    path_lower = filepath.lower()
    for category, keywords in categories.items():
        for keyword in keywords:
            if keyword.lower() in path_lower:
                return category

    # 路径无匹配时，根据节点类型推断
    if workflow is not None:
        node_types = set()
        for node in workflow.get('nodes', []):
            nt = node.get('type', '')
            if nt:
                node_types.add(nt)

        # 视频类节点
        video_nodes = {'VHS_VideoCombine', 'SaveAnimatedWEBP', 'SaveWEBP',
                       'WanVideoTextEncode', 'WanVideoSampler', 'WanVideoDecode',
                       'EmptyMochiLatentVideo', 'MochiSampler', 'MochiDecode'}
        if node_types & video_nodes:
            if 'LoadImage' in node_types:
                return '图生视频'
            return '文生视频'

        # 放大类节点
        upscale_nodes = {'UpscaleModelLoader', 'ImageUpscaleWithModel',
                         'LatentUpscale', 'ModelUpscale'}
        if node_types & upscale_nodes and 'KSampler' not in node_types:
            return '放大'

        # 图生图：有 LoadImage + KSampler
        if 'LoadImage' in node_types and 'KSampler' in node_types:
            return '图生图'

        # 文生图：有 EmptyLatentImage + KSampler
        if 'EmptyLatentImage' in node_types and 'KSampler' in node_types:
            return '文生图'

        # ControlNet 类
        if any('ControlNet' in nt for nt in node_types):
            return '图片编辑'

    return '其他'


def extract_custom_nodes(workflow):
    """提取使用的自定义节点（非comfy核心节点）"""
    nodes = workflow.get('nodes', [])
    custom_nodes = set()
    
    core_nodes = {
        'CheckpointLoaderSimple', 'UNETLoader', 'VAELoader', 'CLIPLoader',
        'CLIPTextEncode', 'KSampler', 'SamplerCustom', 'BasicSampler',
        'EmptyLatentImage', 'VAEDecode', 'VAEEncode', 'SaveImage', 'PreviewImage',
        'LoraLoader', 'LoraLoaderModelOnly', 'ControlNetLoader', 'ControlNetApply',
        'ControlNetApplyAdvanced', 'UpscaleModelLoader', 'ImageUpscaleWithModel',
        'LatentUpscale', 'LoadImage', 'LoadImageMask', 'ConditioningCombine',
        'ConditioningAverage', 'ConditioningConcat', 'CLIPSetLastLayer'
    }
    
    for node in nodes:
        node_type = node.get('type', '')
        if node_type not in core_nodes:
            custom_nodes.add(node_type)
    
    return list(custom_nodes)


def build_node_annotations(workflow, object_info):
    """构建节点注解信息。
    遍历工作流节点，从 object_info 提取每个节点类型的 display_name/description/category/python_module。
    返回结构：{node_id_str: {display_name, description, category, python_module, is_custom_node}}
    - object_info 为空时返回空字典并打印警告（不抛异常）
    - 节点类型不在 object_info 中时 is_custom_node=True，其余字段为空字符串
    """
    annotations = {}
    # object_info 为空时返回空字典并打印警告
    if not object_info:
        print("警告：object_info 为空，无法提取节点注解信息")
        return annotations

    nodes = workflow.get('nodes', [])
    for node in nodes:
        node_type = node.get('type', '')
        node_id = str(node.get('id', ''))
        if not node_id:
            continue

        # 节点类型不在 object_info 中时标记为自定义节点
        if node_type not in object_info:
            annotations[node_id] = {
                'display_name': '',
                'description': '',
                'category': '',
                'python_module': '',
                'is_custom_node': True
            }
            continue

        # 从 object_info 提取节点 schema 信息（object_info 中字段值可能为 None，需用 `or ''` 兜底）
        node_schema = object_info[node_type]
        annotations[node_id] = {
            'display_name': node_schema.get('display_name') or '',
            'description': node_schema.get('description') or '',
            'category': node_schema.get('category') or '',
            'python_module': node_schema.get('python_module') or '',
            'is_custom_node': False
        }

    return annotations


def build_execution_flow(workflow, node_annotations):
    """构建执行流程。
    基于 workflow 的 nodes 和 links 构建邻接表，使用 Kahn 算法做拓扑排序。
    返回结构：{"steps": [...], "cycle_warning": [...] 或 None}
    - 节点显示名优先使用 node_annotations 中的 display_name，无则回退到 node.type
    - 检测循环依赖：拓扑排序后剩余节点数 < 总节点数时附加 cycle_warning
    - 循环依赖时不抛异常，仍输出部分执行流程
    - links 数组格式为 6 元素：[link_id, source_id, source_slot, target_id, target_slot, type]
    """
    nodes = workflow.get('nodes', [])
    links = workflow.get('links', [])

    # 收集所有节点 id 和节点映射
    node_ids = set()
    node_map = {}
    for node in nodes:
        nid = node.get('id')
        if nid is None:
            continue
        node_ids.add(nid)
        node_map[nid] = node

    # 构建邻接表和入度表
    adjacency = defaultdict(list)
    in_degree = {nid: 0 for nid in node_ids}

    # links 格式：[link_id, source_id, source_slot, target_id, target_slot, type]
    for link in links:
        if not isinstance(link, list) or len(link) < 5:
            continue
        source_id = link[1]
        target_id = link[3]
        if source_id in node_ids and target_id in node_ids:
            adjacency[source_id].append(target_id)
            in_degree[target_id] += 1

    # Kahn 算法拓扑排序：使用队列处理入度为 0 的节点
    queue = deque([nid for nid in node_ids if in_degree[nid] == 0])
    sorted_ids = []
    while queue:
        nid = queue.popleft()
        sorted_ids.append(nid)
        for target in adjacency[nid]:
            in_degree[target] -= 1
            if in_degree[target] == 0:
                queue.append(target)

    # 检测循环依赖：剩余节点数 < 总节点数说明存在环
    cycle_warning = None
    if len(sorted_ids) < len(node_ids):
        sorted_set = set(sorted_ids)
        cycle_warning = [str(nid) for nid in node_ids if nid not in sorted_set]

    # 构建有序步骤列表
    steps = []
    for idx, nid in enumerate(sorted_ids, 1):
        node = node_map[nid]
        node_type = node.get('type', '')
        node_id_str = str(nid)
        # 优先使用 node_annotations 中的 display_name，无则回退到 node.type
        annotation = node_annotations.get(node_id_str, {})
        display_name = annotation.get('display_name', '') or node_type
        # 括号内只放用户自定义的 _meta.title（通常是中文简短描述如"加载模型"），
        # 不放 object_info 的 description（那是英文长描述，不适合放在步骤名中）
        title = ''
        meta = node.get('_meta')
        if isinstance(meta, dict):
            title = meta.get('title', '') or ''
        # 构建步骤文本
        if title:
            steps.append(f"{idx}.{display_name}({title})")
        else:
            steps.append(f"{idx}.{display_name}")

    return {
        'steps': steps,
        'cycle_warning': cycle_warning
    }


def build_workflow_template(workflow, name, object_info=None, filepath=None):
    """构建工作流模板（去除具体值，保留结构）。
    使用 object_info 进行 widget 名称映射。
    filepath 用于提取文件元信息（mtime/size）。
    """
    nodes = workflow.get('nodes', [])
    template = {
        'name': name,
        'structure': {
            'node_types': [],
            'data_flow': []
        },
        'configurable': {},
        'node_annotations': {},   # 节点注解
        'execution_flow': {},     # 执行流程
        'file_meta': {}           # 文件元信息（mtime/size）
    }

    # 提取节点类型序列（按执行顺序）
    node_sequence = []
    for node in sorted(nodes, key=lambda x: x.get('order', 0)):
        node_type = node.get('type', '')
        if node_type not in [n['type'] for n in node_sequence]:
            node_sequence.append({
                'type': node_type,
                'category': 'loader' if 'Loader' in node_type else (
                    'sampler' if 'Sampler' in node_type else (
                    'encoder' if 'Encode' in node_type else (
                    'decoder' if 'Decode' in node_type else 'processor'
                )))
            })

    template['structure']['node_types'] = node_sequence

    # 提取可配置项模板（使用 object_info widget 映射）
    for node in nodes:
        node_type = node.get('type', '')
        node_id = str(node.get('id', ''))
        widgets_values = node.get('widgets_values', [])
        if not isinstance(widgets_values, list):
            widgets_values = []
        inputs = node.get('inputs', [])

        # 过滤 control_after_generate 标记
        filtered_values = _filter_control_values(widgets_values)

        # 从 object_info 获取 widget 名称列表
        widget_names = _get_widget_names_from_object_info(node_type, object_info)

        # 构建已连接输入名集合
        connected_names = set()
        for inp in inputs:
            if isinstance(inp, dict) and inp.get('link') is not None:
                connected_names.add(inp.get('name', ''))

        # 映射 widget 值并提取可配置项
        for idx, param_name in enumerate(widget_names):
            if param_name in connected_names:
                continue
            if idx >= len(filtered_values):
                break
            value = filtered_values[idx]

            # 判断是否为可配置参数
            is_configurable = False
            param_type = 'unknown'

            if param_name in ['text', 'prompt']:
                is_configurable = True
                param_type = 'prompt'
            elif param_name in ['seed', 'steps', 'cfg', 'denoise']:
                is_configurable = True
                param_type = 'sampler'
            elif param_name in ['width', 'height', 'batch_size']:
                is_configurable = True
                param_type = 'resolution'
            elif param_name.endswith('_name'):
                is_configurable = True
                param_type = 'model'
            elif param_name in ['sampler_name', 'scheduler']:
                is_configurable = True
                param_type = 'sampler_config'

            if is_configurable:
                key = f"{node_type}.{param_name}"
                if key not in template['configurable']:
                    template['configurable'][key] = {
                        'node_type': node_type,
                        'param': param_name,
                        'param_type': param_type,
                        'default_value': value,
                        'input_type': '',
                        'description': param_name
                    }

    # 构建节点注解（display_name/description/category/python_module）
    template['node_annotations'] = build_node_annotations(workflow, object_info)
    # 构建执行流程（拓扑排序后的步骤列表）
    template['execution_flow'] = build_execution_flow(workflow, template['node_annotations'])
    # 文件元信息：从源文件 os.stat 获取 mtime 和 size
    file_meta = {'mtime': None, 'size': None}
    if filepath and os.path.isfile(filepath):
        try:
            stat_info = os.stat(filepath)
            file_meta = {'mtime': stat_info.st_mtime, 'size': stat_info.st_size}
        except Exception:
            pass
    template['file_meta'] = file_meta

    return template


def build_library(workflows_dir, output_path, object_info=None):
    """构建完整的工作流资料库"""
    print(f"正在扫描目录: {workflows_dir}")
    workflow_files = get_workflow_files(workflows_dir)
    print(f"找到 {len(workflow_files)} 个工作流文件")
    
    library = {
        'metadata': {
            'source_dir': workflows_dir,
            'total_workflows': len(workflow_files),
            'build_time': datetime.now().isoformat()
        },
        'workflows': {},
        'statistics': {
            'node_types': defaultdict(int),
            'models': {
                'checkpoints': set(),
                'unet': set(),
                'vae': set(),
                'clip': set(),
                'lora': set(),
                'controlnet': set(),
                'upscale': set()
            },
            'categories': defaultdict(int),
            'model_families': defaultdict(int),
            'custom_nodes': set(),
            'common_parameters': defaultdict(list)
        },
        'templates': {},
        'component_library': {
            'loaders': {},
            'samplers': {},
            'encoders': {},
            'decoders': {},
            'processors': {},
            'outputs': {},
            'other': {}
        },
        'file_index': {}  # 文件索引：{相对路径: {mtime, size}}
    }
    
    for filepath in workflow_files:
        name = os.path.splitext(os.path.basename(filepath))[0]
        rel_path = os.path.relpath(filepath, workflows_dir)
        
        print(f"  分析: {rel_path}")
        
        workflow = load_workflow(filepath)
        if 'error' in workflow:
            print(f"    错误: {workflow['error']}")
            continue
        
        # 基础信息
        category = analyze_workflow_category(filepath, workflow)
        node_types = extract_node_types(workflow)
        models = extract_models(workflow)
        params = extract_parameters(workflow, object_info)
        connections = extract_connections(workflow)
        custom_nodes = extract_custom_nodes(workflow)
        template = build_workflow_template(workflow, name, object_info, filepath)
        # 识别大模型系列（不同系列工作流不能混用）
        model_family, model_modality, family_models = detect_workflow_model_family(workflow, object_info)

        # 更新 file_index（记录文件 mtime 和 size 用于增量更新）
        try:
            stat_info = os.stat(filepath)
            library['file_index'][rel_path] = {'mtime': stat_info.st_mtime, 'size': stat_info.st_size}
        except Exception:
            pass

        # 保存工作流详情（node_annotations/execution_flow/file_meta 提升到顶层，符合 spec 数据结构要求）
        node_annotations = template.pop('node_annotations', {})
        execution_flow = template.pop('execution_flow', {})
        file_meta = template.pop('file_meta', {'mtime': None, 'size': None})

        library['workflows'][name] = {
            'path': rel_path,
            'category': category,
            'model_family': model_family,
            'model_modality': model_modality,
            'family_models': [{'family': f, 'modality': m, 'name': n, 'role': r} for f, m, n, r in family_models],
            'node_count': len(workflow.get('nodes', [])),
            'link_count': len(workflow.get('links', [])),
            'node_types': node_types,
            'models': models,
            'parameters': params,
            'connections': connections,
            'custom_nodes': custom_nodes,
            'node_annotations': node_annotations,
            'execution_flow': execution_flow,
            'file_meta': file_meta,
            'template': template
        }
        
        # 更新统计
        library['statistics']['categories'][category] += 1
        library['statistics']['model_families'][model_family] += 1
        
        for nt, info in node_types.items():
            library['statistics']['node_types'][nt] += info['count']
        
        for model_type, model_list in models.items():
            if model_type != 'other':
                library['statistics']['models'][model_type].update(model_list)
        
        for cn in custom_nodes:
            library['statistics']['custom_nodes'].add(cn)
        
        # 收集通用参数
        for param_key, param_info in template['configurable'].items():
            library['statistics']['common_parameters'][param_key].append({
                'workflow': name,
                'default_value': param_info['default_value']
            })
        
        # 保存模板
        library['templates'][name] = template
        
        # 组件库分类
        for node in workflow.get('nodes', []):
            node_type = node.get('type', '')
            category_map = {
                'loaders': ['Loader', 'Load'],
                'samplers': ['Sampler'],
                'encoders': ['Encode', 'Text'],
                'decoders': ['Decode'],
                'processors': ['Apply', 'Combine', 'Average', 'Concat'],
                'outputs': ['Save', 'Preview', 'Show']
            }
            
            node_category = 'other'
            for cat, keywords in category_map.items():
                if any(kw in node_type for kw in keywords):
                    node_category = cat
                    break
            
            if node_type not in library['component_library'][node_category]:
                library['component_library'][node_category][node_type] = {
                    'count': 0,
                    'workflows': [],
                    'inputs': [],
                    'outputs': []
                }
            
            library['component_library'][node_category][node_type]['count'] += 1
            if name not in library['component_library'][node_category][node_type]['workflows']:
                library['component_library'][node_category][node_type]['workflows'].append(name)
    
    # 转换set为list以便JSON序列化
    for key in library['statistics']['models']:
        library['statistics']['models'][key] = list(library['statistics']['models'][key])
    library['statistics']['custom_nodes'] = list(library['statistics']['custom_nodes'])
    
    # 保存资料库
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(library, f, indent=2, ensure_ascii=False)
    
    print(f"\n资料库已生成: {output_path}")
    print(f"  工作流总数: {library['metadata']['total_workflows']}")
    print(f"  节点类型数: {len(library['statistics']['node_types'])}")
    print(f"  自定义节点数: {len(library['statistics']['custom_nodes'])}")
    print(f"  类别分布: {dict(library['statistics']['categories'])}")
    print(f"  大模型系列分布: {dict(library['statistics']['model_families'])}")
    
    return library


def compute_file_changes(source_dir, existing_file_index):
    """计算文件变更集。
    扫描源目录下所有 .json 工作流文件（复用 get_workflow_files），
    与 existing_file_index 比对（键为相对 source_dir 的相对路径，值为 {mtime, size}）。
    返回：{"added": [abs_path,...], "modified": [abs_path,...], "deleted": [rel_path,...]}
    - 新增：源目录存在但 file_index 中没有
    - 修改：mtime 或 size 变化
    - 删除：file_index 中有但源目录中没有
    """
    added = []
    modified = []
    deleted = []

    # 扫描源目录下所有工作流文件
    current_files = get_workflow_files(source_dir)
    current_rel_paths = {}  # rel_path -> abs_path
    for abs_path in current_files:
        rel_path = os.path.relpath(abs_path, source_dir)
        current_rel_paths[rel_path] = abs_path

    # 比对新增和修改
    for rel_path, abs_path in current_rel_paths.items():
        if rel_path not in existing_file_index:
            # 新增：源目录存在但 file_index 中没有
            added.append(abs_path)
        else:
            # 检查是否修改：mtime 或 size 变化
            try:
                stat_info = os.stat(abs_path)
                existing = existing_file_index[rel_path]
                if (stat_info.st_mtime != existing.get('mtime') or
                        stat_info.st_size != existing.get('size')):
                    modified.append(abs_path)
            except Exception:
                # 无法读取文件信息时视为修改
                modified.append(abs_path)

    # 检测删除：file_index 中有但源目录中没有
    for rel_path in existing_file_index:
        if rel_path not in current_rel_paths:
            deleted.append(rel_path)

    return {'added': added, 'modified': modified, 'deleted': deleted}


def update_library(source_dir, library_path, object_info):
    """增量更新工作流资料库。
    - 加载现有 library（若不存在则视为空 library，相当于全量构建）
    - 调用 compute_file_changes 计算变更集
    - 仅对 added/modified 文件调用 build_workflow_template
    - 从 library["workflows"] 中删除 deleted 文件对应的条目（通过 path 反查工作流名）
    - 更新 library["file_index"] 和 library["statistics"]
    - 输出变更摘要：新增 N 个、修改 N 个、删除 N 个
    """
    # 加载现有 library（若不存在则视为空 library）
    library = None
    if os.path.isfile(library_path):
        try:
            with open(library_path, 'r', encoding='utf-8') as f:
                library = json.load(f)
        except Exception:
            library = None

    if library is None:
        # 视为空 library，相当于全量构建
        library = {
            'metadata': {
                'source_dir': source_dir,
                'total_workflows': 0,
                'build_time': datetime.now().isoformat()
            },
            'workflows': {},
            'statistics': {
                'node_types': defaultdict(int),
                'models': {
                    'checkpoints': set(), 'unet': set(), 'vae': set(),
                    'clip': set(), 'lora': set(), 'controlnet': set(), 'upscale': set()
                },
                'categories': defaultdict(int),
                'model_families': defaultdict(int),
                'custom_nodes': set(),
                'common_parameters': defaultdict(list)
            },
            'templates': {},
            'component_library': {
                'loaders': {}, 'samplers': {}, 'encoders': {},
                'decoders': {}, 'processors': {}, 'outputs': {}, 'other': {}
            },
            'file_index': {}
        }

    # 确保 file_index 存在（兼容旧版资料库）
    if 'file_index' not in library:
        library['file_index'] = {}

    # 计算变更集
    changes = compute_file_changes(source_dir, library['file_index'])
    added_files = changes['added']
    modified_files = changes['modified']
    deleted_rel_paths = changes['deleted']

    print(f"变更集：新增 {len(added_files)} 个、修改 {len(modified_files)} 个、删除 {len(deleted_rel_paths)} 个")

    # 处理删除的文件：通过 path 反查工作流名并移除
    for rel_path in deleted_rel_paths:
        workflow_name_to_remove = None
        for wf_name, wf_info in library['workflows'].items():
            if wf_info.get('path') == rel_path:
                workflow_name_to_remove = wf_name
                break
        if workflow_name_to_remove:
            del library['workflows'][workflow_name_to_remove]
            if workflow_name_to_remove in library['templates']:
                del library['templates'][workflow_name_to_remove]
        # 从 file_index 中删除
        if rel_path in library['file_index']:
            del library['file_index'][rel_path]

    # 处理新增和修改的文件：调用 build_workflow_template（与 build_library 保持一致）
    for abs_path in added_files + modified_files:
        name = os.path.splitext(os.path.basename(abs_path))[0]
        rel_path = os.path.relpath(abs_path, source_dir)

        print(f"  分析: {rel_path}")

        workflow = load_workflow(abs_path)
        if 'error' in workflow:
            print(f"    错误: {workflow['error']}")
            continue

        # 基础信息（与 build_library 中的调用方式保持一致）
        category = analyze_workflow_category(abs_path, workflow)
        node_types = extract_node_types(workflow)
        models = extract_models(workflow)
        params = extract_parameters(workflow, object_info)
        connections = extract_connections(workflow)
        custom_nodes = extract_custom_nodes(workflow)
        template = build_workflow_template(workflow, name, object_info, abs_path)
        model_family, model_modality, family_models = detect_workflow_model_family(workflow, object_info)

        # 保存工作流详情（node_annotations/execution_flow/file_meta 提升到顶层，符合 spec 数据结构要求）
        node_annotations = template.pop('node_annotations', {})
        execution_flow = template.pop('execution_flow', {})
        file_meta = template.pop('file_meta', {'mtime': None, 'size': None})

        library['workflows'][name] = {
            'path': rel_path,
            'category': category,
            'model_family': model_family,
            'model_modality': model_modality,
            'family_models': [{'family': f, 'modality': m, 'name': n, 'role': r} for f, m, n, r in family_models],
            'node_count': len(workflow.get('nodes', [])),
            'link_count': len(workflow.get('links', [])),
            'node_types': node_types,
            'models': models,
            'parameters': params,
            'connections': connections,
            'custom_nodes': custom_nodes,
            'node_annotations': node_annotations,
            'execution_flow': execution_flow,
            'file_meta': file_meta,
            'template': template
        }

        # 更新 file_index
        try:
            stat_info = os.stat(abs_path)
            library['file_index'][rel_path] = {'mtime': stat_info.st_mtime, 'size': stat_info.st_size}
        except Exception:
            pass

        # 保存模板
        library['templates'][name] = template

    # 重建 statistics：聚合统计需要重新计算所有工作流
    library['statistics'] = {
        'node_types': defaultdict(int),
        'models': {
            'checkpoints': set(), 'unet': set(), 'vae': set(),
            'clip': set(), 'lora': set(), 'controlnet': set(), 'upscale': set()
        },
        'categories': defaultdict(int),
        'model_families': defaultdict(int),
        'custom_nodes': set(),
        'common_parameters': defaultdict(list)
    }

    # 遍历所有工作流重新聚合统计
    for name, wf_info in library['workflows'].items():
        category = wf_info.get('category', '其他')
        model_family = wf_info.get('model_family', 'unknown')
        node_types = wf_info.get('node_types', {})
        models = wf_info.get('models', {})
        custom_nodes = wf_info.get('custom_nodes', [])
        template = wf_info.get('template', {})

        library['statistics']['categories'][category] += 1
        library['statistics']['model_families'][model_family] += 1

        for nt, info in node_types.items():
            library['statistics']['node_types'][nt] += info.get('count', 0)

        for model_type, model_list in models.items():
            if model_type != 'other':
                library['statistics']['models'][model_type].update(model_list)

        for cn in custom_nodes:
            library['statistics']['custom_nodes'].add(cn)

        # 收集通用参数
        for param_key, param_info in template.get('configurable', {}).items():
            library['statistics']['common_parameters'][param_key].append({
                'workflow': name,
                'default_value': param_info.get('default_value')
            })

    # 转换 set 为 list 以便 JSON 序列化
    for key in library['statistics']['models']:
        library['statistics']['models'][key] = list(library['statistics']['models'][key])
    library['statistics']['custom_nodes'] = list(library['statistics']['custom_nodes'])

    # 更新 metadata
    library['metadata']['total_workflows'] = len(library['workflows'])
    library['metadata']['build_time'] = datetime.now().isoformat()

    # 保存资料库
    with open(library_path, 'w', encoding='utf-8') as f:
        json.dump(library, f, indent=2, ensure_ascii=False)

    print(f"\n资料库已更新: {library_path}")
    print(f"  新增 {len(added_files)} 个、修改 {len(modified_files)} 个、删除 {len(deleted_rel_paths)} 个")
    print(f"  工作流总数: {library['metadata']['total_workflows']}")

    return library


def main():
    ap = argparse.ArgumentParser(description="构建工作流生成资料库")
    default_workflows = os.path.join(
        os.path.expanduser(os.environ.get("COMFYUI_PATH", "")),
        "user", "default", "workflows"
    )
    ap.add_argument("--input", default=default_workflows,
                    help="工作流目录路径 (默认从 COMFYUI_PATH 环境变量推导)")
    ap.add_argument("--output", default=".trae/skills/comfyui-controller/assets/workflow_library.json",
                    help="资料库输出路径")
    ap.add_argument("--host", default="127.0.0.1", help="ComfyUI 服务器地址（用于获取 object_info）")
    ap.add_argument("--port", default="3198", help="ComfyUI 服务器端口")  # comfyui-cli项目标准端口
    ap.add_argument("--object-info", help="object_info 文件路径（优先于服务器）")
    ap.add_argument("--update", action="store_true", help="增量更新现有资料库（而非全量重建）")
    args = ap.parse_args()

    # 加载 object_info 用于 widget 映射
    object_info = load_object_info(args.host, args.port, args.object_info)
    if object_info:
        print(f"已加载 object_info: {len(object_info)} 个节点类型")
    else:
        print("警告：无法加载 object_info，widget 参数映射将不可用")

    # 根据 --update 参数选择增量更新或全量重建
    if args.update:
        library = update_library(args.input, args.output, object_info)
    else:
        library = build_library(args.input, args.output, object_info)
    
    # 输出简要统计
    print("\n" + "="*60)
    print("工作流生成资料库统计")
    print("="*60)
    
    print("\n【类别分布】")
    for cat, count in sorted(library['statistics']['categories'].items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}个")

    print("\n【大模型系列分布】（不同系列工作流不能混用）")
    for family, count in sorted(library['statistics']['model_families'].items(), key=lambda x: -x[1]):
        print(f"  {family}: {count}个")
    
    print("\n【最常用节点类型】(Top 10)")
    sorted_nodes = sorted(library['statistics']['node_types'].items(), key=lambda x: -x[1])
    for node_type, count in sorted_nodes[:10]:
        print(f"  {node_type}: {count}次")
    
    print("\n【使用的模型】")
    for model_type, models in library['statistics']['models'].items():
        if models:
            print(f"  {model_type}: {len(models)}个")
            for model in models[:5]:
                print(f"    - {model}")
            if len(models) > 5:
                print(f"    ... 等共{len(models)}个")
    
    print("\n【自定义节点】")
    for cn in sorted(library['statistics']['custom_nodes'])[:20]:
        print(f"  - {cn}")
    if len(library['statistics']['custom_nodes']) > 20:
        print(f"  ... 等共{len(library['statistics']['custom_nodes'])}个")


if __name__ == "__main__":
    main()
