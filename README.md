# ComfyUI Omni-Controller SKILL

**任何智能体都可使用的 ComfyUI 自动化控制工具** —— 用户通过自然语言描述需求，智能体即可自动生成图文、视频的复杂工作流并执行生成。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

***

## 项目简介

本项目是 ComfyUI 的全能命令行与自动化控制工具，核心价值在于**让智能体接管 ComfyUI 的全部操作**：从环境检查、模型选择、工作流构建到任务执行，用户只需用自然语言描述想要的图片或视频，智能体即可完成全部复杂流程。

项目融合了两套成熟体系：

- **脚本控制层**：基于 Python 的 ComfyUI 工作流执行引擎，擅长自动化任务和 AI Agent 调用

- **CLI 管理层**：基于官方 comfy-cli 的完整生命周期管理（安装/启动/节点/模型/依赖编译）

两层共享同一套配置、同一工作空间、同一 ComfyUI 实例，数据完全互通。

### 为什么选择本项目

- **自然语言驱动**：用户说"生成一个女孩微笑的视频"，智能体自动完成预检、选模型、构建工作流、执行

- **强制预检反问**：任何生成任务前，智能体都会完成服务可用性、模型匹配、节点完整性、硬件检测、参数确认五项检查

- **工业级视频架构**：SVI Pro 分段生成 + HIGH+LOW 双阶段串行 + Flux2 图片修正，支持 6 种视频任务类型

- **跨系列模型隔离**：自动识别模型系列（Wan2.2/Flux/SD1.5/SDXL），禁止跨系列混用组件

- **硬件自适应**：性能参数根据 GPU VRAM 分四档智能调整，质量优先（L4≥24GB / L3 16-24GB / L2 12-16GB / L1 8-12GB）

- **工作流仓库**：自动扫描、分析、分类工作流，提取模式供新任务复用

***

## ComfyUI 启动与工作流执行（必读）

> **重要**：本项目严格遵循 **ComfyUI 官方标准启动方式**，**不依赖、也不要求任何第三方 GUI 启动器**（如 wangyi AI绘世启动器.exe、秋叶整合包等 Windows 专属工具）。在任何操作系统（Windows / Linux / macOS）上，都请按以下官方标准方式启动与执行，切勿使用第三方启动器。

### 1. 启动 ComfyUI（官方标准）

在 **ComfyUI 安装目录**（`${COMFYUI_PATH}`）下，使用官方 `main.py` 启动：

```bash
# Windows（嵌入式 Python 独立版）
cd ${COMFYUI_PATH}
.\python\python.exe -u main.py --port 3198 --listen 127.0.0.1

# Linux / macOS（标准 Python 安装，官方标准方式）
cd ${COMFYUI_PATH}
python main.py --listen 127.0.0.1 --port 3198
```

> - `${COMFYUI_PATH}` 通过环境变量 `COMFYUI_PATH` 指定；默认端口 `3198`（通过 `COMFYUI_PORT` 配置）
> - 若 ComfyUI 已安装为独立 venv，则使用 `venv/bin/python main.py`（Linux/macOS）或 `venv\Scripts\python.exe main.py`（Windows）
> - 也可使用本项目内置 CLI 后台启动：`comfy launch --background`（前台：`comfy launch`），停止：`comfy stop`

### 2. 执行工作流（两种方式，等价）

```bash
# 方式一：内置 CLI（推荐，UI/API 双格式自动转换 + NDJSON 结构化输出）
comfy run --workflow workflow.json --json --wait

# 方式二：脚本模式
python scripts/run_workflow.py --workflow workflow.json --wait --timeout 600
```

> - `comfy run` 同时接受 ComfyUI **API 格式**与 **UI 格式**工作流 JSON，UI 格式会自动转换后提交
> - 执行前请先确认服务可用：`GET http://127.0.0.1:3198/system_stats` 返回 200

### 3. 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `COMFYUI_PATH` | ComfyUI 安装目录 | 无（必填） |
| `COMFYUI_HOST` | ComfyUI 服务地址 | `127.0.0.1` |
| `COMFYUI_PORT` | ComfyUI 服务端口 | `3198` |

***

## 功能模块

### 智能体预检与反问

任何生成任务前的强制检查环节，确保任务可执行且参数合理。

- **5 项强制检查**：ComfyUI 服务可用性 / 模型按系列分组展示与选择 / 节点完整性 / 硬件检测与参数反问 / 提示词结构化校验

- **强制反问参数**：画面比例、分辨率、优化程度（步数），即使用户提供完整提示词也不可跳过

- **参数汇总确认**：反问完成后向用户展示最终参数，确认后才执行

- **硬件自适应推荐**：基于 GPU VRAM 分四档（L4 专业级≥24GB / L3 高性能 16-24GB / L2 标准级 12-16GB / L1 入门级 8-12GB），质量优先

### 图片生成

支持多种模型系列的文生图任务，智能体自动选择正确的架构。

- **Flux 2 架构**：F2K-9b-kleinova + Qwen3-8B 文本编码器（12288 维）+ SamplerCustomAdvanced + Flux2Scheduler

- **Flux 1 架构**：DualCLIPLoader（clip\_l + t5xxl）+ CLIPTextEncodeFlux + ModelSamplingFlux

- **SD1.5 / SDXL 架构**：CheckpointLoaderSimple + CLIPTextEncode + KSampler

- **提示词工程**：自动将用户白话中文转换为结构化英文提示词（主体+镜头+场景+画质四要素）

- **标准负面提示词模板**：内置通用负面项，防止变形、低质量、水印等问题

### 视频生成（工业级六阶段架构）

严格遵循 lc.txt 工业级标准，强制预检不可跳过。

- **多架构支持**：SVI Pro 分段生成（长视频）/ 单段 HIGH+LOW 双阶段（短视频）/ 单一模型（测试）

- **6 种视频任务类型**：图生视频 / 首尾帧 / 多图视频 / 长视频 / 视频拼接 / 多参考图视频

- **段间连贯性**：latent 级转移 + ImageBatchExtendWithOverlap + Flux2 图片修正

- **专用节点校验**：WanVideoSampler / VHS\_VideoCombine / RIFE VFI / Deflicker

### 工作流仓库与智能设计

从已有工作流中学习模式，自动设计新工作流。

- **工作流资源库**：自动扫描目录、深度分析节点结构、智能分类（文生图/图生视频等）、模板提取

- **节点功能注释**：自动提取每个节点的 display\_name / description / category，生成可读的执行流程

- **执行流程梳理**：基于拓扑排序输出节点执行顺序，检测循环依赖

- **增量更新**：仅重新分析新增/修改的工作流，避免全量重建

- **模式提取器**：按 (任务类别, 模型系列) 严格分组，提取典型节点序列、参数分布、模型组合

- **智能工作流组装**：

  - 优先从模式库查找匹配的 (任务类别, 模型系列) 模式

  - 无完全匹配时借用中立节点（SaveImage 等），模型相关节点必须同系列

  - 完全无模式时回退到内置基础架构，按目标模型系列分派

  - 强制 model\_family 一致性校验，防止跨系列混用

- **仓库查询 CLI**：按类别 / 模型系列 / 节点类型 / 模型名 / 统计 / 列表 多维过滤

### ComfyUI 生命周期管理

完整的安装、启动、停止、环境检查能力。

- **安装管理**：支持 GPU/CPU/版本/PR 指定，自动检测 GPU 类型

- **服务器控制**：前台/后台启动，端口自定义，就绪等待

- **环境检查**：Python/PyTorch/CUDA/GPU/节点/模型/服务器状态全面检查

- **更新管理**：ComfyUI 与自定义节点一键更新

### 节点与模型管理

- **自定义节点**：安装/卸载/更新/启用/禁用/修复依赖

- **快照管理**：保存/恢复环境状态

- **问题排查**：二分查找问题节点

- **模型下载**：支持 HuggingFace / CivitAI / 普通 URL，自动识别模型类型

- **智能模型匹配**：忽略量化后缀（fp8/fp16/Q5\_K\_M 等），置信度≥85% 自动替换

- **依赖分析**：从工作流提取依赖并批量安装

### 依赖编译

- **uv 批量解析**：使用 uv pip compile 极速解析依赖

- **GPU 自动检测**：自动选择正确的 PyTorch 索引

- **冲突处理**：核心 + 扩展依赖冲突自动处理，OpenCV gui/headless 冲突自动解决

- **独立环境打包**：支持打包独立 Python 环境

### 工作流执行引擎

- **双格式支持**：API 格式直接执行，UI 格式自动转换

- **WebSocket 实时监听**：节点开始/进度/完成/错误全事件推送

- **NDJSON 结构化输出**：9 种事件类型，适合智能体解析

- **超时控制与错误分类**：17 种错误分类，OOM 分级处理策略

### 云端生成（Partner Nodes）

- 文生图/图生图（Flux/DALL-E/Ideogram 等）

- 模型浏览与参数查看

- 本地图片上传

- 异步任务恢复

***

## 使用方法

本项目支持两种使用方式，可根据场景选择或组合使用。

### 方式一：作为 Skill 使用

适用于 Trae IDE 等 AI Agent 环境，智能体自动读取技能文档并执行任务。

1. **安装技能**：将项目放入工作区，智能体会自动识别 `.trae/skills/` 下的技能文档

   - `comfyui-controller`：ComfyUI 全能控制器（技能入口，完整功能映射）→ `comfyui-controller/.trae/skills/comfyui-controller/SKILL.md`

   - `image-task-execution-guide`：图片生成任务执行指南（5 项预检 + Flux 2 架构经验）

   - `video-task-execution-guide`：视频生成任务执行指南（6 项预检 + 六阶段架构）

2. **自然语言驱动**：直接用自然语言描述需求，例如：

   - "生成一张年轻女子的室内人像摄影，35mm 镜头，暖色调"

   - "用这张图片生成一个 5 秒的微笑视频"

   - "检查 ComfyUI 环境状态"

3. **智能体自动执行**：智能体读取技能文档后，自动完成预检反问 → 模型选择 → 工作流构建 → 提交执行 → 结果交付

4. **快速检索经验文档**：智能体先查 `comfyui-controller/docs_cli/INDEX.md`（主题速查 + 章节行号导航），再按需读取 EXPERIENCE.md / 采样器手册 / 双实例调参手册

### 方式二：作为插件安装

适用于命令行环境，提供完整的 ComfyUI 生命周期管理。

1. **手动安装**：

   ```bash
   git clone https://github.com/liuda1999/ComfyUI-Omni-Controller-SKILL.git
   cd ComfyUI-Omni-Controller-SKILL/comfyui-controller
   pip install -e cli/
   ```

2. **智能体自动安装**：智能体可通过技能文档中的安装指引，自动执行克隆、依赖安装、环境配置全流程

3. **安装后即可使用**：智能体既可通过技能模式调用 Python 脚本，也可通过 CLI 命令管理 ComfyUI

### 两种方式的关系

- **Skill 模式**：面向 AI Agent，自然语言驱动，自动预检反问，适合图片/视频生成任务

- **插件模式**：面向命令行，完整生命周期管理，适合环境部署、节点管理、模型下载

- 两种模式共享同一套配置和工作空间，可混合使用

***

## 技术文档

项目内置完整的技术经验文档，供智能体执行任务时参考：

- `comfyui-controller/docs_cli/INDEX.md` — **全量经验/技术文档快速索引**（主题速查 + 章节行号导航，推荐入口）

- `.trae/skills/` — 技能文档（智能体读取入口，含预检指南和架构经验）

- `.trae/specs/` — 规格文档（任务规划、检查清单、验收标准）

- `comfyui-controller/SKILL.md` — 完整功能映射表和 ComfyUI 工作流知识库

- `comfyui-controller/docs_cli/EXPERIENCE.md` — 24 章迭代经验与问题排查记录

- `comfyui-controller/SKILL.md §4.19` — K 采样器完全参考手册（ComfyUI 全家族，独立章节）

- `comfyui-controller/docs_cli/wan22_dual_instance_tuning_guide.md` — Wan2.2 双实例视频生成调参手册

- `comfyui-controller/scripts/` — 核心脚本模块（预检、构建、执行、分析）

***

## 环境要求

- Python 3.10+

- Git

- CUDA 12.x（推荐，用于 GPU 加速）

- GPU VRAM ≥ 6GB（图片生成）/ ≥ 8GB（视频生成）

***

## 许可证

本项目采用 [Apache-2.0](LICENSE) 许可证。项目融合了 `comfy-cli`（ComfyUI 官方 CLI）和 `comfyui-controller`（社区自动化工具）的功能，相关代码遵循其原始许可证，融合后的架构文档为原创内容。

## 致谢

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) — 强大的节点式 Stable Diffusion 界面

- [comfy-cli](https://github.com/Comfy-Org/comfy-cli) — ComfyUI 官方命令行工具

- [uv](https://github.com/astral-sh/uv) — 极速 Python 包管理器

