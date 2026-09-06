# ⚠️ 历史存档 — 请勿参考本文档参数

> **本文件为历史存档，所有内容已被推翻或更新。切勿以本文档中的参数、结论、经验指导任何任务执行。**
>
> 当前最新文档请查阅：
> - 经验与参数：`comfyui-controller/docs_cli/EXPERIENCE.md`（含第21章参数梯度分析）
> - 技能与架构：`comfyui-controller/SKILL.md`
> - 视频任务指南：`.trae/skills/video-task-execution-guide/SKILL.md`
> - 图片任务指南：`.trae/skills/image-task-execution-guide/SKILL.md`
> - 项目硬约束：`c:\Users\15910\.trae-cn\memory\projects\-e-comfyui-cli\project_memory.md`
>
> 本文件仅保留作为 V1-V17 迭代历史记录，不做任何其他用途。

---

# ComfyUI Omni-Controller 实战经验总结与优化建议（历史存档）

> 作者：AI Agent (基于 deepseek-v4-pro 对 comfyui-controller 项目的全部使用经验)
> 用户环境：RTX 3080 20GB | Ryzen 7950X | 64GB RAM | Windows | ComfyUI-WanVideoWrapper
> 更新：2026-06-04（原始）/ 2026-07-22（过时声明）

> **⚠️ 过时声明（2026-07-22）**：本文档记录的是 V1-V17 阶段的经验，部分结论已被 V18/V19 + C5 v3-v14 验证推翻：
> - 调度器结论"unipc 是唯一稳定选择"已被推翻，V18/V19 验证 `dpm++_sde` 才是正确选择（unipc 导致动作卡住旋转）
> - 静态 CFG=5.0 已被推翻，V18/V19 使用动态 CFG 调度 `[2,1,1,1,1,1]`
> - steps=18-25 已被推翻，V18/V19 使用 lightx2v LoRA 加速后 steps=6-8
> - 旧架构（UNETLoader+ModelSamplingSD3+KSampler）已被 V18/V19 架构取代（WanVideoModelLoader+WanVideoSetBlockSwap+WanVideoSetLoRAs+WanVideoSampler）
> - shift=3.0 已被推翻，V18/V19 使用 shift=8.0
> - **lightx2v HIGH strength=3.0 已被推翻**，C5 v14 验证 strength=1.0 是官方推荐值（3.0会破坏MoE自然去噪曲线导致细节丢失）
> - **241帧单次生成"可行"需补充条件**，C5验证超过模型训练长度(81帧)时RIFLEX防数学循环但不防语义重复，长视频应分段生成+拼接
> - **分段生成"不推荐"需修正**，C5验证分段生成+拼接是多图视频的有效方案（段间末帧继承+CLIP权重调整）
> - **LoRA不仅用于加速**，还有画质增强(SVI_v2_PRO/HPS2.1)、重新打光(WanAnimate_relight)等多种类型，使用前必须检查本地已有LoRA并甄别挑选
>
> **请以以下文档为准**：`.trae/skills/video-task-execution-guide/SKILL.md`、`comfyui-controller/docs_cli/EXPERIENCE.md`（含第12章C5多图视频迭代经验）、`comfyui-controller/SKILL.md`、`c:\Users\15910\.trae-cn\memory\projects\-e-comfyui-cli\project_memory.md`
>
> 本文档保留作为历史参考，请勿将其中的参数结论用于实际任务执行。

---

## 目录

1. [项目架构速览](#1-项目架构速览)
2. [服务器生命周期管理](#2-服务器生命周期管理)
3. [工作流构建深度经验](#3-工作流构建深度经验)
4. [质量-速度三代优化历程](#4-质量-速度三代优化历程)
5. [硬件感知参数策略](#5-硬件感知参数策略)
6. [错误模式与解决方案](#6-错误模式与解决方案)
7. [监控与调试模式](#7-监控与调试模式)
8. [后续升级建议](#8-后续升级建议)

---

## 1. 项目架构速览

### 1.1 核心脚本分工

| 脚本 | 用途 | 本次使用频率 |
|------|------|------|
| `scripts/start_server.py` | 启动 ComfyUI 实例 | 高频（首次启动 + 多次重启） |
| `scripts/run_workflow.py` | WebSocket 工作流执行 | 未直接使用 |
| `scripts/check_status.py` | 环境检查 | 使用 1 次 |
| `scripts/download_models.py` | 模型下载 | 未使用（模型已就绪） |
| `scripts/workflow_converter.py` | UI->API 格式转换 | 未使用（直接写 API JSON） |

### 1.2 实际执行模式

本次实践建立了**第三种执行模式**----直接 HTTP API 交互：
- 不通过 `run_workflow.py`（WebSocket 太重）
- 不通过 `comfy run`（CLI 模式需要额外依赖）
- 直接 `POST /prompt` -> 轮询 `/history/{id}` -> 获取输出

这种模式对 AI Agent 最友好：轻量、无额外依赖、进度可观测。

### 1.3 项目目录完整索引（本文档即全量参考）

#### 1.3.1 scripts/ -- 技能模式脚本

| 脚本 | 功能 | 关键参数 | 状态 |
|------|------|------|------|
| `controller.py` | 服务器控制中枢（start/stop/wait） | `--port`, `--cpu`, `--wait` | 稳定 |
| `start_server.py` | 服务器启动脚本（含首次安装，官方标准方式） | `--port`, `--install`, `--cpu` | 稳定 |
| `run_workflow.py` | WebSocket 工作流执行器 | `--workflow`, `--wait`, `--timeout`, `--output-dir` | 需测试 |
| `check_status.py` | 环境检查（Python/PyTorch/CUDA/GPU/节点/模型） | 无参数，全量输出 | 稳定 |
| `workflow_converter.py` | UI 格式(nodes/links) -> API 格式(class_type/inputs) | `--input`, `--output` | 稳定 |
| `edit_workflow.py` | 工作流参数编辑 | `--positive-prompt`, `--seed`, `--width`, `--height`, `--steps`, `--cfg` | 可用 |
| `dependency_manager.py` | 依赖分析+自动修复 | `--workflow`, `--fix` | 需测试 |
| `download_models.py` | 多源模型下载（HF/CivitAI/URL） | URL列表, `--overwrite`, `--no-pget` | 可用 |
| `get_available_models.py` | 查询本地可用模型 | `--search` | 可用 |
| `advanced_workflow_builder.py` | 高级工作流构建 | 待探索 | 未测试 |
| `workflow_analyzer.py` | 工作流分析 | 待探索 | 未测试 |

#### 1.3.2 cli/ -- CLI 模式（comfy-cli 移植）

| 路径 | 功能 | 备注 |
|------|------|------|
| `cli/cmdline.py` | CLI 入口，click 命令注册 | 导入路径已修复（typing_compat/logging_utils） |
| `cli/command/run.py` | `comfy run` 实现 | **Line 584-587 已修复** POST headers + method |
| `cli/command/install.py` | `comfy install` | GPU/CPU/PR 安装 |
| `cli/command/launch.py` | `comfy launch` | 后台模式 --background |
| `cli/command/generate/` | `comfy generate`（云端 Partner Nodes） | 支持 flux-pro/dalle 等 |
| `cli/command/custom_nodes/` | `comfy node *` 全套节点管理 | install/uninstall/update/fix/publish/bisect |
| `cli/command/models/` | `comfy model *` 模型管理 | download/list/remove |
| `cli/command/github/` | `comfy github` PR 信息 | - |
| `cli/command/code_search.py` | 代码搜索 | - |
| `cli/config_manager.py` | 配置管理 | 版本获取已添加异常保护 |
| `cli/workspace_manager.py` | 工作空间管理 | - |
| `cli/uv.py` | uv 依赖编译器 | DependencyCompiler 类 |
| `cli/workflow_to_api.py` | UI->API 转换（CLI 版） | - |
| `cli/env_checker.py` | 环境检查（CLI 版） | - |
| `cli/cuda_detect.py` | CUDA 检测 | - |
| `cli/registry/` | 注册表 API | api.py / config_parser.py / types.py |
| `cli/standalone.py` | 独立 Python 环境打包 | - |

#### 1.3.3 已知的包冲突修复（安装脚本应自动处理）

| 原文件名 | 重命名为 | 原因 |
|------|------|------|
| `cli/typing.py` | `cli/typing_compat.py` | 与 Python 标准库 `typing` 同名，导致 `ImportError: Annotated` |
| `cli/logging.py` | `cli/logging_utils.py` | 与 Python 标准库 `logging` 同名，导致 `AttributeError: getLogger` |

涉及更新的引用（共 30+ 处）：`cmdline.py`, `ui.py`, `env_checker.py`, `update.py`, 所有 `from cli.typing import` -> `from cli.typing_compat import`

#### 1.3.4 ComfyUI 服务端关键目录

```
D:\2026-ComfyUI-V8.3\
  main.py                          # 服务启动入口（已修复 POST headers）
  models/
    checkpoints/                    # SD 模型: v1-5-pruned-emaonly.safetensors
    diffusion_models/               # Wan GGUF: Wan2.2-{T2V|I2V}-A14B-LowNoise-Q5_K_M.gguf
    vae/                            # WanVAE: Wan2_1_VAE_bf16.safetensors
    text_encoders/                  # T5: umt5-xxl-enc-fp8_e4m3fn.safetensors（非scaled）
    upscale_models/                 # RealESRGAN_x2.pth, 2x_StarSample_V2.0.safetensors
    clip/                           # CLIP 模型
  custom_nodes/
    ComfyUI-WanVideoWrapper/        # Wan 节点: ModelLoader/VAELoader/T5Encoder/Sampler/Decode
    ComfyUI-Manager/                # 节点管理
    ComfyUI-VideoHelperSuite/       # VHS_VideoCombine（mp4 合成）
    comfyui_controlnet_aux/         # ControlNet 预处理器
    was-node-suite-comfyui/         # WAS 节点套件
  output/                           # 生成输出目录
  input/                            # 手动输入文件目录（I2V 源图放这里）
```

#### 1.3.5 文档索引

| 文档 | 定位 | 内容 |
|------|------|------|
| `SKILL.md` | 技能主文档 | 项目概述/双模式架构/Wan参数规范/使用指南 |
| `docs_cli/EXPERIENCE.md` | CLI 踩坑记录 | 包冲突修复/依赖缺失/HTTP修复/OOM处理 |
| **`docs_cli/UPGRADE-NOTES.md`** | **本文档** | **全链路实战优化/多档显存策略/所有经验汇总** |
| `docs_cli/DESIGN-uv-compile.md` | uv 编译设计 | - |
| `docs_cli/PRD-uv-compile.md` | uv 编译 PRD | - |
| `docs_cli/TESTING-e2e.md` | E2E 测试 | - |
| `docs_cli/json-output.md` | NDJSON 输出规范 | - |

---

## 2. 服务器生命周期管理

### 2.1 启动命令

经过 5+ 次重启验证的最佳启动命令（官方标准方式，在 ComfyUI 安装目录下执行）：

```bash
# Windows（嵌入式 Python 独立版）
.\python\python.exe -u main.py --port 3198 --listen 127.0.0.1

# Linux / macOS（标准 Python 安装）
python main.py --port 3198 --listen 127.0.0.1
```

- `-u` 无缓冲输出，便于查看日志
- `--port 3198` 自定义端口
- `--listen 127.0.0.1` 仅本地监听（安全性）
- 不依赖任何第三方 GUI 启动器（如 wangyi AI绘世启动器.exe 等）
- **不要**加 `--lowvram`，会严重降低性能（本次实测性能下降 3-5x）

### 2.2 服务器稳定性问题

| 问题 | 现象 | 原因猜测 | 影响 |
|------|------|------|------|
| **历史记录丢失** | `/history` 返回空或缺少已完成条目 | 服务器内部重启（\~90分钟一次） | 输出文件被跳过，需重试 |
| **内存累积** | 多次执行后显存峰值逐渐升高 | force_offload 未完全清理 | 需手动重启 |
| **端口被占用** | 启动失败 "Address in use" | 前一次实例未完全退出 | 需 taskkill |

### 2.3 推荐启动流程（未来应整合到 `start_server.py`）

```python
# 1. 杀掉旧进程
import subprocess
subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)

# 2. 释放端口
import socket
sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('127.0.0.1', 3198))
sock.close()

# 3. 无延迟重启
subprocess.Popen([python_exe, "-s", "main.py", "--port", "3198", "--listen", "127.0.0.1"])

# 4. 健康检查循环
for _ in range(30):
    try:
        urllib.request.urlopen("http://127.0.0.1:3198/system_stats", timeout=2)
        break
    except:
        time.sleep(2)
```

---

## 3. 工作流构建深度经验

### 3.1 三种模型架构对比

| 维度 | SD 1.5 | Wan 2.2 T2V | Wan 2.2 I2V |
|------|------|------|------|
| 文本编码器 | CLIP (77 token limit) | T5-XXL (512 token, 非scaled) | T5-XXL |
| 潜在空间 | 4通道 VAE | 16通道 WanVAE | 16通道 WanVAE |
| 时间维度 | 无 | 理论：n帧 -> 实际：1帧=txt2img | 81帧 @ 16fps |
| 采样器 | KSampler | WanVideoSampler | WanVideoSampler |
| 调度器 | euler/normal | unipc (仅此有效) | unipc |
| cfg | 7.0 | 5.0 | 5.0 |
| shift | 不需要 | 8.0 | 8.0 |
| 分辨率约束 | 64 倍数 | 8 倍数 | 8 倍数 |
| 原生分辨率 | 512x512~512x768 | 832x480 (16:9) | 832x480 |

### 3.2 Wan T2V 节点链（最精简已验证）

```
[1] WanVideoModelLoader ────┐
[2] WanVideoVAELoader ────┐ │
[3] LoadWanVideoT5TextEncoder    │ │
     ↓                         │ │
[4] WanVideoTextEncode ───────┐│ │
[5] WanVideoEmptyEmbeds ─────┤│ │
     ↓                       ↓↓ ↓
[6] WanVideoSampler ───-> [7] WanVideoDecode ─-> [8] SaveImage
```

关键连接：`[4] t5 -> [3]` / `[6] model -> [1]` / `[6] image_embeds -> [5]` / `[6] text_embeds -> [4]` / `[7] vae -> [2]` / `[7] samples -> [6]`

### 3.3 Wan I2V 节点链（图生视频）

在 T2V 基础上修改：
- `WanVideoEmptyEmbeds` -> 替换为 `LoadImage` + `WanVideoImageToVideoEncode`
- 末尾加 `VHS_VideoCombine` 合成 mp4

```
[5] LoadImage ──────────────────┐
[2] WanVideoVAELoader ─────────┤
                                ↓
[6] WanVideoImageToVideoEncode -> [7] WanVideoSampler -> [8] WanVideoDecode -> [9] VHS_VideoCombine
```

### 3.4 2x 放大链（T2V 后处理）

在前述 T2V 链的 VAE 解码和保存之间插入：

```
[7] WanVideoDecode
     ↓
[8] UpscaleModelLoader (RealESRGAN_x2.pth)
     ↓
[9] ImageUpscaleWithModel
     ↓
[10] SaveImage
```

放大耗时：~0.5 秒（几乎免费）。

### 3.5 WanVideoDecode 参数陷阱

**即使关闭 tiling，也必须传 tile 参数**，否则验证失败：

```json
"7": {
    "class_type": "WanVideoDecode",
    "inputs": {
        "vae": ["2", 0],
        "samples": ["6", 0],
        "enable_vae_tiling": true,
        "tile_x": 256,
        "tile_y": 256,
        "tile_stride_x": 128,
        "tile_stride_y": 128
    }
}
```

错误信息：`WanVideoDecode.VALIDATE_INPUTS() missing 4 required positional arguments: 'tile_x', 'tile_y', 'tile_stride_x', and 'tile_stride_y'`

### 3.6 T5 文本编码器选择

**关键坑**：`umt5-xxl-enc-fp8_e4m3fn.safetensors` 是非 scaled 版本，WanVideoWrapper 正确接受。`umt5-xxl-enc-fp8_scaled.safetensors` 是 scaled 版本，会导致错误：

```
ValueError: Invalid T5 text encoder model, fp8 scaled is not supported by this node
```

如果服务器报这个错 -> 切换 enc 模型文件。

---

## 4. 质量-速度三代优化历程

### 4.1 三代数据对比

| | v1 (原始) | v2 (过度优化) | v3 (平衡) |
|------|------|------|------|
| 文件 | `task_mecha_girl.json` | `task_mecha_girl_fast.json` | `task_mecha_girl_v2.json` |
| 输出 | `mecha_girl_warrior_00001_.png` | `mecha_girl_fast_00001_.png` | `mecha_girl_v3_00001_.png` |
| 基分辨率 | 832×480 | **480×480** | 832×480 |
| 最终输出 | 832×480 | 960×960 | **1664×960** |
| 步数 | 25 | **15** | 20 |
| 采样器 | unipc | **euler** | unipc |
| 放大器 | 无 | RealESRGAN 2x | RealESRGAN 2x |
| 耗时 | ~91s | ~60s | **72-76s** (↓16-21%) |
| 文件大小 | 604 KB | 1.19 MB | 2.07-2.13 MB |
| 背景 | 正确白色 | **过曝纯白** | 正确 |
| 脸部 | 清晰 | **模糊** | 清晰 |
| 工业结论 | 基线 | **已排除** | **推荐** |

### 4.2 v2 失败根因分析

问题根因不是"ESRGAN 放大没用"，而是**低分辨率原材料的输入质量不可恢复**：

```
输入:  480×480, 15步, euler (细节欠缺)
       ↓
ESRGAN: 只能锐化现有边缘，不能创造不存在的高频细节
       ↓
输出:  960×960 (看起来清晰，实则细节缺失)
```

ESRGAN 本质是卷积上采样+残差学习，工作于图像域。如果步骤太少，生成器尚未收敛到正确分布，ESRGAN 放大的是"未收敛的模糊图像"。

### 4.3 v3 成功关键

```
输入:  832×480, 20步, unipc (原生分辨率，采样充分)
       ↓
ESRGAN: 在高频信息充足的图像上执行上采样
       ↓
输出:  1664×960 (细节完整，分辨率 4x)
```

**核心原则（已写入 `comfyui-hardware-strategy-v2` 记忆）**：
- 不要在生成阶段降分辨率来"加速"----原生分辨率是质量下限
- 加速靠减步数（25->20，省 16%）而非降分辨率
- 放大器是"锦上添花"不是"雪中送炭"
- 减步数下限：Wan T2V ≥ 18 步，Wan I2V ≥ 10 步

---

## 5. 多档显存硬件策略（8GB / 12GB / 16GB / 20GB+）

> 核心原则不变：保持原生分辨率，减步数而非降分辨率，放大器锦上添花。

### 5.1 显存档位概览

| 档位 | 典型 GPU | 可用模型格式 | Wan T2V 能力 | Wan I2V 能力 | 推荐降级策略 |
|------|------|------|------|------|------|
| **8GB** | RTX 3070/4060Ti | Q4_K_M GGUF | 受限（需降分辨率） | 不可用 | 用 SD 1.5 替代 Wan |
| **12GB** | RTX 3060/4070 | Q5_K_M GGUF | 可用（480x832 竖屏） | 勉强（降低帧数至 33-41） | BlockSwap + force_offload |
| **16GB** | RTX 3080/4070Ti Super | Q8_0 / FP8 | 流畅（832x480 横屏） | 可用（81帧 15步） | 标准配置 |
| **20GB+** | RTX 3080 20G/3090/4090 | BF16 / FP8 | 全速 | 全速 | 无限制 |

### 5.2 8GB 档位策略

```
8GB 显存 = Wan 2.2 勉强运行，但不推荐作为主力
```

| 任务 | 推荐方案 | 配置 | 预估 | 备注 |
|------|------|------|------|------|
| 静态图片 | **SD 1.5（首选）** | 512x768, 20步, euler | ~40s | 质量好速度快 |
| 静态图片（复杂） | Wan T2V Q4_K_M | 480x480, 18步, unipc | ~90s | 原生分辨率妥协 |
| 静态图片（复杂） | Wan T2V Q4_K_M + 2x | 480x480, 18步 + ESRGAN | ~92s | 输出 960x960 |
| 视频 I2V | **不可用** | - | - | 81帧显存不足 |
| 视频 T2V | 不推荐 | 480x480, 21帧, 10步 | 质量极差 | 用云端替代 |

**8GB 专有参数**：
```json
{
  "model": "Wan2.2-T2V-A14B-LowNoise-Q4_K_M.gguf",
  "base_precision": "fp16",
  "quantization": "disabled",
  "load_device": "offload_device",
  "force_offload": true,
  "blocks_to_swap": 20,
  "width": 480, "height": 480,
  "steps": 18, "cfg": 5.0, "shift": 8.0,
  "enable_vae_tiling": true,
  "tile_x": 128, "tile_y": 128
}
```

### 5.3 12GB 档位策略

```
12GB 显存 = Wan 2.2 可用但需节制，优先使用 Q5_K_M
```

| 任务 | 推荐方案 | 配置 | 预估 | 备注 |
|------|------|------|------|------|
| 静态图片 | **SD 1.5 + 2x** | 512x768, 20步, euler | ~40s | 效率最高 |
| 静态图片（复杂） | Wan T2V Q5_K_M | 480x832, 20步, unipc | ~85s | 竖屏原生分辨率 |
| 静态图片（复杂） | Wan T2V Q5_K_M + 2x | 480x832, 20步 + ESRGAN | ~87s | 输出 960x1664 |
| 视频 I2V | Wan I2V Q5_K_M | 480x832, 41帧, 10步 | ~15min | 半时长折中 |
| 视频 T2V | 不推荐 | - | - | T2V 视频质量差 |

**12GB 专有参数**：
```json
{
  "model": "Wan2.2-T2V-A14B-LowNoise-Q5_K_M.gguf",
  "base_precision": "fp16",
  "quantization": "disabled",
  "load_device": "offload_device",
  "force_offload": true,
  "blocks_to_swap": 10,
  "width": 480, "height": 832,
  "steps": 20, "cfg": 5.0, "shift": 8.0,
  "enable_vae_tiling": true,
  "tile_x": 256, "tile_y": 256
}
```

**I2V 12GB 折中**：
```json
{
  "num_frames": 41,
  "steps": 12,
  "width": 480, "height": 832,
  "noise_aug_strength": 0.02,
  "start_latent_strength": 0.85,
  "end_latent_strength": 0.85
}
```

### 5.4 16GB 档位策略

```
16GB 显存 = Wan 2.2 主力档位，大部分任务无压力
```

| 任务 | 推荐方案 | 配置 | 预估 | 备注 |
|------|------|------|------|------|
| 静态图片 | SD 1.5 + 2x | 512x768, 20步, euler | ~40s | 简单任务仍用 SD |
| 静态图片（复杂） | **Wan T2V Q8_0 + 2x** | 832x480, 20步, unipc | ~78s | 输出 1664x960 |
| 视频 I2V | Wan I2V Q5_K_M | 832x480, 81帧, 15步 | ~22min | 标清 5秒 |
| 视频 I2V（轻量） | Wan I2V Q8_0 | 480x832, 41帧, 15步 | ~10min | 半时长竖屏 |

**16GB 推荐模型**：Q8_0 GGUF 或 FP8 safetensors（比 Q5_K_M 质量更好，16GB 足够承载）

```json
{
  "model": "Wan2.2-T2V-A14B-LowNoise-Q8_0.gguf",
  "base_precision": "fp16",
  "quantization": "disabled",
  "load_device": "main_device",
  "force_offload": true,
  "blocks_to_swap": 0,
  "width": 832, "height": 480,
  "steps": 20, "cfg": 5.0, "shift": 8.0
}
```

### 5.5 20GB+ 档位策略（本次实测基准）

```
20GB+ 显存 = Wan 2.2 全速全分辨率，所有任务无限制
```

| 任务 | 模型 | 配置 | 采样速度 | 显存峰值 | 总耗时 |
|------|------|------|------|------|------|
| T2V 单帧 | Wan 2.2 14B Q5_K_M | 832x480, 20步 | 3.3s/it | 10.6 GB | 72-76s |
| T2V 单帧 | Wan 2.2 14B Q5_K_M | 832x480, 25步 | 3.5s/it | 10.8 GB | 91s |
| T2V 单帧 | Wan 2.2 14B BF16 | 832x480, 20步 | ~3.0s/it | ~18 GB | ~65s |
| T2V 单帧 | SD 1.5 | 512x768, 20步 | 0.3s/it | 3.5 GB | ~35s |
| I2V 视频 | Wan 2.2 I2V 14B Q5_K_M | 480x832, 20步, 81帧 | 86s/it | 14.75 GB | ~30min |
| ESRGAN 2x | RealESRGAN | 832x480 -> 1664x960 | N/A | ~1 GB | <1s |

```
                    Wan 2.2 14B 显存负载 (RTX 3080 20GB)
                    =====================================

阶段1: 模型加载      ████████████████████████░░░░░░░░░░░░  ~15.0 GB
阶段2: 采样 (峰值)   ██████████████░░░░░░░░░░░░░░░░░░░░░░  ~10.6 GB
阶段3: VAE 解码      ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ~1.2 GB
阶段4: ESRGAN 放大   ███████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ~3.0 GB (叠加)

缓冲区充足 (20GB 总量)，从未触发 CUDA OOM
```

### 5.6 模型格式选择速查

| 格式 | 扩展名 | 模型大小 | 显存占用 | 质量 | 最低显存 |
|------|------|------|------|------|------|
| BF16 | `.safetensors` | ~28 GB | ~24 GB | 最佳 | 24GB |
| FP16 | `.safetensors` | ~14 GB | ~14 GB | 优秀 | 16GB |
| FP8 | `.fp8.safetensors` | ~7 GB | ~8 GB | 良好 | 12GB |
| Q8_0 GGUF | `.gguf` | ~15 GB | ~10 GB | 良好 | 12GB |
| Q5_K_M GGUF | `.gguf` | ~11 GB | ~8 GB | 可接受 | 10GB |
| Q4_K_M GGUF | `.gguf` | ~9 GB | ~7 GB | 一般 | 8GB |

**模型文件 vs loader 命名对照**：
- `Wan2.2-T2V-A14B-LowNoise-Q5_K_M.gguf` -> `quantization: disabled`
- `Wan2.2-T2V-A14B-LowNoise-Q8_0.gguf` -> `quantization: disabled`
- `Wan2.2-T2V-A14B-LowNoise-fp8_e4m3fn.safetensors` -> 可选 `quantization: fp8`
- `Wan2_1_VAE_bf16.safetensors` -> VAE, `precision: bf16`
- `umt5-xxl-enc-fp8_e4m3fn.safetensors` -> T5 编码器（**非scaled版**）

### 5.7 跨档位通用决策树

```
用户请求
│
├─ 静态图片
│  ├─ 提示词简单 (<200 tokens)
│  │  └─ 任意档位 -> SD 1.5 @ 512x768, 20步, euler -> ~35秒 -> [可选: 2x] ✅
│  │
│  └─ 提示词复杂 (200+ tokens)
│     ├─ 8GB  -> Wan Q4_K_M @ 480x480, 18步 -> ~90秒 -> [2x -> 960x960]
│     ├─ 12GB -> Wan Q5_K_M @ 480x832, 20步 -> ~85秒 -> [2x -> 960x1664]
│     ├─ 16GB -> Wan Q8_0  @ 832x480, 20步 -> ~78秒 -> [2x -> 1664x960] ★
│     └─ 20GB+-> Wan BF16  @ 832x480, 20步 -> ~65秒 -> [2x -> 1664x960] ★
│
└─ 视频 I2V
   ├─ 8GB  -> 不可用，建议云端
   ├─ 12GB -> Wan Q5_K_M @ 480x832, 41帧, 12步 -> ~15min
   ├─ 16GB -> Wan Q5_K_M @ 832x480, 81帧, 15步 -> ~22min
   └─ 20GB+-> Wan Q5_K_M @ 832x480, 81帧, 15步 -> ~22min
```

---

## 6. 错误模式与解决方案

### 6.1 HTTP API 交互错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `HTTP 400: Bad Request` | 工作流 JSON 格式错误或缺少必需字段 | 检查 `class_type` 拼写、连接数组格式 |
| `HTTP 400: prompt_outputs_failed_validation` | 某个节点的必需参数缺失 | 查看返回体的 `node_errors` 字段定位 |
| 提交后无响应 | 端口错误 / 服务器未运行 | `curl system_stats` 确认 |

### 6.2 节点参数错误

| 错误信息 | 根因 | 修复 |
|------|------|------|
| `WanVideoVAELoader.loadmodel() missing argument 'precision'` | VAE loader 缺少 precision 参数 | 添加 `"precision": "bf16"` |
| `WanVideoDecode missing tile_x/y/stride_x/y` | VAE decode 必须显式传 tile 参数 | 即使 tiling=false 也传齐四个 tile 参数 |
| `Invalid T5 text encoder model, fp8 scaled not supported` | 使用了 scaled 版 T5 编码器 | 换用 `umt5-xxl-enc-fp8_e4m3fn.safetensors` |
| `Quantization should be disabled when loading GGUF models` | GGUF 模型设置了非 disabled 的量化 | 设为 `"quantization": "disabled"` |

### 6.3 连接类型不匹配

| 场景 | 错误连接 | 正确连接 |
|------|------|------|
| Wan 采样器接入 | `ModelSamplingSD3 -> WanVideoSampler` | `WanVideoModelLoader -> WanVideoSampler` |
| VAE 接入 | `KSampler -> VAE` | `WanVideoSampler -> WanVideoDecode` |

### 6.4 输出文件找不到

| 症状 | 可能原因 | 验证方法 |
|------|------|------|
| `/history/{id}` 返回空 | 服务器重启清除了内存 history | 直接检查输出目录 |
| 输出目录无文件 | SaveImage 节点的 `filename_prefix` 拼写错误 | 在工作流 JSON 中确认 |
| glob 工具返回空但文件存在 | 工具缓存问题 | 改用 `dir` / `list_directory` |

---

## 7. 监控与调试模式

### 7.1 本次建立的监控模式

在整个会话中建立了三层监控：

**Layer 1: Python HTTP 轮询**（用于 T2V，<3分钟任务）
```python
while time.time() < deadline:
    r = urllib.request.urlopen(f'http://127.0.0.1:3198/history/{pid}')
    h = json.loads(r.read())
    if h.get(pid, {}).get('status', {}).get('completed'):
        # done
    elif status == 'error':
        # failed
    time.sleep(3)
```

**Layer 2: 服务器 stdout 观察**（用于 I2V，30分钟任务）
```python
# 通过 run_background + wait_for_job + job_output 读取服务器日志
# 可以看到 tqdm 进度条 (tqdm 输出到 stdout):
#   5%|         | 1/20 [00:03<01:05,  3.43s/it]
#   100%|██████████| 20/20 [01:06<00:00,  3.33s/it]
```

**Layer 3: 直接文件检查**（兜底）
```bash
dir D:\2026-ComfyUI-V8.3\output\mecha_girl_v3*
```

### 7.2 建议新增的监控 API

在 `/history/{id}` 不稳定的情况下，以下 API 应优先增强：

- `/queue` -- 当前运行/排队任务（已验证稳定）
- `/system_stats` -- 服务器存活检测
- `/prompt` 返回体中的 `node_errors` 字段 -- 提交时即可发现错误

---

## 8. 后续升级建议

### 8.1 高优先级

#### 8.1.1 添加 `--auto-upscale` 标志

在 `scripts/edit_workflow.py` 和工作流生成逻辑中增加自动插入放大器节点：

```python
def add_upscale_chain(workflow: dict, upscale_model: str = "RealESRGAN_x2.pth") -> dict:
    """在 VAE decode 和 Save 之间自动插入 UpscaleModelLoader + ImageUpscaleWithModel"""
    # 找到 SaveImage 节点 -> 插入两个新节点 -> 重连
    # 这样用户只需加 --auto-upscale 即可获得 2x 输出
```

#### 8.1.2 实现任务 JSON 模板系统

15+ 个手写 JSON 文件难以维护。应建立参数化模板：

```json
{
  "template": "wan_t2v_default",
  "params": {
    "positive_prompt": "...",
    "seed": 420420420,
    "width": 832,
    "height": 480,
    "steps": 20,
    "filename_prefix": "mecha_girl_v3"
  }
}
```

运行时展开为完整工作流 JSON。

#### 8.1.3 集成硬件检测自动参数选择

在 `scripts/start_server.py` 或一个新的 `auto_config.py` 中添加：

```python
gpu_mem = torch.cuda.get_device_properties(0).total_mem / (1024**3)
if gpu_mem >= 20:
    default_steps = 20
    default_resolution = (832, 480)
    default_model = "Wan2.2-T2V-A14B-LowNoise-Q5_K_M.gguf"
elif gpu_mem >= 12:
    default_steps = 15
    default_resolution = (480, 832)
    default_model = "Wan2.2-T2V-A14B-LowNoise-Q8_0.gguf"
```

#### 8.1.4 修复已知 Python 包冲突

以下文件重命名工作应编码为安装脚本的一部分：
- `cli/typing.py` -> `cli/typing_compat.py`（与标准库 typing 冲突）
- `cli/logging.py` -> `cli/logging_utils.py`（与标准库 logging 冲突）

### 8.2 中优先级

#### 8.2.1 添加原生放大器节点支持到 `edit_workflow.py`

当前 `edit_workflow.py` 支持的编辑项：提示词、seed、分辨率、步数、cfg、模型名。应新增：
- `--upscale 2x` -- 自动插入 RealESRGAN 2x 节点链
- `--upscale-model RealESRGAN_x2.pth` -- 指定放大模型

#### 8.2.2 服务器稳定性改进

- **历史持久化**：当前 `/history` 在服务器重启后丢失。应在重启脚本中预先备份历史输出路径
- **自动健康检查**：每个任务提交后自动验证服务器是否存活，若死亡则自动重启
- **输出目录定期清理提醒**：当前 `output/` 目录有 50+ 文件，应建议用户定期归档

#### 8.2.3 添加进度 WebSocket 备选

当 WebSocket 不可用时（如 AI Agent 环境），应提供轮询进度的替代方案。当前 `/history` API 在运行中不返回进度----需补充：

```
GET /progress/{prompt_id}
-> {"step": 7, "total_steps": 20, "percent": 35}
```

### 8.3 低优先级

#### 8.3.1 建立"已知良好的工作流"黄金测试集

从本次 15+ 个 JSON 中提取稳定工作的模板，作为回归测试基准：

| 模板 | 用途 | 验证标准 |
|------|------|------|
| `wan_t2v_832x480_20s` | Wan T2V 标准 | 70-80秒内生成 1664x960 PNG |
| `wan_i2v_480x832_15s` | Wan I2V 标准 | 20-25分钟内生成 5秒 mp4 |
| `sd15_512x768_20s` | SD 1.5 快速 | 35秒内生成 PNG |
| `esrgan_2x_upscale` | 放大后处理 | 放大耗时 < 1秒 |

#### 8.3.2 完善 prompt 翻译层

Wan 2.2 的 T5-XXL 编码器对英文响应远好于中文。当前采用手动翻译。可考虑：
- 在 `scripts/edit_workflow.py` 中添加 `--translate` 标志
- 或在工作流构建时自动检测 prompt 语言并调用翻译

#### 8.3.3 添加 GPU 显存使用率仪表盘

在 `scripts/check_status.py` 中增加实时显存报告：
```
Model: Wan2.2-T2V-A14B-LowNoise-Q5_K_M.gguf
VRAM: 10.6 GB used / 20.0 GB total (53%)
Safety margin: 9.4 GB available
Estimated max concurrent tasks: 1
```

---

## 附录 A：已验证的 Wan 2.2 T2V 最小工作流模板

```json
{
  "1": {"class_type":"WanVideoModelLoader","inputs":{"model":"Wan2.2-T2V-A14B-LowNoise-Q5_K_M.gguf","base_precision":"fp16","quantization":"disabled","load_device":"main_device"}},
  "2": {"class_type":"WanVideoVAELoader","inputs":{"model_name":"Wan2_1_VAE_bf16.safetensors","precision":"bf16"}},
  "3": {"class_type":"LoadWanVideoT5TextEncoder","inputs":{"model_name":"umt5-xxl-enc-fp8_e4m3fn.safetensors","precision":"bf16"}},
  "4": {"class_type":"WanVideoTextEncode","inputs":{"positive_prompt":"PROMPT","negative_prompt":"NEGATIVE","t5":["3",0]}},
  "5": {"class_type":"WanVideoEmptyEmbeds","inputs":{"width":832,"height":480,"num_frames":1}},
  "6": {"class_type":"WanVideoSampler","inputs":{"model":["1",0],"image_embeds":["5",0],"text_embeds":["4",0],"steps":20,"cfg":5.0,"shift":8.0,"seed":0,"force_offload":true,"scheduler":"unipc","riflex_freq_index":0}},
  "7": {"class_type":"WanVideoDecode","inputs":{"vae":["2",0],"samples":["6",0],"enable_vae_tiling":true,"tile_x":256,"tile_y":256,"tile_stride_x":128,"tile_stride_y":128}},
  "8": {"class_type":"SaveImage","inputs":{"filename_prefix":"output","images":["7",0]}}
}
```

## 附录 B：已学到的教训清单

1. **不要降原生分辨率来加速** -- 细节损失 ESRGAN 无法恢复
2. **减步数的下限** -- Wan T2V ≥ 18 步，I2V ≥ 10 步，低于此质量崩溃
3. **euler 调度器不适合 Wan** -- unipc 是唯一稳定选择
4. **T5 编码器选非 scaled 版本** -- scaled 版 WanVideoWrapper 不接受
5. **VAE tile 参数必须显式传递** -- 即使关闭 tiling
6. **GGUF 模型 quantization 必须设 disabled** -- 否则双重量化冲突
7. **服务器历史记录不稳定** -- 不要依赖 `/history` API 做唯一验证源
8. **2x 放大器几乎零成本** -- 对 Wan 输出总是有益无害
9. **I2V 视频 81 帧在 20GB 上可行** -- 但需要 22-30 分钟
10. **SD 1.5 不应被忽略** -- 简单提示词用 SD 1.5 比 Wan 快 2x

---

*此文档将作为后续升级 comfyui-controller 项目的核心参考。每次发现新的参数规律、错误模式或优化手段，均应更新本文档。*
