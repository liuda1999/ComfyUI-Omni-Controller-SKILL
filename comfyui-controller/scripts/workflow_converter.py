#!/usr/bin/env python3
"""Convert ComfyUI web format workflow to API format."""
import argparse
import json
import urllib.request

# control_after_generate 标记值，这些值出现在 widgets_values 中但不是真正的输入参数
_CONTROL_AFTER_GENERATE_VALUES = {"fixed", "increment", "randomize", "disable"}


def _get_control_after_generate_fields(node_type, object_info):
    """获取节点中标记了 control_after_generate=True 的字段名集合。"""
    if not object_info or node_type not in object_info:
        return set()

    node_schema = object_info[node_type]
    inputs_def = node_schema.get("input", {})
    cag_fields = set()

    for section in ("required", "optional"):
        section_inputs = inputs_def.get(section, {})
        if isinstance(section_inputs, dict):
            for name, type_info in section_inputs.items():
                if (isinstance(type_info, list) and len(type_info) > 1 and
                    isinstance(type_info[1], dict) and
                    type_info[1].get("control_after_generate")):
                    cag_fields.add(name)

    return cag_fields


def _filter_control_values(widgets_values, widget_names=None, widget_types=None, cag_fields=None):
    """过滤 widgets_values 中的 control_after_generate 标记。

    ComfyUI UI 格式中，带 control_after_generate 的 INT 字段（如 noise_seed）
    会在 widgets_values 数组中插入一个 control_after_generate 标记
    （如 "fixed"/"randomize"/"disable"），但该标记不是真正的输入参数。

    策略：只有 object_info 中标记了 control_after_generate: True 的字段，
    其后面的 control 标记才需要过滤。其他 INT 字段（如 end_at_step）
    后面如果恰好跟了一个 control 标记值，不应过滤（因为那是下一个字段的值）。
    """
    if not widget_names or not widget_types or cag_fields is None:
        # 无 schema 信息，无法精确定位，回退到旧逻辑
        out = []
        i = 0
        while i < len(widgets_values):
            value = widgets_values[i]
            if (isinstance(value, int) and
                i + 1 < len(widgets_values) and
                isinstance(widgets_values[i + 1], str) and
                widgets_values[i + 1] in _CONTROL_AFTER_GENERATE_VALUES):
                out.append(value)
                i += 2
                continue
            out.append(value)
            i += 1
        return out

    # 精确模式：根据 widget_names 和 cag_fields 重建
    out = []
    wv_idx = 0
    for name, wtype in zip(widget_names, widget_types):
        if wv_idx >= len(widgets_values):
            break
        value = widgets_values[wv_idx]

        # 只有 control_after_generate=True 的 INT 字段才需要跳过后面的 control 标记
        if (name in cag_fields and isinstance(value, int) and
            wv_idx + 1 < len(widgets_values) and
            isinstance(widgets_values[wv_idx + 1], str) and
            widgets_values[wv_idx + 1] in _CONTROL_AFTER_GENERATE_VALUES):
            # 跳过 control 标记
            wv_idx += 2
        else:
            wv_idx += 1
        out.append(value)

    return out


def get_object_info(host="127.0.0.1", port="3198"):  # comfyui-cli项目标准端口
    """从 ComfyUI 服务器获取 object_info 字典"""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/object_info", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"Warning: 无法从服务器获取 object_info: {e}")
        return {}


def _is_widget_type(input_type):
    """判断 input_type 是否是 widget 类型（非连接类型）。

    ComfyUI object_info 中 widget 类型包括：
    - 旧格式 COMBO: input_type 是列表（选项列表）
    - 新格式 COMBO: input_type 是 'COMBO' 字符串
    - INT、FLOAT、STRING
    """
    if isinstance(input_type, list):
        return True  # 旧格式 COMBO（选项列表）
    return input_type in ("INT", "FLOAT", "STRING", "COMBO")


def _get_widget_names_from_object_info(node_type, object_info):
    """从 object_info schema 获取有序的 widget 输入名列表。

    UI 格式的 nodes[].inputs 只包含连接输入，widget 定义需要从 object_info 获取。
    widget 类型包括：COMBO（新旧格式）、INT、FLOAT、STRING。
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
                    if _is_widget_type(input_type):
                        widget_names.append(name)

    return widget_names


def _get_widget_types_from_object_info(node_type, object_info):
    """从 object_info schema 获取有序的 widget 输入类型列表，用于类型转换"""
    if not object_info or node_type not in object_info:
        return []

    node_schema = object_info[node_type]
    inputs_def = node_schema.get("input", {})

    widget_types = []
    for section in ("required", "optional"):
        section_inputs = inputs_def.get(section, {})
        if isinstance(section_inputs, dict):
            for name, type_info in section_inputs.items():
                if isinstance(type_info, list) and len(type_info) > 0:
                    input_type = type_info[0]
                    if _is_widget_type(input_type):
                        widget_types.append(input_type)

    return widget_types


def _get_widget_combo_options_from_object_info(node_type, object_info):
    """从 object_info schema 获取每个 widget 的 COMBO 选项列表（如有）。

    返回一个列表，与 widget_names/widget_types 平行。
    对于非 COMBO 类型的 widget，对应位置为 None。
    对于旧格式 COMBO（input_type 是选项列表），返回该列表。
    对于新格式 COMBO（input_type 是 'COMBO' 字符串），从后续元素中提取选项。
    """
    if not object_info or node_type not in object_info:
        return []

    node_schema = object_info[node_type]
    inputs_def = node_schema.get("input", {})

    combo_options = []
    for section in ("required", "optional"):
        section_inputs = inputs_def.get(section, {})
        if isinstance(section_inputs, dict):
            for name, type_info in section_inputs.items():
                if isinstance(type_info, list) and len(type_info) > 0:
                    input_type = type_info[0]
                    if not _is_widget_type(input_type):
                        continue

                    if isinstance(input_type, list):
                        # 旧格式 COMBO：input_type 本身就是选项列表
                        combo_options.append(input_type)
                    elif input_type == "COMBO":
                        # 新格式 COMBO：选项在 type_info[1] 中
                        opts = type_info[1] if len(type_info) > 1 else None
                        if isinstance(opts, dict):
                            opts = opts.get("options", None)
                        combo_options.append(opts if isinstance(opts, list) else None)
                    else:
                        # INT, FLOAT, STRING - 不是 COMBO
                        combo_options.append(None)

    return combo_options


def convert_web_to_api(web_workflow, object_info=None):
    """Convert web UI format to API format.

    Args:
        web_workflow: UI 格式工作流（含 nodes/links 数组）
        object_info: 从 /object_info 获取的节点 schema 字典。
                     如果为 None，widget 值将无法正确映射。
    """
    if "nodes" not in web_workflow:
        # Already in API format
        return web_workflow

    if object_info is None:
        object_info = {}

    api_workflow = {}
    nodes = web_workflow.get("nodes", [])
    links = web_workflow.get("links", [])

    # Build node input connections from the links array (source of truth).
    # 标准 ComfyUI UI 格式中 links 数组是连线的事实来源；按目标节点+目标插槽反查输入名，
    # 不依赖 inputs[].link（builder 生成的工作流可能不填该字段，且对第三方节点同样适用）。
    node_inputs = {}
    for node in nodes:
        node_inputs[str(node.get("id"))] = {}
    node_by_id = {n.get("id"): n for n in nodes}
    for link in links:
        if isinstance(link, list) and len(link) >= 5:
            _link_id, src_id, src_slot, tgt_id, tgt_slot = link[:5]
            tgt_node = node_by_id.get(tgt_id)
            if tgt_node is None:
                continue
            tgt_inputs = tgt_node.get("inputs", [])
            if tgt_slot >= len(tgt_inputs):
                continue
            inp_name = tgt_inputs[tgt_slot].get("name")
            if inp_name:
                node_inputs[str(tgt_id)][inp_name] = [str(src_id), src_slot]

    # Build API nodes
    for node in nodes:
        node_id = str(node.get("id"))
        node_type = node.get("type", "")

        api_node = {
            "class_type": node_type,
            "inputs": {}
        }

        # Get widget values - these are stored in widgets_values array
        widgets_values = node.get("widgets_values", [])

        # 处理 dict 格式的 widgets_values（如 VHS_VideoCombine 等节点）
        # 这类节点的 widgets_values 是 {param_name: value} 字典，直接使用
        if isinstance(widgets_values, dict):
            connected_input_names = set(node_inputs.get(node_id, {}).keys())
            for param_name, value in widgets_values.items():
                # 跳过已被连接占用的参数和 UI 辅助字段
                if param_name in connected_input_names:
                    continue
                # 跳过 videopreview 等 UI 辅助字段
                if param_name in ("videopreview",):
                    continue
                api_node["inputs"][param_name] = value
        else:
            if not isinstance(widgets_values, list):
                widgets_values = []

            # 使用 object_info 获取 widget 名称和类型列表
            # UI 格式的 node["inputs"] 只包含连接输入，不能用于 widget 映射
            widget_names = _get_widget_names_from_object_info(node_type, object_info)
            widget_types = _get_widget_types_from_object_info(node_type, object_info)
            widget_combo_opts = _get_widget_combo_options_from_object_info(node_type, object_info)
            cag_fields = _get_control_after_generate_fields(node_type, object_info)

            # 过滤 control_after_generate 标记，避免 widget 值错位
            # 传入 widget_names, widget_types 和 cag_fields 以精确定位 control 标记位置
            filtered_values = _filter_control_values(widgets_values, widget_names, widget_types, cag_fields)

            # 检查哪些 widget 已被连接占用（有 link 的连接输入会覆盖 widget 值）
            connected_input_names = set(node_inputs.get(node_id, {}).keys())

            # 映射 widget 值到参数名
            for idx, param_name in enumerate(widget_names):
                if param_name in connected_input_names:
                    # 该参数已被连接占用，跳过 widget 值
                    continue
                if idx >= len(filtered_values):
                    break
                value = filtered_values[idx]

                # 类型转换
                if idx < len(widget_types):
                    inp_type = widget_types[idx]
                    if inp_type == "INT" and isinstance(value, str):
                        try:
                            value = int(value)
                        except ValueError:
                            pass
                    elif inp_type == "FLOAT" and isinstance(value, str):
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                    elif isinstance(inp_type, list) or inp_type == "COMBO":
                        # COMBO 类型：如果值是整数索引，转换为对应的字符串选项
                        combo_opts = widget_combo_opts[idx] if idx < len(widget_combo_opts) else None
                        if (isinstance(value, int) and combo_opts and
                            0 <= value < len(combo_opts)):
                            value = combo_opts[value]

                api_node["inputs"][param_name] = value

        # Add connections (these override widget values if there's a link)
        for input_name, connection in node_inputs.get(node_id, {}).items():
            api_node["inputs"][input_name] = connection

        api_workflow[node_id] = api_node

    return api_workflow


def main():
    ap = argparse.ArgumentParser(description="Convert ComfyUI workflow format")
    ap.add_argument("--input", required=True, help="Input workflow JSON")
    ap.add_argument("--output", required=True, help="Output workflow JSON")
    ap.add_argument("--host", default="127.0.0.1", help="ComfyUI server host")
    ap.add_argument("--port", default="3198", help="ComfyUI server port")  # comfyui-cli项目标准端口
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        workflow = json.load(f)

    # 从服务器获取 object_info 用于 widget 映射
    object_info = get_object_info(args.host, args.port)
    if not object_info:
        print("Warning: 无法获取 object_info，widget 值可能无法正确映射")

    api_workflow = convert_web_to_api(workflow, object_info)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(api_workflow, f, indent=2, ensure_ascii=False)

    print(json.dumps({"ok": True, "output": args.output, "nodes": list(api_workflow.keys())}))


if __name__ == "__main__":
    main()
