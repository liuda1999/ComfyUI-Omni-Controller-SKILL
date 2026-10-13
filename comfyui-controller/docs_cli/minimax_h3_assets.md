# MiniMax H3 工作流资产说明

> 本项目新增的 6 个 MiniMax H3 音视频生成工作流资产，及其节点/模型依赖说明。
> 配合 [third_party_nodes.md](third_party_nodes.md)（节点→GitHub 包索引）、[minimax_h3_workflow_params.md](minimax_h3_workflow_params.md)（逐节点参数说明书）与 `assets/node_registry.json`、`assets/node_parameter_standards.json` 使用。

> ⚠️ **运行前提**：当前项目环境**不支持运行** H3 视频生成（需 NVIDIA 大显存 + ComfyUI 0.30.0+ + 上述节点包与数十 GB 权重）。
> 本目录资产用于**检查、分析与交付**，实际运行请在另行准备的测试环境进行。

***

## 1. 资产清单（6 个工作流）

| 资产文件（UI 格式） | API 副本 | 节点数 | 用途 |
|--------------------|---------|-------|------|
| `minimax_h3_t2v_turbo_v1.0.0.json` | `minimax_h3_t2v_turbo_v1.0.0_api.json` | 21 | 文生视频（T2V）· FL2V Turbo 4 步快速版 |
| `minimax_h3_fl2va_first_last_frame_v1.0.0.json` | `minimax_h3_fl2va_first_last_frame_v1.0.0_api.json` | 35 | 首/尾帧参考生视频（FL2VA）· 开源版 |
| `minimax_h3_ref2v_av_turbo_v1.0.0.json` | `minimax_h3_ref2v_av_turbo_v1.0.0_api.json` | 62 | 多参图像+音频极速生视频（Ref2VA） |
| `minimax_h3_ref2v_multi_reference_v1.0.0.json` | `minimax_h3_ref2v_multi_reference_v1.0.0_api.json` | 119 | 多参考生视频优化版（含 latent 3D 放大二采） |
| `minimax_h3_all_in_one_v1.0.0.json` | `minimax_h3_all_in_one_v1.0.0_api.json` | 79 | 综合全能版（社区整合流，含微调基模与放大） |
| `minimax_h3_video_motion_transfer_v1.0.0.json` | `minimax_h3_video_motion_transfer_v1.0.0_api.json` | 83 | 视频驱动动作迁移 / 人物替换（二采流） |

**原始文件名对照**（便于溯源）：

| 落位文件名 | 原始文件名 |
|-----------|-----------|
| `minimax_h3_t2v_turbo_v1.0.0.json` | `minimax_h3_t2v_turbo-快速文生视频.json` |
| `minimax_h3_fl2va_first_last_frame_v1.0.0.json` | `MiniMax+H3+FL2VA开源版-首尾帧参考生视频.json` |
| `minimax_h3_ref2v_av_turbo_v1.0.0.json` | `MiniMax+H3｜多参图像音频极速生视频.json` |
| `minimax_h3_ref2v_multi_reference_v1.0.0.json` | `MiniMax+H3-多参考生视频-优化版.json` |
| `minimax_h3_all_in_one_v1.0.0.json` | `Minimax H3群分享无敌流.json` |
| `minimax_h3_video_motion_transfer_v1.0.0.json` | `Minimax H3视频驱动动作迁移_人物替换工作流v1（二采流）.json` |

> **格式说明**：
> - **UI 格式**（无 `_api` 后缀）：ComfyUI 界面可直接 `Load` 加载、可视化编辑与运行。
> - **API 格式**（`_api` 后缀）：供 `scripts/run_workflow.py` 或 CLI `comfy run` 脚本化执行。
>   ⚠️ **重要**：API 副本由本机降级模式转换（本机缺 H3 与第三方节点 schema），
>   **节点间连接结构正确，但各节点的 widget 参数未完整映射**。
>   请在装齐节点包的测试环境中，用 `scripts/workflow_converter.py` 重新转换以获得完整参数：
>   ```bash
>   python scripts/workflow_converter.py --input minimax_h3_xxx_v1.0.0.json --output xxx_api.json --host 127.0.0.1 --port 8188
>   ```

***

## 2. 模型清单

| 类别 | 文件名 | 来源 | 放置路径 |
|------|--------|------|---------|
| 官方扩散模型（DiT） | minimax_h3_fl2va_* / minimax_h3_ref2va_*（bf16 / int8_convrot / pruned_int8 / pruned_fp8 / nvfp4 等） | Comfy-Org/MiniMax-H3（HuggingFace）/ MiniMaxAI/MiniMax-H3（原始）/ ModelScope 镜像 | `models/diffusion_models/` |
| 官方文本编码器 | qwen3vl_32b_minimax_h3_*（bf16 / int8_convrot / nvfp4_awq） | Comfy-Org/MiniMax-H3 | `models/text_encoders/` |
| 官方视频 VAE | minimax_h3_video_vae_*（fp16 / int8_convrot） | Comfy-Org/MiniMax-H3 | `models/vae/` |
| 官方音频 VAE | minimax_h3_audio_vae_fp32 | Comfy-Org/MiniMax-H3（须 fp32） | `models/vae/` |
| Turbo LoRA（加速） | minimax_h3_turbo_* / minimax_h3_ref2v_turbo_8step_* / minimax_h3_fl2v_turbo_4step_* | larryvrh/MiniMax-H3-Turbo-Lora ｜ lightx2v/Minimax-h3-Turbo | `models/loras/` |
| latent 3D 放大器 | minimax_h3_latent_upscaler_3d_fp16.safetensors | LBH-123-AI/Minimax_h3_latent_Upscaler | `models/latent_upscale_models/` |
| TAE 实时预览 | taeh3.safetensors | Kijai/MiniMax-H3-TAE（vae_approx） | `models/vae_approx/` |
| 社区微调基模 ⚠️待确认 | MysticXXX_MMH3-V1 / H3_Combat_V2 / DasiwaMinimaxH3_dasiwaHybridV2_int8 / minimax_h3_hybrid_fl2va_ref2va_b25-49-int8 / wushu_spatial_physics_v2_1000_pruned | **来源待确认**（疑为社区/Civitai/网盘分享，非官方渠道） | `models/diffusion_models/（部分工作流放在 H3/ 子目录）` |

**官方下载**（推荐 Comfy-Org 预量化版，体积/显存友好）：

```bash
# HuggingFace
hf download Comfy-Org/MiniMax-H3 --local-dir ./models/MiniMax-H3
# 或 ModelScope（国内更快）
# https://modelscope.cn/models/Comfy-Org/MiniMax-H3
```

> 模型按用途区分：**FL2VA**（文生视频/首尾帧）与 **Ref2VA**（多模态参考）是两个不同权重，
> 请按工作流对应的任务类型选择。同一模型在不同工作流中命名不完全一致（官方名 / RH 包名 / 社区名），
> 加载时以工作流内 `UNETLoader`/`CLIPLoader`/`VAELoader` 的实际取值为准。

***

## 3. 使用步骤

1. **装节点包**：按 [third_party_nodes.md](third_party_nodes.md) 第 1 节执行（24 个包，含 23 个第三方）。
2. **装模型**：按上表放置权重到对应 `models/` 子目录。
3. **加载工作流**：ComfyUI 界面 `Load` 对应 UI 格式 JSON，或脚本执行 API 格式副本。
4. **按需重转 API**：如需脚本化执行，先在装齐节点的环境重转（见上）。
5. **查看参数标准**：每个节点的真实参数值与类型标准见 [minimax_h3_workflow_params.md](minimax_h3_workflow_params.md)（逐节点表）与 `assets/node_parameter_standards.json`（59 个关键节点类型的参数定义：类型/默认/取值范围/含义/来源包）。

***

## 4. 待确认项

- **社区微调基模**（MysticXXX_MMH3-V1、H3_Combat_V2、DasiwaMinimaxH3 等）：来源非官方渠道，需补充出处。
- **2 项 UUID 占位节点来源待确认**（见 [third_party_nodes.md](third_party_nodes.md) 第 5 节）：
  - `b38cb4d8-…`：双 VAE(视频+音频)的 H3 采样器，输入 model/conditioning/latent_image/steps/vae/vae_1/trim_frames/sampler_name(er_sde)/scheduler/denoise，输出 LATENT/IMAGE/images/audio。
  - `7c0dfa74-…`：无输入、输出 4 路 SIGMAS(SIGMAS/SIGMAS_1/SIGMAS_2/SIGMAS_3) 的调度/分段生成器。
  - 二者均因导出环境缺节点包被 ComfyUI 替换为 UUID，已排除 ClipStream/IAMCCS/RunningHub/Motion-Context/Motion-Director/Easy-Use/LBH-123-AI/KJNodes/Viggle/ethanfel/RES4LYF 等包；疑似某 H3 自定义采样/二采流专用包。**需源环境确认真实 class_type 后方可加载**。
- **受影响的资产**：`minimax_h3_video_motion_transfer_v1.0.0.json`（视频驱动动作迁移/人物替换·二采流）是唯一含未解析 UUID 节点的工作流，补齐上述 2 个源节点包后方可『加载即用』；其余 5 个工作流已全部解析、可直接加载运行。
- **工作流中的 `H3\` 前缀**：为原作者的本地子目录写法（模型放在 `models/diffusion_models/H3/`），移植时需按实际放置调整。

