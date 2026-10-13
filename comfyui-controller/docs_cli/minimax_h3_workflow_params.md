# MiniMax H3 工作流 · 节点参数说明书

> 本文档为 6 个 MiniMax H3 工作流的**逐节点参数参考**，与其他智能体「加载即用」直接相关。
> 每个节点的**真实参数值**取自工作流 UI JSON 的 `widgets_values`；关键节点类型的**参数标准**（类型/默认/取值范围/含义/来源）见 `assets/node_parameter_standards.json`。
> 仅对“有真实数据/标准 ComfyUI 语义”的参数下笔；无法确认的仅列观测值并标注“见节点包源码”，绝不臆造。

> ⚠️ 运行前提：需 NVIDIA 大显存 + ComfyUI 0.30.0+ + 第三方节点包 + 数十 GB 权重。当前设备无 GPU，仅做格式/参数核查与文档交付，运行请在测试环境进行。

---

## minimax_h3_t2v_turbo_v1.0.0

> 用途：文生视频 T2V · FL2V Turbo 4 步快速版 ｜ 节点数：21 ｜ 格式：UI (ComfyUI 界面可加载)

### ① 模型/编码器加载

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 119 | `VAELoader` | — | vae_name=minimax_h3_video_vae_fp16.safetensors | 标准参数 1 项见 standards.json |
| 120 | `VAELoader` | — | vae_name=minimax_h3_audio_vae_fp32.safetensors | 标准参数 1 项见 standards.json |
| 128 | `CLIPLoader` | — | clip_name=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors；type=minimax；device=default | 标准参数 3 项见 standards.json |
| 127 | `UNETLoader` | — | unet_name=minimax_h3_ref2va_pruned_fp8_scaled.safetensors；weight_dtype=default | 标准参数 2 项见 standards.json |
| 134 | `MiniMaxH3TurboLoRA` | — | lora_name=minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_resi；strength=1；low_vram=False | 标准参数 3 项见 standards.json |

### ② 采样器

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 125 | `SamplerCustomAdvanced` | — | （无 widget，参数经连线输入） |  |
| 126 | `BasicGuider` | — | （无 widget，参数经连线输入） |  |
| 135 | `MiniMaxH3TurboSampler` | — | （无 widget，参数经连线输入） | 该节点无 widgets_values；其参数（步数/调度器/双 VAE 等）由上游连线提供，详见工作流连线。 |

### ③ 调度/噪声

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 129 | `RandomNoise` | — | noise_seed=416835429951143；control_after_generate=randomize | 标准参数 2 项见 standards.json |
| 124 | `BasicScheduler` | — | scheduler=simple；steps=20；denoise=1 | 标准参数 3 项见 standards.json |

### ④ H3 生成主节点

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 131 | `MiniMaxH3ImageToVideo` | — | prompt=写实摄影，恐怖电影场景，中长焦微距镜头，平视略带侧面视角，竖幅中景。器材为索尼A7 IV搭配FE 9；width=1344；height=768；length=73 | 标准参数 5 项见 standards.json |

### ⑦ 输出/IO

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 121 | `VAEDecodeAudio` | — | （无 widget，参数经连线输入） |  |
| 122 | `VAEDecode` | — | （无 widget，参数经连线输入） |  |
| 130 | `CreateVideo` | — | fps=24；bit_depth=8；color_space=sRGB |  |
| 92 | `SaveVideo` | — | filename_prefix=video/MiniMax_H3；format=auto；format.codec=auto；codec=auto | 标准参数 3 项见 standards.json |

### ⑧ 工具/条件/文本

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 116 | `MarkdownNote` | Note: MiniMax H3 | text=## MiniMax H3  [MiniMax H3](https://www.minimax.io |  |
| 117 | `MarkdownNote` | Note: Model Links | text=## Model Links  **vae**  - [minimax_h3_video_vae_f |  |
| 133 | `PrimitiveFloat` | Float (duration) | value=5 |  |
| 132 | `ComfyMathExpression` | — | expression=max(5, round(a * 24)) + (5 - (max(5, round(a * 24) |  |
| 118 | `MarkdownNote` | Note: Size Settings Reference | text=| megapixels | Aspect | Output (multiple=32) | |-- |  |
| 115 | `ResolutionSelector` | — | aspect_ratio=16:9 (Widescreen)；megapixels=0.4；multiple=32 | 标准参数 3 项见 standards.json |

---

## minimax_h3_fl2va_first_last_frame_v1.0.0

> 用途：首/尾帧参考生视频 FL2VA · 开源版 ｜ 节点数：35 ｜ 格式：UI (ComfyUI 界面可加载)

### ① 模型/编码器加载

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 3 | `RHMiniMaxH3FL2VAVAELoader` | FL2VA Dual VAE Loader | model_root=MiniMax-H3；video_vae_path=MiniMax-H3-video_vae.safetensors；audio_vae_path=MiniMax-H3-audio_vae.safetensors | 标准参数 3 项见 standards.json |
| 2 | `RHMiniMaxH3FL2VAModelLoader` | FL2VA DiT Loader | model_root=MiniMax-H3；dtype=auto；transformer_path=MiniMax-H3-FL2VA-int8_convrot.safetensors | 标准参数 3 项见 standards.json |
| 1 | `RHMiniMaxH3FL2VATextEncoderLoader` | FL2VA Qwen3-VL Loader | model_root=MiniMax-H3；dtype=auto；text_encoder_path=qwen3-vl-32b-int8_convrot.safetensors | 标准参数 3 项见 standards.json |
| 6 | `LoadImage` | — | image=0ef234cfae9a607e3b3f9e33ee518f952ad2eaac0fb7dc8e24；upload=image | 标准参数 2 项见 standards.json |
| 4 | `LoadImage` | — | image=a90b99d9fe38257cd05c1ccc05b6604e323e1bc48a9a1ad5bd；upload=image | 标准参数 2 项见 standards.json |

### ② 采样器

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 10 | `RHMiniMaxH3DualSigmaSampler` | Dual Sigma Sampler | seed=42；control_after_generate=fixed；sigma_points=50；video_shift=12；audio_shift=3；accel=manual-velocity；denoise_video=True；cache_dit_rdt=0.12；cache_dit_mc=2；cache_dit_warmup=4；velocity_stride=4；sampler_mode=euler；allow_accel_with_res_multistep=False |  |

### ④ H3 生成主节点

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 7 | `RHMiniMaxH3FL2VATarget` | — | aspect_ratio=4:3；duration_seconds=5；width=832；height=480 |  |
| 8 | `RHMiniMaxH3FL2VAEncode` | — | prompt=0-2s: medium wide shot, the boy raises hand to adj |  |
| 9 | `RHMiniMaxH3EmptyAVLatent` | Empty AV Latent | （无 widget，参数经连线输入） |  |
| 11 | `RHMiniMaxH3DecodeAV` | Decode Video + Audio | （无 widget，参数经连线输入） |  |
| 5 | `RHMiniMaxH3FL2VAFirstFrameCondition` | First / First+Last | （无 widget，参数经连线输入） |  |

### ⑦ 输出/IO

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 12 | `CreateVideo` | — | fps=24；bit_depth=8；color_space=sRGB |  |
| 34 | `PreviewImage` | — | （无 widget，参数经连线输入） |  |
| 13 | `SaveVideo` | — | filename_prefix=minimax_h3/fl2va_first_last_frame；format=mp4；format.codec=h264；format.codec.encoding=auto；codec=auto | 标准参数 3 项见 standards.json |

### ⑧ 工具/条件/文本

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 14 | `MarkdownNote` | — | text=# 素材可以在链接里找 https://vrfi1sk8a0.feishu.cn/wiki/FIWj |  |
| 15 | `Int` | — | Number=640 |  |
| 16 | `Int` | — | Number=576 |  |
| 17 | `Int` | — | Number=768 |  |
| 18 | `Int` | — | Number=768 |  |
| 19 | `Int` | — | Number=576 |  |
| 20 | `Int` | — | Number=432 |  |
| 21 | `Int` | — | Number=768 |  |
| 22 | `Int` | — | Number=640 |  |
| 25 | `Note` | — | text=图像比例 数字1-----1:1 数字2-----3:4 数字3-----4:3 数字4-----9 |  |
| 26 | `Int` | — | Number=432 |  |
| 27 | `Int` | — | Number=768 |  |
| 28 | `Int` | — | Number=768 |  |
| 29 | `Int` | — | Number=432 |  |
| 31 | `Reroute` | — | （无 widget，参数经连线输入） |  |
| 24 | `ImpactSwitch` | — | select=3；sel_mode=False |  |
| 23 | `ImpactSwitch` | — | select=1；sel_mode=False |  |
| 30 | `ImageResize+` | — | width=832；height=832；interpolation=nearest；method=keep proportion；condition=always；multiple_of=32 |  |
| 35 | `ImageResize+` | — | width=832；height=832；interpolation=nearest；method=keep proportion；condition=always；multiple_of=32 |  |
| 33 | `ImageResize+` | — | width=832；height=832；interpolation=nearest；method=fill / crop；condition=always；multiple_of=32 |  |
| 36 | `ImageResize+` | — | width=832；height=832；interpolation=nearest；method=fill / crop；condition=always；multiple_of=32 |  |

---

## minimax_h3_ref2v_av_turbo_v1.0.0

> 用途：多参图像+音频极速生视频 Ref2VA ｜ 节点数：62 ｜ 格式：UI (ComfyUI 界面可加载)

### ① 模型/编码器加载

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 139 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 127 | `UNETLoader` | — | unet_name=minimax_h3_ref2va_pruned_fp8_scaled.safetensors；weight_dtype=default | 标准参数 2 项见 standards.json |
| 206 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 161 | `LoadImage` | — | image=rgthree.compare._temp_ocpsj_00048_.png；upload=image | 标准参数 2 项见 standards.json |
| 247 | `LoadAudio` | — | audio=None；upload=None | 标准参数 2 项见 standards.json |
| 248 | `LoadAudio` | — | audio=None；upload=None | 标准参数 2 项见 standards.json |
| 249 | `LoadAudio` | — | audio=None；upload=None | 标准参数 2 项见 standards.json |
| 231 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 234 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 237 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 232 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 235 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 238 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 233 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 236 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 239 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 128 | `CLIPLoader` | — | clip_name=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors；type=minimax；device=default | 标准参数 3 项见 standards.json |
| 119 | `VAELoader` | — | vae_name=minimax_h3_video_vae_fp16.safetensors | 标准参数 1 项见 standards.json |
| 120 | `VAELoader` | — | vae_name=minimax_h3_audio_vae_fp32.safetensors | 标准参数 1 项见 standards.json |
| 251 | `LoadVideo` | — | file=None；upload=True |  |
| 254 | `LoadVideo` | — | file=None；upload=True |  |
| 256 | `LoadVideo` | — | file=None；upload=True |  |
| 257 | `LoraLoaderModelOnly` | — | lora_name=minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_res；strength_model=1 | 标准参数 2 项见 standards.json |

### ② 采样器

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 123 | `KSamplerSelect` | — | sampler_name=ddim | 标准参数 1 项见 standards.json |
| 126 | `BasicGuider` | — | （无 widget，参数经连线输入） |  |
| 125 | `SamplerCustomAdvanced` | ⚡自定义采样器（高级）⚡ | （无 widget，参数经连线输入） |  |

### ③ 调度/噪声

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 124 | `BasicScheduler` | — | scheduler=simple；steps=20；denoise=1 | 标准参数 3 项见 standards.json |
| 129 | `RandomNoise` | — | noise_seed=1010219011590650；control_after_generate=randomize | 标准参数 2 项见 standards.json |

### ④ H3 生成主节点

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 230 | `MiniMaxH3ReferenceToVideo` | — | prompt=；width=1344；height=768；length=124；ref_image_size=match | 标准参数 5 项见 standards.json |

### ⑥ 性能/注意力优化

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 136 | `EasyCache` | — | reuse_threshold=0.20000000000000004；start_percent=0.15；end_percent=0.9000000000000001；verbose=False | 标准参数 4 项见 standards.json |
| 135 | `PathchSageAttentionKJ` | — | sage_attention=auto；allow_compile=False |  |

### ⑦ 输出/IO

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 121 | `VAEDecodeAudio` | — | （无 widget，参数经连线输入） |  |
| 130 | `CreateVideo` | — | fps=24；bit_depth=8；color_space=sRGB |  |
| 122 | `VAEDecode` | — | （无 widget，参数经连线输入） |  |
| 227 | `ShowAnything|Mie` | — | （无 widget，参数经连线输入） |  |
| 226 | `ShowAnything|Mie` | — | （无 widget，参数经连线输入） |  |
| 92 | `SaveVideo` | — | filename_prefix=video/MiniMax_H3；format=auto；format.codec=auto；codec=auto | 标准参数 3 项见 standards.json |
| 252 | `GetVideoComponents` | — | （无 widget，参数经连线输入） |  |
| 253 | `GetVideoComponents` | — | （无 widget，参数经连线输入） |  |
| 255 | `GetVideoComponents` | — | （无 widget，参数经连线输入） |  |

### ⑧ 工具/条件/文本

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 164 | `DF_Int_to_Float` | — | Value=5 |  |
| 191 | `DF_Int_to_Float` | — | Value=6 |  |
| 192 | `DF_Int_to_Float` | — | Value=7 |  |
| 193 | `DF_Int_to_Float` | — | Value=8 |  |
| 194 | `DF_Int_to_Float` | — | Value=9 |  |
| 195 | `DF_Int_to_Float` | — | Value=10 |  |
| 196 | `DF_Int_to_Float` | — | Value=11 |  |
| 197 | `DF_Int_to_Float` | — | Value=12 |  |
| 198 | `DF_Int_to_Float` | — | Value=13 |  |
| 199 | `DF_Int_to_Float` | — | Value=14 |  |
| 200 | `DF_Int_to_Float` | — | Value=15 |  |
| 117 | `MarkdownNote` | Note: Model Links | text=## Model Links  **vae**  - [minimax_h3_video_vae_f |  |
| 116 | `MarkdownNote` | Note: MiniMax H3 | text=## MiniMax H3  [MiniMax H3](https://www.minimax.io |  |
| 222 | `PrimitiveFloat` | — | value=0.5 |  |
| 210 | `Note` | — | text=480P（标清 SD） |  |
| 205 | `ImpactSwitch` | — | select=11；sel_mode=False |  |
| 115 | `ResolutionSelector` | — | aspect_ratio=4:3 (Standard)；megapixels=0.5；multiple=32 | 标准参数 3 项见 standards.json |
| 132 | `ComfyMathExpression` | — | expression=max(5, round(a * 24)) + (5 - (max(5, round(a * 24) |  |
| 223 | `PrimitiveFloat` | — | value=1 |  |
| 211 | `Note` | — | text=720P（高清 HD） |  |
| 225 | `ImpactSwitch` | — | select=1；sel_mode=False |  |
| 250 | `CR Prompt Text` | — | prompt=一镜到底低空环绕滑行镜头，黏土二次元少女悬浮在蓬松黏土云海之上，长发、纱裙为蓬松黏土塑形，细碎星光黏 |  |

---

## minimax_h3_ref2v_multi_reference_v1.0.0

> 用途：多参考生视频优化版（含 latent 3D 放大二采） ｜ 节点数：119 ｜ 格式：UI (ComfyUI 界面可加载)

### ① 模型/编码器加载

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 19 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 23 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 36 | `VAELoader` | — | vae_name=minimax_h3_video_vae_int8_convrot.safetensors | 标准参数 1 项见 standards.json |
| 37 | `VAELoader` | — | vae_name=minimax_h3_audio_vae_fp32.safetensors | 标准参数 1 项见 standards.json |
| 26 | `VHS_LoadVideo` | — | video=；force_rate=0；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'paused': False, 'hidden': False, 'params': {'cus | 标准参数 3 项见 standards.json |
| 27 | `VHS_LoadVideo` | — | video=；force_rate=0；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'paused': False, 'hidden': False, 'params': {'cus | 标准参数 3 项见 standards.json |
| 25 | `VHS_LoadVideo` | — | video=；force_rate=0；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'paused': False, 'hidden': False, 'params': {'cus | 标准参数 3 项见 standards.json |
| 199 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 200 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 201 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 51 | `LoadImage` | — | image=c715baaee3fa989a7a8c94643fb7945e36f943b91a5a28182e；upload=image | 标准参数 2 项见 standards.json |
| 49 | `LoadImage` | — | image=0fbb787fb39ffa24b5da3f3e6575b54b3d8a65320977dd2a07；upload=image | 标准参数 2 项见 standards.json |
| 50 | `LoadImage` | — | image=5d71adebf3aaa447f8a50300f75ee521b8f63af71fc8a1d8de；upload=image | 标准参数 2 项见 standards.json |
| 53 | `LoraLoaderModelOnly` | — | lora_name=minimax_h3_turbo_v4_step600_ema_pruned_comfyui.saf；strength_model=1.0000000000000002 | 标准参数 2 项见 standards.json |
| 38 | `CLIPLoader` | — | clip_name=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors；type=minimax；device=default | 标准参数 3 项见 standards.json |
| 48 | `LoadAudio` | — | audio=None；upload=None | 标准参数 2 项见 standards.json |
| 14 | `LoadAudio` | — | audio=None；upload=None | 标准参数 2 项见 standards.json |
| 15 | `LoadAudio` | — | audio=None；upload=None | 标准参数 2 项见 standards.json |
| 192 | `UNETLoader` | — | unet_name=minimax_h3_hybrid_fl2va_ref2va_b25-49-int8.safeten；weight_dtype=default | 标准参数 2 项见 standards.json |
| 322 | `LoraLoaderModelOnly` | — | lora_name=wushu_spatial_physics_v2_1000_pruned.safetensors；strength_model=0.30000000000000004 | 标准参数 2 项见 standards.json |
| 128 | `LoraLoaderModelOnly` | — | lora_name=MysticXXX_MMH3-V1.safetensors；strength_model=0.5000000000000001 | 标准参数 2 项见 standards.json |
| 43 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |

### ② 采样器

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 226 | `SamplerCustomAdvanced` | — | （无 widget，参数经连线输入） |  |
| 223 | `BasicGuider` | — | （无 widget，参数经连线输入） |  |
| 144 | `SamplerCustomAdvanced` | — | （无 widget，参数经连线输入） |  |
| 255 | `KSamplerSelect` | — | sampler_name=euler | 标准参数 1 项见 standards.json |

### ③ 调度/噪声

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 256 | `RandomNoise` | — | noise_seed=629900698231524；control_after_generate=randomize | 标准参数 2 项见 standards.json |
| 261 | `BasicScheduler` | — | scheduler=beta；steps=12；denoise=1 | 标准参数 3 项见 standards.json |
| 289 | `SplitSigmas` | — | step=8 | 标准参数 1 项见 standards.json |

### ④ H3 生成主节点

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 265 | `MiniMaxH3ReferenceToVideo` | — | prompt=；width=1344；height=768；length=124；ref_image_size=max | 标准参数 5 项见 standards.json |

### ⑤ 放大/长视频

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 140 | `MinimaxH3LatentUpscaler3D` | — | model_name=minimax_h3_latent_upscaler_3d_fp16.safetensors；mode=scale by multiplier；mode.scale=1.5000000000000002；align=32；keep_proportion=cuda；device=fp16；precision=False；offload_after_upscale=False | 标准参数 8 项见 standards.json |

### ⑥ 性能/注意力优化

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 58 | `MiniMaxH3MemoryEfficientSageAttentionPatch` | — | （无 widget，参数经连线输入） |  |

### ⑦ 输出/IO

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 254 | `VAEDecodeAudio` | — | （无 widget，参数经连线输入） |  |
| 253 | `VAEDecode` | — | （无 widget，参数经连线输入） |  |
| 116 | `VAEDecode` | — | （无 widget，参数经连线输入） |  |
| 115 | `VAEDecodeAudio` | — | （无 widget，参数经连线输入） |  |
| 264 | `VHS_VideoCombine` | — | frame_rate=24；loop_count=0；filename_prefix=YZ_H3_一采；format=video/h264-mp4；pix_fmt=yuv420p；crf=19；save_metadata=True；trim_to_audio=False；pingpong=False；save_output=False；videopreview={'paused': False, 'hidden': False, 'params': {'sco | 标准参数 4 项见 standards.json |
| 214 | `VHS_VideoCombine` | — | frame_rate=24；loop_count=0；filename_prefix=YZ_H3_二采；format=video/h264-mp4；pix_fmt=yuv420p；crf=19；save_metadata=True；trim_to_audio=False；pingpong=False；save_output=True；videopreview={'paused': False, 'hidden': False, 'params': {'sco | 标准参数 4 项见 standards.json |

### ⑧ 工具/条件/文本

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 40 | `SetNode` | — | Constant=Audio_VAE |  |
| 6 | `SetNode` | — | Constant=图像2 |  |
| 5 | `SetNode` | — | Constant=图像1 |  |
| 17 | `SetNode` | — | Constant=图像4 |  |
| 20 | `SetNode` | — | Constant=图像5 |  |
| 7 | `SetNode` | — | Constant=图像3 |  |
| 13 | `SetNode` | — | Constant=参考视频3 |  |
| 12 | `SetNode` | — | Constant=参考视频2 |  |
| 11 | `SetNode` | — | Constant=参考视频1 |  |
| 1 | `SetNode` | — | Constant=CLIP |  |
| 22 | `SetNode` | — | Constant=图像6 |  |
| 202 | `SetNode` | — | Constant=图像7 |  |
| 203 | `SetNode` | — | Constant=图像8 |  |
| 204 | `SetNode` | — | Constant=图像9 |  |
| 59 | `Note` | — | text=混合限制‌： 所有素材（图 + 视频 + 音频）混合输入时，总数不得超过‌12 个‌！！ |  |
| 24 | `Note` | — | text=参考图像最多只能接入9张图像，如果不接入就用开关关掉 |  |
| 114 | `GetNode` | — | Constant=Audio_VAE |  |
| 35 | `SetNode` | — | Constant=Video_VAE |  |
| 220 | `Reroute` | — | （无 widget，参数经连线输入） |  |
| 221 | `Reroute` | — | （无 widget，参数经连线输入） |  |
| 242 | `GetNode` | — | Constant=Audio_VAE |  |
| 243 | `GetNode` | — | Constant=Video_VAE |  |
| 244 | `GetNode` | — | Constant=CLIP |  |
| 246 | `GetNode` | — | Constant=Video_VAE |  |
| 247 | `GetNode` | — | Constant=Audio_VAE |  |
| 241 | `GetNode` | — | Constant=图像1 |  |
| 239 | `GetNode` | — | Constant=图像2 |  |
| 240 | `GetNode` | — | Constant=图像3 |  |
| 238 | `GetNode` | — | Constant=图像4 |  |
| 237 | `GetNode` | — | Constant=图像5 |  |
| 236 | `GetNode` | — | Constant=图像6 |  |
| 235 | `GetNode` | — | Constant=图像7 |  |
| 234 | `GetNode` | — | Constant=图像8 |  |
| 233 | `GetNode` | — | Constant=图像9 |  |
| 228 | `GetNode` | — | Constant=参考视频2 |  |
| 227 | `GetNode` | — | Constant=参考视频3 |  |
| 229 | `GetNode` | — | Constant=参考音频1 |  |
| 230 | `GetNode` | — | Constant=参考音频2 |  |
| 232 | `GetNode` | — | Constant=参考音频3 |  |
| 267 | `GetNode` | — | Constant=提示词 |  |
| 272 | `GetNode` | — | Constant=宽度 |  |
| 273 | `GetNode` | — | Constant=高度 |  |
| 270 | `SetNode` | — | Constant=宽度 |  |
| 271 | `SetNode` | — | Constant=高度 |  |
| 278 | `GetNode` | — | Constant=时长 |  |
| 231 | `GetNode` | — | Constant=参考视频1 |  |
| 286 | `SetNode` | — | Constant=二采倍数 |  |
| 250 | `ComfyMathExpression` | — | expression=max(5, round(a * 24)) + (5 - (max(5, round(a * 24) |  |
| 277 | `SetNode` | — | Constant=时长 |  |
| 292 | `SetNode` | — | Constant=噪波 |  |
| 293 | `SetNode` | — | Constant=引导 |  |
| 294 | `SetNode` | — | Constant=采样器 |  |
| 291 | `SetNode` | — | Constant=一采Latent |  |
| 121 | `GetNode` | — | Constant=Video_VAE |  |
| 142 | `LTXVConcatAVLatent` | — | （无 widget，参数经连线输入） |  |
| 287 | `GetNode` | — | Constant=二采倍数 |  |
| 248 | `MarkdownNote` | 分辨率示例 | text=| megapixels | Aspect | Output (multiple=32) | |-- |  |
| 297 | `GetNode` | — | Constant=引导 |  |
| 298 | `GetNode` | — | Constant=采样器 |  |
| 296 | `GetNode` | — | Constant=噪波 |  |
| 299 | `GetNode` | — | Constant=low_sigmas |  |
| 295 | `GetNode` | — | Constant=一采Latent |  |
| 139 | `LTXVSeparateAVLatent` | — | （无 widget，参数经连线输入） |  |
| 309 | `忽略多组孤海` | — |  |  |
| 308 | `忽略多组孤海` | — |  |  |
| 46 | `Note` | — | text=支持最多‌3 段音频‌（需与图像或视频搭配，总时长不超 15 秒），用于设置节奏、对白或环境声。 支 |  |
| 10 | `SetNode` | — | Constant=参考音频1 |  |
| 9 | `SetNode` | — | Constant=参考音频2 |  |
| 8 | `SetNode` | — | Constant=参考音频3 |  |
| 311 | `Note` | — | text=基础调度器上的步数为总步数，分离sigmas上的为一采步数（不能低于6）总步数减去一采的步数就等于二 |  |
| 310 | `忽略多组孤海` | — |  |  |
| 290 | `SetNode` | — | Constant=low_sigmas |  |
| 251 | `GetNode` | — | Constant=模型 |  |
| 39 | `SetNode` | — | Constant=模型 |  |
| 259 | `PrimitiveFloat` | 视频时长（秒） | value=10 |  |
| 252 | `ResolutionSelector` | — | aspect_ratio=16:9 (Widescreen)；megapixels=0.5；multiple=32 | 标准参数 3 项见 standards.json |
| 263 | `Text` | — | text=subject_definitions: <Subject 1> is the female doc |  |
| 266 | `SetNode` | — | Constant=提示词 |  |
| 307 | `忽略多组孤海` | — |  |  |
| 300 | `Note` | — | text=分辨率示例里的megapixels值是上面分辨率选择里的参考值，而不是二采倍数的参考值，二采倍数需要 |  |
| 283 | `easy float` | — | value=1.5000000000000002 |  |

---

## minimax_h3_all_in_one_v1.0.0

> 用途：综合全能版（社区整合流） ｜ 节点数：79 ｜ 格式：UI (ComfyUI 界面可加载)

### ① 模型/编码器加载

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 225 | `LoadAudio` | — | audio=TE-Speed-FlashVSR_00016.mp4；upload=None | 标准参数 2 项见 standards.json |
| 224 | `LoadAudio` | — | audio=TE-Speed-FlashVSR_00016.mp4；upload=None | 标准参数 2 项见 standards.json |
| 226 | `LoadAudio` | — | audio=TE-Speed-FlashVSR_00016.mp4；upload=None | 标准参数 2 项见 standards.json |
| 233 | `VHS_LoadVideo` | — | video=VID_20260907_130048.mp4；force_rate=0；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'paused': False, 'hidden': False, 'params': {'cus | 标准参数 3 项见 standards.json |
| 234 | `VHS_LoadVideo` | — | video=VID_20260907_130048.mp4；force_rate=0；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'paused': False, 'hidden': False, 'params': {'cus | 标准参数 3 项见 standards.json |
| 221 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 215 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 223 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 222 | `LoadImage` | — | image=None；upload=image | 标准参数 2 项见 standards.json |
| 218 | `LoadImage` | — | image=Krea2-20260920175333_00001_.png；upload=image | 标准参数 2 项见 standards.json |
| 220 | `LoadImage` | — | image=Flux2-Klein-4b-base_00011_.png；upload=image | 标准参数 2 项见 standards.json |
| 219 | `LoadImage` | — | image=ComfyUI_temp_mpsab_00001_.png；upload=image | 标准参数 2 项见 standards.json |
| 127 | `UNETLoader` | — | unet_name=H3\minimax_h3_ref2va_pruned_int8_convrot.safetenso；weight_dtype=default | 标准参数 2 项见 standards.json |
| 217 | `LoadImage` | — | image=Qwen_image_2.1_00010.png；upload=image | 标准参数 2 项见 standards.json |
| 184 | `VAELoader` | — | vae_name=H3\minimax_h3_audio_vae_fp32.safetensors | 标准参数 1 项见 standards.json |
| 280 | `VAELoader` | — | vae_name=H3\minimax_h3_video_vae_int8_convrot.safetensors | 标准参数 1 项见 standards.json |
| 145 | `LoraLoaderModelOnly` | — | lora_name=H3\minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_；strength_model=1 | 标准参数 2 项见 standards.json |
| 128 | `CLIPLoader` | — | clip_name=H3\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors；type=minimax；device=default | 标准参数 3 项见 standards.json |
| 232 | `VHS_LoadVideo` | — | video=9月25日(2).mp4；force_rate=0；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'paused': False, 'hidden': False, 'params': {'cus | 标准参数 3 项见 standards.json |
| 216 | `LoadImage` | — | image=Qwen_image_2.1_00009.png；upload=image | 标准参数 2 项见 standards.json |
| 279 | `LoraLoaderModelOnly` | — | lora_name=H3\H3_Combat_V2.safetensors；strength_model=0.9 | 标准参数 2 项见 standards.json |

### ② 采样器

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 147 | `H3SigmaRefiner` | — | extra_steps=1；start_at_sigma=0.7；end_at_sigma=0；spacing=cosine | 标准参数 4 项见 standards.json |
| 123 | `KSamplerSelect` | — | sampler_name=euler | 标准参数 1 项见 standards.json |
| 171 | `SelfLiftH3Sampler` | — | seed=993477651853231；control_after_generate=randomize；cfg=1；transition_step=8；lowres_scale=0.4；rho=0；w_min=0.2；w_max=1；upscaler_model=minimax_h3_latent_upscaler_3d_fp16.safetensors；highres_tiling=True | 标准参数 10 项见 standards.json |

### ③ 调度/噪声

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 124 | `BasicScheduler` | — | scheduler=beta；steps=12；denoise=1 | 标准参数 3 项见 standards.json |

### ④ H3 生成主节点

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 247 | `MiniMaxH3ReferenceToVideo` | — | prompt=；width=1344；height=768；length=124；ref_image_size=max | 标准参数 5 项见 standards.json |

### ⑥ 性能/注意力优化

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 148 | `ModelAttentionBackend` | — | attention=comfy kitchen attention | 标准参数 1 项见 standards.json |
| 192 | `MiniMaxH3MemoryEfficientSageAttentionPatch` | — | （无 widget，参数经连线输入） |  |
| 153 | `ModelPreviewOverrideKJ` | — | max_resolution=1024；jpeg_quality=80；suppress_default_preview=True；preview_frames=1；preview_fps=12；tiny_vae=taeh3.safetensors；preview= |  |

### ⑦ 输出/IO

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 122 | `VAEDecode` | — | （无 widget，参数经连线输入） |  |
| 121 | `VAEDecodeAudio` | — | （无 widget，参数经连线输入） |  |
| 180 | `VHS_VideoCombine` | — | frame_rate=24；loop_count=0；filename_prefix=minimaxh3；format=video/h264-mp4；pix_fmt=yuv420p；crf=12；save_metadata=True；trim_to_audio=False；pingpong=False；save_output=True；videopreview={'hidden': False, 'paused': False, 'params': {'fil | 标准参数 4 项见 standards.json |

### ⑧ 工具/条件/文本

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 231 | `Fast Groups Bypasser (rgthree)` | 音频 | （无 widget，参数经连线输入） |  |
| 249 | `SetNode` | Set_高 | Constant=高 |  |
| 248 | `SetNode` | Set_宽 | Constant=宽 |  |
| 238 | `SetNode` | Set_图像1 | Constant=图像1 |  |
| 239 | `SetNode` | Set_图像2 | Constant=图像2 |  |
| 240 | `SetNode` | Set_图像3 | Constant=图像3 |  |
| 241 | `SetNode` | Set_图像6 | Constant=图像6 |  |
| 242 | `SetNode` | Set_图像5 | Constant=图像5 |  |
| 243 | `SetNode` | Set_图像4 | Constant=图像4 |  |
| 246 | `SetNode` | Set_图像9 | Constant=图像9 |  |
| 245 | `SetNode` | Set_图像8 | Constant=图像8 |  |
| 244 | `SetNode` | Set_图像7 | Constant=图像7 |  |
| 229 | `SetNode` | Set_音频2 | Constant=音频2 |  |
| 230 | `SetNode` | Set_音频3 | Constant=音频3 |  |
| 228 | `SetNode` | Set_音频1 | Constant=音频1 |  |
| 235 | `SetNode` | Set_视频1 | Constant=视频1 |  |
| 236 | `SetNode` | Set_视频2 | Constant=视频2 |  |
| 237 | `SetNode` | Set_视频3 | Constant=视频3 |  |
| 262 | `GetNode` | Get_图像4 | Constant=图像4 |  |
| 258 | `GetNode` | Get_图像5 | Constant=图像5 |  |
| 257 | `GetNode` | Get_图像6 | Constant=图像6 |  |
| 256 | `GetNode` | Get_图像7 | Constant=图像7 |  |
| 261 | `GetNode` | Get_图像8 | Constant=图像8 |  |
| 260 | `GetNode` | Get_图像9 | Constant=图像9 |  |
| 259 | `GetNode` | Get_视频1 | Constant=视频1 |  |
| 267 | `GetNode` | Get_视频2 | Constant=视频2 |  |
| 266 | `GetNode` | Get_视频3 | Constant=视频3 |  |
| 254 | `GetNode` | Get_图像3 | Constant=图像3 |  |
| 255 | `GetNode` | Get_图像2 | Constant=图像2 |  |
| 252 | `GetNode` | Get_图像1 | Constant=图像1 |  |
| 265 | `GetNode` | Get_音频1 | Constant=音频1 |  |
| 264 | `GetNode` | Get_音频2 | Constant=音频2 |  |
| 263 | `GetNode` | Get_音频3 | Constant=音频3 |  |
| 272 | `GetNode` | Get_宽 | Constant=宽 |  |
| 273 | `GetNode` | Get_高 | Constant=高 |  |
| 131 | `ComfyMathExpression` | — | expression=max(5, round(a * 24)) + (5 - (max(5, round(a * 24) |  |
| 250 | `SetNode` | Set_时长 | Constant=时长 |  |
| 274 | `GetNode` | Get_时长 | Constant=时长 |  |
| 275 | `GetNode` | Get_提示词输入 | Constant=提示词输入 |  |
| 140 | `MarkdownNote` | Note: Size Settings Reference | text=| megapixels | Aspect | Output (multiple=32) | |-- |  |
| 173 | `ConditioningZeroOut` | — | （无 widget，参数经连线输入） |  |
| 285 | `TE_text_display` | — | text=873594099337389 |  |
| 253 | `SetNode` | Set_提示词输入 | Constant=提示词输入 |  |
| 286 | `Text Multiline` | — | text=subject_definitions  <Picture 1>：参考图1中的女人，约30–40岁， |  |
| 214 | `Text Multiline` | — | text=subject_definitions: <Subject 1> 是 <Picture 1> 中的红 |  |
| 132 | `PrimitiveFloat` | Float (Duration) | value=5 |  |
| 115 | `ResolutionSelector` | Resolution Selector (Size) | aspect_ratio=9:16 (Portrait Widescreen)；megapixels=1；multiple=32 | 标准参数 3 项见 standards.json |

---

## minimax_h3_video_motion_transfer_v1.0.0

> 用途：视频驱动动作迁移 / 人物替换（二采流） ｜ 节点数：83 ｜ 格式：UI (ComfyUI 界面可加载)

### ① 模型/编码器加载

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 584 | `VAELoader` | — | vae_name=H3\minimax_h3_audio_vae_fp32.safetensors | 标准参数 1 项见 standards.json |
| 216 | `LoraLoaderModelOnly` | 加速Lora | lora_name=H3\minimax_h3_turbo_v4_step600_ema_pruned_comfyui.；strength_model=1.0000000000000002 | 标准参数 2 项见 standards.json |
| 5455 | `LoadImage` | 参考图4 | image=Qwen_image_2.1_00015.png；upload=image | 标准参数 2 项见 standards.json |
| 5456 | `LoadImage` | 参考图5 | image=Qwen_image_2.1_00017.png；upload=image | 标准参数 2 项见 standards.json |
| 5454 | `LoadImage` | 参考图3 | image=Qwen_image_2.1_00050.png；upload=image | 标准参数 2 项见 standards.json |
| 264 | `LoadImage` | 参考图1 | image=Qwen_image_2.1_00012.png；upload=image | 标准参数 2 项见 standards.json |
| 581 | `UNETLoader` | — | unet_name=H3\DasiwaMinimaxH3_dasiwaHybridV2_int8.safetensors；weight_dtype=default | 标准参数 2 项见 standards.json |
| 582 | `CLIPLoader` | — | clip_name=H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors；type=minimax；device=default | 标准参数 3 项见 standards.json |
| 583 | `VAELoader` | — | vae_name=H3\minimax_h3_video_vae_int8_convrot.safetensors | 标准参数 1 项见 standards.json |
| 5435 | `LoraLoaderModelOnly` | 动作优化（一采） | lora_name=H3\H3_Combat_V2.safetensors；strength_model=1 | 标准参数 2 项见 standards.json |
| 5402 | `VHS_LoadVideo` | — | video=双人Loli参考视频.mp4；force_rate=24；custom_width=0；custom_height=0；frame_load_cap=0；skip_first_frames=0；select_every_nth=1；format=AnimateDiff；choose video to upload=None；videopreview={'hidden': False, 'paused': False, 'params': {'fil | 标准参数 3 项见 standards.json |
| 5424 | `LoadImage` | 参考图2 | image=Qwen_image_2.1_00009.png；upload=image | 标准参数 2 项见 standards.json |
| 5142 | `MiniMaxClipBinDualPicker` | — | project_name=2；mode=Strict Chaining (严格接续，空库报错)；clip_selection=clip_20261006_010319_457786_Shot1；custom_clip_path= |  |
| 5458 | `LoraLoaderModelOnly` | 动作优化（二采） | lora_name=H3\H3_Combat_V2.safetensors；strength_model=1 | 标准参数 2 项见 standards.json |

### ③ 调度/噪声

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 5141 | `MiniMaxH3ContextLatentTaperNoise` | — | tail_frames=22；alpha=0.45；alpha_end=0.1；ramp_steps=2；seed=879120741482747；control_after_generate=randomize；noise_scale=match_latent_std | 标准参数 7 项见 standards.json |
| 5149 | `MiniMaxH3ContextLatentTaperNoise` | — | tail_frames=22；alpha=0.45；alpha_end=0.1；ramp_steps=2；seed=555540423438918；control_after_generate=randomize；noise_scale=match_latent_std | 标准参数 7 项见 standards.json |
| 682 | `MiniMaxH3SigmaShift` | — | shift_video=12；shift_audio=3 | 标准参数 2 项见 standards.json |
| 5399 | `MiniMaxChunkFeedForward` | — | chunks=2；seq_threshold=4096 | 标准参数 2 项见 standards.json |

### ④ H3 生成主节点

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 5358 | `MiniMaxH3MotionContextClipStream` | — | context_length=22；audio_context_length=24；enable_audio_context=False | 标准参数 3 项见 standards.json |
| 5368 | `MiniMaxH3MotionContextClipStream` | — | context_length=22；audio_context_length=24；enable_audio_context=False | 标准参数 3 项见 standards.json |
| 261 | `MiniMaxH3ReferenceToVideo` | — | prompt=；width=1344；height=768；length=124；ref_image_size=max | 标准参数 5 项见 standards.json |

### ⑤ 放大/长视频

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 5401 | `H3 Long Video Manager` | — | fps=24；segment_duration=9；motion_context_frames=22；segment_id=2；scale_percent=60；align_to_h3_grid=True；project_name=loli换装双人；save_enabled=True；save_preview_mp4=True；final_align=up；person_crop=False；person_crop_expand_percent=0；save_dtype=int8 | 标准参数 13 项见 standards.json |
| 5395 | `H3 Segment Picker` | — | project_name=loli换装双人；segment_id=2 | 标准参数 2 项见 standards.json |
| 721 | `MMH3TemporalSplitParams` | — | chunk_length=153；temporal_overlap=17；anchor_strength=0.99 | 标准参数 3 项见 standards.json |

### ⑥ 性能/注意力优化

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 213 | `ModelAttentionBackend` | — | attention=comfy kitchen attention | 标准参数 1 项见 standards.json |
| 5398 | `MiniMaxLowVRAMAttention` | — | head_chunks=4 | 标准参数 1 项见 standards.json |
| 143 | `MiniMaxH3MemoryEfficientSageAttentionPatch` | — | （无 widget，参数经连线输入） |  |
| 418 | `ReservedVRAMSetter` | — | reserved=0.8；mode=manual；seed=317446889702894；control_after_generate=randomize；auto_max_reserved=0；clean_gpu_before=True | 标准参数 1 项见 standards.json |
| 567 | `ModelPreviewOverrideKJ` | 一采 | max_resolution=480；jpeg_quality=80；suppress_default_preview=True；preview_frames=999；preview_fps=12；tiny_vae=taeh3.safetensors；preview= |  |
| 5464 | `ModelPreviewOverrideKJ` | 二采 | max_resolution=1024；jpeg_quality=80；suppress_default_preview=True；preview_frames=1；preview_fps=12；tiny_vae=none；preview= |  |

### ⑦ 输出/IO

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 665 | `VHS_VideoCombine` | 一采 | frame_rate=24；loop_count=0；filename_prefix=视频驱动动作迁移/1采/；format=video/h264-mp4；pix_fmt=yuv420p；crf=19；save_metadata=False；trim_to_audio=False；pingpong=False；save_output=False；videopreview={'hidden': True, 'paused': False, 'params': {'file | 标准参数 4 项见 standards.json |
| 667 | `VHS_VideoCombine` | 二采 | frame_rate=24；loop_count=0；filename_prefix=视频驱动动作迁移/2采/；format=video/h264-mp4；pix_fmt=yuv420p；crf=19；save_metadata=False；trim_to_audio=False；pingpong=False；save_output=True；videopreview={'hidden': True, 'paused': False, 'params': {'file | 标准参数 4 项见 standards.json |
| 5143 | `MiniMaxClipBinDualSaver` | — | project_name=Default_Project；shot_tag=Auto (自动编号)；prompt=；parent_clip_id=；save_video=False | 标准参数 5 项见 standards.json |
| 426 | `easy showAnything` | — | text=[     false,     [         "D:\\AIUI\\ComfyUI-aki- |  |
| 5408 | `easy showAnything` | 分段数 | text=3 |  |

### ⑧ 工具/条件/文本

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 5139 | `easy boolean` | 一采手动强制关闭加噪 (True=始终跳过) | value=True |  |
| 5409 | `easy clearCacheAll` | — | （无 widget，参数经连线输入） |  |
| 427 | `easy cleanGpuUsed` | — | （无 widget，参数经连线输入） |  |
| 428 | `easy clearCacheAll` | — | （无 widget，参数经连线输入） |  |
| 227 | `SetNode` | Set_clip | Constant=clip |  |
| 228 | `SetNode` | Set_video vae | Constant=video vae |  |
| 229 | `SetNode` | Set_audio vae | Constant=audio vae |  |
| 243 | `SetNode` | Set_视频宽度 | Constant=视频宽度 |  |
| 244 | `SetNode` | Set_视频高度 | Constant=视频高度 |  |
| 411 | `SetNode` | Set_放大倍率 | Constant=放大倍率 |  |
| 5355 | `SetNode` | Set_一采步数 | Constant=一采步数 |  |
| 386 | `Reroute` | — | （无 widget，参数经连线输入） |  |
| 256 | `SetNode` | Set_提示词 | Constant=提示词 |  |
| 673 | `Note` | H3 Context Taper Noise 设置 | text=参数	默认	说明 context_latent	—	上一镜的 AV latent，直接来自 H3 M |  |
| 738 | `MarkdownNote` | — | text=  ### 显存参考（起始建议）  | 显存 | 建议 tile 大小 | 建议 chunk_len |  |
| 239 | `GetNode` | Get_clip | Constant=clip |  |
| 259 | `GetNode` | Get_提示词 | Constant=提示词 |  |
| 240 | `GetNode` | Get_video vae | Constant=video vae |  |
| 248 | `GetNode` | Get_视频宽度 | Constant=视频宽度 |  |
| 5356 | `GetNode` | Get_一采步数 | Constant=一采步数 |  |
| 241 | `GetNode` | Get_audio vae | Constant=audio vae |  |
| 249 | `GetNode` | Get_视频高度 | Constant=视频高度 |  |
| 5418 | `MarkdownNote` | 标题 | text= # 视频驱动动作迁移/人物替换工作流v1 # 作者：b站——阿喵喵Az # B站主页：https: |  |
| 5421 | `CR Text Concatenate` | — | separator= |  |
| 668 | `VRGDG_VideoCompareSlider` | — | slider_position=0.74；before_label=一采；after_label=二采；show_labels=True；loop=True；muted=False |  |
| 5438 | `PrimitiveStringMultiline` | 提示词 | value=subject_definitions  <Subject 1> is the target cha |  |
| 5357 | `FloatConstant` | — | value=0.999 |  |
| 5396 | `MarkdownNote` | 复制到任意AI | text=```markdown # 视频角色替换提示词生成模板  你是一个视频提示词格式化工具。你的唯一任务 |  |
| 5148 | `easy boolean` | 二采手动强制关闭加噪 (True=始终跳过) | value=True |  |
| 140 | `MarkdownNote` | Note: Size Settings Reference | text=| megapixels | Aspect | Output (multiple=32) | |-- |  |
| 5414 | `Note` | — | text=Load Video的force rate一定是24. H3 Long Video Manager的 |  |
| 5423 | `Text Multiline` | — | text= |  |
| 5354 | `INTConstant` | 一采步数（建议4-8） | value=8 |  |
| 115 | `ResolutionSelector` | 分辨率选择器（像素） | aspect_ratio=3:4 (Portrait Standard)；megapixels=0.6；multiple=32 | 标准参数 3 项见 standards.json |
| 335 | `PrimitiveFloat` | 二采放大倍率 | value=1.5 |  |
| 5403 | `Fast Groups Bypasser (rgthree)` | 切换工作 | （无 widget，参数经连线输入） |  |
| 5400 | `MarkdownNote` | 低显存可开设置 | text=# MiniMax H3 KJNodes 显存优化节点配置表   | 显存容量 | head_chu |  |
| 222 | `SetNode` | Set_model | Constant=model |  |
| 5460 | `SetNode` | Set_model2 | Constant=model2 |  |
| 235 | `GetNode` | Get_model | Constant=model |  |
| 5461 | `GetNode` | Get_model2 | Constant=model2 |  |
| 5420 | `Seed (rgthree)` | — | seed=-1；🎲 Randomize Each Time=；🎲 New Fixed Random=；USE_LAST_SEED=okay |  |
| 138 | `PrimitiveStringMultiline` | 提示词 | value=subject_definitions: <Subject 1> is the silver-pur |  |

### ⑨ UUID 占位（待源环境确认）

| 节点ID | 类型 | 标题 | 关键参数（真实值） | 标准/备注 |
|------|------|------|----------------|---------|
| 5140 | `1e83e52d-c4d4-4071-be6f-2ad81c64b715` | — | boolean=True | 布尔任意开关（yolain/ComfyUI-Easy-Use 的 If else）；输入 boolean/on_true*/on_false* → 输出 *【已定位包】 |
| 5367 | `b38cb4d8-b7ff-4df4-990e-876cf5cb5857` | — | noise_seed=873375719539214；steps=8；sampler_name=0；scheduler=er_sde；denoise=simple | 【未解析·关键】双 VAE(视频+音频)的 H3 二采采样+解码节点：输入 model/conditioning/latent_image(一采 latent)/steps/vae(视频)/vae_1(音频)/trim_frames(来自 MotionContextClipStream)/sampler_name(er |
| 5380 | `d9bc6b7f-16bd-40f7-8c53-729f89091fea` | — | noise_seed=13796200085181；model_name=0；device=minimax_h3_latent_upscaler_3d_fp16.safetensors；precision=cuda；sampler_name=fp16 | 3D latent 放大+双 VAE 解码（LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler 的 MinimaxH3LatentUpscaler3D）【已定位包】 |
| 5150 | `7a522690-eadb-45bc-b4b8-4fbf5b09e1a0` | — | boolean=True | 布尔任意开关（yolain/ComfyUI-Easy-Use 的 If else）；输入 boolean/on_true*/on_false* → 输出 *【已定位包】 |
| 5352 | `7c0dfa74-7583-4d61-98d6-cae724dc6517` | — | （无 widget，参数经连线输入） | 【未解析·关键】无输入、输出 4 路 SIGMAS(SIGMAS/SIGMAS_1/SIGMAS_2/SIGMAS_3) 的调度生成器；本工作流仅 SIGMAS_2 经 Reroute#386 接入下游（二采采样 sigma 调度）。功能=为二采多阶段采样预生成 4 条 sigma 调度、择一使用。候选：二采/多阶段  |

---