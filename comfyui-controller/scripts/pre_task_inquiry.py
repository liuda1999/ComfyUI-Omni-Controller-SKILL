#!/usr/bin/env python3
"""
视频生成任务执行前的强制预检反问模块。

通过交互式问答依次完成：
  1. 模型查询与展示
  2. 模型选择与同系列组件自动匹配
  3. 生成参数收集
  4. 硬件兼容性检查
任何一个环节失败即终止任务，返回 None。
"""
import json
import os
import subprocess
import urllib.request

# ComfyUI 服务器地址
COMFYUI_HOST = "127.0.0.1"
COMFYUI_PORT = 3198  # comfyui-cli项目标准端口
COMFYUI_BASE = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"

# 模型系列关键词映射（不区分大小写）
# 模型名包含任一关键词即归入对应系列，按顺序优先匹配
FAMILY_KEYWORDS = [
    ("Wan2.2", ["wan"]),
    ("Flux", ["flux"]),
    ("SD1.5", ["sd1", "v1-5"]),
    ("SDXL", ["sdxl"]),
]

# 各系列组件自动匹配关键词
# 用于在可用 VAE/CLIP/CLIP_VISION 列表中按关键词挑选同系列组件
# 空列表表示该系列通常不使用该类组件，允许跳过
FAMILY_MATCH_RULES = {
    "Wan2.2": {
        "vae": ["wan"],
        "clip": ["t5"],
        "clip_vision": ["clip_vision_h"],
    },
    "Flux": {
        "vae": ["flux"],
        "clip": ["qwen", "t5"],
        "clip_vision": ["clip_vision"],
    },
    "SD1.5": {
        "vae": ["vae-ft", "sd"],
        "clip": ["sd1", "clip-vit"],
        "clip_vision": [],
    },
}

# 目标尺寸查找表（宽×高），所有尺寸均为 16 的倍数
# 键: (比例代号, 分辨率代号) -> (width, height)
#   比例: 1=9:16竖屏, 2=16:9横屏, 3=1:1方形
#   分辨率: 1=480P, 2=720P, 3=1080P
SIZE_TABLE = {
    (1, 1): (480, 832),    # 9:16 竖屏 480P
    (1, 2): (720, 1280),   # 9:16 竖屏 720P
    (1, 3): (1088, 1920),  # 9:16 竖屏 1080P
    (2, 1): (832, 480),    # 16:9 横屏 480P
    (2, 2): (1280, 720),   # 16:9 横屏 720P
    (2, 3): (1920, 1088),  # 16:9 横屏 1080P
    (3, 1): (640, 640),    # 1:1 方形 480P
    (3, 2): (720, 720),    # 1:1 方形 720P
    (3, 3): (1088, 1088),  # 1:1 方形 1080P
}

# 内存最低要求（MB），低于此值终止任务
MIN_RAM_MB = 16 * 1024


def http_json(url, timeout=10):
    """发起 GET 请求并返回解析后的 JSON 对象，超时默认 10 秒。"""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def detect_family(model_name):
    """根据模型名关键词判断所属系列，未匹配则返回 '其他'。"""
    lower = model_name.lower()
    for family, keywords in FAMILY_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return family
    return "其他"


def fetch_model_list(node_type, param_name):
    """从 /object_info/{node_type} 查询可用模型列表。

    兼容 ComfyUI 两种参数格式：
      旧格式: [["model1.safetensors", ...], {config}]，取 [0] 即为列表
      新格式(v0.27+): ["COMBO", {"options": [...]}]
    """
    try:
        data = http_json(f"{COMFYUI_BASE}/object_info/{node_type}", timeout=10)
    except Exception as e:
        print(f"[警告] 查询 {node_type} 失败: {e}")
        return []
    node_schema = data.get(node_type, {})
    if not node_schema:
        return []
    required = node_schema.get("input", {}).get("required", {})
    param_def = required.get(param_name, [])
    if not param_def or not isinstance(param_def, list) or len(param_def) == 0:
        return []
    first = param_def[0]
    # 旧格式: [["model1.safetensors", ...], {config}] -> [0] 即为模型列表
    if isinstance(first, list):
        return list(first)
    # 新格式: ["COMBO", {"options": [...]}]
    if isinstance(first, str) and len(param_def) > 1 and isinstance(param_def[1], dict):
        options = param_def[1].get("options", [])
        if isinstance(options, list):
            return list(options)
    return []


def query_all_models():
    """查询 ComfyUI 服务器上所有可用的模型组件（diffusion/vae/clip/clip_vision）。"""
    return {
        "diffusion_models": fetch_model_list("UNETLoader", "unet_name"),
        "vae": fetch_model_list("VAELoader", "vae_name"),
        "clip": fetch_model_list("CLIPLoader", "clip_name"),
        "clip_vision": fetch_model_list("CLIPVisionLoader", "clip_name"),
    }


def group_by_family(model_list):
    """将模型列表按系列分组，返回 {系列名: [模型名]}，按预定义顺序排列。"""
    groups = {f: [] for f, _ in FAMILY_KEYWORDS}
    groups["其他"] = []
    for name in model_list:
        groups[detect_family(name)].append(name)
    return groups


def _print_grouped(model_list, start_index=1):
    """内部辅助：按系列打印单个类别的模型，返回 (序号->模型名 映射, 下一个序号)。"""
    index_map = {}
    idx = start_index
    if not model_list:
        print("  （无可用模型）")
        return index_map, idx
    groups = group_by_family(model_list)
    for family in [f for f, _ in FAMILY_KEYWORDS] + ["其他"]:
        names = groups.get(family, [])
        if not names:
            continue
        print(f"  [{family}系列]")
        for name in names:
            print(f"    {idx}. {name}")
            index_map[idx] = name
            idx += 1
    return index_map, idx


def print_models_grouped(models):
    """按系列分组打印所有类别的可用模型，返回扩散模型的 {序号: 模型名} 映射。"""
    print("\n--- 可用扩散模型 (diffusion_models) ---")
    diffusion_map, next_idx = _print_grouped(models["diffusion_models"], start_index=1)

    print("\n--- 可用 VAE ---")
    _print_grouped(models["vae"], start_index=1)

    print("\n--- 可用 CLIP ---")
    _print_grouped(models["clip"], start_index=1)

    print("\n--- 可用 CLIP_VISION ---")
    _print_grouped(models["clip_vision"], start_index=1)

    return diffusion_map


def match_component(available_list, keywords):
    """从可用列表中匹配包含任一关键词的第一个组件（不区分大小写）。

    关键词按顺序匹配，返回首个命中项；无匹配返回 None。
    """
    if not keywords:
        return None
    lowered = [(name, name.lower()) for name in available_list]
    for kw in keywords:
        kw_lower = kw.lower()
        for name, lower in lowered:
            if kw_lower in lower:
                return name
    return None


def detect_component_family(name, component_type):
    """判断单个组件所属系列，用于跨系列混用校验。

    通过 FAMILY_MATCH_RULES 反查：若某系列在该组件类型的关键词命中该名称，则归入该系列。
    """
    lower = name.lower()
    for family, rules in FAMILY_MATCH_RULES.items():
        for kw in rules.get(component_type, []):
            if kw.lower() in lower:
                return family
    return "其他"


def query_and_select_models():
    """查询并展示模型，由用户选择主模型后自动匹配同系列组件。

    返回 {diffusion_model, vae, clip, clip_vision, model_family}，失败返回 None。
    """
    # 查询所有可用模型
    models = query_all_models()
    if not models["diffusion_models"]:
        print("[错误] 服务器上没有可用的扩散模型，无法继续。")
        return None

    # 展示模型列表
    diffusion_map = print_models_grouped(models)

    # 用户选择主模型（名称或序号）
    print("\n请选择扩散模型（输入序号或完整模型名）:")
    raw = input("> ").strip()
    if not raw:
        print("[错误] 未输入模型选择，终止任务。")
        return None

    selected = None
    # 优先按序号匹配
    if raw.isdigit():
        num = int(raw)
        selected = diffusion_map.get(num)
        if selected is None:
            print(f"[错误] 序号 {num} 不在扩散模型列表中。")
            return None
    else:
        # 按名称精确匹配
        if raw in models["diffusion_models"]:
            selected = raw
        else:
            # 容错：名称包含匹配
            matches = [m for m in models["diffusion_models"] if raw.lower() in m.lower()]
            if len(matches) == 1:
                selected = matches[0]
            elif len(matches) > 1:
                print(f"[错误] 输入匹配到多个模型，请输入更精确的名称: {matches}")
                return None
            else:
                print(f"[错误] 未找到模型: {raw}")
                return None

    family = detect_family(selected)
    print(f"\n已选择扩散模型: {selected}")
    print(f"识别模型系列: {family}")

    # 自动匹配同系列组件
    rules = FAMILY_MATCH_RULES.get(family, {})
    result = {
        "diffusion_model": selected,
        "model_family": family,
    }

    for comp_type in ["vae", "clip", "clip_vision"]:
        keywords = rules.get(comp_type, [])
        available = models[comp_type]
        if not keywords:
            # 该系列通常不使用此类组件，允许留空
            result[comp_type] = None
            print(f"  {comp_type}: 该系列无需此类组件，已跳过")
            continue
        matched = match_component(available, keywords)
        if matched is None:
            # 无匹配，禁止跨系列混用，报错终止
            print(f"[错误] 未能为 {family} 系列匹配到 {comp_type}（关键词: {keywords}）。")
            print(f"       可用 {comp_type} 列表: {available if available else '空'}")
            print("       禁止跨系列混用组件，请补充对应系列组件后重试。")
            return None
        # 二次校验：确认匹配项确实属于同系列
        comp_family = detect_component_family(matched, comp_type)
        if comp_family != family:
            print(f"[错误] 匹配到的 {comp_type} '{matched}' 属于 {comp_family} 系列，"
                  f"与主模型 {family} 系列不兼容，禁止跨系列混用。")
            return None
        result[comp_type] = matched
        print(f"  {comp_type}: {matched}（自动匹配）")

    return result


def collect_architecture_scheme(model_family="Wan2.2"):
    """收集架构方案选择（方案A: HIGH+LOW双采集器串行 / 方案B: 单一模型）。

    生产环境推荐方案A（HIGH模型负责高噪声主结构，LOW模型负责低噪声细节，
    两个 WanVideo I2V Sampler 串行）；方案B仅适用于快速测试或简单场景。

    Args:
        model_family: 已选模型系列，用于在提示中说明适用性

    Returns:
        "dual_serial"(方案A) 或 "single"(方案B)，失败返回 None
    """
    print("\n" + "-" * 40)
    print("步骤 1.5: 架构方案选择")
    print("-" * 40)
    print("\n请选择模型架构方案:")
    print("  1. 方案A: HIGH+LOW 双采集器串行（生产环境推荐）")
    print("     - HIGH 模型负责高噪声阶段（denoise=1.0 主结构生成）")
    print("     - LOW 模型负责低噪声阶段（denoise=0.3 细节细化）")
    print("     - 两个 WanVideo I2V Sampler 串行，画质最佳")
    print("     - 需要更大显存（同时加载 HIGH+LOW 两个 fp8 模型）")
    print("  2. 方案B: 单一模型（简单场景）")
    print("     - 单个 wan2.2_i2v_14B 模型，单次采样")
    print("     - 适用于快速测试或简单场景")
    print(f"\n(当前模型系列: {model_family}，默认推荐方案A)")

    choice = _read_int("请输入 (1/2，默认 1): ", default=1, valid_choices=[1, 2])
    if choice is None:
        print("[错误] 未选择架构方案，终止任务。")
        return None
    if choice == 1:
        print("已选择方案A: HIGH+LOW 双采集器串行（生产环境）")
        return "dual_serial"
    else:
        print("已选择方案B: 单一模型（简单场景）")
        return "single"


def _read_int(prompt_text, default=None, valid_choices=None):
    """内部辅助：读取用户输入的整数，支持默认值与可选值校验。"""
    raw = input(prompt_text).strip()
    if not raw:
        if default is not None:
            return default
        return None
    try:
        val = int(raw)
    except ValueError:
        print(f"[错误] 请输入有效数字，收到: {raw}")
        return None
    if valid_choices is not None and val not in valid_choices:
        print(f"[错误] 输入 {val} 不在可选范围 {valid_choices} 内。")
        return None
    return val


def select_k_sampler(positive_prompt="", is_video=False):
    """K 采样器选择（强制，根据提示词内容与目标效果推荐）。

    依据 SKILL.md 4.6.4 节：先判定收敛型 vs 随机型，再按提示词关键词推荐采样器。
    返回 {sampler_name, scheduler}，失败返回 None。

    视频任务：按模型系列约定优先（Wan2.2 用 dpmpp_sde），由调用方在模型选择后传入 is_video=True。
    图片任务：根据提示词内容判断画面目标。
    """
    prompt = (positive_prompt or "").lower()

    # 视频任务：按模型系列约定选择（见 SKILL.md 4.6.4 模型系列特殊约定）
    if is_video:
        print("\n[视频任务] K 采样器按模型系列约定选择（Wan2.2: scheduler=dpm++_sde，见 SKILL.md 4.6.4，已验证不可改）")
        return {"sampler_name": "dpmpp_sde", "scheduler": "dpm++_sde"}

    # 判定画面目标：写实/产品/建筑 → 收敛型；创意/艺术/插画 → 随机型
    creative_kw = ["art", "style", "stylized", "illustration", "anime", "creative",
                   "concept", "painting", "watercolor", "impression", "sketch",
                   "插画", "动漫", "艺术", "风格化", "创意", "概念", "手绘", "水彩", "素描"]
    realistic_kw = ["photoreal", "realistic", "portrait", "product", "photo",
                    "architect", "commercial", "still", "jewel", "interior",
                    "写实", "人像", "产品", "摄影", "建筑", "商业", "静物", "珠宝"]

    is_creative = any(k in prompt for k in creative_kw)
    is_realistic = any(k in prompt for k in realistic_kw)

    # 推荐决策（对应 SKILL.md 4.6.4 决策表）
    if is_realistic and not is_creative:
        rec = {"sampler_name": "dpmpp_2m_sde", "scheduler": "karras", "steps_hint": "25-35",
               "why": "写实/产品/摄影 → 收敛型 dpmpp_2m_sde（平滑自然）"}
    elif is_creative and not is_realistic:
        rec = {"sampler_name": "euler_ancestral", "scheduler": "karras", "steps_hint": "20-30",
               "why": "创意/艺术/插画 → 随机型 euler_ancestral（纹理丰富）"}
    else:
        # 无明确倾向或同时包含 → 通用默认
        rec = {"sampler_name": "dpmpp_2m", "scheduler": "karras", "steps_hint": "15-25",
               "why": "日常通用 → dpmpp_2m（行业黄金标准）"}

    print("\n步骤 2.5: K 采样器选择（强制，根据提示词内容）")
    print("-" * 40)
    print(f"[推荐] {rec['why']} → sampler={rec['sampler_name']}, scheduler={rec['scheduler']}, steps={rec['steps_hint']}")
    print("  1. 采用推荐")
    print("  2. euler_ancestral (随机/艺术)")
    print("  3. dpmpp_2m (收敛/通用)")
    print("  4. dpmpp_2m_sde (收敛/平滑写实)")
    print("  5. ddim (收敛/绝对稳定)")
    print("  6. dpmpp_2m_cfg_pp (收敛/复杂提示词高控制)")
    print("  7. 自定义输入")
    choice = _read_int("请输入 (1-7，默认 1): ", default=1, valid_choices=[1, 2, 3, 4, 5, 6, 7])
    if choice is None:
        return None
    preset = {
        1: (rec["sampler_name"], "karras"),
        2: ("euler_ancestral", "karras"),
        3: ("dpmpp_2m", "karras"),
        4: ("dpmpp_2m_sde", "karras"),
        5: ("ddim", "ddim_uniform"),
        6: ("dpmpp_2m_cfg_pp", "beta"),
    }
    if choice in preset:
        sampler_name, scheduler = preset[choice]
    else:
        sampler_name = input("请输入 sampler_name: ").strip()
        if not sampler_name:
            print("[错误] 采样器不能为空，终止任务。")
            return None
        scheduler = input("请输入 scheduler (默认 karras): ").strip() or "karras"
    print(f"已选择: sampler={sampler_name}, scheduler={scheduler}")
    return {"sampler_name": sampler_name, "scheduler": scheduler}


def collect_generation_params():
    """收集生成参数：画面比例、分辨率、步数、提示词，并计算目标尺寸。

    返回 {ratio, resolution, steps, positive_prompt, negative_prompt,
          target_width, target_height, adaptive_params, sampler_name, scheduler}，
    失败返回 None。
    """
    print("\n" + "-" * 40)
    print("步骤 2: 生成参数收集")
    print("-" * 40)

    # 画面比例
    print("\n请选择画面比例:")
    print("  1. 9:16 竖屏")
    print("  2. 16:9 横屏")
    print("  3. 1:1 方形")
    ratio = _read_int("请输入 (1/2/3): ", default=None, valid_choices=[1, 2, 3])
    if ratio is None:
        print("[错误] 未选择画面比例，终止任务。")
        return None

    # 分辨率
    print("\n请选择分辨率:")
    print("  1. 480P 基础")
    print("  2. 720P 增强")
    print("  3. 1080P 高清")
    resolution = _read_int("请输入 (1/2/3): ", default=None, valid_choices=[1, 2, 3])
    if resolution is None:
        print("[错误] 未选择分辨率，终止任务。")
        return None

    # 优化步数 - 根据硬件自适应推荐
    vram_mb = query_gpu_vram_mb()
    adaptive = get_adaptive_params(vram_mb)
    if adaptive is None and vram_mb is not None:
        print(f"[错误] 当前设备显存 {vram_mb / 1024:.1f} GB 不足以运行视频生成任务 (最低 8GB)。")
        return None
    if adaptive:
        rec_steps = adaptive["steps"]
        print(f"\n请输入优化步数 steps (推荐 {rec_steps}，基于 {adaptive['vram_gb']}GB VRAM {adaptive['tier']}档次):")
        steps = _read_int("> ", default=rec_steps)
    else:
        print("\n请输入优化步数 steps (无法检测显存，默认 8):")
        steps = _read_int("> ", default=8)
    if steps is None:
        return None
    if steps < 1 or steps > 100:
        print(f"[警告] 步数 {steps} 超出常见范围 1-100，仍继续。")
    elif adaptive and steps < adaptive["steps"]:
        print(f"[提示] 步数 {steps} 低于推荐值 {adaptive['steps']}，可能影响质量。")

    # 正面提示词
    print("\n请输入正面提示词 (直接回车可留空):")
    positive = input("> ").strip()

    # 负面提示词
    print("\n请输入负面提示词 (直接回车可留空):")
    negative = input("> ").strip()

    # K 采样器选择（视频任务按模型系列约定，见 SKILL.md 4.6.4）
    sampler = select_k_sampler(positive, is_video=True)
    if sampler is None:
        return None

    # 计算目标尺寸
    size_key = (ratio, resolution)
    width, height = SIZE_TABLE.get(size_key, (None, None))
    if width is None or height is None:
        print(f"[错误] 不支持的比例/分辨率组合: {size_key}")
        return None
    # 安全校验：确保尺寸为 16 的倍数
    width = _round_to_16(width)
    height = _round_to_16(height)

    ratio_names = {1: "9:16竖屏", 2: "16:9横屏", 3: "1:1方形"}
    res_names = {1: "480P", 2: "720P", 3: "1080P"}
    print(f"\n目标尺寸: {width}×{height} ({ratio_names[ratio]} {res_names[resolution]})")

    return {
        "ratio": ratio,
        "resolution": resolution,
        "steps": steps,
        "positive_prompt": positive,
        "negative_prompt": negative,
        "target_width": width,
        "target_height": height,
        "adaptive_params": adaptive,
        "sampler_name": sampler["sampler_name"],
        "scheduler": sampler["scheduler"],
    }


def _round_to_16(value):
    """将数值向上取整到最近的 16 的倍数（尺寸规范要求）。"""
    return ((value + 15) // 16) * 16


def query_gpu_vram_mb():
    """通过 nvidia-smi 查询 GPU 显存总量（MB），失败返回 None。"""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if output.returncode != 0:
            return None
        line = output.stdout.strip().splitlines()
        if not line:
            return None
        return int(line[0].strip())
    except Exception as e:
        print(f"[警告] 查询 GPU 显存失败: {e}")
        return None


def get_adaptive_params(vram_mb):
    """根据 GPU 显存返回 WanVideo 性能参数推荐档次（质量优先）。

    四档配置（与 SKILL.md 4.5.1 / video-guide 检查4 的硬件梯度表对齐）:
      - L4 专业级 (VRAM >= 24576 MB / 24GB): steps=10, blocks_to_swap=20, split_step=5, fp16_fast
      - L3 高性能 (16384 <= VRAM < 24576 MB / 16-24GB): steps=8, blocks_to_swap=20, split_step=4, bf16
      - L2 标准级 (12288 <= VRAM < 16384 MB / 12-16GB): steps=6, blocks_to_swap=38, split_step=3, bf16
      - L1 入门级 (8192 <= VRAM < 12288 MB / 8-12GB): steps=6, blocks_to_swap=40, split_step=3, bf16
      - 不足 (VRAM < 8192 MB): 返回 None

    核心质量参数:
      - attention_mode 强制 sdpa（sageattn 在 PyTorch 2.9.1+cu128 触发 DLL 加载失败，
        code 0xc0000139，参见 SKILL.md 4.11.1 禁忌表）
      - base_precision 按档位：L1-L3 用 bf16，仅 L4 用 fp16_fast（fp16_fast 低显存+lightx2v 会 OOM）
      - scheduler=dpm++_sde（lightx2v 验证，unipc 会导致动作卡住旋转）
      - blocks_to_swap 按档位：L1/L2 高（显存小需多换出），L3/L4 20（C8 验证，38 导致专用显存闲置）

    返回 dict: {tier, steps, blocks_to_swap, split_step, attention_mode, base_precision, scheduler, vram_gb}
    或 None（显存不足）。
    """
    if vram_mb is None:
        return None
    vram_gb = vram_mb / 1024
    # 核心质量参数
    core = {
        "attention_mode": "sdpa",
        "scheduler": "dpm++_sde",
    }
    if vram_mb >= 24576:
        return {"tier": "L4 专业级", "steps": 10, "blocks_to_swap": 20, "split_step": 5,
                "base_precision": "fp16_fast", "vram_gb": round(vram_gb, 1), **core}
    elif vram_mb >= 16384:
        return {"tier": "L3 高性能", "steps": 8, "blocks_to_swap": 20, "split_step": 4,
                "base_precision": "bf16", "vram_gb": round(vram_gb, 1), **core}
    elif vram_mb >= 12288:
        return {"tier": "L2 标准级", "steps": 6, "blocks_to_swap": 38, "split_step": 3,
                "base_precision": "bf16", "vram_gb": round(vram_gb, 1), **core}
    elif vram_mb >= 8192:
        return {"tier": "L1 入门级", "steps": 6, "blocks_to_swap": 40, "split_step": 3,
                "base_precision": "bf16", "vram_gb": round(vram_gb, 1), **core}
    else:
        return None


def query_system_ram_mb():
    """查询系统物理内存总量（MB），失败返回 None。"""
    try:
        output = subprocess.run(
            ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
            capture_output=True, text=True, timeout=10
        )
        if output.returncode != 0:
            return None
        # wmic 输出形如: TotalPhysicalMemory\n17179869184\n
        lines = [ln.strip() for ln in output.stdout.splitlines() if ln.strip()]
        # 跳过表头，取第一个数值
        for ln in lines[1:]:
            try:
                bytes_total = int(ln)
                return bytes_total // (1024 * 1024)
            except ValueError:
                continue
        return None
    except Exception as e:
        print(f"[警告] 查询系统内存失败: {e}")
        return None


def determine_vram_requirement(model_name):
    """根据模型名规格估算所需显存（MB）。

    规则:
      14B + fp16: 20480 MB（启用 lowvram 时降为 8192 MB）
      14B + fp8:  12288 MB
      5B:         8192 MB
      其他:       8192 MB
    本函数返回基础需求，lowvram 修正由调用方处理。
    """
    lower = model_name.lower()
    is_14b = "14b" in lower
    is_fp16 = "fp16" in lower
    is_fp8 = "fp8" in lower
    is_5b = "5b" in lower

    if is_14b and is_fp16:
        return 20480
    if is_14b and is_fp8:
        return 12288
    if is_5b:
        return 8192
    return 8192


def check_hardware_compatibility(model_name, architecture_scheme="single"):
    """检查 GPU 显存与系统内存是否满足所选模型的运行要求。

    通过则返回 {vram_mb, ram_mb, model_vram_required_mb, passed}，
    显存或内存不足返回 None（终止任务）。

    Args:
        model_name: 主模型名称
        architecture_scheme: 架构方案，"dual_serial"(方案A) 或 "single"(方案B)
            方案A 同时加载 HIGH+LOW 两个模型，显存需求更高
    """
    print("\n" + "-" * 40)
    print("步骤 3: 硬件兼容性检查")
    print("-" * 40)

    # 查询显存
    vram_mb = query_gpu_vram_mb()
    if vram_mb is None:
        print("[错误] 无法获取 GPU 显存信息，请确认已安装 NVIDIA 显卡及驱动。")
        return None
    print(f"GPU 显存: {vram_mb} MB ({vram_mb / 1024:.1f} GB)")

    # 查询内存
    ram_mb = query_system_ram_mb()
    if ram_mb is None:
        print("[错误] 无法获取系统内存信息。")
        return None
    print(f"系统内存: {ram_mb} MB ({ram_mb / 1024:.1f} GB)")

    # 确定所需显存
    required_mb = determine_vram_requirement(model_name)

    # 14B fp16 模型询问是否启用 lowvram
    lower = model_name.lower()
    if "14b" in lower and "fp16" in lower:
        ans = input("检测到 14B fp16 模型，是否已使用 --lowvram 启动 ComfyUI? (y/n，默认 n): ").strip().lower()
        if ans == "y":
            required_mb = 8192
            print("已确认启用 lowvram，显存需求降至 8192 MB")

    # 方案A（双采集器串行）：同时加载 HIGH+LOW 两个模型，显存需求翻倍
    if architecture_scheme == "dual_serial":
        dual_required_mb = required_mb * 2
        print(f"[方案A] 双采集器串行模式：同时加载 HIGH+LOW 两个模型，"
              f"显存需求约 {dual_required_mb} MB ({dual_required_mb / 1024:.1f} GB)")
        required_mb = dual_required_mb

    print(f"模型 '{model_name}' 所需显存: {required_mb} MB ({required_mb / 1024:.1f} GB)")

    # 显存校验
    if vram_mb < required_mb:
        print(f"[错误] 当前设备显存 {vram_mb / 1024:.1f} GB 不足以运行模型 {model_name} "
              f"(需要 {required_mb / 1024:.1f} GB)。请降低模型规格或启用 --lowvram 启动 ComfyUI")
        return None

    # 内存校验
    if ram_mb < MIN_RAM_MB:
        print(f"[错误] 当前设备内存 {ram_mb / 1024:.1f} GB 不足（最低需要 16 GB），"
              f"请增加物理内存后重试。")
        return None

    print("硬件兼容性检查通过。")
    return {
        "vram_mb": vram_mb,
        "ram_mb": ram_mb,
        "model_vram_required_mb": required_mb,
        "passed": True,
    }


def print_summary(models, params, hw, architecture_scheme="single"):
    """打印本次任务的模型、参数、硬件、架构方案汇总信息供用户确认。"""
    scheme_names = {"dual_serial": "方案A: HIGH+LOW双采集器串行（生产环境）",
                    "single": "方案B: 单一模型（简单场景）"}
    print("\n" + "=" * 60)
    print("任务预检汇总")
    print("=" * 60)
    print(f"扩散模型:    {models.get('diffusion_model')}")
    print(f"模型系列:    {models.get('model_family')}")
    print(f"架构方案:    {scheme_names.get(architecture_scheme, architecture_scheme)}")
    print(f"VAE:         {models.get('vae')}")
    print(f"CLIP:        {models.get('clip')}")
    print(f"CLIP_VISION: {models.get('clip_vision')}")
    ratio_names = {1: "9:16竖屏", 2: "16:9横屏", 3: "1:1方形"}
    res_names = {1: "480P", 2: "720P", 3: "1080P"}
    print(f"画面比例:    {ratio_names.get(params.get('ratio'), params.get('ratio'))}")
    print(f"分辨率:      {res_names.get(params.get('resolution'), params.get('resolution'))}")
    print(f"目标尺寸:    {params.get('target_width')}×{params.get('target_height')}")
    print(f"优化步数:    {params.get('steps')}")
    print(f"采样器:      {params.get('sampler_name')} / {params.get('scheduler')}")
    print(f"正面提示词:  {params.get('positive_prompt')}")
    print(f"负面提示词:  {params.get('negative_prompt')}")
    print(f"GPU 显存:    {hw.get('vram_mb')} MB (需要 {hw.get('model_vram_required_mb')} MB)")
    print(f"系统内存:    {hw.get('ram_mb')} MB")
    print("=" * 60)


def run_pre_task_inquiry():
    """任务预检反问环节主入口，不可跳过。

    依次执行模型选择、架构方案选择、参数收集、硬件检查，
    全部通过后返回合并字典（含 architecture_scheme 字段），
    任一环节失败返回 None。
    """
    print("=" * 60)
    print("视频生成任务预检环节（不可跳过）")
    print("=" * 60)

    # 步骤1: 模型选择
    models = query_and_select_models()
    if models is None:
        return None

    # 步骤1.5: 架构方案选择（方案A双采集器串行/方案B单一模型）
    architecture_scheme = collect_architecture_scheme(models.get("model_family", "Wan2.2"))
    if architecture_scheme is None:
        return None

    # 步骤2: 参数收集
    params = collect_generation_params()
    if params is None:
        return None

    # 步骤3: 硬件检查（方案A显存需求翻倍）
    hw = check_hardware_compatibility(models["diffusion_model"], architecture_scheme)
    if hw is None:
        return None

    # 汇总确认
    print_summary(models, params, hw, architecture_scheme)
    return {**models, **params, **hw, "architecture_scheme": architecture_scheme}


if __name__ == "__main__":
    run_pre_task_inquiry()
