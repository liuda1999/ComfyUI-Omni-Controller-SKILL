"""
C5多图视频生成任务 - V19架构 分段生成v7版
v7修复v6两个问题：
1. 衔接没有转场 → 段1末尾"走入门道"，段2开头"从门道走入教室"，形成自然转场衔接
2. 后半段未使用1.png角色参考 → 段2使用双图CLIP融合：
   - image_1=1.png(角色外貌参考, strength=1.0)
   - image_2=2.png(教室场景参考, strength=1.0)
   - start_image=2.png(场景锚定，角色走入2.png场景)
   - combine_embeds="average"（角色和场景特征平均融合）
策略：分段生成+ffmpeg拼接
  - 段1: 121帧@24fps=5秒, 图1作start_image, 前3动作(转身→深蹲→走入门口)
  - 段2: 121帧@24fps=5秒, 图2作start_image+1.png角色参考, 后3动作(进入教室→拉椅→落座)
  - ffmpeg拼接两段为10秒视频
编码：crf=14, pix_fmt=yuv420p10le
"""
import urllib.request
import json
import time
import sys
import os
import subprocess

COMFYUI_URL = "http://127.0.0.1:3198"

# v6参数 - 分段生成
WIDTH = 480
HEIGHT = 768  # 5:8比例, 接近1.png的0.6273, 避免裁剪
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

# 段1提示词: 前3动作(转身→深蹲→走入门道), 5秒, 末尾衔接转场
POSITIVE_PROMPT_SEG1 = (
    "masterpiece, best quality, 8k, highly detailed, "
    "indoor corridor scene, woman standing in corridor, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman does a 360 degree clockwise spin in place, "
    "then slowly lowers into a deep sumo squat with legs spread wide apart, "
    "low angle shot from below looking up at the character during the squat, "
    "pauses holding the squat pose briefly, then stands back up straight, "
    "then walks forward and passes through a doorway, disappearing into the doorway at the end, "
    "smooth body motion, natural continuous movement, "
    "consistent character throughout"
)

# 段2提示词: 后3动作(从门口进入教室→拉椅→落座), 5秒, 开头衔接转场
POSITIVE_PROMPT_SEG2 = (
    "masterpiece, best quality, 8k, highly detailed, "
    "indoor classroom scene, woman entering classroom through a doorway, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman walks through the doorway into the classroom, "
    "continues walking to the center of the classroom, "
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
    "blurry, low detail, pixelated, compressed artifacts"
)


def build_workflow_segment(segment_name, start_image, positive_prompt, reference_image=None):
    """构建V19架构FLF2V I2V工作流(分段生成版)

    每段使用单图I2V(非首尾帧), 避免double_decode
    FLF2V模式: fun_or_fl2v_model=true

    参数:
      - reference_image: 可选角色参考图路径(段2使用1.png作角色外貌参考)
        当提供时, WanVideoClipVisionEncode使用双图融合:
          image_1=reference_image(角色), image_2=start_image(场景)
        未提供时, 单图编码
    """
    workflow = {
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": start_image}
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
    }

    # 段2: 使用双图CLIP融合(1.png角色参考 + 2.png场景参考)
    if reference_image is not None:
        workflow["load_reference_image"] = {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image}
        }
        workflow["resize_reference_image"] = {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["load_reference_image", 0],
                "upscale_method": "lanczos",
                "width": WIDTH,
                "height": HEIGHT,
                "crop": "disabled"
            }
        }
        workflow["clip_vision_encode"] = {
            "class_type": "WanVideoClipVisionEncode",
            "inputs": {
                "clip_vision": ["clip_vision_loader", 0],
                "image_1": ["resize_reference_image", 0],
                "image_2": ["resize_start_image", 0],
                "strength_1": 1.0,
                "strength_2": 1.0,
                "crop": "center",
                "combine_embeds": "average",
                "force_offload": True
            }
        }
    else:
        # 段1: 单图编码
        workflow["clip_vision_encode"] = {
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
        }

    workflow.update({
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
                "start_image": ["resize_start_image", 0],
                "fun_or_fl2v_model": True
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
                "positive_prompt": positive_prompt,
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
                "seed": SEED,
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
                "filename_prefix": f"c5_{segment_name}_{int(time.time())}",
                "format": "video/h264-mp4",
                "pingpong": False,
                "save_output": True,
                "crf": 14,
                "pix_fmt": "yuv420p10le"
            }
        }
    })
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
    """等待任务完成, 返回输出文件路径"""
    print(f"\n  [{segment_name}] 等待完成, prompt_id: {prompt_id}")
    start_time = time.time()
    check_interval = 30

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
                            print(f"  [{segment_name}] 完成! 耗时: {elapsed_min:.1f}分钟")
                            print(f"  [{segment_name}] 输出: {filepath}")
                            return filepath
                    if "images" in node_output:
                        pass
            print(f"  [{segment_name}] 等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  [{segment_name}] 查询超时, 重试... ({e})")
        time.sleep(check_interval)


def concatenate_videos(seg1_path, seg2_path, output_path):
    """使用ffmpeg拼接两段视频"""
    print(f"\n[拼接] 使用ffmpeg合并两段视频...")
    list_file = os.path.join("E:/comfyui-cli/temp", "concat_list.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        f.write(f"file '{seg1_path}'\n")
        f.write(f"file '{seg2_path}'\n")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  [拼接] concat copy失败, 尝试重编码...")
        cmd_reencode = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264",
            "-crf", "14",
            "-pix_fmt", "yuv420p10le",
            "-c:a", "aac",
            output_path
        ]
        result = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  [拼接] 重编码失败: {result.stderr[-500:]}")
            return False

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  [拼接] 成功! 输出: {output_path} ({size_mb:.2f} MB)")
    return True


def main():
    print("=" * 60)
    print("C5多图视频生成任务 - V19架构 分段生成v7版 (10秒@24fps)")
    print(f"分辨率: {WIDTH}x{HEIGHT} (5:8, 遵从1.png比例)")
    print(f"每段: {NUM_FRAMES}帧, 24fps, 5秒")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-end)")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print(f"v7修复: 段1末尾走入门道(转场衔接) + 段2双图CLIP融合(1.png角色+2.png场景)")
    print("=" * 60)

    # ============ 段1 ============
    print("\n[段1/2] 生成前3动作: 转身→深蹲(低位机位)→走入门道(转场衔接)")
    print(f"  start_image: c5_1.png (走廊)")
    print(f"  帧数: {NUM_FRAMES} (5秒@24fps)")

    print("\n[1/6] 构建段1工作流...")
    workflow_seg1 = build_workflow_segment("seg1", "c5_1.png", POSITIVE_PROMPT_SEG1)
    print(f"  节点数: {len(workflow_seg1)}")

    print("\n[2/6] 提交段1到ComfyUI...")
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

    seg1_path = wait_for_completion(prompt_id_1, "段1")
    if not seg1_path or not os.path.exists(seg1_path):
        print(f"错误: 段1输出文件不存在: {seg1_path}")
        sys.exit(1)

    seg1_size = os.path.getsize(seg1_path) / (1024 * 1024)
    print(f"  段1文件大小: {seg1_size:.2f} MB")

    # ============ 段2 ============
    print("\n" + "=" * 60)
    print("[段2/2] 生成后3动作: 进入教室→拉椅→落座")
    print(f"  start_image: c5_2.png (教室场景锚定)")
    print(f"  reference_image: c5_1.png (角色外貌参考)")
    print(f"  CLIP融合: image_1=c5_1(角色) + image_2=c5_2(场景), combine=average")
    print(f"  帧数: {NUM_FRAMES} (5秒@24fps)")

    print("\n[3/6] 构建段2工作流(双图CLIP融合)...")
    workflow_seg2 = build_workflow_segment("seg2", "c5_2.png", POSITIVE_PROMPT_SEG2, reference_image="c5_1.png")
    print(f"  节点数: {len(workflow_seg2)}")

    print("\n[4/6] 提交段2到ComfyUI...")
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

    seg2_path = wait_for_completion(prompt_id_2, "段2")
    if not seg2_path or not os.path.exists(seg2_path):
        print(f"错误: 段2输出文件不存在: {seg2_path}")
        sys.exit(1)

    seg2_size = os.path.getsize(seg2_path) / (1024 * 1024)
    print(f"  段2文件大小: {seg2_size:.2f} MB")

    # ============ 拼接 ============
    print("\n" + "=" * 60)
    print("[5/6] 拼接两段视频...")

    output_filename = f"c5_task_v6_{int(time.time())}_merged.mp4"
    output_path = os.path.join("E:/comfyui-cli/output", output_filename)

    success = concatenate_videos(seg1_path, seg2_path, output_path)
    if not success:
        print("错误: 拼接失败")
        sys.exit(1)

    # ============ 完成 ============
    print("\n" + "=" * 60)
    print("[6/6] v6分段生成任务完成!")
    print(f"  段1: {seg1_path} ({seg1_size:.2f} MB)")
    print(f"  段2: {seg2_path} ({seg2_size:.2f} MB)")
    print(f"  合并: {output_path}")
    total_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"  总大小: {total_size:.2f} MB")
    print(f"  规格: {WIDTH}x{HEIGHT}, 10秒@24fps (2x5秒拼接)")
    print("=" * 60)


if __name__ == "__main__":
    main()
