"""
C4视频生成任务 - V19架构
任务：使用c4_1.jpg生成10秒@24fps俯卧撑力竭视频
动作：预备撑起→3次俯卧撑→躬身翘臀→力竭回落趴地
规格：10秒，24fps，480x848，241帧
策略：单次生成（V19验证架构），允许轻微视角偏移，动作简化为4阶段
"""
import urllib.request
import json
import time
import sys

COMFYUI_URL = "http://127.0.0.1:3198"

# V19验证参数 - 10秒@24fps
WIDTH = 480
HEIGHT = 848
NUM_FRAMES = 241  # 4n+1, 10秒@24fps
STEPS = 8
SPLIT_STEP = 4
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.1

# 模型（V19验证组合）
HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

# 提示词（三段式结构 + 4阶段关键动作 + 背面视角为主）
POSITIVE_PROMPT = (
    "masterpiece, best quality, 8k, highly detailed, fixed camera, medium full body shot, "
    "back view, facing away from camera, indoor scene with yoga mat, "
    "subject appearance clear, same person as reference image, sportswear, "
    "consistent appearance throughout the video, "
    "the girl lies prone on a yoga mat facing away from camera, "
    "then pushes up to standard pushup plank position, "
    "then performs three standard pushups with smooth controlled motion, "
    "then arches back upward lifting hips to highest point, "
    "then slowly loses strength and sinks down with trembling muscles, "
    "finally collapses flat on the mat with residual muscle trembling, "
    "smooth body motion, natural continuous movement, realistic muscle fatigue, "
    "fixed camera, no camera movement, standing in place"
)

NEGATIVE_PROMPT = (
    "面部露出，正面转头，侧转露脸，肢体扭曲畸形，多手多脚，关节错位，"
    "服装穿模，瑜伽垫穿帮，塌腰翘腿，动作僵硬卡顿，画面闪烁，跳帧，"
    "人物漂移，背景突变，模糊重影，比例失调，低画质，噪点，"
    "运镜剧烈晃动，人物出框，违背人体发力逻辑的违和动作, "
    "face visible, turning around, side view, front view, "
    "色调艳丽，过曝，曝光变化，亮度突变，背景亮度变化，background brightening, "
    "exposure drift, lighting changes, overexposed, highlight clipping, detail loss, "
    "background replacement, background changing, different background, "
    "静态，细节模糊不清，字幕，最差质量，低质量，JPEG压缩残留， "
    "丑陋的，残缺的，多余的手指，畸形的，毁容的，手指融合， "
    "杂乱的背景，三条腿，腿部消失，肢体断裂，肢体溶解， "
    "多余肢体，缺失肢体，motion blur, frame skipping, "
    "distorted body, deformed limbs, floating hair, gravity defiance, "
    "camera movement, camera pan, camera tilt, camera zoom, camera dolly, "
    "camera shake, unstable framing, 视角变化, 运镜, 镜头移动, "
    "face changing, character drift, inconsistent appearance, "
    "blurry, low detail, pixelated, compressed artifacts, "
    "blurring progression, detail degradation, cumulative quality loss"
)


def build_workflow():
    """构建V19架构API工作流"""
    workflow = {
        "load_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c4_1.jpg"}
        },
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["load_image", 0],
                "strength_1": 1.0,
                "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "average",
                "force_offload": True
            }
        },
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": VAE_MODEL,
                "precision": "bf16"
            }
        },
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
                "start_image": ["load_image", 0]
            }
        },
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": T5_MODEL,
                "precision": "bf16"
            }
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
        "block_swap": {
            "class_type": "WanVideoBlockSwap",
            "inputs": {
                "blocks_to_swap": BLOCKS_TO_SWAP,
                "offload_img_emb": False,
                "offload_txt_emb": False
            }
        },
        "high_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["high_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        "high_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 3.0,
                "merge_loras": False
            }
        },
        "high_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["high_set_blockswap", 0],
                "lora": ["high_lora_select", 0]
            }
        },
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
        "steps_const": {
            "class_type": "INTConstant",
            "inputs": {"value": STEPS}
        },
        "split_step_const": {
            "class_type": "INTConstant",
            "inputs": {"value": SPLIT_STEP}
        },
        "high_sampler": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["high_set_loras", 0],
                "image_embeds": ["i2v_encode", 0],
                "text_embeds": ["text_encode", 0],
                "steps": ["steps_const", 0],
                "cfg": ["cfg_schedule", 0],
                "shift": SHIFT,
                "seed": int(time.time()) % 1000000,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "rope_function": "comfy_chunked",
                "riflex_freq_index": 0,
                "start_step": 0,
                "end_step": ["split_step_const", 0]
            }
        },
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
        "low_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["low_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        "low_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 1.0,
                "merge_loras": False
            }
        },
        "low_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["low_set_blockswap", 0],
                "lora": ["low_lora_select", 0]
            }
        },
        "low_sampler": {
            "class_type": "WanVideoSampler",
            "inputs": {
                "model": ["low_set_loras", 0],
                "image_embeds": ["i2v_encode", 0],
                "text_embeds": ["text_encode", 0],
                "steps": ["steps_const", 0],
                "cfg": 1.0,
                "shift": SHIFT,
                "seed": int(time.time()) % 1000000,
                "force_offload": True,
                "scheduler": "dpm++_sde",
                "rope_function": "comfy_chunked",
                "riflex_freq_index": 0,
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
                "tile_x": 272,
                "tile_y": 272,
                "tile_stride_x": 144,
                "tile_stride_y": 144
            }
        },
        "video_combine": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c4_task_{int(time.time())}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True
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
    print("C4视频生成任务 - V19架构 (10秒@24fps)")
    print(f"规格: {WIDTH}x{HEIGHT}, {NUM_FRAMES}帧, 24fps, 10秒")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-end)")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print("动作: 预备撑起→3次俯卧撑→躬身翘臀→力竭回落趴地")
    print("视角: 背面视角为主，允许轻微偏移")
    print("=" * 60)

    print("\n[1/4] 构建V19工作流...")
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
