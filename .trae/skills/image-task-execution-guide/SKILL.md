---
name: "image-task-execution-guide"
description: "图片生成任务执行前的强制检查与反问指南。当用户请求生成图片（文生图/图生图等）时必须调用，引导完成5项预检含强制反问环节：服务可用性/模型选择/节点完整性/硬件与参数反问/提示词校验。"
---

# 图片任务执行前检查指南

## 0. 智能体快速导航（AI Agent Quick Nav）

> **如果你是 AI 智能体，首次读取本文件时，按以下路径快速了解。不要从头到尾通读。**

### 0.1 核心流程速览

| 步骤 | 内容 | 跳转 |
|------|------|------|
| **预检** | 5项强制检查（服务/模型/节点/硬件反问/提示词） | [→ 检查1-5](#5项强制检查) |
| **架构选择** | Flux2 / Flux1 / SD1.5 / SDXL 按模型系列 | [→ 检查2 模型选择](#检查2-模型选择按系列分组禁止跨系列混用) |
| **参数反问** | 比例 + 分辨率 + 步数（三问不可跳过） | [→ 检查4.2 强制反问](#步骤42-强制反问参数禁止跳过) |
| **排错** | 维度不匹配/模型混用/节点缺失 | [→ Flux2架构经验](#flux-2-f2k-9b-kleinova-架构经验) + [SKILL.md 第8节](../../comfyui-controller/SKILL.md) |

### 0.2 场景化入口

**你要用 Flux2 生成图片？** → [Flux2 架构经验](#flux-2-f2k-9b-kleinova-架构经验) + [检查2](#检查2-模型选择按系列分组禁止跨系列混用)

**你要用 SD1.5/SDXL 生成图片？** → [检查2 系列映射表](#检查2-模型选择按系列分组禁止跨系列混用) + [检查3 节点清单](#检查3-节点完整性)

**你要为图片选用 LoRA？** → [LoRA 选择策略](#lora-选择策略图片生成专用) 类型分类 + 决策表

**你要排查图片质量问题？** → [Flux2 vs Flux1 架构对比](#flux-1-vs-flux-2-架构对比) + [EXPERIENCE.md 第13章](../../comfyui-controller/docs_cli/EXPERIENCE.md)

---

## 适用场景

- 用户请求文生图（text-to-image）
- 用户请求图生图（image-to-image）
- 用户请求图片放大/重绘
- 任何涉及扩散模型的静态图片生成任务

## 核心教训（2026-07-10）

**严重错误案例**: 收到用户的图片生成提示词后，未进行任何反问，直接使用默认参数（1024×1024、steps=25）执行生成。违反了"预检反问环节不可跳过"的硬约束。

**正确做法**: 必须先与用户确认画面比例、分辨率、优化程度，再执行生成。即使用户提供了完整提示词，也不能跳过反问环节。

**步数默认值更新**（C8 任务经验总结）：
- 早期默认 `steps=25` 偏高，实际 20-25 步已足够（原生模型）
- 有加速 LoRA 时默认 `steps=6-8` 即可
- 反问模板中 `{rec_steps}` 应根据模型类型动态计算，不可固定为 25

---

## 5项强制检查

### 检查1: ComfyUI 服务可用性

**执行方式**: 向 ComfyUI 发送 HTTP GET 请求
- 端口连通检查: `GET http://127.0.0.1:${COMFYUI_PORT}/system_stats`
- API 响应检查: `GET http://127.0.0.1:${COMFYUI_PORT}/object_info`

**通过标准**: 两个请求均返回 HTTP 200 且 JSON 可解析

**失败处理**: 终止任务，提示"ComfyUI 服务不可用，请确认服务已启动（端口 ${COMFYUI_PORT}）"

---

### 检查2: 模型选择（按系列分组，禁止跨系列混用）

**执行方式**: `GET http://127.0.0.1:${COMFYUI_PORT}/object_info` 查询以下节点获取可用模型列表
- `UNETLoader` → diffusion_models（按系列分组展示）
- `VAELoader` → vae
- `CLIPLoader` → clip / text_encoders

**通过标准**:
- 所需模型文件均出现在可用列表中
- 所有组件属于同一模型系列（禁止跨系列混用）

**系列关键词映射**:
| 系列 | 扩散模型关键词 | VAE 关键词 | CLIP 关键词 | 加载节点 | type 参数 |
|------|--------------|-----------|------------|---------|----------|
| Flux 2 | F2K, flux-2, klein | flux2 | qwen3 | CLIPLoader | `flux2` |
| Flux 1 | flux-dev, flux-schnell | ae, flux | clip_l + t5xxl | DualCLIPLoader | `flux` |
| SD1.5 | v1-5, sd1 | vae-ft, sd | clip-vit | CLIPLoader | `stable_diffusion` |
| SDXL | sdxl | sdxl-vae | clip_g + clip_l | DualCLIPLoader | `sdxl` |

**失败处理**: 终止任务，列出缺失的模型文件名，提示用户下载

**重要**: 必须向用户展示可用模型列表并让其选择，不能自动假设使用哪个模型。

---

### 检查3: 节点完整性

**执行方式**: `GET http://127.0.0.1:${COMFYUI_PORT}/object_info/{node_name}` 逐一查询

**必需节点清单（按模型系列）**:

| 模型系列 | 必需节点 |
|---------|---------|
| Flux 2 | UNETLoader, CLIPLoader, VAELoader, CLIPTextEncode, EmptyFlux2LatentImage, RandomNoise, KSamplerSelect, Flux2Scheduler, CFGGuider, SamplerCustomAdvanced, VAEDecode, SaveImage |
| Flux 1 | UNETLoader, DualCLIPLoader, VAELoader, CLIPTextEncodeFlux, EmptyLatentImage, ModelSamplingFlux, KSampler, VAEDecode, SaveImage |
| SD1.5/SDXL | CheckpointLoaderSimple, VAELoader, CLIPTextEncode, EmptyLatentImage, KSampler, VAEDecode, SaveImage |

**通过标准**: 所选系列的所有必需节点在 /object_info 响应中存在

**失败处理**: 终止任务，列出缺失节点，提示安装对应的 ComfyUI 插件包

---

### 检查4: 硬件检测与强制反问参数收集（核心！不可跳过！）

**这是本次检查的重中之重。** 即使用户提供了完整提示词，也必须完成以下反问环节。

#### 步骤4.1: 硬件检测

**执行方式**:
1. GPU VRAM 查询: `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits`
2. 系统内存查询: `wmic ComputerSystem get TotalPhysicalMemory`

**通过标准**:
- VRAM ≥ 6144 MB（6GB，图片生成最低要求）
- 系统内存 ≥ 8192 MB（8GB）

**失败处理**: VRAM < 6GB 时终止任务

#### 步骤4.2: 强制反问参数（禁止跳过！）

必须依次向用户询问以下三项参数，展示基于硬件的推荐值，用户可确认或覆盖：

**反问1: 画面比例**
```
请选择画面比例:
  1. 1:1 方形（适合肖像、居中构图）
  2. 3:4 竖屏（适合人像摄影）
  3. 4:3 横屏（适合风景、场景）
  4. 9:16 竖屏（适合手机壁纸）
  5. 16:9 横屏（适合桌面壁纸）
请输入 (1/2/3/4/5):
```

**反问2: 分辨率**
```
请选择分辨率（基于 {vram_gb}GB VRAM，推荐 {recommended_res}）:
  1. 512×512 基础（低显存）
  2. 768×768 标准（{推荐中端}）
  3. 1024×1024 高清（{推荐高端}）
  4. 1536×1536 超清（需 ≥16GB VRAM）
请输入 (1/2/3/4):
```

分辨率推荐档次（基于 VRAM，质量优先）:
| VRAM 范围 | 推荐分辨率 | 最大允许分辨率 |
|----------|-----------|--------------|
| ≥24GB | 1536×1536 | 2048×2048 |
| 12-24GB | 1024×1024 | 1536×1536 |
| 6-12GB | 768×768 | 1024×1024 |

**反问3: 优化程度（steps 步数）**
```
请选择优化程度（基于 {vram_gb}GB VRAM，推荐 {rec_steps} 步）:
  1. 快速预览（{max(6, rec_steps-4)} 步，约15-30秒）
  2. 标准质量（{rec_steps} 步，约1-2分钟）← 推荐
  3. 高质量（{rec_steps+5} 步，约2-3分钟）
  4. 极致质量（{rec_steps+10} 步，约3-5分钟）
请输入 (1/2/3/4):
```

> **步数区间说明**：
> - `{rec_steps}` 默认值基于模型类型动态计算：有加速 LoRA 时取 8，原生 SD1.5 取 18，原生 Flux2/SDXL 取 22
> - 快速预览下限不低于 6 步（避免质量崩溃）
> - 极致质量上限不超过 35 步（收益递减）

steps 推荐档次（基于 VRAM 与模型类型，质量优先）:

| VRAM 范围 | 蒸馏/加速 LoRA | 原生模型（无 LoRA） | 模型类型 |
|----------|---------------|-------------------|---------|
| ≥24GB | 8-12 | 20-25 | Flux 2 / SDXL |
| 12-24GB | 6-10 | 18-22 | Flux 2 / SDXL |
| 6-12GB | 6-8 | 15-20 | SD1.5 / Flux 1 |

> **步数选择原则**（C8 任务经验总结）：
> - **有加速 LoRA**（如 lightx2v/蒸馏 LoRA）：6-8 步即可达到原生 20-30 步质量
> - **无加速 LoRA**：SD1.5 原生 15-20 步，Flux2/SDXL 原生 20-25 步
> - **超过 30 步收益递减**，不建议单纯堆步数
> - **低于 6 步画面严重模糊**（Wan2.2 特性；图片模型类似，无 LoRA 时低于 12 步质量崩溃）

**重要**:
- 上述三项反问必须全部完成，不能使用默认值直接执行
- 用户如果只说"用默认"或"你决定"，可以采用推荐值但仍需展示所选参数让用户确认
- 反问完成后，向用户汇总最终参数（比例+分辨率+步数+模型），等待最终确认后再执行

#### 步骤4.3: 参数汇总确认

```
=== 最终参数确认 ===
模型: {model_name} ({family}系列)
画面比例: {ratio}
分辨率: {width}×{height}
优化步数: {steps} 步
采样器: {sampler}
CFG: {cfg}
==================
确认执行? (y/n):
```

**通过标准**: 用户确认 `y`

**失败处理**: 用户输入 `n` 则返回步骤4.2 重新收集

---

### 检查5: 提示词结构化校验

**执行方式**: 检查正面提示词是否包含必要元素

**图片提示词结构要求**:
1. **主体描述**: 人物/物体的外观、姿态、表情
2. **镜头语言**: 焦距、光圈、视角、构图
3. **场景描述**: 环境、光线、氛围
4. **画质修饰**: 分辨率、风格、细节要求

**负面提示词标准模板**:
```
deformed, distorted, disfigured, bad anatomy, extra limbs, missing limbs,
mutated hands, disconnected limbs, blurry, low quality, worst quality,
jpeg artifacts, watermark, signature, text, oversaturated, overexposed,
poor lighting, unnatural colors, artificial looking, plastic skin, cgi, 3d render, cartoon
```

**通过标准**:
- 正面提示词包含主体描述
- 正面提示词包含场景或镜头描述
- 负面提示词包含基本负面项

**失败处理**: 警告并建议补充缺失元素，或自动将用户白话转换为结构化提示词

---

## 检查流程总结

```
用户请求图片生成
    ↓
检查1: ComfyUI 服务可用?  ──否──→ 终止，提示启动服务
    ↓ 是
检查2: 模型可用且同系列?  ──否──→ 终止，列出缺失模型
    ↓ 是（展示模型列表让用户选择）
检查3: 节点完整?          ──否──→ 终止，列出缺失节点
    ↓ 是
检查4: 硬件达标            ──否──→ 终止，提示显存不足
    ↓ 是
检查4.2: 强制反问（比例+分辨率+步数）  ← 不可跳过！
    ↓
检查4.3: 参数汇总确认      ──n──→ 返回重新收集
    ↓ y
检查5: 提示词结构化?      ──否──→ 警告并自动转换
    ↓ 是
全部通过 → 执行图片生成任务
```

---

## Flux 2 (F2K-9b-kleinova) 架构经验

### 核心教训：Flux 1 与 Flux 2 架构完全不同，禁止混用！

**错误案例**: 使用 Flux 1 的 DualCLIPLoader(clip_l + t5xxl) 加载 Flux 2 模型，导致 `mat1 and mat2 shapes cannot be multiplied (512x4096 and 12288x4096)` 错误。

**根因**: F2K-9b-kleinova 的 `txt_in` 层期望 **12288 维**输入（Qwen3-8B 取第 9/18/27 层拼接 = 3×4096），而 T5XXL 只输出 4096 维。

### Flux 2 完整节点链（基于官方蓝图验证 2026-07-10）

| 序号 | 节点 | 关键参数 | 说明 |
|------|------|---------|------|
| 1 | UNETLoader | unet_name=F2K-9b, weight_dtype=default | 加载 Flux 2 模型 |
| 2 | CLIPLoader | clip_name=qwen_3_8b, **type=flux2**, device=default | Qwen3-8B 编码器（12288维） |
| 3 | VAELoader | vae_name=flux2-vae | Flux 2 专用 VAE |
| 4 | CLIPTextEncode | clip=[2], text=正面提示词 | **标准 CLIPTextEncode**（非 CLIPTextEncodeFlux） |
| 5 | CLIPTextEncode | clip=[2], text=负面提示词 | 负面提示词 |
| 6 | EmptyFlux2LatentImage | width, height, batch_size | Flux 2 潜空间 |
| 7 | RandomNoise | noise_seed=seed | 随机噪声 |
| 8 | KSamplerSelect | sampler_name=euler | 采样器选择 |
| 9 | Flux2Scheduler | steps, width, height | **Flux 2 专用调度器**（非 ModelSamplingFlux） |
| 10 | CFGGuider | model=[1], positive=[4], negative=[5], cfg=5.0 | CFG 引导器 |
| 11 | SamplerCustomAdvanced | noise=[7], guider=[10], sampler=[8], sigmas=[9], latent=[6] | 高级采样器 |
| 12 | VAEDecode | samples=[11], vae=[3] | VAE 解码 |
| 13 | SaveImage | images=[12] | 保存图片 |

### Flux 1 vs Flux 2 架构对比

| 组件 | Flux 1（错误） | Flux 2（正确） |
|------|--------------|--------------|
| CLIP 加载 | DualCLIPLoader(clip_l + t5xxl, type=flux) | **CLIPLoader**(qwen3_8b, **type=flux2**) |
| 文本编码维度 | 4096 维 | **12288 维**（3×4096 层拼接） |
| 提示词节点 | CLIPTextEncodeFlux(clip_l + t5xxl + guidance) | **CLIPTextEncode**(单文本) |
| 采样器 | KSampler + ModelSamplingFlux | **SamplerCustomAdvanced** + CFGGuider + KSamplerSelect + Flux2Scheduler |
| CFG | 1.0（guidance 通过 CLIPTextEncodeFlux 控制） | **5.0** |
| 潜空间 | EmptyLatentImage | **EmptyFlux2LatentImage** |
| LoRA 兼容 | Flux 1 LoRA 可用 | **Flux 1 LoRA 不兼容**（维度不匹配） |

### Flux 2 模型文件对应关系

| 模型规模 | 扩散模型 | 文本编码器 | 维度 | VAE |
|---------|---------|----------|------|-----|
| Flux 2 Klein 4B | flux-2-klein-base-4b-fp8.safetensors | qwen_3_4b.safetensors | 7680 (3×2560) | flux2-vae |
| Flux 2 Klein 9B | F2K-9b-kleinova_10FP8.safetensors | **qwen_3_8b_fp8mixed.safetensors** | **12288 (3×4096)** | flux2-vae |

**重要**: 选错 Qwen3 规模会导致同样的维度不匹配错误。4B 模型用 qwen3_4b，9B 模型用 qwen3_8b。

### 实测性能基准（RTX 3080 20GB VRAM）

| 配置 | 分辨率 | 步数 | 单图耗时 |
|------|--------|------|---------|
| F2K-9b-kleinova FP8（原生） | 1024×1024 | 20-25 | 约60-75秒 |
| F2K-9b-kleinova FP8（原生，高质量） | 1024×1024 | 28 | 约90秒 |

> **步数建议**：Flux2 原生模型 20-25 步已达质量上限，28 步以上收益递减。若有 Flux2 专用加速 LoRA，可降至 8-12 步。

---

### LoRA 选择策略（图片生成专用）

**重要**：图片生成也应选用 LoRA，不可跳过。LoRA 类型多样，需根据任务需求甄别挑选。

#### 图片 LoRA 类型分类

| 类型 | 用途 | 适用模型系列 | 是否可叠加 |
|------|------|------------|-----------|
| 画质增强 | 提升细节、质感、纹理 | Flux2/Flux1/SD1.5/SDXL | 可与其他类型叠加 |
| 风格迁移 | 动漫/写实/油画/水彩等风格 | SD1.5/SDXL/Flux1 | 通常不可叠加多个风格LoRA |
| 色调控制 | 调整画面色调、色温 | Flux2/Flux1 | 可叠加（注意强度） |
| 皮肤增强 | 提升人物皮肤质感 | Flux2 | 可叠加（注意强度，过高过度平滑） |
| 细节增强 | 提升纹理锐度、花纹清晰度 | Flux2 | 可叠加 |
| 角色一致性 | 锁定特定角色外观 | SD1.5/SDXL | 通常单独使用 |

#### Flux2 LoRA 使用决策

**Flux2 修正工作流常用 LoRA（v12 验证）**：

| LoRA | 作用 | 推荐strength | 使用场景 |
|------|------|------------|---------|
| ColorTone | 色调修正 | 0.2-0.4 | 画面偏色时调整色调 |
| Skin | 皮肤质感 | 0.6 | 人物皮肤模糊时增强（>0.7会过度平滑） |
| Detail | 细节增强 | 1.0 | 恢复被压缩的纹理和细节 |

**使用原则**：
- 通过 `/object_info/LoraLoaderModelOnly` 或 `/object_info/LoraLoader` 查询可用 LoRA
- Flux1 LoRA **不可**用于 Flux2 模型（维度不匹配）
- LoRA 文件名含 `480p`/`720p` 表示分辨率适配，需与生成分辨率匹配

#### SD1.5/SDXL LoRA 使用决策

| 场景 | 推荐LoRA类型 | 典型strength | 注意事项 |
|------|------------|-------------|---------|
| 写实人像 | 画质增强 + 皮肤增强 | 0.5-0.8 | 叠加时总强度不超过1.2 |
| 动漫风格 | 风格迁移 | 0.7-1.0 | 通常单独使用 |
| 特定角色 | 角色一致性 | 0.8-1.0 | 可能影响背景构图 |

---

## 参数与架构参考

- **技术文档**: `${PROJECT_PATH}/comfyui-controller/docs_cli/EXPERIENCE.md`
  - 图片生成任务相关经验（Flux2 架构、参数梯度、排错流程）
- **预检模块**: `${PROJECT_PATH}/comfyui-controller/scripts/pre_task_inquiry.py`
  - `get_adaptive_params(vram_mb)` — 硬件自适应参数推荐（视频用，图片可参考）
- **官方蓝图**: `${COMFYUI_PATH}/blueprints/Image Edit (Flux.2 Klein 4B).json`
