"""v10段2单独执行脚本 - 段1已完成,末帧已复制到ComfyUI input"""
import urllib.request
import json
import time
import sys
import os
import subprocess

COMFYUI_URL = "http://127.0.0.1:3198"

WIDTH = 480
HEIGHT = 768
NUM_FRAMES = 121
STEPS = 8
SPLIT_STEP = 4
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.1
SEED = 660631  # 与段1相同SEED

HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

# 段1末帧文件名(已复制到ComfyUI input)
SEG1_LASTFRAME = "c5_v10_seg1_lastframe_1784663014.png"

POSITIVE_PROMPT_SEG2 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor classroom scene, woman standing in front of a door, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman opens the door and walks through the doorway, "
    "enters the classroom and walks to the center of the classroom, "
    "then pulls out a chair with one hand, "
    "finally sits down on the chair and settles in a seated position, "
    "smooth body motion, natural continuous movement, "
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
    "blurry, low detail, pixelated, compressed artifacts, "
    "action repeating, motion repeating, looping animation"
)


def build_workflow_seg2():
    """段2: FLF2V双图锚定 + CLIP concat约束
    start=段1末帧, end=2.png, CLIP: concat(1.png角色 + 段1末帧场景)
    """
    return {
        "load_seg1_lastframe": {
            "class_type": "LoadImage",
            "inputs": {"image": SEG1_LASTFRAME}
        },
        "resize_seg1_lastframe": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_seg1_lastframe", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT,
                "crop": "disabled"
            }
        },
        "load_char_ref": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_1.png"}
        },
        "resize_char_ref": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_char_ref", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT,
                "crop": "disabled"
            }
        },
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
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_char_ref", 0],
                "image_2": ["resize_seg1_lastframe", 0],
                "strength_1": 1.0, "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "concat",
                "force_offload": True
            }
        },
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {"model_name": VAE_MODEL, "precision": "bf16"}
        },
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
                "start_image": ["resize_seg1_lastframe", 0],
                "end_image": ["resize_end_image", 0],
                "fun_or_fl2v_model": True
            }
        },
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {"model_name": T5_MODEL, "precision": "bf16"}
        },
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": POSITIVE_PROMPT_SEG2,
                "negative_prompt": NEGATIVE_PROMPT,
                "t5": ["t5_loader", 0],
                "force_offload": True
            }
        },
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
        "cfg_schedule": {
            "class_type": "CreateCFGScheduleFloatList",
            "inputs": {
                "steps": STEPS, "cfg_scale_start": 2.0, "cfg_scale_end": 2.0,
                "interpolation": "linear", "start_percent": 0.0, "end_percent": 0.01
            }
        },
        "steps_const": {"class_type": "INTConstant", "inputs": {"value": STEPS}},
        "split_step_const": {"class_type": "INTConstant", "inputs": {"value": SPLIT_STEP}},
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
                "rope_function": "comfy_chunked",
                "riflex_freq_index": 6,
                "start_step": 0,
                "end_step": ["split_step_const", 0]
            }
        },
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
                "rope_function": "comfy_chunked",
                "riflex_freq_index": 6,
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
        "video_combine_seg2": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c5_v10_seg2_{int(time.time())}",
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
    print("v10段2单独执行 (段1已完成,末帧已就位)")
    print(f"  start_image: {SEG1_LASTFRAME} (段1末帧)")
    print(f"  end_image: c5_2.png (教室)")
    print(f"  CLIP: concat(1.png角色 + 段1末帧场景)")
    print(f"  FLF2V模式, 121帧/5秒")
    print("=" * 60)

    # 清理段1大量PNG输出(SaveImage保存了所有帧)
    print("\n[清理] 删除段1多余的PNG帧...")
    png_count = 0
    for f in os.listdir("E:/comfyui-cli/output"):
        if f.startswith("c5_v10_seg1_lastframe_") and f.endswith(".png"):
            os.remove(os.path.join("E:/comfyui-cli/output", f))
            png_count += 1
    print(f"  已删除{png_count}个PNG帧")

    print("\n[段2] 构建工作流...")
    workflow = build_workflow_seg2()
    print(f"  节点数: {len(workflow)}")

    print("\n[段2] 提交工作流到ComfyUI...")
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

    print(f"\n[段2] 等待完成...")
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
                            size_mb = os.path.getsize(filepath) / (1024 * 1024)
                            print(f"\n[段2] 完成! 耗时: {elapsed_min:.1f}分钟")
                            print(f"  输出: {filepath} ({size_mb:.2f} MB)")
                            print("=" * 60)
                            return
            print(f"  等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  查询超时, 重试... ({e})")
        time.sleep(30)


if __name__ == "__main__":
    main()
