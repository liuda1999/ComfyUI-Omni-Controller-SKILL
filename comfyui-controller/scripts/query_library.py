#!/usr/bin/env python3
"""
工作流仓库查询 CLI

从 workflow_library.json 工作流仓库中按类别、模型系列、节点类型、模型等条件查询工作流，
并支持输出仓库统计信息和完整列表。

默认仓库路径：.trae/skills/comfyui-controller/assets/workflow_library.json

数据结构（已扩展）：
  workflows:
    name:
      path, category, model_family, node_count,
      node_types {type: {count, instances}},
      models {checkpoints: [...], lora: [...], ...},
      node_annotations, execution_flow, file_meta
  statistics: {...}
  file_index: {rel_path: {mtime, size}}
"""
import argparse
import json
import os
import sys
import unicodedata
from collections import defaultdict


DEFAULT_LIBRARY = ".trae/skills/comfyui-controller/assets/workflow_library.json"

# 表格列宽（显示宽度），打印前按数据动态调整
_WIDTHS = {"name": 22, "path": 45, "count": 8, "family": 10}


def _display_width(s):
    """计算字符串显示宽度（CJK/全角字符算 2，其余算 1）。"""
    width = 0
    for ch in str(s):
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _pad_right(s, width):
    """按显示宽度在右侧填充空格至指定宽度。"""
    s = str(s)
    return s + " " * max(0, width - _display_width(s))


def load_library(path):
    """加载工作流仓库 JSON 文件。
    文件不存在或解析失败时打印错误信息并 sys.exit(1)。
    """
    if not os.path.isfile(path):
        print(f"[ERROR] Library file not found: {path}", file=sys.stderr)
        sys.exit(1)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse library JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Failed to load library: {e}", file=sys.stderr)
        sys.exit(1)


def _get_model_family(info):
    """获取工作流的模型系列，缺失时回退到 template，再缺失返回 'unknown'。"""
    family = info.get("model_family")
    if not family:
        template = info.get("template", {}) or {}
        family = template.get("model_family", "unknown")
    return family or "unknown"


def _format_models(info):
    """将工作流模型字典格式化为 [(category, "model1, model2"), ...]，过滤空类别。"""
    models = info.get("models", {}) or {}
    lines = []
    for category, model_list in models.items():
        if not model_list:
            continue
        if category == "other":
            names = []
            for m in model_list:
                if isinstance(m, dict):
                    names.append(str(m.get("value", m)))
                else:
                    names.append(str(m))
            if names:
                lines.append((category, ", ".join(names)))
        else:
            names = [str(m) for m in model_list]
            if names:
                lines.append((category, ", ".join(names)))
    return lines


def _set_widths(items):
    """根据 (name, info) 列表动态计算表格列宽。"""
    name_w = _display_width("名称")
    path_w = _display_width("路径")
    count_w = _display_width("节点数")
    family_w = _display_width("模型系列")
    for name, info in items:
        name_w = max(name_w, _display_width(name))
        path_w = max(path_w, _display_width(info.get("path", "")))
        count_w = max(count_w, _display_width(str(info.get("node_count", 0))))
        family_w = max(family_w, _display_width(_get_model_family(info)))
    _WIDTHS["name"] = max(name_w, 8)
    _WIDTHS["path"] = max(path_w, 8)
    _WIDTHS["count"] = max(count_w, 6)
    _WIDTHS["family"] = max(family_w, 6)


def _print_table_header():
    """打印工作流摘要表格表头。"""
    print(
        _pad_right("名称", _WIDTHS["name"]) + "  "
        + _pad_right("路径", _WIDTHS["path"]) + "  "
        + _pad_right("节点数", _WIDTHS["count"]) + "  "
        + _pad_right("模型系列", _WIDTHS["family"]) + "  "
        + "模型"
    )


def print_workflow_summary(name, info):
    """打印单个工作流摘要（表格行；模型多类别时换行续接并对齐模型列）。"""
    models = _format_models(info)
    family = _get_model_family(info)
    path = info.get("path", "")
    count = info.get("node_count", 0)

    prefix = (
        _pad_right(name, _WIDTHS["name"]) + "  "
        + _pad_right(path, _WIDTHS["path"]) + "  "
        + _pad_right(str(count), _WIDTHS["count"]) + "  "
        + _pad_right(family, _WIDTHS["family"]) + "  "
    )
    if not models:
        print(prefix + "(无)")
        return
    indent = " " * _display_width(prefix)
    for idx, (category, line) in enumerate(models):
        if idx == 0:
            print(prefix + f"{category}: {line}")
        else:
            print(indent + f"{category}: {line}")


def _print_section(title, items):
    """打印一个查询结果区段：标题 + 表头 + 各工作流摘要行。"""
    print(f"\n=== {title} ({len(items)} 个工作流) ===")
    if not items:
        print("(无匹配工作流)")
        return
    _set_widths(items)
    _print_table_header()
    for name, info in items:
        print_workflow_summary(name, info)


def filter_by_category(library, category):
    """按类别过滤工作流，返回 [(name, info), ...]。"""
    workflows = library.get("workflows", {}) or {}
    return [
        (name, info)
        for name, info in workflows.items()
        if info.get("category", "") == category
    ]


def filter_by_model_family(library, family):
    """按模型系列过滤工作流，返回 [(name, info), ...]。"""
    workflows = library.get("workflows", {}) or {}
    return [
        (name, info)
        for name, info in workflows.items()
        if _get_model_family(info) == family
    ]


def filter_by_node_type(library, node_type):
    """按节点类型过滤（部分匹配，如 KSampler 可匹配 KSamplerAdvanced）。"""
    workflows = library.get("workflows", {}) or {}
    nt_lower = node_type.lower()
    items = []
    for name, info in workflows.items():
        node_types = info.get("node_types", {}) or {}
        for nt in node_types.keys():
            if nt_lower in nt.lower():
                items.append((name, info))
                break
    return items


def filter_by_model(library, model_name):
    """按模型文件名过滤（部分匹配，搜索 models 中所有类别的模型）。"""
    workflows = library.get("workflows", {}) or {}
    m_lower = model_name.lower()
    items = []
    for name, info in workflows.items():
        models = info.get("models", {}) or {}
        matched = False
        for model_list in models.values():
            for m in model_list:
                m_str = str(m.get("value", m)) if isinstance(m, dict) else str(m)
                if m_lower in m_str.lower():
                    matched = True
                    break
            if matched:
                break
        if matched:
            items.append((name, info))
    return items


def print_stats(library):
    """打印仓库统计信息：总数、类别分布、模型系列分布、常用节点 Top 10、模型清单。"""
    workflows = library.get("workflows", {}) or {}

    print("\n" + "=" * 60)
    print("工作流仓库统计")
    print("=" * 60)

    # 工作流总数
    print(f"\n【工作流总数】 {len(workflows)}")

    # 类别分布
    print("\n【类别分布】")
    cat_count = defaultdict(int)
    for info in workflows.values():
        cat_count[info.get("category", "未分类")] += 1
    if cat_count:
        for cat, count in sorted(cat_count.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {cat}: {count} 个")
    else:
        print("  (无)")

    # 模型系列分布
    print("\n【模型系列分布】")
    family_count = defaultdict(int)
    for info in workflows.values():
        family_count[_get_model_family(info)] += 1
    if family_count:
        for family, count in sorted(family_count.items(), key=lambda x: (-x[1], x[0])):
            print(f"  {family}: {count} 个")
    else:
        print("  (无)")

    # 最常用节点 Top 10（按出现工作流数排序）
    print("\n【最常用节点 Top 10】（按出现工作流数排序）")
    node_wf_count = defaultdict(int)
    for info in workflows.values():
        node_types = info.get("node_types", {}) or {}
        for nt in node_types.keys():
            node_wf_count[nt] += 1
    if node_wf_count:
        for nt, count in sorted(node_wf_count.items(), key=lambda x: (-x[1], x[0]))[:10]:
            print(f"  {nt}: {count} 个工作流")
    else:
        print("  (无)")

    # 模型清单（按类别分组）
    print("\n【模型清单】（按类别分组）")
    models_by_cat = defaultdict(set)
    for info in workflows.values():
        models = info.get("models", {}) or {}
        for category, model_list in models.items():
            for m in model_list:
                if isinstance(m, dict):
                    val = m.get("value")
                    if val:
                        models_by_cat[category].add(str(val))
                elif isinstance(m, str) and m:
                    models_by_cat[category].add(m)
    if models_by_cat:
        for category in sorted(models_by_cat.keys()):
            model_set = sorted(models_by_cat[category])
            print(f"  {category} ({len(model_set)} 个):")
            for m in model_set:
                print(f"    - {m}")
    else:
        print("  (无)")


def main():
    ap = argparse.ArgumentParser(
        description="工作流仓库查询 CLI - 从 workflow_library.json 中查询工作流",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python query_library.py --list
  python query_library.py --category 文生图
  python query_library.py --model-family Wan2.2
  python query_library.py --node-type KSampler
  python query_library.py --model flux1-dev
  python query_library.py --stats
""",
    )
    ap.add_argument("--library", default=DEFAULT_LIBRARY,
                    help=f"工作流仓库 JSON 路径 (默认: {DEFAULT_LIBRARY})")
    ap.add_argument("--category", help="按类别过滤工作流")
    ap.add_argument("--model-family", dest="model_family",
                    help="按模型系列过滤工作流")
    ap.add_argument("--node-type", dest="node_type",
                    help="按节点类型过滤工作流（部分匹配，如 KSampler 可匹配 KSamplerAdvanced）")
    ap.add_argument("--model", help="按模型文件名过滤工作流（部分匹配，搜索所有类别）")
    ap.add_argument("--stats", action="store_true", help="输出仓库统计信息")
    ap.add_argument("--list", dest="list_all", action="store_true",
                    help="列出所有工作流名称和路径")
    args = ap.parse_args()

    library = load_library(args.library)

    if args.list_all:
        workflows = library.get("workflows", {}) or {}
        print(f"\n=== 工作流列表 ({len(workflows)} 个) ===")
        if not workflows:
            print("(无工作流)")
            return
        items = list(workflows.items())
        _set_widths(items)
        print(_pad_right("名称", _WIDTHS["name"]) + "  " + _pad_right("路径", _WIDTHS["path"]))
        for name, info in workflows.items():
            print(_pad_right(name, _WIDTHS["name"]) + "  " + info.get("path", ""))
        return

    if args.stats:
        print_stats(library)
        return

    if args.category:
        _print_section(f"类别: {args.category}", filter_by_category(library, args.category))
        return

    if args.model_family:
        _print_section(f"模型系列: {args.model_family}",
                       filter_by_model_family(library, args.model_family))
        return

    if args.node_type:
        _print_section(f"节点类型: {args.node_type}",
                       filter_by_node_type(library, args.node_type))
        return

    if args.model:
        _print_section(f"模型: {args.model}", filter_by_model(library, args.model))
        return

    # 无参数时输出帮助文本
    ap.print_help()


if __name__ == "__main__":
    main()
