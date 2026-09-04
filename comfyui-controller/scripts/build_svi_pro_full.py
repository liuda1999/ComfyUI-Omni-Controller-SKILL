"""
构建 SVI Pro 长视频 API 工作流（严格按原工作流结构）。

核心设计（源自原工作流深度研读）：
1. 两个 UNETLoader 加载同一模型文件，分别构建 HIGH/LOW 两条独立模型链路
2. HIGH 链路：UNETLoader → LoraLoader → SageAttention → TorchSettings → high_model
3. LOW 链路：UNETLoader → LoraLoader → SageAttention → TorchSettings → low_model
4. 每段 KSamplerAdvanced HIGH 用 high_model，LOW 用 low_model
5. 段间通过 prev_samples 传递 latent（motion_latent_count=1）
6. ImageBatchExtendWithOverlap(overlap=5, linear_blend) 链式拼接

关键修正（对比之前版本）：
- 模型文件改用 Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors（避免_scaled_KJ触发requantize OOM）
- 恢复 HIGH/LOW 双独立模型链路（之前错误合并为单一链路）
- 分辨率 848×480（480p，16:9，16倍数）
- 帧数 81（原工作流值），5段×81-5×4=385帧/20fps≈19.25秒
- cfg 按段递增（段1=1, 段2=2, 段3-5=2.5），LOW 统一为 1
- ImageResizeKJv2 添加 device="cpu"（原工作流设置，节省GPU显存）
"""
import json
import os

# ============ 参数配置（严格对齐原工作流） ============
WIDTH = 480          # 480p 9:16 竖屏 (原图1080x1920)
HEIGHT = 848         # 848是16的倍数，比例0.567接近9:16的0.5625
LENGTH = 81          # 每段帧数（原工作流值）
STEPS = 6            # 总步数（原工作流值）
STEPS2 = 2           # split_step（HIGH执行0-2，LOW执行2-6）
OVERLAP = 5          # 段间重叠帧数
FRAME_RATE = 20      # 输出帧率
SEED = 214           # 原工作流 noise_seed 值
MOTION_LATENT_COUNT = 1  # 段间传递的motion latent数

# 模型配置（关键修正：使用原工作流的 Remix 模型，不用 _scaled_KJ 格式）
MODEL_FILE = "Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors"
VAE_FILE = "comfy-wan_2.1_vae.safetensors"
CLIP_FILE = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
LORA_FILE = "SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors"
LORA_STRENGTH = 1.0
WEIGHT_DTYPE = "default"  # 原工作流值，不运行时量化

# 每段 HIGH 阶段的 cfg 值（原工作流按段递增）
CFG_HIGH_PER_SEG = [1.0, 2.0, 2.5, 2.5, 2.5]
CFG_LOW = 1.0  # LOW 阶段统一 cfg

# 输入图片
INPUT_IMAGE = "c7_1.png"

# ============ 提示词（5段） ============
POSITIVE_PROMPTS = [
    # 段1: 转身比心
    "一个漂亮的女孩，站在原地，缓慢转身360度，然后面向前方伸出双手做比心手势，"
    "微笑表情，自然流畅的动作，光线柔和，高清画质，电影级质感",
    # 段2: 完成比心保持姿态
    "一个漂亮的女孩，保持比心手势姿态，微笑着看向镜头，"
    "身体轻微晃动，呼吸自然，光线柔和，高清画质，电影级质感",
    # 段3: 按摩上身
    "一个漂亮的女孩，收回比心手势，双手缓慢抬起按摩上身胸部区域，"
    "动作轻柔自然，表情放松，光线柔和，高清画质，电影级质感",
    # 段4: 举手跳跃
    "一个漂亮的女孩，双手举过头顶，然后轻轻跳跃2次，"
    "动作轻盈，表情愉悦，光线柔和，高清画质，电影级质感",
    # 段5: 摇摆抬腿
    "一个漂亮的女孩，自然摇摆身体，然后优雅的抬起左腿，"
    "动作优美流畅，表情自信，光线柔和，高清画质，电影级质感",
]

NEGATIVE_PROMPT = (
    "色调艳丽，过曝，静态，细节模糊不清，字幕，风格，作品，画作，画面，静止，"
    "整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指，"
    "画得不好的手部，画得不好的脸部，畸形的，毁容的，形态畸形的肢体，手指融合，"
    "静止不动的画面，杂乱的背景，三条腿，背景人很多，倒着走"
)

# ============ 构建 API 工作流 ============
def build_workflow():
    wf = {}

    # ===== HIGH 模型链路（节点2→10→7→8） =====
    wf["g_unet_high"] = {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": MODEL_FILE, "weight_dtype": WEIGHT_DTYPE}
    }
    wf["g_lora_high"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": ["g_unet_high", 0],
            "lora_name": LORA_FILE,
            "strength_model": LORA_STRENGTH
        }
    }
    wf["g_sage_high"] = {
        "class_type": "PathchSageAttentionKJ",
        "inputs": {
            "model": ["g_lora_high", 0],
            "sage_attention": "auto",
            "allow_compile": False
        }
    }
    wf["g_torch_high"] = {
        "class_type": "ModelPatchTorchSettings",
        "inputs": {
            "model": ["g_sage_high", 0],
            "enable_fp16_accumulation": True
        }
    }

    # ===== LOW 模型链路（节点3→34→6→9） =====
    # 加载同一模型文件，ComfyUI 缓存复用原始权重，不会重复占用显存
    wf["g_unet_low"] = {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": MODEL_FILE, "weight_dtype": WEIGHT_DTYPE}
    }
    wf["g_lora_low"] = {
        "class_type": "LoraLoaderModelOnly",
        "inputs": {
            "model": ["g_unet_low", 0],
            "lora_name": LORA_FILE,
            "strength_model": LORA_STRENGTH
        }
    }
    wf["g_sage_low"] = {
        "class_type": "PathchSageAttentionKJ",
        "inputs": {
            "model": ["g_lora_low", 0],
            "sage_attention": "auto",
            "allow_compile": False
        }
    }
    wf["g_torch_low"] = {
        "class_type": "ModelPatchTorchSettings",
        "inputs": {
            "model": ["g_sage_low", 0],
            "enable_fp16_accumulation": True
        }
    }

    # ===== 全局共享节点 =====
    wf["g_clip"] = {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": CLIP_FILE, "type": "wan"}
    }
    wf["g_vae"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": VAE_FILE}
    }
    wf["g_loadimage"] = {
        "class_type": "LoadImage",
        "inputs": {"image": INPUT_IMAGE}
    }
    # ImageResizeKJv2 - device="cpu" 在CPU上resize，节省GPU显存（原工作流设置）
    wf["g_resize"] = {
        "class_type": "ImageResizeKJv2",
        "inputs": {
            "image": ["g_loadimage", 0],
            "width": WIDTH,
            "height": HEIGHT,
            "upscale_method": "lanczos",
            "keep_proportion": "crop",
            "pad_color": "0, 0, 0",
            "crop_position": "center",
            "divisible_by": 16,
            "device": "cpu"
        }
    }
    wf["g_vaeencode"] = {
        "class_type": "VAEEncode",
        "inputs": {
            "pixels": ["g_resize", 0],
            "vae": ["g_vae", 0]
        }
    }

    # ===== 5段采样 =====
    prev_low_latent_ref = None  # 前段 LOW 输出的 latent 引用

    for seg_idx in range(5):
        seg_prefix = f"seg{seg_idx+1}"

        # CLIPTextEncode (正/负)
        wf[f"{seg_prefix}_clip_pos"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["g_clip", 0],
                "text": POSITIVE_PROMPTS[seg_idx]
            }
        }
        wf[f"{seg_prefix}_clip_neg"] = {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "clip": ["g_clip", 0],
                "text": NEGATIVE_PROMPT
            }
        }

        # WanImageToVideoSVIPro
        svi_inputs = {
            "positive": [f"{seg_prefix}_clip_pos", 0],
            "negative": [f"{seg_prefix}_clip_neg", 0],
            "anchor_samples": ["g_vaeencode", 0],
            "length": LENGTH,
            "motion_latent_count": MOTION_LATENT_COUNT if seg_idx > 0 else 0
        }
        if prev_low_latent_ref is not None:
            svi_inputs["prev_samples"] = prev_low_latent_ref
        wf[f"{seg_prefix}_svi"] = {
            "class_type": "WanImageToVideoSVIPro",
            "inputs": svi_inputs
        }

        # KSamplerAdvanced (HIGH) - 用 high_model
        # add_noise=enable, start=0, end=steps2, return_leftover=enable
        wf[f"{seg_prefix}_ks_high"] = {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["g_torch_high", 0],
                "positive": [f"{seg_prefix}_svi", 0],
                "negative": [f"{seg_prefix}_svi", 1],
                "latent_image": [f"{seg_prefix}_svi", 2],
                "add_noise": "enable",
                "noise_seed": SEED,
                "steps": STEPS,
                "cfg": CFG_HIGH_PER_SEG[seg_idx],
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": 0,
                "end_at_step": STEPS2,
                "return_with_leftover_noise": "enable"
            }
        }

        # KSamplerAdvanced (LOW) - 用 low_model
        # add_noise=disable, start=steps2, end=10000, return_leftover=disable
        wf[f"{seg_prefix}_ks_low"] = {
            "class_type": "KSamplerAdvanced",
            "inputs": {
                "model": ["g_torch_low", 0],
                "positive": [f"{seg_prefix}_svi", 0],
                "negative": [f"{seg_prefix}_svi", 1],
                "latent_image": [f"{seg_prefix}_ks_high", 0],
                "add_noise": "disable",
                "noise_seed": SEED,
                "steps": STEPS,
                "cfg": CFG_LOW,
                "sampler_name": "euler",
                "scheduler": "simple",
                "start_at_step": STEPS2,
                "end_at_step": 10000,
                "return_with_leftover_noise": "disable"
            }
        }

        # 更新前段 latent 引用
        prev_low_latent_ref = [f"{seg_prefix}_ks_low", 0]

        # VAEDecode
        wf[f"{seg_prefix}_vaedecode"] = {
            "class_type": "VAEDecode",
            "inputs": {
                "samples": [f"{seg_prefix}_ks_low", 0],
                "vae": ["g_vae", 0]
            }
        }

    # ===== 图像拼接链（ImageBatchExtendWithOverlap） =====
    wf["merge1"] = {
        "class_type": "ImageBatchExtendWithOverlap",
        "inputs": {
            "source_images": ["seg1_vaedecode", 0],
            "new_images": ["seg2_vaedecode", 0],
            "overlap": OVERLAP,
            "overlap_side": "source",
            "overlap_mode": "linear_blend"
        }
    }
    wf["merge2"] = {
        "class_type": "ImageBatchExtendWithOverlap",
        "inputs": {
            "source_images": ["merge1", 2],
            "new_images": ["seg3_vaedecode", 0],
            "overlap": OVERLAP,
            "overlap_side": "source",
            "overlap_mode": "linear_blend"
        }
    }
    wf["merge3"] = {
        "class_type": "ImageBatchExtendWithOverlap",
        "inputs": {
            "source_images": ["merge2", 2],
            "new_images": ["seg4_vaedecode", 0],
            "overlap": OVERLAP,
            "overlap_side": "source",
            "overlap_mode": "linear_blend"
        }
    }
    wf["final_merge"] = {
        "class_type": "ImageBatchExtendWithOverlap",
        "inputs": {
            "source_images": ["merge3", 2],
            "new_images": ["seg5_vaedecode", 0],
            "overlap": OVERLAP,
            "overlap_side": "source",
            "overlap_mode": "linear_blend"
        }
    }

    # 最终视频输出（原工作流参数：pix_fmt=yuv420p, crf=20）
    wf["final_video"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["final_merge", 2],
            "frame_rate": FRAME_RATE,
            "loop_count": 0,
            "filename_prefix": "c7_svi_final_20s",
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 20,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True
        }
    }

    return wf


def main():
    wf = build_workflow()
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets", "svi_pro_long_video_v1.0.0.json"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)

    total_frames = LENGTH * 5 - OVERLAP * 4
    print(f"工作流已生成: {output_path}")
    print(f"节点总数: {len(wf)}")
    print(f"分辨率: {WIDTH}x{HEIGHT} (480p)")
    print(f"每段帧数: {LENGTH}")
    print(f"总帧数: {total_frames} (5段x{LENGTH}帧 - {OVERLAP}x4重叠)")
    print(f"总时长: {total_frames/FRAME_RATE:.2f}秒 @{FRAME_RATE}fps")
    print(f"采样步数: HIGH 0-{STEPS2}, LOW {STEPS2}-{STEPS} (总{STEPS}步)")
    print(f"模型: {MODEL_FILE}")
    print(f"LoRA: {LORA_FILE} (strength={LORA_STRENGTH})")
    print(f"HIGH/LOW: 双独立模型链路（加载同一文件，ComfyUI缓存复用）")
    print(f"优化节点: PathchSageAttentionKJ + ModelPatchTorchSettings + LoraLoaderModelOnly")


if __name__ == "__main__":
    main()
