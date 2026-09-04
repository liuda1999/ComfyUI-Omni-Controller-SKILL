"""v13段3执行 (提示词优化+CLIP权重1.5/0.5)"""
import urllib.request
import json
import time
import sys
import os
import subprocess

COMFYUI_URL = "http://127.0.0.1:3198"

WIDTH = 480
HEIGHT = 640
NUM_FRAMES = 81
STEPS = 6
SPLIT_STEP = 3
SHIFT = 8.0
BLOCKS_TO_SWAP = 38
NOISE_AUG = 0.0
SEED = 659598

HIGH_MODEL = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
LOW_MODEL = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
VAE_MODEL = "Wan2_1_VAE_bf16.safetensors"
T5_MODEL = "umt5-xxl-enc-fp8_e4m3fn.safetensors"
CLIP_VISION_MODEL = "clip_vision_h.safetensors"
LORA_MODEL = "lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors"

SEG2_LASTFRAME = "c5_v13_seg2_lastframe_1784667135.png"

# v13段3提示词: 详细描述从门口进入教室
POSITIVE_PROMPT_SEG3 = (
    "masterpiece, best quality, 8k, highly detailed, fixed medium shot, "
    "indoor classroom scene, woman standing at the doorway, "
    "same appearance as reference image, same face as reference image, "
    "same clothing as reference image, consistent face, consistent clothing, "
    "same hairstyle as reference image, same body proportion as reference image, "
    "the woman pushes the door open and steps into the classroom, "
    "walks forward into the classroom to find a desk, "
    "pulls out a chair with one hand, "
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
    "returning to start position, walking backwards, reversing, "
    "teleporting, sudden position change"
)


def build_seg3():
    return {
        "load_start_image": {"class_type": "LoadImage", "inputs": {"image": SEG2_LASTFRAME}},
        "resize_start_image": {"class_type": "ImageScale", "inputs": {"image": ["load_start_image", 0], "upscale_method": "lanczos", "width": WIDTH, "height": HEIGHT, "crop": "disabled"}},
        "load_char_ref": {"class_type": "LoadImage", "inputs": {"image": "c5_1.png"}},
        "resize_char_ref": {"class_type": "ImageScale", "inputs": {"image": ["load_char_ref", 0], "upscale_method": "lanczos", "width": WIDTH, "height": HEIGHT, "crop": "disabled"}},
        "load_end_image": {"class_type": "LoadImage", "inputs": {"image": "c5_2.png"}},
        "resize_end_image": {"class_type": "ImageScale", "inputs": {"image": ["load_end_image", 0], "upscale_method": "lanczos", "width": WIDTH, "height": HEIGHT, "crop": "disabled"}},
        "clip_vision_loader": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": CLIP_VISION_MODEL}},
        # v13: strength_1=1.5(1.png角色强约束), strength_2=0.5(末帧场景弱化)
        "clip_vision_encode": {"class_type": "WanVideoClipVisionEncode", "inputs": {
            "clip_vision": ["clip_vision_loader", 0],
            "image_1": ["resize_char_ref", 0], "image_2": ["resize_start_image", 0],
            "strength_1": 1.5, "strength_2": 0.5,
            "crop": "center", "combine_embeds": "concat", "force_offload": True
        }},
        "vae_loader": {"class_type": "WanVideoVAELoader", "inputs": {"model_name": VAE_MODEL, "precision": "bf16"}},
        "i2v_encode": {"class_type": "WanVideoImageToVideoEncode", "inputs": {
            "width": WIDTH, "height": HEIGHT, "num_frames": NUM_FRAMES,
            "noise_aug_strength": NOISE_AUG, "start_latent_strength": 1.0, "end_latent_strength": 1.0,
            "force_offload": True, "vae": ["vae_loader", 0], "clip_embeds": ["clip_vision_encode", 0],
            "start_image": ["resize_start_image", 0], "end_image": ["resize_end_image", 0],
            "fun_or_fl2v_model": False
        }},
        "t5_loader": {"class_type": "LoadWanVideoT5TextEncoder", "inputs": {"model_name": T5_MODEL, "precision": "bf16"}},
        "text_encode": {"class_type": "WanVideoTextEncode", "inputs": {"positive_prompt": POSITIVE_PROMPT_SEG3, "negative_prompt": NEGATIVE_PROMPT, "t5": ["t5_loader", 0], "force_offload": True}},
        "high_model_loader": {"class_type": "WanVideoModelLoader", "inputs": {"model": HIGH_MODEL, "base_precision": "bf16", "quantization": "fp8_e4m3fn_scaled", "load_device": "offload_device", "attention_mode": "sageattn"}},
        "block_swap": {"class_type": "WanVideoBlockSwap", "inputs": {"blocks_to_swap": BLOCKS_TO_SWAP, "offload_img_emb": False, "offload_txt_emb": False}},
        "high_set_blockswap": {"class_type": "WanVideoSetBlockSwap", "inputs": {"model": ["high_model_loader", 0], "block_swap_args": ["block_swap", 0]}},
        "high_lora_select": {"class_type": "WanVideoLoraSelect", "inputs": {"lora": LORA_MODEL, "strength": 3.0, "merge_loras": False}},
        "high_set_loras": {"class_type": "WanVideoSetLoRAs", "inputs": {"model": ["high_set_blockswap", 0], "lora": ["high_lora_select", 0]}},
        "low_model_loader": {"class_type": "WanVideoModelLoader", "inputs": {"model": LOW_MODEL, "base_precision": "bf16", "quantization": "fp8_e4m3fn_scaled", "load_device": "offload_device", "attention_mode": "sageattn"}},
        "low_set_blockswap": {"class_type": "WanVideoSetBlockSwap", "inputs": {"model": ["low_model_loader", 0], "block_swap_args": ["block_swap", 0]}},
        "low_lora_select": {"class_type": "WanVideoLoraSelect", "inputs": {"lora": LORA_MODEL, "strength": 1.0, "merge_loras": False}},
        "low_set_loras": {"class_type": "WanVideoSetLoRAs", "inputs": {"model": ["low_set_blockswap", 0], "lora": ["low_lora_select", 0]}},
        "cfg_schedule": {"class_type": "CreateCFGScheduleFloatList", "inputs": {"steps": STEPS, "cfg_scale_start": 2.0, "cfg_scale_end": 2.0, "interpolation": "linear", "start_percent": 0.0, "end_percent": 0.01}},
        "steps_const": {"class_type": "INTConstant", "inputs": {"value": STEPS}},
        "split_step_const": {"class_type": "INTConstant", "inputs": {"value": SPLIT_STEP}},
        "high_sampler": {"class_type": "WanVideoSampler", "inputs": {
            "model": ["high_set_loras", 0], "image_embeds": ["i2v_encode", 0], "text_embeds": ["text_encode", 0],
            "steps": ["steps_const", 0], "cfg": ["cfg_schedule", 0],
            "shift": SHIFT, "seed": SEED, "force_offload": True,
            "scheduler": "dpm++_sde", "rope_function": "comfy", "riflex_freq_index": 0,
            "start_step": 0, "end_step": ["split_step_const", 0]
        }},
        "low_sampler": {"class_type": "WanVideoSampler", "inputs": {
            "model": ["low_set_loras", 0], "image_embeds": ["i2v_encode", 0], "text_embeds": ["text_encode", 0],
            "steps": ["steps_const", 0], "cfg": 1.0, "shift": SHIFT, "seed": SEED, "force_offload": True,
            "scheduler": "dpm++_sde", "rope_function": "comfy", "riflex_freq_index": 0,
            "samples": ["high_sampler", 0], "start_step": ["split_step_const", 0], "end_step": -1
        }},
        "decode": {"class_type": "WanVideoDecode", "inputs": {"vae": ["vae_loader", 0], "samples": ["low_sampler", 0], "enable_vae_tiling": False, "tile_x": 272, "tile_y": 272, "tile_stride_x": 144, "tile_stride_y": 144}},
        "video_combine": {"class_type": "VHS_VideoCombine", "inputs": {
            "images": ["decode", 0], "frame_rate": 24, "loop_count": 0,
            "filename_prefix": f"c5_v13_seg3_{int(time.time())}",
            "format": "video/h264-mp4", "pingpong": False, "save_output": True,
            "crf": 14, "pix_fmt": "yuv420p10le"
        }}
    }


def main():
    print("=" * 60)
    print("v13段3 (CLIP 1.png=1.5/末帧=0.5 + 提示词优化)")
    print(f"  段2末帧: {SEG2_LASTFRAME}")
    print("=" * 60)

    print("\n[段3] 进入教室→拉椅→落座")
    wf = build_seg3()
    data = json.dumps({"prompt": wf}).encode("utf-8")
    req = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=data, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())
    pid = r.get("prompt_id")
    print(f"  prompt_id: {pid}")

    print(f"\n  [段3] 等待...")
    t0 = time.time()
    seg3_video = None
    while True:
        try:
            h = json.loads(urllib.request.urlopen(f"{COMFYUI_URL}/history/{pid}", timeout=30).read())
            if pid in h:
                for nid, no in h[pid].get("outputs", {}).items():
                    if "gifs" in no:
                        for g in no["gifs"]:
                            fp = os.path.join("E:/comfyui-cli/output", g.get("subfolder", ""), g.get("filename", ""))
                            if os.path.exists(fp):
                                seg3_video = fp
                                break
                if seg3_video:
                    break
            print(f"  [段3] 等待中... {time.time()-t0:.0f}秒")
        except:
            pass
        time.sleep(20)

    print(f"\n  [段3] 完成! {time.time()-t0:.0f}秒, {os.path.getsize(seg3_video)/1048576:.2f}MB")
    print(f"  段3视频: {seg3_video}")


if __name__ == "__main__":
    main()
