#!/usr/bin/env python3
"""
工作流模式提取器
- 从工作流仓库中按 (task_category, model_family) 严格分组提取典型模式
- 提取典型节点序列、参数、模型组合、中立节点
- 生成模式库供后续工作流生成参考
- model_family 为强制分组键，同 task_category 不同 model_family 的工作流绝不合并
"""
import argparse
import json
import os
import sys
from collections import defaultdict, Counter

# 添加同目录到 sys.path 以便 import build_workflow_library
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_workflow_library import detect_model_family


# 中立节点类型集合（与模型无关的节点，可跨 model_family 复用）
_NEUTRAL_NODE_TYPES = {
    "SaveImage", "PreviewImage", "PreviewText", "Note", "PrimitiveNode",
    "Reroute", "MathExpression", "DisplayAny", "ShowAny", "InfoNode",
    "ReadNoteFromImage", "ETN_LoadImageBase64", "ImageComparer",
}


def _extract_node_type_from_step(step):
    """从执行流程步骤文本中提取节点类型。
    步骤格式如 '1.CheckpointLoaderSimple(加载模型)'，
    需提取括号前的节点类型，去掉序号前缀。
    """
    # 去掉序号前缀 'N.'（按第一个点分割）
    if '.' in step:
        _, rest = step.split('.', 1)
    else:
        rest = step
    # 取括号前的部分作为节点类型
    if '(' in rest:
        return rest.split('(', 1)[0]
    return rest


def _get_execution_flow(workflow):
    """获取工作流的 execution_flow，兼容顶层和 template 内两种位置。"""
    # 优先取顶层（扩展后的结构）
    execution_flow = workflow.get('execution_flow')
    if not isinstance(execution_flow, dict) or not execution_flow:
        # 降级取 template 内（原始结构）
        template = workflow.get('template', {}) or {}
        execution_flow = template.get('execution_flow', {}) or {}
    return execution_flow if isinstance(execution_flow, dict) else {}


def _get_configurable(workflow):
    """获取工作流的 configurable 参数，兼容顶层和 template 内两种位置。"""
    template = workflow.get('template', {}) or {}
    configurable = template.get('configurable')
    if not isinstance(configurable, dict) or not configurable:
        # 降级取顶层
        configurable = workflow.get('configurable', {}) or {}
    return configurable if isinstance(configurable, dict) else {}


def _get_node_sequence(workflow):
    """获取工作流的节点类型序列。
    优先从 execution_flow.steps 提取（去掉序号前缀和括号描述），
    若 execution_flow 不存在或为空，则从 node_types 的 keys 按字典序构造（降级方案）。
    """
    execution_flow = _get_execution_flow(workflow)
    steps = execution_flow.get('steps', [])
    if isinstance(steps, list) and steps:
        sequence = []
        for step in steps:
            if not isinstance(step, str):
                continue
            node_type = _extract_node_type_from_step(step)
            if node_type:
                sequence.append(node_type)
        if sequence:
            return sequence

    # 降级方案：从 node_types 的 keys 按字典序构造
    node_types = workflow.get('node_types', {}) or {}
    if isinstance(node_types, dict) and node_types:
        return sorted(node_types.keys())
    return []


def _get_workflow_models(workflow):
    """获取工作流中所有模型名及简化组合。
    返回 (all_model_names, combo_dict) 元组：
    - all_model_names: 所有角色所有模型名的扁平列表（用于 family 验证）
    - combo_dict: {role: first_model_name} 简化组合（每个角色取排序后第一个）
    """
    models = workflow.get('models', {}) or {}
    if not isinstance(models, dict):
        return [], {}
    all_model_names = []
    combo_dict = {}
    # 模型角色顺序（other 为字典列表，不参与组合统计）
    roles = ['checkpoints', 'unet', 'vae', 'clip', 'lora', 'controlnet', 'upscale']
    for role in roles:
        model_list = models.get(role, [])
        if not isinstance(model_list, list):
            continue
        # 过滤非字符串和空字符串
        str_models = [m for m in model_list if isinstance(m, str) and m]
        if not str_models:
            continue
        # 收集所有模型名用于 family 验证
        all_model_names.extend(str_models)
        # combo 取排序后的第一个模型（保证确定性）
        combo_dict[role] = sorted(str_models)[0]
    return all_model_names, combo_dict


def _validate_combo_family(all_model_names, group_family):
    """验证 combo 中所有模型的 family 是否与分组 family 一致。
    - 若某模型检测出明确的 family 且与 group_family 不同，则不一致（跳过）
    - 'unknown' 视为无法判定，不视为不一致（避免误杀辅助模型如 VAE）
    """
    for model_name in all_model_names:
        family, _modality = detect_model_family(model_name)
        # 仅当检测出明确 family 且与分组不一致时才判定为不通过
        if family != 'unknown' and family != group_family:
            return False
    return True


def _extract_params_from_workflow(workflow):
    """从单个工作流提取参数名 -> 值列表。
    优先从 template.configurable 提取，并从 parameters 字段补充提取。
    返回 {param_name: [value1, value2, ...]} 字典。
    """
    result = defaultdict(list)

    # 1. 从 template.configurable 提取（主来源）
    configurable = _get_configurable(workflow)
    for key, info in configurable.items():
        if not isinstance(info, dict):
            continue
        param_name = info.get('param', '')
        if not param_name:
            # 降级：用 key 的最后一段（如 'KSampler.steps' -> 'steps'）
            param_name = key.split('.')[-1] if '.' in key else key
        value = info.get('default_value')
        result[param_name].append(value)

    # 2. 从 parameters 字段补充提取（如有）
    parameters = workflow.get('parameters', {}) or {}
    if isinstance(parameters, dict):
        # 采样器参数：{node_id: {steps: 20, cfg: 7.0, ...}}
        sampler = parameters.get('sampler', {}) or {}
        if isinstance(sampler, dict):
            for _node_id, params in sampler.items():
                if not isinstance(params, dict):
                    continue
                for pname, value in params.items():
                    result[pname].append(value)
        # 分辨率参数：{width: 512, height: 512, ...}
        resolution = parameters.get('resolution', {}) or {}
        if isinstance(resolution, dict):
            for pname, value in resolution.items():
                result[pname].append(value)

    return result


def _count_param_values(param_values_list):
    """统计跨工作流的参数值频率，返回每个参数的 Top 5 值。
    param_values_list: 每个工作流的 {param_name: [values]} 字典列表
    返回 {param_name: [{value, count}, ...]} 字典
    """
    # 收集每个参数的所有值
    all_values = defaultdict(list)
    for param_dict in param_values_list:
        for pname, values in param_dict.items():
            all_values[pname].extend(values)

    result = {}
    for pname, values in all_values.items():
        # 值需要可哈希才能计数，不可哈希的转为 JSON 字符串
        counter = Counter()
        for v in values:
            if isinstance(v, (list, dict)):
                key = json.dumps(v, ensure_ascii=False, sort_keys=True)
            else:
                key = v
            counter[key] += 1
        # 按频率降序排序，频率相同按值字典序，取 Top 5
        top = sorted(counter.items(), key=lambda x: (-x[1], str(x[0])))[:5]
        result[pname] = [{"value": k, "count": c} for k, c in top]

    return result


def extract_patterns(library):
    """从工作流仓库提取模式。
    输入：工作流仓库字典（含 'workflows' 字段）
    按 (task_category, model_family) 严格分组：
    - model_family 为强制分组键，同 task_category 不同 model_family 绝不合并
    - model_family 为 'unknown' 或空的工作流被跳过，记录到 warnings
    返回 {"patterns": [...], "warnings": [...]} 字典
    """
    warnings = []
    patterns = []

    workflows = library.get('workflows', {}) or {}
    if not isinstance(workflows, dict):
        return {"patterns": [], "warnings": ["workflows 字段不是字典类型"]}

    # 按 (task_category, model_family) 分组
    groups = defaultdict(list)  # {(category, family): [(name, workflow), ...]}
    for name, workflow in workflows.items():
        if not isinstance(workflow, dict):
            warnings.append(f"工作流 '{name}' 不是字典类型，已跳过")
            continue
        category = workflow.get('category', '') or ''
        family = workflow.get('model_family', '') or ''
        # model_family 为 unknown 或空的工作流被跳过
        if not family or family == 'unknown':
            warnings.append(f"工作流 '{name}' model_family 为 unknown，已跳过")
            continue
        groups[(category, family)].append((name, workflow))

    # 对每组计算模式
    for (category, family), wf_list in groups.items():
        sample_count = len(wf_list)

        # 1. typical_node_sequence: 统计节点类型序列频率，取 Top 3 变体
        seq_counter = Counter()
        for _name, wf in wf_list:
            sequence = _get_node_sequence(wf)
            if sequence:
                seq_counter[tuple(sequence)] += 1
        typical_node_sequence = []
        for seq_tuple, freq in sorted(seq_counter.items(), key=lambda x: (-x[1], x[0]))[:3]:
            typical_node_sequence.append({
                "frequency": freq,
                "sequence": list(seq_tuple),
            })

        # 2. typical_parameters: 统计每个参数常见值及出现次数，取 Top 5
        param_values_list = []
        for _name, wf in wf_list:
            param_values_list.append(_extract_params_from_workflow(wf))
        typical_parameters = _count_param_values(param_values_list)

        # 3. typical_model_combos: 统计模型组合频率，取 Top 5
        #    需验证 combo 中所有模型的 family 与分组一致
        combo_counter = Counter()
        for _name, wf in wf_list:
            all_model_names, combo_dict = _get_workflow_models(wf)
            if not combo_dict:
                continue
            # 验证 combo 中所有模型的 family 一致性
            if not _validate_combo_family(all_model_names, family):
                continue
            # 转为可哈希的 tuple 进行计数
            combo_key = tuple(sorted(combo_dict.items()))
            combo_counter[combo_key] += 1
        typical_model_combos = []
        for combo_key, freq in sorted(combo_counter.items(), key=lambda x: (-x[1], x[0]))[:5]:
            typical_model_combos.append({
                "frequency": freq,
                "combo": dict(combo_key),
            })

        # 4. neutral_nodes: 收集该分组中出现的所有中立节点（去重，按字母序排序）
        neutral_set = set()
        for _name, wf in wf_list:
            node_types = wf.get('node_types', {}) or {}
            if isinstance(node_types, dict):
                for nt in node_types.keys():
                    if nt in _NEUTRAL_NODE_TYPES:
                        neutral_set.add(nt)
        neutral_nodes = sorted(neutral_set)

        patterns.append({
            "task_category": category,
            "model_family": family,
            "sample_count": sample_count,
            "typical_node_sequence": typical_node_sequence,
            "typical_parameters": typical_parameters,
            "typical_model_combos": typical_model_combos,
            "neutral_nodes": neutral_nodes,
        })

    return {"patterns": patterns, "warnings": warnings}


def save_patterns(patterns, path):
    """将模式库（含 patterns 和 warnings）保存为 JSON 文件。"""
    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(path))
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(patterns, f, indent=2, ensure_ascii=False)


def load_patterns(path):
    """加载模式库 JSON。文件不存在时返回空字典 {"patterns": [], "warnings": []}。"""
    if not os.path.isfile(path):
        return {"patterns": [], "warnings": []}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"patterns": [], "warnings": []}
        if "patterns" not in data:
            data["patterns"] = []
        if "warnings" not in data:
            data["warnings"] = []
        return data
    except (json.JSONDecodeError, OSError):
        return {"patterns": [], "warnings": []}


def main():
    """CLI 入口：加载工作流仓库，提取模式，保存到输出路径。"""
    parser = argparse.ArgumentParser(
        description="工作流模式提取器：从工作流仓库提取典型模式"
    )
    parser.add_argument(
        '--library',
        default='.trae/skills/comfyui-controller/assets/workflow_library.json',
        help='工作流仓库路径（默认：.trae/skills/comfyui-controller/assets/workflow_library.json）',
    )
    parser.add_argument(
        '--output',
        default='.trae/skills/comfyui-controller/assets/workflow_patterns.json',
        help='模式库输出路径（默认：.trae/skills/comfyui-controller/assets/workflow_patterns.json）',
    )
    args = parser.parse_args()

    library_path = args.library
    output_path = args.output

    # 1. 加载工作流仓库
    if not os.path.isfile(library_path):
        print(f"错误：工作流仓库不存在：{library_path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(library_path, 'r', encoding='utf-8') as f:
            library = json.load(f)
    except json.JSONDecodeError as e:
        print(f"错误：工作流仓库 JSON 解析失败：{e}", file=sys.stderr)
        sys.exit(1)

    # 2. 提取模式
    result = extract_patterns(library)

    # 3. 保存模式库
    save_patterns(result, output_path)

    # 4. 打印摘要
    patterns = result.get('patterns', [])
    warnings = result.get('warnings', [])
    print(f"已提取 {len(patterns)} 个模式，保存到 {output_path}")
    for p in patterns:
        print(f"  - task_category={p['task_category']}, "
              f"model_family={p['model_family']}, "
              f"sample_count={p['sample_count']}")

    # 5. 若有 warnings，打印警告信息
    if warnings:
        print(f"\n警告（{len(warnings)} 条）：")
        for w in warnings:
            print(f"  ! {w}")


if __name__ == '__main__':
    main()
