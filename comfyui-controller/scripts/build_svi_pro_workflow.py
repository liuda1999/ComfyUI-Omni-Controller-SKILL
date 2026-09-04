"""
SVI Pro 逐段长视频工作流生成器 v2
HIGH/LOW 拆分为独立工作流，避免同时加载两个大模型
每段2个工作流（HIGH采样 + LOW细化），加融合共 5*2+1=11 个工作流
"""
import json
import os

# ===================== 配置区 =====================
UNET_HIGH = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
UNET_LOW = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
SVI_LORA = "SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors"
VAE_NAME = "Wan2_1_VAE_bf16.safetensors"
CLIP_NAME = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
INPUT_IMAGE = "1.png"

# 分辨率（L3档位20GB显存，SVI Pro架构KSamplerAdvanced无BlockSwap，需降低分辨率）
WIDTH = 352
HEIGHT = 640

STEPS = 6
STEPS2 = 2
CFG = 1.0
SAMPLER = "euler"
SCHEDULER = "simple"
SEED = 987654321

NUM_SEGMENTS = 5
FRAMES_PER_SEGMENT = 81
FPS = 20
OVERLAP = 5

PROMPTS = [
    "1秒: 角色开始缓慢原地转身360度，白色长发随转身飘动; 2秒: 继续转身，裙摆展开; 3秒: 完成转身面朝前方，缓慢伸出双手; 4秒: 双手在胸前做比心手势，微笑看向前方, camera slowly zooms in slightly",
    "5秒: 角色缓慢收回比心手势，双手放下; 6秒: 双手缓缓抬起至上身胸部区域; 7秒: 双手轻轻按摩上身胸部区域，动作柔和; 8秒: 继续按摩，身体微微晃动, camera maintains close-up",
    "9秒: 角色双手缓缓举过头顶，伸展身体; 10秒: 双手在头顶上方，准备跳跃; 11秒: 轻轻跳跃第一次，双脚离地; 12秒: 轻轻跳跃第二次，落地稳定, camera slowly zooms out to full body",
    "13秒: 角色自然摇摆身体，左右轻晃; 14秒: 继续摇摆，手臂自然摆动; 15秒: 摇摆3秒后，开始优雅抬起左腿; 16秒: 左腿抬高保持平衡，姿态优雅, camera maintains full body view",
    "17秒: 角色保持左腿抬起，身体稳定; 18秒: 缓慢放下左腿，恢复站立; 19秒: 自然站立，微微调整姿势; 20秒: 静止微笑，画面定格, camera slowly zooms in slightly"
]

NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，"
    "整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，"
    "画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，"
    "静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走，"
    "spinning, rotating, turning around repeatedly, 持续旋转, 肢体消失, 画面穿模"
)


def build_high_workflow(seg_idx, prev_latent_filename=None):
    """构建HIGH阶段工作流
    只加载HIGH模型，执行KSampler(0→STEPS2)，保存latent
    """
    wf = {}
    nid = [0]

    def next_id():
        nid[0] += 1
        return str(nid[0])

    # HIGH 模型链
    id_unet = next_id()
    wf[id_unet] = {"class_type": "UNETLoader", "inputs": {"unet_name": UNET_HIGH, "weight_dtype": "default"}}
    id_lora = next_id()
    wf[id_lora] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": [id_unet, 0], "lora_name": SVI_LORA, "strength_model": 1.0}}
    id_sage = next_id()
    wf[id_sage] = {"class_type": "PathchSageAttentionKJ", "inputs": {"model": [id_lora, 0], "sage_attention": "auto", "allow_compile": False}}
    id_torch = next_id()
    wf[id_torch] = {"class_type": "ModelPatchTorchSettings", "inputs": {"model": [id_sage, 0], "enable_fp16_accumulation": True}}
    high_ref = [id_torch, 0]

    # CLIP + VAE
    id_clip = next_id()
    wf[id_clip] = {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_NAME, "type": "wan"}}
    id_vae = next_id()
    wf[id_vae] = {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}}

    # 锚定
    id_img = next_id()
    wf[id_img] = {"class_type": "LoadImage", "inputs": {"image": INPUT_IMAGE}}
    id_resize = next_id()
    wf[id_resize] = {"class_type": "ImageResizeKJv2", "inputs": {
        "image": [id_img, 0], "width": WIDTH, "height": HEIGHT,
        "upscale_method": "lanczos", "keep_proportion": "stretch",
        "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 16
    }}
    id_vae_enc = next_id()
    wf[id_vae_enc] = {"class_type": "VAEEncode", "inputs": {"pixels": [id_resize, 0], "vae": [id_vae, 0]}}
    anchor_ref = [id_vae_enc, 0]

    # 提示词
    id_pos = next_id()
    wf[id_pos] = {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPTS[seg_idx], "clip": [id_clip, 0]}}
    id_neg = next_id()
    wf[id_neg] = {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE_PROMPT, "clip": [id_clip, 0]}}

    # SVI Pro 节点
    id_svi = next_id()
    svi_inputs = {
        "positive": [id_pos, 0], "negative": [id_neg, 0],
        "length": FRAMES_PER_SEGMENT, "anchor_samples": anchor_ref,
        "motion_latent_count": 0 if seg_idx == 0 else 1
    }
    if seg_idx > 0 and prev_latent_filename:
        id_load_latent = next_id()
        wf[id_load_latent] = {"class_type": "LoadLatent", "inputs": {"latent": prev_latent_filename}}
        svi_inputs["prev_samples"] = [id_load_latent, 0]
    wf[id_svi] = {"class_type": "WanImageToVideoSVIPro", "inputs": svi_inputs}

    # KSampler HIGH (0 → STEPS2, 保留残噪声)
    id_ks = next_id()
    wf[id_ks] = {"class_type": "KSamplerAdvanced", "inputs": {
        "model": high_ref, "add_noise": "enable", "noise_seed": SEED + seg_idx,
        "steps": STEPS, "cfg": CFG, "sampler_name": SAMPLER, "scheduler": SCHEDULER,
        "positive": [id_svi, 0], "negative": [id_svi, 1], "latent_image": [id_svi, 2],
        "start_at_step": 0, "end_at_step": STEPS2, "return_with_leftover_noise": "enable"
    }}

    # SaveLatent
    id_save = next_id()
    wf[id_save] = {"class_type": "SaveLatent", "inputs": {
        "samples": [id_ks, 0], "filename_prefix": f"c7_svi_seg{seg_idx+1}_high"
    }}

    return wf


def build_low_workflow(seg_idx, high_latent_filename):
    """构建LOW阶段工作流
    只加载LOW模型，加载HIGH的latent，执行KSampler(STEPS2→10000)，保存latent和视频
    """
    wf = {}
    nid = [0]

    def next_id():
        nid[0] += 1
        return str(nid[0])

    # LOW 模型链
    id_unet = next_id()
    wf[id_unet] = {"class_type": "UNETLoader", "inputs": {"unet_name": UNET_LOW, "weight_dtype": "default"}}
    id_lora = next_id()
    wf[id_lora] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": [id_unet, 0], "lora_name": SVI_LORA, "strength_model": 1.0}}
    id_sage = next_id()
    wf[id_sage] = {"class_type": "PathchSageAttentionKJ", "inputs": {"model": [id_lora, 0], "sage_attention": "auto", "allow_compile": False}}
    id_torch = next_id()
    wf[id_torch] = {"class_type": "ModelPatchTorchSettings", "inputs": {"model": [id_sage, 0], "enable_fp16_accumulation": True}}
    low_ref = [id_torch, 0]

    # CLIP + VAE
    id_clip = next_id()
    wf[id_clip] = {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_NAME, "type": "wan"}}
    id_vae = next_id()
    wf[id_vae] = {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}}

    # 提示词（LOW阶段需要相同的条件引导）
    id_pos = next_id()
    wf[id_pos] = {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPTS[seg_idx], "clip": [id_clip, 0]}}
    id_neg = next_id()
    wf[id_neg] = {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE_PROMPT, "clip": [id_clip, 0]}}

    # SVI Pro 节点（LOW阶段不需要anchor和prev，只需要positive/negative）
    # 注意：LOW阶段的latent_image是HIGH输出的latent
    id_load_high = next_id()
    wf[id_load_high] = {"class_type": "LoadLatent", "inputs": {"latent": high_latent_filename}}

    # SVI Pro在LOW阶段不需要重新生成latent，只需要positive/negative
    # 但KSamplerAdvanced需要positive/negative输入
    # LOW阶段直接用LoadLatent加载HIGH的输出作为latent_image
    id_ks = next_id()
    wf[id_ks] = {"class_type": "KSamplerAdvanced", "inputs": {
        "model": low_ref, "add_noise": "disable", "noise_seed": SEED + seg_idx,
        "steps": STEPS, "cfg": CFG, "sampler_name": SAMPLER, "scheduler": SCHEDULER,
        "positive": [id_pos, 0], "negative": [id_neg, 0], "latent_image": [id_load_high, 0],
        "start_at_step": STEPS2, "end_at_step": 10000, "return_with_leftover_noise": "disable"
    }}

    # VAEDecode → VHS_VideoCombine
    id_vae_dec = next_id()
    wf[id_vae_dec] = {"class_type": "VAEDecode", "inputs": {"samples": [id_ks, 0], "vae": [id_vae, 0]}}

    id_vhs = next_id()
    wf[id_vhs] = {"class_type": "VHS_VideoCombine", "inputs": {
        "images": [id_vae_dec, 0], "frame_rate": FPS, "loop_count": 0,
        "filename_prefix": f"c7_svi_seg{seg_idx+1}", "format": "video/h264-mp4",
        "pix_fmt": "yuv420p10le", "crf": 14, "pingpong": False, "save_output": True
    }}

    # SaveLatent (保存LOW的latent供下一段的HIGH使用)
    id_save = next_id()
    wf[id_save] = {"class_type": "SaveLatent", "inputs": {
        "samples": [id_ks, 0], "filename_prefix": f"c7_svi_seg{seg_idx+1}_low"
    }}

    return wf


def build_merge_workflow(segment_video_filenames):
    """构建融合工作流"""
    wf = {}
    nid = [0]

    def next_id():
        nid[0] += 1
        return str(nid[0])

    load_refs = []
    for i, fname in enumerate(segment_video_filenames):
        id_load = next_id()
        wf[id_load] = {"class_type": "VHS_LoadVideo", "inputs": {
            "video": fname, "force_rate": 0,
            "custom_width": 0, "custom_height": 0,
            "frame_load_cap": 0, "skip_first_frames": 0,
            "select_every_nth": 1, "format": "Wan"
        }}
        load_refs.append([id_load, 0])

    current_source = load_refs[0]
    for i in range(1, len(load_refs)):
        id_merge = next_id()
        wf[id_merge] = {"class_type": "ImageBatchExtendWithOverlap", "inputs": {
            "source_images": current_source, "new_images": load_refs[i],
            "overlap": OVERLAP, "overlap_side": "source", "overlap_mode": "linear_blend"
        }}
        current_source = [id_merge, 0]

    id_vhs = next_id()
    wf[id_vhs] = {"class_type": "VHS_VideoCombine", "inputs": {
        "images": current_source, "frame_rate": FPS, "loop_count": 0,
        "filename_prefix": "c7_svi_pro_20s_final", "format": "video/h264-mp4",
        "pix_fmt": "yuv420p10le", "crf": 14, "pingpong": False, "save_output": True
    }}

    return wf


def main():
    print("=" * 60)
    print("SVI Pro 逐段长视频工作流生成器 v2 (HIGH/LOW 拆分)")
    print("=" * 60)
    print(f"分辨率: {WIDTH}x{HEIGHT}, 段数: {NUM_SEGMENTS}, 每段: {FRAMES_PER_SEGMENT}帧")
    print(f"总帧数: {NUM_SEGMENTS * FRAMES_PER_SEGMENT}, 总时长: {NUM_SEGMENTS * FRAMES_PER_SEGMENT / FPS:.2f}秒")
    print(f"采样: steps={STEPS}({STEPS2}+{STEPS-STEPS2}), cfg={CFG}, {SAMPLER}, {SCHEDULER}")
    print()

    assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

    # 生成5段×2步=10个工作流
    for seg in range(NUM_SEGMENTS):
        # HIGH工作流
        prev_latent = f"AUTO_DETECT_SEG{seg}_LOW" if seg > 0 else None
        wf_high = build_high_workflow(seg, prev_latent)
        fname_high = f"c7_svi_seg{seg+1}_high.json"
        with open(os.path.join(assets_dir, fname_high), "w", encoding="utf-8") as f:
            json.dump(wf_high, f, ensure_ascii=False, indent=2)
        print(f"✓ {fname_high}: {len(wf_high)} 节点")

        # LOW工作流
        wf_low = build_low_workflow(seg, f"AUTO_DETECT_SEG{seg+1}_HIGH")
        fname_low = f"c7_svi_seg{seg+1}_low.json"
        with open(os.path.join(assets_dir, fname_low), "w", encoding="utf-8") as f:
            json.dump(wf_low, f, ensure_ascii=False, indent=2)
        print(f"✓ {fname_low}: {len(wf_low)} 节点")

    # 融合工作流
    seg_videos = [f"AUTO_DETECT_SEG{i+1}_VIDEO" for i in range(NUM_SEGMENTS)]
    merge_wf = build_merge_workflow(seg_videos)
    with open(os.path.join(assets_dir, "c7_svi_merge.json"), "w", encoding="utf-8") as f:
        json.dump(merge_wf, f, ensure_ascii=False, indent=2)
    print(f"✓ c7_svi_merge.json: {len(merge_wf)} 节点")

    print(f"\n总计: {NUM_SEGMENTS*2+1} 个工作流文件")
    print(f"执行顺序: seg1_high → seg1_low → seg2_high → seg2_low → ... → seg5_low → merge")


if __name__ == "__main__":
    main()
