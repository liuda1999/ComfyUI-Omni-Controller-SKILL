import json
import urllib.request

# 查询object_info获取正确的widget名称
def get_schema(node_type):
    try:
        r = urllib.request.urlopen(f'http://127.0.0.1:3198/object_info/{node_type}', timeout=10)
        d = json.loads(r.read())
        return d[node_type]['input']
    except:
        return {}

# 加载转换后的API工作流
path = 'comfyui-controller/assets/c6_wan22_i2v_api.json'
with open(path, 'r', encoding='utf-8') as f:
    wf = json.load(f)

# === 1. 删除无关节点 ===
remove_ids = [
    "157",  # Note
    "158",  # Note
    "164",  # FancyTimerNode
    "161",  # TextInput_ (positive_prompt来源，需先处理引用)
    "155",  # easy cleanGpuUsed
    "156",  # easy cleanGpuUsed
    "154",  # easy clearCacheAll
    "143",  # ImageFromBatch+
    "163",  # ImageUpscaleWithModel
    "162",  # UpscaleModelLoader (RealESRGAN_x2)
    "145",  # PrimitiveNode (seed)
    "152",  # WanVideoEasyCache (LOW cache)
    "151",  # WanVideoEasyCache (HIGH cache)
    "153",  # WanVideoBlockSwap (用WanVideoSetBlockSwap替代)
    "136",  # CreateCFGScheduleFloatList (不用动态CFG，用固定5.0)
    "137",  # INTConstant (steps，改为直接值)
    "138",  # INTConstant (split_step，改为直接值)
    "122",  # GetImageSizeAndCount
]

for nid in remove_ids:
    if nid in wf:
        del wf[nid]

# === 2. 修改模型加载节点 ===
# 114 = HIGH模型
wf["114"]["inputs"]["model"] = "Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors"
wf["114"]["inputs"]["base_precision"] = "bf16"
wf["114"]["inputs"]["quantization"] = "fp8_e4m3fn_scaled"
wf["114"]["inputs"]["load_device"] = "offload_device"
wf["114"]["inputs"]["attention_mode"] = "sageattn"
# 移除block_swap_args引用（指向已删除的153）
if "block_swap_args" in wf["116"]["inputs"]:
    del wf["116"]["inputs"]["block_swap_args"]

# 115 = LOW模型
wf["115"]["inputs"]["model"] = "Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors"
wf["115"]["inputs"]["base_precision"] = "bf16"
wf["115"]["inputs"]["quantization"] = "fp8_e4m3fn_scaled"
wf["115"]["inputs"]["load_device"] = "offload_device"
wf["115"]["inputs"]["attention_mode"] = "sageattn"
if "block_swap_args" in wf["117"]["inputs"]:
    del wf["117"]["inputs"]["block_swap_args"]

# === 3. 修改LoRA节点 ===
# 124 (用于HIGH模型链): 改为SVI画质LoRA
wf["124"]["inputs"]["lora"] = "SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors"
wf["124"]["inputs"]["strength"] = 1.0

# 123 (用于LOW模型链): 也用SVI画质（HIGH专用LoRA用于LOW可能效果不佳，但比lightx2v安全）
# 实际上LOW模型可以不用LoRA，但WanVideoSetLoRAs节点需要lora输入
# 保持SVI画质，strength=1.0
wf["123"]["inputs"]["lora"] = "SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors"
wf["123"]["inputs"]["strength"] = 1.0

# === 4. 修改VAE ===
wf["119"]["inputs"]["model_name"] = "wan2.2_vae.safetensors"
wf["119"]["inputs"]["precision"] = "bf16"

# === 5. 修改文本编码器 ===
wf["125"]["inputs"]["model_name"] = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
wf["125"]["inputs"]["precision"] = "bf16"
wf["125"]["inputs"]["load_device"] = "offload_device"
wf["125"]["inputs"]["quantization"] = "disabled"

# === 6. 修改LoadImage ===
wf["131"]["inputs"]["image"] = "c6_1.png"

# === 7. 修改WanVideoImageToVideoEncode ===
wf["128"]["inputs"]["width"] = 720
wf["128"]["inputs"]["height"] = 1280
wf["128"]["inputs"]["num_frames"] = 100
wf["128"]["inputs"]["noise_aug_strength"] = 0.1

# === 8. 修改WanVideoTextEncode ===
positive_prompt = (
    "Ancient Chinese style Chang'e, white-haired goddess, wearing deep blue "
    "gold-traced qipao, magnificent blue sapphire phoenix crown, red eyes. "
    "Standing in a moonlit lotus pond in shallow water, slowly and elegantly "
    "rising to stand, then gently walking forward. A glowing white jade rabbit "
    "lively circles around her, lightly hopping. Purple-blue flowing light mist "
    "drifting slowly, gentle ripples on water surface, lotus petals floating "
    "slightly, full moon and ancient pavilion background unchanged, soft and "
    "coherent lighting, stable facial features, smooth cinematic camera movement, "
    "Chinese fantasy xianxia aesthetic, highly consistent with original art style"
)

negative_prompt = (
    "face distortion, facial features deformation, limb clipping, screen flickering, "
    "character model collapse, rabbit deformation, motion freezing, sudden brightness "
    "changes, major composition changes, "
    "worst quality, low quality, JPEG artifacts, blurry, pixelated, "
    "distorted body, deformed limbs, extra limbs, missing limbs, "
    "motion blur, frame skipping, detail degradation"
)

wf["129"]["inputs"]["positive_prompt"] = positive_prompt
wf["129"]["inputs"]["negative_prompt"] = negative_prompt
# 移除positive_prompt对已删除节点161的引用
# 如果positive_prompt是连接引用，改为直接字符串
# 从转换结果看，positive_prompt->[161,0]，需要改为字符串
# 已上面直接赋值为字符串

# === 9. 修改WanVideoSampler (HIGH = 134) ===
# 修正widget映射错误，直接设置正确值
wf["134"]["inputs"] = {
    "model": ["121", 0],          # HIGH模型+BlockSwap+LoRA
    "image_embeds": ["128", 0],    # 图片编码
    "text_embeds": ["129", 0],     # 文本编码
    "steps": 25,                   # 画质LoRA需20-30步
    "cfg": 5.0,                    # 画质LoRA用固定CFG
    "shift": 8.0,                  # Wan2.2源工作流值
    "seed": 987654321,
    "force_offload": True,
    "scheduler": "dpm++_sde",
    "riflex_freq_index": 6,        # 100帧>81帧训练长度
    "denoise_strength": 1.0,
    "rope_function": "comfy_chunked",  # 720x1280高分辨率必须
    "start_step": 0,
    "end_step": 12,                # split_step=12（约一半）
}

# === 10. 修改WanVideoSampler (LOW = 135) ===
wf["135"]["inputs"] = {
    "model": ["118", 0],          # LOW模型+BlockSwap+LoRA
    "image_embeds": ["128", 0],    # 图片编码
    "text_embeds": ["129", 0],     # 文本编码
    "samples": ["134", 0],         # HIGH采样输出
    "steps": 25,
    "cfg": 5.0,
    "shift": 8.0,
    "seed": 987654321,
    "force_offload": True,
    "scheduler": "dpm++_sde",
    "riflex_freq_index": 6,
    "denoise_strength": 1.0,
    "rope_function": "comfy_chunked",
    "start_step": 12,              # 从split_step开始
    "end_step": -1,                # 到最后
    "add_noise_to_samples": False, # 不添加噪声
}

# === 11. 修改WanVideoDecode ===
wf["120"]["inputs"]["tile_x"] = False
wf["120"]["inputs"]["tile_y"] = 272
wf["120"]["inputs"]["tile_stride_x"] = 272
wf["120"]["inputs"]["tile_stride_y"] = 144
wf["120"]["inputs"]["normalization"] = "128"
wf["120"]["inputs"]["vae"] = ["119", 0]
wf["120"]["inputs"]["samples"] = ["135", 0]  # LOW采样输出

# === 12. 修改VHS_VideoCombine ===
wf["126"]["inputs"] = {
    "images": ["120", 0],          # 解码输出
    "frame_rate": 20,
    "loop_count": 0,
    "filename_prefix": "c6_chang_e",
    "format": "video/h264-mp4",
    "pix_fmt": "yuv420p10le",
    "crf": 14,
    "save_metadata": False,
    "trim_to_audio": False,
    "pingpong": False,
    "save_output": True,
}

# === 13. 保存修改后的工作流 ===
output_path = 'comfyui-controller/assets/c6_wan22_i2v_final.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(wf, f, indent=2, ensure_ascii=False)

print(f"工作流已保存: {output_path}")
print(f"剩余节点数: {len(wf)}")
print("\n=== 最终节点列表 ===")
for nid, node in sorted(wf.items(), key=lambda x: int(x[0])):
    ct = node.get('class_type', '')
    print(f"  {nid}: {ct}")
