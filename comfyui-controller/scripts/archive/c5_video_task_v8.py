"""
C5多图视频生成任务 - V19架构 v8版（基于v3架构修复两个问题）
v3效果最好，但存在：1.提示词执行两遍 2.深蹲姿势不对
v8修复方案（保持v3架构不变，只改两个地方）：
1. 提示词执行两遍 → 启用RIFLEX: riflex_freq_index=6（v3错误设为0，禁用了RIFLEX）
   - 根因：241帧超出模型训练长度，riflex=0导致时间编码循环，动作执行两遍
   - 修复：riflex_freq_index=6防止长视频时间循环
2. 深蹲姿势不对 → 优化深蹲提示词描述
   - 旧：performs a deep squat with legs spread wide and stands back up
   - 新：slowly lowers into a deep sumo squat with legs spread wide apart,
         pauses holding the squat pose briefly, then stands back up straight
保持v3架构（效果最好的部分）：
  - FLF2V模式: fun_or_fl2v_model=true
  - 双图: start_image=图1走廊, end_image=图2教室
  - CLIP融合: combine_embeds="concat"
  - 统一SEED
  - 241帧@24fps=10秒
  - 分辨率480x768 (5:8, 遵从1.png比例)
编码：crf=14, pix_fmt=yuv420p10le
"""
import urllib.request
import json
import time
import sys
import os

COMFYUI_URL = "http://127.0.0.1:3198"

# v8参数（基于v3，修复riflex）
WIDTH = 480
HEIGHT = 768  # 5:8比例, 遵从1.png比例
NUM_FRAMES = 241  # 4n+1, 10秒@24fps
STEPS = 8
SPLIT_STEP = 4
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.1
SEED = int(time.time()) % 1000000

# 模型
HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

# 提示词（v3基础 + 优化深蹲描述）
POSITIVE_PROMPT = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, following camera during transition, "
    "indoor corridor scene, woman standing in corridor, "
    "subject appearance clear, same person throughout the video, consistent appearance, consistent clothing, "
    "the woman does a 360 degree clockwise spin in place, "
    "then slowly lowers into a deep sumo squat with legs spread wide apart, "
    "low angle shot from below looking up at the character during the squat, "
    "pauses holding the squat pose briefly, then stands back up straight, "
    "then walks forward through a doorway from corridor to classroom in a single continuous motion, "
    "then continues walking to the center of the classroom, "
    "then pulls out a chair with one hand, "
    "finally sits down on the chair and settles in a seated position, "
    "smooth body motion, natural continuous movement, single continuous take, "
    "consistent character throughout"
)

NEGATIVE_PROMPT = (
    "面部崩坏，五官错位，表情扭曲，肢体畸形，多手多脚，关节错位，"
    "服装穿模，桌椅穿帮，转场跳变，人物变脸，服装突变，场景错乱，"
    "动作僵硬卡顿，画面闪烁，跳帧，人物漂移，比例失调，"
    "运镜剧烈晃动，人物出框，悬浮物体，违背人体力学的违和动作，场景元素错位, "
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
    "blurry, low detail, pixelated, compressed artifacts"
)


def build_workflow():
    """构建V19架构FLF2V多图生成工作流（v8: v3架构 + riflex=6）"""
    workflow = {
        # 1. 加载起始图（走廊场景，人物主体）
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_1.png"}
        },
        # 2. 加载结束图（教室场景，目标场景）
        "load_end_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_2.png"}
        },
        # 3. 起始图resize
        "resize_start_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_start_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH,
                "height": HEIGHT,
                "crop": "disabled"
            }
        },
        # 4. 结束图resize
        "resize_end_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_end_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH,
                "height": HEIGHT,
                "crop": "disabled"
            }
        },
        # 5. CLIP Vision加载
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
        # 6. CLIP Vision编码（FLF2V: combine_embeds="concat"）
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_start_image", 0],
                "image_2": ["resize_end_image", 0],
                "strength_1": 1.0,
                "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "concat",
                "force_offload": True
            }
        },
        # 7. VAE加载
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": VAE_MODEL,
                "precision": "bf16"
            }
        },
        # 8. I2V编码（FLF2V模式: fun_or_fl2v_model=true）
        "i2v_encode": {
            "class_type": "WanVideoImageToVideoEncode",
            "inputs": {
                "width": WIDTH,
                "height": HEIGHT,
                "num_frames": NUM_FRAMES,
                "noise_aug_strength": NOISE_AUG,
                "start_latent_strength": 1.0,
                "end_latent_strength": 1.0,
                "force_offload": True,
                "vae": ["vae_loader", 0],
                "clip_embeds": ["clip_vision_encode", 0],
                "start_image": ["resize_start_image", 0],
                "end_image": ["resize_end_image", 0],
                "fun_or_fl2v_model": True
            }
        },
        # 9. T5加载
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": T5_MODEL,
                "precision": "bf16"
            }
        },
        # 10. 文本编码
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": POSITIVE_PROMPT,
                "negative_prompt": NEGATIVE_PROMPT,
                "t5": ["t5_loader", 0],
                "force_offload": True
            }
        },
        # 11. HIGH模型加载
        "high_model_loader": {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": HIGH_MODEL,
                "base_precision": "bf16",
                "quantization": "fp8_e4m3fn_scaled",
                "load_device": "offload_device",
                "attention_mode": "sageattn"
            }
        },
        # 12. BlockSwap配置
        "block_swap": {
            "class_type": "WanVideoBlockSwap",
            "inputs": {
                "blocks_to_swap": BLOCKS_TO_SWAP,
                "offload_img_emb": False,
                "offload_txt_emb": False
            }
        },
        # 13. HIGH BlockSwap
        "high_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["high_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        # 14. HIGH LoRA选择
        "high_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 3.0,
                "merge_loras": False
            }
        },
        # 15. HIGH LoRA应用
        "high_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["high_set_blockswap", 0],
                "lora": ["high_lora_select", 0]
            }
        },
        # 16. 动态CFG调度
        "cfg_schedule": {
            "class_type": "CreateCFGScheduleFloatList",
            "inputs": {
                "steps": STEPS,
                "cfg_scale_start": 2.0,
                "cfg_scale_end": 2.0,
                "interpolation": "linear",
                "start_percent": 0.0,
                "end_percent": 0.01
            }
        },
        # 17. 共享steps
        "steps_const": {
            "class_type": "INTConstant",
            "inputs": {"value": STEPS}
        },
        # 18. 共享split_step
        "split_step_const": {
            "class_type": "INTConstant",
            "inputs": {"value": SPLIT_STEP}
        },
        # 19. HIGH采样器（v8修复: riflex_freq_index=6）
        "high_sampler": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["high_set_loras", 0],
                "image_embeds": ["i2v_encode", 0],
                "text_embeds": ["text_encode", 0],
                "steps": ["steps_const", 0],
                "cfg": ["cfg_schedule", 0],
                "shift": SHIFT,
                "seed": SEED,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "rope_function": "comfy_chunked",
                "riflex_freq_index": 6,
                "start_step": 0,
                "end_step": ["split_step_const", 0]
            }
        },
        # 20. LOW模型加载
        "low_model_loader": {
            "class_type": "WanVideoModelLoader",
            "inputs": {
                "model": LOW_MODEL,
                "base_precision": "bf16",
                "quantization": "fp8_e4m3fn_scaled",
                "load_device": "offload_device",
                "attention_mode": "sageattn"
            }
        },
        # 21. LOW BlockSwap
        "low_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["low_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        # 22. LOW LoRA选择
        "low_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 1.0,
                "merge_loras": False
            }
        },
        # 23. LOW LoRA应用
        "low_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["low_set_blockswap", 0],
                "lora": ["low_lora_select", 0]
            }
        },
        # 24. LOW采样器（v8修复: riflex_freq_index=6）
        "low_sampler": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["low_set_loras", 0],
                "image_embeds": ["i2v_encode", 0],
                "text_embeds": ["text_encode", 0],
                "steps": ["steps_const", 0],
                "cfg": 1.0,
                "shift": SHIFT,
                "seed": SEED,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "rope_function": "comfy_chunked",
                "riflex_freq_index": 6,
                "samples": ["high_sampler", 0],
                "start_step": ["split_step_const", 0],
                "end_step": -1
            }
        },
        # 25. VAE解码
        "decode": {
            "class_type": "WanVideoDecode",
            "inputs": {
                "vae": ["vae_loader", 0],
                "samples": ["low_sampler", 0],
                "enable_vae_tiling": False,
                "tile_x": 272,
                "tile_y": 272,
                "tile_stride_x": 144,
                "tile_stride_y": 144
            }
        },
        # 26. 视频合成（高质量编码）
        "video_combine": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c5_task_v8_{int(time.time())}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "crf": 14,
                "pix_fmt": "yuv420p10le"
            }
        }
    }
    return workflow


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
    print("C5多图视频生成任务 - V19架构 v8版 (基于v3架构修复)")
    print(f"分辨率: {WIDTH}x{HEIGHT} (5:8, 遵从1.png比例)")
    print(f"帧数: {NUM_FRAMES} (10秒@24fps)")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-end)")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print(f"FLF2V模式: fun_or_fl2v_model=true, combine_embeds=concat")
    print(f"  start_image=c5_1(走廊), end_image=c5_2(教室)")
    print(f"v8修复1: riflex_freq_index=6 (v3为0, 禁用RIFLEX导致执行两遍)")
    print(f"v8修复2: 优化深蹲提示词 (sumo squat + low angle + pause)")
    print(f"编码: crf=14, pix_fmt=yuv420p10le")
    print("=" * 60)

    print("\n[1/4] 构建v8工作流（v3架构+riflex=6）...")
    workflow = build_workflow()
    print(f"  节点数: {len(workflow)}")

    print("\n[2/4] 提交工作流到ComfyUI...")
    try:
        result = queue_prompt(workflow)
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            print(f"错误: 未获取到prompt_id: {result}")
            sys.exit(1)
        print(f"  prompt_id: {prompt_id}")
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.read().decode()}")
        sys.exit(1)

    print(f"\n[3/4] 等待任务完成...")
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
                            print(f"\n[4/4] 任务完成! 耗时: {elapsed_min:.1f}分钟")
                            print(f"  输出: {filepath}")
                            if os.path.exists(filepath):
                                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                                print(f"  文件大小: {size_mb:.2f} MB")
                            print("=" * 60)
                            return
            print(f"  等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  查询超时, 重试... ({e})")
        time.sleep(30)


if __name__ == "__main__":
    main()
