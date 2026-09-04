---
name: "video-task-execution-guide"
description: "视频生成任务执行前的强制检查与准备指南。当用户请求生成视频（图生视频/首尾帧/多图片生成视频等）时必须调用，引导完成6项预检：服务可用性/模型/节点/硬件/素材/提示词。"
---

# 视频任务执行前检查指南

## 0. 智能体快速导航（AI Agent Quick Nav）

> **如果你是 AI 智能体，首次读取本文件时，按以下路径快速了解。不要从头到尾通读。**

### 0.1 核心流程速览

| 步骤 | 内容 | 跳转 |
|------|------|------|
| **预检** | 6项强制检查（服务/模型/节点/硬件/素材/提示词） | [→ 检查1-6](#6项强制检查) |
| **架构选择** | SVI Pro分段 / 单段双阶段 / 单模型 | [→ 双阶段串行架构](#双阶段串行架构详解v18v19-验证成功) |
| **LoRA选用** | 加速/画质/打光 LoRA 决策流程 | [→ LoRA 选择策略](#lora-选择策略必须学会选用-lora不能跳过) |
| **参数选择** | 硬件四档(L1-L4)自适应 + 梯度分析 | [→ 检查4](#检查4-硬件检测与自适应参数选择) + [EXPERIENCE.md 第21章](../../comfyui-controller/docs_cli/EXPERIENCE.md) |
| **排错** | 节点链/参数/文件操作/连接错误 | [→ SKILL.md 第8节](../../comfyui-controller/SKILL.md) + [EXPERIENCE.md 第10/14/23章](../../comfyui-controller/docs_cli/EXPERIENCE.md) |

### 0.2 场景化入口

**你要生成短视频（3-5秒）？** → 单段 HIGH+LOW 双阶段 + [检查4 参数梯度](#检查4-硬件检测与自适应参数选择)

**你要生成长视频（5秒+）？** → SVI Pro 分段生成 + [SKILL.md 4.15](../../comfyui-controller/SKILL.md) + Flux2修正

**你要排查画质问题？** → [EXPERIENCE.md 第14章 通用排查流程](../../comfyui-controller/docs_cli/EXPERIENCE.md) + [第16章 LOW阶段模型配置](../../comfyui-controller/docs_cli/EXPERIENCE.md)

**你要选 LoRA？** → [LoRA 选择策略](#lora-选择策略必须学会选用-lora不能跳过) 决策流程

---

## 适用场景

- 用户请求图生视频（img2vid）
- 用户请求首尾帧视频（first_last_frame）
- 用户请求多图片生成视频（multi_image_video，本质是从多个图片中提取元素生成视频）
- 用户请求长视频/视频拼接/多参考视频
- 任何涉及 WanVideo 采样器的视频生成任务

## 关键备注

**重要**：本指南基于 Wan2.2-I2V-A14B 模型的 V1-V19 + C5 v3-v14 + C8 完整迭代验证。如使用其他模型系列或硬件配置，需参考"多种可尝试方向"章节和"硬件梯度档位"进行调整。

**硬件梯度档位**（所有参数推荐均以此为依据）：

| 档位 | VRAM范围 | 推荐分辨率 | 单次最大帧数 | blocks_to_swap | base_precision |
|------|---------|-----------|------------|----------------|----------------|
| L1 入门级 | 8-12GB | 352×640 | 81帧 | 40-42 | bf16 |
| L2 标准级 | 12-16GB | 480×640 | 121帧 | 38-40 | bf16 |
| L3 高性能级 | 16-24GB | 480×848 | 121-241帧 | 20-24（C8验证） | bf16 |
| L4 专业级 | ≥24GB | 576×1024 | 241帧 | 20-24 | fp16_fast |

> **C8 验证更新**：L3 档 blocks_to_swap 从 36-38 修正为 20-24。值过高会导致专用显存闲置（仅用 40%），转而使用共享 GPU 内存。降至 20 后专用显存利用率提升至 75%+。

**路径变量约定**（本指南使用以下变量替代绝对路径）：
- `${COMFYUI_PATH}`: ComfyUI安装目录
- `${PROJECT_PATH}`: 本项目根目录
- `${COMFYUI_PORT}`: ComfyUI服务端口（默认3198，可通过环境变量配置）
- `${OUTPUT_DIR}`: 视频输出目录
- `${TEMP_DIR}`: 临时文件目录

**端口约定**：ComfyUI 服务运行在端口 `${COMFYUI_PORT}`（默认3198，可通过环境变量配置）。

## 6项强制检查

### 检查1: ComfyUI 服务可用性

**执行方式**: 向 ComfyUI 发送 HTTP GET 请求
- 端口连通检查: `GET http://127.0.0.1:${COMFYUI_PORT}/system_stats`
- API 响应检查: `GET http://127.0.0.1:${COMFYUI_PORT}/object_info`

**通过标准**: 两个请求均返回 HTTP 200 且 JSON 可解析

**失败处理**: 终止任务，提示"ComfyUI 服务不可用，请确认服务已启动（端口 ${COMFYUI_PORT}）"

**备注**：
- 如服务启动失败，检查 ComfyUI 控制台是否有第三方节点报错（如 zsq_prompt 的 VAELoader.vae_list() 错误），这类错误通常非致命，服务仍可继续启动
- 如端口被占用，使用 `--port` 指定其他端口

**ComfyUI 启动标准命令（验证成功，必须使用）**：
```powershell
.\python\python.exe -u main.py --port ${COMFYUI_PORT} --listen 127.0.0.1 `
  --disable-all-custom-nodes `
  --whitelist-custom-nodes ComfyUI-WanVideoWrapper ComfyUI-VideoHelperSuite ComfyUI-KJNodes comfyui-frame-interpolation comfyui-essentials ComfyUI_LayerStyle `
  --output-directory ${OUTPUT_DIR} `
  --temp-directory ${TEMP_DIR}
```
- **必须使用嵌入式 Python** `.\python\python.exe`（venv 已失效）
- **`--whitelist-custom-nodes` 必须与 `--disable-all-custom-nodes` 同时使用**（单独使用无效）
- **`--whitelist-custom-nodes` 参数必须使用空格分隔**（逗号分隔会被识别为单个字符串导致白名单失效）
- **必须重定向输出目录**（避免 ComfyUI 安装目录权限问题导致 VHS_VideoCombine 失败）
- **白名单必须包含 `ComfyUI_LayerStyle`**（提供 `PurgeVRAM V2` 节点，用于双模型架构显存清理）
- 白名单模式自动跳过 Manager（联网超时崩溃）和 Impact-Pack（加载卡住）
- 启动耗时约 90 秒
- **连续任务间必须重启 ComfyUI**（单次任务后内存占用 30GB+ 不释放，导致 HTTP 超时）

---

### 检查2: 模型可用性（按系列分组，禁止跨系列混用）

**执行方式**: `GET http://127.0.0.1:${COMFYUI_PORT}/object_info` 查询以下节点获取可用模型列表
- `WanVideoModelLoader` → diffusion_models（HIGH/LOW 模型）
- `WanVideoVAELoader` → vae
- `LoadWanVideoT5TextEncoder` → t5 文本编码器
- `CLIPVisionLoader` → clip_vision

**通过标准**:
- 所需模型文件均出现在可用列表中
- 所有组件属于同一模型系列（如 Wan2.2 系列: wan 模型 + wan VAE + t5 编码器 + clip_vision_h）
- 双阶段架构需同时存在 HIGH 和 LOW 模型文件

**失败处理**: 终止任务，列出缺失的模型文件名，提示用户下载或切换方案

**系列关键词映射**:
- Wan2.2: 模型含 "wan"，VAE 含 "wan"，CLIP 含 "t5"，clip_vision 含 "clip_vision_h"
- 禁止组合: Wan2.2 模型 + SD VAE、Flux 模型 + wan VAE 等跨系列混用

**推荐模型组合（V18/V19 验证成功）**：
- HIGH 模型: `Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors`
- LOW 模型: `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors`
- VAE: `Wan2_1_VAE_bf16.safetensors`
- T5: `umt5-xxl-enc-fp8_e4m3fn.safetensors`
- CLIP Vision: `clip_vision_h.safetensors`

---

### 检查3: 视频专用节点完整性（V18 验证架构）

**执行方式**: `GET http://127.0.0.1:${COMFYUI_PORT}/object_info/{node_name}` 逐一查询以下节点

**必需节点清单（V18 验证成功的 WanVideoWrapper 原生架构）**:

| 节点名称 | 用途 | 备注 |
|---------|------|------|
| WanVideoModelLoader | 加载 HIGH/LOW 扩散模型 | 不直接接收 block_swap_args 和 lora |
| WanVideoBlockSwap | 生成 BlockSwap 配置参数 | 独立节点，输出 BLOCKSWAPARGS |
| WanVideoSetBlockSwap | 将 BlockSwap 配置应用到模型 | 接收 model + block_swap_args，输出 model |
| WanVideoLoraSelect | 选择 LoRA 并设置强度 | 输出 WANVIDLORA |
| WanVideoSetLoRAs | 将 LoRA 应用到模型 | 接收 model + lora，输出 model |
| WanVideoVAELoader | 加载 Wan VAE | |
| LoadWanVideoT5TextEncoder | 加载 T5 文本编码器 | |
| WanVideoTextEncode | T5 编码提示词 | |
| WanVideoClipVisionEncode | CLIP Vision 编码图像 | |
| WanVideoImageToVideoEncode | I2V 编码 | 输出 image_embeds |
| WanVideoSampler | Wan 专用采样器 | 支持双阶段串行 |
| WanVideoDecode | 解码视频潜在空间 | 禁用 enable_vae_tiling |
| VHS_VideoCombine | 视频合成输出 | |
| LoadImage | 加载素材 | |
| INTConstant | 共享参数节点 | 用于 steps 和 split_step |
| CreateCFGScheduleFloatList | 动态 CFG 调度 | V18 关键改进 |

**正确的节点链架构（V18 验证）**：
```
WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler
```

**错误架构（V16/V17 旋转问题根因）**：
```
WanVideoBlockSwap(生成args) → WanVideoModelLoader(直接接收block_swap_args) → WanVideoSampler
```

**条件必需节点**（按任务类型）:
| 任务类型 | 额外必需节点 | 说明 |
|---------|------------|------|
| 多图片生成视频（multi_image_video） | `ImageConcatMulti`（来自 KJNodes）、`ImageScale` | C8 验证：必须用 ImageConcatMulti 拼接多图作为 start_image，CLIP Vision 的 concat 仅是语义引导 |
| 首尾帧 | `WanFirstLastFrameToVideo` | - |
| 显存管理（双模型架构） | `PurgeVRAM V2`（来自 ComfyUI_LayerStyle） | C8 验证：HIGH→LOW 切换点必须插入显式显存清理节点 |

**通过标准**: 所有必需节点在 /object_info 响应中存在

**失败处理**: 终止任务，列出缺失节点，提示安装对应的 ComfyUI 插件包

**节点必填参数（踩坑记录，缺失会导致工作流验证失败）**:
| 节点 | 必填参数 | 值 |
|------|---------|-----|
| WanVideoSampler | riflex_freq_index | 0 |
| WanVideoVAELoader | precision | bf16 |

---

### 检查4: 硬件检测与自适应参数选择

**执行方式**:
1. GPU VRAM 查询: `nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits`
2. 系统内存查询: `wmic ComputerSystem get TotalPhysicalMemory`
3. 调用 `get_adaptive_params(vram_mb)` 获取推荐参数档次

**显存物理限制公式（重要）**：
```
FFN激活值 ≈ (帧数 × 宽 × 高 / 4096) × 20480 × 2bytes
```
当 FFN激活值 > 显存总量 时，物理不可行，必须降低分辨率或帧数。

**示例计算**：
- 241帧@480x848: FFN约15.7GB（L3档可行）
- 241帧@576x1024: FFN约22.8GB（L3档不可行，需L4档）
- 241帧@720x1280: FFN约35.4GB（L4档不可行）

**四档参数表（V18/V19 + C5 v14 + C8 验证值，质量优先）**:

| 档位 | VRAM 范围 | 分辨率 | 单次最大帧数 | steps | split_step | blocks_to_swap | base_precision |
|------|----------|--------|------------|-------|------------|----------------|----------------|
| L4 专业级 | ≥24GB | 576x1024 | 241 | 8-10 | 4-5 | 20-24 | fp16_fast |
| L3 高性能级 | 16-24GB | 480x848 | 121-241 | 4-8 | 2-4 | 20-24（C8验证） | bf16 |
| L2 标准级 | 12-16GB | 480x640 | 121 | 4-8 | 2-4 | 38-40 | bf16 |
| L1 入门级 | 8-12GB | 352x640 | 81 | 4-6 | 2-3 | 40-42 | bf16 |
| 不足 | <8GB | — | — | — | — | — | — |

> **C8 验证更新**：L3 档单段短视频使用 steps=4（HIGH:2+LOW:2）质量足够，blocks_to_swap=20（非36）。steps=8 适用于分段长视频或追求更高质量的场景。

**V18/V19 + C5 v14 + C8 验证成功的核心参数**:
- attention_mode: `sdpa`（C8 验证 + 本机 PyTorch 2.9.1+cu128 实测：sageattn 的 C++/CUDA 扩展与当前 PyTorch 版本不兼容，触发 `code 0xc0000139` DLL 加载失败（入口点缺失），强制使用 `sdpa`（PyTorch 原生注意力），稳定性优先）
- base_precision: 按硬件档位选择（L1/L2/L3:bf16, L4:fp16_fast）
- quantization: `fp8_e4m3fn_scaled`
- scheduler: `dpm++_sde`（重要：非 unipc，unipc 会导致动作卡住旋转）
- shift: `8.0`（重要：非 3.0 或 5.0）
- rope_function: `comfy_chunked`（480x848 及以上必须使用，降低显存峰值）
- noise_aug_strength: `0.1`（禁止 0，会导致亮度锚定缺失）

**通过标准**:
- VRAM ≥ 8192 MB（8GB）
- 系统内存 ≥ 16384 MB（16GB）
- 双模型架构 VRAM 需求 ×2，需确认显存充足

**失败处理**: VRAM < 8GB 时终止任务，提示"显存不足，最低需要 8GB VRAM"

**重要**: 性能参数禁止完全写死，必须根据硬件动态选择。用户可手动覆盖推荐值，但系统应先展示基于硬件的推荐。

### 检查4.5: 视频时长与帧数策略（最高优规则）

**【最高优先级】无论如何优化，必须保障最终画面质量为 16-24fps**。任何优化措施不得以低于16fps为代价换取速度或显存。

#### 单次生成策略（帧数与硬件配置相关）

**重要**：单次可生成的最大帧数受**显存容量**和**模型语义理解**双重约束，不能写死固定帧数。

Wan2.2 I2V 模型训练原生长度约81帧（3.4秒@24fps）。超过训练长度时：
- **RIFLEX** 可防止 RoPE 数学循环（`riflex_freq_index=6`）
- **但 RIFLEX 不防语义重复**：模型会通过重复动作序列填充时间（C5任务v3-v8验证）

**单次生成帧数推荐（按显存分档）**：

| 显存档位 | 推荐单次最大帧数 | 对应时长@24fps | 说明 |
|---------|----------------|---------------|------|
| ≥24GB | 241帧 | 10秒 | 可尝试单次10秒，但注意语义重复风险 |
| 16-24GB | 121帧 | 5秒 | 超过121帧易触发语义重复 |
| 8-16GB | 81帧 | 3.4秒 | 训练原生长度，最安全 |
| <8GB | 不建议 | — | 显存不足 |

**超过单次帧数限制时**：采用分段生成+拼接（见方向4），或使用官方Context Window方案

#### 多种可尝试方向（OOM 或语义重复时选择）

**方向1: 降分辨率保帧数（推荐）**
- 优点: 保持 10 秒时长，动作连贯性不受影响
- 缺点: 画质下降
- 适用: 显存接近极限但未超出
- 示例: 480x848 → 352x640

**方向2: 降帧数保分辨率（需配合插帧补足时长）**
- 优点: 保持画质
- 缺点: 单次时长缩短，需后续 RIFE 插帧补足总时长
- 适用: 必须保持高分辨率且单次显存不足的场景
- 示例: 241帧 → 121帧（5秒）+ RIFE 插帧到 10 秒
- **硬约束**：禁止直接降级时长（如 10秒→3.4秒），必须通过插帧保持总时长

**方向3: 降精度保帧数和分辨率**
- 优点: 保持时长和分辨率
- 缺点: 画质轻微下降，bf16 比 fp16_fast 慢约 1.5 倍
- 适用: 显存略不足
- 示例: fp16_fast → bf16

**方向4: 分段生成+拼接（多图视频推荐）**
- 优点: 可生成任意时长，每段在模型训练长度内避免语义重复
- 缺点: 段间转场需精心设计（末帧继承+CLIP权重调整）
- 适用: 超过单次帧数限制，或多图视频需要场景转场
- C5验证成功配置：3段×81帧=10秒，每段start_image=前段末帧，CLIP concat(1.png=1.5 + 末帧=0.5)
- **关键**：段间转场需提取前段末帧作为后段start_image，CLIP双图权重调整保持角色一致性

**禁止策略**：
- 禁止直接将 10 秒降级为 3.4 秒（违反用户时长需求）
- 禁止双阶段帧数低于 16 帧（违反最高优规则）
- 禁止使用 SaveLatent/LoadLatent 跨工作流传递 latent（精度损失）

---

### 检查5: 素材文件校验

**执行方式**: 检查 ComfyUI input 目录中是否存在任务引用的素材文件
- input 目录: `${COMFYUI_PATH}/input/`
- 列出目录: `LS ${COMFYUI_PATH}/input/`
- 或通过 API: `GET http://127.0.0.1:${COMFYUI_PORT}/upload/image` 查看

**通过标准**:
- LoadImage 节点引用的所有图片文件均存在于 input 目录
- 图片尺寸合理（非 0 字节文件）
- 图片分辨率与目标视频分辨率匹配（避免 VAE latent mismatch）
- 如需多图片生成视频，所有引用的图片均存在

**失败处理**: 终止任务，列出缺失的素材文件，提示用户将文件复制到 input 目录

**备注**：输入图片分辨率应与目标视频分辨率接近，否则 VAE 编码后 latent 尺寸不匹配会导致 `tensor size mismatch` 错误。

---

### 检查6: 提示词结构化校验

**执行方式**: 检查正面提示词是否符合三段式结构

**三段式结构要求**:
1. **画质前缀 + 镜头语言 + 场景描述**: `masterpiece, best quality, 8k, highly detailed, fixed camera, close-up shot, [场景描述]`
2. **主体外观 + 状态**: `subject appearance clear, [主体外观描述], [状态描述]`
3. **时序动作 + 控制词**: `[动作描述], smooth body motion, slight camera push, [控制词如"缓慢连贯"]`

**负面提示词标准模板（V19 验证）**:
```
色调艳丽，过曝，曝光变化，亮度突变，背景亮度变化，background brightening,
exposure drift, lighting changes, overexposed, highlight clipping, detail loss,
background replacement, background changing, different background,
静态，细节模糊不清，字幕，最差质量，低质量，JPEG压缩残留，
丑陋的，残缺的，多余的手指，畸形的，毁容的，手指融合，
杂乱的背景，三条腿，腿部消失，肢体断裂，肢体溶解，
多余肢体，缺失肢体，动作僵硬，动作断裂，motion blur, frame skipping,
distorted body, deformed limbs, floating hair, gravity defiance,
camera movement, camera pan, camera tilt, camera zoom, camera dolly,
camera shake, unstable framing, 视角变化, 运镜, 镜头移动,
face changing, character drift, inconsistent appearance,
blurry, low detail, pixelated, compressed artifacts,
blurring progression, detail degradation, cumulative quality loss
```

**通过标准**:
- 正面提示词包含画质前缀（masterpiece/best quality 等）
- 正面提示词包含主体描述
- 正面提示词包含动作/运动描述
- 负面提示词包含基本负面项

**失败处理**: 警告并自动补充缺失的三段式元素，或将用户白话转换为结构化提示词后再执行

**提示词动作控制备注（V16 旋转问题教训）**：
- 提示词中的动作描述会直接影响生成结果
- "turning steps" + "hip swaying" 在 V16 导致角色持续旋转
- V18/V19 使用 dpm++_sde 调度器后，完整舞蹈动作提示词不再导致旋转
- 如使用 unipc 调度器，需在负面提示词中加入 "spinning, rotating, turning around, pirouette, 360 rotation"

**不能直接使用用户白话作为提示词，必须经过三段式结构化转换。**

---

## 检查流程总结

```
用户请求视频生成
    ↓
检查1: ComfyUI 服务可用?  ──否──→ 终止，提示启动服务
    ↓ 是
检查2: 模型可用且同系列?  ──否──→ 终止，列出缺失模型
    ↓ 是
检查3: 视频专用节点完整?  ──否──→ 终止，列出缺失节点
    ↓ 是
检查4: 硬件达标+自适应参数  ──否──→ 终止，提示显存不足
    ↓ 是
检查5: 素材文件存在?      ──否──→ 终止，列出缺失文件
    ↓ 是
检查6: 提示词结构化?      ──否──→ 警告并自动转换
    ↓ 是
全部通过 → 执行视频生成任务
```

## LoRA 选择策略（必须学会选用 LoRA，不能跳过）

**重要**：项目硬约束要求必须学会选用 LoRA，不能跳过。LoRA不仅用于加速，还有画质增强、角色一致性、重新打光等多种类型。使用前必须检查本地`models/loras/`目录已有文件，根据任务需求甄别挑选。

### LoRA 类型分类

| 类型 | 用途 | 本地文件示例 | 是否可叠加 |
|------|------|-------------|-----------|
| 加速蒸馏 | 减少步数和CFG计算量 | `lightx2v_I2V_14B_480p_cfg_step_distill` | 不可与其他LoRA叠加 |
| 画质增强 | 提升细节和质感 | `SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH`、`Wan2.2-Fun-A14B-InP-low-noise-HPS2.1` | 可与其他类型叠加 |
| 重新打光 | 调整场景光线 | `WanAnimate_relight` | 可与其他类型叠加 |

### 加速 LoRA 选择（V18/V19 + C5 v14 + C8 验证）

**推荐: lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors**
- 用途: 加速采样，4-8步即可生成视频（**非画质增强**）
- 类型: cfg_step_distill（同时蒸馏 CFG + 步数）
- 适用: I2V（图生视频）专用
- **配置: HIGH strength=1.0, LOW strength=1.0**（C5 v14 + C8 验证，官方推荐值；HIGH=3.0会破坏MoE自然去噪曲线导致细节丢失）
- merge_loras: False
- 优点: 显著降低采样步数需求，30步→4-8步
- 缺点: 不能提升画质；在错误节点链架构（V16）中会破坏 CFG 引导一致性导致旋转
- **分辨率匹配**: 480p版本应用于480p分辨率（832×480或接近），用于非标准分辨率属分布外推理
- **步数选择**（C8 验证）：
  - 单段短视频（81帧/3.4秒）：steps=4（HIGH:2 + LOW:2）质量足够
  - 分段长视频（多段拼接）：steps=6-8 质量更优
  - 追求极致质量：steps=8-10（收益递减）

**不推荐: Wan21_I2V_14B_lightx2v_cfg_step_distill_lora_rank64.safetensors**
- 原因: Wan2.1 版本，可能不完全兼容 Wan2.2

### 画质增强 LoRA（可选）

**可选: SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16**
- 用途: HIGH模型画质增强
- 适用: 需要提升细节时（但不可与lightx2v叠加）
- 配置: merge_loras 必须为 False
- 优点: 提升细节和质感
- 缺点: 不可与加速LoRA叠加，需增加步数到20-30步

**可选: Wan2.2-Fun-A14B-InP-low-noise-HPS2.1**
- 用途: HPS质量评分增强
- 适用: 需要提升整体画质时
- 缺点: 不可与加速LoRA叠加

### 重新打光 LoRA（可选）

**可选: WanAnimate_relight_lora_fp16**
- 用途: 场景光线重新打光
- 适用: 需要调整场景光线时

### LoRA 使用决策流程

1. 检查本地`models/loras/`目录已有文件
2. 根据任务需求选择类型（加速/画质/角色/打光）
3. 确认LoRA与模型版本匹配（Wan2.1 vs Wan2.2）
4. 确认LoRA与分辨率匹配（480p vs 720p）
5. 确认LoRA间是否可叠加（加速LoRA通常不可叠加）
6. 遵循官方推荐strength值，不可随意提高

## 双阶段串行架构详解（V18/V19 + C8 验证成功）

### 架构原理

通过 WanVideoSampler 的 start_step/end_step 参数控制双阶段采样：
- HIGH 阶段: start_step=0, end_step=split_step（处理高噪声主结构）
- LOW 阶段: start_step=split_step, end_step=-1, samples=HIGH输出（处理低噪声细化）

### 动态 CFG 调度（V18 关键改进）

使用 CreateCFGScheduleFloatList 节点生成动态 CFG 调度：
- 配置: cfg_scale_start=2, cfg_scale_end=2, start_percent=0.0, end_percent=0.01
- 效果: 第一步 CFG=2，其余步 CFG=1
- 连接: 输出连接到 HIGH sampler 的 cfg 输入
- LOW sampler: 固定 cfg=1

### 多种可尝试方向（调度器选择）

**方向1: dpm++_sde 调度器（V18/V19 验证，推荐）**
- 优点: 随机性调度器，产生自然动作变化，不卡住旋转
- 缺点: 结果不完全可复现（即使种子相同）
- 适用: 舞蹈、动作丰富的视频生成

**方向2: unipc 调度器（V16/V17 使用，不推荐）**
- 优点: 确定性调度器，结果可复现
- 缺点: 确定性导致动作卡住旋转，需更强的提示词约束
- 适用: 静态或微动作视频

**方向3: euler 调度器（未验证）**
- 优点: 简单稳定
- 缺点: 可能缺乏动作多样性
- 适用: 简单测试场景

### 双模型显存管理（C8 任务验证，必须遵循）

> **硬约束**：在专用 GPU 显存未被尽可能利用前，尽量不使用共享 GPU 内存。每次显存里只能加载一个模型，不用的模型要立即卸载掉。

**三层显存管理防线**（必须同时启用）：

1. **第一层：模型加载与卸载**
   - `WanVideoModelLoader` 的 `load_device="offload_device"`：模型初始加载到 CPU，按需载入 GPU
   - `WanVideoSampler` 的 `force_offload=true`：采样后强制卸载模型

2. **第二层：显式显存清理**
   - 在 HIGH→LOW 切换点插入 `PurgeVRAM V2` 节点（来自 `ComfyUI_LayerStyle`）
   - `purge_cache=true` + `purge_models=true`：彻底清理显存
   - 仅依赖 `force_offload` 无法彻底释放显存，ComfyUI 模型缓存会保留引用

3. **第三层：分块卸载**
   - `WanVideoBlockSwap` 的 `blocks_to_swap`：采样过程中动态交换 transformer blocks
   - 按硬件档位选择：L3 级推荐 20（专用显存利用率 75%+）
   - 值过高会导致专用显存闲置，转而使用共享内存

**节点链顺序**（必须遵循）：
```
WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler (HIGH)
                                                                        ↓
                                                                  PurgeVRAM V2
                                                                        ↓
WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler (LOW)
                                                                        ↓
                                                                  PurgeVRAM V2
```

**连续任务间必须重启 ComfyUI**：单次任务后显存占用 30GB+ 不释放，下次任务会 OOM。

### 多图视频识别关键认知（C8 任务验证）

> **核心认知**：`WanVideoClipVisionEncode` 的 `combine_embeds="concat"` 仅合并语义特征向量，非像素合并。画面内容由 `start_image` 决定，CLIP Vision 仅作语义辅助引导。

**多图视频正确架构**：
```
LoadImage(1.png) → ImageScale ─┐
                               ├─→ ImageConcatMulti(direction="right") ──→ WanVideoImageToVideoEncode.start_image
LoadImage(2.png) → ImageScale ─┘
                               (同时仍分别送入 WanVideoClipVisionEncode.image_1/image_2)
```

**关键参数**：
- `ImageConcatMulti` 的 `direction="right"`：水平拼接（人物同框）
- `WanVideoImageToVideoEncode` 的 `width`/`height`：必须设置为拼接后的实际尺寸（如两张 480x640 拼接后为 960x640）
- `WanVideoClipVisionEncode` 的 `strength_1=1.5`/`strength_2=1.0`：主图权重略高

**提示词要求**：必须明确每个人物位置关系，如"左边女孩来自参考图1，右边女孩来自参考图2"。

## 参数与架构参考

- **技术文档**: `${PROJECT_PATH}/comfyui-controller/docs_cli/EXPERIENCE.md`
  - V1-V19 + C5 + C8 完整迭代经验教训
  - 显存物理限制公式与计算
  - LoRA 选择策略
  - 第 23 章 C8 多图视频完整任务复盘（显存管理、多图识别、提示词、排错思路）
- **源工作流参考**: `${COMFYUI_PATH}/custom_nodes/ComfyUI-WanVideoWrapper/example_workflows/wanvideo2_2_I2V_A14B_example_WIP.json`
- **任务执行脚本参考**: `${PROJECT_PATH}/comfyui-controller/scripts/c2_video_task.py`（5秒@20fps）、`c3_video_task.py`（10秒@24fps）、`c4_video_task.py`（10秒@24fps）
- **预检模块**: `${PROJECT_PATH}/comfyui-controller/scripts/pre_task_inquiry.py`
- **依赖检查**: `${PROJECT_PATH}/comfyui-controller/scripts/check_workflow_dependencies.py`

## 预检反问完整性要求（强制，不可跳过）

**预检反问必须包含以下4个必要环节，缺一不可**：

1. **模型选择展示**：查询 `GET /object_info` 获取可用模型列表，向用户展示当前可用的 HIGH/LOW/VAE/T5/CLIP 模型，确认使用哪套模型组合（不可直接使用默认模型而不告知用户）
2. **参数收集**：至少包含生成策略（单次/分段）、动作描述方式（简化/完整）、分辨率与帧数确认
3. **相机视角确认**（硬约束）：固定相机/运镜方式/视角变化，用户确认后方可执行
4. **硬件校验结果展示**：明示 GPU 显存、系统内存、推荐参数档次（高性能/标准/低性能），让用户确认参数选择

**反问执行顺序**：模型展示 → 参数收集 → 相机视角 → 硬件校验 → 用户确认 → 执行

**反面案例（C3 任务教训）**：仅反问生成策略/动作/运镜3项，未展示模型选择和硬件校验过程，违反硬约束。
