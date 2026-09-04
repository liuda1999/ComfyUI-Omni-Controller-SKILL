"""
C5多图视频生成任务 - V19架构 v9版（分段生成+多图CLIP融合）
根因分析结论：Wan2.2 I2V模型不建议单次生成超过5秒(121帧)视频
  - v3/v8使用241帧(10秒)导致提示词执行两遍（模型语义重复，非RIFLEX问题）
  - FLF2V双图锚定加剧"往返"现象
v9修复方案（基于v3架构，用户确认效果最好）：
  1. 分段生成：2段×121帧@24fps=5秒/段，每段在模型训练长度内
  2. 多图CLIP融合：段2用1.png约束角色外貌（解决v7角色不一致问题）
  3. 段间衔接：段1末尾走入门道，段2开头从门道进入教室
  4. ffmpeg拼接为10秒视频
保持v3架构（V19）：
  - WanVideoModelLoader + WanVideoSetBlockSwap + WanVideoSetLoRAs
  - 动态CFG [2,1,1,1,1,1]
  - dpm++_sde, shift=8.0
  - lightx2v LoRA (HIGH=3, LOW=1)
  - bf16精度, fp8_e4m3fn_scaled量化
  - blocks_to_swap=38
编码：crf=14, pix_fmt=yuv420p10le
"""
import urllib.request
import json
import time
import sys
import os
import subprocess

COMFYUI_URL = "http://127.0.0.1:3198"

# v9参数（分段生成，每段121帧=5秒）
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

# 段1提示词: 前3动作(转身→深蹲→走入门道), 5秒, 末尾衔接转场
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
    "then turns and walks forward toward a doorway, "
    "walks through the doorway and disappears from view at the end, "
    "smooth body motion, natural continuous movement, "
    "consistent character throughout"
)

# 段2提示词: 后3动作(从门道进入教室→拉椅→落座), 5秒, 开头衔接转场
POSITIVE_PROMPT_SEG2 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor classroom scene, woman entering classroom through a doorway, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman emerges from a doorway and walks into the classroom, "
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
    "blurry, low detail, pixelated, compressed artifacts, "
    "action repeating, motion repeating, looping animation"
)


def build_workflow_segment(segment_name, start_image_path, positive_prompt,
                            reference_image_path=None):
    """构建V19架构I2V工作流(分段生成版)

    v9关键设计:
    - 每段单图I2V(非首尾帧), 避免FLF2V双图锚定导致"往返"
    - 段2使用多图CLIP融合: image_1=1.png(角色外貌), image_2=2.png(场景)
      combine_embeds="average" 让1.png约束角色外貌

    参数:
      - start_image_path: start_image文件名(段1用1.png, 段2用2.png)
      - reference_image_path: 可选角色参考图(段2使用1.png作角色外貌约束)
        当提供时, WanVideoClipVisionEncode使用双图融合:
          image_1=reference_image_path(角色外貌), image_2=start_image_path(场景)
        未提供时, 单图编码(image_1=start_image_path)
    """
    workflow = {
        # 1. 加载start_image
        "load_start_image": {
            "class_type": "LoadImage",
            "inputs": {"image": start_image_path}
        },
        # 2. start_image resize
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
        # 3. CLIP Vision加载
        "clip_vision_loader": {
            "class_type": "CLIPVisionLoader",
            "inputs": {"clip_name": CLIP_VISION_MODEL}
        },
    }

    # 段2: 使用双图CLIP融合(1.png角色外貌 + 2.png场景锚定)
    if reference_image_path is not None:
        workflow["load_reference_image"] = {
            "class_type": "LoadImage",
            "inputs": {"image": reference_image_path}
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
        # 多图CLIP融合: 1.png(角色) + 2.png(场景), average融合
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
        # 段1: 单图CLIP编码(start_image=1.png)
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
        # 4. VAE加载
        "vae_loader": {
            "class_type": "WanVideoVAELoader",
            "inputs": {
                "model_name": VAE_MODEL,
                "precision": "bf16"
            }
        },
        # 5. I2V编码(单图模式, 非FLF2V)
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
                "fun_or_fl2v_model": False
            }
        },
        # 6. T5加载
        "t5_loader": {
            "class_type": "LoadWanVideoT5TextEncoder",
            "inputs": {
                "model_name": T5_MODEL,
                "precision": "bf16"
            }
        },
        # 7. 文本编码
        "text_encode": {
            "class_type": "WanVideoTextEncode",
            "inputs": {
                "positive_prompt": positive_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "t5": ["t5_loader", 0],
                "force_offload": True
            }
        },
        # 8. HIGH模型加载
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
        # 9. BlockSwap配置
        "block_swap": {
            "class_type": "WanVideoBlockSwap",
            "inputs": {
                "blocks_to_swap": BLOCKS_TO_SWAP,
                "offload_img_emb": False,
                "offload_txt_emb": False
            }
        },
        # 10. HIGH BlockSwap
        "high_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["high_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        # 11. HIGH LoRA选择
        "high_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 3.0,
                "merge_loras": False
            }
        },
        # 12. HIGH LoRA应用
        "high_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["high_set_blockswap", 0],
                "lora": ["high_lora_select", 0]
            }
        },
        # 13. 动态CFG调度
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
        # 14. 共享steps
        "steps_const": {
            "class_type": "INTConstant",
            "inputs": {"value": STEPS}
        },
        # 15. 共享split_step
        "split_step_const": {
            "class_type": "INTConstant",
            "inputs": {"value": SPLIT_STEP}
        },
        # 16. HIGH采样器
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
        # 17. LOW模型加载
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
        # 18. LOW BlockSwap
        "low_set_blockswap": {
            "class_type": "WanVideoSetBlockSwap",
            "inputs": {
                "model": ["low_model_loader", 0],
                "block_swap_args": ["block_swap", 0]
            }
        },
        # 19. LOW LoRA选择
        "low_lora_select": {
            "class_type": "WanVideoLoraSelect",
            "inputs": {
                "lora": LORA_MODEL,
                "strength": 1.0,
                "merge_loras": False
            }
        },
        # 20. LOW LoRA应用
        "low_set_loras": {
            "class_type": "WanVideoSetLoRAs",
            "inputs": {
                "model": ["low_set_blockswap", 0],
                "lora": ["low_lora_select", 0]
            }
        },
        # 21. LOW采样器
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
        # 22. VAE解码
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
        # 23. 视频合成（高质量编码）
        "video_combine": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["decode", 0],
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": f"c5_v9_{segment_name}_{int(time.time())}",
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
            print(f"  [{segment_name}] 等待中... {elapsed:.0f}秒")
        except Exception as e:
            print(f"  [{segment_name}] 查询超时, 重试... ({e})")
        time.sleep(check_interval)


def merge_videos(seg1_path, seg2_path, output_path):
    """使用ffmpeg拼接两段视频"""
    # 创建concat列表文件
    concat_file = os.path.join("E:/comfyui-cli/temp", f"concat_{int(time.time())}.txt")
    # ffmpeg concat需要用正斜杠或转义反斜杠
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
        # 如果copy模式失败，重新编码
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
    print("C5多图视频生成任务 - V19架构 v9版 (分段生成+多图CLIP融合)")
    print(f"分辨率: {WIDTH}x{HEIGHT} (5:8, 遵从1.png比例)")
    print(f"分段: 2段x{NUM_FRAMES}帧 (5秒@24fps/段, 共10秒)")
    print(f"双阶段: HIGH(0-{SPLIT_STEP}) + LOW({SPLIT_STEP}-end)")
    print(f"调度器: dpm++_sde, shift={SHIFT}")
    print(f"LoRA: lightx2v (HIGH=3, LOW=1)")
    print(f"v9核心: 分段生成(121帧/段) + 多图CLIP融合(段2用1.png约束角色)")
    print(f"  段1: start_image=1.png, 单图CLIP, fun_or_fl2v=false")
    print(f"  段2: start_image=2.png, 多图CLIP(1.png角色+2.png场景), average融合")
    print(f"编码: crf=14, pix_fmt=yuv420p10le")
    print("=" * 60)

    # ========== 段1: 前3动作 ==========
    print("\n[段1] 构建工作流 (前3动作: 转身→深蹲→走入门道)...")
    print(f"  start_image: 1.png (走廊场景)")
    print(f"  CLIP: 单图 (1.png)")
    print(f"  fun_or_fl2v_model: false (单图I2V)")
    workflow_seg1 = build_workflow_segment(
        segment_name="seg1",
        start_image_path="c5_1.png",
        positive_prompt=POSITIVE_PROMPT_SEG1,
        reference_image_path=None  # 段1单图
    )
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

    seg1_path = wait_for_completion(prompt_id_1, "段1")
    if not seg1_path or not os.path.exists(seg1_path):
        print(f"错误: 段1输出文件不存在: {seg1_path}")
        sys.exit(1)
    size1 = os.path.getsize(seg1_path) / (1024 * 1024)
    print(f"  段1文件大小: {size1:.2f} MB")

    # ========== 段2: 后3动作 ==========
    print("\n[段2] 构建工作流 (后3动作: 进入教室→拉椅→落座)...")
    print(f"  start_image: 2.png (教室场景)")
    print(f"  CLIP: 多图融合 (image_1=1.png角色 + image_2=2.png场景, average)")
    print(f"  fun_or_fl2v_model: false (单图I2V + 多图CLIP融合)")
    workflow_seg2 = build_workflow_segment(
        segment_name="seg2",
        start_image_path="c5_2.png",
        positive_prompt=POSITIVE_PROMPT_SEG2,
        reference_image_path="c5_1.png"  # 段2用1.png约束角色外貌
    )
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

    seg2_path = wait_for_completion(prompt_id_2, "段2")
    if not seg2_path or not os.path.exists(seg2_path):
        print(f"错误: 段2输出文件不存在: {seg2_path}")
        sys.exit(1)
    size2 = os.path.getsize(seg2_path) / (1024 * 1024)
    print(f"  段2文件大小: {size2:.2f} MB")

    # ========== ffmpeg拼接 ==========
    print("\n[拼接] 使用ffmpeg合并两段视频...")
    merged_filename = f"c5_v9_merged_{int(time.time())}.mp4"
    merged_path = os.path.join("E:/comfyui-cli/output", merged_filename)

    success = merge_videos(seg1_path, seg2_path, merged_path)
    if not success:
        print("错误: ffmpeg拼接失败")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("v9任务全部完成!")
    print(f"  段1(5秒): {seg1_path} ({size1:.2f} MB)")
    print(f"  段2(5秒): {seg2_path} ({size2:.2f} MB)")
    if os.path.exists(merged_path):
        merged_size = os.path.getsize(merged_path) / (1024 * 1024)
        print(f"  最终(10秒): {merged_path} ({merged_size:.2f} MB)")
    print("=" * 60)


if __name__ == "__main__":
    main()
