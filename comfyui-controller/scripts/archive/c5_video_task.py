"""
C5多图视频生成任务 - V19架构 FLF2V模式 (v5修复版)
任务：使用c5_1.png(人物主体)和c5_2.png(教室场景)生成10秒@24fps多图视频
动作：转身→深蹲→行走转场→教室行走→拉椅→落座（单连续流程，6阶段）
规格：10秒，24fps，480x640(3:4), 241帧
策略：FLF2V多图生成模式（参考wanvideo_FLF2V_720P_example_02.json）
  - fun_or_fl2v_model=true（FLF2V模式，不触发double_decode，正确生成241帧）
  - WanVideoClipVisionEncode(combine_embeds="concat")（非average，FLF2V标准）
  - start_image=图1走廊, end_image=图2教室, clip_embeds=CLIP concat融合
v5修复两个严重问题：
  1. 使用FLF2V多图生成模式（非v1首尾帧模式，非v4单图模式）
     - v1错误：fun_or_fl2v_model=false触发double_decode+245帧
     - v4错误：移除图2，丢失教室场景参考
     - v5修复：fun_or_fl2v_model=true，正确使用两张图，不触发double_decode
  2. 启用RIFLEX：riflex_freq_index=6（v2/v3/v4错误设为0）
     - 根因：241帧超出模型训练长度，riflex=0导致时间编码循环，动作执行两遍
     - 修复：riflex_freq_index=6防止长视频时间循环
运镜：固定中景+跟拍转场
编码：crf=14, pix_fmt=yuv420p10le（高质量10位色深）
"""
import urllib.request
import json
import time
import sys

COMFYUI_URL = "http://127.0.0.1:3198"

# V19验证参数 - 10秒@24fps
# 分辨率：480x640 (3:4比例，遵从1.png的画面比例)
WIDTH = 480
HEIGHT = 640
NUM_FRAMES = 241  # 4n+1, 10秒@24fps
STEPS = 8
SPLIT_STEP = 4
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.1
# 修复：HIGH 和 LOW 必须使用相同 seed（源工作流验证）
# v2 bug：两次 int(time.time()) 调用产生不同 seed，导致 LOW 阶段生成器状态不一致
SEED = int(time.time()) % 1000000

# 模型（V19验证组合）
HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

# 提示词（三段式结构 + 单连续流程 + 固定中景+跟拍转场）
# 提示词本身无问题，v2的"执行两遍"问题根因是工作流设计，不是提示词密度
POSITIVE_PROMPT = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, following camera during transition, "
    "indoor corridor scene, woman standing in corridor, "
    "subject appearance clear, same person throughout the video, consistent appearance, consistent clothing, "
    "the woman does a 360 degree clockwise spin in place, "
    "then slowly lowers into a deep sumo squat with legs spread wide apart, pauses holding the pose briefly, then stands back up straight, "
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
    "色调艳丽，过曝，曝光变化，亮度突变，背景亮度变化，background brightening, "
    "exposure drift, lighting changes, overexposed, highlight clipping, detail loss, "
    "background replacement, background changing, different background, "
    "静态，细节模糊不清，字幕，最差质量，低质量，JPEG压缩残留， "
    "丑陋的，残缺的，多余的手指，畸形的，毁容的，手指融合， "
    "杂乱的背景，三条腿，腿部消失，肢体断裂，肢体溶解， "
    "多余肢体，缺失肢体，motion blur, frame skipping, "
    "distorted body, deformed limbs, floating hair, gravity defiance, "
    "camera pan, camera tilt, camera zoom, camera dolly, camera shake, unstable framing, "
    "视角变化, 运镜, 镜头移动, "
    "face changing, character drift, inconsistent appearance, "
    "blurry, low detail, pixelated, compressed artifacts, "
    "blurring progression, detail degradation, cumulative quality loss"
)


def build_workflow():
    """构建V19架构FLF2V多图生成工作流（v5修复版）

    v5修复两个严重问题（参考FLF2V官方工作流）：
    1. 使用FLF2V多图生成模式（非首尾帧模式）：
       - 参考工作流：wanvideo_FLF2V_720P_example_02.json
       - fun_or_fl2v_model=true（FLF2V模式，不触发double_decode，不生成额外帧）
       - WanVideoClipVisionEncode(combine_embeds="concat")（非average）
       - start_image=图1（走廊，人物主体），end_image=图2（教室，目标场景）
       - 与v1首尾帧模式区别：fun_or_fl2v_model=false触发double_decode+245帧，
         FLF2V模式fun_or_fl2v_model=true不触发double_decode，正确生成241帧
    2. 启用RIFLEX：riflex_freq_index=6（v2/v3/v4错误设为0，禁用了RIFLEX）
       - RIFLEX作用：当视频帧数超过模型训练长度时，修改RoPE频率分量，防止时间位置编码循环
       - 根因：241帧（10秒）超出模型训练长度，riflex_freq_index=0导致时间编码周期性重复，
         模型把241帧当成两个循环，每个循环执行一遍提示词动作（"执行两遍"问题）
       - 源工作流使用81帧（短视频），riflex_freq_index=0不需要RIFLEX
       - 长视频（241帧）必须启用RIFLEX，设置riflex_freq_index=6（tooltip推荐默认值）
    """
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
        # 3. 起始图resize到目标分辨率（避免tensor size mismatch）
        "resize_start_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_start_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH,
                "height": HEIGHT,
                "crop": "center"
            }
        },
        # 4. 结束图resize到目标分辨率
        "resize_end_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_end_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH,
                "height": HEIGHT,
                "crop": "center"
            }
        },
        # 5. 加载CLIP Vision模型（FLF2V模式需要CLIP Vision编码）
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
        # 6. CLIP Vision编码（FLF2V模式：combine_embeds="concat"，非average）
        #    参考FLF2V工作流Node 88: combine_embeds="concat"
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
        # 7. 加载VAE
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": VAE_MODEL,
                "precision": "bf16"
            }
        },
        # 8. I2V编码（FLF2V多图生成模式：fun_or_fl2v_model=true）
        #    参考FLF2V工作流Node 89: fun_or_fl2v_model=true
        #    start_image=图1走廊, end_image=图2教室, clip_embeds=CLIP融合
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
        # 7. 加载T5
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": T5_MODEL,
                "precision": "bf16"
            }
        },
        # 8. 文本编码
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": POSITIVE_PROMPT,
                "negative_prompt": NEGATIVE_PROMPT,
                "t5": ["t5_loader", 0],
                "force_offload": True
            }
        },
        # 9. HIGH模型加载
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
        # 10. BlockSwap配置
        "block_swap": {
            "class_type": "WanVideoBlockSwap",
            "inputs": {
                "blocks_to_swap": BLOCKS_TO_SWAP,
                "offload_img_emb": False,
                "offload_txt_emb": False
            }
        },
        # 11. 应用BlockSwap到HIGH模型
        "high_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["high_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        # 12. HIGH LoRA选择
        "high_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 3.0,
                "merge_loras": False
            }
        },
        # 13. 应用LoRA到HIGH模型
        "high_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["high_set_blockswap", 0],
                "lora": ["high_lora_select", 0]
            }
        },
        # 14. 动态CFG调度
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
        # 15. 共享steps
        "steps_const": {
            "class_type": "INTConstant",
            "inputs": {"value": STEPS}
        },
        # 16. 共享split_step
        "split_step_const": {
            "class_type": "INTConstant",
            "inputs": {"value": SPLIT_STEP}
        },
        # 17. HIGH阶段采样（v5修复：riflex_freq_index=6，启用RIFLEX防止长视频循环）
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
        # 18. LOW模型加载
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
        # 19. 应用BlockSwap到LOW模型
        "low_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["low_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        # 20. LOW LoRA选择
        "low_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 1.0,
                "merge_loras": False
            }
        },
        # 21. 应用LoRA到LOW模型
        "low_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["low_set_blockswap", 0],
                "lora": ["low_lora_select", 0]
            }
        },
        # 22. LOW阶段采样
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
        # 23. 解码视频
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
        # 24. 视频合成输出（高质量编码：crf=14, pix_fmt=yuv420p10le 10位色深）
        "video_combine": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c5_task_{int(time.time())}",
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
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read())


def get_history(prompt_id):
    resp = urllib.request.urlopen(
        f"{COMFYUI_URL}/history/{prompt_id}", timeout=120
    )
    return json.loads(resp.read())


def main():
    print("=" * 60)
    print("C5多图视频生成任务 - V19架构 FLF2V模式 v5修复版 (10秒@24fps)")
    print(f"规格: {WIDTH}x{HEIGHT} (3:4), {NUM_FRAMES}帧, 24fps, 10秒")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-end)")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print("FLF2V模式: fun_or_fl2v_model=true, combine_embeds=concat")
    print("  start_image=c5_1(走廊), end_image=c5_2(教室), CLIP concat融合")
    print("v5修复: FLF2V多图模式(非首尾帧) + RIFLEX=6(防时间循环) + 统一SEED")
    print("动作: 转身→深蹲外展→行走转场→教室行走→拉椅→落座（6阶段单连续流程）")
    print("运镜: 固定中景+跟拍转场")
    print("编码: crf=14, pix_fmt=yuv420p10le (高质量10位色深)")
    print("=" * 60)

    print("\n[1/4] 构建V19 FLF2V多图工作流...")
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
        print(f"HTTP错误: {e.code}")
        print(e.read().decode("utf-8"))
        sys.exit(1)
    except Exception as e:
        print(f"提交失败: {e}")
        sys.exit(1)

    print("\n[3/4] 等待执行完成...")
    start_time = time.time()
    last_status = -1
    while True:
        elapsed = time.time() - start_time
        try:
            history = get_history(prompt_id)
        except Exception:
            time.sleep(10)
            continue
        if prompt_id in history:
            status = history[prompt_id]
            outputs = status.get("outputs", {})
            status_code = status.get("status", {}).get("status_str", "unknown")
            if status_code == "error":
                print(f"\n执行失败!")
                print(json.dumps(status.get("status", {}), indent=2, ensure_ascii=False)[:2000])
                sys.exit(1)
            print(f"\n执行完成! 耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
            for node_id, node_output in outputs.items():
                if "gifs" in node_output:
                    for gif in node_output["gifs"]:
                        print(f"  输出: {gif.get('filename')} ({gif.get('subfolder', '')})")
                if "images" in node_output:
                    for img in node_output["images"]:
                        print(f"  输出: {img.get('filename')} ({img.get('subfolder', '')})")
            break
        if int(elapsed) % 30 == 0 and int(elapsed) != last_status:
            print(f"  已等待 {int(elapsed)}秒 ({elapsed/60:.1f}分钟)...", end="\r")
            last_status = int(elapsed)
        time.sleep(10)

    print("\n[4/4] 任务完成!")


if __name__ == "__main__":
    main()
