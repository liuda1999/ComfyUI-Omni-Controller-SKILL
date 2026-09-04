"""
C5视频生成任务 - v11版（回归官方标准I2V）
基于官方文档和示例工作流调研后的修正方案:

核心修正:
  1. 帧数: 81帧@24fps=3.375秒 (训练原生长度, 不触发RoPE周期性折返)
  2. 模式: 标准I2V (fun_or_fl2v_model=false, 适用Wan2_2-I2V-A14B标准模型)
  3. 多图: start_image=1.png + end_image=2.png (参考, 不强制末帧)
  4. CLIP: 单图1.png (角色约束)
  5. rope_function="comfy" (官方推荐, 非chunked)
  6. riflex_freq_index=0 (81帧在训练范围内, 无需RIFLEX)
  7. 分辨率: 480x640 (3:4, 遵从1.png比例)

动作精简(3.4秒内): 转身→深蹲→起身→开始走向门口
  - 3.4秒只能容纳1-2个核心动作
  - 避免动作密度过高导致重复

参考官方示例: wanvideo2_2_I2V_A14B_example_WIP.json
  - 81帧, 832x480, fun_or_fl2v_model=false, riflex=0, rope=comfy
"""
import urllib.request
import json
import time
import sys
import os

COMFYUI_URL = "http://127.0.0.1:3198"

# v11参数 (回归官方标准)
WIDTH = 480
HEIGHT = 640  # 3:4比例, 遵从1.png
NUM_FRAMES = 81  # 官方训练原生长度, 3.375秒@24fps
STEPS = 6  # 官方示例使用6步 (配合lightx2v蒸馏)
SPLIT_STEP = 3  # 官方示例: HIGH 0-3, LOW 3-6
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.0  # 官方示例使用0
SEED = int(time.time()) % 1000000

# 模型
HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

# v11提示词: 3.4秒内的核心动作 (转身→深蹲→起身→开始走向门口)
# 动作密度匹配时长, 避免重复
POSITIVE_PROMPT = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor corridor scene, woman standing in corridor, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman does a 360 degree clockwise spin in place, "
    "then slowly lowers into a deep sumo squat with legs spread wide apart, "
    "low angle shot from below looking up at the character during the squat, "
    "pauses holding the squat pose briefly, then stands back up straight, "
    "then turns and starts walking forward down the corridor, "
    "smooth body motion, natural continuous movement, "
    "consistent character throughout"
)

NEGATIVE_PROMPT = (
    "面部崩坏，五官错位，表情扭曲，肢体畸形，多手多脚，关节错位，"
    "服装穿模，转场跳变，人物变脸，服装突变，场景错乱，"
    "动作僵硬卡顿，画面闪烁，跳帧，人物漂移，比例失调，"
    "运镜剧烈晃动，人物出框，悬浮物体，违背人体力学的违和动作，"
    "色调艳丽，过曝，曝光变化，亮度突变，背景亮度变化, "
    "exposure drift, lighting changes, overexposed, "
    "background replacement, background changing, different background, "
    "静态，细节模糊不清，字幕，最差质量，低质量，JPEG压缩残留， "
    "丑陋的，残缺的，多余的手指，畸形的，毁容的，手指融合， "
    "杂乱的背景，三条腿，腿部消失，肢体断裂，肢体溶解， "
    "多余肢体，缺失肢体，motion blur, frame skipping, "
    "distorted body, deformed limbs, floating hair, "
    "camera pan, camera tilt, camera zoom, camera shake, "
    "face changing, character drift, inconsistent appearance, "
    "blurry, low detail, pixelated, compressed artifacts, "
    "action repeating, motion repeating, looping animation, "
    "returning to start position, walking backwards, reversing"
)


def build_workflow():
    """构建v11标准I2V工作流 (回归官方配置)

    关键配置 (对齐官方示例):
    - fun_or_fl2v_model=false (标准I2V, 非FLF2V)
    - num_frames=81 (训练原生长度)
    - riflex_freq_index=0 (无需RIFLEX)
    - rope_function="comfy" (官方推荐)
    - steps=6, split_step=3 (官方蒸馏配置)
    - noise_aug_strength=0 (官方示例)
    """
    return {
        # 加载1.png (start_image + CLIP参考)
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_1.png"}
        },
        "resize_start_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_start_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT,
                "crop": "disabled"
            }
        },
        # 加载2.png (end_image参考, 标准I2V模式下作为末尾参考)
        "load_end_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_2.png"}
        },
        "resize_end_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_end_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT,
                "crop": "disabled"
            }
        },
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
        # CLIP单图编码 (1.png角色约束)
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_start_image", 0],
                "strength_1": 1.0,
                "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "average",
                "force_offload": True
            }
        },
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {"model_name": VAE_MODEL, "precision": "bf16"}
        },
        # 标准I2V编码 (fun_or_fl2v_model=false)
        # start_image=1.png, end_image=2.png (作为末尾参考)
        "i2v_encode": {
            "class_type": "WanVideoImageToVideoEncode",
            "inputs": {
                "width": WIDTH, "height": HEIGHT,
                "num_frames": NUM_FRAMES,
                "noise_aug_strength": NOISE_AUG,
                "start_latent_strength": 1.0,
                "end_latent_strength": 1.0,
                "force_offload": True,
                "vae": ["vae_loader", 0],
                "clip_embeds": ["clip_vision_encode", 0],
                "start_image": ["resize_start_image", 0],
                "end_image": ["resize_end_image", 0],
                "fun_or_fl2v_model": False  # 标准I2V模式
            }
        },
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {"model_name": T5_MODEL, "precision": "bf16"}
        },
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": POSITIVE_PROMPT,
                "negative_prompt": NEGATIVE_PROMPT,
                "t5": ["t5_loader", 0],
                "force_offload": True
            }
        },
        # HIGH模型 (主结构)
        "high_model_loader": {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": HIGH_MODEL, "base_precision": "bf16",
                "quantization": "fp8_e4m3fn_scaled",
                "load_device": "offload_device", "attention_mode": "sageattn"
            }
        },
        "block_swap": {
            "class_type": "WanVideoBlockSwap",
            "inputs": {"blocks_to_swap": BLOCKS_TO_SWAP, "offload_img_emb": False, "offload_txt_emb": False}
        },
        "high_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {"model": ["high_model_loader", 0], "block_swap_args": ["block_swap", 0]}
        },
        "high_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {"lora": LORA_MODEL, "strength": 3.0, "merge_loras": False}
        },
        "high_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {"model": ["high_set_blockswap", 0], "lora": ["high_lora_select", 0]}
        },
        # 动态CFG调度 (官方风格: 高CFG启动, 快速降到1)
        "cfg_schedule": {
            "class_type": "CreateCFGScheduleFloatList",
            "inputs": {
                "steps": STEPS, "cfg_scale_start": 2.0, "cfg_scale_end": 2.0,
                "interpolation": "linear", "start_percent": 0.0, "end_percent": 0.01
            }
        },
        "steps_const": {"class_type": "INTConstant", "inputs": {"value": STEPS}},
        "split_step_const": {"class_type": "INTConstant", "inputs": {"value": SPLIT_STEP}},
        # HIGH采样器 (0-3步)
        "high_sampler": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["high_set_loras", 0],
                "image_embeds": ["i2v_encode", 0],
                "text_embeds": ["text_encode", 0],
                "steps": ["steps_const", 0],
                "cfg": ["cfg_schedule", 0],
                "shift": SHIFT, "seed": SEED,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "rope_function": "comfy",  # 官方推荐
                "riflex_freq_index": 0,  # 81帧无需RIFLEX
                "start_step": 0,
                "end_step": ["split_step_const", 0]
            }
        },
        # LOW模型 (细化)
        "low_model_loader": {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": LOW_MODEL, "base_precision": "bf16",
                "quantization": "fp8_e4m3fn_scaled",
                "load_device": "offload_device", "attention_mode": "sageattn"
            }
        },
        "low_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {"model": ["low_model_loader", 0], "block_swap_args": ["block_swap", 0]}
        },
        "low_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {"lora": LORA_MODEL, "strength": 1.0, "merge_loras": False}
        },
        "low_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {"model": ["low_set_blockswap", 0], "lora": ["low_lora_select", 0]}
        },
        # LOW采样器 (3-6步)
        "low_sampler": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["low_set_loras", 0],
                "image_embeds": ["i2v_encode", 0],
                "text_embeds": ["text_encode", 0],
                "steps": ["steps_const", 0],
                "cfg": 1.0, "shift": SHIFT, "seed": SEED,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "rope_function": "comfy",  # 官方推荐
                "riflex_freq_index": 0,  # 81帧无需RIFLEX
                "samples": ["high_sampler", 0],
                "start_step": ["split_step_const", 0],
                "end_step": -1
            }
        },
        "decode": {
            "class_type": "WanVideoDecode",
            "inputs": {
                "vae": ["vae_loader", 0],
                "samples": ["low_sampler", 0],
                "enable_vae_tiling": False,
                "tile_x": 272, "tile_y": 272,
                "tile_stride_x": 144, "tile_stride_y": 144
            }
        },
        "video_combine": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c5_v11_{int(time.time())}",
                "format": "video/h264-mp4",
                "pingpong": False, "save_output": True,
                "crf": 14, "pix_fmt": "yuv420p10le"
            }
        }
    }


def queue_prompt(prompt_workflow):
    data = json.dumps({"prompt": prompt_workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req, timeout=30)
    return json.loads(resp.read())


def get_history(prompt_id):
    resp = urllib.request.urlopen(
        f"{COMFYUI_URL}/history/{prompt_id}", timeout=30
    )
    return json.loads(resp.read())


def main():
    print("=" * 60)
    print("C5视频生成任务 - v11版 (回归官方标准I2V)")
    print(f"分辨率: {WIDTH}x{HEIGHT} (3:4, 遵从1.png)")
    print(f"帧数: {NUM_FRAMES} (3.375秒@24fps, 训练原生长度)")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-{STEPS})")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print(f"v11核心修正:")
    print(f"  - 81帧(训练原生, 不触发RoPE周期性折返)")
    print(f"  - 标准I2V模式 (fun_or_fl2v_model=false)")
    print(f"  - rope_function=comfy (官方推荐)")
    print(f"  - riflex_freq_index=0 (无需RIFLEX)")
    print(f"  - 动作: 转身→深蹲→起身→开始走向门口")
    print(f"编码: crf=14, pix_fmt=yuv420p10le")
    print("=" * 60)

    print("\n构建工作流...")
    workflow = build_workflow()
    print(f"  节点数: {len(workflow)}")

    print("\n提交工作流到ComfyUI...")
    try:
        result = queue_prompt(workflow)
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            print(f"错误: {result}")
            sys.exit(1)
        print(f"  prompt_id: {prompt_id}")
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.read().decode()}")
        sys.exit(1)

    print(f"\n等待完成...")
    start_time = time.time()
    while True:
        elapsed = time.time() - start_time
        try:
            history = get_history(prompt_id)
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in outputs.items():
                    if "gifs" in node_output:
                        for gif in node_output["gifs"]:
                            filename = gif.get("filename", "")
                            subfolder = gif.get("subfolder", "")
                            filepath = os.path.join("E:/comfyui-cli/output", subfolder, filename)
                            elapsed_min = elapsed / 60
                            if os.path.exists(filepath):
                                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                                print(f"\n完成! 耗时: {elapsed_min:.1f}分钟")
                                print(f"  输出: {filepath} ({size_mb:.2f} MB)")
                                print("=" * 60)
                            return
            print(f"  等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  查询超时, 重试... ({e})")
        time.sleep(30)


if __name__ == "__main__":
    main()
