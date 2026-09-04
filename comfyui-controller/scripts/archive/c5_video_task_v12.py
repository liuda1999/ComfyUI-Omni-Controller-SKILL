"""
C5视频生成任务 - v12版 (3段×81帧拼接, 10秒完整动作)
基于v11验证: 81帧在训练原生范围, 不触发RoPE周期性折返

方案:
  段1(81帧/3.4秒): start=1.png, 360旋转→深蹲→起身
  段2(81帧/3.4秒): start=段1末帧, 转身走向教室门口(持续走动到末帧)
  段3(81帧/3.4秒): start=段2末帧, end=2.png参考, 进入教室→拉椅→落座
  ffmpeg拼接3段 = 10秒完整视频

每段关键设计:
  - 81帧(训练原生, 不折返)
  - start_image=前段末帧(转场连贯)
  - CLIP concat(1.png角色 + start_image场景)(强约束角色外貌)
  - 标准I2V(fun_or_fl2v_model=false)
  - rope_function=comfy, riflex_freq_index=0

完整动作弧线:
  360旋转 → 深蹲 → 起身 → 走向门口 → 进入教室 → 拉椅 → 落座
"""
import urllib.request
import json
import time
import sys
import os
import subprocess

COMFYUI_URL = "http://127.0.0.1:3198"

# v12参数
WIDTH = 480
HEIGHT = 640  # 3:4, 遵从1.png
NUM_FRAMES = 81  # 训练原生, 3.375秒@24fps
STEPS = 6
SPLIT_STEP = 3
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.0
SEED = int(time.time()) % 1000000

# 模型
HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

# 段1提示词: 360旋转→深蹲→起身 (3.4秒)
POSITIVE_PROMPT_SEG1 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor corridor scene, woman standing in corridor, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman does a full 360 degree clockwise spin in place, "
    "completes the full rotation facing forward again, "
    "then slowly lowers into a deep sumo squat with legs spread wide apart, "
    "low angle shot from below looking up at the character during the squat, "
    "holds the squat pose briefly, then stands back up straight, "
    "smooth body motion, natural continuous movement, "
    "consistent character throughout"
)

# 段2提示词: 转身走向教室门口 (3.4秒, 持续走动到末帧)
POSITIVE_PROMPT_SEG2 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor corridor scene, woman standing in corridor, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman turns and walks forward down the corridor, "
    "walks continuously toward a door at the end of the corridor, "
    "the video ends while she is still walking toward the door, "
    "smooth natural walking motion, continuous forward movement, "
    "consistent character throughout"
)

# 段3提示词: 进入教室→拉椅→落座 (3.4秒)
POSITIVE_PROMPT_SEG3 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor classroom scene, woman entering classroom, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman walks through the doorway into the classroom, "
    "walks to a desk, pulls out a chair with one hand, "
    "sits down on the chair and settles in a seated position, "
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


def build_common_nodes():
    """构建公共节点(模型加载等)"""
    return {
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {"model_name": VAE_MODEL, "precision": "bf16"}
        },
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {"model_name": T5_MODEL, "precision": "bf16"}
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
        "cfg_schedule": {
            "class_type": "CreateCFGScheduleFloatList",
            "inputs": {
                "steps": STEPS, "cfg_scale_start": 2.0, "cfg_scale_end": 2.0,
                "interpolation": "linear", "start_percent": 0.0, "end_percent": 0.01
            }
        },
        "steps_const": {"class_type": "INTConstant", "inputs": {"value": STEPS}},
        "split_step_const": {"class_type": "INTConstant", "inputs": {"value": SPLIT_STEP}},
    }


def build_workflow_seg1():
    """段1: start=1.png, CLIP单图(1.png), 360旋转→深蹲→起身"""
    wf = build_common_nodes()
    wf.update({
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_1.png"}
        },
        "resize_start_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_start_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT, "crop": "disabled"
            }
        },
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_start_image", 0],
                "strength_1": 1.0, "strength_2": 1.0,
                "crop": "center", "combine_embeds": "average",
                "force_offload": True
            }
        },
        "i2v_encode": {
            "class_type": "WanVideoImageToVideoEncode",
            "inputs": {
                "width": WIDTH, "height": HEIGHT, "num_frames": NUM_FRAMES,
                "noise_aug_strength": NOISE_AUG,
                "start_latent_strength": 1.0, "end_latent_strength": 1.0,
                "force_offload": True,
                "vae": ["vae_loader", 0],
                "clip_embeds": ["clip_vision_encode", 0],
                "start_image": ["resize_start_image", 0],
                "fun_or_fl2v_model": False
            }
        },
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": POSITIVE_PROMPT_SEG1,
                "negative_prompt": NEGATIVE_PROMPT,
                "t5": ["t5_loader", 0], "force_offload": True
            }
        },
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
                "rope_function": "comfy",
                "riflex_freq_index": 0,
                "start_step": 0,
                "end_step": ["split_step_const", 0]
            }
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
                "rope_function": "comfy",
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
                "filename_prefix": f"c5_v12_seg1_{int(time.time())}",
                "format": "video/h264-mp4",
                "pingpong": False, "save_output": True,
                "crf": 14, "pix_fmt": "yuv420p10le"
            }
        }
    })
    return wf


def build_workflow_seg23(segment_name, start_image_filename, positive_prompt, use_end_image=False):
    """段2/段3: start=前段末帧, CLIP concat(1.png角色 + start_image场景)

    关键设计:
    - start_image=前段末帧(转场连贯, VAE latent继承角色)
    - CLIP image_1=1.png(角色强约束), image_2=start_image(场景)
    - combine_embeds=concat(保留双图独立特征)
    - 段3可选end_image=2.png(教室参考)
    """
    wf = build_common_nodes()
    wf.update({
        # 加载前段末帧(start_image + CLIP image_2)
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": start_image_filename}
        },
        "resize_start_image": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_start_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT, "crop": "disabled"
            }
        },
        # 加载1.png(CLIP image_1, 角色外貌约束)
        "load_char_ref": {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_1.png"}
        },
        "resize_char_ref": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_char_ref", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT, "crop": "disabled"
            }
        },
        # CLIP concat(1.png角色 + start_image场景) - 强约束角色
        "clip_vision_encode": {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_char_ref", 0],         # 1.png角色约束
                "image_2": ["resize_start_image", 0],       # 前段末帧场景
                "strength_1": 1.0, "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "concat",                 # concat强约束
                "force_offload": True
            }
        },
    })

    # 段3: 加载2.png作为end_image(教室参考)
    i2v_inputs = {
        "width": WIDTH, "height": HEIGHT, "num_frames": NUM_FRAMES,
        "noise_aug_strength": NOISE_AUG,
        "start_latent_strength": 1.0, "end_latent_strength": 1.0,
        "force_offload": True,
        "vae": ["vae_loader", 0],
        "clip_embeds": ["clip_vision_encode", 0],
        "start_image": ["resize_start_image", 0],
        "fun_or_fl2v_model": False
    }
    if use_end_image:
        wf["load_end_image"] = {
            "class_type": "LoadImage",
            "inputs": {"image": "c5_2.png"}
        }
        wf["resize_end_image"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_end_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH, "height": HEIGHT, "crop": "disabled"
            }
        }
        i2v_inputs["end_image"] = ["resize_end_image", 0]

    wf["i2v_encode"] = {
        "class_type": "WanVideoImageToVideoEncode",
        "inputs": i2v_inputs
    }
    wf["text_encode"] = {
        "class_type": "WanVideoTextEncode",
        "inputs": {
            "positive_prompt": positive_prompt,
            "negative_prompt": NEGATIVE_PROMPT,
            "t5": ["t5_loader", 0], "force_offload": True
        }
    }
    wf["high_sampler"] = {
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
            "rope_function": "comfy",
            "riflex_freq_index": 0,
            "start_step": 0,
            "end_step": ["split_step_const", 0]
        }
    }
    wf["low_sampler"] = {
        "class_type": "WanVideoSampler",
        "inputs": {
            "model": ["low_set_loras", 0],
            "image_embeds": ["i2v_encode", 0],
            "text_embeds": ["text_encode", 0],
            "steps": ["steps_const", 0],
            "cfg": 1.0, "shift": SHIFT, "seed": SEED,
            "force_offload": True,
            "scheduler": "dpm++_sde",
            "rope_function": "comfy",
            "riflex_freq_index": 0,
            "samples": ["high_sampler", 0],
            "start_step": ["split_step_const", 0],
            "end_step": -1
        }
    }
    wf["decode"] = {
        "class_type": "WanVideoDecode",
        "inputs": {
            "vae": ["vae_loader", 0],
            "samples": ["low_sampler", 0],
            "enable_vae_tiling": False,
            "tile_x": 272, "tile_y": 272,
            "tile_stride_x": 144, "tile_stride_y": 144
        }
    }
    wf["video_combine"] = {
        "class_type": "VHS_VideoCombine",
        "inputs": {
            "images": ["decode", 0],
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": f"c5_v12_{segment_name}_{int(time.time())}",
            "format": "video/h264-mp4",
            "pingpong": False, "save_output": True,
            "crf": 14, "pix_fmt": "yuv420p10le"
        }
    }
    return wf


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


def wait_for_video(prompt_id, segment_name):
    """等待视频完成, 返回视频文件路径"""
    print(f"\n  [{segment_name}] 等待完成, prompt_id: {prompt_id}")
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
                            if os.path.exists(filepath):
                                elapsed_min = elapsed / 60
                                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                                print(f"  [{segment_name}] 完成! 耗时: {elapsed_min:.1f}分钟, 大小: {size_mb:.2f}MB")
                                return filepath
            print(f"  [{segment_name}] 等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  [{segment_name}] 查询超时, 重试...")
        time.sleep(20)


def extract_last_frame(video_path, output_png_path):
    """提取视频最后一帧为PNG"""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", "select=eq(n\,80)",  # 第80帧(0-indexed)即最后一帧(81帧)
        "-vframes", "1", output_png_path
    ]
    print(f"  提取末帧: {os.path.basename(video_path)} -> {os.path.basename(output_png_path)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        # 备用: 用reverse取第一帧
        cmd2 = ["ffmpeg", "-y", "-i", video_path, "-vf", "reverse", "-vframes", "1", output_png_path]
        result = subprocess.run(cmd2, capture_output=True, text=True, timeout=120)
    return os.path.exists(output_png_path)


def copy_to_comfyui_input(src_path, filename):
    """复制文件到ComfyUI input目录(用PowerShell避免沙箱)"""
    dst = f"D:/2026-ComfyUI-V8.3/input/{filename}"
    cmd = ["powershell", "-Command", f"Copy-Item '{src_path}' '{dst}' -Force"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0 and os.path.exists(dst)


def merge_videos(video_paths, output_path):
    """ffmpeg拼接多段视频"""
    concat_file = os.path.join("E:/comfyui-cli/temp", f"concat_{int(time.time())}.txt")
    with open(concat_file, "w") as f:
        for vp in video_paths:
            normalized = vp.replace("\\", "/")
            f.write(f"file '{normalized}'\n")

    # 先尝试copy模式
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        # 重新编码
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
               "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p10le", "-r", "24", output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return os.path.exists(output_path)


def main():
    print("=" * 60)
    print("C5视频生成任务 - v12版 (3段×81帧拼接, 10秒完整动作)")
    print(f"分辨率: {WIDTH}x{HEIGHT} (3:4)")
    print(f"分段: 3段×{NUM_FRAMES}帧 (3.375秒/段, 共10.1秒)")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-{STEPS})")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"v12核心设计:")
    print(f"  段1: start=1.png, CLIP单图(1.png), 360旋转→深蹲→起身")
    print(f"  段2: start=段1末帧, CLIP concat(1.png+末帧), 走向门口")
    print(f"  段3: start=段2末帧, end=2.png参考, 进入教室→拉椅→落座")
    print("=" * 60)

    video_paths = []

    # ========== 段1 ==========
    print("\n[段1] 360旋转→深蹲→起身")
    workflow1 = build_workflow_seg1()
    try:
        result = queue_prompt(workflow1)
        prompt_id1 = result.get("prompt_id")
        print(f"  prompt_id: {prompt_id1}")
    except Exception as e:
        print(f"  提交失败: {e}")
        sys.exit(1)

    seg1_video = wait_for_video(prompt_id1, "段1")
    if not seg1_video:
        print("段1失败"); sys.exit(1)
    video_paths.append(seg1_video)
    print(f"  段1视频: {seg1_video}")

    # 提取段1末帧
    seg1_lastframe = os.path.join("E:/comfyui-cli/temp", f"c5_v12_seg1_lastframe_{int(time.time())}.png")
    if not extract_last_frame(seg1_video, seg1_lastframe):
        print("段1末帧提取失败"); sys.exit(1)
    seg1_lastframe_name = os.path.basename(seg1_lastframe)
    if not copy_to_comfyui_input(seg1_lastframe, seg1_lastframe_name):
        print("段1末帧复制失败"); sys.exit(1)
    print(f"  段1末帧: {seg1_lastframe_name}")

    # ========== 段2 ==========
    print("\n[段2] 转身走向教室门口")
    workflow2 = build_workflow_seg23("seg2", seg1_lastframe_name, POSITIVE_PROMPT_SEG2, use_end_image=False)
    try:
        result = queue_prompt(workflow2)
        prompt_id2 = result.get("prompt_id")
        print(f"  prompt_id: {prompt_id2}")
    except Exception as e:
        print(f"  提交失败: {e}"); sys.exit(1)

    seg2_video = wait_for_video(prompt_id2, "段2")
    if not seg2_video:
        print("段2失败"); sys.exit(1)
    video_paths.append(seg2_video)
    print(f"  段2视频: {seg2_video}")

    # 提取段2末帧
    seg2_lastframe = os.path.join("E:/comfyui-cli/temp", f"c5_v12_seg2_lastframe_{int(time.time())}.png")
    if not extract_last_frame(seg2_video, seg2_lastframe):
        print("段2末帧提取失败"); sys.exit(1)
    seg2_lastframe_name = os.path.basename(seg2_lastframe)
    if not copy_to_comfyui_input(seg2_lastframe, seg2_lastframe_name):
        print("段2末帧复制失败"); sys.exit(1)
    print(f"  段2末帧: {seg2_lastframe_name}")

    # ========== 段3 ==========
    print("\n[段3] 进入教室→拉椅→落座")
    workflow3 = build_workflow_seg23("seg3", seg2_lastframe_name, POSITIVE_PROMPT_SEG3, use_end_image=True)
    try:
        result = queue_prompt(workflow3)
        prompt_id3 = result.get("prompt_id")
        print(f"  prompt_id: {prompt_id3}")
    except Exception as e:
        print(f"  提交失败: {e}"); sys.exit(1)

    seg3_video = wait_for_video(prompt_id3, "段3")
    if not seg3_video:
        print("段3失败"); sys.exit(1)
    video_paths.append(seg3_video)
    print(f"  段3视频: {seg3_video}")

    # ========== 拼接 ==========
    print("\n[拼接] ffmpeg合并3段视频")
    merged_path = os.path.join("E:/comfyui-cli/output", f"c5_v12_merged_{int(time.time())}.mp4")
    if not merge_videos(video_paths, merged_path):
        print("拼接失败"); sys.exit(1)

    merged_size = os.path.getsize(merged_path) / (1024 * 1024)
    print("\n" + "=" * 60)
    print("v12任务全部完成!")
    for i, vp in enumerate(video_paths, 1):
        size = os.path.getsize(vp) / (1024 * 1024)
        print(f"  段{i}(3.4秒): {vp} ({size:.2f} MB)")
    print(f"  最终(10秒): {merged_path} ({merged_size:.2f} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
