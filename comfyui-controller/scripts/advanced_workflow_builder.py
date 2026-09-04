#!/usr/bin/env python3
"""
高级工作流智能组装引擎
- 基于用户需求从零组装工作流
- 支持复杂结构：多采样器串联、ControlNet、LoRA叠加、IPAdapter、放大链等
- 自动拓扑排序和连接布线
- 智能参数填充和模型选择
- 支持条件分支和并行处理
"""
import argparse
import json
import os
import random
import re
import sys
import urllib.request
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

# 引入 build_workflow_library 中的 detect_model_family（用于 model_family 一致性校验）
# 同时引入 _MODEL_FAMILY_RULES 用于根据 family 名查 modality（架构-modality 适配性校验）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from build_workflow_library import detect_model_family, _MODEL_FAMILY_RULES
except Exception:
    # 兜底：build_workflow_library 不可用时提供空实现，避免本模块导入失败
    def detect_model_family(model_name):
        return ("unknown", "unknown")
    _MODEL_FAMILY_RULES = []


# 中立节点类型集合：这些节点与 model_family 无关，可在不同 family 的工作流之间借用
# 所有 loader/sampler/encoder 节点不属于此集合，必须来自同一 model_family
_NEUTRAL_NODE_TYPES = {
    "SaveImage", "PreviewImage", "PreviewText", "Note", "PrimitiveNode",
    "Reroute", "MathExpression", "DisplayAny", "ShowAny", "InfoNode",
    "ReadNoteFromImage", "ETN_LoadImageBase64", "ImageComparer",
}


# 阶段3 标准负面提示词模板（lc.txt 六阶段架构）
# 涵盖内容安全、人体结构、画面质量、视频时序四类负面约束
STANDARD_NEGATIVE_PROMPT = (
    "nsfw, 扭曲, 多只手, 断肢, 坏手, 模糊, 重影, 抖动, 闪烁, 跳跃, 静止, "
    "文字, 水印, 画面撕裂, 变形, motion blur, distortion, bad anatomy, "
    "low quality, worst quality"
)


class NodeRegistry:
    """节点注册表 - 管理所有可用节点类型"""
    
    def __init__(self, object_info_path: str = None):
        self.nodes = {}
        self.categories = defaultdict(list)
        if object_info_path and os.path.exists(object_info_path):
            self.load_from_file(object_info_path)
    
    def load_from_file(self, path: str):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for node_type, info in data.items():
            self.nodes[node_type] = info
            category = info.get('category', 'unknown')
            self.categories[category].append(node_type)
    
    def get_node_info(self, node_type: str) -> dict:
        return self.nodes.get(node_type, {})
    
    def find_nodes_by_category(self, category: str) -> List[str]:
        return self.categories.get(category, [])
    
    def find_nodes_by_input_type(self, input_type: str) -> List[str]:
        """查找接受特定输入类型的节点"""
        results = []
        for node_type, info in self.nodes.items():
            inputs = info.get('input', {})
            for param_def in inputs.get('required', {}).values():
                if isinstance(param_def, list) and param_def[0] == input_type:
                    results.append(node_type)
                    break
            for param_def in inputs.get('optional', {}).values():
                if isinstance(param_def, list) and param_def[0] == input_type:
                    results.append(node_type)
                    break
        return results
    
    def find_nodes_by_output_type(self, output_type: str) -> List[str]:
        """查找输出特定类型的节点"""
        results = []
        for node_type, info in self.nodes.items():
            outputs = info.get('output', [])
            if output_type in outputs:
                results.append(node_type)
        return results


class WorkflowNode:
    """工作流节点"""
    
    def __init__(self, node_id: int, node_type: str, pos: List[int] = None):
        self.id = node_id
        self.type = node_type
        self.pos = pos or [0, 0]
        self.size = [200, 100]
        self.inputs = []
        self.outputs = []
        self.widgets_values = []
        self._meta = {}
        self.connections = {}  # input_name -> (source_node_id, source_slot)
        self.order = 0
    
    def to_web_format(self) -> dict:
        """转换为ComfyUI Web格式"""
        return {
            "id": self.id,
            "type": self.type,
            "pos": self.pos,
            "size": self.size,
            "flags": {},
            "order": self.order,
            "mode": 0,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "widgets_values": self.widgets_values,
            "_meta": self._meta
        }


class WorkflowGraph:
    """工作流图 - 管理节点和连接"""
    
    def __init__(self):
        self.nodes: Dict[int, WorkflowNode] = {}
        self.links: List[List] = []
        self.next_id = 1
        self.next_link_id = 1
        self.metadata = {}  # 图元数据：design_source/design_notes/target_model_family/adapter_check

    def add_node(self, node_type: str, pos: List[int] = None) -> WorkflowNode:
        """添加节点"""
        node = WorkflowNode(self.next_id, node_type, pos)
        self.nodes[self.next_id] = node
        self.next_id += 1
        return node
    
    def connect(self, source_id: int, source_slot: int,
                target_id: int, target_slot: int, link_type: str = ""):
        """连接两个节点。
        ComfyUI UI 格式的 links 数组为 6 元素：
        [link_id, source_id, source_slot, target_id, target_slot, type]
        type 字段为输出插槽的类型字符串（如 "LATENT", "CONDITIONING"）。
        """
        link_id = self.next_link_id
        self.links.append([link_id, source_id, source_slot, target_id, target_slot, link_type])
        self.next_link_id += 1

        # 记录连接关系
        target_node = self.nodes[target_id]
        if target_slot < len(target_node.inputs):
            input_name = target_node.inputs[target_slot].get('name', '')
            target_node.connections[input_name] = (source_id, source_slot)
            # 回填 inputs[].link，使输出符合标准 ComfyUI UI 格式
            # （转换器依赖该字段解析连线；缺失会导致全部连线连接丢失）
            target_node.inputs[target_slot]['link'] = link_id
    
    def to_web_format(self) -> dict:
        """转换为ComfyUI Web格式"""
        # 拓扑排序确定执行顺序
        sorted_ids = self._topological_sort()
        
        web_nodes = []
        for i, node_id in enumerate(sorted_ids):
            node = self.nodes[node_id]
            node.order = i
            web_nodes.append(node.to_web_format())
        
        return {
            "last_node_id": self.next_id - 1,
            "last_link_id": self.next_link_id - 1,
            "nodes": web_nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {},
            "metadata": self.metadata,
            "version": 0.4
        }
    
    def _topological_sort(self) -> List[int]:
        """拓扑排序"""
        in_degree = {nid: 0 for nid in self.nodes}
        adj = defaultdict(list)
        
        for link in self.links:
            # link 格式: [link_id, source_id, source_slot, target_id, target_slot, type]
            src = link[1]
            tgt = link[3]
            adj[src].append(tgt)
            in_degree[tgt] += 1
        
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        
        while queue:
            nid = queue.pop(0)
            result.append(nid)
            for neighbor in adj[nid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 添加未连接的节点
        for nid in self.nodes:
            if nid not in result:
                result.append(nid)
        
        return result


class RequirementParser:
    """需求解析器 - 将自然语言需求解析为结构化指令"""
    
    def __init__(self):
        self.keywords = {
            'task_types': {
                'txt2img': ['文生图', '文字生成图片', 'text to image', 'generate image'],
                'img2img': ['图生图', '图片生成图片', 'image to image'],
                'txt2vid': ['文生视频', '文字生成视频', 'text to video'],
                'img2vid': ['图生视频', '图片生成视频', 'image to video'],
                'upscale': ['放大', '超分', 'upscale', 'super resolution'],
                'inpaint': ['修复', '补全', 'inpaint', 'outpaint'],
                'controlnet': ['控制', 'controlnet', 'pose', 'depth'],
                'animation': ['动画', '动作迁移', 'animate', 'motion'],
                # 新增5类特殊视频任务
                'first_last_frame': ['首尾帧', '首帧尾帧', 'first last frame', 'first_last_frame', 'start end frame', '首尾帧生成视频'],
                'multi_image_video': ['多图片生成视频', '多图生成视频', 'multi image to video', '多图合成视频', '图片序列生成视频'],
                'long_video': ['长视频', '长时间视频', 'long video', '无限时长', '无限视频', '20秒', '30秒', '60秒', 'extended video'],
                'video_concat': ['视频拼接', '多视频拼接', '拼接视频', 'video concat', 'video stitch', 'video merge', '合并视频'],
                'multi_ref_video': ['多图片参考', '多参考图', 'multi reference', '多图参考生成视频', 'multi ref video'],
                # 新增3类特殊任务（数字人/LLM文本/TTS音频）
                'digital_human_lipsync': ['数字人', '口型同步', '口型', 'lipsync', 'lip sync', '说话', '说话头', 'talking head', '数字人唱歌', '数字人播报'],
                'llm_text_task': ['qwen编辑', 'qwen图像编辑', 'qwen局部重绘', 'qwen controlnet', '文本编辑图片', 'llm编辑', 'qwen-image', '文本任务'],
                'tts_audio': ['语音克隆', '声音克隆', 'tts', 'text to speech', '语音合成', 'index tts', '声音合成', '配音'],
            },
            'quality': {
                'high_quality': ['高质量', '高清', 'high quality', 'HD'],
                'fast': ['快速', 'fast', 'quick', 'speed'],
                'detailed': ['细节丰富', 'detailed', 'rich details'],
            },
            'styles': {
                'anime': ['动漫', '二次元', 'anime', 'manga'],
                'realistic': ['真实', '写实', 'realistic', 'photo'],
                '3d': ['3D', '三维', '立体', '3d render'],
                'painting': ['油画', '水彩', 'painting', 'artistic'],
            },
            'techniques': {
                'lora': ['lora', '风格', 'style'],
                'controlnet': ['controlnet', '控制', 'pose', 'openpose'],
                'ipadapter': ['ipadapter', '参考', 'reference'],
                'upscale': ['放大', 'upscale', '超分'],
                'face_restore': ['人脸修复', 'face restore', 'gfpgan'],
                'tile': ['tile', '分块', 'tiled'],
                'hires_fix': ['高清修复', 'hires', 'hires fix'],
                'detail_enhance': ['细节增强', 'detail enhance', '细节'],
                'multi_sampler': ['多采样', 'multi sampler', '串联'],
            }
        }
    
    def parse(self, requirement: str) -> dict:
        """解析需求"""
        req_lower = requirement.lower()
        result = {
            'original': requirement,
            'task_type': 'txt2img',
            'quality': 'standard',
            'style': None,
            'techniques': [],
            'parameters': {},
            'complexity': 'simple'
        }
        
        # 检测任务类型
        # 注意：特殊视频任务（首尾帧/多图/长视频/拼接/多参考）的关键词更具体，
        # 必须在通用任务（img2vid/txt2vid）之前检查，否则"多图片生成视频"会被
        # "图片生成视频"（img2vid 的关键词）先匹配到。
        # 实现：按 task_types 字典的声明顺序检查，特殊任务已声明在通用任务之后，
        # 所以这里反转检查顺序，让特殊任务优先匹配。
        ordered_task_types = list(self.keywords['task_types'].items())
        # 将特殊视频任务移到前面检查
        special_types = ['first_last_frame', 'multi_image_video', 'long_video',
                        'video_concat', 'multi_ref_video', 'animation']
        ordered_task_types.sort(key=lambda x: 0 if x[0] in special_types else 1)
        for task_type, keywords in ordered_task_types:
            if any(kw in req_lower for kw in keywords):
                result['task_type'] = task_type
                break
        
        # 检测质量要求
        for quality, keywords in self.keywords['quality'].items():
            if any(kw in req_lower for kw in keywords):
                result['quality'] = quality
                break
        
        # 检测风格
        for style, keywords in self.keywords['styles'].items():
            if any(kw in req_lower for kw in keywords):
                result['style'] = style
                break
        
        # 检测技术
        for technique, keywords in self.keywords['techniques'].items():
            if any(kw in req_lower for kw in keywords):
                result['techniques'].append(technique)
        
        # 检测复杂度
        technique_count = len(result['techniques'])
        if technique_count >= 3:
            result['complexity'] = 'complex'
        elif technique_count >= 1:
            result['complexity'] = 'medium'
        
        # 提取参数
        result['parameters'] = self._extract_parameters(requirement)
        
        return result
    
    def _extract_parameters(self, requirement: str) -> dict:
        """提取具体参数"""
        params = {}
        
        # 分辨率
        res_match = re.search(r'(\d+)\s*[xX×]\s*(\d+)', requirement)
        if res_match:
            params['width'] = int(res_match.group(1))
            params['height'] = int(res_match.group(2))
        
        # 步数
        steps_match = re.search(r'(\d+)\s*步', requirement)
        if steps_match:
            params['steps'] = int(steps_match.group(1))
        
        # CFG
        cfg_match = re.search(r'cfg\s*(\d+\.?\d*)', requirement.lower())
        if cfg_match:
            params['cfg'] = float(cfg_match.group(1))
        
        # 数量
        count_match = re.search(r'(\d+)\s*张', requirement)
        if count_match:
            params['batch_size'] = int(count_match.group(1))
        
        # 种子
        seed_match = re.search(r'种子\s*(\d+)', requirement)
        if seed_match:
            params['seed'] = int(seed_match.group(1))
        
        return params


class WorkflowAssembler:
    """工作流组装器 - 根据解析结果组装工作流"""

    def __init__(self, registry: NodeRegistry = None, library_path: str = None,
                 patterns: dict = None, target_model_family: str = None,
                 library: dict = None, object_info: dict = None):
        # registry 可选（便于无 object_info 文件时实例化）
        self.registry = registry if registry is not None else NodeRegistry()
        # 兼容旧 library_path：从文件加载工作流仓库
        self.library = {}
        if library_path and os.path.exists(library_path):
            try:
                with open(library_path, 'r', encoding='utf-8') as f:
                    self.library = json.load(f)
            except Exception:
                pass
        # 显式传入的 library 字典优先（用于 _pick_model）
        if library:
            self.library = library
        # 模式库（pattern_extractor 提取的结构）
        self.patterns = patterns if patterns is not None else {"patterns": [], "warnings": []}
        # 目标大模型系列（如 'Wan2.2'/'Flux'），强制节点-模型适配性
        self.target_model_family = target_model_family
        # object_info（节点 schema），优先用显式传入，其次从 registry.nodes 获取
        if object_info is not None:
            self.object_info = object_info
        else:
            self.object_info = self.registry.nodes if self.registry.nodes else {}

    def assemble(self, requirement) -> WorkflowGraph:
        """组装工作流 - 接入模式库，强制 model_family 一致性

        支持两种输入：
        - 字符串：内部调用 RequirementParser().parse 解析
        - 已解析的 dict：直接使用
        """
        # 1. 解析需求
        if isinstance(requirement, str):
            parsed = RequirementParser().parse(requirement)
            req_text = requirement
        else:
            parsed = requirement if isinstance(requirement, dict) else {}
            req_text = parsed.get('original', '')

        graph = WorkflowGraph()
        task_type = parsed.get('task_type', 'txt2img')

        # 2. 推断 target_model_family（若构造时未指定）
        target_family = self.target_model_family
        if not target_family:
            target_family = self._infer_model_family(req_text)
            self.target_model_family = target_family  # 缓存供 _build_*_base / _pick_model 使用

        # SubTask 14.1：架构-modality 适配性校验
        # 根据 target_model_family 的 modality 纠正 task_type，避免视频系列走图像架构（或反之）
        modality_note = None  # 记录纠正说明，末尾合并到 design_notes
        target_modality = self._get_modality_for_family(target_family)
        # 新增的5类特殊视频任务都是视频 modality，无需纠正
        video_task_types = ('txt2vid', 'img2vid', 'first_last_frame', 'multi_image_video',
                           'long_video', 'video_concat', 'multi_ref_video', 'animation',
                           'digital_human_lipsync')
        if target_modality == 'video' and task_type in ('txt2img', 'img2img'):
            corrected = {'txt2img': 'txt2vid', 'img2img': 'img2vid'}[task_type]
            modality_note = f"task_type 由 {task_type} 纠正为 {corrected}（modality 适配：{target_family} 为视频系列）"
            task_type = corrected
            parsed['task_type'] = task_type  # 回写，确保后续 _assemble_* 使用纠正后的值
        elif target_modality == 'image' and task_type in video_task_types:
            # 图像系列不能做视频任务，纠正为 img2img
            corrected = 'img2img'
            modality_note = f"task_type 由 {task_type} 纠正为 {corrected}（modality 适配：{target_family} 为图像系列，不支持视频任务）"
            task_type = corrected
            parsed['task_type'] = task_type

        # 3. task_category 映射（中文类别，与模式库对齐）
        task_category_map = {
            'txt2img': '文生图',
            'img2img': '图生图',
            'txt2vid': '文生视频',
            'img2vid': '图生视频',
            'upscale': '放大',
            # 新增5类特殊视频任务的中文类别
            'first_last_frame': '首尾帧生成视频',
            'multi_image_video': '多图片生成视频',
            'long_video': '长视频生成',
            'video_concat': '视频拼接',
            'multi_ref_video': '多图片参考生成视频',
            # 新增3类特殊任务的中文类别
            'digital_human_lipsync': '数字人口型同步',
            'llm_text_task': 'LLM文本编辑',
            'tts_audio': '语音合成',
        }
        task_category = task_category_map.get(task_type, '文生图')

        # 4. 从模式库查找匹配 (task_category, target_model_family)
        patterns_list = (self.patterns or {}).get('patterns', []) or []
        matched_pattern = None
        other_family_patterns = []
        for p in patterns_list:
            p_family = p.get('model_family')
            p_category = p.get('task_category')
            if p_category == task_category and p_family == target_family:
                matched_pattern = p
                break
            if p_family == target_family:
                other_family_patterns.append(p)

        # 5. 根据匹配情况分派
        if matched_pattern:
            # SubTask 11.3：匹配模式时按模式组装
            self._assemble_from_pattern(graph, parsed, matched_pattern, task_category, target_family)
            design_source = f"pattern:{task_category}:{target_family}"
            design_notes = "基于学习模式组装"
        elif other_family_patterns:
            # SubTask 11.4：无完全匹配时组合设计
            self._assemble_combined(graph, parsed, other_family_patterns, task_type, target_family)
            design_source = f"combined:{target_family}"
            other_tasks = ",".join(p.get('task_category', '?') for p in other_family_patterns[:2])
            design_notes = f"组合设计：基础来自{target_family}的{other_tasks}模式，技术组件来自通用中立节点"
        else:
            # SubTask 11.5：完全无匹配时回退到内置基础架构
            self._assemble_builtin(graph, parsed, task_type)
            design_source = "builtin"
            design_notes = f"未找到匹配的学习模式，使用内置{target_family or '通用'}基础架构"

        # 6. 验证 model_family 一致性（SubTask 11.7）
        issues = self._validate_model_family_consistency(graph, target_family)

        # 7. 设置 graph.metadata（SubTask 11.6）
        # 合并 modality 纠正说明到 design_notes
        if modality_note:
            design_notes = f"{modality_note}；{design_notes}"
        graph.metadata = {
            'design_source': design_source,
            'design_notes': design_notes,
            'target_model_family': target_family,
            'adapter_check': 'passed' if not issues else 'degraded',
        }
        if issues:
            graph.metadata['design_notes'] += f"（已自动替换 {len(issues)} 个不一致模型）"

        return graph

    def _infer_model_family(self, requirement_text: str) -> Optional[str]:
        """从需求字符串推断目标大模型系列（参考 workflow_generator.py 的 family_keywords）"""
        if not requirement_text:
            return None
        text_lower = requirement_text.lower()
        family_keywords = {
            'SD1.5': ['sd1.5', 'sd15', 'sd 1.5', 'stable diffusion 1.5'],
            'SDXL': ['sdxl', 'sd xl', 'stable diffusion xl'],
            'SD3': ['sd3', 'stable-diffusion-3'],
            'Flux': ['flux'],
            'Pony': ['pony'],
            'Illustrious': ['illustrious'],
            'Wan2.2': ['wan2.2', 'wan 2.2', 'wan2_2', 'wan2.1', 'wan2_1'],
            'HunyuanVideo': ['hunyuan', 'hunyuan video'],
            'LTX-Video': ['ltxv', 'ltx-video', 'ltx'],
            'CogVideoX': ['cogvideo', 'cogvideox'],
            'Mochi': ['mochi'],
            'Qwen-VL': ['qwen-vl', 'qwen_vl', 'qwenvl', 'qwen2vl'],
        }
        for fam, keywords in family_keywords.items():
            if any(kw in text_lower for kw in keywords):
                return fam
        return None

    def _get_modality_for_family(self, family_name: str) -> str:
        """根据大模型系列名查 modality（'image'/'video'/'text'/'unknown'）。

        遍历 build_workflow_library._MODEL_FAMILY_RULES 查找该 family 的 modality，
        用于架构-modality 适配性校验（避免视频系列走图像架构）。
        """
        if not family_name:
            return 'unknown'
        for fam, _keywords, modality in _MODEL_FAMILY_RULES:
            if fam == family_name:
                return modality
        return 'unknown'

    def _assemble_builtin(self, graph: WorkflowGraph, parsed: dict, task_type: str):
        """SubTask 11.5：回退到内置 _build_*_base，并叠加技术组件"""
        # 视频任务类型走 lc.txt 六阶段架构，通过 _dispatch_video_task 分派
        # 六阶段架构为严格节点序列，不叠加技术组件、不走模式覆盖
        _VIDEO_TASKS = {'img2vid', 'first_last_frame', 'multi_image_video',
                        'long_video', 'video_concat', 'multi_ref_video'}
        if task_type in _VIDEO_TASKS:
            self._dispatch_video_task(graph, parsed, task_type)
            return

        if task_type == 'txt2img':
            self._build_txt2img_base(graph, parsed)
        elif task_type == 'img2img':
            self._build_img2img_base(graph, parsed)
        elif task_type == 'txt2vid':
            self._build_txt2vid_base(graph, parsed)
        elif task_type == 'upscale':
            self._build_upscale_base(graph, parsed)
        elif task_type == 'digital_human_lipsync':
            self._build_digital_human_lipsync(graph, parsed)
        elif task_type == 'llm_text_task':
            self._build_llm_text_task(graph, parsed)
        elif task_type == 'tts_audio':
            self._build_tts_audio(graph, parsed)
        else:
            self._build_txt2img_base(graph, parsed)
        # 叠加技术组件
        self._apply_techniques(graph, parsed)

    def _assemble_from_pattern(self, graph: WorkflowGraph, parsed: dict,
                               pattern: dict, task_category: str, target_family: str):
        """SubTask 11.3：匹配模式时按模式组装

        策略：先用内置 _build_*_base 搭建合法布线骨架（保证图可执行），
        再用模式的 typical_model_combos / typical_parameters 覆盖模型与参数。
        对 combo 中每个模型再次调用 detect_model_family 验证一致性，
        不一致的用 _pick_model 替换。
        """
        task_type = parsed.get('task_type', 'txt2img')
        # 视频任务类型走 lc.txt 六阶段架构，通过 _dispatch_video_task 分派
        # 六阶段架构为严格节点序列，不走模式覆盖
        _VIDEO_TASKS = {'img2vid', 'first_last_frame', 'multi_image_video',
                        'long_video', 'video_concat', 'multi_ref_video'}
        if task_type in _VIDEO_TASKS:
            self._dispatch_video_task(graph, parsed, task_type)
            return

        # 1. 构建合法布线骨架
        if task_type == 'txt2img':
            self._build_txt2img_base(graph, parsed)
        elif task_type == 'img2img':
            self._build_img2img_base(graph, parsed)
        elif task_type == 'txt2vid':
            self._build_txt2vid_base(graph, parsed)
        elif task_type == 'upscale':
            self._build_upscale_base(graph, parsed)
        elif task_type == 'digital_human_lipsync':
            self._build_digital_human_lipsync(graph, parsed)
        elif task_type == 'llm_text_task':
            self._build_llm_text_task(graph, parsed)
        elif task_type == 'tts_audio':
            self._build_tts_audio(graph, parsed)
        else:
            self._build_txt2img_base(graph, parsed)

        # 2. 模型取自 typical_model_combos[0].combo（频率最高组合）
        combos = pattern.get('typical_model_combos', []) or []
        combo = {}
        if combos:
            combos_sorted = sorted(combos, key=lambda x: -x.get('frequency', 0))
            combo = combos_sorted[0].get('combo', {}) or {}

        # combo key -> (model_role, 目标节点类型)
        combo_role_map = {
            'checkpoints': ('checkpoint', 'CheckpointLoaderSimple'),
            'checkpoint': ('checkpoint', 'CheckpointLoaderSimple'),
            'unet': ('unet', 'UNETLoader'),
            'lora': ('lora', 'LoraLoader'),
            'controlnet': ('controlnet', 'ControlNetLoader'),
            'vae': ('vae', 'VAELoader'),
            'clip': ('clip', 'CLIPLoader'),
        }
        for role_key, model_name in combo.items():
            if not isinstance(model_name, str) or not model_name:
                continue
            role, node_type = combo_role_map.get(role_key, (role_key, None))
            # 防御模式库错误归类：再次验证 family 一致性
            fam, _ = detect_model_family(model_name)
            if fam != target_family:
                model_name = self._pick_model(role, target_family, self.library, self.object_info)
            # 应用到图中对应节点（首个匹配类型）
            target_node = self._find_node(graph, node_type) if node_type else None
            if target_node is not None and model_name:
                if target_node.widgets_values:
                    target_node.widgets_values[0] = model_name
                else:
                    target_node.widgets_values = [model_name]

        # 3. 参数取自 typical_parameters（每个参数取 Top 1 值），应用到 KSampler
        typical_params = pattern.get('typical_parameters', {}) or {}
        samplers = self._find_nodes(graph, 'KSampler')
        for param_name, steps in typical_params.items():
            if not steps or not isinstance(steps, list):
                continue
            try:
                top_step = sorted(steps, key=lambda x: -x.get('count', 0))[0]
            except Exception:
                continue
            value = top_step.get('value')
            if value is None:
                continue
            for sampler in samplers:
                # KSampler widgets: [seed, steps, cfg, sampler_name, scheduler, denoise]
                if param_name == 'steps' and len(sampler.widgets_values) > 1:
                    sampler.widgets_values[1] = value
                elif param_name == 'cfg' and len(sampler.widgets_values) > 2:
                    sampler.widgets_values[2] = value
                elif param_name == 'sampler_name' and len(sampler.widgets_values) > 3:
                    sampler.widgets_values[3] = value
                elif param_name == 'scheduler' and len(sampler.widgets_values) > 4:
                    sampler.widgets_values[4] = value
                elif param_name == 'denoise' and len(sampler.widgets_values) > 5:
                    sampler.widgets_values[5] = value

    def _assemble_combined(self, graph: WorkflowGraph, parsed: dict,
                           other_family_patterns: list, task_type: str, target_family: str):
        """SubTask 11.4：无完全匹配时组合设计

        基础架构使用目标 model_family 的内置 _build_*_base（保证 loader/sampler 同源），
        技术组件中的中立节点（属于 _NEUTRAL_NODE_TYPES）可从其他模式借用。
        """
        # 视频任务类型走 lc.txt 六阶段架构，通过 _dispatch_video_task 分派
        # 六阶段架构为严格节点序列，不借用中立节点
        _VIDEO_TASKS = {'img2vid', 'first_last_frame', 'multi_image_video',
                        'long_video', 'video_concat', 'multi_ref_video'}
        if task_type in _VIDEO_TASKS:
            self._dispatch_video_task(graph, parsed, task_type)
            return

        # 1. 基础架构：目标 model_family 的内置架构
        if task_type == 'txt2img':
            self._build_txt2img_base(graph, parsed)
        elif task_type == 'img2img':
            self._build_img2img_base(graph, parsed)
        elif task_type == 'txt2vid':
            self._build_txt2vid_base(graph, parsed)
        elif task_type == 'upscale':
            self._build_upscale_base(graph, parsed)
        else:
            self._build_txt2img_base(graph, parsed)

        # 2. 仅借用中立节点（SaveImage/PreviewImage/Note 等），不借用任何 loader/sampler/encoder
        existing_types = {n.type for n in graph.nodes.values()}
        for p in other_family_patterns:
            for node_type in (p.get('neutral_nodes') or []):
                if node_type in _NEUTRAL_NODE_TYPES and node_type not in existing_types:
                    borrowed = graph.add_node(node_type, [1200, 100 + len(graph.nodes) * 30])
                    borrowed.inputs = []
                    borrowed.outputs = []
                    borrowed.widgets_values = []
                    existing_types.add(node_type)

        # 3. 叠加技术组件（基于需求中的 techniques）
        self._apply_techniques(graph, parsed)

    def _apply_techniques(self, graph: WorkflowGraph, parsed: dict):
        """应用技术组件（lora/controlnet/upscale/hires_fix 等）"""
        techniques = parsed.get('techniques', []) or []
        complexity = parsed.get('complexity', 'simple')
        if 'lora' in techniques:
            self._add_lora(graph, parsed)
        if 'controlnet' in techniques:
            self._add_controlnet(graph, parsed)
        if 'ipadapter' in techniques:
            self._add_ipadapter(graph, parsed)
        if 'upscale' in techniques:
            self._add_upscale_chain(graph, parsed)
        if 'face_restore' in techniques:
            self._add_face_restore(graph, parsed)
        if 'hires_fix' in techniques:
            self._add_hires_fix(graph, parsed)
        if 'detail_enhance' in techniques:
            self._add_detail_enhance(graph, parsed)
        if 'multi_sampler' in techniques:
            self._add_multi_sampler(graph, parsed)
        if complexity == 'complex':
            self._add_complex_processing(graph, parsed)

    def _validate_model_family_consistency(self, graph: WorkflowGraph, target_model_family: str) -> list:
        """SubTask 11.7 + 14.5：遍历图中所有模型相关节点，验证 widget_values 中的模型名通过 detect_model_family 验证一致；
        同时校验架构族（modality）适配性：视频 modality 下禁止出现图像架构节点，反之亦然。

        返回 issues 列表；对不一致的节点尝试用 _pick_model 替换。
        """
        # 模型相关节点类型到 model_role 的映射
        model_node_roles = {
            "CheckpointLoaderSimple": "checkpoint",
            "UNETLoader": "unet",
            "UnetLoaderGGUF": "unet",
            "LoraLoader": "lora",
            "LoraLoaderModelOnly": "lora",
            "ControlNetLoader": "controlnet",
            "VAELoader": "vae",
            "CLIPLoader": "clip",
            "DoubleCLIPLoader": "clip",
        }
        # SubTask 14.5：架构族黑名单
        # video modality 下禁止出现的图像架构节点
        image_arch_nodes_blacklist = {"CheckpointLoaderSimple", "EmptyLatentImage"}
        # image modality 下禁止出现的视频架构节点（VAELoader 需谨慎：图像工作流中也可能出现，
        # 仅在无 CheckpointLoaderSimple 时才警告——此时说明走的是视频架构而非图像架构）
        video_arch_nodes_blacklist = {"UNETLoader", "CLIPLoader", "DoubleCLIPLoader", "VAELoader"}

        issues = []
        # SubTask 14.5：先做架构族（modality）校验
        target_modality = self._get_modality_for_family(target_model_family)
        if target_modality in ('video', 'image'):
            # 预计算图像工作流中是否存在 CheckpointLoaderSimple（用于 VAELoader 豁免判断）
            has_ckpt = any(n.type == "CheckpointLoaderSimple" for n in graph.nodes.values())
            for node in graph.nodes.values():
                if target_modality == 'video' and node.type in image_arch_nodes_blacklist:
                    issues.append({
                        "node_id": node.id,
                        "type": node.type,
                        "model": "",
                        "detected_family": "架构不匹配",
                        "reason": f"视频系列 {target_model_family} 不应出现图像架构节点 {node.type}",
                    })
                elif target_modality == 'image' and node.type in video_arch_nodes_blacklist:
                    # VAELoader 在图像工作流中也可能出现（与 CheckpointLoaderSimple 搭配时合法），
                    # 仅在无 CheckpointLoaderSimple 时才警告
                    if node.type == "VAELoader" and has_ckpt:
                        continue
                    issues.append({
                        "node_id": node.id,
                        "type": node.type,
                        "model": "",
                        "detected_family": "架构不匹配",
                        "reason": f"图像系列 {target_model_family} 不应出现视频架构节点 {node.type}",
                    })

        # 模型名一致性校验（SubTask 11.7 原有逻辑）
        for node in graph.nodes.values():
            if node.type in model_node_roles:
                if node.widgets_values:
                    model_name = node.widgets_values[0]
                    if isinstance(model_name, str) and model_name:
                        family, _ = detect_model_family(model_name)
                        if family != target_model_family and family != "unknown":
                            issues.append({
                                "node_id": node.id,
                                "type": node.type,
                                "model": model_name,
                                "detected_family": family,
                            })
                            # 尝试替换为同 family 的模型
                            replacement = self._pick_model(
                                model_node_roles[node.type], target_model_family,
                                self.library, self.object_info
                            )
                            if replacement:
                                node.widgets_values[0] = replacement
        return issues
    
    def _build_txt2img_base(self, graph: WorkflowGraph, requirement: dict):
        """构建文生图基础架构"""
        params = requirement.get('parameters', {})
        
        # 1. 模型加载器
        loader = graph.add_node('CheckpointLoaderSimple', [100, 100])
        loader.inputs = [
            {"name": "ckpt_name", "type": "MODEL", "link": None, "widget": {"name": "ckpt_name"}}
        ]
        loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0},
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 1},
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 2}
        ]
        loader.widgets_values = [self._pick_model('checkpoint', self.target_model_family, self.library, self.object_info)]
        
        # 2. 正面提示词编码
        pos_encode = graph.add_node('CLIPTextEncode', [100, 300])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        pos_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        pos_encode.widgets_values = [requirement.get('original', 'masterpiece, best quality')]
        
        # 3. 负面提示词编码
        neg_encode = graph.add_node('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        neg_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        neg_encode.widgets_values = ["worst quality, low quality, bad anatomy"]
        
        # 4. 空Latent
        empty_latent = graph.add_node('EmptyLatentImage', [500, 100])
        empty_latent.inputs = [
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "batch_size", "type": "INT", "link": None, "widget": {"name": "batch_size"}}
        ]
        empty_latent.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        empty_latent.widgets_values = [
            params.get('width', 512),
            params.get('height', 512),
            params.get('batch_size', 1)
        ]
        
        # 5. 采样器
        sampler = graph.add_node('KSampler', [500, 300])
        sampler.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20),
            params.get('cfg', 8.0),
            "euler",
            "normal",
            1.0
        ]
        
        # 6. VAE解码
        vae_decode = graph.add_node('VAEDecode', [700, 300])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        
        # 7. 保存图像
        save = graph.add_node('SaveImage', [900, 300])
        save.inputs = [
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "images", "type": "IMAGE", "link": None}
        ]
        save.outputs = []
        save.widgets_values = ["ComfyUI_Output"]
        
        # 连接
        graph.connect(loader.id, 1, pos_encode.id, 1)  # CLIP -> pos clip
        graph.connect(loader.id, 1, neg_encode.id, 1)  # CLIP -> neg clip
        graph.connect(loader.id, 0, sampler.id, 0)     # MODEL -> sampler model
        graph.connect(pos_encode.id, 0, sampler.id, 6) # CONDITIONING -> positive
        graph.connect(neg_encode.id, 0, sampler.id, 7) # CONDITIONING -> negative
        graph.connect(empty_latent.id, 0, sampler.id, 8) # LATENT -> latent_image
        graph.connect(sampler.id, 0, vae_decode.id, 0) # LATENT -> samples
        graph.connect(loader.id, 2, vae_decode.id, 1)  # VAE -> vae
        graph.connect(vae_decode.id, 0, save.id, 1)    # IMAGE -> images
    
    def _build_img2img_base(self, graph: WorkflowGraph, requirement: dict):
        """构建图生图基础架构：LoadImage + CheckpointLoaderSimple + 双 CLIPTextEncode + VAEEncode + KSampler(denoise=0.5) + VAEDecode + SaveImage"""
        params = requirement.get('parameters', {})

        # 1. LoadImage（加载输入图像）
        load_image = graph.add_node('LoadImage', [100, 100])
        load_image.inputs = [
            {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
        ]
        load_image.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
        ]
        load_image.widgets_values = ["example.png"]

        # 2. CheckpointLoaderSimple（模型加载，使用 _pick_model）
        loader = graph.add_node('CheckpointLoaderSimple', [100, 300])
        loader.inputs = [
            {"name": "ckpt_name", "type": "MODEL", "link": None, "widget": {"name": "ckpt_name"}}
        ]
        loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0},
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 1},
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 2}
        ]
        loader.widgets_values = [self._pick_model('checkpoint', self.target_model_family, self.library, self.object_info)]

        # 3. 正面提示词编码
        pos_encode = graph.add_node('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        pos_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        pos_encode.widgets_values = [requirement.get('original', 'masterpiece, best quality')]

        # 4. 负面提示词编码
        neg_encode = graph.add_node('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        neg_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        neg_encode.widgets_values = ["worst quality, low quality, bad anatomy"]

        # 5. VAEEncode（将输入图像编码为 latent，作为图生图起点）
        vae_encode = graph.add_node('VAEEncode', [500, 100])
        vae_encode.inputs = [
            {"name": "pixels", "type": "IMAGE", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_encode.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]

        # 6. KSampler（denoise=0.5 适合图生图）
        sampler = graph.add_node('KSampler', [700, 200])
        sampler.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20),
            params.get('cfg', 8.0),
            "euler",
            "normal",
            0.5  # 图生图典型 denoise
        ]

        # 7. VAE 解码
        vae_decode = graph.add_node('VAEDecode', [900, 200])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]

        # 8. 保存图像
        save = graph.add_node('SaveImage', [1100, 200])
        save.inputs = [
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "images", "type": "IMAGE", "link": None}
        ]
        save.outputs = []
        save.widgets_values = ["ComfyUI_Output"]

        # 连接
        graph.connect(loader.id, 1, pos_encode.id, 1)        # CLIP -> pos clip
        graph.connect(loader.id, 1, neg_encode.id, 1)        # CLIP -> neg clip
        graph.connect(loader.id, 0, sampler.id, 0)           # MODEL -> sampler model
        graph.connect(pos_encode.id, 0, sampler.id, 6)       # CONDITIONING -> positive
        graph.connect(neg_encode.id, 0, sampler.id, 7)       # CONDITIONING -> negative
        graph.connect(load_image.id, 0, vae_encode.id, 0)    # IMAGE -> pixels
        graph.connect(loader.id, 2, vae_encode.id, 1)        # VAE -> vae_encode
        graph.connect(vae_encode.id, 0, sampler.id, 8)       # LATENT -> latent_image
        graph.connect(sampler.id, 0, vae_decode.id, 0)       # LATENT -> samples
        graph.connect(loader.id, 2, vae_decode.id, 1)        # VAE -> vae
        graph.connect(vae_decode.id, 0, save.id, 1)          # IMAGE -> images

    def _build_txt2vid_base(self, graph: WorkflowGraph, requirement: dict):
        """构建文生视频基础架构 - 按目标 model_family 分派不同视频架构

        不同 model_family 之间不混用 loader/sampler/输出节点：
        - Wan2.2：UNETLoader + CLIPLoader + VAELoader + EmptyHunyuanLatentVideo + KSampler + VAEDecode + SaveAnimatedWEBP
        - HunyuanVideo：UNETLoader + DoubleCLIPLoader + VAELoader + EmptyHunyuanLatentVideo + KSampler + VAEDecode + VHS_VideoCombine
        - LTX-Video/CogVideoX/Mochi/Qwen-VL：各自通用视频架构（UNETLoader + CLIPLoader + VAELoader + EmptyLatent + KSampler + VAEDecode + SaveAnimatedWEBP）
        - 默认（未知系列）：通用视频架构，并记录警告
        """
        family = self.target_model_family
        if family == 'Wan2.2':
            self._build_wan22_video(graph, requirement)
        elif family == 'HunyuanVideo':
            self._build_hunyuan_video(graph, requirement)
        elif family in ('LTX-Video', 'CogVideoX', 'Mochi', 'Qwen-VL'):
            self._build_generic_video(graph, requirement, family)
        else:
            # SubTask 14.4：未知视频系列使用通用视频输出节点并记录警告
            print(f"[警告] _build_txt2vid_base: 未知视频系列 {family!r}，回退到通用视频架构（SaveAnimatedWEBP）")
            self._build_generic_video(graph, requirement, family or 'unknown')

    def _build_img2vid(self, image_name, user_prompt, ratio="9:16", steps=8, seed=12345,
                       filename_prefix="img2vid", architecture_scheme="single",
                       num_frames=121, blocks_to_swap=20, attention_mode="sdpa",
                       base_precision="bf16", high_lora_strength=1.0,
                       low_lora_strength=1.0, split_step=None):
        """图生视频（V19验证成功架构，lc.txt 六阶段架构，动态架构选择）

        V19架构变更：
        - 阶段3: 双路径文本编码
          · CLIPTextEncode (legacy CLIP) → CONDITIONING → FaceDetailer.pos/neg
          · WanVideoTextEncode (T5) → text_embeds → WanVideoSampler.text_embeds
        - 阶段3.5: CLIPVisionEncode → WanVideoClipVisionEncode（输出 clip_embeds）
        - 阶段3.6（新增）: WanVideoImageToVideoEncode（vae+clip_embeds+start_image → image_embeds）
        - 阶段4: _build_core_generation 新签名（image_embeds, text_embeds, model_high, model_low）
        - 阶段5: _build_video_output 已升级为 WanVideoDecode

        组装流程:
        阶段1: _build_image_preprocessing → LoadImage/Image Resize/FaceDetailer/VAEEncode
        阶段2: _build_model_loading → V19 WanVideoModelLoader链 + T5 + VAE + CLIPVision + legacy CLIP
        阶段3: CLIPTextEncode (FaceDetailer) + WanVideoTextEncode (WanVideoSampler)
        阶段3.5: WanVideoClipVisionEncode → clip_embeds
        阶段3.6: WanVideoImageToVideoEncode → image_embeds
        阶段4: _build_core_generation → WanVideoSampler（方案A双串行/方案B单次）
        阶段5: _build_video_output → WanVideoDecode + VHS_VideoCombine
        阶段6: _build_post_processing → Upscale + RIFE + Deflicker + Video Combine

        Returns: 完整的UI格式工作流JSON (含 nodes, links, last_node_id, last_link_id)
        """
        graph = WorkflowGraph()
        graph.metadata = {"design_source": "V19 六阶段架构", "task_type": "img2vid"}

        width, height = self._ratio_to_dimensions(ratio)
        # 单次生成帧数（默认 121）：C5 验证超过模型训练长度（81 帧）时 RIFLEX 不防语义重复，
        # 241 帧单次生成会导致动作重复；长视频请使用分段生成（_build_long_video）

        # === 阶段1: 图像预处理 ===
        s1_nodes, s1_links, s1_out_id, s1_out_slot = self._build_image_preprocessing(
            image_name, width, height)
        id_map1 = self._merge_stage_into_graph(graph, s1_nodes, s1_links)
        s1_latent_global = id_map1[s1_out_id]

        # 查找阶段1中的 Image Resize 节点（供 WanVideoClipVisionEncode 和
        # WanVideoImageToVideoEncode 的 image 输入使用）
        image_resize_node = self._find_node(graph, 'Image Resize')
        start_image_global = image_resize_node.id if image_resize_node else s1_latent_global

        # === 阶段2: 模型加载（V19架构，动态架构选择） ===
        s2_nodes, s2_links, s2_ids = self._build_model_loading(
            "wan22", architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision,
            high_lora_strength=high_lora_strength, low_lora_strength=low_lora_strength)
        id_map2 = self._merge_stage_into_graph(graph, s2_nodes, s2_links)
        model_global = id_map2[s2_ids["model_id"]]            # 主模型（供 FaceDetailer 共用，方案A指向 HIGH）
        model_high_global = id_map2[s2_ids["model_high_id"]]  # 高噪声阶段模型
        model_low_global = id_map2[s2_ids["model_low_id"]]    # 低噪声阶段模型
        vae_global = id_map2[s2_ids["vae_id"]]                # WanVideoVAELoader
        clip_global = id_map2[s2_ids["clip_id"]]              # T5 (LoadWanVideoT5TextEncoder)
        clip_legacy_global = id_map2[s2_ids["clip_legacy_id"]]  # Legacy CLIP (CLIPLoader)
        clip_vision_global = id_map2[s2_ids["clip_vision_id"]]  # CLIPVisionLoader

        # === 阶段3: 提示词工程（双路径文本编码） ===
        structured_prompt = self._structure_prompt(user_prompt, ratio)
        negative_prompt = STANDARD_NEGATIVE_PROMPT

        s3_nodes = []
        s3_links = []
        _id3 = [0]

        def _new3(node_type, pos):
            _id3[0] += 1
            node = WorkflowNode(_id3[0], node_type, pos)
            s3_nodes.append(node)
            return node

        # --- 3a: CLIPTextEncode（legacy，供 FaceDetailer 的 pos/neg CONDITIONING） ---
        pos_encode = _new3('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [structured_prompt]

        neg_encode = _new3('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = [negative_prompt]

        # 外部连接: clip_legacy_global → CLIPTextEncode.clip (slot 1)
        s3_links.append((clip_legacy_global, 0, pos_encode.id, 1, "CLIP"))
        s3_links.append((clip_legacy_global, 0, neg_encode.id, 1, "CLIP"))

        # --- 3b: WanVideoTextEncode（V19，供 WanVideoSampler 的 text_embeds） ---
        text_encode = _new3('WanVideoTextEncode', [300, 500])
        text_encode.inputs = [
            {"name": "positive_prompt", "type": "STRING", "link": None, "widget": {"name": "positive_prompt"}},
            {"name": "negative_prompt", "type": "STRING", "link": None, "widget": {"name": "negative_prompt"}},
            {"name": "t5", "type": "T5", "link": None},                       # slot 2 ← LoadWanVideoT5TextEncoder
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        text_encode.outputs = [
            {"name": "TEXT_EMBEDS", "type": "TEXT_EMBEDS", "links": [], "slot_index": 0}
        ]
        text_encode.widgets_values = [
            structured_prompt,   # positive_prompt
            negative_prompt,     # negative_prompt
            True,                # force_offload
        ]
        # 外部连接: clip_global(T5) → WanVideoTextEncode.t5 (slot 2)
        s3_links.append((clip_global, 0, text_encode.id, 2, "T5"))

        pos_local = pos_encode.id
        neg_local = neg_encode.id
        text_encode_local = text_encode.id
        id_map3 = self._merge_stage_into_graph(graph, s3_nodes, s3_links)
        pos_global = id_map3[pos_local]
        neg_global = id_map3[neg_local]
        text_embeds_global = id_map3[text_encode_local]

        # === 连接阶段1的外部输入 ===
        # FaceDetailer: model(slot1) / clip_vision(slot2) / positive(slot3) / negative(slot4)
        # VAEEncode: vae(slot1)
        face_detailer = self._find_node(graph, 'FaceDetailer')
        vae_encode_node = self._find_node(graph, 'VAEEncode')
        if face_detailer:
            self._add_cross_stage_link(graph, model_global, 0, face_detailer.id, 1, "MODEL")
            self._add_cross_stage_link(graph, clip_vision_global, 0, face_detailer.id, 2, "CLIP_VISION")
            self._add_cross_stage_link(graph, pos_global, 0, face_detailer.id, 3, "CONDITIONING")
            self._add_cross_stage_link(graph, neg_global, 0, face_detailer.id, 4, "CONDITIONING")
        if vae_encode_node:
            self._add_cross_stage_link(graph, vae_global, 0, vae_encode_node.id, 1, "VAE")

        # === 阶段3.5: WanVideoClipVisionEncode（V19替换CLIPVisionEncode） ===
        s35_nodes = []
        s35_links = []
        _id35 = [0]

        def _new35(node_type, pos):
            _id35[0] += 1
            node = WorkflowNode(_id35[0], node_type, pos)
            s35_nodes.append(node)
            return node

        clip_vision_encode = _new35('WanVideoClipVisionEncode', [500, 500])
        clip_vision_encode.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},      # slot 0 ← CLIPVisionLoader
            {"name": "image_1", "type": "IMAGE", "link": None},                # slot 1 ← Image Resize
            {"name": "strength_1", "type": "FLOAT", "link": None, "widget": {"name": "strength_1"}},
            {"name": "strength_2", "type": "FLOAT", "link": None, "widget": {"name": "strength_2"}},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
            {"name": "combine_embeds", "type": "COMBO", "link": None, "widget": {"name": "combine_embeds"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        clip_vision_encode.outputs = [
            {"name": "CLIP_EMBEDS", "type": "CLIP_EMBEDS", "links": [], "slot_index": 0}
        ]
        clip_vision_encode.widgets_values = [
            1.0,       # strength_1
            1.0,       # strength_2
            "center",  # crop
            "average", # combine_embeds
            True,      # force_offload
        ]
        s35_links.append((clip_vision_global, 0, clip_vision_encode.id, 0, "CLIP_VISION"))
        s35_links.append((start_image_global, 0, clip_vision_encode.id, 1, "IMAGE"))

        clip_vision_local = clip_vision_encode.id
        id_map35 = self._merge_stage_into_graph(graph, s35_nodes, s35_links)
        clip_embeds_global = id_map35[clip_vision_local]

        # === 阶段3.6: WanVideoImageToVideoEncode（V19新增，生成 image_embeds） ===
        s36_nodes = []
        s36_links = []
        _id36 = [0]

        def _new36(node_type, pos):
            _id36[0] += 1
            node = WorkflowNode(_id36[0], node_type, pos)
            s36_nodes.append(node)
            return node

        i2v_encode = _new36('WanVideoImageToVideoEncode', [500, 700])
        i2v_encode.inputs = [
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "num_frames", "type": "INT", "link": None, "widget": {"name": "num_frames"}},
            {"name": "noise_aug_strength", "type": "FLOAT", "link": None, "widget": {"name": "noise_aug_strength"}},
            {"name": "start_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "start_latent_strength"}},
            {"name": "end_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "end_latent_strength"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
            {"name": "vae", "type": "VAE", "link": None},                      # slot 7 ← WanVideoVAELoader
            {"name": "clip_embeds", "type": "CLIP_EMBEDS", "link": None},      # slot 8 ← WanVideoClipVisionEncode
            {"name": "start_image", "type": "IMAGE", "link": None},            # slot 9 ← Image Resize
        ]
        i2v_encode.outputs = [
            {"name": "IMAGE_EMBEDS", "type": "IMAGE_EMBEDS", "links": [], "slot_index": 0}
        ]
        # V19验证参数: noise_aug_strength=0.1（亮度锚定），start/end_latent_strength=1.0
        i2v_encode.widgets_values = [
            width,                # width
            height,               # height
            num_frames,           # num_frames=241（10秒@24fps）
            0.1,                  # noise_aug_strength（V19值，锚定亮度）
            1.0,                  # start_latent_strength
            1.0,                  # end_latent_strength
            True,                 # force_offload
        ]
        # 外部连接: vae / clip_embeds / start_image
        s36_links.append((vae_global, 0, i2v_encode.id, 7, "VAE"))
        s36_links.append((clip_embeds_global, 0, i2v_encode.id, 8, "CLIP_EMBEDS"))
        s36_links.append((start_image_global, 0, i2v_encode.id, 9, "IMAGE"))

        i2v_local = i2v_encode.id
        id_map36 = self._merge_stage_into_graph(graph, s36_nodes, s36_links)
        image_embeds_global = id_map36[i2v_local]

        # === 阶段4: 核心生成（V19新签名） ===
        s4_nodes, s4_links, s4_out_id, s4_out_slot = self._build_core_generation(
            image_embeds_global, 0,    # WanVideoImageToVideoEncode 输出
            text_embeds_global, 0,     # WanVideoTextEncode 输出
            model_high_global, 0,
            model_low_global, 0,
            architecture_scheme=architecture_scheme,
            steps=steps, seed=seed, split_step=split_step)
        id_map4 = self._merge_stage_into_graph(graph, s4_nodes, s4_links)
        sampler_global = id_map4[s4_out_id]

        # === 阶段5: 初级合成（V19 WanVideoDecode） ===
        s5_nodes, s5_links, s5_out_id, s5_out_slot = self._build_video_output(
            sampler_global, s4_out_slot,
            vae_global, 0,
            filename_prefix)
        id_map5 = self._merge_stage_into_graph(graph, s5_nodes, s5_links)
        vae_decode_global = id_map5[s5_out_id]

        # === 阶段6: 后处理提升 ===
        s6_nodes, s6_links, _, _ = self._build_post_processing(
            vae_decode_global, s5_out_slot,
            filename_prefix)
        self._merge_stage_into_graph(graph, s6_nodes, s6_links)

        return graph.to_web_format()

    def _build_wan22_video(self, graph: WorkflowGraph, requirement: dict, with_loadimage: bool = False):
        """[已废弃] Wan2.2 专属视频架构（旧 KSampler 两阶段架构）。

        .. deprecated::
            本方法使用旧的两阶段 KSampler（denoise=1.0/0.3）+ ModelSamplingSD3 + CreateVideo + SaveVideo
            架构，不符合 lc.txt 六阶段架构要求。lc.txt 要求使用 WanVideo I2V Sampler（禁止 KSampler）
            + VHS_VideoCombine（禁止 CreateVideo+SaveVideo）+ 后处理链(Upscale/RIFE/Deflicker)。
            新代码应使用 _build_image_preprocessing + _build_model_loading + _structure_prompt +
            _build_core_generation + _build_video_output + _build_post_processing 组合。
            本方法保留方法体，Task 5 将重写。

        改进点（宁可多花时间也不产出低质量内容）：
        1. ModelSamplingSD3：Flow Matching 噪声调度偏移（shift=3.0），对视频运动质量关键
        2. 两阶段采样：第一阶段 denoise=1.0 生成大体结构，第二阶段 denoise=0.3 细化细节
        3. RIFE VFI 帧插值：将帧数翻倍，提升动画流畅度
        4. CreateVideo + SaveVideo：输出 MP4 格式（替代 webp），并保持首帧一致性

        with_loadimage=True 时构建图生视频变体（LoadImage + WanImageToVideo 嵌入图片条件）
        """
        import warnings
        warnings.warn(
            "_build_wan22_video 使用旧 KSampler 两阶段架构 + CreateVideo + SaveVideo，"
            "已被 lc.txt 六阶段架构取代，请改用 _build_core_generation / _build_video_output / "
            "_build_post_processing。Task 5 将重写本方法。",
            DeprecationWarning,
            stacklevel=2,
        )
        params = requirement.get('parameters', {})
        # 1. UNETLoader
        unet_loader = graph.add_node('UNETLoader', [100, 100])
        unet_loader.inputs = [
            {"name": "unet_name", "type": "COMBO", "link": None, "widget": {"name": "unet_name"}},
            {"name": "weight_dtype", "type": "COMBO", "link": None, "widget": {"name": "weight_dtype"}}
        ]
        unet_loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
        ]
        unet_loader.widgets_values = [
            self._pick_model('unet', 'Wan2.2', self.library, self.object_info),
            "fp8_e4m3fn"
        ]
        # 2. ModelSamplingSD3（改进1：噪声调度偏移，Wan2.2 作为 Flow Matching 模型必需）
        model_sampling = graph.add_node('ModelSamplingSD3', [100, 220])
        model_sampling.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "shift", "type": "FLOAT", "link": None, "widget": {"name": "shift"}}
        ]
        model_sampling.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
        ]
        model_sampling.widgets_values = [3.0]
        # 3. CLIPLoader
        clip_loader = graph.add_node('CLIPLoader', [100, 340])
        clip_loader.inputs = [
            {"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}},
            {"name": "type", "type": "COMBO", "link": None, "widget": {"name": "type"}}
        ]
        clip_loader.outputs = [
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 0}
        ]
        clip_loader.widgets_values = [
            self._pick_model('clip', 'Wan2.2', self.library, self.object_info),
            "wan"
        ]
        # 4. VAELoader
        vae_loader = graph.add_node('VAELoader', [100, 460])
        vae_loader.inputs = [
            {"name": "vae_name", "type": "COMBO", "link": None, "widget": {"name": "vae_name"}}
        ]
        vae_loader.outputs = [
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 0}
        ]
        vae_loader.widgets_values = [self._pick_model('vae', 'Wan2.2', self.library, self.object_info)]
        # 5. 双 CLIPTextEncode
        pos_encode = graph.add_node('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        pos_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        pos_encode.widgets_values = [requirement.get('original', 'masterpiece, best quality')]
        neg_encode = graph.add_node('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        neg_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        neg_encode.widgets_values = ["low quality, blurry"]
        # 6. latent 来源：with_loadimage=True 时用 WanImageToVideo（图生视频），否则用 EmptyHunyuanLatentVideo（文生视频）
        if with_loadimage:
            # 图生视频：LoadImage + CLIPVisionLoader + CLIPVisionEncode + WanImageToVideo
            load_image = graph.add_node('LoadImage', [400, 100])
            load_image.inputs = [
                {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
            ]
            load_image.outputs = [
                {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
                {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
            ]
            load_image.widgets_values = ["example.png"]
            # CLIPVisionLoader + CLIPVisionEncode（图生视频必需，编码图片条件）
            clip_vision_loader = graph.add_node('CLIPVisionLoader', [400, 220])
            clip_vision_loader.inputs = [
                {"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}}
            ]
            clip_vision_loader.outputs = [
                {"name": "CLIP_VISION", "type": "CLIP_VISION", "links": [], "slot_index": 0}
            ]
            clip_vision_loader.widgets_values = [self._pick_model('clip_vision', 'Wan2.2', self.library, self.object_info)]
            clip_vision_encode = graph.add_node('CLIPVisionEncode', [400, 340])
            clip_vision_encode.inputs = [
                {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
                {"name": "image", "type": "IMAGE", "link": None},
                {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}}
            ]
            clip_vision_encode.outputs = [
                {"name": "CLIP_VISION_OUTPUT", "type": "CLIP_VISION_OUTPUT", "links": [], "slot_index": 0}
            ]
            clip_vision_encode.widgets_values = ["center"]
            # WanImageToVideo（嵌入图片条件并生成 latent）
            latent = graph.add_node('WanImageToVideo', [550, 100])
            latent.inputs = [
                {"name": "positive", "type": "CONDITIONING", "link": None},
                {"name": "negative", "type": "CONDITIONING", "link": None},
                {"name": "vae", "type": "VAE", "link": None},
                {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
                {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
                {"name": "length", "type": "INT", "link": None, "widget": {"name": "length"}},
                {"name": "batch_size", "type": "INT", "link": None, "widget": {"name": "batch_size"}},
                {"name": "clip_vision_output", "type": "CLIP_VISION_OUTPUT", "link": None},
                {"name": "start_image", "type": "IMAGE", "link": None},
            ]
            latent.outputs = [
                {"name": "positive", "type": "CONDITIONING", "links": [], "slot_index": 0},
                {"name": "negative", "type": "CONDITIONING", "links": [], "slot_index": 1},
                {"name": "latent", "type": "LATENT", "links": [], "slot_index": 2},
            ]
            width = params.get('width', 768)
            height = params.get('height', 576)
            length = params.get('length', 41)
            latent.widgets_values = [width, height, length, 1]
        else:
            # 文生视频：EmptyHunyuanLatentVideo（Wan2.2 复用视频 latent）
            latent = graph.add_node('EmptyHunyuanLatentVideo', [500, 100])
            latent.inputs = [
                {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
                {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
                {"name": "length", "type": "INT", "link": None, "widget": {"name": "length"}},
                {"name": "batch_size", "type": "INT", "link": None, "widget": {"name": "batch_size"}}
            ]
            latent.outputs = [
                {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
            ]
            latent.widgets_values = [params.get('width', 832), params.get('height', 480), params.get('length', 49), 1]
        # 7. 第一阶段 KSampler（改进2：高噪音阶段，生成大体结构，denoise=1.0）
        sampler1 = graph.add_node('KSampler', [700, 100])
        sampler1.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler1.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        seed = params.get('seed', random.randint(0, 2**32))
        sampler1.widgets_values = [
            seed, params.get('steps', 20), params.get('cfg', 3.0),
            "euler", "simple", 1.0
        ]
        # 8. 第二阶段 KSampler（改进2：低噪音阶段，细化细节，denoise=0.3）
        sampler2 = graph.add_node('KSampler', [700, 350])
        sampler2.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler2.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler2.widgets_values = [
            seed, params.get('steps', 20), params.get('cfg', 3.0),
            "euler", "simple", 0.3
        ]
        # 9. VAEDecode
        vae_decode = graph.add_node('VAEDecode', [900, 200])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # 10. RIFE VFI 帧插值（改进3：帧数翻倍，提升动画流畅度）
        rife = graph.add_node('RIFE VFI', [1050, 200])
        rife.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "multiplier", "type": "INT", "link": None, "widget": {"name": "multiplier"}},
        ]
        rife.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        rife.widgets_values = [2]  # 帧数翻倍
        # 11. CreateVideo（改进4：IMAGE → VIDEO 桥接，输出 MP4）
        create_video = graph.add_node('CreateVideo', [1200, 200])
        create_video.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "fps", "type": "FLOAT", "link": None, "widget": {"name": "fps"}},
        ]
        create_video.outputs = [
            {"name": "VIDEO", "type": "VIDEO", "links": [], "slot_index": 0}
        ]
        fps = params.get('fps', 16)
        create_video.widgets_values = [fps]
        # 12. SaveVideo（改进4：保存为 MP4 格式）
        save = graph.add_node('SaveVideo', [1350, 200])
        save.inputs = [
            {"name": "video", "type": "VIDEO", "link": None},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "format", "type": "COMBO", "link": None, "widget": {"name": "format"}},
            {"name": "codec", "type": "COMBO", "link": None, "widget": {"name": "codec"}},
        ]
        save.outputs = []
        save.widgets_values = ["ComfyUI_Wan22", "mp4", "h264"]
        # === 连接 ===
        # 模型链路：UNETLoader → ModelSamplingSD3 → 两个 KSampler
        graph.connect(unet_loader.id, 0, model_sampling.id, 0)
        graph.connect(model_sampling.id, 0, sampler1.id, 0)
        graph.connect(model_sampling.id, 0, sampler2.id, 0)
        # CLIP 文本编码链路
        graph.connect(clip_loader.id, 0, pos_encode.id, 1)
        graph.connect(clip_loader.id, 0, neg_encode.id, 1)
        if with_loadimage:
            # 图生视频：WanImageToVideo 嵌入图片条件
            graph.connect(clip_vision_loader.id, 0, clip_vision_encode.id, 0)
            graph.connect(load_image.id, 0, clip_vision_encode.id, 1)
            graph.connect(pos_encode.id, 0, latent.id, 0)   # positive → WanImageToVideo.positive
            graph.connect(neg_encode.id, 0, latent.id, 1)   # negative → WanImageToVideo.negative
            graph.connect(vae_loader.id, 0, latent.id, 2)   # vae → WanImageToVideo.vae
            graph.connect(clip_vision_encode.id, 0, latent.id, 7)  # clip_vision_output
            graph.connect(load_image.id, 0, latent.id, 8)   # start_image
            # 第一阶段采样使用 WanImageToVideo 输出的 conditioning 和 latent
            graph.connect(latent.id, 0, sampler1.id, 6)  # WanImageToVideo.positive → KSampler1.positive
            graph.connect(latent.id, 1, sampler1.id, 7)  # WanImageToVideo.negative → KSampler1.negative
            graph.connect(latent.id, 2, sampler1.id, 8)  # WanImageToVideo.latent → KSampler1.latent_image
            # 第二阶段采样同样使用 WanImageToVideo 的 conditioning，但 latent 来自第一阶段
            graph.connect(latent.id, 0, sampler2.id, 6)  # positive
            graph.connect(latent.id, 1, sampler2.id, 7)  # negative
            graph.connect(sampler1.id, 0, sampler2.id, 8)  # 第一阶段 latent → 第二阶段 latent_image
        else:
            # 文生视频：直接使用 CLIPTextEncode 的 conditioning
            graph.connect(pos_encode.id, 0, sampler1.id, 6)
            graph.connect(neg_encode.id, 0, sampler1.id, 7)
            graph.connect(latent.id, 0, sampler1.id, 8)
            graph.connect(pos_encode.id, 0, sampler2.id, 6)
            graph.connect(neg_encode.id, 0, sampler2.id, 7)
            graph.connect(sampler1.id, 0, sampler2.id, 8)
        # VAE 解码 → 帧插值 → 视频保存
        graph.connect(sampler2.id, 0, vae_decode.id, 0)
        graph.connect(vae_loader.id, 0, vae_decode.id, 1)
        graph.connect(vae_decode.id, 0, rife.id, 0)
        graph.connect(rife.id, 0, create_video.id, 0)
        graph.connect(create_video.id, 0, save.id, 0)

    def _build_hunyuan_video(self, graph: WorkflowGraph, requirement: dict, with_loadimage: bool = False):
        """HunyuanVideo 专属架构：UNETLoader + DoubleCLIPLoader + VAELoader + EmptyHunyuanLatentVideo + KSampler + VAEDecode + VHS_VideoCombine。
        with_loadimage=True 时构建图生视频变体（增加 LoadImage+VAEEncode）"""
        params = requirement.get('parameters', {})
        # 1. UNETLoader
        unet_loader = graph.add_node('UNETLoader', [100, 100])
        unet_loader.inputs = [
            {"name": "unet_name", "type": "COMBO", "link": None, "widget": {"name": "unet_name"}},
            {"name": "weight_dtype", "type": "COMBO", "link": None, "widget": {"name": "weight_dtype"}}
        ]
        unet_loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
        ]
        unet_loader.widgets_values = [
            self._pick_model('unet', 'HunyuanVideo', self.library, self.object_info),
            "fp8_e4m3fn"
        ]
        # 2. DoubleCLIPLoader
        double_clip = graph.add_node('DoubleCLIPLoader', [100, 300])
        double_clip.inputs = [
            {"name": "clip_name1", "type": "COMBO", "link": None, "widget": {"name": "clip_name1"}},
            {"name": "clip_name2", "type": "COMBO", "link": None, "widget": {"name": "clip_name2"}},
            {"name": "type", "type": "COMBO", "link": None, "widget": {"name": "type"}}
        ]
        double_clip.outputs = [
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 0}
        ]
        double_clip.widgets_values = [
            self._pick_model('clip', 'HunyuanVideo', self.library, self.object_info),
            self._pick_model('clip', 'HunyuanVideo', self.library, self.object_info),
            "sdxl"
        ]
        # 3. VAELoader
        vae_loader = graph.add_node('VAELoader', [100, 500])
        vae_loader.inputs = [
            {"name": "vae_name", "type": "COMBO", "link": None, "widget": {"name": "vae_name"}}
        ]
        vae_loader.outputs = [
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 0}
        ]
        vae_loader.widgets_values = [self._pick_model('vae', 'HunyuanVideo', self.library, self.object_info)]
        # 4. 双 CLIPTextEncode
        pos_encode = graph.add_node('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        pos_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        pos_encode.widgets_values = [requirement.get('original', 'masterpiece, best quality')]
        neg_encode = graph.add_node('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        neg_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        neg_encode.widgets_values = ["low quality, blurry"]
        # 5. latent 来源：with_loadimage=True 时用 LoadImage+VAEEncode（图生视频），否则用 EmptyHunyuanLatentVideo（文生视频）
        if with_loadimage:
            # SubTask 14.3：图生视频变体 - LoadImage 加载输入图像，VAEEncode 编码为 latent 作为视频起始
            load_image = graph.add_node('LoadImage', [400, 100])
            load_image.inputs = [
                {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
            ]
            load_image.outputs = [
                {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
                {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
            ]
            load_image.widgets_values = ["example.png"]
            latent = graph.add_node('VAEEncode', [500, 100])
            latent.inputs = [
                {"name": "pixels", "type": "IMAGE", "link": None},
                {"name": "vae", "type": "VAE", "link": None}
            ]
            latent.outputs = [
                {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
            ]
        else:
            # 5. EmptyHunyuanLatentVideo
            latent = graph.add_node('EmptyHunyuanLatentVideo', [500, 100])
            latent.inputs = [
                {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
                {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
                {"name": "length", "type": "INT", "link": None, "widget": {"name": "length"}},
                {"name": "batch_size", "type": "INT", "link": None, "widget": {"name": "batch_size"}}
            ]
            latent.outputs = [
                {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
            ]
            latent.widgets_values = [params.get('width', 848), params.get('height', 480), params.get('length', 49), 1]
        # 6. KSampler
        sampler = graph.add_node('KSampler', [700, 200])
        sampler.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20), params.get('cfg', 6.0),
            "euler", "normal", 1.0
        ]
        # 7. VAEDecode
        vae_decode = graph.add_node('VAEDecode', [900, 200])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # 8. VHS_VideoCombine
        save = graph.add_node('VHS_VideoCombine', [1100, 200])
        save.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "frame_rate", "type": "FLOAT", "link": None, "widget": {"name": "frame_rate"}},
            {"name": "loop_count", "type": "INT", "link": None, "widget": {"name": "loop_count"}},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "format", "type": "COMBO", "link": None, "widget": {"name": "format"}},
            {"name": "pix_fmt", "type": "STRING", "link": None, "widget": {"name": "pix_fmt"}},
            {"name": "save_metadata", "type": "BOOLEAN", "link": None, "widget": {"name": "save_metadata"}}
        ]
        save.outputs = []
        save.widgets_values = [16, 0, "HunyuanVideo", "video/h264-mp4", "yuv420p", True]
        # 连接
        graph.connect(double_clip.id, 0, pos_encode.id, 1)
        graph.connect(double_clip.id, 0, neg_encode.id, 1)
        graph.connect(unet_loader.id, 0, sampler.id, 0)
        graph.connect(pos_encode.id, 0, sampler.id, 6)
        graph.connect(neg_encode.id, 0, sampler.id, 7)
        graph.connect(latent.id, 0, sampler.id, 8)
        # with_loadimage=True 时连接 LoadImage -> VAEEncode.pixels 和 VAELoader -> VAEEncode.vae
        if with_loadimage:
            graph.connect(load_image.id, 0, latent.id, 0)   # IMAGE -> pixels
            graph.connect(vae_loader.id, 0, latent.id, 1)   # VAE -> vae
        graph.connect(sampler.id, 0, vae_decode.id, 0)
        graph.connect(vae_loader.id, 0, vae_decode.id, 1)
        graph.connect(vae_decode.id, 0, save.id, 0)

    def _build_generic_video(self, graph: WorkflowGraph, requirement: dict, family: str, with_loadimage: bool = False):
        """通用视频架构（LTX-Video/CogVideoX/Mochi/Qwen-VL/默认）：UNETLoader + CLIPLoader + VAELoader + EmptyLatent + KSampler + VAEDecode + SaveAnimatedWEBP。
        with_loadimage=True 时构建图生视频变体（增加 LoadImage+VAEEncode）"""
        params = requirement.get('parameters', {})
        # 1. UNETLoader
        unet_loader = graph.add_node('UNETLoader', [100, 100])
        unet_loader.inputs = [
            {"name": "unet_name", "type": "COMBO", "link": None, "widget": {"name": "unet_name"}},
            {"name": "weight_dtype", "type": "COMBO", "link": None, "widget": {"name": "weight_dtype"}}
        ]
        unet_loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
        ]
        unet_loader.widgets_values = [
            self._pick_model('unet', family, self.library, self.object_info),
            "fp8_e4m3fn"
        ]
        # 2. CLIPLoader
        clip_loader = graph.add_node('CLIPLoader', [100, 300])
        clip_loader.inputs = [
            {"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}},
            {"name": "type", "type": "COMBO", "link": None, "widget": {"name": "type"}}
        ]
        clip_loader.outputs = [
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 0}
        ]
        clip_loader.widgets_values = [
            self._pick_model('clip', family, self.library, self.object_info),
            "sdxl"
        ]
        # 3. VAELoader
        vae_loader = graph.add_node('VAELoader', [100, 500])
        vae_loader.inputs = [
            {"name": "vae_name", "type": "COMBO", "link": None, "widget": {"name": "vae_name"}}
        ]
        vae_loader.outputs = [
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 0}
        ]
        vae_loader.widgets_values = [self._pick_model('vae', family, self.library, self.object_info)]
        # 4. 双 CLIPTextEncode
        pos_encode = graph.add_node('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        pos_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        pos_encode.widgets_values = [requirement.get('original', 'masterpiece, best quality')]
        neg_encode = graph.add_node('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        neg_encode.outputs = [
            {"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}
        ]
        neg_encode.widgets_values = ["low quality, blurry"]
        # 5. latent 来源：with_loadimage=True 时用 LoadImage+VAEEncode（图生视频），否则用 EmptyLatent（文生视频）
        if with_loadimage:
            # SubTask 14.3：图生视频变体 - LoadImage 加载输入图像，VAEEncode 编码为 latent 作为视频起始
            load_image = graph.add_node('LoadImage', [400, 100])
            load_image.inputs = [
                {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
            ]
            load_image.outputs = [
                {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
                {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
            ]
            load_image.widgets_values = ["example.png"]
            latent = graph.add_node('VAEEncode', [500, 100])
            latent.inputs = [
                {"name": "pixels", "type": "IMAGE", "link": None},
                {"name": "vae", "type": "VAE", "link": None}
            ]
            latent.outputs = [
                {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
            ]
        else:
            # 5. EmptyLatent（通用视频 latent 占位）
            latent = graph.add_node('EmptyLatent', [500, 100])
            latent.inputs = [
                {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
                {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
                {"name": "batch_size", "type": "INT", "link": None, "widget": {"name": "batch_size"}}
            ]
            latent.outputs = [
                {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
            ]
            latent.widgets_values = [params.get('width', 512), params.get('height', 512), 1]
        # 6. KSampler
        sampler = graph.add_node('KSampler', [700, 200])
        sampler.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20), params.get('cfg', 6.0),
            "euler", "normal", 1.0
        ]
        # 7. VAEDecode
        vae_decode = graph.add_node('VAEDecode', [900, 200])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # 8. SaveAnimatedWEBP
        save = graph.add_node('SaveAnimatedWEBP', [1100, 200])
        save.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "fps", "type": "FLOAT", "link": None, "widget": {"name": "fps"}},
            {"name": "lossless", "type": "BOOLEAN", "link": None, "widget": {"name": "lossless"}},
            {"name": "quality", "type": "INT", "link": None, "widget": {"name": "quality"}},
            {"name": "method", "type": "COMBO", "link": None, "widget": {"name": "method"}}
        ]
        save.outputs = []
        save.widgets_values = [f"ComfyUI_{family}", 16, False, 80, "default"]
        # 连接
        graph.connect(clip_loader.id, 0, pos_encode.id, 1)
        graph.connect(clip_loader.id, 0, neg_encode.id, 1)
        graph.connect(unet_loader.id, 0, sampler.id, 0)
        graph.connect(pos_encode.id, 0, sampler.id, 6)
        graph.connect(neg_encode.id, 0, sampler.id, 7)
        graph.connect(latent.id, 0, sampler.id, 8)
        # with_loadimage=True 时连接 LoadImage -> VAEEncode.pixels 和 VAELoader -> VAEEncode.vae
        if with_loadimage:
            graph.connect(load_image.id, 0, latent.id, 0)   # IMAGE -> pixels
            graph.connect(vae_loader.id, 0, latent.id, 1)   # VAE -> vae
        graph.connect(sampler.id, 0, vae_decode.id, 0)
        graph.connect(vae_loader.id, 0, vae_decode.id, 1)
        graph.connect(vae_decode.id, 0, save.id, 0)

    def _build_upscale_base(self, graph: WorkflowGraph, requirement: dict):
        """构建放大基础架构：LoadImage + CheckpointLoaderSimple + UpscaleModelLoader + ImageUpscaleWithModel + VAEEncode + KSampler(denoise=0.2) + VAEDecode + SaveImage"""
        params = requirement.get('parameters', {})
        # 1. LoadImage（输入图像）
        load_image = graph.add_node('LoadImage', [100, 100])
        load_image.inputs = [
            {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
        ]
        load_image.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
        ]
        load_image.widgets_values = ["example.png"]
        # 2. CheckpointLoaderSimple（模型加载，用于 KSampler 精修）
        loader = graph.add_node('CheckpointLoaderSimple', [100, 300])
        loader.inputs = [
            {"name": "ckpt_name", "type": "MODEL", "link": None, "widget": {"name": "ckpt_name"}}
        ]
        loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0},
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 1},
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 2}
        ]
        loader.widgets_values = [self._pick_model('checkpoint', self.target_model_family, self.library, self.object_info)]
        # 3. UpscaleModelLoader（使用 _pick_model('upscale', ...)）
        up_loader = graph.add_node('UpscaleModelLoader', [300, 100])
        up_loader.inputs = [
            {"name": "model_name", "type": "COMBO", "link": None, "widget": {"name": "model_name"}}
        ]
        up_loader.outputs = [
            {"name": "UPSCALE_MODEL", "type": "UPSCALE_MODEL", "links": [], "slot_index": 0}
        ]
        up_loader.widgets_values = [self._pick_model('upscale', self.target_model_family, self.library, self.object_info)]
        # 4. ImageUpscaleWithModel
        up_node = graph.add_node('ImageUpscaleWithModel', [500, 100])
        up_node.inputs = [
            {"name": "upscale_model", "type": "UPSCALE_MODEL", "link": None},
            {"name": "image", "type": "IMAGE", "link": None}
        ]
        up_node.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # 5. VAEEncode（放大后图像编码为 latent 以便 KSampler 精修）
        vae_encode = graph.add_node('VAEEncode', [700, 100])
        vae_encode.inputs = [
            {"name": "pixels", "type": "IMAGE", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_encode.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        # 6. KSampler（denoise 较低，如 0.2）
        sampler = graph.add_node('KSampler', [700, 300])
        sampler.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20), params.get('cfg', 7.0),
            "euler", "normal", 0.2  # 放大精修使用较低 denoise
        ]
        # 7. VAE Decode
        vae_decode = graph.add_node('VAEDecode', [900, 300])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None}
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # 8. SaveImage
        save = graph.add_node('SaveImage', [1100, 300])
        save.inputs = [
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "images", "type": "IMAGE", "link": None}
        ]
        save.outputs = []
        save.widgets_values = ["ComfyUI_Upscale"]
        # 连接
        graph.connect(load_image.id, 0, up_node.id, 1)       # IMAGE -> image
        graph.connect(up_loader.id, 0, up_node.id, 0)        # UPSCALE_MODEL -> upscale_model
        graph.connect(up_node.id, 0, vae_encode.id, 0)       # IMAGE -> pixels
        graph.connect(loader.id, 2, vae_encode.id, 1)        # VAE -> vae_encode
        graph.connect(loader.id, 0, sampler.id, 0)           # MODEL -> sampler model
        graph.connect(vae_encode.id, 0, sampler.id, 8)       # LATENT -> latent_image
        graph.connect(sampler.id, 0, vae_decode.id, 0)       # LATENT -> samples
        graph.connect(loader.id, 2, vae_decode.id, 1)        # VAE -> vae
        graph.connect(vae_decode.id, 0, save.id, 1)          # IMAGE -> images
    
    def _build_first_last_frame(self, first_image, last_image, user_prompt,
                                ratio="9:16", steps=8, seed=12345,
                                filename_prefix="first_last", architecture_scheme="single",
                                blocks_to_swap=20, attention_mode="sdpa", base_precision="bf16",
                                high_lora_strength=1.0, low_lora_strength=1.0):
        """首尾帧视频（V19兼容架构，lc.txt 六阶段架构）

        WanFirstLastFrameToVideo 使用旧的 CONDITIONING/CLIP_VISION_OUTPUT 输入模式，
        因此保留 CLIPTextEncode + CLIPVisionEncode 路径。
        V19兼容变更：使用 clip_legacy_id（CLIPLoader）替代 clip_global（T5）供 CLIPTextEncode。

        Returns: 完整的UI格式工作流JSON (含 nodes, links, last_node_id, last_link_id)
        """
        graph = WorkflowGraph()
        graph.metadata = {"design_source": "V19 六阶段架构", "task_type": "first_last_frame"}

        width, height = self._ratio_to_dimensions(ratio)

        # === 阶段1: 两条图像预处理链（首帧 + 尾帧） ===
        # 首帧预处理链
        s1a_nodes, s1a_links, s1a_out_id, s1a_out_slot = self._build_image_preprocessing(
            first_image, width, height)
        id_map1a = self._merge_stage_into_graph(graph, s1a_nodes, s1a_links)
        s1a_latent_global = id_map1a[s1a_out_id]

        # 尾帧预处理链
        s1b_nodes, s1b_links, s1b_out_id, s1b_out_slot = self._build_image_preprocessing(
            last_image, width, height)
        id_map1b = self._merge_stage_into_graph(graph, s1b_nodes, s1b_links)
        s1b_latent_global = id_map1b[s1b_out_id]

        # 查找两条链中的 Image Resize 节点（供 CLIPVisionEncode 使用）
        image_resize_nodes = self._find_nodes(graph, 'Image Resize')
        first_resize_global = image_resize_nodes[0].id if len(image_resize_nodes) > 0 else s1a_latent_global
        last_resize_global = image_resize_nodes[1].id if len(image_resize_nodes) > 1 else s1b_latent_global

        # === 阶段2: 模型加载（V19架构，动态架构选择） ===
        s2_nodes, s2_links, s2_ids = self._build_model_loading(
            "wan22", architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision,
            high_lora_strength=high_lora_strength, low_lora_strength=low_lora_strength)
        id_map2 = self._merge_stage_into_graph(graph, s2_nodes, s2_links)
        model_global = id_map2[s2_ids["model_id"]]
        model_high_global = id_map2[s2_ids["model_high_id"]]
        model_low_global = id_map2[s2_ids["model_low_id"]]
        vae_global = id_map2[s2_ids["vae_id"]]
        clip_legacy_global = id_map2[s2_ids["clip_legacy_id"]]  # Legacy CLIP for CLIPTextEncode
        clip_vision_global = id_map2[s2_ids["clip_vision_id"]]

        # === 阶段3: 提示词工程 ===
        structured_prompt = self._structure_prompt(user_prompt, ratio)
        negative_prompt = STANDARD_NEGATIVE_PROMPT

        s3_nodes = []
        s3_links = []
        _id3 = [0]

        def _new3(node_type, pos):
            _id3[0] += 1
            node = WorkflowNode(_id3[0], node_type, pos)
            s3_nodes.append(node)
            return node

        pos_encode = _new3('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [structured_prompt]

        neg_encode = _new3('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = [negative_prompt]

        # V19兼容: 使用 clip_legacy_global（CLIPLoader）而非 clip_global（T5）
        s3_links.append((clip_legacy_global, 0, pos_encode.id, 1, "CLIP"))
        s3_links.append((clip_legacy_global, 0, neg_encode.id, 1, "CLIP"))

        pos_local = pos_encode.id
        neg_local = neg_encode.id
        id_map3 = self._merge_stage_into_graph(graph, s3_nodes, s3_links)
        pos_global = id_map3[pos_local]
        neg_global = id_map3[neg_local]

        # === 连接阶段1两条链的外部输入 ===
        # FaceDetailer: model(slot1) / clip_vision(slot2) / positive(slot3) / negative(slot4)
        # VAEEncode: vae(slot1)
        face_detailers = self._find_nodes(graph, 'FaceDetailer')
        vae_encodes = self._find_nodes(graph, 'VAEEncode')
        for fd in face_detailers:
            self._add_cross_stage_link(graph, model_global, 0, fd.id, 1, "MODEL")
            self._add_cross_stage_link(graph, clip_vision_global, 0, fd.id, 2, "CLIP_VISION")
            self._add_cross_stage_link(graph, pos_global, 0, fd.id, 3, "CONDITIONING")
            self._add_cross_stage_link(graph, neg_global, 0, fd.id, 4, "CONDITIONING")
        for ve in vae_encodes:
            self._add_cross_stage_link(graph, vae_global, 0, ve.id, 1, "VAE")

        # === 阶段3.5: 两个 CLIPVisionEncode（首帧 + 尾帧） ===
        s35_nodes = []
        s35_links = []
        _id35 = [0]

        def _new35(node_type, pos):
            _id35[0] += 1
            node = WorkflowNode(_id35[0], node_type, pos)
            s35_nodes.append(node)
            return node

        clip_vision_encode_start = _new35('CLIPVisionEncode', [500, 500])
        clip_vision_encode_start.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
            {"name": "image", "type": "IMAGE", "link": None},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
        ]
        clip_vision_encode_start.outputs = [
            {"name": "CLIP_VISION_OUTPUT", "type": "CLIP_VISION_OUTPUT", "links": [], "slot_index": 0}]
        clip_vision_encode_start.widgets_values = ["center"]

        clip_vision_encode_end = _new35('CLIPVisionEncode', [500, 700])
        clip_vision_encode_end.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
            {"name": "image", "type": "IMAGE", "link": None},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
        ]
        clip_vision_encode_end.outputs = [
            {"name": "CLIP_VISION_OUTPUT", "type": "CLIP_VISION_OUTPUT", "links": [], "slot_index": 0}]
        clip_vision_encode_end.widgets_values = ["center"]

        s35_links.append((clip_vision_global, 0, clip_vision_encode_start.id, 0, "CLIP_VISION"))
        s35_links.append((first_resize_global, 0, clip_vision_encode_start.id, 1, "IMAGE"))
        s35_links.append((clip_vision_global, 0, clip_vision_encode_end.id, 0, "CLIP_VISION"))
        s35_links.append((last_resize_global, 0, clip_vision_encode_end.id, 1, "IMAGE"))

        clip_vision_start_local = clip_vision_encode_start.id
        clip_vision_end_local = clip_vision_encode_end.id
        id_map35 = self._merge_stage_into_graph(graph, s35_nodes, s35_links)
        clip_vision_start_global = id_map35[clip_vision_start_local]
        clip_vision_end_global = id_map35[clip_vision_end_local]

        # === 阶段4: 核心生成（WanFirstLastFrameToVideo，动态架构选择） ===
        # 使用 WanFirstLastFrameToVideo 节点，支持 start_image + end_image +
        # clip_vision_start + clip_vision_end；若不可用则回退到 WanVideo I2V Sampler
        # 方案A(双串行): HIGH模型denoise=1.0主结构 → LOW模型denoise=0.3细节
        # 方案B(单一): 单采样器denoise=1.0
        s4_nodes = []
        s4_links = []
        _id4 = [0]

        def _new4(node_type, pos):
            _id4[0] += 1
            node = WorkflowNode(_id4[0], node_type, pos)
            s4_nodes.append(node)
            return node

        def _make_flf_sampler(pos, denoise_strength):
            """构造一个 WanFirstLastFrameToVideo 采样器节点"""
            s = _new4('WanFirstLastFrameToVideo', pos)
            s.inputs = [
                {"name": "latent", "type": "LATENT", "link": None},                          # slot 0
                {"name": "model", "type": "MODEL", "link": None},                            # slot 1
                {"name": "positive", "type": "CONDITIONING", "link": None},                  # slot 2
                {"name": "negative", "type": "CONDITIONING", "link": None},                  # slot 3
                {"name": "clip_vision_output_start", "type": "CLIP_VISION_OUTPUT", "link": None},  # slot 4
                {"name": "clip_vision_output_end", "type": "CLIP_VISION_OUTPUT", "link": None},    # slot 5
            ]
            s.outputs = [
                {"name": "latents", "type": "LATENT", "links": [], "slot_index": 0}]
            s.widgets_values = [
                steps,              # steps
                5.5,                # cfg
                "euler",            # sampler
                "karras",           # scheduler
                0.6,                # motion_scale
                0.0,                # noise_aug
                48,                 # frames
                24,                 # fps
                denoise_strength,   # denoise_strength: 方案A第一阶段=1.0，第二阶段=0.3；方案B=1.0
                seed,               # seed
                1.0,                # shift
            ]
            return s

        is_dual = (architecture_scheme == "dual_serial")

        if is_dual:
            # === 方案A: HIGH+LOW 双采集器串行 ===
            # 第一阶段: HIGH 模型，denoise=1.0，主结构生成，latent 来自首帧 VAE Encode
            sampler_high = _make_flf_sampler([800, 250], 1.0)
            s4_links.append((s1a_latent_global, s1a_out_slot, sampler_high.id, 0, "LATENT"))
            s4_links.append((model_high_global, 0, sampler_high.id, 1, "MODEL"))
            s4_links.append((pos_global, 0, sampler_high.id, 2, "CONDITIONING"))
            s4_links.append((neg_global, 0, sampler_high.id, 3, "CONDITIONING"))
            s4_links.append((clip_vision_start_global, 0, sampler_high.id, 4, "CLIP_VISION_OUTPUT"))
            s4_links.append((clip_vision_end_global, 0, sampler_high.id, 5, "CLIP_VISION_OUTPUT"))

            # 第二阶段: LOW 模型，denoise=0.3，细节细化，latent 来自第一阶段输出
            sampler_low = _make_flf_sampler([800, 450], 0.3)
            final_local = sampler_low.id
            # latent 来自第一阶段输出（合并后建立内部连接）
            sampler_high_local = sampler_high.id
        else:
            # === 方案B: 单一采样器 ===
            sampler = _make_flf_sampler([800, 300], 1.0)
            final_local = sampler.id
            sampler_high_local = None

        id_map4 = self._merge_stage_into_graph(graph, s4_nodes, s4_links)
        sampler_global = id_map4[final_local]

        # 方案A: 建立第一阶段 → 第二阶段的 latent 内部连接（需在合并后用全局 id）
        if is_dual and sampler_high_local is not None:
            sampler_high_global = id_map4[sampler_high_local]
            self._add_cross_stage_link(graph, sampler_high_global, 0, sampler_global, 0, "LATENT")

        # === 阶段5: 初级合成 ===
        s5_nodes, s5_links, s5_out_id, s5_out_slot = self._build_video_output(
            sampler_global, 0,
            vae_global, 0,
            filename_prefix)
        id_map5 = self._merge_stage_into_graph(graph, s5_nodes, s5_links)
        vae_decode_global = id_map5[s5_out_id]

        # === 阶段6: 后处理提升 ===
        s6_nodes, s6_links, _, _ = self._build_post_processing(
            vae_decode_global, s5_out_slot,
            filename_prefix)
        self._merge_stage_into_graph(graph, s6_nodes, s6_links)

        return graph.to_web_format()

    def _build_multi_image_video(self, image_names, user_prompt, ratio="9:16",
                                 steps=8, seed=12345, filename_prefix="multi_img",
                                 architecture_scheme="single",
                                 num_frames=121, blocks_to_swap=20, attention_mode="sdpa",
                                 base_precision="bf16", high_lora_strength=1.0,
                                 low_lora_strength=1.0, split_step=None):
        """多图视频（V19验证成功架构，lc.txt 六阶段架构）

        V19架构变更：
        - 移除 LatentBatch 拼接（V19 sampler 使用 image_embeds，不接收 latent）
        - 使用第一张图作为 start_image（WanVideoImageToVideoEncode）
        - 使用第一张图作为 image_1（WanVideoClipVisionEncode）
        - 其余图片仍经预处理（FaceDetailer），但不直接参与 V19 sampler 输入

        Returns: 完整的UI格式工作流JSON (含 nodes, links, last_node_id, last_link_id)
        """
        graph = WorkflowGraph()
        graph.metadata = {"design_source": "V19 六阶段架构", "task_type": "multi_image_video"}

        width, height = self._ratio_to_dimensions(ratio)
        # 单次生成帧数（默认 121，避免超过训练长度触发语义重复）

        # === 阶段1: 多条图像预处理链（每张图独立预处理） ===
        for img_name in image_names:
            s1_nodes, s1_links, _, _ = self._build_image_preprocessing(
                img_name, width, height)
            self._merge_stage_into_graph(graph, s1_nodes, s1_links)

        # 查找所有 Image Resize 节点（第一张图的 resize 作为 start_image）
        image_resize_nodes = self._find_nodes(graph, 'Image Resize')
        start_image_global = image_resize_nodes[0].id if image_resize_nodes else None

        # === 阶段2: 模型加载（V19架构，动态架构选择） ===
        s2_nodes, s2_links, s2_ids = self._build_model_loading(
            "wan22", architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision,
            high_lora_strength=high_lora_strength, low_lora_strength=low_lora_strength)
        id_map2 = self._merge_stage_into_graph(graph, s2_nodes, s2_links)
        model_global = id_map2[s2_ids["model_id"]]
        model_high_global = id_map2[s2_ids["model_high_id"]]
        model_low_global = id_map2[s2_ids["model_low_id"]]
        vae_global = id_map2[s2_ids["vae_id"]]
        clip_global = id_map2[s2_ids["clip_id"]]
        clip_legacy_global = id_map2[s2_ids["clip_legacy_id"]]
        clip_vision_global = id_map2[s2_ids["clip_vision_id"]]

        # === 阶段3: 提示词工程（双路径文本编码） ===
        structured_prompt = self._structure_prompt(user_prompt, ratio)
        negative_prompt = STANDARD_NEGATIVE_PROMPT

        s3_nodes = []
        s3_links = []
        _id3 = [0]

        def _new3(node_type, pos):
            _id3[0] += 1
            node = WorkflowNode(_id3[0], node_type, pos)
            s3_nodes.append(node)
            return node

        # 3a: CLIPTextEncode (legacy, for FaceDetailer)
        pos_encode = _new3('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [structured_prompt]

        neg_encode = _new3('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = [negative_prompt]

        s3_links.append((clip_legacy_global, 0, pos_encode.id, 1, "CLIP"))
        s3_links.append((clip_legacy_global, 0, neg_encode.id, 1, "CLIP"))

        # 3b: WanVideoTextEncode (V19, for WanVideoSampler)
        text_encode = _new3('WanVideoTextEncode', [300, 500])
        text_encode.inputs = [
            {"name": "positive_prompt", "type": "STRING", "link": None, "widget": {"name": "positive_prompt"}},
            {"name": "negative_prompt", "type": "STRING", "link": None, "widget": {"name": "negative_prompt"}},
            {"name": "t5", "type": "T5", "link": None},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        text_encode.outputs = [
            {"name": "TEXT_EMBEDS", "type": "TEXT_EMBEDS", "links": [], "slot_index": 0}
        ]
        text_encode.widgets_values = [structured_prompt, negative_prompt, True]
        s3_links.append((clip_global, 0, text_encode.id, 2, "T5"))

        pos_local = pos_encode.id
        neg_local = neg_encode.id
        text_encode_local = text_encode.id
        id_map3 = self._merge_stage_into_graph(graph, s3_nodes, s3_links)
        pos_global = id_map3[pos_local]
        neg_global = id_map3[neg_local]
        text_embeds_global = id_map3[text_encode_local]

        # === 连接阶段1所有链的外部输入 ===
        face_detailers = self._find_nodes(graph, 'FaceDetailer')
        vae_encodes = self._find_nodes(graph, 'VAEEncode')
        for fd in face_detailers:
            self._add_cross_stage_link(graph, model_global, 0, fd.id, 1, "MODEL")
            self._add_cross_stage_link(graph, clip_vision_global, 0, fd.id, 2, "CLIP_VISION")
            self._add_cross_stage_link(graph, pos_global, 0, fd.id, 3, "CONDITIONING")
            self._add_cross_stage_link(graph, neg_global, 0, fd.id, 4, "CONDITIONING")
        for ve in vae_encodes:
            self._add_cross_stage_link(graph, vae_global, 0, ve.id, 1, "VAE")

        # === 阶段3.5: WanVideoClipVisionEncode（V19） ===
        s35_nodes = []
        s35_links = []
        _id35 = [0]

        def _new35(node_type, pos):
            _id35[0] += 1
            node = WorkflowNode(_id35[0], node_type, pos)
            s35_nodes.append(node)
            return node

        clip_vision_encode = _new35('WanVideoClipVisionEncode', [500, 500])
        clip_vision_encode.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
            {"name": "image_1", "type": "IMAGE", "link": None},
            {"name": "strength_1", "type": "FLOAT", "link": None, "widget": {"name": "strength_1"}},
            {"name": "strength_2", "type": "FLOAT", "link": None, "widget": {"name": "strength_2"}},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
            {"name": "combine_embeds", "type": "COMBO", "link": None, "widget": {"name": "combine_embeds"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        clip_vision_encode.outputs = [
            {"name": "CLIP_EMBEDS", "type": "CLIP_EMBEDS", "links": [], "slot_index": 0}
        ]
        clip_vision_encode.widgets_values = [1.0, 1.0, "center", "average", True]
        s35_links.append((clip_vision_global, 0, clip_vision_encode.id, 0, "CLIP_VISION"))
        s35_links.append((start_image_global, 0, clip_vision_encode.id, 1, "IMAGE"))

        clip_vision_local = clip_vision_encode.id
        id_map35 = self._merge_stage_into_graph(graph, s35_nodes, s35_links)
        clip_embeds_global = id_map35[clip_vision_local]

        # === 阶段3.6: WanVideoImageToVideoEncode（V19新增） ===
        s36_nodes = []
        s36_links = []
        _id36 = [0]

        def _new36(node_type, pos):
            _id36[0] += 1
            node = WorkflowNode(_id36[0], node_type, pos)
            s36_nodes.append(node)
            return node

        i2v_encode = _new36('WanVideoImageToVideoEncode', [500, 700])
        i2v_encode.inputs = [
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "num_frames", "type": "INT", "link": None, "widget": {"name": "num_frames"}},
            {"name": "noise_aug_strength", "type": "FLOAT", "link": None, "widget": {"name": "noise_aug_strength"}},
            {"name": "start_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "start_latent_strength"}},
            {"name": "end_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "end_latent_strength"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
            {"name": "vae", "type": "VAE", "link": None},
            {"name": "clip_embeds", "type": "CLIP_EMBEDS", "link": None},
            {"name": "start_image", "type": "IMAGE", "link": None},
        ]
        i2v_encode.outputs = [
            {"name": "IMAGE_EMBEDS", "type": "IMAGE_EMBEDS", "links": [], "slot_index": 0}
        ]
        i2v_encode.widgets_values = [width, height, num_frames, 0.1, 1.0, 1.0, True]
        s36_links.append((vae_global, 0, i2v_encode.id, 7, "VAE"))
        s36_links.append((clip_embeds_global, 0, i2v_encode.id, 8, "CLIP_EMBEDS"))
        s36_links.append((start_image_global, 0, i2v_encode.id, 9, "IMAGE"))

        i2v_local = i2v_encode.id
        id_map36 = self._merge_stage_into_graph(graph, s36_nodes, s36_links)
        image_embeds_global = id_map36[i2v_local]

        # === 阶段4: 核心生成（V19新签名） ===
        s4_nodes, s4_links, s4_out_id, s4_out_slot = self._build_core_generation(
            image_embeds_global, 0,
            text_embeds_global, 0,
            model_high_global, 0,
            model_low_global, 0,
            architecture_scheme=architecture_scheme,
            steps=steps, seed=seed, split_step=split_step)
        id_map4 = self._merge_stage_into_graph(graph, s4_nodes, s4_links)
        sampler_global = id_map4[s4_out_id]

        # === 阶段5: 初级合成（V19 WanVideoDecode） ===
        s5_nodes, s5_links, s5_out_id, s5_out_slot = self._build_video_output(
            sampler_global, s4_out_slot,
            vae_global, 0,
            filename_prefix)
        id_map5 = self._merge_stage_into_graph(graph, s5_nodes, s5_links)
        vae_decode_global = id_map5[s5_out_id]

        # === 阶段6: 后处理提升 ===
        s6_nodes, s6_links, _, _ = self._build_post_processing(
            vae_decode_global, s5_out_slot,
            filename_prefix)
        self._merge_stage_into_graph(graph, s6_nodes, s6_links)

        return graph.to_web_format()

    def _build_long_video(self, image_name, user_prompt, ratio="9:16", steps=8, seed=12345,
                          segments=2, filename_prefix="long_vid", architecture_scheme="single",
                          blocks_to_swap=20, attention_mode="sdpa", base_precision="bf16",
                          high_lora_strength=1.0, low_lora_strength=1.0, split_step=None):
        """长视频（V19验证成功架构，lc.txt 六阶段架构）

        V19架构变更：
        - 阶段3.6: WanVideoImageToVideoEncode 的 num_frames = segments * 48（长视频帧数）
        - 阶段4: _build_core_generation 使用 V19 新签名

        Returns: 完整的UI格式工作流JSON (含 nodes, links, last_node_id, last_link_id)
        """
        graph = WorkflowGraph()
        graph.metadata = {"design_source": "V19 六阶段架构", "task_type": "long_video"}

        width, height = self._ratio_to_dimensions(ratio)
        # 长视频帧数 = 段数 × 48（每段约2秒@24fps）
        num_frames = segments * 48

        # === 阶段1: 图像预处理 ===
        s1_nodes, s1_links, s1_out_id, s1_out_slot = self._build_image_preprocessing(
            image_name, width, height)
        id_map1 = self._merge_stage_into_graph(graph, s1_nodes, s1_links)
        s1_latent_global = id_map1[s1_out_id]

        # 查找阶段1中的 Image Resize 节点（供 V19 编码节点使用）
        image_resize_node = self._find_node(graph, 'Image Resize')
        start_image_global = image_resize_node.id if image_resize_node else s1_latent_global

        # === 阶段2: 模型加载（V19架构，动态架构选择） ===
        s2_nodes, s2_links, s2_ids = self._build_model_loading(
            "wan22", architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision,
            high_lora_strength=high_lora_strength, low_lora_strength=low_lora_strength)
        id_map2 = self._merge_stage_into_graph(graph, s2_nodes, s2_links)
        model_global = id_map2[s2_ids["model_id"]]
        model_high_global = id_map2[s2_ids["model_high_id"]]
        model_low_global = id_map2[s2_ids["model_low_id"]]
        vae_global = id_map2[s2_ids["vae_id"]]
        clip_global = id_map2[s2_ids["clip_id"]]
        clip_legacy_global = id_map2[s2_ids["clip_legacy_id"]]
        clip_vision_global = id_map2[s2_ids["clip_vision_id"]]

        # === 阶段3: 提示词工程（双路径文本编码） ===
        structured_prompt = self._structure_prompt(user_prompt, ratio)
        negative_prompt = STANDARD_NEGATIVE_PROMPT

        s3_nodes = []
        s3_links = []
        _id3 = [0]

        def _new3(node_type, pos):
            _id3[0] += 1
            node = WorkflowNode(_id3[0], node_type, pos)
            s3_nodes.append(node)
            return node

        # 3a: CLIPTextEncode (legacy, for FaceDetailer)
        pos_encode = _new3('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [structured_prompt]

        neg_encode = _new3('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = [negative_prompt]

        s3_links.append((clip_legacy_global, 0, pos_encode.id, 1, "CLIP"))
        s3_links.append((clip_legacy_global, 0, neg_encode.id, 1, "CLIP"))

        # 3b: WanVideoTextEncode (V19, for WanVideoSampler)
        text_encode = _new3('WanVideoTextEncode', [300, 500])
        text_encode.inputs = [
            {"name": "positive_prompt", "type": "STRING", "link": None, "widget": {"name": "positive_prompt"}},
            {"name": "negative_prompt", "type": "STRING", "link": None, "widget": {"name": "negative_prompt"}},
            {"name": "t5", "type": "T5", "link": None},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        text_encode.outputs = [
            {"name": "TEXT_EMBEDS", "type": "TEXT_EMBEDS", "links": [], "slot_index": 0}
        ]
        text_encode.widgets_values = [structured_prompt, negative_prompt, True]
        s3_links.append((clip_global, 0, text_encode.id, 2, "T5"))

        pos_local = pos_encode.id
        neg_local = neg_encode.id
        text_encode_local = text_encode.id
        id_map3 = self._merge_stage_into_graph(graph, s3_nodes, s3_links)
        pos_global = id_map3[pos_local]
        neg_global = id_map3[neg_local]
        text_embeds_global = id_map3[text_encode_local]

        # === 连接阶段1的外部输入 ===
        face_detailer = self._find_node(graph, 'FaceDetailer')
        vae_encode_node = self._find_node(graph, 'VAEEncode')
        if face_detailer:
            self._add_cross_stage_link(graph, model_global, 0, face_detailer.id, 1, "MODEL")
            self._add_cross_stage_link(graph, clip_vision_global, 0, face_detailer.id, 2, "CLIP_VISION")
            self._add_cross_stage_link(graph, pos_global, 0, face_detailer.id, 3, "CONDITIONING")
            self._add_cross_stage_link(graph, neg_global, 0, face_detailer.id, 4, "CONDITIONING")
        if vae_encode_node:
            self._add_cross_stage_link(graph, vae_global, 0, vae_encode_node.id, 1, "VAE")

        # === 阶段3.5: WanVideoClipVisionEncode（V19） ===
        s35_nodes = []
        s35_links = []
        _id35 = [0]

        def _new35(node_type, pos):
            _id35[0] += 1
            node = WorkflowNode(_id35[0], node_type, pos)
            s35_nodes.append(node)
            return node

        clip_vision_encode = _new35('WanVideoClipVisionEncode', [500, 500])
        clip_vision_encode.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
            {"name": "image_1", "type": "IMAGE", "link": None},
            {"name": "strength_1", "type": "FLOAT", "link": None, "widget": {"name": "strength_1"}},
            {"name": "strength_2", "type": "FLOAT", "link": None, "widget": {"name": "strength_2"}},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
            {"name": "combine_embeds", "type": "COMBO", "link": None, "widget": {"name": "combine_embeds"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        clip_vision_encode.outputs = [
            {"name": "CLIP_EMBEDS", "type": "CLIP_EMBEDS", "links": [], "slot_index": 0}
        ]
        clip_vision_encode.widgets_values = [1.0, 1.0, "center", "average", True]
        s35_links.append((clip_vision_global, 0, clip_vision_encode.id, 0, "CLIP_VISION"))
        s35_links.append((start_image_global, 0, clip_vision_encode.id, 1, "IMAGE"))

        clip_vision_local = clip_vision_encode.id
        id_map35 = self._merge_stage_into_graph(graph, s35_nodes, s35_links)
        clip_embeds_global = id_map35[clip_vision_local]

        # === 阶段3.6: WanVideoImageToVideoEncode（V19新增，长视频 num_frames = segments * 48） ===
        s36_nodes = []
        s36_links = []
        _id36 = [0]

        def _new36(node_type, pos):
            _id36[0] += 1
            node = WorkflowNode(_id36[0], node_type, pos)
            s36_nodes.append(node)
            return node

        i2v_encode = _new36('WanVideoImageToVideoEncode', [500, 700])
        i2v_encode.inputs = [
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "num_frames", "type": "INT", "link": None, "widget": {"name": "num_frames"}},
            {"name": "noise_aug_strength", "type": "FLOAT", "link": None, "widget": {"name": "noise_aug_strength"}},
            {"name": "start_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "start_latent_strength"}},
            {"name": "end_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "end_latent_strength"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
            {"name": "vae", "type": "VAE", "link": None},
            {"name": "clip_embeds", "type": "CLIP_EMBEDS", "link": None},
            {"name": "start_image", "type": "IMAGE", "link": None},
        ]
        i2v_encode.outputs = [
            {"name": "IMAGE_EMBEDS", "type": "IMAGE_EMBEDS", "links": [], "slot_index": 0}
        ]
        # 长视频: num_frames = segments * 48
        i2v_encode.widgets_values = [width, height, num_frames, 0.1, 1.0, 1.0, True]
        s36_links.append((vae_global, 0, i2v_encode.id, 7, "VAE"))
        s36_links.append((clip_embeds_global, 0, i2v_encode.id, 8, "CLIP_EMBEDS"))
        s36_links.append((start_image_global, 0, i2v_encode.id, 9, "IMAGE"))

        i2v_local = i2v_encode.id
        id_map36 = self._merge_stage_into_graph(graph, s36_nodes, s36_links)
        image_embeds_global = id_map36[i2v_local]

        # === 阶段4: 核心生成（V19新签名） ===
        s4_nodes, s4_links, s4_out_id, s4_out_slot = self._build_core_generation(
            image_embeds_global, 0,
            text_embeds_global, 0,
            model_high_global, 0,
            model_low_global, 0,
            architecture_scheme=architecture_scheme,
            steps=steps, seed=seed, split_step=split_step)
        id_map4 = self._merge_stage_into_graph(graph, s4_nodes, s4_links)
        sampler_global = id_map4[s4_out_id]

        # === 阶段5: 初级合成（V19 WanVideoDecode） ===
        s5_nodes, s5_links, s5_out_id, s5_out_slot = self._build_video_output(
            sampler_global, s4_out_slot,
            vae_global, 0,
            filename_prefix)
        id_map5 = self._merge_stage_into_graph(graph, s5_nodes, s5_links)
        vae_decode_global = id_map5[s5_out_id]

        # === 阶段6: 后处理提升 ===
        s6_nodes, s6_links, _, _ = self._build_post_processing(
            vae_decode_global, s5_out_slot,
            filename_prefix)
        self._merge_stage_into_graph(graph, s6_nodes, s6_links)

        return graph.to_web_format()

    def _build_video_concat(self, video_paths, user_prompt, ratio="9:16",
                            filename_prefix="vid_concat"):
        """视频拼接（lc.txt 六阶段架构 - 输出阶段）

        视频拼接不涉及生成，仅加载多个视频并拼接为一个长视频。
        使用 VHS_VideoCombine 输出 MP4（禁止 CreateVideo + SaveVideo）。

        Returns: 完整的UI格式工作流JSON (含 nodes, links, last_node_id, last_link_id)
        """
        graph = WorkflowGraph()
        graph.metadata = {"design_source": "lc.txt 六阶段架构", "task_type": "video_concat"}

        # === 加载多个视频 ===
        s1_nodes = []
        s1_links = []
        _id1 = [0]

        def _new1(node_type, pos):
            _id1[0] += 1
            node = WorkflowNode(_id1[0], node_type, pos)
            s1_nodes.append(node)
            return node

        load_video_locals = []
        for i, vpath in enumerate(video_paths):
            lv = _new1('VHS_LoadVideo', [100, 100 + i * 150])
            lv.inputs = [{"name": "video", "type": "STRING", "link": None, "widget": {"name": "video"}}]
            lv.outputs = [
                {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
                {"name": "frame_count", "type": "INT", "links": [], "slot_index": 1},
                {"name": "audio", "type": "AUDIO", "links": [], "slot_index": 2},
                {"name": "video_metadata", "type": "VHS_METADATA", "links": [], "slot_index": 3},
            ]
            lv.widgets_values = [vpath, "full_video"]
            load_video_locals.append(lv.id)

        id_map1 = self._merge_stage_into_graph(graph, s1_nodes, s1_links)

        # === ImageBatch 链式拼接（将多个视频的帧序列拼接） ===
        s15_nodes = []
        s15_links = []
        _id15 = [0]

        def _new15(node_type, pos):
            _id15[0] += 1
            node = WorkflowNode(_id15[0], node_type, pos)
            s15_nodes.append(node)
            return node

        if len(load_video_locals) > 1:
            prev_batch_local = None
            for i in range(len(load_video_locals) - 1):
                batch_node = _new15('ImageBatch', [400, 100 + i * 100])
                batch_node.inputs = [
                    {"name": "image1", "type": "IMAGE", "link": None},
                    {"name": "image2", "type": "IMAGE", "link": None},
                ]
                batch_node.outputs = [{"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}]
                if i == 0:
                    s15_links.append((id_map1[load_video_locals[0]], 0, batch_node.id, 0, "IMAGE"))
                else:
                    s15_links.append((prev_batch_local, 0, batch_node.id, 0, "IMAGE"))
                s15_links.append((id_map1[load_video_locals[i + 1]], 0, batch_node.id, 1, "IMAGE"))
                prev_batch_local = batch_node.id

            id_map15 = self._merge_stage_into_graph(graph, s15_nodes, s15_links)
            combined_image_global = id_map15[prev_batch_local]
        else:
            combined_image_global = id_map1[load_video_locals[0]]

        # === 输出阶段: VHS_VideoCombine（禁止 CreateVideo + SaveVideo） ===
        s_out_nodes = []
        s_out_links = []
        _id_out = [0]

        def _new_out(node_type, pos):
            _id_out[0] += 1
            node = WorkflowNode(_id_out[0], node_type, pos)
            s_out_nodes.append(node)
            return node

        video_combine = _new_out('VHS_VideoCombine', [700, 200])
        video_combine.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "frame_rate", "type": "FLOAT", "link": None, "widget": {"name": "frame_rate"}},
            {"name": "loop_count", "type": "INT", "link": None, "widget": {"name": "loop_count"}},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "format", "type": "COMBO", "link": None, "widget": {"name": "format"}},
            {"name": "pix_fmt", "type": "STRING", "link": None, "widget": {"name": "pix_fmt"}},
            {"name": "save_metadata", "type": "BOOLEAN", "link": None, "widget": {"name": "save_metadata"}},
            {"name": "crf", "type": "FLOAT", "link": None, "widget": {"name": "crf"}},
        ]
        video_combine.outputs = []
        video_combine.widgets_values = [
            24.0,               # frame_rate
            0,                  # loop_count
            filename_prefix,    # filename_prefix
            "video/h264-mp4",   # format H.264 MP4
            "yuv420p",          # pix_fmt 兼容性最佳
            True,               # save_metadata
            18,                 # crf=18 高质量
        ]

        s_out_links.append((combined_image_global, 0, video_combine.id, 0, "IMAGE"))
        self._merge_stage_into_graph(graph, s_out_nodes, s_out_links)

        return graph.to_web_format()

    def _build_multi_ref_video(self, ref_images, user_prompt, ratio="9:16", steps=8, seed=12345,
                               filename_prefix="multi_ref", architecture_scheme="single",
                               num_frames=121, blocks_to_swap=20, attention_mode="sdpa",
                               base_precision="bf16", high_lora_strength=1.0,
                               low_lora_strength=1.0, split_step=None):
        """多参考图视频（V19验证成功架构，lc.txt 六阶段架构）

        V19架构变更：
        - 阶段3.5: WanVideoClipVisionEncode 使用第一张参考图
        - 阶段3.6: WanVideoImageToVideoEncode 使用第一张参考图作为 start_image
        - 阶段4: _build_core_generation 使用 V19 新签名

        Returns: 完整的UI格式工作流JSON (含 nodes, links, last_node_id, last_link_id)
        """
        graph = WorkflowGraph()
        graph.metadata = {"design_source": "V19 六阶段架构", "task_type": "multi_ref_video"}

        width, height = self._ratio_to_dimensions(ratio)
        # 单次生成帧数（默认 121，避免超过训练长度触发语义重复）

        # 第一张参考图作为主输入
        first_ref = ref_images[0] if ref_images else "input_image.png"

        # === 阶段1: 图像预处理（使用第一张参考图） ===
        s1_nodes, s1_links, s1_out_id, s1_out_slot = self._build_image_preprocessing(
            first_ref, width, height)
        id_map1 = self._merge_stage_into_graph(graph, s1_nodes, s1_links)
        s1_latent_global = id_map1[s1_out_id]

        # 查找阶段1中的 Image Resize 节点（供 V19 编码节点使用）
        image_resize_node = self._find_node(graph, 'Image Resize')
        start_image_global = image_resize_node.id if image_resize_node else s1_latent_global

        # === 阶段2: 模型加载（V19架构，动态架构选择） ===
        s2_nodes, s2_links, s2_ids = self._build_model_loading(
            "wan22", architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision,
            high_lora_strength=high_lora_strength, low_lora_strength=low_lora_strength)
        id_map2 = self._merge_stage_into_graph(graph, s2_nodes, s2_links)
        model_global = id_map2[s2_ids["model_id"]]
        model_high_global = id_map2[s2_ids["model_high_id"]]
        model_low_global = id_map2[s2_ids["model_low_id"]]
        vae_global = id_map2[s2_ids["vae_id"]]
        clip_global = id_map2[s2_ids["clip_id"]]
        clip_legacy_global = id_map2[s2_ids["clip_legacy_id"]]
        clip_vision_global = id_map2[s2_ids["clip_vision_id"]]

        # === 阶段3: 提示词工程（双路径文本编码） ===
        structured_prompt = self._structure_prompt(user_prompt, ratio)
        negative_prompt = STANDARD_NEGATIVE_PROMPT

        s3_nodes = []
        s3_links = []
        _id3 = [0]

        def _new3(node_type, pos):
            _id3[0] += 1
            node = WorkflowNode(_id3[0], node_type, pos)
            s3_nodes.append(node)
            return node

        # 3a: CLIPTextEncode (legacy, for FaceDetailer)
        pos_encode = _new3('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [structured_prompt]

        neg_encode = _new3('CLIPTextEncode', [300, 300])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = [negative_prompt]

        s3_links.append((clip_legacy_global, 0, pos_encode.id, 1, "CLIP"))
        s3_links.append((clip_legacy_global, 0, neg_encode.id, 1, "CLIP"))

        # 3b: WanVideoTextEncode (V19, for WanVideoSampler)
        text_encode = _new3('WanVideoTextEncode', [300, 500])
        text_encode.inputs = [
            {"name": "positive_prompt", "type": "STRING", "link": None, "widget": {"name": "positive_prompt"}},
            {"name": "negative_prompt", "type": "STRING", "link": None, "widget": {"name": "negative_prompt"}},
            {"name": "t5", "type": "T5", "link": None},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        text_encode.outputs = [
            {"name": "TEXT_EMBEDS", "type": "TEXT_EMBEDS", "links": [], "slot_index": 0}
        ]
        text_encode.widgets_values = [structured_prompt, negative_prompt, True]
        s3_links.append((clip_global, 0, text_encode.id, 2, "T5"))

        pos_local = pos_encode.id
        neg_local = neg_encode.id
        text_encode_local = text_encode.id
        id_map3 = self._merge_stage_into_graph(graph, s3_nodes, s3_links)
        pos_global = id_map3[pos_local]
        neg_global = id_map3[neg_local]
        text_embeds_global = id_map3[text_encode_local]

        # === 连接阶段1的外部输入 ===
        face_detailer = self._find_node(graph, 'FaceDetailer')
        vae_encode_node = self._find_node(graph, 'VAEEncode')
        if face_detailer:
            self._add_cross_stage_link(graph, model_global, 0, face_detailer.id, 1, "MODEL")
            self._add_cross_stage_link(graph, clip_vision_global, 0, face_detailer.id, 2, "CLIP_VISION")
            self._add_cross_stage_link(graph, pos_global, 0, face_detailer.id, 3, "CONDITIONING")
            self._add_cross_stage_link(graph, neg_global, 0, face_detailer.id, 4, "CONDITIONING")
        if vae_encode_node:
            self._add_cross_stage_link(graph, vae_global, 0, vae_encode_node.id, 1, "VAE")

        # === 阶段3.5: WanVideoClipVisionEncode（V19，使用第一张参考图） ===
        s35_nodes = []
        s35_links = []
        _id35 = [0]

        def _new35(node_type, pos):
            _id35[0] += 1
            node = WorkflowNode(_id35[0], node_type, pos)
            s35_nodes.append(node)
            return node

        clip_vision_encode = _new35('WanVideoClipVisionEncode', [500, 500])
        clip_vision_encode.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
            {"name": "image_1", "type": "IMAGE", "link": None},
            {"name": "strength_1", "type": "FLOAT", "link": None, "widget": {"name": "strength_1"}},
            {"name": "strength_2", "type": "FLOAT", "link": None, "widget": {"name": "strength_2"}},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
            {"name": "combine_embeds", "type": "COMBO", "link": None, "widget": {"name": "combine_embeds"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
        ]
        clip_vision_encode.outputs = [
            {"name": "CLIP_EMBEDS", "type": "CLIP_EMBEDS", "links": [], "slot_index": 0}
        ]
        clip_vision_encode.widgets_values = [1.0, 1.0, "center", "average", True]
        s35_links.append((clip_vision_global, 0, clip_vision_encode.id, 0, "CLIP_VISION"))
        s35_links.append((start_image_global, 0, clip_vision_encode.id, 1, "IMAGE"))

        clip_vision_local = clip_vision_encode.id
        id_map35 = self._merge_stage_into_graph(graph, s35_nodes, s35_links)
        clip_embeds_global = id_map35[clip_vision_local]

        # === 阶段3.6: WanVideoImageToVideoEncode（V19新增） ===
        s36_nodes = []
        s36_links = []
        _id36 = [0]

        def _new36(node_type, pos):
            _id36[0] += 1
            node = WorkflowNode(_id36[0], node_type, pos)
            s36_nodes.append(node)
            return node

        i2v_encode = _new36('WanVideoImageToVideoEncode', [500, 700])
        i2v_encode.inputs = [
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "num_frames", "type": "INT", "link": None, "widget": {"name": "num_frames"}},
            {"name": "noise_aug_strength", "type": "FLOAT", "link": None, "widget": {"name": "noise_aug_strength"}},
            {"name": "start_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "start_latent_strength"}},
            {"name": "end_latent_strength", "type": "FLOAT", "link": None, "widget": {"name": "end_latent_strength"}},
            {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
            {"name": "vae", "type": "VAE", "link": None},
            {"name": "clip_embeds", "type": "CLIP_EMBEDS", "link": None},
            {"name": "start_image", "type": "IMAGE", "link": None},
        ]
        i2v_encode.outputs = [
            {"name": "IMAGE_EMBEDS", "type": "IMAGE_EMBEDS", "links": [], "slot_index": 0}
        ]
        i2v_encode.widgets_values = [width, height, num_frames, 0.1, 1.0, 1.0, True]
        s36_links.append((vae_global, 0, i2v_encode.id, 7, "VAE"))
        s36_links.append((clip_embeds_global, 0, i2v_encode.id, 8, "CLIP_EMBEDS"))
        s36_links.append((start_image_global, 0, i2v_encode.id, 9, "IMAGE"))

        i2v_local = i2v_encode.id
        id_map36 = self._merge_stage_into_graph(graph, s36_nodes, s36_links)
        image_embeds_global = id_map36[i2v_local]

        # === 阶段4: 核心生成（V19新签名） ===
        s4_nodes, s4_links, s4_out_id, s4_out_slot = self._build_core_generation(
            image_embeds_global, 0,
            text_embeds_global, 0,
            model_high_global, 0,
            model_low_global, 0,
            architecture_scheme=architecture_scheme,
            steps=steps, seed=seed, split_step=split_step)
        id_map4 = self._merge_stage_into_graph(graph, s4_nodes, s4_links)
        sampler_global = id_map4[s4_out_id]

        # === 阶段5: 初级合成（V19 WanVideoDecode） ===
        s5_nodes, s5_links, s5_out_id, s5_out_slot = self._build_video_output(
            sampler_global, s4_out_slot,
            vae_global, 0,
            filename_prefix)
        id_map5 = self._merge_stage_into_graph(graph, s5_nodes, s5_links)
        vae_decode_global = id_map5[s5_out_id]

        # === 阶段6: 后处理提升 ===
        s6_nodes, s6_links, _, _ = self._build_post_processing(
            vae_decode_global, s5_out_slot,
            filename_prefix)
        self._merge_stage_into_graph(graph, s6_nodes, s6_links)

        return graph.to_web_format()

    def _build_digital_human_lipsync(self, graph: WorkflowGraph, requirement: dict):
        """构建数字人口型同步架构 - 图片+音频生成说话视频

        参考"Wan2.2 Animate动作迁移+完美口型数字人长视频生成加速版"和"MultiTalk数字人唱歌"工作流架构：
        - LoadImage（人物参考图）+ LoadAudio（音频输入）
        - MultiTalkModelLoader + MultiTalkWav2VecEmbeds + DownloadAndLoadWav2VecModel（口型同步核心）
        - WanVideoModelLoader + WanVideoSampler + WanVideoDecode（Wan2.2视频底座）
        - WanVideoClipVisionEncode + CLIPVisionLoader（图片条件编码）
        - FaceMaskFromPoseKeypoints（面部遮罩，限定口型区域）
        - VHS_VideoCombine（视频输出，含音频）
        """
        params = requirement.get('parameters', {})
        family = self.target_model_family or 'Wan2.2'
        # 1. WanVideoModelLoader（加载 Wan2.2 视频模型）
        model_loader = graph.add_node('WanVideoModelLoader', [100, 100])
        model_loader.inputs = [
            {"name": "unet_name", "type": "COMBO", "link": None, "widget": {"name": "unet_name"}},
            {"name": "weight_dtype", "type": "COMBO", "link": None, "widget": {"name": "weight_dtype"}},
        ]
        model_loader.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0},
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 1},  # low_model
        ]
        model_loader.widgets_values = [
            self._pick_model('unet', family, self.library, self.object_info), "fp8_e4m3fn"
        ]
        # 2. LoadWanVideoT5TextEncoder（加载 T5 文本编码器）
        t5_loader = graph.add_node('LoadWanVideoT5TextEncoder', [100, 220])
        t5_loader.inputs = [
            {"name": "t5_name", "type": "COMBO", "link": None, "widget": {"name": "t5_name"}},
            {"name": "weight_dtype", "type": "COMBO", "link": None, "widget": {"name": "weight_dtype"}},
        ]
        t5_loader.outputs = [{"name": "T5", "type": "T5", "links": [], "slot_index": 0}]
        t5_loader.widgets_values = [self._pick_model('clip', family, self.library, self.object_info), "fp8_e4m3fn"]
        # 3. WanVideoVAELoader（加载 VAE）
        vae_loader = graph.add_node('WanVideoVAELoader', [100, 340])
        vae_loader.inputs = [{"name": "vae_name", "type": "COMBO", "link": None, "widget": {"name": "vae_name"}}]
        vae_loader.outputs = [{"name": "VAE", "type": "VAE", "links": [], "slot_index": 0}]
        vae_loader.widgets_values = [self._pick_model('vae', family, self.library, self.object_info)]
        # 4. CLIPVisionLoader + LoadImage + WanVideoClipVisionEncode
        clip_vision_loader = graph.add_node('CLIPVisionLoader', [100, 460])
        clip_vision_loader.inputs = [{"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}}]
        clip_vision_loader.outputs = [{"name": "CLIP_VISION", "type": "CLIP_VISION", "links": [], "slot_index": 0}]
        clip_vision_loader.widgets_values = [self._pick_model('clip_vision', family, self.library, self.object_info)]
        load_image = graph.add_node('LoadImage', [100, 580])
        load_image.inputs = [{"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}]
        load_image.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
        ]
        load_image.widgets_values = ["portrait.png"]
        clip_vision_encode = graph.add_node('WanVideoClipVisionEncode', [300, 460])
        clip_vision_encode.inputs = [
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},
            {"name": "image", "type": "IMAGE", "link": None},
        ]
        clip_vision_encode.outputs = [
            {"name": "CLIP_VISION_OUTPUT", "type": "CLIP_VISION_OUTPUT", "links": [], "slot_index": 0}
        ]
        # 5. 2x CLIPTextEncode（正/负提示词）
        pos_encode = graph.add_node('CLIPTextEncode', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [requirement.get('original', 'masterpiece, best quality')]
        neg_encode = graph.add_node('CLIPTextEncode', [300, 220])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None}
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = ["low quality, blurry"]
        # 6. 口型同步核心：LoadAudio + DownloadAndLoadWav2VecModel + MultiTalkModelLoader + MultiTalkWav2VecEmbeds
        load_audio = graph.add_node('LoadAudio', [100, 700])
        load_audio.inputs = [{"name": "audio", "type": "STRING", "link": None, "widget": {"name": "audio"}}]
        load_audio.outputs = [{"name": "AUDIO", "type": "AUDIO", "links": [], "slot_index": 0}]
        load_audio.widgets_values = ["speech.wav"]
        wav2vec_loader = graph.add_node('DownloadAndLoadWav2VecModel', [100, 820])
        wav2vec_loader.inputs = [{"name": "model", "type": "COMBO", "link": None, "widget": {"name": "model"}}]
        wav2vec_loader.outputs = [{"name": "WAV2VEC", "type": "WAV2VEC", "links": [], "slot_index": 0}]
        wav2vec_loader.widgets_values = ["default"]
        multitalk_model = graph.add_node('MultiTalkModelLoader', [300, 700])
        multitalk_model.inputs = [
            {"name": "wav2vec", "type": "WAV2VEC", "link": None},
            {"name": "model", "type": "COMBO", "link": None, "widget": {"name": "model"}},
        ]
        multitalk_model.outputs = [{"name": "MULTITALK", "type": "MULTITALK", "links": [], "slot_index": 0}]
        multitalk_model.widgets_values = ["default"]
        multitalk_embeds = graph.add_node('MultiTalkWav2VecEmbeds', [500, 700])
        multitalk_embeds.inputs = [
            {"name": "multitalk_model", "type": "MULTITALK", "link": None},
            {"name": "audio", "type": "AUDIO", "link": None},
        ]
        multitalk_embeds.outputs = [{"name": "EMBEDS", "type": "EMBEDS", "links": [], "slot_index": 0}]
        # 7. FaceMaskFromPoseKeypoints（面部遮罩，限定口型区域）
        face_mask = graph.add_node('FaceMaskFromPoseKeypoints', [300, 820])
        face_mask.inputs = [{"name": "image", "type": "IMAGE", "link": None}]
        face_mask.outputs = [{"name": "MASK", "type": "MASK", "links": [], "slot_index": 0}]
        # 8. WanVideoSampler
        sampler = graph.add_node('WanVideoSampler', [700, 100])
        sampler.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "vae", "type": "VAE", "link": None},
            {"name": "t5", "type": "T5", "link": None},
            {"name": "clip_vision_output", "type": "CLIP_VISION_OUTPUT", "link": None},
            {"name": "image", "type": "IMAGE", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "shift", "type": "FLOAT", "link": None, "widget": {"name": "shift"}},
            {"name": "sampler_name", "type": "COMBO", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "COMBO", "link": None, "widget": {"name": "scheduler"}},
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "length", "type": "INT", "link": None, "widget": {"name": "length"}},
            {"name": "batch_size", "type": "INT", "link": None, "widget": {"name": "batch_size"}},
        ]
        sampler.outputs = [{"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}]
        sampler.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 3), params.get('cfg', 1.0), params.get('shift', 5.0),
            "dpmpp_sde", "simple",
            params.get('width', 512), params.get('height', 768), params.get('length', 81), 1,
        ]
        # 9. WanVideoDecode
        vae_decode = graph.add_node('WanVideoDecode', [900, 100])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None},
        ]
        vae_decode.outputs = [{"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}]
        # 10. VHS_VideoCombine（视频输出，含音频）
        save = graph.add_node('VHS_VideoCombine', [1100, 100])
        save.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "audio", "type": "AUDIO", "link": None},
            {"name": "frame_rate", "type": "FLOAT", "link": None, "widget": {"name": "frame_rate"}},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "format", "type": "COMBO", "link": None, "widget": {"name": "format"}},
        ]
        save.outputs = []
        save.widgets_values = [params.get('fps', 16), "ComfyUI_DigitalHuman", "video/h264-mp4"]
        # === 连接 ===
        graph.connect(clip_vision_loader.id, 0, clip_vision_encode.id, 0)
        graph.connect(load_image.id, 0, clip_vision_encode.id, 1)
        graph.connect(load_image.id, 0, face_mask.id, 0)
        graph.connect(t5_loader.id, 0, pos_encode.id, 1)
        graph.connect(t5_loader.id, 0, neg_encode.id, 1)
        # 口型同步链路
        graph.connect(wav2vec_loader.id, 0, multitalk_model.id, 0)
        graph.connect(load_audio.id, 0, multitalk_embeds.id, 1)
        graph.connect(multitalk_model.id, 0, multitalk_embeds.id, 0)
        # 采样器链路
        graph.connect(model_loader.id, 0, sampler.id, 0)  # MODEL
        graph.connect(pos_encode.id, 0, sampler.id, 1)    # positive
        graph.connect(neg_encode.id, 0, sampler.id, 2)    # negative
        graph.connect(vae_loader.id, 0, sampler.id, 3)    # vae
        graph.connect(t5_loader.id, 0, sampler.id, 4)     # t5
        graph.connect(clip_vision_encode.id, 0, sampler.id, 5)  # clip_vision_output
        graph.connect(load_image.id, 0, sampler.id, 6)    # image
        graph.connect(sampler.id, 0, vae_decode.id, 0)
        graph.connect(vae_loader.id, 0, vae_decode.id, 1)
        graph.connect(vae_decode.id, 0, save.id, 0)
        graph.connect(load_audio.id, 0, save.id, 1)  # 音频输出到视频

    def _build_llm_text_task(self, graph: WorkflowGraph, requirement: dict):
        """构建 LLM 文本/图像编辑架构 - 基于 Qwen-image 等大语言模型的图像编辑

        参考"Qwen-image-Controlnet"和"QWEN-image标准图像编辑"工作流架构：
        - UNETLoader + CLIPLoader + VAELoader（Qwen-image 模型加载）
        - TextEncodeQwenImageEditPlus（Qwen 专用文本编码，支持编辑指令）
        - LoadImage + VAEEncode（输入图片编码为 latent）
        - KSampler + VAEDecode + SaveImage
        - 可选 ControlNetApplyAdvanced（姿态/深度控制）
        """
        params = requirement.get('parameters', {})
        family = self.target_model_family or 'Qwen-VL'
        # 1. UNETLoader
        unet_loader = graph.add_node('UNETLoader', [100, 100])
        unet_loader.inputs = [
            {"name": "unet_name", "type": "COMBO", "link": None, "widget": {"name": "unet_name"}},
            {"name": "weight_dtype", "type": "COMBO", "link": None, "widget": {"name": "weight_dtype"}},
        ]
        unet_loader.outputs = [{"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}]
        unet_loader.widgets_values = [
            self._pick_model('unet', family, self.library, self.object_info), "default"
        ]
        # 2. CLIPLoader（Qwen-image 专用 CLIP）
        clip_loader = graph.add_node('CLIPLoader', [100, 220])
        clip_loader.inputs = [
            {"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}},
            {"name": "type", "type": "COMBO", "link": None, "widget": {"name": "type"}},
        ]
        clip_loader.outputs = [{"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 0}]
        clip_loader.widgets_values = [self._pick_model('clip', family, self.library, self.object_info), "qwen_image"]
        # 3. VAELoader
        vae_loader = graph.add_node('VAELoader', [100, 340])
        vae_loader.inputs = [{"name": "vae_name", "type": "COMBO", "link": None, "widget": {"name": "vae_name"}}]
        vae_loader.outputs = [{"name": "VAE", "type": "VAE", "links": [], "slot_index": 0}]
        vae_loader.widgets_values = [self._pick_model('vae', family, self.library, self.object_info)]
        # 4. LoadImage + VAEEncode（输入图片编码为 latent）
        load_image = graph.add_node('LoadImage', [100, 460])
        load_image.inputs = [{"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}]
        load_image.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
        ]
        load_image.widgets_values = ["input_image.png"]
        vae_encode = graph.add_node('VAEEncode', [300, 460])
        vae_encode.inputs = [
            {"name": "pixels", "type": "IMAGE", "link": None},
            {"name": "vae", "type": "VAE", "link": None},
        ]
        vae_encode.outputs = [{"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}]
        # 5. TextEncodeQwenImageEditPlus（Qwen 专用编辑指令编码）
        pos_encode = graph.add_node('TextEncodeQwenImageEditPlus', [300, 100])
        pos_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        pos_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        pos_encode.widgets_values = [requirement.get('original', '编辑：增强画质')]
        neg_encode = graph.add_node('TextEncodeQwenImageEditPlus', [300, 220])
        neg_encode.inputs = [
            {"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}},
            {"name": "clip", "type": "CLIP", "link": None},
        ]
        neg_encode.outputs = [{"name": "CONDITIONING", "type": "CONDITIONING", "links": [], "slot_index": 0}]
        neg_encode.widgets_values = ["low quality, blurry"]
        # 6. KSampler
        sampler = graph.add_node('KSampler', [500, 200])
        self._init_ksampler(sampler, params, denoise=0.7)  # LLM编辑通常 denoise<1.0
        # 7. VAEDecode + SaveImage
        vae_decode = graph.add_node('VAEDecode', [700, 200])
        vae_decode.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "vae", "type": "VAE", "link": None},
        ]
        vae_decode.outputs = [{"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}]
        save = graph.add_node('SaveImage', [900, 200])
        save.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
        ]
        save.outputs = []
        save.widgets_values = ["ComfyUI_LLM_Edit"]
        # === 连接 ===
        graph.connect(clip_loader.id, 0, pos_encode.id, 1)
        graph.connect(clip_loader.id, 0, neg_encode.id, 1)
        graph.connect(load_image.id, 0, vae_encode.id, 0)
        graph.connect(vae_loader.id, 0, vae_encode.id, 1)
        graph.connect(unet_loader.id, 0, sampler.id, 0)
        graph.connect(pos_encode.id, 0, sampler.id, 6)
        graph.connect(neg_encode.id, 0, sampler.id, 7)
        graph.connect(vae_encode.id, 0, sampler.id, 8)
        graph.connect(sampler.id, 0, vae_decode.id, 0)
        graph.connect(vae_loader.id, 0, vae_decode.id, 1)
        graph.connect(vae_decode.id, 0, save.id, 0)

    def _build_tts_audio(self, graph: WorkflowGraph, requirement: dict):
        """构建 TTS 语音合成架构 - 基于参考音频克隆语音

        参考"INDEX TTS2"和"双人INDEX TTS2"工作流架构：
        - LoadAudio（参考音色音频）
        - IndexTTS2Run（核心 TTS 节点）
        - MultiLinePromptIndex（多行文本输入）
        - SaveAudioMP3（音频输出）
        """
        params = requirement.get('parameters', {})
        # 1. LoadAudio（参考音色）
        load_audio = graph.add_node('LoadAudio', [100, 100])
        load_audio.inputs = [{"name": "audio", "type": "STRING", "link": None, "widget": {"name": "audio"}}]
        load_audio.outputs = [{"name": "AUDIO", "type": "AUDIO", "links": [], "slot_index": 0}]
        load_audio.widgets_values = ["reference_voice.wav"]
        # 2. MultiLinePromptIndex（多行文本输入）
        prompt_node = graph.add_node('MultiLinePromptIndex', [300, 100])
        prompt_node.inputs = [{"name": "text", "type": "STRING", "link": None, "widget": {"name": "text"}}]
        prompt_node.outputs = [{"name": "STRING", "type": "STRING", "links": [], "slot_index": 0}]
        prompt_node.widgets_values = [requirement.get('original', '请输入要合成的文本')]
        # 3. IndexTTS2Run（核心 TTS 节点）
        tts_run = graph.add_node('IndexTTS2Run', [500, 100])
        tts_run.inputs = [
            {"name": "reference_audio", "type": "AUDIO", "link": None},
            {"name": "text", "type": "STRING", "link": None},
            {"name": "model", "type": "COMBO", "link": None, "widget": {"name": "model"}},
        ]
        tts_run.outputs = [{"name": "AUDIO", "type": "AUDIO", "links": [], "slot_index": 0}]
        tts_run.widgets_values = ["default"]
        # 4. SaveAudioMP3（音频输出）
        save = graph.add_node('SaveAudioMP3', [700, 100])
        save.inputs = [
            {"name": "audio", "type": "AUDIO", "link": None},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
        ]
        save.outputs = []
        save.widgets_values = ["ComfyUI_TTS"]
        # === 连接 ===
        graph.connect(load_audio.id, 0, tts_run.id, 0)
        graph.connect(prompt_node.id, 0, tts_run.id, 1)
        graph.connect(tts_run.id, 0, save.id, 0)

    def _init_ksampler(self, sampler_node, params: dict, denoise: float = 1.0):
        """辅助方法：初始化 KSampler 节点的 inputs 和 widgets_values"""
        sampler_node.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler_node.outputs = [{"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}]
        sampler_node.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20), params.get('cfg', 3.0),
            "euler", "simple", denoise
        ]

    def _find_node(self, graph: WorkflowGraph, node_type: str) -> Optional[WorkflowNode]:
        """查找图中指定类型的第一个节点"""
        for node in graph.nodes.values():
            if node.type == node_type:
                return node
        return None

    def _find_nodes(self, graph: WorkflowGraph, node_type: str) -> List[WorkflowNode]:
        """查找图中指定类型的所有节点"""
        return [n for n in graph.nodes.values() if n.type == node_type]

    def _remove_link(self, graph: WorkflowGraph, source_id: int, source_slot: int,
                     target_id: int, target_slot: int):
        """移除指定连接并清理inputs中的link"""
        graph.links = [
            link for link in graph.links
            if not (link[1] == source_id and link[2] == source_slot
                    and link[3] == target_id and link[4] == target_slot)
        ]
        target_node = graph.nodes.get(target_id)
        if target_node and target_slot < len(target_node.inputs):
            target_node.inputs[target_slot]['link'] = None
            input_name = target_node.inputs[target_slot].get('name', '')
            if input_name in target_node.connections:
                del target_node.connections[input_name]

    def _get_model_options(self, model_type: str) -> List[str]:
        """从资料库或object_info中获取可用模型列表"""
        # 优先从object_info中读取combo选项
        if model_type == 'lora':
            info = self.registry.get_node_info('LoraLoader')
            if info:
                lora_list = info.get('input', {}).get('required', {}).get('lora_name', [[]])[0]
                if isinstance(lora_list, list):
                    return lora_list
        elif model_type == 'controlnet':
            info = self.registry.get_node_info('ControlNetLoader')
            if info:
                cn_list = info.get('input', {}).get('required', {}).get('control_net_name', [[]])[0]
                if isinstance(cn_list, list):
                    return cn_list
        elif model_type == 'upscale':
            info = self.registry.get_node_info('UpscaleModelLoader')
            if info:
                up_list = info.get('input', {}).get('required', {}).get('model_name', [{}])[0]
                if isinstance(up_list, list):
                    return up_list
                opts = info.get('input', {}).get('required', {}).get('model_name', [{}])
                if len(opts) > 1 and isinstance(opts[1], dict):
                    return opts[1].get('options', [])
        elif model_type == 'checkpoint':
            info = self.registry.get_node_info('CheckpointLoaderSimple')
            if info:
                ckpt_list = info.get('input', {}).get('required', {}).get('ckpt_name', [[]])[0]
                if isinstance(ckpt_list, list):
                    return ckpt_list
        # 从资料库中汇总
        if self.library and 'workflows' in self.library:
            models = set()
            for wf in self.library['workflows'].values():
                wf_models = wf.get('models', {})
                if model_type in ('checkpoint', 'checkpoints'):
                    models.update(wf_models.get('checkpoints', []))
                elif model_type in wf_models:
                    models.update(wf_models.get(model_type, []))
            return list(models)
        return []

    def _pick_model(self, model_role: str, model_family: str,
                    library: dict = None, object_info: dict = None) -> str:
        """智能选择模型 - 强制与目标 model_family 一致

        Args:
            model_role: 'checkpoint'/'unet'/'lora'/'controlnet'/'vae'/'clip'/'upscale'
            model_family: 目标大模型系列（如 'Wan2.2'），模型必须属于该 family
            library: 工作流仓库字典（可选，用于按频率挑选候选）
            object_info: object_info 字典（可选，用于从 COMBO 选项中过滤）
        Returns:
            第一个通过 detect_model_family 验证的模型名；无可用时返回空字符串
        """
        lib = library if library is not None else self.library
        oi = object_info if object_info is not None else self.object_info

        # 步骤1：从 library 中收集 model_family 匹配工作流的候选，按出现频率排序
        if lib and 'workflows' in lib:
            freq_map = {}  # model_name -> count
            for wf in lib['workflows'].values():
                # 防御 library 错误归类：仅取 model_family 匹配的工作流
                wf_family = wf.get('model_family') or wf.get('family')
                if wf_family and model_family and wf_family != model_family:
                    continue
                wf_models = wf.get('models', {}) or {}
                # 适配多种 key 写法
                keys = [model_role]
                if model_role == 'checkpoint':
                    keys = ['checkpoint', 'checkpoints']
                elif model_role == 'unet':
                    keys = ['unet', 'unets']
                elif model_role == 'lora':
                    keys = ['lora', 'loras']
                elif model_role == 'controlnet':
                    keys = ['controlnet', 'controlnets']
                elif model_role == 'vae':
                    keys = ['vae', 'vaes']
                elif model_role == 'clip':
                    keys = ['clip', 'clips']
                elif model_role == 'upscale':
                    keys = ['upscale', 'upscales', 'upscale_model']
                for key in keys:
                    vals = wf_models.get(key, [])
                    if isinstance(vals, str):
                        vals = [vals]
                    if not isinstance(vals, list):
                        continue
                    for v in vals:
                        if isinstance(v, str) and v:
                            freq_map[v] = freq_map.get(v, 0) + 1
            # 按频率降序
            sorted_candidates = sorted(freq_map.items(), key=lambda x: -x[1])
            # 步骤2/3：对每个候选用 detect_model_family 验证，返回第一个一致者
            for candidate, _ in sorted_candidates:
                fam, _ = detect_model_family(candidate)
                if model_family and fam == model_family:
                    return candidate

        # 步骤4：library 无数据或全部不一致时，从 object_info 的 COMBO 选项中按 detect_model_family 过滤
        if oi:
            role_to_node = {
                'checkpoint': 'CheckpointLoaderSimple',
                'unet': 'UNETLoader',
                'lora': 'LoraLoader',
                'controlnet': 'ControlNetLoader',
                'vae': 'VAELoader',
                'clip': 'CLIPLoader',
                'upscale': 'UpscaleModelLoader',
            }
            role_to_widget = {
                'checkpoint': 'ckpt_name',
                'unet': 'unet_name',
                'lora': 'lora_name',
                'controlnet': 'control_net_name',
                'vae': 'vae_name',
                'clip': 'clip_name',
                'upscale': 'model_name',
            }
            node_type = role_to_node.get(model_role)
            widget_name = role_to_widget.get(model_role)
            if node_type and widget_name:
                node_info = oi.get(node_type, {}) or {}
                required = (node_info.get('input', {}) or {}).get('required', {}) or {}
                param_def = required.get(widget_name)
                if param_def and isinstance(param_def, list) and param_def:
                    options = param_def[0]
                    if isinstance(options, list):
                        for opt in options:
                            if isinstance(opt, str) and opt:
                                fam, _ = detect_model_family(opt)
                                if model_family and fam == model_family:
                                    return opt

        # 步骤5：两者都不可用，返回空字符串并告警
        print(f"[警告] _pick_model: 未找到与 model_family={model_family} 匹配的 {model_role} 模型")
        return ''

    def _add_lora(self, graph: WorkflowGraph, requirement: dict):
        """添加LoRA支持：在CheckpointLoaderSimple和KSampler之间插入LoraLoader"""
        loader = self._find_node(graph, 'CheckpointLoaderSimple')
        samplers = self._find_nodes(graph, 'KSampler')
        if not loader or not samplers:
            return

        # 选择 LoRA 模型（强制与 target_model_family 一致）
        lora_name = self._pick_model('lora', self.target_model_family, self.library, self.object_info)
        strength_model = requirement.get('lora_strength', 0.8)
        strength_clip = requirement.get('lora_clip_strength', 1.0)

        # 插入LoraLoader节点（放在loader右侧）
        lora_node = graph.add_node('LoraLoader', [loader.pos[0] + 250, loader.pos[1]])
        lora_node.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "clip", "type": "CLIP", "link": None},
            {"name": "lora_name", "type": "COMBO", "link": None, "widget": {"name": "lora_name"}},
            {"name": "strength_model", "type": "FLOAT", "link": None, "widget": {"name": "strength_model"}},
            {"name": "strength_clip", "type": "FLOAT", "link": None, "widget": {"name": "strength_clip"}}
        ]
        lora_node.outputs = [
            {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0},
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 1}
        ]
        lora_node.widgets_values = [lora_name, strength_model, strength_clip]

        # 重新布线：loader -> lora -> sampler
        for sampler in samplers:
            # 断开 loader MODEL -> sampler model
            self._remove_link(graph, loader.id, 0, sampler.id, 0)
            # 断开 loader CLIP -> sampler（通过CLIPTextEncode间接，这里不处理text encode）
            # 实际基础结构中 loader CLIP 连到 CLIPTextEncode，再由 encode 连到 sampler
            # 所以需要把 encode 的 clip 输入从 loader 改到 lora
            for node in graph.nodes.values():
                if node.type == 'CLIPTextEncode':
                    # 检查是否由 loader 提供 CLIP
                    if node.inputs[1].get('link') is not None:
                        # 找到连接到 node.inputs[1] 的源
                        for link in list(graph.links):
                            if link[3] == node.id and link[4] == 1:
                                if link[1] == loader.id:
                                    self._remove_link(graph, loader.id, 1, node.id, 1)
                                    graph.connect(lora_node.id, 1, node.id, 1)
                                    break
            graph.connect(lora_node.id, 0, sampler.id, 0)

        # lora 接收 loader 的 MODEL 和 CLIP
        graph.connect(loader.id, 0, lora_node.id, 0)
        graph.connect(loader.id, 1, lora_node.id, 1)

    def _add_controlnet(self, graph: WorkflowGraph, requirement: dict):
        """添加ControlNet支持：在CLIPTextEncode和KSampler之间插入ControlNetApplyAdvanced"""
        samplers = self._find_nodes(graph, 'KSampler')
        pos_encode = self._find_node(graph, 'CLIPTextEncode')
        if not samplers or not pos_encode:
            return

        # 查找负面编码节点（另一个CLIPTextEncode）
        neg_encode = None
        for node in graph.nodes.values():
            if node.type == 'CLIPTextEncode' and node.id != pos_encode.id:
                neg_encode = node
                break

        # 选择 ControlNet 模型（强制与 target_model_family 一致）
        cn_name = self._pick_model('controlnet', self.target_model_family, self.library, self.object_info)

        strength = requirement.get('controlnet_strength', 1.0)
        start_percent = requirement.get('controlnet_start', 0.0)
        end_percent = requirement.get('controlnet_end', 1.0)

        # 1. ControlNetLoader
        cn_loader = graph.add_node('ControlNetLoader', [pos_encode.pos[0] - 250, pos_encode.pos[1] - 80])
        cn_loader.inputs = [
            {"name": "control_net_name", "type": "COMBO", "link": None, "widget": {"name": "control_net_name"}}
        ]
        cn_loader.outputs = [
            {"name": "CONTROL_NET", "type": "CONTROL_NET", "links": [], "slot_index": 0}
        ]
        cn_loader.widgets_values = [cn_name]

        # 2. LoadImage（ControlNet输入图像）
        load_img = graph.add_node('LoadImage', [pos_encode.pos[0] - 250, pos_encode.pos[1] + 120])
        load_img.inputs = [
            {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
        ]
        load_img.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
        ]
        load_img.widgets_values = ["example.png"]

        # 3. ControlNetApplyAdvanced
        cn_apply = graph.add_node('ControlNetApplyAdvanced', [pos_encode.pos[0] + 120, pos_encode.pos[1] + 60])
        cn_apply.inputs = [
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "control_net", "type": "CONTROL_NET", "link": None},
            {"name": "image", "type": "IMAGE", "link": None},
            {"name": "strength", "type": "FLOAT", "link": None, "widget": {"name": "strength"}},
            {"name": "start_percent", "type": "FLOAT", "link": None, "widget": {"name": "start_percent"}},
            {"name": "end_percent", "type": "FLOAT", "link": None, "widget": {"name": "end_percent"}}
        ]
        cn_apply.outputs = [
            {"name": "positive", "type": "CONDITIONING", "links": [], "slot_index": 0},
            {"name": "negative", "type": "CONDITIONING", "links": [], "slot_index": 1}
        ]
        cn_apply.widgets_values = [strength, start_percent, end_percent]

        # 重新布线：将 sampler 的 positive/negative 从 encode 改为 cn_apply
        for sampler in samplers:
            # 断开 pos_encode -> sampler positive (slot 6)
            self._remove_link(graph, pos_encode.id, 0, sampler.id, 6)
            if neg_encode:
                self._remove_link(graph, neg_encode.id, 0, sampler.id, 7)
            # 连接 cn_apply -> sampler
            graph.connect(cn_apply.id, 0, sampler.id, 6)
            graph.connect(cn_apply.id, 1, sampler.id, 7)

        # 连接 encode -> cn_apply
        graph.connect(pos_encode.id, 0, cn_apply.id, 0)
        if neg_encode:
            graph.connect(neg_encode.id, 0, cn_apply.id, 1)
        # 连接 loader 和 image -> cn_apply
        graph.connect(cn_loader.id, 0, cn_apply.id, 2)
        graph.connect(load_img.id, 0, cn_apply.id, 3)

    def _add_ipadapter(self, graph: WorkflowGraph, requirement: dict):
        """添加IPAdapter支持（占位，需根据具体节点包实现）"""
        pass

    def _add_upscale_chain(self, graph: WorkflowGraph, requirement: dict):
        """添加放大链：在VAEDecode和SaveImage之间插入UpscaleModelLoader+ImageUpscaleWithModel"""
        vae_decode = self._find_node(graph, 'VAEDecode')
        save = self._find_node(graph, 'SaveImage')
        if not vae_decode or not save:
            return

        # 选择放大模型（强制与 target_model_family 一致）
        up_name = self._pick_model('upscale', self.target_model_family, self.library, self.object_info)

        # 1. UpscaleModelLoader
        up_loader = graph.add_node('UpscaleModelLoader', [vae_decode.pos[0] + 80, vae_decode.pos[1] - 100])
        up_loader.inputs = [
            {"name": "model_name", "type": "COMBO", "link": None, "widget": {"name": "model_name"}}
        ]
        up_loader.outputs = [
            {"name": "UPSCALE_MODEL", "type": "UPSCALE_MODEL", "links": [], "slot_index": 0}
        ]
        up_loader.widgets_values = [up_name]

        # 2. ImageUpscaleWithModel
        up_node = graph.add_node('ImageUpscaleWithModel', [vae_decode.pos[0] + 250, vae_decode.pos[1]])
        up_node.inputs = [
            {"name": "upscale_model", "type": "UPSCALE_MODEL", "link": None},
            {"name": "image", "type": "IMAGE", "link": None}
        ]
        up_node.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]

        # 重新布线：vae_decode -> up_node -> save
        self._remove_link(graph, vae_decode.id, 0, save.id, 1)
        graph.connect(vae_decode.id, 0, up_node.id, 1)
        graph.connect(up_loader.id, 0, up_node.id, 0)
        graph.connect(up_node.id, 0, save.id, 1)

    def _add_face_restore(self, graph: WorkflowGraph, requirement: dict):
        """添加人脸修复（占位，依赖ImpactPack等自定义节点）"""
        pass

    def _add_hires_fix(self, graph: WorkflowGraph, requirement: dict):
        """添加高清修复（双采样器）：KSampler -> VAEDecode 之间改为 KSampler1 -> LatentUpscale -> KSampler2 -> VAEDecode"""
        sampler_list = self._find_nodes(graph, 'KSampler')
        if not sampler_list:
            return
        sampler1 = sampler_list[0]
        vae_decode = self._find_node(graph, 'VAEDecode')
        if not vae_decode:
            return

        params = requirement.get('parameters', {})
        width = params.get('width', 512)
        height = params.get('height', 512)
        # hires 放大倍率
        scale = requirement.get('hires_scale', 2.0)
        hires_width = int(width * scale)
        hires_height = int(height * scale)

        # 找到sampler1之后、vae_decode之前的节点，断开 sampler1 -> vae_decode
        self._remove_link(graph, sampler1.id, 0, vae_decode.id, 0)

        # 1. LatentUpscale
        latent_up = graph.add_node('LatentUpscale', [sampler1.pos[0] + 200, sampler1.pos[1]])
        latent_up.inputs = [
            {"name": "samples", "type": "LATENT", "link": None},
            {"name": "upscale_method", "type": "COMBO", "link": None, "widget": {"name": "upscale_method"}},
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}}
        ]
        latent_up.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        latent_up.widgets_values = ["nearest-exact", hires_width, hires_height, "disabled"]

        # 2. 第二个KSampler（使用较低denoise进行精修）
        sampler2 = graph.add_node('KSampler', [sampler1.pos[0] + 450, sampler1.pos[1]])
        sampler2.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler2.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler2.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20),
            params.get('cfg', 8.0),
            "euler",
            "normal",
            0.5  # hires fix 通常使用较低denoise
        ]

        # 找到 sampler1 的 model/positive/negative 输入源并连接到 sampler2
        # model (slot 0)
        for link in graph.links:
            if link[3] == sampler1.id and link[4] == 0:
                graph.connect(link[1], link[2], sampler2.id, 0)
                break
        # positive (slot 6)
        for link in graph.links:
            if link[3] == sampler1.id and link[4] == 6:
                graph.connect(link[1], link[2], sampler2.id, 6)
                break
        # negative (slot 7)
        for link in graph.links:
            if link[3] == sampler1.id and link[4] == 7:
                graph.connect(link[1], link[2], sampler2.id, 7)
                break

        # 连接链路
        graph.connect(sampler1.id, 0, latent_up.id, 0)
        graph.connect(latent_up.id, 0, sampler2.id, 8)
        graph.connect(sampler2.id, 0, vae_decode.id, 0)

    def _add_detail_enhance(self, graph: WorkflowGraph, requirement: dict):
        """添加细节增强：在SaveImage前添加TilePreprocessor+ControlNet组合（简化占位）"""
        pass

    def _add_multi_sampler(self, graph: WorkflowGraph, requirement: dict):
        """添加多采样器串联：在第一个KSampler后追加第二个KSampler进行refine"""
        sampler_list = self._find_nodes(graph, 'KSampler')
        if len(sampler_list) < 1:
            return
        sampler1 = sampler_list[-1]  # 取最后一个采样器
        # 找到 sampler1 的输出目标（通常是VAEDecode或LatentUpscale）
        target_node = None
        target_slot = 0
        for link in graph.links:
            if link[1] == sampler1.id and link[2] == 0:
                target_node = graph.nodes.get(link[3])
                target_slot = link[4]
                break
        if not target_node:
            return

        params = requirement.get('parameters', {})
        # 插入第二个KSampler
        sampler2 = graph.add_node('KSampler', [sampler1.pos[0] + 250, sampler1.pos[1]])
        sampler2.inputs = [
            {"name": "model", "type": "MODEL", "link": None},
            {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
            {"name": "steps", "type": "INT", "link": None, "widget": {"name": "steps"}},
            {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
            {"name": "sampler_name", "type": "STRING", "link": None, "widget": {"name": "sampler_name"}},
            {"name": "scheduler", "type": "STRING", "link": None, "widget": {"name": "scheduler"}},
            {"name": "positive", "type": "CONDITIONING", "link": None},
            {"name": "negative", "type": "CONDITIONING", "link": None},
            {"name": "latent_image", "type": "LATENT", "link": None},
            {"name": "denoise", "type": "FLOAT", "link": None, "widget": {"name": "denoise"}}
        ]
        sampler2.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]
        sampler2.widgets_values = [
            params.get('seed', random.randint(0, 2**32)),
            params.get('steps', 20),
            params.get('cfg', 8.0),
            "euler",
            "normal",
            0.6
        ]

        # 复制 model/positive/negative 连接到 sampler2
        for link in graph.links:
            if link[3] == sampler1.id and link[4] == 0:
                graph.connect(link[1], link[2], sampler2.id, 0)
            if link[3] == sampler1.id and link[4] == 6:
                graph.connect(link[1], link[2], sampler2.id, 6)
            if link[3] == sampler1.id and link[4] == 7:
                graph.connect(link[1], link[2], sampler2.id, 7)

        # 断开 sampler1 -> target，改为 sampler1 -> sampler2 -> target
        self._remove_link(graph, sampler1.id, 0, target_node.id, target_slot)
        graph.connect(sampler1.id, 0, sampler2.id, 8)
        graph.connect(sampler2.id, 0, target_node.id, target_slot)

    def _add_complex_processing(self, graph: WorkflowGraph, requirement: dict):
        """添加复杂处理：当复杂度为complex时，自动叠加细节增强+多采样器"""
        # 自动叠加：先添加 hires_fix，再添加 multi_sampler，再添加 upscale_chain
        self._add_hires_fix(graph, requirement)
        self._add_multi_sampler(graph, requirement)
        self._add_upscale_chain(graph, requirement)

    # ==================================================================
    # lc.txt 六阶段架构 - 阶段1~3 方法（图像预处理 / 模型加载 / 提示词工程）
    # ==================================================================

    def _build_image_preprocessing(self, image_name, width, height):
        """构建阶段1图像预处理节点链（lc.txt 六阶段架构）

        节点序列: LoadImage → Image Resize → FaceDetailer → VAE Encode

        - Image Resize (WAS Node Suite): 目标尺寸由参数指定，lanczos 重采样
        - FaceDetailer (Impact Pack): bbox/face_yolov8m.pt 检测 + CodeFormer 修复(强度0.5)
        - VAE Encode: 将预处理图像转为 latent

        Returns: (nodes_list, links_list, output_node_id, output_slot)
            - nodes_list: WorkflowNode 列表（使用本地自增 id）
            - links_list: 内部连接元组列表 (source_id, source_slot, target_id, target_slot, link_type)
            - output_node_id / output_slot: 指向 VAE Encode 的 LATENT 输出

        外部需连接的输入（link=None，由调用方从阶段2/3接入）：
            - FaceDetailer.model        (MODEL)
            - FaceDetailer.clip_vision  (CLIP_VISION)
            - FaceDetailer.positive     (CONDITIONING)
            - FaceDetailer.negative     (CONDITIONING)
            - VAE Encode.vae            (VAE)
        """
        nodes = []
        links = []
        _id = [0]  # 本地自增 id 计数器

        def _new(node_type, pos):
            _id[0] += 1
            node = WorkflowNode(_id[0], node_type, pos)
            nodes.append(node)
            return node

        def _link(src, src_slot, tgt, tgt_slot, link_type):
            links.append((src.id, src_slot, tgt.id, tgt_slot, link_type))

        # --- 1. LoadImage ---
        load_image = _new('LoadImage', [100, 100])
        load_image.inputs = [
            {"name": "image", "type": "COMBO", "link": None, "widget": {"name": "image"}}
        ]
        load_image.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "MASK", "type": "MASK", "links": [], "slot_index": 1}
        ]
        load_image.widgets_values = [image_name]

        # --- 2. Image Resize (WAS Node Suite) ---
        # 目标尺寸 832×480(横屏)或 480×832(竖屏)，lanczos 重采样
        image_resize = _new('Image Resize', [300, 100])
        image_resize.inputs = [
            {"name": "image", "type": "IMAGE", "link": None},
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "interpolation", "type": "COMBO", "link": None, "widget": {"name": "interpolation"}},
            {"name": "method", "type": "COMBO", "link": None, "widget": {"name": "method"}},
        ]
        image_resize.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # widgets: [width, height, interpolation, method]
        image_resize.widgets_values = [width, height, "lanczos", "keep proportion"]

        # --- 3. UltralyticsDetectorProvider ---
        # 提供 BBOX_DETECTOR 输出（face_yolov8m.pt），供 FaceDetailer 使用
        detector = _new('UltralyticsDetectorProvider', [300, 300])
        detector.inputs = [
            {"name": "model_name", "type": "COMBO", "link": None, "widget": {"name": "model_name"}}
        ]
        detector.outputs = [
            {"name": "BBOX_DETECTOR", "type": "BBOX_DETECTOR", "links": [], "slot_index": 0},
            {"name": "SEGMENTATION", "type": "SEGMENTATION", "links": [], "slot_index": 1}
        ]
        detector.widgets_values = ["bbox/face_yolov8m.pt"]

        # --- 4. FaceDetailer (Impact Pack) ---
        # bbox/face_yolov8m.pt 检测 + CodeFormer 修复(强度0.5)
        face_detailer = _new('FaceDetailer', [500, 100])
        face_detailer.inputs = [
            {"name": "image", "type": "IMAGE", "link": None},               # slot 0 ← Image Resize
            {"name": "model", "type": "MODEL", "link": None},               # slot 1 ← 外部(阶段2 MODEL)
            {"name": "clip_vision", "type": "CLIP_VISION", "link": None},   # slot 2 ← 外部(阶段2 CLIP_VISION)
            {"name": "positive", "type": "CONDITIONING", "link": None},     # slot 3 ← 外部(阶段3 正面提示词)
            {"name": "negative", "type": "CONDITIONING", "link": None},     # slot 4 ← 外部(阶段3 负面提示词)
            {"name": "bbox_detector", "type": "BBOX_DETECTOR", "link": None},  # slot 5 ← UltralyticsDetectorProvider
            {"name": "sam_model_opt", "type": "SAM_MODEL", "link": None},   # slot 6 (可选，不连接)
        ]
        face_detailer.outputs = [
            {"name": "image", "type": "IMAGE", "links": [], "slot_index": 0},
            {"name": "mask", "type": "MASK", "links": [], "slot_index": 1},
        ]
        # FaceDetailer widgets（按 Impact Pack 标准顺序）
        face_detailer.widgets_values = [
            512,            # guide_size
            "bbox",         # guide_size_for
            1024,           # max_size
            random.randint(0, 2 ** 32),  # seed
            20,             # steps
            8,              # cfg
            "euler",        # sampler_name
            "normal",       # scheduler
            0.5,            # denoise
            5,              # feather
            True,           # noise_mask
            False,          # force_inpaint
            0.5,            # bbox_threshold
            10,             # bbox_dilation
            3,              # bbox_crop_factor
            "center-1",     # sam_detection_hint
            0,              # sam_dilation
            0.93,           # sam_threshold
            0,              # sam_bbox_expansion
            0.7,            # sam_mask_hint_threshold
            0,              # sam_mask_hint_expansion
            10,             # drop_size
            "",             # wildcards
            "CodeFormer",   # face_restore_model（lc.txt 要求 CodeFormer）
            "1",            # face_restore_order
            1.0,            # face_restore_visibility
            0.5,            # face_restore_weight（强度0.5）
        ]

        # --- 5. VAE Encode ---
        # 将 FaceDetailer 修复后的图像转为 latent
        vae_encode = _new('VAEEncode', [700, 100])
        vae_encode.inputs = [
            {"name": "pixels", "type": "IMAGE", "link": None},   # slot 0 ← FaceDetailer.image
            {"name": "vae", "type": "VAE", "link": None},        # slot 1 ← 外部(阶段2 VAE)
        ]
        vae_encode.outputs = [
            {"name": "LATENT", "type": "LATENT", "links": [], "slot_index": 0}
        ]

        # --- 内部连接 ---
        _link(load_image, 0, image_resize, 0, "IMAGE")          # LoadImage.IMAGE → Image Resize.image
        _link(image_resize, 0, face_detailer, 0, "IMAGE")       # Image Resize.IMAGE → FaceDetailer.image
        _link(detector, 0, face_detailer, 5, "BBOX_DETECTOR")   # Detector.BBOX_DETECTOR → FaceDetailer.bbox_detector
        _link(face_detailer, 0, vae_encode, 0, "IMAGE")         # FaceDetailer.image → VAE Encode.pixels

        # 禁止将原始 LoadImage 输出直接连接到采样器 —— 预处理链最终输出是 VAE Encode 的 latent
        return (nodes, links, vae_encode.id, 0)

    def _build_model_loading(self, model_family="wan22", architecture_scheme="single",
                             blocks_to_swap=20, attention_mode="sdpa", base_precision="bf16",
                             high_lora_strength=1.0, low_lora_strength=1.0):
        """构建阶段2模型加载节点（V19验证成功架构，动态架构选择）

        【V19架构变更】替换旧的 UNETLoader 为完整 V19 节点链：
        WanVideoBlockSwap（共享配置） → WanVideoModelLoader → WanVideoSetBlockSwap →
        WanVideoLoraSelect → WanVideoSetLoRAs

        架构方案根据预检环节用户选择动态决定：
        - 方案A（生产环境推荐，architecture_scheme="dual_serial"）：
          HIGH+LOW 双模型链。HIGH 模型用于高噪声阶段（start_step=0, end_step=split_step），
          LOW 模型用于低噪声阶段（start_step=split_step, end_step=-1），两个 WanVideoSampler 串行。
        - 方案B（简单场景，architecture_scheme="single"）：
          单一 HIGH 模型链，单个 WanVideoSampler 全程采样。

        V19关键参数（默认值，可由 blocks_to_swap/attention_mode/base_precision/high_lora_strength 覆盖）：
        - base_precision="bf16", quantization="fp8_e4m3fn_scaled", attention_mode="sdpa"
          （sageattn 与本机 PyTorch 2.9.1+cu128 不兼容，强制 sdpa，见 SKILL.md 4.11.1）
        - BLOCKS_TO_SWAP=20（C8 验证推荐值，38 会导致专用显存闲置）
        - lightx2v LoRA: HIGH strength=1.0（C5 v14 官方推荐）, LOW strength=1.0, merge_loras=False
        - VAE="Wan2_1_VAE_bf16.safetensors" (precision="bf16")
        - T5="umt5-xxl-enc-fp8_e4m3fn.safetensors" (precision="bf16", load_device="offload_device")

        Args:
            model_family: 模型系列，默认 "wan22"
            architecture_scheme: 架构方案，"dual_serial"(方案A) 或 "single"(方案B)

        Returns: (nodes_list, links_list, ids_dict)
            ids_dict 包含:
            - model_id: 主模型 id（方案A指向 HIGH WanVideoSetLoRAs，供 FaceDetailer 共用；方案B指向单一链）
            - model_high_id: HIGH 链 WanVideoSetLoRAs 输出 id
            - model_low_id: LOW 链 WanVideoSetLoRAs 输出 id（方案B与 high_id 相同）
            - vae_id: WanVideoVAELoader 输出 id
            - clip_id: LoadWanVideoT5TextEncoder 输出 id（T5，供 WanVideoTextEncode 使用）
            - clip_vision_id: CLIPVisionLoader 输出 id
            - block_swap_id: WanVideoBlockSwap 配置节点 id（共享）
        """
        # 规范化 model_family 别名
        fam_key = (model_family or "wan22").lower().replace(".", "").replace("-", "").replace("_", "")
        # V19 模型文件名映射（验证成功配置）
        model_specs = {
            "wan22": {
                # 方案A: HIGH+LOW 双模型（V19验证成功）
                "diffusion_high": "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors",
                "diffusion_low": "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors",
                # 方案B: 单一 HIGH 模型
                "diffusion_single": "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors",
                # V19 验证成功的模型配置
                "vae": "Wan2_1_VAE_bf16.safetensors",
                "t5": "umt5-xxl-enc-fp8_e4m3fn.safetensors",
                "clip_vision": "clip_vision_h.safetensors",
                # lightx2v 加速 LoRA
                "accel_lora": "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors",
            },
        }
        spec = model_specs.get(fam_key)
        if spec is None:
            print(f"[警告] _build_model_loading: 未知 model_family={model_family!r}，回退到 Wan2.2")
            spec = model_specs["wan22"]

        # 关键参数：可由预检自适应参数覆盖；默认值对齐 C8 / UPGRADE-NOTES 验证结论
        # （blocks_to_swap=20：C8 验证 L3 档推荐值，38 会导致专用显存闲置；
        #   high_lora_strength=1.0：C5 v14 验证官方推荐，3.0 破坏 MoE 去噪曲线）
        BLOCKS_TO_SWAP = blocks_to_swap
        HIGH_LORA_STRENGTH = high_lora_strength
        LOW_LORA_STRENGTH = low_lora_strength

        nodes = []
        links = []
        _id = [0]

        def _new(node_type, pos):
            _id[0] += 1
            node = WorkflowNode(_id[0], node_type, pos)
            nodes.append(node)
            return node

        def _link(src, src_slot, tgt, tgt_slot, link_type):
            links.append((src.id, src_slot, tgt.id, tgt_slot, link_type))

        is_dual = (architecture_scheme == "dual_serial")

        # === V19: WanVideoBlockSwap 共享配置节点 ===
        block_swap = _new('WanVideoBlockSwap', [50, 100])
        block_swap.inputs = []
        block_swap.outputs = [
            {"name": "BLOCK_SWAP_ARGS", "type": "BLOCK_SWAP_ARGS", "links": [], "slot_index": 0}
        ]
        block_swap.widgets_values = [
            BLOCKS_TO_SWAP,   # blocks_to_swap=38（V19验证值）
            True,             # offload_img_emb
            True,             # offload_txt_emb
            0,                # vace_blocks_to_swap
            0,                # prefetch_blocks
            False,            # block_swap_debug
        ]

        def _build_model_chain(model_name, lora_strength, pos):
            """构建 V19 模型链: WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoLoraSelect → WanVideoSetLoRAs

            返回 WanVideoSetLoRAs 节点（其输出 MODEL 供 WanVideoSampler 使用）
            """
            # 1. WanVideoModelLoader
            loader = _new('WanVideoModelLoader', pos)
            loader.inputs = []
            loader.outputs = [
                {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
            ]
            loader.widgets_values = [
                model_name,                # model
                base_precision,            # base_precision（默认 bf16）
                "fp8_e4m3fn_scaled",       # quantization
                "offload_device",          # load_device
                attention_mode,            # attention_mode（默认 sdpa，sageattn 与本机 PyTorch 不兼容）
                "default",                 # rms_norm_function
                None,                      # lora（通过 WanVideoSetLoRAs 单独设置）
                None,                      # block_swap_args（通过 WanVideoSetBlockSwap 单独设置）
            ]

            # 2. WanVideoSetBlockSwap
            set_bs = _new('WanVideoSetBlockSwap', [pos[0] + 200, pos[1]])
            set_bs.inputs = [
                {"name": "model", "type": "MODEL", "link": None},                       # slot 0 ← WanVideoModelLoader
                {"name": "block_swap_args", "type": "BLOCK_SWAP_ARGS", "link": None},   # slot 1 ← WanVideoBlockSwap
            ]
            set_bs.outputs = [
                {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
            ]
            set_bs.widgets_values = []

            # 3. WanVideoLoraSelect
            lora_select = _new('WanVideoLoraSelect', [pos[0] + 400, pos[1]])
            lora_select.inputs = []
            lora_select.outputs = [
                {"name": "LORA", "type": "WANVIDLORA", "links": [], "slot_index": 0}
            ]
            lora_select.widgets_values = [
                spec["accel_lora"],   # lora: lightx2v 加速LoRA
                lora_strength,        # strength: HIGH=3, LOW=1
                False,                # low_mem_load
                False,                # merge_loras（V19验证值）
            ]

            # 4. WanVideoSetLoRAs
            set_lora = _new('WanVideoSetLoRAs', [pos[0] + 600, pos[1]])
            set_lora.inputs = [
                {"name": "model", "type": "MODEL", "link": None},           # slot 0 ← WanVideoSetBlockSwap
                {"name": "lora", "type": "WANVIDLORA", "link": None},       # slot 1 ← WanVideoLoraSelect
            ]
            set_lora.outputs = [
                {"name": "MODEL", "type": "MODEL", "links": [], "slot_index": 0}
            ]
            set_lora.widgets_values = []

            # 内部连接
            _link(loader, 0, set_bs, 0, "MODEL")                # ModelLoader → SetBlockSwap
            _link(block_swap, 0, set_bs, 1, "BLOCK_SWAP_ARGS")  # BlockSwap配置 → SetBlockSwap
            _link(set_bs, 0, set_lora, 0, "MODEL")              # SetBlockSwap → SetLoRAs
            _link(lora_select, 0, set_lora, 1, "WANVIDLORA")    # LoraSelect → SetLoRAs

            return set_lora

        if is_dual:
            # === 方案A: HIGH + LOW 双模型链 ===
            high_chain = _build_model_chain(spec["diffusion_high"], HIGH_LORA_STRENGTH, [100, 200])
            low_chain = _build_model_chain(spec["diffusion_low"], LOW_LORA_STRENGTH, [100, 400])
            high_id = high_chain.id
            low_id = low_chain.id
        else:
            # === 方案B: 单一 HIGH 模型链 ===
            single_chain = _build_model_chain(spec["diffusion_single"], HIGH_LORA_STRENGTH, [100, 200])
            high_id = single_chain.id
            low_id = single_chain.id

        # === V19: WanVideoVAELoader（precision="bf16"）===
        vae_loader = _new('WanVideoVAELoader', [100, 600])
        vae_loader.inputs = [
            {"name": "model_name", "type": "COMBO", "link": None, "widget": {"name": "model_name"}},
            {"name": "precision", "type": "COMBO", "link": None, "widget": {"name": "precision"}},
        ]
        vae_loader.outputs = [
            {"name": "VAE", "type": "VAE", "links": [], "slot_index": 0}
        ]
        vae_loader.widgets_values = [spec["vae"], "bf16"]

        # === V19: LoadWanVideoT5TextEncoder（替换旧 CLIPLoader）===
        # T5 文本编码器（供 WanVideoTextEncode 使用），precision="bf16", load_device="offload_device"
        t5_loader = _new('LoadWanVideoT5TextEncoder', [100, 700])
        t5_loader.inputs = [
            {"name": "model_name", "type": "COMBO", "link": None, "widget": {"name": "model_name"}},
            {"name": "precision", "type": "COMBO", "link": None, "widget": {"name": "precision"}},
            {"name": "load_device", "type": "COMBO", "link": None, "widget": {"name": "load_device"}},
            {"name": "quantization", "type": "COMBO", "link": None, "widget": {"name": "quantization"}},
        ]
        t5_loader.outputs = [
            {"name": "T5", "type": "T5", "links": [], "slot_index": 0}
        ]
        t5_loader.widgets_values = [
            spec["t5"],             # model_name: umt5-xxl-enc-fp8_e4m3fn
            "bf16",                 # precision
            "offload_device",       # load_device
            "disabled",             # quantization
        ]

        # === CLIPVisionLoader（保持不变，供 WanVideoClipVisionEncode 使用）===
        clip_vision_loader = _new('CLIPVisionLoader', [100, 800])
        clip_vision_loader.inputs = [
            {"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}}
        ]
        clip_vision_loader.outputs = [
            {"name": "CLIP_VISION", "type": "CLIP_VISION", "links": [], "slot_index": 0}
        ]
        clip_vision_loader.widgets_values = [spec["clip_vision"]]

        # === CLIPLoader（legacy，供 FaceDetailer 的 CLIPTextEncode 使用）===
        # V19架构使用T5进行文本编码（WanVideoTextEncode），但 _build_image_preprocessing
        # 中的 FaceDetailer 仍需 CLIP-based CONDITIONING 输入。此处加载 CLIP 供
        # CLIPTextEncode 使用，与 V19 的 T5 路径并行存在。
        clip_legacy_loader = _new('CLIPLoader', [100, 900])
        clip_legacy_loader.inputs = [
            {"name": "clip_name", "type": "COMBO", "link": None, "widget": {"name": "clip_name"}},
            {"name": "type", "type": "COMBO", "link": None, "widget": {"name": "type"}},
        ]
        clip_legacy_loader.outputs = [
            {"name": "CLIP", "type": "CLIP", "links": [], "slot_index": 0}
        ]
        clip_legacy_loader.widgets_values = [spec["t5"], "wan"]

        ids = {
            "model_id": high_id,          # 主模型（供 FaceDetailer 等共用，方案A指向 HIGH）
            "model_high_id": high_id,     # HIGH 链 WanVideoSetLoRAs 输出
            "model_low_id": low_id,       # LOW 链 WanVideoSetLoRAs 输出（方案B与 high_id 相同）
            "vae_id": vae_loader.id,
            "clip_id": t5_loader.id,      # T5 文本编码器（供 WanVideoTextEncode 使用）
            "clip_legacy_id": clip_legacy_loader.id,  # Legacy CLIP（供 FaceDetailer 的 CLIPTextEncode 使用）
            "clip_vision_id": clip_vision_loader.id,
            "block_swap_id": block_swap.id,  # V19新增: BlockSwap 配置节点（共享）
        }
        return (nodes, links, ids)

    def _structure_prompt(self, user_prompt, ratio="9:16"):
        """将用户白话提示词转换为三段式结构化提示词（lc.txt 阶段3）

        三段式结构:
            [画质前缀], [镜头语言], [场景描述].
            [主体详细外观], [主体状态].
            [精确的时序动作描述], 动作缓慢连贯, 无突变, 稳定清晰.

        动作描述包含"缓慢""轻微""连贯"控制词，确保单一小幅度确定性动作。
        禁止直接使用用户白话作为提示词（必须结构化转换）。

        Args:
            user_prompt: 用户白话提示词
            ratio: 画面比例（"9:16"竖屏 / "16:9"横屏 / "1:1"方形）

        Returns: structured_prompt_string
        """
        # --- 第一段：画质前缀 + 镜头语言 + 场景描述 ---
        quality_prefix = "masterpiece, best quality, 8k, highly detailed"

        # 镜头语言根据比例选择（固定机位是视频稳定的关键约束）
        ratio_norm = ratio.lower().replace("/", ":").strip()
        if ratio_norm in ("9:16", "9:16portrait", "portrait"):
            camera_lang = "固定机位, 特写镜头, 干净纯色背景"
        elif ratio_norm in ("16:9", "16:9landscape", "landscape"):
            camera_lang = "固定机位, 广角镜头, 干净背景"
        else:
            camera_lang = "固定机位, 中景镜头, 干净背景"

        # 场景描述：从用户提示词提取（去除常见画质关键词避免重复）
        _quality_keywords = re.compile(
            r"(masterpiece|best quality|high quality|8k|4k|hd|ultra?\s*detailed|highly detailed|高清|高质量|超清)",
            re.IGNORECASE,
        )
        scene_desc = _quality_keywords.sub("", user_prompt or "").strip(" ,，。.")
        if not scene_desc:
            scene_desc = "一个人物面对镜头站立"

        # --- 第二段：主体详细外观 + 主体状态 ---
        # 默认主体外观描述（用户提示词已融入场景描述，此处补充状态）
        subject_appearance = "主体外观清晰完整, 五官端正"
        subject_state = "表情平静, 面对镜头站立"

        # --- 第三段：精确时序动作描述 + 控制词 ---
        # 单一小幅度确定性动作，包含"缓慢""轻微""连贯"控制词
        action_desc = "主体缓慢将头部从侧面轻微转向正前方, 动作连贯流畅"
        control_words = "动作缓慢连贯, 无突变, 稳定清晰"

        # 组装三段式结构化提示词
        structured = (
            f"{quality_prefix}, {camera_lang}, {scene_desc}. "
            f"{subject_appearance}, {subject_state}. "
            f"{action_desc}, {control_words}."
        )
        return structured

    # ==================================================================
    # lc.txt 六阶段架构 - 阶段4~6 方法（核心生成 / 初级合成 / 后处理提升）
    # ==================================================================

    def _build_core_generation(self, image_embeds_node_id, image_embeds_slot,
                                text_embeds_node_id, text_embeds_slot,
                                model_high_node_id, model_high_slot,
                                model_low_node_id, model_low_slot,
                                architecture_scheme="single",
                                steps=8, seed=12345, split_step=None):
        """构建阶段4核心生成节点（V19验证成功架构，动态架构选择）

        【V19架构变更】完全重写为V19架构：
        - 替换废弃节点名 "WanVideo I2V Sampler (img2vid)" → "WanVideoSampler"
        - 创建 INTConstant (steps) 和 INTConstant (split_step) 节点
        - 创建 CreateCFGScheduleFloatList 节点（动态CFG调度[2,1,1,1,1,1]）
        - WanVideoSampler 输入为 model/image_embeds/text_embeds/steps/cfg，不是 latent/positive/negative

        架构方案：
        - 方案A（dual_serial）: HIGH采样器(start_step=0, end_step=split_step, cfg=动态调度)
          + LOW采样器(start_step=split_step, end_step=-1, cfg=1固定, samples=HIGH输出)
        - 方案B（single）: 单一采样器(start_step=0, end_step=-1, cfg=动态调度)

        V19关键参数：
        - steps=8, split_step=4 (HIGH处理0-4步, LOW处理4-8步)
        - CFG动态调度: CreateCFGScheduleFloatList 生成[2,1,1,1,1,1]
        - LOW sampler固定CFG=1
        - shift=8.0, scheduler="dpm++_sde", rope_function="comfy_chunked"
        - denoise_strength=1.0, force_offload=True, riflex_freq_index=0

        Args:
            image_embeds_node_id/slot: WanVideoImageToVideoEncode 的 image_embeds 输出
            text_embeds_node_id/slot: WanVideoTextEncode 的 text_embeds 输出
            model_high_node_id/slot: 阶段2 HIGH 链 WanVideoSetLoRAs 的 MODEL 输出
            model_low_node_id/slot: 阶段2 LOW 链 WanVideoSetLoRAs 的 MODEL 输出
            architecture_scheme: "dual_serial"(方案A) 或 "single"(方案B)
            steps: 采样步数，默认8（V19验证值）
            seed: 随机种子

        Returns: (nodes_list, links_list, output_node_id, output_slot)
            output指向最终 WanVideoSampler 的 LATENT 输出
        """
        # V19 关键参数
        # split_step 优先使用预检自适应参数（硬件分档），未提供时回退 steps//2
        SPLIT_STEP = split_step if split_step is not None else steps // 2
        SHIFT = 8.0
        LOW_CFG = 1  # LOW sampler固定CFG=1
        # CFG调度参数（V19验证配置：第一步CFG=2，其余CFG=1）
        CFG_SCALE_START = 2
        CFG_SCALE_END = 2
        CFG_START_PERCENT = 0.0
        CFG_END_PERCENT = 0.01

        nodes = []
        links = []
        _id = [0]

        def _new(node_type, pos):
            _id[0] += 1
            node = WorkflowNode(_id[0], node_type, pos)
            nodes.append(node)
            return node

        def _ext_link(ext_node_id, ext_slot, tgt, tgt_slot, link_type):
            links.append((ext_node_id, ext_slot, tgt.id, tgt_slot, link_type))

        def _link(src, src_slot, tgt, tgt_slot, link_type):
            links.append((src.id, src_slot, tgt.id, tgt_slot, link_type))

        is_dual = (architecture_scheme == "dual_serial")

        # === V19: INTConstant - Steps ===
        steps_const = _new('INTConstant', [700, 100])
        steps_const.inputs = [
            {"name": "value", "type": "INT", "link": None, "widget": {"name": "value"}}
        ]
        steps_const.outputs = [
            {"name": "INT", "type": "INT", "links": [], "slot_index": 0}
        ]
        steps_const.widgets_values = [steps]

        # === V19: CreateCFGScheduleFloatList - 动态CFG调度 ===
        # 生成[2,1,1,1,1,1]（第一步CFG=2，其余CFG=1）
        cfg_schedule = _new('CreateCFGScheduleFloatList', [700, 200])
        cfg_schedule.inputs = [
            {"name": "steps", "type": "INT", "link": None},                                      # slot 0 ← INTConstant
            {"name": "cfg_scale_start", "type": "FLOAT", "link": None, "widget": {"name": "cfg_scale_start"}},
            {"name": "cfg_scale_end", "type": "FLOAT", "link": None, "widget": {"name": "cfg_scale_end"}},
            {"name": "interpolation", "type": "COMBO", "link": None, "widget": {"name": "interpolation"}},
            {"name": "start_percent", "type": "FLOAT", "link": None, "widget": {"name": "start_percent"}},
            {"name": "end_percent", "type": "FLOAT", "link": None, "widget": {"name": "end_percent"}},
        ]
        cfg_schedule.outputs = [
            {"name": "FLOAT", "type": "FLOAT", "links": [], "slot_index": 0}
        ]
        cfg_schedule.widgets_values = [
            CFG_SCALE_START,    # cfg_scale_start=2
            CFG_SCALE_END,      # cfg_scale_end=2
            "linear",           # interpolation
            CFG_START_PERCENT,  # start_percent=0.0
            CFG_END_PERCENT,    # end_percent=0.01（只在第一步应用CFG=2）
        ]
        # 内部连接: INTConstant(steps) → CreateCFGScheduleFloatList.steps
        _link(steps_const, 0, cfg_schedule, 0, "INT")

        if is_dual:
            # === V19: INTConstant - Split_step（仅方案A需要） ===
            split_const = _new('INTConstant', [700, 300])
            split_const.inputs = [
                {"name": "value", "type": "INT", "link": None, "widget": {"name": "value"}}
            ]
            split_const.outputs = [
                {"name": "INT", "type": "INT", "links": [], "slot_index": 0}
            ]
            split_const.widgets_values = [SPLIT_STEP]

            # === 方案A: HIGH + LOW 双 WanVideoSampler 串行 ===

            # --- HIGH采样器（前split_step步） ---
            sampler_high = _new('WanVideoSampler', [800, 250])
            sampler_high.inputs = [
                {"name": "model", "type": "MODEL", "link": None},                        # slot 0 ← HIGH WanVideoSetLoRAs
                {"name": "image_embeds", "type": "IMAGE_EMBEDS", "link": None},          # slot 1 ← WanVideoImageToVideoEncode
                {"name": "text_embeds", "type": "TEXT_EMBEDS", "link": None},            # slot 2 ← WanVideoTextEncode
                {"name": "steps", "type": "INT", "link": None},                          # slot 3 ← INTConstant(steps)
                {"name": "cfg", "type": "FLOAT", "link": None},                          # slot 4 ← CreateCFGScheduleFloatList
                {"name": "shift", "type": "FLOAT", "link": None, "widget": {"name": "shift"}},
                {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
                {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
                {"name": "scheduler", "type": "COMBO", "link": None, "widget": {"name": "scheduler"}},
                {"name": "riflex_freq_index", "type": "INT", "link": None, "widget": {"name": "riflex_freq_index"}},
                {"name": "denoise_strength", "type": "FLOAT", "link": None, "widget": {"name": "denoise_strength"}},
                {"name": "start_step", "type": "INT", "link": None, "widget": {"name": "start_step"}},
                {"name": "end_step", "type": "INT", "link": None},                       # slot 12 ← INTConstant(split_step)
                {"name": "rope_function", "type": "COMBO", "link": None, "widget": {"name": "rope_function"}},
            ]
            sampler_high.outputs = [
                {"name": "latents", "type": "LATENT", "links": [], "slot_index": 0}
            ]
            sampler_high.widgets_values = [
                SHIFT,                    # shift=8.0
                seed,                     # seed
                True,                     # force_offload
                "dpm++_sde",              # scheduler
                0,                        # riflex_freq_index
                1.0,                      # denoise_strength
                0,                        # start_step=0（HIGH从第0步开始）
                "comfy_chunked",          # rope_function
            ]
            # 外部连接: model(HIGH) / image_embeds / text_embeds
            _ext_link(model_high_node_id, model_high_slot, sampler_high, 0, "MODEL")
            _ext_link(image_embeds_node_id, image_embeds_slot, sampler_high, 1, "IMAGE_EMBEDS")
            _ext_link(text_embeds_node_id, text_embeds_slot, sampler_high, 2, "TEXT_EMBEDS")
            # 内部连接: steps / cfg / end_step(split_step)
            _link(steps_const, 0, sampler_high, 3, "INT")
            _link(cfg_schedule, 0, sampler_high, 4, "FLOAT")
            _link(split_const, 0, sampler_high, 12, "INT")

            # --- LOW采样器（后split_step~end步） ---
            sampler_low = _new('WanVideoSampler', [800, 500])
            sampler_low.inputs = [
                {"name": "model", "type": "MODEL", "link": None},                        # slot 0 ← LOW WanVideoSetLoRAs
                {"name": "image_embeds", "type": "IMAGE_EMBEDS", "link": None},          # slot 1 ← WanVideoImageToVideoEncode
                {"name": "text_embeds", "type": "TEXT_EMBEDS", "link": None},            # slot 2 ← WanVideoTextEncode
                {"name": "steps", "type": "INT", "link": None},                          # slot 3 ← INTConstant(steps)
                {"name": "cfg", "type": "FLOAT", "link": None, "widget": {"name": "cfg"}},
                {"name": "shift", "type": "FLOAT", "link": None, "widget": {"name": "shift"}},
                {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
                {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
                {"name": "scheduler", "type": "COMBO", "link": None, "widget": {"name": "scheduler"}},
                {"name": "riflex_freq_index", "type": "INT", "link": None, "widget": {"name": "riflex_freq_index"}},
                {"name": "samples", "type": "LATENT", "link": None},                     # slot 10 ← HIGH sampler输出
                {"name": "denoise_strength", "type": "FLOAT", "link": None, "widget": {"name": "denoise_strength"}},
                {"name": "start_step", "type": "INT", "link": None},                     # slot 12 ← INTConstant(split_step)
                {"name": "end_step", "type": "INT", "link": None, "widget": {"name": "end_step"}},
                {"name": "add_noise_to_samples", "type": "BOOLEAN", "link": None, "widget": {"name": "add_noise_to_samples"}},
                {"name": "rope_function", "type": "COMBO", "link": None, "widget": {"name": "rope_function"}},
            ]
            sampler_low.outputs = [
                {"name": "latents", "type": "LATENT", "links": [], "slot_index": 0}
            ]
            sampler_low.widgets_values = [
                LOW_CFG,                  # cfg=1（LOW固定CFG=1）
                SHIFT,                    # shift=8.0
                seed,                     # seed
                True,                     # force_offload
                "dpm++_sde",              # scheduler
                0,                        # riflex_freq_index
                1.0,                      # denoise_strength
                -1,                       # end_step=-1（LOW到最后）
                False,                    # add_noise_to_samples=False
                "comfy_chunked",          # rope_function
            ]
            # 外部连接: model(LOW) / image_embeds / text_embeds
            _ext_link(model_low_node_id, model_low_slot, sampler_low, 0, "MODEL")
            _ext_link(image_embeds_node_id, image_embeds_slot, sampler_low, 1, "IMAGE_EMBEDS")
            _ext_link(text_embeds_node_id, text_embeds_slot, sampler_low, 2, "TEXT_EMBEDS")
            # 内部连接: steps / start_step(split_step) / samples(HIGH输出)
            _link(steps_const, 0, sampler_low, 3, "INT")
            _link(split_const, 0, sampler_low, 12, "INT")
            _link(sampler_high, 0, sampler_low, 10, "LATENT")

            # 输出指向 LOW 采样器的 latents 输出（slot 0）
            return (nodes, links, sampler_low.id, 0)
        else:
            # === 方案B: 单一 WanVideoSampler ===
            sampler = _new('WanVideoSampler', [800, 300])
            sampler.inputs = [
                {"name": "model", "type": "MODEL", "link": None},                        # slot 0 ← WanVideoSetLoRAs
                {"name": "image_embeds", "type": "IMAGE_EMBEDS", "link": None},          # slot 1 ← WanVideoImageToVideoEncode
                {"name": "text_embeds", "type": "TEXT_EMBEDS", "link": None},            # slot 2 ← WanVideoTextEncode
                {"name": "steps", "type": "INT", "link": None},                          # slot 3 ← INTConstant(steps)
                {"name": "cfg", "type": "FLOAT", "link": None},                          # slot 4 ← CreateCFGScheduleFloatList
                {"name": "shift", "type": "FLOAT", "link": None, "widget": {"name": "shift"}},
                {"name": "seed", "type": "INT", "link": None, "widget": {"name": "seed"}},
                {"name": "force_offload", "type": "BOOLEAN", "link": None, "widget": {"name": "force_offload"}},
                {"name": "scheduler", "type": "COMBO", "link": None, "widget": {"name": "scheduler"}},
                {"name": "riflex_freq_index", "type": "INT", "link": None, "widget": {"name": "riflex_freq_index"}},
                {"name": "denoise_strength", "type": "FLOAT", "link": None, "widget": {"name": "denoise_strength"}},
                {"name": "start_step", "type": "INT", "link": None, "widget": {"name": "start_step"}},
                {"name": "end_step", "type": "INT", "link": None, "widget": {"name": "end_step"}},
                {"name": "rope_function", "type": "COMBO", "link": None, "widget": {"name": "rope_function"}},
            ]
            sampler.outputs = [
                {"name": "latents", "type": "LATENT", "links": [], "slot_index": 0}
            ]
            sampler.widgets_values = [
                SHIFT,                    # shift=8.0
                seed,                     # seed
                True,                     # force_offload
                "dpm++_sde",              # scheduler
                0,                        # riflex_freq_index
                1.0,                      # denoise_strength
                0,                        # start_step=0
                -1,                       # end_step=-1（全程采样）
                "comfy_chunked",          # rope_function
            ]
            # 外部连接: model / image_embeds / text_embeds
            _ext_link(model_high_node_id, model_high_slot, sampler, 0, "MODEL")
            _ext_link(image_embeds_node_id, image_embeds_slot, sampler, 1, "IMAGE_EMBEDS")
            _ext_link(text_embeds_node_id, text_embeds_slot, sampler, 2, "TEXT_EMBEDS")
            # 内部连接: steps / cfg
            _link(steps_const, 0, sampler, 3, "INT")
            _link(cfg_schedule, 0, sampler, 4, "FLOAT")

            # 输出指向 WanVideoSampler 的 latents 输出（slot 0）
            return (nodes, links, sampler.id, 0)

    def _build_video_output(self, latent_node_id, latent_slot, vae_node_id, vae_slot,
                             filename_prefix, frame_rate=24):
        """构建阶段5初级合成节点链（V19验证成功架构）

        【V19架构变更】VAEDecode → WanVideoDecode
        WanVideoDecode → VHS_VideoCombine
        - WanVideoDecode: 使用与阶段2相同的 WanVideoVAELoader VAE，将潜空间帧转换为像素帧
          V19参数: enable_vae_tiling=False, tile_x=272, tile_y=272, tile_stride_x=144, tile_stride_y=128
        - VHS_VideoCombine (VideoHelperSuite): 编码为 MP4，禁止使用 CreateVideo + SaveVideo
          参数: frame_rate=24, format=video/h264-mp4, crf=15, save_metadata=True

        Args:
            latent_node_id/slot: 阶段4 WanVideoSampler 的 LATENT 输出
            vae_node_id/slot: 阶段2 WanVideoVAELoader 的 VAE 输出
            filename_prefix: 输出文件名前缀
            frame_rate: 帧率，默认24

        Returns: (nodes_list, links_list, output_node_id, output_slot)
            output指向 WanVideoDecode 的 IMAGE 输出（供阶段6后处理链使用）
        """
        nodes = []
        links = []
        _id = [0]

        def _new(node_type, pos):
            _id[0] += 1
            node = WorkflowNode(_id[0], node_type, pos)
            nodes.append(node)
            return node

        def _ext_link(ext_node_id, ext_slot, tgt, tgt_slot, link_type):
            links.append((ext_node_id, ext_slot, tgt.id, tgt_slot, link_type))

        def _link(src, src_slot, tgt, tgt_slot, link_type):
            links.append((src.id, src_slot, tgt.id, tgt_slot, link_type))

        # --- 1. WanVideoDecode（V19替换VAEDecode） ---
        # 使用同一 WanVideoVAELoader VAE，将潜空间帧转换为像素帧
        vae_decode = _new('WanVideoDecode', [1000, 300])
        vae_decode.inputs = [
            {"name": "vae", "type": "VAE", "link": None},         # slot 0 ← 阶段2 WanVideoVAELoader
            {"name": "samples", "type": "LATENT", "link": None},  # slot 1 ← 阶段4 WanVideoSampler
            {"name": "enable_vae_tiling", "type": "BOOLEAN", "link": None, "widget": {"name": "enable_vae_tiling"}},
            {"name": "tile_x", "type": "INT", "link": None, "widget": {"name": "tile_x"}},
            {"name": "tile_y", "type": "INT", "link": None, "widget": {"name": "tile_y"}},
            {"name": "tile_stride_x", "type": "INT", "link": None, "widget": {"name": "tile_stride_x"}},
            {"name": "tile_stride_y", "type": "INT", "link": None, "widget": {"name": "tile_stride_y"}},
        ]
        vae_decode.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # V19验证参数: enable_vae_tiling=False, tile尺寸默认值
        vae_decode.widgets_values = [
            False,   # enable_vae_tiling=False（V19验证值）
            272,     # tile_x
            272,     # tile_y
            144,     # tile_stride_x
            128,     # tile_stride_y
        ]

        # --- 2. VHS_VideoCombine (VideoHelperSuite) ---
        vhs_node_type = "VHS_VideoCombine"
        video_combine = _new(vhs_node_type, [1200, 300])
        video_combine.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "frame_rate", "type": "FLOAT", "link": None, "widget": {"name": "frame_rate"}},
            {"name": "loop_count", "type": "INT", "link": None, "widget": {"name": "loop_count"}},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "format", "type": "COMBO", "link": None, "widget": {"name": "format"}},
            {"name": "pix_fmt", "type": "STRING", "link": None, "widget": {"name": "pix_fmt"}},
            {"name": "save_metadata", "type": "BOOLEAN", "link": None, "widget": {"name": "save_metadata"}},
            {"name": "crf", "type": "FLOAT", "link": None, "widget": {"name": "crf"}},
        ]
        video_combine.outputs = []
        # V19验证参数: crf=15（V19值，原18改为15提升质量）
        video_combine.widgets_values = [
            float(frame_rate),   # frame_rate=24
            0,                   # loop_count 不循环
            filename_prefix,     # 文件名前缀
            "video/h264-mp4",    # format H.264 MP4
            "yuv420p",           # pix_fmt 兼容性最佳
            True,                # save_metadata
            15,                  # crf=15（V19验证值）
        ]

        # --- 连接 ---
        # 外部: 阶段2 VAE → WanVideoDecode.vae (slot 0)
        _ext_link(vae_node_id, vae_slot, vae_decode, 0, "VAE")
        # 外部: 阶段4 latents → WanVideoDecode.samples (slot 1)
        _ext_link(latent_node_id, latent_slot, vae_decode, 1, "LATENT")
        # 内部: WanVideoDecode.IMAGE → VHS_VideoCombine.images
        _link(vae_decode, 0, video_combine, 0, "IMAGE")

        # 输出指向 WanVideoDecode 的 IMAGE 输出，供阶段6后处理链接入
        return (nodes, links, vae_decode.id, 0)

    def _build_post_processing(self, images_node_id, images_slot, filename_prefix):
        """构建阶段6后处理链（lc.txt 六阶段架构）

        完整序列: Upscale → RIFE VFI → Deflicker → Video Combine
        - Upscale: UpscaleModelLoader(RealESRGAN_x2plus) → Image Upscale With Model(2x) → Image Scale(1280×720)
        - RIFE VFI: 2x插帧，24→48fps，模型rife49.pth
        - Deflicker: strength=0.3, window_size=3（时域去闪烁，避免画面"软"）
        - 最终 Video Combine: 48fps输出，得到1280×720成品视频

        顺序严格遵循 lc.txt 阶段6，不可调换：先超分补全细节(不改变帧数)，
        再插帧提升流畅度，最后去闪烁平滑时域。

        Args:
            images_node_id/slot: 阶段5 VAE Decode 的 IMAGE 输出
            filename_prefix: 输出文件名前缀

        Returns: (nodes_list, links_list, output_node_id, output_slot)
            output_node_id/output_slot: 指向最终 Video Combine（无输出，slot为-1）
        """
        nodes = []
        links = []
        _id = [0]

        def _new(node_type, pos):
            _id[0] += 1
            node = WorkflowNode(_id[0], node_type, pos)
            nodes.append(node)
            return node

        def _ext_link(ext_node_id, ext_slot, tgt, tgt_slot, link_type):
            links.append((ext_node_id, ext_slot, tgt.id, tgt_slot, link_type))

        def _link(src, src_slot, tgt, tgt_slot, link_type):
            links.append((src.id, src_slot, tgt.id, tgt_slot, link_type))

        # --- 6.1 时域超分辨率 (提升至 1280×720) ---
        # 6.1a. UpscaleModelLoader: 加载 RealESRGAN_x2plus.pth
        upscale_model_loader = _new('UpscaleModelLoader', [1400, 100])
        upscale_model_loader.inputs = [
            {"name": "model_name", "type": "COMBO", "link": None, "widget": {"name": "model_name"}}
        ]
        upscale_model_loader.outputs = [
            {"name": "UPSCALE_MODEL", "type": "UPSCALE_MODEL", "links": [], "slot_index": 0}
        ]
        upscale_model_loader.widgets_values = ["RealESRGAN_x2plus.pth"]

        # 6.1b. Image Upscale With Model: 使用模型2x超分（补全细节，不改帧数）
        image_upscale = _new('Image Upscale With Model', [1400, 250])
        image_upscale.inputs = [
            {"name": "upscale_model", "type": "UPSCALE_MODEL", "link": None},  # slot 0 ← UpscaleModelLoader
            {"name": "image", "type": "IMAGE", "link": None},                  # slot 1 ← 阶段5 VAE Decode
        ]
        image_upscale.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        image_upscale.widgets_values = []

        # 6.1c. Image Scale: 调整到目标尺寸 1280×720（lanczos 重采样）
        image_scale = _new('ImageScale', [1400, 400])
        image_scale.inputs = [
            {"name": "image", "type": "IMAGE", "link": None},
            {"name": "upscale_method", "type": "COMBO", "link": None, "widget": {"name": "upscale_method"}},
            {"name": "width", "type": "INT", "link": None, "widget": {"name": "width"}},
            {"name": "height", "type": "INT", "link": None, "widget": {"name": "height"}},
            {"name": "crop", "type": "COMBO", "link": None, "widget": {"name": "crop"}},
        ]
        image_scale.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # widgets: upscale_method, width, height, crop
        image_scale.widgets_values = ["lanczos", 1280, 720, "disabled"]

        # --- 6.2 插帧提升流畅度: RIFE VFI (2x, 24→48fps) ---
        rife = _new('RIFE VFI', [1600, 250])
        rife.inputs = [
            {"name": "frames", "type": "IMAGE", "link": None},                    # slot 0 ← Image Scale
            {"name": "multiplier", "type": "INT", "link": None, "widget": {"name": "multiplier"}},
            {"name": "model", "type": "COMBO", "link": None, "widget": {"name": "model"}},
        ]
        rife.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # widgets: multiplier, model
        rife.widgets_values = [
            2,                # multiplier=2x，将24fps提升至48fps
            "rife49.pth",     # model rife49（备选rife50），更平滑
        ]

        # --- 6.3 时域去闪烁: Deflicker (strength=0.3, window_size=3) ---
        deflicker = _new('Deflicker', [1800, 250])
        deflicker.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},                       # slot 0 ← RIFE VFI
            {"name": "strength", "type": "FLOAT", "link": None, "widget": {"name": "strength"}},
            {"name": "window_size", "type": "INT", "link": None, "widget": {"name": "window_size"}},
        ]
        deflicker.outputs = [
            {"name": "IMAGE", "type": "IMAGE", "links": [], "slot_index": 0}
        ]
        # widgets: strength, window_size
        deflicker.widgets_values = [
            0.3,              # strength=0.3 避免画面变"软"（lc.txt 推荐0.3~0.5）
            3,                # window_size=3 对连续帧亮度/色度做均值平滑（推荐3~5）
        ]

        # --- 最终 Video Combine: 48fps输出 ---
        # 禁止使用 CreateVideo + SaveVideo；优先 VHS_VideoCombine，备选 "Video Combine"
        vhs_node_type = "VHS_VideoCombine"
        final_combine = _new(vhs_node_type, [2000, 250])
        final_combine.inputs = [
            {"name": "images", "type": "IMAGE", "link": None},
            {"name": "frame_rate", "type": "FLOAT", "link": None, "widget": {"name": "frame_rate"}},
            {"name": "loop_count", "type": "INT", "link": None, "widget": {"name": "loop_count"}},
            {"name": "filename_prefix", "type": "STRING", "link": None, "widget": {"name": "filename_prefix"}},
            {"name": "format", "type": "COMBO", "link": None, "widget": {"name": "format"}},
            {"name": "pix_fmt", "type": "STRING", "link": None, "widget": {"name": "pix_fmt"}},
            {"name": "save_metadata", "type": "BOOLEAN", "link": None, "widget": {"name": "save_metadata"}},
            {"name": "crf", "type": "FLOAT", "link": None, "widget": {"name": "crf"}},
        ]
        final_combine.outputs = []
        # widgets: frame_rate=48(插帧后), loop_count, filename_prefix, format, pix_fmt, save_metadata, crf
        final_combine.widgets_values = [
            48.0,              # frame_rate=48 插帧后输出帧率
            0,                 # loop_count 不循环
            filename_prefix,   # 文件名前缀（最终成品）
            "video/h264-mp4",  # format H.264 MP4
            "yuv420p",         # pix_fmt 兼容性最佳
            True,              # save_metadata 保存元数据
            18,                # crf=18 高质量
        ]

        # --- 连接（严格顺序: Upscale → RIFE VFI → Deflicker → Video Combine） ---
        # 外部: 阶段5 VAE Decode.IMAGE → Image Upscale With Model.image
        _ext_link(images_node_id, images_slot, image_upscale, 1, "IMAGE")
        # 内部: UpscaleModelLoader → Image Upscale With Model
        _link(upscale_model_loader, 0, image_upscale, 0, "UPSCALE_MODEL")
        # 内部: Image Upscale With Model → Image Scale
        _link(image_upscale, 0, image_scale, 0, "IMAGE")
        # 内部: Image Scale → RIFE VFI
        _link(image_scale, 0, rife, 0, "IMAGE")
        # 内部: RIFE VFI → Deflicker
        _link(rife, 0, deflicker, 0, "IMAGE")
        # 内部: Deflicker → 最终 Video Combine
        _link(deflicker, 0, final_combine, 0, "IMAGE")

        # 最终 Video Combine 无输出，返回 -1 表示无后续连接
        return (nodes, links, final_combine.id, -1)

    # ==================================================================
    # 六阶段架构组装辅助方法（节点ID偏移 / 跨阶段连接 / 参数提取）
    # ==================================================================

    def _ratio_to_dimensions(self, ratio):
        """将画面比例转换为像素尺寸（Wan2.2 标准分辨率）

        Args:
            ratio: 比例字符串，如 "9:16"/"16:9"/"1:1"

        Returns: (width, height) 元组
        """
        ratio_norm = str(ratio).lower().replace("/", ":").strip()
        if ratio_norm in ("9:16", "portrait"):
            return (480, 832)   # 竖屏
        elif ratio_norm in ("16:9", "landscape"):
            return (832, 480)   # 横屏
        else:
            return (640, 640)   # 方形

    def _merge_stage_into_graph(self, graph, nodes, links):
        """将一个阶段的节点和连接合并到图中，自动偏移ID避免冲突。

        六阶段方法返回的节点使用本地自增ID（从1开始），连接中的 source/target
        可能是本阶段的本地ID（内部连接）或前阶段的全局ID（外部连接）。
        本方法通过 id_map 区分：在 map 中的ID会被偏移，不在 map 中的保持不变。

        Args:
            graph: 目标 WorkflowGraph
            nodes: WorkflowNode 列表（本地自增 id）
            links: 连接元组列表 (source_id, source_slot, target_id, target_slot, link_type)

        Returns: id_map (local_id → global_id 的映射字典)
        """
        id_map = {}
        offset = graph.next_id - 1  # 本地ID从1开始，偏移使其接续全局ID

        for node in nodes:
            global_id = node.id + offset
            id_map[node.id] = global_id
            node.id = global_id
            graph.nodes[global_id] = node

        if nodes:
            graph.next_id = max(n.id for n in nodes) + 1

        # 偏移连接中的ID（仅偏移属于本阶段的节点ID，外部节点ID保持不变）
        for src, src_slot, tgt, tgt_slot, lt in links:
            global_src = id_map.get(src, src)
            global_tgt = id_map.get(tgt, tgt)
            link_id = graph.next_link_id
            graph.links.append([link_id, global_src, src_slot, global_tgt, tgt_slot, lt])
            graph.next_link_id += 1
            # 回填目标节点输入的 link 字段（标准 ComfyUI UI 格式）
            tgt_node = graph.nodes.get(global_tgt)
            if tgt_node is not None and tgt_slot < len(tgt_node.inputs):
                tgt_node.inputs[tgt_slot]['link'] = link_id

        return id_map

    def _add_cross_stage_link(self, graph, src_id, src_slot, tgt_id, tgt_slot, link_type):
        """添加跨阶段连接到图中（用于手动建立阶段间的 link）"""
        link_id = graph.next_link_id
        graph.links.append([link_id, src_id, src_slot, tgt_id, tgt_slot, link_type])
        graph.next_link_id += 1
        # 回填目标节点输入的 link 字段（标准 ComfyUI UI 格式）
        tgt_node = graph.nodes.get(tgt_id)
        if tgt_node is not None and tgt_slot < len(tgt_node.inputs):
            tgt_node.inputs[tgt_slot]['link'] = link_id

    def _populate_graph_from_workflow(self, graph, workflow_json):
        """将工作流 JSON 中的节点和连接填充到 WorkflowGraph 中。

        用于将 _build_* 方法返回的完整工作流 JSON 回填到图中，
        以便后续 _apply_techniques / pattern 覆盖等流程继续操作。
        """
        for node_data in workflow_json.get("nodes", []):
            node = WorkflowNode(node_data["id"], node_data["type"], node_data.get("pos"))
            node.size = node_data.get("size", [200, 100])
            node.inputs = node_data.get("inputs", [])
            node.outputs = node_data.get("outputs", [])
            node.widgets_values = node_data.get("widgets_values", [])
            node._meta = node_data.get("_meta", {})
            node.order = node_data.get("order", 0)
            graph.nodes[node.id] = node
        for link in workflow_json.get("links", []):
            graph.links.append(link)
        graph.next_id = max(graph.next_id, workflow_json.get("last_node_id", 0) + 1)
        graph.next_link_id = max(graph.next_link_id, workflow_json.get("last_link_id", 0) + 1)
        if workflow_json.get("metadata"):
            graph.metadata.update(workflow_json["metadata"])

    def _dispatch_video_task(self, graph, parsed, task_type):
        """从解析结果中提取参数并调用对应的六阶段视频构建方法。

        各 _build_* 方法返回完整的 UI 格式工作流 JSON，本方法将其回填到 graph 中。
        """
        params = parsed.get('parameters', {})
        user_prompt = parsed.get('original', '')
        ratio = params.get('ratio', '9:16')
        # V19验证：lightx2v LoRA加速后6-8步即可，默认8步
        steps = params.get('steps', 8)
        seed = params.get('seed', 12345)

        if task_type == 'img2vid':
            wf = self._build_img2vid(
                image_name=params.get('image_name', 'input_image.png'),
                user_prompt=user_prompt, ratio=ratio, steps=steps, seed=seed,
                filename_prefix='img2vid')
        elif task_type == 'first_last_frame':
            wf = self._build_first_last_frame(
                first_image=params.get('first_image', 'first_frame.png'),
                last_image=params.get('last_image', 'last_frame.png'),
                user_prompt=user_prompt, ratio=ratio, steps=steps, seed=seed,
                filename_prefix='first_last')
        elif task_type == 'multi_image_video':
            image_names = params.get('image_names')
            if not image_names:
                image_count = params.get('image_count', 3)
                image_names = [f'image_{i+1}.png' for i in range(image_count)]
            wf = self._build_multi_image_video(
                image_names=image_names,
                user_prompt=user_prompt, ratio=ratio, steps=steps, seed=seed,
                filename_prefix='multi_img')
        elif task_type == 'long_video':
            wf = self._build_long_video(
                image_name=params.get('image_name', 'input_image.png'),
                user_prompt=user_prompt, ratio=ratio, steps=steps, seed=seed,
                segments=params.get('segments', 2),
                filename_prefix='long_vid')
        elif task_type == 'video_concat':
            video_paths = params.get('video_paths')
            if not video_paths:
                video_count = params.get('video_count', 2)
                video_paths = [f'input_video_{i+1}.mp4' for i in range(video_count)]
            wf = self._build_video_concat(
                video_paths=video_paths,
                user_prompt=user_prompt, ratio=ratio,
                filename_prefix='vid_concat')
        elif task_type == 'multi_ref_video':
            ref_images = params.get('ref_images')
            if not ref_images:
                ref_count = params.get('ref_count', 2)
                ref_images = [f'ref_image_{i+1}.png' for i in range(ref_count)]
            wf = self._build_multi_ref_video(
                ref_images=ref_images,
                user_prompt=user_prompt, ratio=ratio, steps=steps, seed=seed,
                filename_prefix='multi_ref')
        else:
            return

        self._populate_graph_from_workflow(graph, wf)


class AdvancedWorkflowGenerator:
    """高级工作流生成器 - 主控类"""
    
    def __init__(self, object_info_path: str = None, library_path: str = None):
        self.registry = NodeRegistry(object_info_path)
        self.parser = RequirementParser()
        self.assembler = WorkflowAssembler(self.registry, library_path)
    
    def generate(self, requirement_text: str) -> dict:
        """生成工作流"""
        # 1. 解析需求
        parsed = self.parser.parse(requirement_text)
        
        # 2. 组装工作流
        graph = self.assembler.assemble(parsed)
        
        # 3. 转换为Web格式
        workflow = graph.to_web_format()
        
        # 4. 生成报告
        report = {
            'ok': True,
            'requirement': requirement_text,
            'parsed': parsed,
            'workflow': workflow,
            'statistics': {
                'node_count': len(graph.nodes),
                'link_count': len(graph.links),
                'complexity': parsed['complexity']
            }
        }
        
        return report
    
    def generate_and_save(self, requirement_text: str, output_path: str) -> dict:
        """生成并保存工作流"""
        result = self.generate(requirement_text)
        
        if result['ok']:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(result['workflow'], f, indent=2, ensure_ascii=False)
            result['saved_to'] = output_path
        
        return result


def main():
    ap = argparse.ArgumentParser(description="高级工作流生成器")
    ap.add_argument("--requirement", required=True, help="工作流需求描述")
    ap.add_argument("--object-info", default=".trae/skills/comfyui-controller/assets/object_info.json",
                    help="object_info.json路径")
    ap.add_argument("--library", default=".trae/skills/comfyui-controller/assets/workflow_library.json",
                    help="工作流资料库路径")
    ap.add_argument("--output", help="输出工作流文件路径")
    args = ap.parse_args()
    
    generator = AdvancedWorkflowGenerator(args.object_info, args.library)
    
    if args.output:
        result = generator.generate_and_save(args.requirement, args.output)
    else:
        result = generator.generate(args.requirement)
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
