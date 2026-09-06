# ComfyUI Omni-Controller

ComfyUI 全能控制器 —— 一站式 ComfyUI 命令行与自动化控制工具。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

## 目录

- [项目简介](#项目简介)
- [功能总览](#功能总览)
- [安装](#安装)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
  - [服务器控制](#服务器控制)
  - [工作流执行](#工作流执行)
  - [工作流编辑](#工作流编辑)
  - [模型管理](#模型管理)
  - [节点与依赖管理](#节点与依赖管理)
  - [工作流分析与生成](#工作流分析与生成)
  - [视频生成](#视频生成)
- [核心功能详解](#核心功能详解)
- [配置管理](#配置管理)
- [错误处理与故障排除](#错误处理与故障排除)
- [开发指南](#开发指南)
- [测试](#测试)
- [文档](#文档)
- [作者与社区](#作者与社区)
- [许可证](#许可证)

---

## 项目简介

ComfyUI Omni-Controller 是 ComfyUI 生态中最全面的命令行与自动化控制工具，提供从安装、配置、工作流执行到节点管理的完整生命周期支持。

### 项目总结

本项目旨在解决 ComfyUI 用户在以下场景中的痛点：

1. **自动化执行**：通过脚本批量执行工作流，无需手动操作 Web 界面
2. **环境管理**：一键检查 Python、PyTorch、CUDA、GPU 等环境状态
3. **工作流智能处理**：格式转换、参数编辑、依赖分析、自动修复
4. **模型智能匹配**：本地模型扫描、相似模型推荐、量化后缀忽略
5. **工作流生成与重组**：基于自然语言描述从零组装工作流，支持 LoRA、ControlNet、放大链等复杂结构
6. **资源库管理**：持续扩展的工作流资源库，支持深度学习和结构分析

项目采用双模式设计：
- **脚本模式**：基于 Python 脚本，适合自动化任务和 AI Agent 调用
- **CLI 模式**：基于 `typer` 框架，适合手动管理和交互式操作

两种模式共享同一套配置、同一工作空间、同一 ComfyUI 实例，数据完全互通。

---

## 功能总览

### 生命周期管理
- [x] ComfyUI 安装（GPU/CPU/版本/PR 指定）
- [x] 服务器启动（前台/后台）
- [x] 服务器停止
- [x] 环境检查（Python/PyTorch/CUDA/GPU/节点/模型）
- [x] 更新管理（ComfyUI/节点）

### 工作流执行
- [x] API 格式工作流执行
- [x] UI 格式工作流自动转换执行
- [x] WebSocket 实时进度监听
- [x] NDJSON 结构化输出（CLI 模式）
- [x] 超时控制与错误分类
- [x] 工作流参数编辑（提示词/分辨率/种子/步数/CFG/模型）

### 工作流分析与生成
- [x] 深度分析工作流结构（节点功能、参数、连接关系）
- [x] 工作流资源库构建（自动扫描、分类、统计）
- [x] 基于自然语言生成工作流（文生图/图生图/文生视频/放大等）
- [x] 复杂结构组装（LoRA 叠加、ControlNet、放大链、高清修复、多采样器串联）
- [x] 自动拓扑排序和连接布线
- [x] 工作流模板提取与复用

### 视频生成
- [x] 多架构支持（SVI Pro 长视频分段生成 / 单段 I2V / 图生视频 / 首尾帧）
- [x] 动态架构选择（方案A: HIGH+LOW 双采集器串行 / 方案B: 单一模型，不写死）
- [x] 强制预检反问环节（模型选择→架构方案→参数收集→硬件校验，不可跳过）
- [x] 视频专用节点完整性校验（WanVideo I2V Sampler/FaceDetailer/VHS_VideoCombine/RIFE VFI/Deflicker）
- [x] 6种视频任务类型（img2vid/first_last_frame/multi_image_video/long_video/video_concat/multi_ref_video）
- [x] 段间连贯性保障（Flux2 图片修正 + SVI Pro anchor_samples + prev_samples 传递）

### 节点与模型管理
- [x] 自定义节点安装/卸载/更新/启用/禁用
- [x] 模型下载（HuggingFace / CivitAI / URL）
- [x] 智能模型匹配（忽略量化后缀）
- [x] 依赖分析与自动修复
- [x] 环境快照保存/恢复
- [x] 从工作流提取依赖并安装
- [x] 节点发布到 Registry
- [x] 节点打包与项目脚手架
- [x] 问题节点二分查找

### 依赖编译
- [x] `uv pip compile` 批量解析
- [x] GPU 类型自动检测
- [x] 核心 + 扩展依赖冲突处理
- [x] OpenCV 冲突自动处理
- [x] 独立 Python 环境打包

### 云端生成（Partner Nodes）
- [x] 文生图/图生图（Flux/DALL-E/Ideogram 等）
- [x] 模型浏览与参数查看
- [x] 本地图片上传
- [x] 异步任务恢复

---

## 安装

### 前提条件
- Python 3.10+
- Git
- CUDA 12.x（推荐，用于 GPU 加速）

### 安装步骤

```bash
# 克隆仓库
git clone https://github.com/liuda1999/ComfyUI-Omni-Controller-SKILL.git
cd ComfyUI-Omni-Controller-SKILL

# 进入控制器目录
cd comfyui-controller

# 安装依赖
pip install -r requirements.txt

# 或者使用 uv（推荐）
uv pip install -r requirements.txt

# 安装 CLI 模式（可选）
pip install -e cli/
```

### 环境变量配置

```bash
# Windows
set COMFYUI_PATH=D:\ComfyUI
set COMFYUI_HOST=127.0.0.1
set COMFYUI_PORT=3198

# Linux/Mac
export COMFYUI_PATH=/home/user/ComfyUI
export COMFYUI_HOST=127.0.0.1
export COMFYUI_PORT=3198
```

---

## 快速开始

> **重要**：本项目严格遵循 **ComfyUI 官方标准启动方式**（`python main.py` 或内置 CLI `comfy launch`），**不依赖任何第三方 GUI 启动器**（如 wangyi AI绘世启动器.exe、秋叶整合包等 Windows 专属工具）。在 Windows / Linux / macOS 上均按官方标准方式启动，切勿使用第三方启动器。

### 1. 环境检查

```bash
# 脚本模式
python scripts/check_status.py

# CLI 模式
comfy env
```

### 2. 安装 ComfyUI

```bash
# CLI 模式（推荐首次安装）
comfy install --gpu --fast-deps

# 或者脚本模式
python scripts/start_server.py --install --port 3198
```

### 3. 启动服务器

> **官方标准启动**（在 ComfyUI 安装目录下）：
>
> ```bash
> # Windows（嵌入式 Python 独立版）
> cd ${COMFYUI_PATH}
> .\python\python.exe -u main.py --port 3198 --listen 127.0.0.1
>
> # Linux / macOS（标准 Python 安装）
> cd ${COMFYUI_PATH}
> python main.py --listen 127.0.0.1 --port 3198
> ```

```bash
# CLI 模式（后台，等价于官方 `python main.py` 启动）
comfy launch --background

# 脚本模式（前台）
python scripts/start_server.py --port 3198
```

### 4. 执行工作流

```bash
# 脚本模式
python scripts/run_workflow.py --workflow workflow.json --wait --timeout 600

# CLI 模式
comfy run workflow.json --json
```

### 5. 停止服务器

```bash
# CLI 模式
comfy stop

# 脚本模式
python scripts/controller.py stop
```

---

## 使用指南

### 服务器控制

```bash
# 检查服务器状态
python scripts/controller.py status

# 启动服务器
python scripts/start_server.py --port 3198

# 停止服务器
python scripts/controller.py stop

# 等待服务器就绪
python scripts/controller.py wait --timeout 120
```

### 工作流执行

```bash
# 执行 API 格式工作流
python scripts/run_workflow.py --workflow api_workflow.json --wait

# 转换并执行 UI 格式工作流
python scripts/workflow_converter.py --input ui_workflow.json --output api_workflow.json
python scripts/run_workflow.py --workflow api_workflow.json --wait

# 带超时和自定义输出目录
python scripts/run_workflow.py --workflow workflow.json --wait --timeout 900 --output-dir ./my_output
```

### 工作流编辑

```bash
# 修改提示词和分辨率
python scripts/edit_workflow.py \
  --input workflow.json \
  --output edited.json \
  --positive-prompt "a beautiful sunset over mountains" \
  --width 1920 --height 1080 \
  --steps 30 --cfg 7.5 \
  --random-seed
```

### 模型管理

```bash
# 查询可用模型
python scripts/get_available_models.py --search "wan" --type checkpoints

# 下载模型
python scripts/download_models.py \
  --base ~/ComfyUI \
  "https://huggingface.co/.../model.safetensors" \
  "https://civitai.com/api/download/models/12345 loras"

# 分析工作流依赖
python scripts/dependency_manager.py --workflow workflow.json

# 自动修复依赖
python scripts/dependency_manager.py --workflow workflow.json --fix --output fixed.json
```

### 节点与依赖管理

```bash
# 安装节点
comfy node install comfyui-manager

# 使用 uv 编译安装
comfy node install comfyui-manager --uv-compile

# 更新所有节点
comfy node update all

# 保存快照
comfy node save-snapshot snapshot.json

# 恢复快照
comfy node restore-snapshot snapshot.json

# 二分查找问题节点
comfy node bisect
```

### 工作流分析与生成

```bash
# 深度分析工作流结构
python scripts/workflow_analyzer.py --workflow workflow.json --output analysis.json

# 构建工作流资源库
python scripts/build_workflow_library.py --input assets --output assets/workflow_library.json

# 基于自然语言生成工作流
python scripts/advanced_workflow_builder.py \
  --requirement "文生图，高质量，动漫风格，添加LoRA，分辨率512x768" \
  --output generated_workflow.json

# 根据任务描述查询资源库并生成建议
python scripts/workflow_generator.py \
  --task "生成一个文生视频工作流" \
  --check-deps \
  --output suggestion.json
```

### 视频生成

视频生成预检反问环节强制不可跳过。

#### 一键执行视频任务

```bash
# 执行视频生成任务（自动走预检→节点校验→工作流生成→执行全流程）
python scripts/video_task_runner.py --task img2vid --image input.png --prompt "a girl smiling"

# 支持的任务类型: img2vid / first_last_frame / multi_image_video / long_video / video_concat / multi_ref_video
```

#### 核心架构

| 架构 | 适用场景 | 核心机制 |
|------|---------|---------|
| **SVI Pro 分段生成** | 长视频（5秒+） | 段间 latent 级连贯转移 + ImageBatchExtendWithOverlap(5帧overlap线性混合) + Flux2图片修正传递 |
| **单段 HIGH+LOW 双阶段** | 短视频（3-5秒） | HIGH主结构(start_step=0) → LOW细化(start_step=split_step)，dpm++_sde, shift=8.0, 动态CFG |
| **单一模型** | 简单场景/测试 | 单次采样，快速验证 |

#### 段间连贯性（SVI Pro v12 验证）

- anchor_samples：每段锁定首帧VAE编码，维持角色外观一致性
- prev_samples：前段末帧VAE编码传递（非整段latent），避免累积误差
- motion_latent_count=0（段2+）：避免anchor与motion拼接导致暗→亮渐变
- Flux2修正工作流：ReferenceLatent单图(B图)注入 + denoise=0.5 + steps=32

#### 预检反问环节（强制不可跳过）

执行任何视频任务前，`scripts/pre_task_inquiry.py` 强制执行四步预检：

1. **模型查询展示**：通过 `/object_info` API 查询可用模型，按系列分组展示供用户选择
2. **架构方案选择**：让用户选择方案A（双采集器串行）或方案B（单一模型），默认推荐方案A
3. **生成参数收集**：画面比例、分辨率、优化步数、正负面提示词
4. **硬件兼容性检查**：查询 GPU VRAM/RAM，方案A显存需求×2，不足时**终止任务**

```bash
# 单独运行预检环节
python scripts/pre_task_inquiry.py
```

#### 关键设计原则

- **工作流架构根据情况和模型动态决定，不写死**（方案A生产/方案B简单场景）
- 使用 WanVideoSampler 替代 KSampler（后者缺 motion_scale/noise_aug 控制导致模糊噪点）
- 使用 VHS_VideoCombine 替代 CreateVideo+SaveVideo（支持 crf=18 高质量编码）
- SVI Pro 现实人物：HIGH链路用 high_lighting 模型+HIGH_lora，LOW链路用 LOW_fp8 模型+LOW_lora（不可混用）
- 段间画面传递：prev_samples使用前段末帧VAE编码（非整段latent），避免累积误差
- 文本提示词只写动作，不写主体外观（主体由anchor_samples锁定）
- 质量优先于速度：宁可增加生成时间也不产出低质量内容

---

## 核心功能详解

### 工作流格式转换

ComfyUI 有两种工作流格式：
- **UI 格式**：包含 `nodes` 和 `links`，用于前端展示
- **API 格式**：包含 `class_type` 和 `inputs`，用于后端执行

两种模式都支持自动转换：
- 脚本模式：`scripts/workflow_converter.py`
- CLI 模式：`comfy run` 自动检测并转换

### 智能模型匹配

依赖管理器支持智能模型匹配：
1. 精确匹配
2. 忽略大小写匹配
3. 忽略量化后缀匹配（`fp8`, `fp16`, `Q5_K_M` 等）
4. 关键词匹配

置信度阈值：
- `>= 85%`：自动替换
- `50-85%`：警告提示
- `< 50%`：视为缺失

### WebSocket 实时监听

工作流执行时通过 WebSocket 连接 ComfyUI 服务器，实时接收：
- 节点开始执行
- 执行进度（百分比）
- 节点执行完成
- 最终完成或错误

### NDJSON 结构化输出

CLI 模式的 `--json` 标志输出 NDJSON（Newline Delimited JSON），适合自动化代理解析：

```json
{"event": "converted", "data": {"original_format": "ui"}}
{"event": "prompt_preview", "data": {"node_count": 10}}
{"event": "queued", "data": {"prompt_id": "abc123"}}
{"event": "node_executing", "data": {"node": "KSampler", "node_id": "7"}}
{"event": "node_progress", "data": {"node": "KSampler", "progress": 0.5}}
{"event": "node_executed", "data": {"node": "KSampler", "output": [...]}}
{"event": "completed", "data": {"outputs": [...]}}
```

### UV 依赖编译

`uv` 是一个极速 Python 包管理器。依赖编译器：
- 使用 `uv pip compile` 批量解析依赖
- 自动检测 GPU 类型选择正确 PyTorch 索引
- 处理核心与扩展节点的依赖冲突
- 生成 `override.txt` 确保核心依赖优先
- 自动处理 OpenCV `gui` vs `headless` 冲突

### 工作流资源库

工作流资源库是项目的核心能力之一，支持：

1. **自动扫描**：递归扫描目录内所有工作流文件
2. **深度分析**：提取节点类型、模型、参数、连接关系
3. **智能分类**：根据文件路径和内容自动分类（文生图/图生视频等）
4. **模板提取**：去除具体值保留结构，生成可复用模板
5. **组件库**：按 loaders/samplers/encoders/decoders/processors/outputs 分类
6. **持续扩展**：将新工作流放入目录，重新运行构建脚本即可更新

### 高级工作流组装

基于自然语言描述从零组装复杂工作流：

- **基础架构**：文生图、图生图、文生视频、放大
- **视频六阶段架构**：严格遵循 lc.txt 工业级标准（预处理→模型加载→提示词→核心生成→合成→后处理）
- **动态架构选择**：视频任务支持方案A（HIGH+LOW 双采集器串行）/ 方案B（单一模型），根据预检用户选择决定，不写死
- **LoRA 叠加**：自动在模型加载器和采样器之间插入 LoraLoader
- **ControlNet**：插入 ControlNetApplyAdvanced，支持强度控制
- **放大链**：UpscaleModelLoader + ImageUpscaleWithModel
- **高清修复**：双采样器串联（KSampler1 → LatentUpscale → KSampler2）
- **多采样器**：追加 refine 采样器进行细节优化
- **自动布线**：拓扑排序、断开旧连接、建立新连接

---

## 配置管理

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `COMFYUI_PATH` | ComfyUI 安装路径 | `~/ComfyUI` |
| `COMFYUI_HOST` | 服务器主机 | `127.0.0.1` |
| `COMFYUI_PORT` | 服务器端口 | `3198` |
| `COMFYUI_OUTPUT_DIR` | 输出目录 | `ComfyUI/output` |

### CLI 配置文件

`config.ini` 存储：
- 默认工作空间路径
- Manager GUI 模式设置
- UV 编译默认值
- 后台进程信息（PID、端口、日志路径）

### 工作空间管理

四级回退策略：
1. `--workspace` 参数指定
2. `--here` 当前目录
3. `--recent` 最近使用
4. 默认路径（`~/ComfyUI`）

---

## 错误处理与故障排除

### 常见错误

| 错误类型 | 症状 | 解决方案 |
|----------|------|----------|
| `workflow_not_found` | 工作流文件不存在 | 检查文件路径 |
| `validation_error` | 节点参数错误 | 检查工作流 JSON 格式 |
| `execution_error` | 执行时出错 | 查看具体节点日志 |
| `timeout` | 执行超时 | 增加 `--timeout` 或降低参数 |
| `connection_error` | 无法连接服务器 | 检查服务器是否运行 |
| `out_of_memory` | 显存不足 | 降低步数/帧数/启用 BlockSwap |
| `model_not_found` | 模型不存在 | 检查模型路径或下载 |
| `node_not_found` | 节点类型不存在 | 安装缺失的自定义节点 |

### OOM（显存不足）处理策略

按优先级尝试：
1. 降低采样步数（30 → 20 → 15）
2. 降低帧数（81 → 41 → 21）
3. 增加 BlockSwap `blocks_to_swap`
4. 降低分辨率（保持 16 的倍数）
5. 启用 CPU offload（最后手段）

### 显存管理规则

1. **严禁使用共享 GPU 显存**：当专用显存足够时，禁止使用共享显存
2. **BlockSwap 优先**：显存不足时优先使用 BlockSwap 而非降低分辨率
3. **分辨率约束**：视频生成分辨率必须能被 16 整除
4. **模型选择**：
   - 文生视频/图生视频：使用 LowNoise 模型
   - 严禁使用 HighNoise 模型生成图片
   - 严禁使用视频生成大模型生成静态图片

---

## 开发指南

### 添加新脚本（脚本模式）

在 `scripts/` 目录下创建 Python 脚本：

```python
#!/usr/bin/env python3
import argparse
import json

def main():
    ap = argparse.ArgumentParser(description="My new script")
    ap.add_argument("--input", required=True)
    args = ap.parse_args()
    
    # Your logic here
    result = {"ok": True, "data": "..."}
    print(json.dumps(result))

if __name__ == "__main__":
    main()
```

规范：
- 使用 `argparse` 处理参数
- 输出 JSON 格式结果
- 支持环境变量配置
- 包含详细错误处理

### 添加新 CLI 命令

在 `cli/command/` 目录下创建子模块：

```python
import typer
from comfy_cli.command.custom_nodes.command import custom_node_manager

app = typer.Typer()

@app.command()
def my_command(arg: str):
    """Command description."""
    pass
```

规范：
- 使用 `typer` 框架
- 继承 `ClickException` 处理错误
- 支持 `--json` 输出
- 集成追踪分析

### 注册表发布

```bash
# 配置 Token
comfy node publish --token YOUR_REGISTRY_TOKEN

# 发布当前节点
comfy node publish
```

---

## 测试

### 测试结构

```
tests/
├── unit/               # 单元测试
├── integration/        # 集成测试
├── e2e/                # 端到端测试
└── uv_compile/         # uv 编译测试
```

### 运行测试

```bash
# 单元测试
pytest tests/unit/

# 集成测试
pytest tests/integration/

# E2E 测试
pytest tests/e2e/ -v

# uv 编译测试
pytest tests/uv_compile/ -v
```

### E2E 测试要点
- 使用真实包和冲突 fixture 包
- 渐进式冲突测试
- 配置默认测试
- 环境变量隔离

---

## 文档

| 文档 | 说明 |
|------|------|
| `.trae/skills/comfyui-controller/SKILL.md` | **技能入口**（安装为 Trae/Agent 技能时加载，含快速导航与路径） |
| `SKILL.md` | 技能模式完整文档（AI Agent 使用，主文档） |
| `README.md` | 项目 README（本文件） |
| `docs_cli/INDEX.md` | **全量经验/技术文档快速索引**（主题速查 + 章节行号导航） |
| `docs_cli/EXPERIENCE.md` | 24 章迭代经验与问题排查记录 |
| `SKILL.md §4.19` | K 采样器完全参考手册（ComfyUI 全家族，独立章节） |
| `docs_cli/wan22_dual_instance_tuning_guide.md` | Wan2.2 双实例视频生成调参手册 |
| `docs_cli/long_video_svi_pro_wan22_report.md` | 长视频完整任务报告 |
| `docs_cli/DESIGN-uv-compile.md` | uv 编译架构设计 |
| `docs_cli/PRD-uv-compile.md` | uv 编译产品需求 |
| `docs_cli/TESTING-e2e.md` | E2E 测试指南 |
| `docs_cli/json-output.md` | NDJSON 输出规范 |

---

## 作者与社区

**作者**：liuda1999

**QQ 群**：336439290

欢迎加入 QQ 群交流讨论，获取最新更新和技术支持。

---

## 许可证

本项目采用 [Apache-2.0](LICENSE) 许可证。

- 本项目融合了 `comfy-cli`（ComfyUI 官方 CLI）和 `comfyui-controller`（社区自动化工具）的功能
- `comfy-cli` 相关代码遵循其原始许可证
- `comfyui-controller` 相关代码遵循其原始许可证
- 融合后的架构文档和 README 为原创内容

---

## 致谢

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) - 强大的节点式 Stable Diffusion 界面
- [comfy-cli](https://github.com/Comfy-Org/comfy-cli) - ComfyUI 官方命令行工具
- [uv](https://github.com/astral-sh/uv) - 极速 Python 包管理器
