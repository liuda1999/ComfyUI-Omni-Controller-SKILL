"""生成简化测试工作流：1段，41帧，848x480，验证降低帧数能否解决OOM。"""
import json
import os

WIDTH = 848
HEIGHT = 480
LENGTH = 41  # 降低帧数
STEPS = 6
STEPS2 = 2
SEED = 214

MODEL_FILE = "Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors"
VAE_FILE = "comfy-wan_2.1_vae.safetensors"
CLIP_FILE = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
LORA_FILE = "SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors"
LORA_STRENGTH = 1.0
WEIGHT_DTYPE = "default"

INPUT_IMAGE = "c7_1.png"

POSITIVE = "一个漂亮的女孩，站在原地，缓慢转身360度，微笑表情，自然流畅的动作，光线柔和，高清画质"
NEGATIVE = "色调艳丽，过曝，静态，细节模糊不清，字幕，最差质量，低质量，丑陋的，残缺的"

wf = {}

# HIGH 链路
wf["g_unet_high"] = {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL_FILE, "weight_dtype": WEIGHT_DTYPE}}
wf["g_lora_high"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["g_unet_high", 0], "lora_name": LORA_FILE, "strength_model": LORA_STRENGTH}}
wf["g_sage_high"] = {"class_type": "PathchSageAttentionKJ", "inputs": {"model": ["g_lora_high", 0], "sage_attention": "auto", "allow_compile": False}}
wf["g_torch_high"] = {"class_type": "ModelPatchTorchSettings", "inputs": {"model": ["g_sage_high", 0], "enable_fp16_accumulation": True}}

# LOW 链路
wf["g_unet_low"] = {"class_type": "UNETLoader", "inputs": {"unet_name": MODEL_FILE, "weight_dtype": WEIGHT_DTYPE}}
wf["g_lora_low"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["g_unet_low", 0], "lora_name": LORA_FILE, "strength_model": LORA_STRENGTH}}
wf["g_sage_low"] = {"class_type": "PathchSageAttentionKJ", "inputs": {"model": ["g_lora_low", 0], "sage_attention": "auto", "allow_compile": False}}
wf["g_torch_low"] = {"class_type": "ModelPatchTorchSettings", "inputs": {"model": ["g_sage_low", 0], "enable_fp16_accumulation": True}}

# 共享节点
wf["g_clip"] = {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_FILE, "type": "wan"}}
wf["g_vae"] = {"class_type": "VAELoader", "inputs": {"vae_name": VAE_FILE}}
wf["g_loadimage"] = {"class_type": "LoadImage", "inputs": {"image": INPUT_IMAGE}}
wf["g_resize"] = {"class_type": "ImageResizeKJv2", "inputs": {"image": ["g_loadimage", 0], "width": WIDTH, "height": HEIGHT, "upscale_method": "lanczos", "keep_proportion": "crop", "pad_color": "0, 0, 0", "crop_position": "center", "divisible_by": 16, "device": "cpu"}}
wf["g_vaeencode"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["g_resize", 0], "vae": ["g_vae", 0]}}

# 1段采样
wf["clip_pos"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["g_clip", 0], "text": POSITIVE}}
wf["clip_neg"] = {"class_type": "CLIPTextEncode", "inputs": {"clip": ["g_clip", 0], "text": NEGATIVE}}
wf["svi"] = {"class_type": "WanImageToVideoSVIPro", "inputs": {"positive": ["clip_pos", 0], "negative": ["clip_neg", 0], "anchor_samples": ["g_vaeencode", 0], "length": LENGTH, "motion_latent_count": 0}}
wf["ks_high"] = {"class_type": "KSamplerAdvanced", "inputs": {"model": ["g_torch_high", 0], "positive": ["svi", 0], "negative": ["svi", 1], "latent_image": ["svi", 2], "add_noise": "enable", "noise_seed": SEED, "steps": STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": 0, "end_at_step": STEPS2, "return_with_leftover_noise": "enable"}}
wf["ks_low"] = {"class_type": "KSamplerAdvanced", "inputs": {"model": ["g_torch_low", 0], "positive": ["svi", 0], "negative": ["svi", 1], "latent_image": ["ks_high", 0], "add_noise": "disable", "noise_seed": SEED, "steps": STEPS, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "start_at_step": STEPS2, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}
wf["vaedecode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["ks_low", 0], "vae": ["g_vae", 0]}}
wf["video"] = {"class_type": "VHS_VideoCombine", "inputs": {"images": ["vaedecode", 0], "frame_rate": 20, "loop_count": 0, "filename_prefix": "c7_test_41f", "format": "video/h264-mp4", "pix_fmt": "yuv420p", "crf": 20, "save_metadata": True, "trim_to_audio": False, "pingpong": False, "save_output": True}}

output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "c7_test_41f.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)

print(f"测试工作流已生成: {output_path}")
print(f"帧数: {LENGTH}, 分辨率: {WIDTH}x{HEIGHT}, 时长: {LENGTH/20:.2f}秒")
