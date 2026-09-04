"""
C5多图视频生成任务 - V19架构 v10版（分段生成+末帧继承+CLIP concat约束）
基于用户分析修正v9的两个致命问题:
  1. 段间无转场 → 段2首帧=段1末帧, 保证视觉连贯
  2. 段2角色不一致 → 段2 start_image=段1末帧(VAE latent继承角色)
     + CLIP concat(1.png角色 + 段1末帧场景) 强力约束角色外貌

v10方案(用户确认):
  段1(5秒/121帧): start=1.png, 单图I2V, 转身→深蹲→走向走廊→门前停下
  段2(5秒/121帧): start=段1末帧, end=2.png, FLF2V模式
    CLIP: concat(1.png角色 + 段1末帧场景) 强约束角色
    动作: 开门→穿越门道→进入教室→走到中间→拉椅→落座

保持V19架构:
  - WanVideoModelLoader + WanVideoSetBlockSwap + WanVideoSetLoRAs
  - 动态CFG [2,1,1,1,1,1]
  - dpm++_sde, shift=8.0
  - lightx2v LoRA (HIGH=3, LOW=1)
  - bf16, fp8_e4m3fn_scaled, blocks_to_swap=38
编码: crf=14, pix_fmt=yuv420p10le
"""
import urllib.request
import json
import time
import sys
import os
import subprocess

COMFYUI_URL = "http://127.0.0.1:3198"

# v10参数
WIDTH = 480
HEIGHT = 768  # 5:8比例, 遵从1.png比例
NUM_FRAMES = 121  # 4n+1, 5秒@24fps
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

# 段1提示词: 前3动作(转身→深蹲→走向走廊), 5秒
# v11修复: "走向门口"持续到末帧, 角色在走动中结束(不停下), 避免剩余时间重复旋转
# 末帧角色仍在走动, 供段2继承
POSITIVE_PROMPT_SEG1 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor corridor scene, woman standing in corridor, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman does a 360 degree clockwise spin in place, "
    "then slowly lowers into a deep sumo squat with legs spread wide apart, "
    "low angle shot from below looking up at the character during the squat, "
    "pauses holding the squat pose briefly, then stands back up straight, "
    "then turns and walks forward down the corridor toward a door, "
    "continues walking toward the door throughout the rest of the video, "
    "video ends while the woman is still walking toward the door, "
    "smooth body motion, natural continuous walking movement, "
    "consistent character throughout"
)

# 段2提示词: 后3动作(开门→穿越门道→进入教室→走到中间→拉椅→落座), 5秒
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


def build_workflow_seg1():
    """构建段1工作流: 单图I2V (start=1.png)
    
    动作: 转身→深蹲→走向走廊→门前停下
    末尾保留角色在画面中, 供段2继承
    """
    workflow = {
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_1.png"}
        },
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
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
        # 段1: 单图CLIP编码(1.png)
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
        # 段1: 单图I2V (fun_or_fl2v=false)
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
                "fun_or_fl2v_model": False
            }
        },
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {"model_name": T5_MODEL, "precision": "bf16"}
        },
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": POSITIVE_PROMPT_SEG1,
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
        # 段1: 只保存视频(末帧通过ffmpeg提取, 避免SaveImage保存全部121帧)
        "video_combine_seg1": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c5_v10_seg1_{int(time.time())}",
                "format": "video/h264-mp4",
                "pingpong": False, "save_output": True,
                "crf": 14, "pix_fmt": "yuv420p10le"
            }
        }
    }
    return workflow


def build_workflow_seg2(seg1_last_frame_filename):
    """构建段2工作流: FLF2V双图锚定 + CLIP concat约束
    
    关键设计:
    - start_image = 段1末帧 (转场连贯 + VAE latent继承角色)
    - end_image = 2.png (FLF2V场景过渡到教室)
    - CLIP concat: image_1=1.png(角色强约束) + image_2=段1末帧(场景)
    - fun_or_fl2v_model=true (启用FLF2V双图锚定)
    
    动作: 开门→穿越门道→进入教室→走到中间→拉椅→落座
    """
    workflow = {
        # 加载段1末帧(作为start_image和CLIP image_2)
        "load_seg1_lastframe": {
            "class_type": "LoadImage",
            "inputs": {"image": seg1_last_frame_filename}
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
        # 加载1.png(作为CLIP image_1, 角色外貌约束)
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
        # 加载2.png(作为end_image, 场景过渡目标)
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
        # 段2: CLIP concat(1.png角色 + 段1末帧场景) - 强力约束角色外貌
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_char_ref", 0],        # 1.png角色约束
                "image_2": ["resize_seg1_lastframe", 0],   # 段1末帧场景
                "strength_1": 1.0,
                "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "concat",                # concat强约束
                "force_offload": True
            }
        },
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {"model_name": VAE_MODEL, "precision": "bf16"}
        },
        # 段2: FLF2V双图锚定 (start=段1末帧, end=2.png)
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
                "start_image": ["resize_seg1_lastframe", 0],  # 段1末帧
                "end_image": ["resize_end_image", 0],          # 2.png教室
                "fun_or_fl2v_model": True                      # FLF2V模式
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


def wait_for_completion(prompt_id, segment_name):
    """等待任务完成, 返回输出文件路径列表"""
    print(f"\n  [{segment_name}] 等待完成, prompt_id: {prompt_id}")
    start_time = time.time()
    check_interval = 30
    outputs = {}

    while True:
        elapsed = time.time() - start_time
        try:
            history = get_history(prompt_id)
            if prompt_id in history:
                node_outputs = history[prompt_id].get("outputs", {})
                for node_id, node_output in node_outputs.items():
                    if "gifs" in node_output:
                        for gif in node_output["gifs"]:
                            filename = gif.get("filename", "")
                            subfolder = gif.get("subfolder", "")
                            filepath = os.path.join("E:/comfyui-cli/output", subfolder, filename)
                            outputs["video"] = filepath
                    if "images" in node_output:
                        for img in node_output["images"]:
                            filename = img.get("filename", "")
                            subfolder = img.get("subfolder", "")
                            filepath = os.path.join("E:/comfyui-cli/output", subfolder, filename)
                            outputs.setdefault("images", []).append(filepath)
                if "video" in outputs:
                    elapsed_min = elapsed / 60
                    print(f"  [{segment_name}] 完成! 耗时: {elapsed_min:.1f}分钟")
                    print(f"  [{segment_name}] 视频: {outputs['video']}")
                    if "images" in outputs:
                        print(f"  [{segment_name}] 图片: {outputs['images']}")
                    return outputs
            print(f"  [{segment_name}] 等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  [{segment_name}] 查询超时, 重试... ({e})")
        time.sleep(check_interval)


def extract_last_frame(video_path, output_png_path):
    """使用ffmpeg提取视频最后一帧为PNG"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", "select=eq(n\,120)",  # 第120帧(0-indexed)即最后一帧(121帧)
        "-vframes", "1",
        output_png_path
    ]
    print(f"  提取末帧: {video_path} -> {output_png_path}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        # 备用方案: 使用-seek EOF
        cmd2 = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", "reverse",
            "-vframes", "1",
            output_png_path
        ]
        result = subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"  ffmpeg错误: {result.stderr[-500:]}")
            return False
    if os.path.exists(output_png_path):
        size_kb = os.path.getsize(output_png_path) / 1024
        print(f"  末帧保存成功: {output_png_path} ({size_kb:.1f} KB)")
        return True
    return False


def merge_videos(seg1_path, seg2_path, output_path):
    """使用ffmpeg拼接两段视频"""
    concat_file = os.path.join("E:/comfyui-cli/temp", f"concat_{int(time.time())}.txt")
    seg1_normalized = seg1_path.replace("\\", "/")
    seg2_normalized = seg2_path.replace("\\", "/")
    with open(concat_file, "w") as f:
        f.write(f"file '{seg1_normalized}'\n")
        f.write(f"file '{seg2_normalized}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        output_path
    ]
    print(f"\n  ffmpeg拼接: {seg1_path} + {seg2_path} -> {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  copy模式失败, 重新编码...")
        cmd_reencode = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264",
            "-crf", "14",
            "-pix_fmt", "yuv420p10le",
            "-r", "24",
            output_path
        ]
        result = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  ffmpeg错误: {result.stderr[-500:]}")
            return False
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  拼接成功: {output_path} ({size_mb:.2f} MB)")
        return True
    return False


def main():
    print("=" * 60)
    print("C5多图视频生成任务 - V19架构 v10版 (末帧继承+CLIP concat约束)")
    print(f"分辨率: {WIDTH}x{HEIGHT} (5:8, 遵从1.png比例)")
    print(f"分段: 2段x{NUM_FRAMES}帧 (5秒@24fps/段, 共10秒)")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-end)")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print(f"v10核心设计:")
    print(f"  段1: start=1.png, 单图I2V, 转身→深蹲→走向走廊→门前停下")
    print(f"  段2: start=段1末帧(转场继承), end=2.png(场景过渡)")
    print(f"        CLIP concat(1.png角色 + 段1末帧场景) 强约束角色")
    print(f"        FLF2V模式, 开门→进入教室→拉椅→落座")
    print(f"编码: crf=14, pix_fmt=yuv420p10le")
    print("=" * 60)

    # ========== 段1: 单图I2V ==========
    print("\n[段1] 构建工作流 (转身→深蹲→走向走廊→门前停下)...")
    workflow_seg1 = build_workflow_seg1()
    print(f"  节点数: {len(workflow_seg1)}")

    print("\n[段1] 提交工作流到ComfyUI...")
    try:
        result = queue_prompt(workflow_seg1)
        prompt_id_1 = result.get("prompt_id")
        if not prompt_id_1:
            print(f"错误: 未获取到prompt_id: {result}")
            sys.exit(1)
        print(f"  prompt_id: {prompt_id_1}")
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.read().decode()}")
        sys.exit(1)

    seg1_outputs = wait_for_completion(prompt_id_1, "段1")
    seg1_video = seg1_outputs.get("video")
    if not seg1_video or not os.path.exists(seg1_video):
        print(f"错误: 段1视频不存在: {seg1_video}")
        sys.exit(1)
    size1 = os.path.getsize(seg1_video) / (1024 * 1024)
    print(f"  段1视频大小: {size1:.2f} MB")

    # ========== 提取段1末帧 ==========
    print("\n[末帧提取] 从段1视频提取最后一帧...")
    seg1_lastframe_path = os.path.join("E:/comfyui-cli/temp", f"c5_v10_seg1_lastframe_{int(time.time())}.png")
    if not extract_last_frame(seg1_video, seg1_lastframe_path):
        print("错误: 末帧提取失败")
        sys.exit(1)

    # 复制末帧到ComfyUI input目录(使用PowerShell避免沙箱权限问题)
    comfy_input = "D:/2026-ComfyUI-V8.3/input"
    seg1_lastframe_filename = os.path.basename(seg1_lastframe_path)
    comfy_lastframe_path = os.path.join(comfy_input, seg1_lastframe_filename)
    copy_cmd = ["powershell", "-Command", f"Copy-Item '{seg1_lastframe_path}' '{comfy_lastframe_path}' -Force"]
    copy_result = subprocess.run(copy_cmd, capture_output=True, text=True, timeout=30)
    if copy_result.returncode != 0 or not os.path.exists(comfy_lastframe_path):
        print(f"错误: 末帧复制失败: {copy_result.stderr}")
        sys.exit(1)
    print(f"  末帧已复制到ComfyUI input: {seg1_lastframe_filename}")

    # ========== 段2: FLF2V + CLIP concat ==========
    print("\n[段2] 构建工作流 (开门→进入教室→拉椅→落座)...")
    print(f"  start_image: 段1末帧 ({seg1_lastframe_filename})")
    print(f"  end_image: 2.png (教室场景)")
    print(f"  CLIP: concat(1.png角色 + 段1末帧场景)")
    print(f"  fun_or_fl2v_model: true (FLF2V双图锚定)")
    workflow_seg2 = build_workflow_seg2(seg1_lastframe_filename)
    print(f"  节点数: {len(workflow_seg2)}")

    print("\n[段2] 提交工作流到ComfyUI...")
    try:
        result = queue_prompt(workflow_seg2)
        prompt_id_2 = result.get("prompt_id")
        if not prompt_id_2:
            print(f"错误: 未获取到prompt_id: {result}")
            sys.exit(1)
        print(f"  prompt_id: {prompt_id_2}")
    except urllib.error.HTTPError as e:
        print(f"HTTP错误: {e.code} - {e.read().decode()}")
        sys.exit(1)

    seg2_outputs = wait_for_completion(prompt_id_2, "段2")
    seg2_video = seg2_outputs.get("video")
    if not seg2_video or not os.path.exists(seg2_video):
        print(f"错误: 段2视频不存在: {seg2_video}")
        sys.exit(1)
    size2 = os.path.getsize(seg2_video) / (1024 * 1024)
    print(f"  段2视频大小: {size2:.2f} MB")

    # ========== ffmpeg拼接 ==========
    print("\n[拼接] 使用ffmpeg合并两段视频...")
    merged_filename = f"c5_v10_merged_{int(time.time())}.mp4"
    merged_path = os.path.join("E:/comfyui-cli/output", merged_filename)

    success = merge_videos(seg1_video, seg2_video, merged_path)
    if not success:
        print("错误: ffmpeg拼接失败")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("v10任务全部完成!")
    print(f"  段1(5秒): {seg1_video} ({size1:.2f} MB)")
    print(f"  段1末帧: {seg1_lastframe_path}")
    print(f"  段2(5秒): {seg2_video} ({size2:.2f} MB)")
    if os.path.exists(merged_path):
        merged_size = os.path.getsize(merged_path) / (1024 * 1024)
        print(f"  最终(10秒): {merged_path} ({merged_size:.2f} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
