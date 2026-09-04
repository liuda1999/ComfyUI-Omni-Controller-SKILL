---
name: "comfyui-controller"
description: "ComfyUI 全能控制器。支持安装/启动/工作流执行/节点管理/模型下载/依赖编译/云端生成/环境检查。当用户需要执行 ComfyUI 相关任务时调用。"
---

# ComfyUI 全能控制器 (ComfyUI Omni-Controller)

## 0. 智能体快速导航（AI Agent Quick Nav）

> **如果你是 AI 智能体，首次读取本文件时，按以下路径快速了解项目核心能力。不要从头到尾通读。**

### 0.1 四大核心模块速览

| 模块 | 一句话描述 | 跳转 |
|------|-----------|------|
| **工作流创建** | 从零构建 ComfyUI 工作流 JSON，支持图片/视频/放大所有任务类型 | [→ 4.1-4.4 节](#41-工作流基础架构) |
| **工作流库管理** | 扫描、分类、查询已有工作流，提取模式复用 | [→ 3.1.9 节(scripts/)](#319-get_available_modelspy---模型查询器) + [4.15 节](#415-svi-pro-长视频工作流架构分析基于源码研读与-v12-实战验证) |
| **任务执行** | 提交工作流到 ComfyUI、监控进度、获取输出 | [→ 第 6 节 CLI 工作流程](#6-cli-工作运行流程标准操作程序) |
| **排错流程** | 工作流失败时的系统化排查方法 | [→ 第 8 节](#8-错误处理与故障排除) + [EXPERIENCE.md 第10/14章](docs_cli/EXPERIENCE.md) |

### 0.2 场景化入口（按你的任务类型跳转）

**你要生成图片？**
1. [4.1.1 图片生成核心节点链](#411-图片生成核心节点链) — 理解基础架构
2. [4.4 图片生成工作流参数](#44-图片生成工作流参数) — 按模型系列选参数
3. [6.3 关键 API 端点](#63-关键-api-端点) — `/object_info` 查询模型名

**你要生成视频？**
1. [4.2 视频生成通用流程](#42-视频生成通用流程适用于所有视频模型) — 7 步标准流程
2. [4.3 参考案例：Wan2.2](#43-参考案例wan22-视频生成v18v19-验证架构) — 节点链 + 参数梯度
3. [4.15 SVI Pro 长视频](#415-svi-pro-长视频工作流架构分析基于源码研读与-v12-实战验证) — 分段生成架构
4. [4.16 Flux2 修正工作流](#416-flux2-图片修正工作流img2img-模式) — 画质修正链路
5. [4.18 长视频色调/动作/拼接修复](#418-长视频色调动作拼接修复经验2026-07-29-验证) — 三大问题修复方案
6. [4.18.6 提示词工程完整方法论](#4186-提示词工程完整方法论引用) — 公式/人物/场景/动作/镜头/关系
7. [4.11 关键设计禁忌](#411-关键设计禁忌) — 踩坑前先看

**你要编写提示词？**
1. [EXPERIENCE.md 24.7.1 提示词公式体系](docs_cli/EXPERIENCE.md) — T2V/I2V/多镜头/运镜万能公式 + **分层写作法（主体+场景+风格）**
2. [EXPERIENCE.md 24.7.2 人物外貌描写](docs_cli/EXPERIENCE.md) — 面部/发型/服装/体态 8 维度 + 3 种气质类型综合示例
3. [EXPERIENCE.md 24.7.3 场景与物品描写](docs_cli/EXPERIENCE.md) — 类型/时间/光源/光线/物品/氛围 6 维度 + 4 种场景类型综合示例 + 场景层稳定框架原则
4. [EXPERIENCE.md 24.7.4 动作控制描写](docs_cli/EXPERIENCE.md) — 幅度/速率/连贯/多人/镜头配合 5 维度 + 4 大进阶技巧（时间逻辑词/分镜式描述/首尾帧稳定/单一焦点）
5. [EXPERIENCE.md 24.7.5 镜头设计术语库](docs_cli/EXPERIENCE.md) — 8 级景别 + 6 种角度 + 18 种运镜
6. [EXPERIENCE.md 24.7.6 关系描写方法论](docs_cli/EXPERIENCE.md) — 空间/互动/情感/因果/多人物 5 层次 + 4 种场景类型完整示例
7. [EXPERIENCE.md 24.7.7 完整提示词实战案例](docs_cli/EXPERIENCE.md) — 5 个案例（分层前后对比+多场景范例）
8. [EXPERIENCE.md 24.7.8 提示词编写禁忌](docs_cli/EXPERIENCE.md) — 21 大禁忌与正确做法（含分层/多人物/首尾帧等）

**你要排查工作流错误？**
1. [8.1 常见错误分类](#81-常见错误分类) — 快速匹配错误类型
2. [4.17 API/UI 格式映射](#417-api-格式与-ui-格式参数映射) — 参数错位问题
3. [8.8 长视频排错思路](#88-长视频排错思路2026-07-29-长视频任务验证) — 色调/动作/拼接/时间/格式
4. [EXPERIENCE.md 第14章](docs_cli/EXPERIENCE.md) — 通用问题分析解决流程（6 步法）
5. [EXPERIENCE.md 第21章](docs_cli/EXPERIENCE.md) — 参数梯度分析（调参参考）
6. [EXPERIENCE.md 第24章](docs_cli/EXPERIENCE.md) — 长视频三大问题修复完整复盘

**你要管理工作流库？**
1. [scripts/build_workflow_library.py](scripts/build_workflow_library.py) — 构建/更新工作流库
2. [scripts/query_library.py](scripts/query_library.py) — 6 种维度查询
3. [EXPERIENCE.md 13.4 节](docs_cli/EXPERIENCE.md) — 工作流仓库管理功能验证

### 0.3 文档关系图谱

```
SKILL.md (本文件) — 主入口
  │
  ├── 第 4 节: ComfyUI 工作流知识库（架构/参数/禁忌）
  │   ├── 详细经验 → EXPERIENCE.md（24章迭代经验 + 参数梯度分析第21章 + 节点场景化分析第22章 + 长视频修复第24章 + 提示词工程第24.7节）
  │   ├── SVI Pro 长视频 → EXPERIENCE.md 第15/18章 + 本文件 4.15节 + 第22章节点详解 + **第24章三大问题修复**
  │   ├── Flux2 修正 → EXPERIENCE.md 第17章 + 本文件 4.16节 + 第22章ReferenceLatent + **第24章换皮动作保留**
  │   ├── 多图/长视频节点 → EXPERIENCE.md 第12/22章（节点详解+短视频vs长视频差异+决策矩阵）
  │   ├── 长视频色调/动作/拼接修复 → 本文件 4.18节 + EXPERIENCE.md 第24章 + 8.8节排错
  │   ├── 提示词工程 → 本文件 4.18.6节（索引） + EXPERIENCE.md 第24.7节（完整方法论：公式/人物8维度/场景6维度/动作5维度/镜头18种/关系5层次）
  │   └── API/UI格式映射陷阱 → EXPERIENCE.md 第19章 + 本文件 4.17节 + 第22章KSamplerAdvanced陷阱
  │
  ├── 第 6 节: CLI 标准操作程序（10步执行流程）
  │
  ├── 第 8 节: 错误处理（OOM/连接/节点错误分类/长视频排错）
  │   ├── 通用排查方法 → EXPERIENCE.md 第10/14章
  │   └── 长视频排错 → 本文件 8.8节 + EXPERIENCE.md 第24章
  │
  └── 关联技能文件:
      ├── .trae/skills/video-task-execution-guide/SKILL.md  —— 视频任务6项强制预检
      ├── .trae/skills/image-task-execution-guide/SKILL.md  —— 图片任务5项强制预检+LoRA选择
      └── .trae/skills/comfyui-controller/SKILL.md —— 本技能包入口（快速导航 + 安装为技能）
      （本机 Agent 硬约束另存于 IDE 记忆/项目 memory 中，不随仓库分发）

docs_cli/ 技术文档（统一入口 → docs_cli/INDEX.md 快速索引）:
      ├── EXPERIENCE.md —— 24章迭代经验/排查（INDEX.md 含全章节行号导航）
      ├── wan22_dual_instance_tuning_guide.md —— Wan2.2 双实例双卡调参手册（架构/标定/编排）
      ├── dpmpp_ddpm_samplers_guide.md —— DPM++/DDPM 采样器完全参考手册
      ├── long_video_svi_pro_wan22_report.md —— C8/长视频完整任务报告
      └── json-output.md / DESIGN-uv-compile.md / PRD-uv-compile.md / TESTING-e2e.md —— CLI 功能文档
```

### 0.4 关键资料速查（按问题类型）

| 你想知道... | 查阅文件 | 章节 |
|------------|---------|------|
| 全量经验/技术文档怎么快速检索？ | docs_cli/INDEX.md | 主题速查（关键词→章节+行号）+ EXPERIENCE.md 全章节行号导航 |
| 某参数选什么值？ | EXPERIENCE.md | 第21章 参数梯度分析（15大参数+综合矩阵） |
| 采样器怎么选（DPM++/DDPM）？ | dpmpp_ddpm_samplers_guide.md | 第2/3章 各采样器详解+快速选择 |
| Wan2.2 双卡/双实例怎么配？ | wan22_dual_instance_tuning_guide.md | 0-3章 架构/阶段节点/标定/编排 |
| SVI Pro分段怎么搭？ | EXPERIENCE.md | 第15章 架构分析 + 第18章 段间连贯性 + 第22章节点详解 |
| Flux2修正怎么配？ | EXPERIENCE.md | 第17章 v12实战经验 + 第22章 ReferenceLatent |
| 多图视频怎么做？ | EXPERIENCE.md | 第12章 C5迭代 + 第22章 节点详解 + **第23章 C8完整复盘** |
| 长视频分段怎么拼接？ | EXPERIENCE.md | 第22章 长视频vs短视频节点差异 + 决策矩阵 + **第24章长视频拼接修复** |
| 工作流出错了怎么排查？ | EXPERIENCE.md | 第10章通用流程 + 第14章6步排查法 + **第23章 C8完整任务复盘** + **第24章长视频三大问题修复** |
| 显存管理怎么优化？ | EXPERIENCE.md | **第23章 C8显存管理问题** + SKILL.md 8.3节显存管理排错思路 |
| 多图视频只有单个人物？ | EXPERIENCE.md | **第23章 C8多图识别问题** + SKILL.md 8.4节多图视频排错思路 |
| 长视频色调漂移怎么修复？ | EXPERIENCE.md | **第24章 长视频色调修复（两层防线+ColorMatch）** + SKILL.md 4.18.1节 + 8.8.1节 |
| Flux2换皮动作偏离？ | EXPERIENCE.md | **第24章 Flux2 denoise梯度分析** + SKILL.md 4.18.2节 + 8.8.2节 |
| 视频拼接有渐变？ | EXPERIENCE.md | **第24章 overlap_mode梯度分析** + SKILL.md 4.18.3节 + 8.8.3节 |
| 长视频执行时间过长？ | EXPERIENCE.md | **第24章 执行时间优化策略** + SKILL.md 4.18.4节 + 8.8.4节 |
| 工作流加载报TypeError? | EXPERIENCE.md | **第24章 group格式兼容性** + SKILL.md 8.8.5节 |
| 提示词怎么写？ | EXPERIENCE.md | **第24.7节 提示词工程深度指南**（公式体系/人物8维度/场景6维度/动作5维度/镜头18种运镜/关系5层次） + SKILL.md 4.18.6节 |
| 人物-场景-物品关系怎么描写？ | EXPERIENCE.md | **第24.7.6节 关系描写5层次方法论**（空间/互动/情感/因果/多人物） + SKILL.md 4.18.6节 |
| 镜头运镜怎么选？ | EXPERIENCE.md | **第24.7.5节 镜头设计完整术语库**（8级景别/6种角度/18种运镜） + SKILL.md 4.18.6节 |
| 采样器卡死怎么判断？ | EXPERIENCE.md | **第23章 C8任务监控问题** + SKILL.md 8.3.3节采样器卡死判断 |
| KSamplerAdvanced参数怎么填？ | EXPERIENCE.md | 第19章 widgets_values 10值对齐 + 第22章详细陷阱表 |
| 某节点长视频/短视频怎么用？ | EXPERIENCE.md | 第22章 逐节点短视频vs长视频差异分析 |
| 文件复制失败怎么办？ | EXPERIENCE.md | 第20章 PowerShell→Python shutil |
| CLIP多图权重怎么分配？ | EXPERIENCE.md | 第21章 21.15 CLIP强度梯度 + 第22章 22.1 |
| ComfyUI启动命令？ | video-task-execution-guide | 检查1 标准启动命令 |
| 视频预检流程？ | video-task-execution-guide | 6项强制检查 |
| 图片预检流程？ | image-task-execution-guide | 5项强制检查+LoRA选择 |
| 显存硬约束？ | SKILL.md §4.5.3 显存管理硬约束 + video-task-execution-guide | 4.5.3节 + 6项强制检查 |

## 1. 项目概述

本项目是 ComfyUI 的**全能命令行与自动化控制工具**，融合了两个成熟项目的全部功能：
- **comfyui-controller**: 基于 Python 脚本的 ComfyUI 工作流执行引擎，擅长自动化任务执行
- **comfy-cli**: 官方 CLI 工具，提供完整的 ComfyUI 生命周期管理

## 2. 融合架构设计

### 2.1 双模式运行体系

| 模式 | 来源 | 适用场景 | 优先级 |
|------|------|----------|--------|
| **技能模式 (Skill Mode)** | comfyui-controller | 自动化任务、AI Agent 调用、工作流批量执行 | 默认 |
| **CLI 模式 (CLI Mode)** | comfy-cli | 手动管理、交互式操作、完整生命周期管理 | 备选 |

两种模式共享同一套配置、同一工作空间、同一 ComfyUI 实例，数据完全互通。

### 2.2 功能映射表（相同功能保留双方案）

| 功能领域 | 技能模式 (默认) | CLI 模式 (备选) | 说明 |
|----------|----------------|----------------|------|
| **安装 ComfyUI** | `scripts/start_server.py --install` | `comfy install` | CLI 支持更多选项（GPU/CPU/PR） |
| **启动服务器** | `scripts/start_server.py` | `comfy launch` | CLI 支持后台模式 `--background` |
| **停止服务器** | `scripts/controller.py stop` | `comfy stop` | **非完全等价**：`comfy stop` 仅停止 `comfy launch --background` 启动的实例；直接 `python main.py` 启动的实例需用 psutil 按命令行匹配终止（详见 EXPERIENCE.md 13.2 节） |
| **执行工作流** | `scripts/run_workflow.py` | `comfy run` | CLI 支持 `--json` NDJSON 输出 |
| **格式转换** | `scripts/workflow_converter.py` | `comfy run` (自动转换) | 两者都支持 UI→API 转换 |
| **节点管理** | `scripts/dependency_manager.py` | `comfy node` | CLI 支持发布/打包/二分查找 |
| **模型下载** | `scripts/download_models.py` | `comfy model download` | 两者都支持多源下载 |
| **依赖编译** | `scripts/dependency_manager.py --fix` | `comfy dependency` / `--uv-compile` | CLI 的 uv 编译更强大 |
| **环境检查** | `scripts/check_status.py` | `comfy env` | 技能模式检查更详细 |
| **工作流编辑** | `scripts/edit_workflow.py` | 无直接对应 | 技能模式独有功能 |
| **云端生成** | 无直接对应 | `comfy generate` | CLI 模式独有功能（Partner Nodes） |
| **快照管理** | 无直接对应 | `comfy node save-snapshot` | CLI 模式独有功能 |
| **GitHub PR** | 无直接对应 | `comfy github` | CLI 模式独有功能 |

### 2.3 项目目录结构（融合后）

```
comfyui-controller/
├── SKILL.md                          # 本文件 - 技能主文档
├── README.md                         # 项目 README
├── assets/                           # 工作流模板和示例（语义化版本号，禁止 v2/v3/final 命名）
│   ├── t2v_wan22_v1.0.0.json         # 文生视频工作流模板（Wan2.2）
│   ├── i2v_wan22_v1.0.0.json         # 图生视频工作流模板（Wan2.2）
│   ├── i2v_wan22_kj_v1.0.0.json      # 图生视频 KJ 变体（Wan2.2）
│   ├── svi_pro_long_video_v1.0.0.json # SVI Pro 长视频分段工作流
│   ├── img_gen_v1.0.0.json           # 图片生成工作流模板
│   ├── img2img_flux2_example_v1.0.0.json # Flux2 图生图示例
│   ├── wan22_i2v_workflow.json       # Wan2.2 I2V 参考模板（无版本问题）
│   ├── wan22_t2v_workflow.json       # Wan2.2 T2V 参考模板
│   ├── workflow_library.json         # 工作流资源库索引（build_workflow_library.py 生成）
│   └── archive/                      # 旧版本归档（task1_*/task2_v3_final/c5_video_task_v6 等历史版本）
├── scripts/                          # 技能模式脚本（comfyui-controller 原有）
│   ├── controller.py                 # 服务器控制（启动/停止/状态）
│   ├── start_server.py               # 服务器启动器（支持安装）
│   ├── run_workflow.py               # 工作流执行器（WebSocket 实时监听）
│   ├── check_status.py               # 环境检查器
│   ├── workflow_converter.py         # UI→API 格式转换器
│   ├── edit_workflow.py              # 工作流编辑器
│   ├── dependency_manager.py         # 依赖管理器（节点/模型/修复）
│   ├── download_models.py            # 模型下载器（支持 pget）
│   ├── get_available_models.py       # 模型查询器
│   ├── advanced_workflow_builder.py  # 高级工作流构建器（六阶段架构+动态方案选择）
│   ├── pre_task_inquiry.py           # 任务预检反问模块（模型选择+架构方案+参数收集+硬件检查）
│   ├── video_task_runner.py          # 视频任务执行主入口（集成预检+节点校验+工作流生成+执行）
│   ├── check_workflow_dependencies.py # 依赖检查（含视频专用节点校验）
│   ├── workflow_analyzer.py          # 工作流深度分析器
│   ├── build_workflow_library.py     # 工作流资源库构建器
│   └── workflow_generator.py         # 工作流生成建议器
├── cli/                              # CLI 模式工具（comfy-cli 移植）
│   ├── cmdline.py                    # CLI 入口
│   ├── command/                      # CLI 命令子模块
│   │   ├── install.py                # ComfyUI 安装
│   │   ├── launch.py                 # 启动 ComfyUI
│   │   ├── run.py                    # 运行工作流（NDJSON 输出）
│   │   ├── generate/                 # 云端生成（Partner Nodes）
│   │   ├── custom_nodes/             # 自定义节点管理
│   │   ├── models/                   # 模型管理
│   │   └── github/                   # GitHub PR 信息
│   ├── registry/                     # 注册表 API
│   ├── workspace_manager.py          # 工作空间管理
│   ├── config_manager.py             # 配置管理
│   ├── uv.py                         # uv 依赖编译器
│   ├── workflow_to_api.py            # UI→API 转换（CLI 版）
│   ├── env_checker.py                # 环境检查
│   └── cuda_detect.py                # CUDA 检测
├── docs_cli/                         # 文档目录
│   ├── INDEX.md                      # **全量经验/技术文档快速索引**（主题速查 + 章节行号导航）
│   ├── EXPERIENCE.md                 # 迭代经验与问题排查（24 章：导入/依赖/HTTP/工作流/参数梯度/节点详解/任务复盘/长视频修复）
│   ├── dpmpp_ddpm_samplers_guide.md  # DPM++/DDPM 采样器参考手册
│   ├── wan22_dual_instance_tuning_guide.md # Wan2.2 双实例视频生成调参手册
│   ├── long_video_svi_pro_wan22_report.md  # C8/长视频完整任务报告
│   ├── DESIGN-uv-compile.md          # uv 编译设计文档
│   ├── PRD-uv-compile.md             # uv 编译产品需求
│   ├── TESTING-e2e.md                # E2E 测试指南
│   └── json-output.md                # NDJSON 输出规范
└── (无 tests/ 目录，测试通过脚本内联验证)
```

## 3. 核心功能详解

### 3.1 技能模式功能（scripts/）

#### 3.1.1 controller.py - 服务器控制中枢
- `start()`: 启动 ComfyUI 服务器，支持 GPU/CPU 模式
- `stop()`: 停止服务器
- `is_running()`: 检查服务器状态
- `wait_for_ready()`: 等待服务器就绪
- `get_gpu_info()`: 获取 GPU 信息

#### 3.1.2 start_server.py - 服务器启动器
- 支持 `--install` 自动安装 ComfyUI
- 支持 `--cpu` CPU 模式启动
- 支持 `--port` 自定义端口
- 自动检测 GPU 类型

#### 3.1.3 run_workflow.py - 工作流执行引擎
- **仅支持 API 格式工作流**（UI 格式需先用 `workflow_converter.py` 转换）
- 通过 HTTP 轮询 `/history/{prompt_id}` 监听执行进度（非 WebSocket）
- 默认等待执行完成才返回（无需 `--wait` 参数）
- 支持的实际参数：
  - `--workflow`：工作流 JSON 文件路径（必填）
  - `--host`：服务器主机（默认 127.0.0.1）
  - `--port`：服务器端口（默认 3198，可通过环境变量 `COMFYUI_PORT` 覆盖）
  - `--timeout`：超时秒数（默认 300，视频任务建议设为 900+）
  - `--poll`：轮询间隔秒数（默认 1.5）
- **输出识别**：脚本默认解析 `images` 字段；视频任务输出在 `gifs` 字段（VHS_VideoCombine 节点特性），需额外查询 `/history/{prompt_id}` 确认
- **错误处理**：通过 `/history` 的 `status.messages` 提取 `execution_error`，返回节点 ID、类型、异常信息

#### 3.1.4 check_status.py - 环境检查器
- 检查 Python 版本
- 检查 PyTorch 和 CUDA
- 检查 ComfyUI 安装
- 检查 GPU 可用性和显存
- 检查自定义节点
- 检查模型文件
- 检查服务器运行状态

#### 3.1.5 workflow_converter.py - 格式转换器
- UI 格式（`nodes`/`links`）→ API 格式（`class_type`/`inputs`）
- 自动类型转换（字符串→数字）
- 保留所有连接关系

#### 3.1.6 edit_workflow.py - 工作流编辑器
- 更新正向/负向提示词
- 更新种子（支持随机）
- 更新分辨率
- 更新采样步数
- 更新 CFG 值
- 更新模型名称

#### 3.1.7 dependency_manager.py - 依赖管理器
- 扫描本地模型文件
- 获取服务器可用节点
- 智能模型匹配（忽略量化后缀）
- 分析工作流依赖
- 自动修复模型替换
- 生成安装报告

#### 3.1.8 download_models.py - 模型下载器
- 支持 HuggingFace / CivitAI / 普通 URL
- 自动推断模型子目录
- 优先使用 pget 并行下载
- 支持 `--overwrite` 覆盖
- 支持 `--no-pget` 回退到 urllib

#### 3.1.9 get_available_models.py - 模型查询器
- 查询服务器可用模型列表
- 支持 `--search` 搜索过滤
- 优先推荐 fp8 版本

### 3.2 CLI 模式功能（cli/）

#### 3.2.1 安装与启动
- `comfy install`: 安装 ComfyUI + ComfyUI-Manager
  - `--gpu`: NVIDIA/AMD/Intel Arc/Mac M 系列自动检测
  - `--cpu`: CPU 模式
  - `--version`: 指定版本
  - `--pr`: 安装特定 PR
  - `--fast-deps`: 使用 uv 快速解析依赖
- `comfy launch`: 启动 ComfyUI
  - `--background`: 后台启动
  - `--frontend-pr`: 切换前端 PR
- `comfy stop`: 停止后台进程

#### 3.2.2 工作流执行
- `comfy run <workflow>`: 执行工作流
  - `--json`: NDJSON 结构化输出（9 种事件类型）
  - 自动 UI→API 格式转换
  - WebSocket 实时进度
  - 17 种错误分类

#### 3.2.3 自定义节点管理
- `comfy node install <node>`: 安装节点
  - `--fast-deps` / `--no-deps` / `--uv-compile`
- `comfy node reinstall/uninstall/update`: 重新安装/卸载/更新
- `comfy node enable/disable`: 启用/禁用
- `comfy node fix`: 修复依赖
- `comfy node show`: 列出节点
- `comfy node save-snapshot/restore-snapshot`: 快照管理
- `comfy node install-deps`: 从工作流提取依赖
- `comfy node publish`: 发布到 Registry
- `comfy node pack`: 打包节点
- `comfy node scaffold`: 使用 cookiecutter 创建项目
- `comfy node bisect`: 二分查找问题节点

#### 3.2.4 模型管理
- `comfy model download <url>`: 下载模型
  - 支持 HuggingFace / CivitAI / 普通 URL
  - 自动识别模型类型
  - `--set-civitai-api-token`: 设置 CivitAI Token
  - `--set-hf-api-token`: 设置 HF Token
- `comfy model list`: 列出模型
- `comfy model remove`: 删除模型

#### 3.2.5 云端生成（Partner Nodes）
- `comfy generate <model>`: 文生图/图生图
  - 支持 `flux-pro`, `dalle`, `ideogram-edit` 等
- `comfy generate list`: 浏览可用模型
- `comfy generate schema <model>`: 查看参数
- `comfy generate upload`: 上传本地图片
- `comfy generate resume`: 恢复异步任务

#### 3.2.6 依赖编译（uv）
- `comfy dependency`: 依赖编译安装
- `comfy standalone`: 打包独立 Python 环境
- `--uv-compile`: 使用 uv 编译（7 个命令支持）
- `DependencyCompiler` 类：
  - `uv pip compile` 批量解析
  - GPU 类型自动检测
  - 核心 + 扩展依赖冲突处理
  - OpenCV 冲突自动处理

#### 3.2.7 其他功能
- `comfy set-default`: 设置默认工作空间
- `comfy which`: 显示当前 ComfyUI 路径
- `comfy env`: 打印环境信息
- `comfy update`: 更新 ComfyUI 或节点
- `comfy github`: GitHub PR 信息

## 4. ComfyUI 图片与视频生成工作流知识

### 4.1 工作流基础架构

ComfyUI 采用**节点图（Node Graph）**架构，数据通过节点间的连线流动。工作流有两种格式：
- **UI 格式**：包含 `nodes` 和 `links`，用于前端展示
- **API 格式**：包含 `class_type` 和 `inputs`，用于后端执行

#### 4.1.1 图片生成核心节点链

标准文生图工作流的数据流：

```
CheckpointLoaderSimple → CLIPTextEncode(正/负) → EmptyLatentImage → KSampler → VAEDecode → SaveImage
                              ↑                      ↑
                         提示词输入              分辨率设置
```

核心节点说明：
| 节点 | 功能 | 关键参数 |
|------|------|----------|
| `CheckpointLoaderSimple` | 加载 SD 模型 | `ckpt_name` |
| `CLIPTextEncode` | 编码文本提示词 | `text` |
| `EmptyLatentImage` | 创建空白潜在空间 | `width`, `height`, `batch_size` |
| `KSampler` | 采样去噪 | `seed`, `steps`, `cfg`, `sampler_name`, `scheduler` |
| `VAEDecode` | VAE 解码为图片 | `vae`, `samples` |
| `SaveImage` | 保存输出 | `filename_prefix` |

#### 4.1.2 视频生成与图片生成的关键区别

视频生成工作流与图片生成有本质区别：

1. **模型不同**：视频使用专门的视频模型（Wan, HunyuanVideo, CogVideo），而非 SD 模型
2. **编码器不同**：Wan 模型使用 **T5 编码器**（`LoadWanVideoT5TextEncoder`），而非 CLIP
3. **采样器不同**：使用专用视频采样器（`WanVideoSampler`），而非通用 `KSampler`
4. **潜在空间不同**：视频潜在空间包含时间维度（帧数）
5. **解码器不同**：使用 `WanVideoDecode` 解码为视频帧
6. **输出节点不同**：使用 `VHS_VideoCombine` 合并帧为视频文件

### 4.2 视频生成通用流程（适用于所有视频模型）

**核心原则**：视频生成参数（节点链、采样器、shift、CFG 调度等）**与模型系列和 LoRA 类型强绑定**，不可跨系列套用。以下流程适用于所有视频模型（Wan2.2/HunyuanVideo/CogVideoX/LTX-Video 等）。

#### 4.2.1 通用执行流程

```
Step 1: 查询可用视频模型
  按模型系列查询对应的模型加载节点：
  - Wan2.2: GET /object_info/WanVideoModelLoader → 获取 diffusion_models 列表
  - HunyuanVideo: GET /object_info/HunyuanVideoModelLoader
  - 通用 UNET 模型: GET /object_info/UNETLoader
  GET /object_info/UpscaleModelLoader → 获取放大模型列表
  注: 不同系列使用不同的模型加载节点，不可混用（见 4.2.2 节对照表）

Step 2: 识别模型系列
  根据模型文件名识别系列（Wan2.2/HunyuanVideo/CogVideoX/LTX-Video 等）
  使用 scripts/build_workflow_library.py 的 detect_model_family() 辅助识别
  不同系列工作流不可混用组件（模型/VAE/CLIP/LoRA 必须同系列）

Step 3: 查询该系列对应的节点链
  方式A: 从工作流仓库查询参考工作流
    python scripts/query_library.py --model-family Wan2.2
  方式B: 从 custom_nodes 目录的 example_workflows 查找官方示例
  方式C: 从 ComfyUI 官方文档查询节点链架构

Step 4: 动态查询参数范围
  所有 COMBO 类型参数（模型选择、采样器、调度器等）必须从 /object_info/{NodeType} 动态获取
  禁止硬编码模型名、采样器名、调度器名
  必需输入（required inputs）也必须查询，不能凭记忆补全（如 VHS_LoadVideo 的 custom_width/custom_height）
  枚举值（如 VHS_LoadVideo 的 format）必须使用合法值，不接受任意字符串

Step 5: 按硬件档位选择参数
  根据 GPU VRAM 选择分辨率/帧数/精度/blocks_to_swap（见 4.4 节硬件梯度表）

Step 6: 预检反问（强制不可跳过，见 4.8 节）
  模型选择展示 → 参数收集 → 相机视角确认 → 硬件校验

Step 7: 执行并验证
  python scripts/run_workflow.py --workflow <api.json> --timeout 900
```

#### 4.2.2 模型系列与节点链对照（通用参考）

不同视频模型系列使用不同的节点链，下表为常见系列的节点链对照，**具体节点名和参数以 `/object_info` 查询结果为准**：

| 模型系列 | 自定义节点包 | 模型加载节点 | 采样器节点 | VAE 解码节点 | 视频输出节点 |
|---------|------------|-------------|-----------|-------------|-------------|
| Wan2.2 | ComfyUI-WanVideoWrapper | WanVideoModelLoader | WanVideoSampler | WanVideoDecode | VHS_VideoCombine |
| HunyuanVideo | ComfyUI-HunyuanVideoWrapper | HunyuanVideoModelLoader | HunyuanVideoSampler | HunyuanVideoDecode | VHS_VideoCombine |
| CogVideoX | ComfyUI-CogVideoXWrapper | CogVideoModelLoader | CogVideoSampler | CogVideoDecode | VHS_VideoCombine |
| LTX-Video | ComfyUI-LTXVideo | LTXModelLoader | LTXSampler | LTXDecode | VHS_VideoCombine |

**注**：以上节点名仅供参考，实际节点名以本地安装的自定义节点包和 `/object_info` 查询结果为准。

#### 4.2.3 通用视频生成约束（适用于所有系列）

1. **分辨率必须能被 16 整除**：避免 tensor size mismatch（如 360 需用 352）
2. **帧数受模型训练长度约束**：超过训练长度会导致语义重复（RIFLEX 仅防数学循环，不防语义重复）
3. **段间转场用末帧继承**：分段生成时提取前段末帧作为后段首帧
4. **VAE 解码禁用 tiling（视频任务）**：enable_vae_tiling 会导致视频帧间不一致
5. **VHS_VideoCombine 高质量编码**：`crf=14` + `pix_fmt=yuv420p10le`

### 4.3 参考案例：Wan2.2 视频生成（V18/V19 验证架构）

**重要备注**：本节为 Wan2.2 + lightx2v LoRA 组合的验证案例，**仅作参考**。以下参数（steps/shift/scheduler/CFG 调度等）是针对该特定组合验证的值，换其他模型或 LoRA 时需重新验证，不可直接套用。

**源工作流参考**: `${COMFYUI_PATH}/custom_nodes/ComfyUI-WanVideoWrapper/example_workflows/wanvideo2_2_I2V_A14B_example_WIP.json`

#### 4.3.1 Wan2.2 节点链架构（V18/V19 验证）

**核心节点链**：
```
WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler
```

**错误架构（V16/V17 旋转问题根因，禁止使用）**：
```
WanVideoBlockSwap(生成args) → WanVideoModelLoader(直接接收block_swap_args) → WanVideoSampler
```

**架构差异说明**：
- WanVideoSetBlockSwap 和 WanVideoSetLoRAs 是独立节点，在模型加载后单独应用
- 直接将 block_swap_args 传给 ModelLoader 的输入参数是错误的
- 错误架构导致 lightx2v LoRA 无法正确应用，引发旋转问题

#### 4.3.1.1 Wan2.2 专用节点清单

| 节点 | 功能 | 备注 |
|------|------|------|
| `WanVideoModelLoader` | 加载 Wan 视频模型 | 不直接接收 block_swap_args 和 lora |
| `WanVideoBlockSwap` | 生成 BlockSwap 配置参数 | 独立节点，输出 BLOCKSWAPARGS |
| `WanVideoSetBlockSwap` | 将 BlockSwap 配置应用到模型 | 接收 model + block_swap_args，输出 model |
| `WanVideoLoraSelect` | 选择 LoRA 并设置强度 | 输出 WANVIDLORA |
| `WanVideoSetLoRAs` | 将 LoRA 应用到模型 | 接收 model + lora，输出 model |
| `WanVideoVAELoader` | 加载 Wan VAE | |
| `LoadWanVideoT5TextEncoder` | 加载 T5 文本编码器 | |
| `WanVideoTextEncode` | T5 编码提示词 | |
| `WanVideoClipVisionEncode` | CLIP Vision 编码图像 | |
| `WanVideoImageToVideoEncode` | I2V 编码 | 输出 image_embeds |
| `WanVideoSampler` | Wan 专用采样器 | 支持双阶段串行 |
| `WanVideoDecode` | 解码视频潜在空间 | 禁用 enable_vae_tiling |
| `INTConstant` | 共享参数节点 | 用于 steps 和 split_step |
| `CreateCFGScheduleFloatList` | 动态 CFG 调度 | V18 关键改进 |

#### 4.3.2 双阶段串行架构（Wan2.2 参考）

通过 WanVideoSampler 的 start_step/end_step 参数控制双阶段采样：
- HIGH 阶段: start_step=0, end_step=split_step（处理高噪声主结构）
- LOW 阶段: start_step=split_step, end_step=-1, samples=HIGH输出, add_noise_to_samples=False（处理低噪声细化）

**动态 CFG 调度（Wan2.2 + lightx2v 验证）**：
- 使用 CreateCFGScheduleFloatList 节点生成动态 CFG 调度
- 参考配置: cfg_scale_start=2, cfg_scale_end=2, start_percent=0.0, end_percent=0.01
- 效果: 第一步 CFG=2，其余步 CFG=1
- HIGH sampler: cfg 输入连接 CreateCFGScheduleFloatList 输出
- LOW sampler: 固定 cfg=1

**注**：此 CFG 调度方案针对 lightx2v 蒸馏模型验证，其他模型/LoRA 组合需重新验证。

#### 4.3.3 Wan2.2 关键参数梯度建议

**重要**：以下参数为 Wan2.2 + lightx2v LoRA 组合的参考值，按硬件档位提供梯度建议。实际使用时应根据模型类型、LoRA 类型、任务需求动态调整，不可直接套用。

**WanVideoModelLoader 参数梯度**：
| 参数 | 说明 | L1 (8-12GB) | L2 (12-16GB) | L3 (16-24GB) | L4 (≥24GB) | 备注 |
|------|------|-------------|-------------|-------------|-----------|------|
| `base_precision` | 基础精度 | bf16 | bf16 | bf16 | fp16_fast | fp16_fast 在低显存+lightx2v 时 OOM |
| `quantization` | 量化模式 | fp8_e4m3fn_scaled | fp8_e4m3fn_scaled | fp8_e4m3fn_scaled | bf16/fp8 | 按显存选择 |
| `load_device` | 加载设备 | offload_device | offload_device | offload_device | default | 显存紧张时必须 offload |
| `attention_mode` | 注意力模式 | sdpa | sdpa | sdpa | sageattn/flash | **本机环境（PyTorch 2.9.1+cu128）已验证**：sageattn 的 C++/CUDA 扩展与当前 PyTorch 版本不兼容，触发 `code 0xc0000139` DLL 加载失败（入口点缺失），全档位强制使用 `sdpa`（PyTorch 原生注意力）；Linux 环境若 sageattn 可用，L4 档可省约 50% 注意力显存 |

**WanVideoSampler 参数梯度（lightx2v LoRA 加速后）**：
| 参数 | 说明 | L1 (8-12GB) | L2 (12-16GB) | L3 (16-24GB) | L4 (≥24GB) | 备注 |
|------|------|-------------|-------------|-------------|-----------|------|
| `steps` | 采样步数 | 6-8 | 6-8 | 8-10 | 10-15 | lightx2v 加速后 6-8 步；无加速 LoRA 时 20-30 步 |
| `cfg` | 引导系数 | 动态调度 | 动态调度 | 动态调度 | 动态调度/固定 | lightx2v 用 [2,1,1,1,1,1]；无 LoRA 时用 5.0-7.0 |
| `shift` | 调度器偏移 | 8.0 | 8.0 | 8.0 | 8.0 | Wan2.2 源工作流值；其他模型需查官方文档 |
| `scheduler` | 调度器 | dpm++_sde | dpm++_sde | dpm++_sde | dpm++_sde | Wan2.2+lightx2v 验证值；其他模型可尝试 euler/unipc |
| `rope_function` | RoPE 函数 | comfy_chunked | comfy_chunked | comfy_chunked | comfy_chunked | 480x848 及以上必须使用 |
| `force_offload` | 强制卸载 | true | true | true | false | L4 显存充足时可关闭 |
| `riflex_freq_index` | Riflex 频率索引 | 0(≤81帧) | 0(≤81帧) | 6(>81帧) | 6(>81帧) | 训练范围内无需 RIFLEX |

**WanVideoImageToVideoEncode 参数约束**：
| 参数 | 说明 | 约束 |
|------|------|------|
| `width` | 视频宽度 | 必须能被 16 整除 |
| `height` | 视频高度 | 必须能被 16 整除 |
| `num_frames` | 帧数 | 按硬件档位选择（见 4.4 节），Wan2.2 训练原生长度约 81 帧 |
| `noise_aug_strength` | 噪声增强强度 | 0.1（禁止 0，会导致亮度锚定缺失） |

#### 4.3.4 模型文件格式与选择（通用）

| 格式 | 扩展名 | 适用场景 | 显存占用 | 质量 |
|------|--------|----------|----------|------|
| BF16 | `.safetensors` | 24GB+ 显存 | 高 | 最佳 |
| FP8 | `.fp8.safetensors` | 16-24GB 显存 | 中 | 良好 |
| Q8_0 GGUF | `.gguf` | 10-12GB 显存 | 低 | 接近 fp16 |
| Q5_K_M GGUF | `.gguf` | 8-10GB 显存 | 很低 | 可接受 |
| Q4_K_M GGUF | `.gguf` | <8GB 显存 | 最低 | 一般 |

**GGUF 模型加载规则**：
- `.gguf` 模型已经过量化，加载时必须设置 `quantization: disabled`
- 否则会出现 `Quantization should be disabled when loading GGUF models` 错误

#### 4.3.5 LoRA 选择策略（通用方法论）

**重要**：LoRA不仅用于加速，还有画质增强、角色一致性、重新打光等多种类型。使用前必须检查本地`models/loras/`目录已有文件，根据任务需求甄别挑选。

**LoRA 类型分类**：

| 类型 | 用途 | 是否可叠加 |
|------|------|-----------|
| 加速蒸馏 | 减少步数和CFG计算量 | 不可与其他LoRA叠加 |
| 画质增强 | 提升细节和质感 | 可与其他类型叠加 |
| 重新打光 | 调整场景光线 | 可与其他类型叠加 |
| 角色一致性 | 约束角色外貌 | 可与其他类型叠加 |

**LoRA 使用决策流程（适用于所有模型系列）**：
1. 检查本地`models/loras/`目录已有文件
2. 根据任务需求选择类型（加速/画质/角色/打光）
3. 确认LoRA与模型版本匹配（如 Wan2.1 vs Wan2.2，不可混用）
4. 确认LoRA与分辨率匹配（如 480p LoRA 应用于 480p 分辨率）
5. 确认LoRA间是否可叠加（加速LoRA通常不可叠加）
6. 遵循官方推荐strength值，不可随意提高

**Wan2.2 LoRA 参考案例**（仅作示例，其他模型系列需查对应文档）：
- 加速: `lightx2v_I2V_14B_480p_cfg_step_distill`，strength=1.0（官方推荐），30步→6-8步
- 画质增强: `SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH`，需增加步数到20-30步
- 重新打光: `WanAnimate_relight_lora_fp16`
- 不推荐: `Wan21_I2V_14B_lightx2v`（Wan2.1 版本，不兼容 Wan2.2）

#### 4.3.6 调度器选择方法论（通用）

调度器选择与模型系列和任务类型相关，不同模型有不同的推荐调度器。下表为常见调度器特性，**实际选择应以模型官方文档推荐为准**：

| 调度器 | 特性 | 适用场景 |
|--------|------|---------|
| `dpm++_sde` | 随机性调度器，产生自然动作变化 | 动作丰富的视频生成（Wan2.2 验证） |
| `unipc` | 确定性调度器，结果可复现 | 静态或微动作视频，需可复现场景 |
| `euler` | 简单稳定 | 简单测试场景，Flux 图片生成常用 |
| `euler_ancestral` | 带随机性的 euler | SD1.5/SDXL 图片生成常用 |
| `karras` | 噪声调度优化 | 通常作为 scheduler 配合采样器使用 |

**注**：Wan2.2 + lightx2v 组合验证 dpm++_sde 效果优于 unipc（unipc 导致动作卡住旋转），但此结论不可泛化到其他模型。

### 4.4 图片生成工作流参数

#### 4.4.1 SD 1.5 / SDXL 标准参数

| 参数 | 说明 | 推荐范围 |
|------|------|----------|
| `steps` | 采样步数 | 20-30（SD1.5）/ 30-50（SDXL） |
| `cfg` | 引导系数 | 7.0-8.0 |
| `sampler_name` | 采样器 | `euler_ancestral`, `dpmpp_2m` |
| `scheduler` | 调度器 | `normal`, `karras` |
| `width x height` | 分辨率 | SD1.5: 512x512, 512x768 / SDXL: 1024x1024 |

#### 4.4.2 Flux 模型参数

**Flux 1 参数**：

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `steps` | 采样步数 | 4-20（Flux 步数可更少） |
| `cfg` | 引导系数 | 1.0-3.5（Flux 使用较低 CFG） |
| `sampler_name` | 采样器 | `euler`, `heun` |
| `model` | 模型 | `flux1-dev.safetensors` |

**Flux 2 参数（Klein 系列）**：

| 参数 | 说明 | 推荐值 | 备注 |
|------|------|--------|------|
| `steps` | 采样步数 | 20-30 | 高画质建议 30 步 |
| `cfg` | 引导系数 | 1.0 | Distill 模型特性，cfg=1 |
| `sampler_name` | 采样器 | `euler` | - |
| `scheduler` | 调度器 | `simple` | - |
| `model` | UNET 模型 | 按本地实际文件名 | 执行前必查 `/object_info/UNETLoader` |
| `clip` | 文本编码器 | qwen_3_8b 系列 | type=flux2（必填） |
| `vae` | VAE | flux2-vae.safetensors | - |

**Flux 2 节点链架构（与 Flux 1 完全不同，禁止混用）**：

| 节点 | 功能 | 关键差异 |
|------|------|---------|
| `UNETLoader` | 模型加载 | weight_dtype=default（无 type 参数） |
| `CLIPLoader` | 文本编码器 | **type=flux2（必填）**，device=default |
| `EmptyFlux2LatentImage` | 潜在空间 | **非 EmptyLatentImage**，Flux2 专用 |
| `CLIPTextEncode` | 正向条件 | 英文提示词（Flux2 对中文支持有限） |
| `ConditioningZeroOut` | 负向条件 | **零化正向条件**，非 CLIPTextEncode 负面文本 |
| `KSampler` | 采样 | cfg=1，sampler=euler，scheduler=simple |
| `VAEDecode` | 解码 | - |

**备注**：Flux 1 与 Flux 2 架构完全不同，禁止混用。F2K-9b-kleinova 的 txt_in 层期望 12288 维（Qwen3-8B 取第9/18/27层拼接=3×4096），T5XXL 只输出 4096 维，混用会导致 mat1/mat2 shapes cannot be multiplied 错误。

### 4.5 显存管理规则（通用）

1. **严禁使用共享 GPU 显存**：当专用 GPU 显存足够时，禁止使用共享显存
2. **BlockSwap 策略**：显存不足时优先使用 BlockSwap 而非降低分辨率
3. **分辨率约束**：视频生成分辨率必须能被 16 整除（360非16倍数，必须用352）

#### 4.5.1 硬件梯度档位参考表

| 档位 | VRAM范围 | 推荐分辨率 | 单次最大帧数 | blocks_to_swap | base_precision |
|------|---------|-----------|------------|----------------|----------------|
| L1 入门级 | 8-12GB | 352×640 | 81帧 | 40-42 | bf16 |
| L2 标准级 | 12-16GB | 480×640 | 121帧 | 38-40 | bf16 |
| L3 高性能级 | 16-24GB | 480×848 | 121帧 | 20-24（C8验证） | bf16 |
| L4 专业级 | ≥24GB | 576×1024 | 121帧 | 20-24 | fp16_fast |

> **C8 验证更新**：L3 档 blocks_to_swap 从 36-38 修正为 20-24。值过高会导致专用显存闲置（仅用 40%），转而使用共享 GPU 内存。降至 20 后专用显存利用率提升至 75%+。

**注**：以上为单次生成参考值。**Wan2.2 训练原生长度约 81 帧（3.4秒），单次生成超过 121 帧会导致语义重复**（角色执行两遍动作）。长视频应采用分段生成+拼接（每段 81-121 帧），而非单次超过训练长度。图片生成可适当提高分辨率档位。

#### 4.5.2 显存物理限制公式

```
FFN激活值 ≈ (帧数 × 宽 × 高 / 4096) × 20480 × 2bytes
```

**示例计算（L3高性能级，16-24GB VRAM，单次生成不超过121帧）**：
- 121帧@480x848: FFN约7.9GB（可行）
- 121帧@576x1024: FFN约11.4GB（可行）
- 121帧@720x1280: FFN约17.7GB（不可行）
- 注: 241帧单次生成虽显存可行(15.7GB)，但会触发语义重复，应分段生成

#### 4.5.3 显存管理硬约束（用户明确指示）

**最高优先级原则**：
1. **必须优先使用 CPU**：模型加载、数据预处理等非GPU必需任务应交给CPU
2. **必须优先使用 GPU 显存**：GPU显存是有限资源，应合理规划使用
3. **绝对禁止使用内存交换（共享GPU内存）**：除非用户主动要求，否则绝对不能启用
   - 禁止使用 `--lowvram` 启动 ComfyUI（会启用GPU显存↔系统内存交换）
   - 禁止使用 `--cpu-vram` 或类似的内存交换参数
   - 原因：内存交换会导致生成速度降低数倍
4. **多模型加载策略（基于原 SVI Pro 工作流分析）**：
   - **同一模型文件场景**：原 SVI Pro 工作流中 high_model 和 low_model 链路各自有一个 UNETLoader，但**加载同一个模型文件**。ComfyUI 的模型缓存机制会自动复用，显存中只驻留一份模型，不会 OOM
   - **不同模型文件场景**：若 HIGH 和 LOW 确实使用不同模型文件（如现实类配置：Remix HIGH + Wan2.2 LOW），则不可同时加载，必须串行执行（HIGH 完成释放后加载 LOW）
   - **禁止臆测工作流设计**：必须先研读原工作流的实际节点连接和模型加载逻辑，不可凭推测拆分/修改工作流架构

**OOM 正确处理顺序**：
1. 检查是否同时加载了多个大模型 → 改为串行加载
2. 降低分辨率（保持16倍数）
3. 分段生成+拼接（保持总时长）
4. 降低精度（如 fp16_fast → bf16）
5. **最后手段**：增加 BlockSwap（CPU↔GPU 数据搬运，速度变慢但不下降低质量）

#### 4.5.4 OOM 处理策略（硬约束：禁止降级时长）

**核心原则**：项目硬约束明确要求"视频时长不足时禁止直接降级时长：OOM 时应采用分段生成+拼接方案，而非从 10 秒降到 3.4 秒"。以下方向按优先级排列，**方向2（降帧数）已被禁止**：

**方向1: 降分辨率保帧数（推荐）**
- 优点: 保持时长，动作连贯性不受影响
- 缺点: 画质下降，可后续用 X2 放大器补偿
- 示例: 480x848 → 352x640

**方向2: 分段生成+拼接（替代降帧数，硬约束要求）**
- 优点: 保持总时长和分辨率
- 缺点: 需多次执行，段间转场需用末帧继承处理
- 示例: 241帧单次 → 3段×81帧拼接（每段末帧作为下段 start_image）

**方向3: 降精度保帧数和分辨率**
- 优点: 保持时长和分辨率
- 缺点: 画质轻微下降，bf16 比 fp16_fast 慢约 1.5 倍
- 示例: fp16_fast → bf16

**方向4: 调整 BlockSwap**
- 优点: 不降低任何质量参数
- 缺点: CPU↔GPU 数据搬运增加，速度变慢
- 示例: blocks_to_swap 20 → 24（递增 2-4 个单位）
- **注意**（C8 验证）：blocks_to_swap 值过高会导致专用显存闲置，转而使用共享 GPU 内存。L3 档推荐 20-24，非 36-38。

**禁止方向：直接降帧数**
- ❌ 241帧 → 121帧（5秒）+ 插帧
- 原因: 违反硬约束"禁止直接降级时长"，且插帧无法恢复原始动作语义

### 4.6 采样参数选择方法论（通用）

**核心原则**：采样参数（steps/cfg/shift/scheduler）与模型系列、LoRA 类型强相关，不存在通用最优值。应按以下原则选择：

#### 4.6.1 步数选择（按 LoRA 类型）

| LoRA 类型 | steps 范围 | 说明 |
|-----------|-----------|------|
| 加速蒸馏 LoRA（如 lightx2v） | 6-10 | 蒸馏后步数大幅降低，L1/L2 用 6-8，L3/L4 可用 8-10 |
| 画质增强 LoRA | 20-30 | 画质 LoRA 需更多步数发挥效果 |
| 无 LoRA（原生模型） | 20-30 | 按模型官方推荐，Wan2.2 原生约 20-30 步 |

#### 4.6.2 CFG 选择（按 LoRA 类型）

| LoRA 类型 | CFG 范围 | 说明 |
|-----------|---------|------|
| 加速蒸馏 LoRA（如 lightx2v） | 动态调度 [2,1,1,1,1,1] | 第一步 CFG=2，其余 CFG=1 |
| 画质增强 LoRA | 5.0-7.0 | 按官方推荐 |
| 无 LoRA（原生模型） | 5.0-8.0 | 按模型官方推荐 |

#### 4.6.3 shift 和 scheduler 选择（按模型系列）

| 参数 | 选择原则 | Wan2.2 参考值 |
|------|---------|-------------|
| `shift` | 查模型官方文档/源工作流 | 8.0（源工作流值） |
| `scheduler` | 查模型官方文档，不同调度器特性见 4.3.6 节 | dpm++_sde（+lightx2v 验证） |
| `rope_function` | 高分辨率（480x848+）需 comfy_chunked | comfy_chunked |
| `noise_aug_strength` | 禁止 0（会导致亮度锚定缺失） | 0.1 |

**注**：以上 Wan2.2 参考值仅适用于 Wan2.2 + lightx2v 组合，其他模型需查对应官方文档。

### 4.7 工作流执行规则

1. **必须先检查环境**：执行前运行 `check_status.py`
2. **模型必须先检查本地可用性**：禁止自动下载大模型（询问用户）
3. **工作流格式**：优先使用 API 格式，UI 格式需转换
4. **输出目录**：视频输出到 `output/`，文件名包含版本号
5. **错误处理**：OOM 时优先降分辨率或降精度，而非降帧数（详见 4.5.3 节硬约束）
6. **端口约定**：`run_workflow.py` 默认端口为 3198（硬编码），可通过 `--port` 参数或 `COMFYUI_PORT` 环境变量覆盖；启动 ComfyUI 时必须使用相同端口

### 4.8 模型匹配规则

1. 精确匹配 > 忽略大小写匹配 > 忽略量化后缀匹配 > 关键词匹配
2. 量化后缀：`fp8`, `fp16`, `fp32`, `bf16`, `e4m3fn`, `Q5_K_M` 等
3. 置信度阈值：>=85 自动替换，50-85 警告，<50 视为缺失

### 4.9 视频生成预检反问环节（强制不可跳过）

**入口**: `scripts/pre_task_inquiry.py` → `run_pre_task_inquiry()`
**执行入口**: `scripts/video_task_runner.py` → `run_video_task()`

| 步骤 | 功能 | 对应函数 | 说明 |
|------|------|---------|------|
| 1 | 模型查询展示 | `query_and_select_models()` | `/object_info` API 查询 diffusion_models/vae/clip/clip_vision，按系列分组展示 |
| 2 | 架构方案选择 | `collect_architecture_scheme()` | 方案A 双采样器（HIGH+LOW 顺序执行，硬约束）/ 方案B 单采样器（降级备选） |
| 3 | 生成参数收集 | `collect_generation_params()` | 画面比例、分辨率、优化步数、正负面提示词 |
| 4 | 硬件兼容性检查 | `check_hardware_compatibility()` | GPU VRAM/RAM 查询，不足时**终止任务** |
| 5 | 汇总确认 | `print_summary()` | 输出完整参数表，用户最终确认后方可执行 |

**重要**：预检反问环节不可跳过。收到提示词后不可直接执行，必须先反问确认架构方案、画面比例、分辨率、优化程度（steps），再汇总参数等待用户最终确认。

**绕过路径警示**：
- 仅 `video_task_runner.py::run_video_task()` 入口强制预检
- `scripts/run_workflow.py` 直接执行工作流时不经过预检，需用户自行确认参数
- `video_task_runner.py` 模块级函数（`ui_to_api`/`queue_prompt`/`wait_for_completion`/`_extract_output_path`）可被独立调用绕过预检，不建议直接使用

### 4.10 视频任务类型支持

| 任务类型 | 说明 | 特殊节点 |
|----------|------|----------|
| img2vid | 图生视频 | 标准双阶段架构 |
| first_last_frame | 首尾帧视频 | WanFirstLastFrameToVideo（start_image+end_image） |
| multi_image_video | 多图片生成视频（从多个图片中提取元素生成视频） | WanVideoClipVisionEncode（combine_embeds=concat/average） |
| long_video | 长视频 | ImageBatchExtendWithOverlap |
| video_concat | 视频拼接 | VHS_LoadVideo + ImageBatch |
| multi_ref_video | 多参考视频 | 多参考图嵌入 |

**multi_image_video 多图视频生成要点（C5任务验证）**：
- 使用`WanVideoClipVisionEncode`的`combine_embeds`参数融合多图特征（concat或average）
- `strength_1`/`strength_2`调整各图权重：角色参考图高权重(1.5)约束外貌，场景图低权重(0.5)弱化干扰
- 标准 I2V 模型使用`fun_or_fl2v_model=false`，FLF2V是专用模型功能
- 长视频超过单次帧数限制时采用分段生成+拼接，每段start_image=前段末帧
- 详见 `docs_cli/EXPERIENCE.md` 第12章

### 4.11 关键设计禁忌

#### 4.11.1 通用禁忌（适用于所有模型系列）

| 禁止 | 原因 | 正确做法 |
|------|------|----------|
| 分辨率非16整除 | tensor size mismatch | 使用352/480/640等16倍数值 |
| 跨系列混用模型组件 | Wan2.2+SD VAE 等组合不允许 | 同系列组件自动匹配 |
| 直接用用户白话作提示词 | 模型无法精准理解 | 三段式结构化转换 |
| 跳过预检环节 | 显存不足或模型不匹配时盲目执行 | 强制预检不可跳过 |
| 使用 RealESRGAN_x2 超分AI生成内容 | 不适合AI生成内容，产生伪影 | 使用 2x_StarSample_V2.0 等 AI 专用放大模型 |
| 分段生成+每段超分 | 段间累积损失，清晰度崩塌 | 单次生成或最终统一超分 |
| 加速LoRA与画质LoRA叠加 | 官方明确警告易崩溃 | 二选一：加速优先或画质优先 |
| 超过模型训练长度单次生成 | RIFLEX防数学循环但不防语义重复，导致动作执行两遍 | 分段生成+拼接，每段在训练长度内 |
| 分段生成无末帧继承 | 段间转场突兀，角色不一致 | 提取前段末帧作为后段start_image |
| 视频任务只查 `images` 字段 | VHS_VideoCombine 输出在 `gifs` 字段，漏检导致误判任务失败 | 同时检查 `images` 和 `gifs` 字段 |
| 跨盘直接复制文件到 input 目录 | 文件系统白名单限制，PermissionError | 用 `/upload/image` API 上传（Python requests） |
| 凭记忆补全节点必需输入 | 节点版本更新后参数变化，导致 Required input missing 错误 | 查询 `/object_info/{NodeType}` 确认必需输入 |
| ReferenceLatent 双图注入 | 双图注入时模型取平均，细节被稀释 | 只用最清晰的参考图（单 B 图注入） |
| Flux2 修正用 EmptyFlux2LatentImage | 文生图模式从零生成，丢失原图背景 | 用 A 图 VAEEncode 作为 latent 起点（img2img 模式） |
| Flux2 修正用英文提示词 | qwen_3_8b 对中文理解更好 | 使用中文提示词 |
| PowerShell 文件复制 | 路径白名单权限静默失败 | 用 Python shutil.copy2 + 验证文件大小 |
| KSamplerAdvanced widgets_values 缺值 | UI 格式按 position 顺序映射，缺 control_after_generate 导致全部错位 | 确保 widgets_values 有 10 个值 |
| 多图视频仅靠 CLIP Vision concat | `combine_embeds="concat"` 仅合并语义特征向量，非像素合并，画面仍只有 start_image 单图内容 | 使用 `ImageConcatMulti` 水平拼接多图作为 `start_image`，CLIP Vision 仅作语义辅助引导 |
| 双模型同时加载到显存 | HIGH 未卸载即加载 LOW，导致 OOM 或被迫使用共享内存 | 在 HIGH→LOW 切换点插入 `PurgeVRAM V2` 显式清理节点，实现串行执行 |
| `blocks_to_swap` 过高导致专用显存闲置 | 值过高时 GPU 保留 block 过少，专用显存未利用，转而使用共享内存 | 按硬件档位选择：L3 级推荐 20，专用显存利用率 75%+ |
| `--disable-smart-memory` + `--disable-cuda-malloc` 组合 | 禁用智能内存管理和 cudaMallocAsync，导致大模型加载时内存碎片化卡死 | 使用默认智能内存管理，移除这两个启动参数 |
| 连续任务不重启 ComfyUI | 单次任务后显存占用 30GB+ 不释放，下次任务 OOM | 连续任务间必须重启 ComfyUI 服务 |
| 使用 sageattn 注意力模式 | sageattention 的 C++/CUDA 扩展与本机 PyTorch 2.9.1+cu128 不兼容，触发 `code 0xc0000139` DLL 加载失败（入口点缺失） | 使用 `sdpa`（PyTorch 原生注意力），牺牲少量速度换取稳定性 |
| `--whitelist-custom-nodes` 用逗号分隔 | ComfyUI 要求空格分隔的多个独立参数，逗号分隔会被识别为单个字符串导致白名单失效 | 每个节点名作为独立参数传入 |
| 提示词包含 "360 orbit" 等运镜词 | Wan2.2 对运镜描述极敏感，"orbit" 类词直接触发相机旋转，画面混乱 | 删除运镜词，改为"固定镜头"或"画面稳定" |
| 多图视频提示词未明确人物位置 | 仅描述"两个女孩跳舞"，模型无法确定左右位置关系，位置混乱 | 明确描述："左边女孩来自参考图1，右边女孩来自参考图2" |
| 误删 LOW 模型节点改为单采样器 | 双模型架构是项目硬约束，单采样器无法达到同等质量 | 保持 HIGH+LOW 双采样器架构，通过 `start_step`/`end_step` 控制双阶段采样 |
| Flux2 换皮 `denoise > 0.7` | 接近文生图模式，破坏 SVI Pro 生成的动作结构，角色动作偏离原始截图 | Flux2 换皮推荐 `denoise=0.5-0.65`（长视频任务验证 0.6 为最优平衡点，见 `EXPERIENCE.md` 24.3.1） |
| 长视频仅靠提示词约束色调 | 提示词约束无法防止多段累积漂移，5 段以上视频仍会逐渐变冷变白 | 长视频（>5秒/多段拼接）必须插入 `ColorMatch` 节点硬性锚定（`method=reinhard, strength=0.8-0.9`，见 `EXPERIENCE.md` 24.4.2） |
| Flux2 换皮后未做颜色还原 | Flux2 换皮会改变色彩，LoRA-ColorTone 强度不足以校正 | Flux2 输出后必须插入 `ColorMatch` 节点，`image_ref` 指向原参考图（见 `EXPERIENCE.md` 24.4.2） |
| 多段拼接默认使用 `linear_blend` | 线性混合产生渐变过渡，不符合"直接拼接"需求 | 根据场景选择 `overlap_mode`：`linear_blend`（渐变）/ `cut`（硬切直接拼接）/ `fade`（淡入淡出），见 `EXPERIENCE.md` 24.5.1 |
| ColorMatch 的 `image_ref` 使用生成帧 | 生成帧本身存在色调偏移，作为参考会导致二次漂移 | 所有 `ColorMatch` 节点必须共用同一张原始参考图（LoadImage），避免使用生成帧作为参考 |
| SVI Pro 正负向提示词色调约束冲突 | 正向要求"暖色调"同时负向禁止"暖色溢色"，模型在避免暖色溢出时过度倾向冷色 | 正向约束指定目标色调（"保持暖色调"），负向约束仅禁止偏离方向（"禁止变冷变白"），不可冲突 |
| 工作流 group 使用 `pos+size` 旧格式 | ComfyUI 0.27.0+ 要求 `bounding` 数组格式，旧格式导致 `TypeError: can't convert undefined to object` | 转换为 `bounding: [x, y, w, h]` 格式，添加 `id` 和 `flags: {}` 字段（见 `EXPERIENCE.md` 24.2.3） |
| 长视频优化时降低分辨率保时长 | 分辨率直接影响画质，降低分辨率导致画面模糊 | 优先降低 `steps`（线性影响耗时）和 `length`（线性影响耗时和时长），保持分辨率不变 |
| 手部/肢体修复仅用负向提示词 | 仅禁止错误结构（"多手指"）而不指定正确结构，模型可能生成中间状态 | 双向约束：正向指定正确结构（"十指分明，两臂两腿"）+ 负向禁止错误结构（"多手指，三头六臂"） |

#### 4.11.2 Wan2.2 专用禁忌（仅适用于 Wan2.2 + lightx2v 组合）

| 禁止 | 原因 | 正确做法 |
|------|------|----------|
| 使用 KSampler 替代 WanVideoSampler | 缺 motion_scale/noise_aug 控制，导致模糊噪点 | 使用 WanVideoSampler |
| 直接将 block_swap_args 传给 ModelLoader | LoRA 无法正确应用，导致旋转 | 使用 WanVideoSetBlockSwap 独立节点 |
| 使用 unipc 调度器 | 确定性导致动作卡住旋转 | 使用 dpm++_sde（仅 Wan2.2+lightx2v 验证） |
| shift=3.0 或 5.0 | 非源工作流值 | shift=8.0（仅 Wan2.2 源工作流值） |
| 静态 CFG=5.0 | 引导过强或不足 | 动态 CFG 调度[2,1,1,1,1,1]（仅 lightx2v 验证） |
| noise_aug_strength=0 | 亮度锚定缺失 | noise_aug_strength=0.1 |
| 标准 I2V 模型启用 FLF2V 模式 | FLF2V是专用模型功能，标准模型用fun_or_fl2v_model=false | 仅FLF2V专用模型启用 |
| lightx2v HIGH strength=3.0 | 破坏MoE自然去噪曲线导致细节丢失 | strength=1.0（官方推荐） |
| 分段生成CLIP双图权重相同 | 末帧场景特征干扰角色外貌 | 角色参考图高权重(1.5)，末帧低权重(0.5) |
| 仅使用 LOW 模型处理高噪声阶段 | 人物结构崩塌 | HIGH+LOW 双阶段架构 |

**注**：4.11.2 的禁忌仅适用于 Wan2.2 + lightx2v LoRA 组合，其他模型系列应查对应官方文档确定专属禁忌。

### 4.12 负面提示词构建原则

**核心原则**：负面提示词应按任务类型构建，不同任务类型的负面词完全不同。以下为分类参考，实际使用时应根据具体场景调整。

#### 4.12.1 通用负面词（所有任务适用）

```
最差质量，低质量，JPEG压缩残留，模糊，pixelated, compressed artifacts,
丑陋的，残缺的，畸形的，毁容的，多余的手指，手指融合,
杂乱的背景，detail loss, blurry, low detail
```

#### 4.12.2 图片生成负面词

```
静态，字幕，水印，文字，logo，
过曝，欠曝，色调艳丽，highlight clipping,
多余的物体，构图错误，透视错误
```

#### 4.12.3 视频生成负面词（通用）

```
motion blur, frame skipping, 动作僵硬，动作断裂,
distorted body, deformed limbs, floating hair, gravity defiance,
face changing, character drift, inconsistent appearance,
blurring progression, detail degradation, cumulative quality loss,
多余肢体，缺失肢体，肢体断裂，肢体溶解，三条腿，腿部消失
```

#### 4.12.4 视频生成负面词（固定相机场景专用）

```
camera movement, camera pan, camera tilt, camera zoom, camera dolly,
camera shake, unstable framing, 视角变化, 运镜, 镜头移动
```

**注**：若任务为运镜视频（非固定相机），则**不应**使用 4.12.4 的负面词。

#### 4.12.5 视频生成负面词（分段生成亮度一致性专用）

```
色调艳丽，过曝，曝光变化，亮度突变，背景亮度变化，background brightening,
exposure drift, lighting changes, overexposed, highlight clipping,
background replacement, background changing, different background
```

**注**：此组负面词仅适用于分段生成时保障段间亮度一致，非分段任务无需使用。

#### 4.12.6 提示词结构化转换（通用）

用户白话提示词应转换为三段式结构：
1. **主体描述**：人物/物体的外貌、动作、表情
2. **环境描述**：场景、光线、氛围
3. **质量描述**：画质要求、风格

动作描述需使用严格约束语句（如 "standing in place, no turning, no spinning"），避免复合动作导致肢体消失。

### 4.13 一键执行视频任务

```bash
# 执行视频生成任务（task_type 为位置参数，非 --task 选项）
# 完整调用链: check_server_online → run_pre_task_inquiry → check_video_nodes_available
#            → _generate_workflow → ui_to_api → queue_prompt
#            → wait_for_completion → _extract_output_path
python scripts/video_task_runner.py img2vid --image input.png --prompt "a girl smiling"

# 支持的任务类型: img2vid / first_last_frame / multi_image_video / long_video / video_concat / multi_ref_video
# 注意: video_task_runner.py 内部调用 run_workflow.py，同样仅支持 API 格式工作流
```

### 4.14 迭代经验总结

**重要**：以下经验为 Wan2.2 + lightx2v LoRA 组合的迭代总结，**仅作参考**。其他模型系列的迭代经验应记录在 `docs_cli/EXPERIENCE.md` 中。

**Wan2.2 成功架构参考（V18/V19 + C8 验证）**：
- WanVideoWrapper 原生节点链 + lightx2v 加速 LoRA + 动态 CFG 调度 + dpm++_sde 调度器
- 参考配置（L3高性能级）: 480x848 + 81-121帧 + 4-8步 + bf16 + BLOCKS_TO_SWAP=20-24（C8验证，非36-38）
- **重要**：单次生成帧数应控制在模型训练长度内（Wan2.2 推荐 81-121 帧/3.4-5秒）。241帧（10秒）会导致语义重复（角色执行两遍动作），长视频应采用分段生成+拼接

**C5多图视频迭代经验（v3-v14，2026-07-22）**：
- 详见 `docs_cli/EXPERIENCE.md` 第12章
- 核心教训1：单次生成帧数与硬件配置相关，超过模型训练长度(81帧)时RIFLEX防数学循环但不防语义重复
- 核心教训2：LoRA类型多样需甄别挑选，lightx2v是加速LoRA非画质LoRA，HIGH strength=1.0是官方推荐值
- 核心教训3：分段生成+拼接是多图视频的有效方案，段间转场用末帧继承+CLIP权重调整
- 最终v14架构：3段×81帧=10秒，HIGH strength=1.0，steps=8，CLIP concat(1.png=1.5 + 末帧=0.5)

**Wan2.2 失败教训（仅参考）**：
- V3 KSampler 架构：shift/VAE/scheduler 全部不匹配，高曝光+模糊
- C5 v3-v8: 241帧单次生成导致提示词执行两遍（RIFLEX不防语义重复）
- C5 v9-v11: 分段生成段间无转场，角色不一致
- C5 v13: HIGH strength=3.0导致细节丢失（发型、皮肤、衣服质感）
- V16 lightx2v + 错误节点链：LoRA 破坏 CFG 引导一致性，角色持续旋转
- V17 移除 LoRA + unipc：确定性调度器导致动作卡住旋转
- V18 首版 fp16_fast + 480x848：OOM 崩溃

**基础功能验证经验（2026-07-22）**：
- 详见 `docs_cli/EXPERIENCE.md` 第13章
- 核心教训1：`comfy stop` 仅停止 background 实例，直接启动的实例用 psutil 按命令行匹配终止
- 核心教训2：复杂场景文生图用 Flux 2.0，SD1.5 仅适合简单场景，Flux2 提示词转英文
- 核心教训3：模型名执行前必查 `/object_info/{NodeType}`，不可硬编码
- 核心教训4：AI 图片放大用 2x_StarSample_V2.0，RealESRGAN_x2 对 AI 内容产生伪影

**C7 SVI Pro + Flux2 修正迭代经验（v12，2026-07-25）**：
- 详见 `docs_cli/EXPERIENCE.md` 第16-20章
- 核心教训1：SVI Pro 现实人物必须用现实类配置（HIGH模型+HIGH lora + LOW模型+LOW lora），动漫类配置（两个都是HIGH模型）导致LOW阶段无效、画质模糊
- 核心教训2：Flux2 修正时 ReferenceLatent 只用单图（B图原参考图），双图注入导致细节平均化稀释
- 核心教训3：Flux2 修正用 img2img 模式（A图VAEEncode作为latent起点），文生图模式丢失背景
- 核心教训4：段间过渡 motion_latent_count=0 + 修正图作为段2-5起点，避免暗→亮渐变
- 核心教训5：KSamplerAdvanced widgets_values 必须 10 个值（含 control_after_generate），API格式按key映射、UI格式按position顺序
- 核心教训6：PowerShell文件操作不可靠，优先用Python shutil.copy2

### 4.15 SVI Pro 长视频工作流架构分析（基于源码研读与 v12 实战验证）

**背景**：SVI = Stable Video Infinity，v2.0 Pro 版本兼容 Wan2.2，通过 LoRA + 分段生成 + latent 传递 + 重叠融合实现长视频制作，修复长视频重复运动问题。

**源工作流**：`${COMFYUI_PATH}/user/default/workflows/Wan2.2-Svi 2.0无限图生视频-20秒.json`

#### 4.15.1 核心节点：WanImageToVideoSVIPro（KJNodes）

**源码位置**：`${COMFYUI_PATH}/custom_nodes/ComfyUI-KJNodes/nodes/nodes.py`

**功能**：创建 I2V 条件编码（concat_latent_image + concat_mask）和空 latent，供 KSamplerAdvanced 采样。

**输入**：
- `positive` / `negative`（CONDITIONING）：文本条件
- `anchor_samples`（LATENT）：输入图像经 VAEEncode 的 latent（固定锚点）
- `prev_samples`（LATENT，可选）：前段输出 latent（段间连贯）
- `length`（INT）：帧数（默认 81）
- `motion_latent_count`（INT）：从前段携带的 motion latent 数（段1=0，段2-5=1）

**内部逻辑**：
1. `anchor_latent` = anchor_samples 的 clone（形状 B,C,T,H,W，T=1）
2. `empty_latent` = zeros [B, 16, ((length-1)//4)+1, H, W]（待采样的空 latent）
3. 若有 prev_samples：`image_cond_latent` = concat([anchor_latent, prev末尾motion_latent_count帧])，实现段间连贯
4. 填充 padding 至 total_latents 长度
5. `mask` = ones，首帧=0（锚点固定不采样），其余=1（待生成）
6. 将 concat_latent_image 和 concat_mask 写入 positive/negative 条件

**输出**：修改后的 positive/negative + 空 latent

#### 4.15.2 三大优化节点（SVI Pro 核心，不可省略）

| 节点 | 源码位置 | 功能 | 工作流参数 |
|------|---------|------|-----------|
| `PathchSageAttentionKJ` | model_optimization_nodes.py:114 | 将模型注意力替换为 SageAttention（auto 自动选择最佳模式），加速注意力计算 | sage_attention="auto", allow_compile=false |
| `ModelPatchTorchSettings` | model_optimization_nodes.py:328 | 采样前启用 `torch.backends.cuda.matmul.allow_fp16_accumulation=True`，需 PyTorch 2.7.1+（本机 2.9.1+cu128 已满足） | enable_fp16_accumulation=true |
| `LoraLoaderModelOnly` | comfy-core | 加载 SVI HIGH lora（rank 128, fp16），修复长视频重复运动，提升动作连贯性 | lora="SVI_v2_PRO_..._HIGH_lora_rank_128_fp16.safetensors", strength=1 |

**注意**：SageAttention 和 fp16_accumulation 是显存和速度优化，**不改变生成质量**。SVI HIGH lora 才是质量增强的核心。三个节点分别应用于 high_model 链路和 low_model 链路（共 6 个节点实例）。

#### 4.15.3 模型加载策略（关键认知纠正）

原工作流模型加载区有 3 个 UNETLoader：

| 节点 | 模型文件 | 用途 | 状态 |
|------|---------|------|------|
| 节点2 | `Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors` | HIGH 链路 → SetNode high_model | 启用 |
| 节点3 | `Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors`（**同一文件**） | LOW 链路 → SetNode low_model | 启用 |
| 节点129 | `Wan2.2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` | 备用 LOW 模型 | **未连接（links 为空）** |

**核心机制**：节点2 和节点3 加载**同一个模型文件**，ComfyUI 的模型缓存机制自动复用，显存中只驻留一份 14B 模型。high_model 和 low_model 虽名字不同，但指向同一模型实例。

**两种配置模式**（通过 group 标注区分）：
- **动漫类**（当前启用）：HIGH 和 LOW 都用 `Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors`（同一文件，缓存复用）
- **现实类**（备用）：HIGH 用 Remix 模型，LOW 用 `Wan2.2_2-I2V-A14B-LOW` 模型（不同文件，需串行加载）

#### 4.15.4 双阶段采样（KSamplerAdvanced step 分段）

原工作流是**一个完整图**，5 段 × (1 HIGH + 1 LOW) = 10 个 KSamplerAdvanced 节点，通过 SetNode/GetNode 引用模型和参数。

**参数（通过 INTConstant + link 覆盖 widget）**：
- `length=81`（每段 81 帧）
- `width=1024, height=576`（原工作流分辨率）
- `steps=6`（总步数，INTConstant 节点30）
- `steps2=2`（split_step，INTConstant 节点31）

**每段双阶段**：
- **HIGH**：`add_noise=enable, start_at_step=0, end_at_step=steps2(2), return_with_leftover_noise=enable`
- **LOW**：`add_noise=disable, start_at_step=steps2(2), end_at_step=10000, return_with_leftover_noise=disable`
- HIGH 通过 `return_with_leftover_noise=enable` 将带噪 latent 传递给 LOW
- LOW 接收 HIGH 的输出 latent（`add_noise=disable`），从 step 2 继续采样至完成

#### 4.15.5 段间连贯机制

**Latent 层传递**：
- 段1：WanImageToVideoSVIPro 的 prev_samples 未连接（motion_latent_count=0）
- 段2-5：prev_samples ← 前段 LOW KSamplerAdvanced 的输出 latent，motion_latent_count=1

**图像层拼接**（ImageBatchExtendWithOverlap）：
- 源码位置：`${COMFYUI_PATH}/custom_nodes/ComfyUI-KJNodes/nodes/image_nodes.py:1791`
- 参数：`overlap=5, overlap_side="source", overlap_mode="linear_blend"`
- 逻辑：prefix(source[:-5]) + linear_blend(source[-5:], new[:5]) + suffix(new[5:])
- 5 段 81 帧 × overlap 5 → 最终 385 帧 ≈ 20 秒@20fps

#### 4.15.6 显存要求与适配

原工作流 group 标注："低于 16G 显存和 32G 内存，跑不动的哈！"

**RTX 3080 20GB 适配建议**（保持工作流完整性，不拆分）：
1. 保持所有优化节点（SageAttention + TorchSettings + LoraLoader）
2. 分辨率从 1024×576 降至 832×480 或 640×352（保持 16 倍数）
3. 帧数保持 81 帧/段（SVI 推荐值，不宜降低）
4. weight_dtype 保持 "default"（让 ComfyUI 自动选择）
5. 禁止启用内存交换（`--lowvram` 等）

#### 4.15.7 SVI Pro 工作流使用禁忌

1. **禁止拆分工作流**：不可将 HIGH/LOW 拆成独立工作流文件，破坏 ComfyUI 的模型缓存和内存管理
2. **禁止省略优化节点**：SageAttention、TorchSettings、LoraLoader 三者是 SVI Pro 核心
3. **禁止臆测参数**：steps/steps2/length 等参数必须参照原工作流 INTConstant 节点的值
4. **禁止混用模型系列**：SVI HIGH lora 仅兼容 Wan2.2-I2V-A14B，不可用于其他系列
5. **适用场景**：生活化、慢节奏场景；不推荐快速镜头运动

#### 4.15.8 v12 段间连贯性优化（实战验证）

**暗→亮渐变问题**（第18章详记）：
- 当 `motion_latent_count>0` 且 `prev_samples` 来自不同来源时，内部 `concat([anchor_latent, motion_latent])` 因 VAE 分布差异导致亮度异常
- **解决**：段 2-5 使用 Flux2 修正图作为 LoadImage 输入，保持 `motion_latent_count=0`，不连接 prev_samples

**段间过渡正确架构**：
```
段1: LoadImage(原图) → anchor_samples，motion_latent_count=0
Flux2修正段1最后帧 → 修正图

段2-5: LoadImage(上一段修正图)，anchor_samples=原图（不变），motion_latent_count=0
```

### 4.16 Flux2 图片修正工作流（img2img 模式）

**用途**：对 SVI Pro 输出的视频帧进行画质修正（去躁、恢复细节、保持色调），修正后的图片作为下一段 SVI Pro 的参考图。

#### 4.16.1 核心架构

```
LoadImage(A图=待修正图片) → ImageResizeKJv2 → VAEEncode → latent_image(KSampler起点)
                                                              ↓
UNETLoader(F2K-9b) → LoraLoader×3 → CFGGuider
                                      ↓
CLIPLoader(type=flux2) → CLIPTextEncode → ReferenceLatent(B图=原参考图) → CFGGuider
                                                                          ↓
SplitSigmasDenoise(denoise=0.5) → KSampler(cfg=3.5, steps=32) → VAEDecode → SaveImage
```

**A图**：待修正的模糊图片（SVI Pro 输出）
**B图**：原始参考图（清晰的参考源）

#### 4.16.2 关键设计原则

| 原则 | 说明 |
|------|------|
| ReferenceLatent 只用 B 图 | 双图注入导致模型平均化，细节被稀释。只用最清晰的参考图 |
| img2img 模式 | 用 A 图 VAEEncode 作为 latent 起点，保留背景构图 |
| 中文提示词 | qwen_3_8b 对中文语义理解优于英文 |
| 提示词具体化 | 不写"花纹"而写"精美的绣花纹路" |
| SplitSigmasDenoise | denoise=0.5 控制噪声添加量，平衡保真与修正 |

#### 4.16.3 推荐参数（基于 v12 实战验证）

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| denoise | 0.5 | 0.4 过低导致修正不足，0.5 平衡保真与修正 |
| steps | 32 | 28-32 步获取最佳细节恢复 |
| cfg | 3.5 | 3.5 避免 img2img 色彩过度饱和 |
| LoRA ColorTone | 0.4 | 降低暖色叠加，防止偏黄 |
| LoRA Skin | 0.6 | 增强皮肤质感恢复 |
| LoRA Detail | 1.0 | 最大化细节增强 |
| sampler/scheduler | euler/simple | Flux2 标准配置 |

#### 4.16.4 关键禁忌

1. **禁止 ReferenceLatent 双图注入**：A+B 双图导致细节平均化稀释
2. **禁止 EmptyFlux2LatentImage 作为起点**：纯文生图模式无法保留原图背景
3. **禁止英文提示词**：qwen_3_8b 对中文理解更好
4. **禁止过高 LoRA ColorTone**：>0.6 导致明显偏色

### 4.17 API 格式与 UI 格式参数映射

#### 4.17.1 核心差异

| 特性 | API 格式 | UI 格式 |
|------|---------|---------|
| 参数映射 | 按 key 名映射（顺序无关） | 按 widgets_values position 顺序映射 |
| 节点结构 | `class_type` + `inputs`（字典） | `nodes`(含 widgets_values) + `links` |
| 隐式 widget | 不需要 | 必须包含（如 control_after_generate） |

#### 4.17.2 KSamplerAdvanced widgets_values 规范

`noise_seed` 带有 `control_after_generate: True` 时，前端自动追加隐式 widget，需 10 个值：

```
widgets_values: [add_noise, noise_seed, control_after_generate, steps, cfg, sampler_name, scheduler, start_at_step, end_at_step, return_with_leftover_noise]
```

**control_after_generate 可选值**：`"fixed"`, `"increment"`, `"decrement"`, `"randomize"`

**常见错误**：只有 9 个值（缺少 control_after_generate）→ 参数全部错位 → `Value not in list` / `Failed to convert`

#### 4.17.3 文件操作最佳实践

| 操作 | 推荐方式 | 避免方式 | 原因 |
|------|---------|---------|------|
| 跨盘文件复制 | Python `shutil.copy2` | PowerShell `Copy-Item` | PowerShell 路径白名单静默失败 |
| 二进制上传 | Python `requests` + `/upload/image` API | PowerShell multipart | 二进制处理不稳定，易 500 |
| 复制后验证 | 检查文件大小/修改时间 | 信任命令返回值 | PowerShell 可能返回成功但未更新 |

### 4.18 长视频色调/动作/拼接修复经验（2026-07-29 验证）

> 本节基于 SVI Pro 长视频工作流（`long_video_svi_pro_wan22_v1.0.0.json`）完整迭代验证，针对长视频（>5秒/多段拼接）场景的色调漂移、动作偏离、拼接渐变三大问题的系统化解决方案。完整复盘见 `EXPERIENCE.md` 第 24 章。

#### 4.18.1 长视频色调锚定方案（ColorMatch 硬性锚定）

**适用场景**：长视频（>5秒）、多段拼接、Flux2 换皮后颜色加深

**核心问题**：仅靠提示词约束无法防止多段 SVI Pro 生成的累积色调漂移，Flux2 换皮会引入额外色彩偏移

**解决方案**：两层色调防线

| 防线 | 机制 | 实现方式 | 适用场景 |
|------|------|---------|---------|
| 提示词约束（软性） | 文本引导控制色调 | 正向"保持暖色调，与参考图B色温一致"；负向"禁止变冷变白" | 短视频（≤5秒），色调偏移轻微 |
| ColorMatch 锚定（硬性） | 算法级颜色迁移 | 插入 `ColorMatch` 节点，`image_ref` 指向原参考图 | 长视频（>5秒），多段拼接，Flux2 换皮 |

**ColorMatch 节点参数梯度选择**：

| 参数 | 物理意义 | L1-L2（8-16GB） | L3（16-24GB） | L4（≥24GB） | 关键禁忌 |
|------|---------|-----------------|---------------|-------------|---------|
| `method` | 颜色迁移算法 | `reinhard`（平滑） | `reinhard`（平滑） | `reinhard` 或 `idt-matrix`（精确） | `mkl` 过于强烈，视频序列慎用 |
| `strength` | 锚定强度 | 0.7-0.8（轻度） | 0.85（强锚定） | 0.8-0.9（强锚定） | 1.0 完全匹配，丢失场景细节 |
| `image_ref` | 颜色参考源 | 原始参考图 | 原始参考图 | 原始参考图 | 禁止使用生成帧作为参考 |
| 部署数量 | 节点数 | 每段 SVI + Flux2 各 1 个 | 同左 | 同左 | 最少 5 个（仅 SVI），推荐 9 个（SVI+Flux2） |

**部署架构**：
```
参考图(LoadImage) ─────────────────────────┐
                                          ↓ (image_ref)
SVI Pro 段N VAEDecode 输出 → ColorMatch_N → 下游节点
Flux2 段N ImageResize 输出 → ColorMatch_N → 下游节点
```

**提示词色调约束原则**：
- 正向约束指定目标色调（"保持暖色调"）
- 负向约束禁止偏离方向（"禁止变冷变白"）
- 正负向提示词不可冲突（如正向要求暖色，负向禁止暖色溢色）
- 色调约束需明确参考基准（"与参考图B的色温保持一致"）

#### 4.18.2 Flux2 换皮动作保留方案

**适用场景**：Flux2 img2img 换皮修正（保留 SVI Pro 动作 + 替换外貌）

**核心问题**：`denoise` 参数过高破坏动作结构，过低换皮不彻底

**denoise 梯度分析（Flux2 换皮专用）**：

| denoise 值 | 修正力度 | 动作保留 | 外貌替换 | 适用场景 |
|-----------|---------|---------|---------|---------|
| 0.3-0.4 | 极弱 | 100% | 20% | 轻微色调调整 |
| 0.4-0.5 | 弱 | 90% | 50% | 降噪+色调统一 |
| 0.5-0.6 | 平衡 | 80% | 70% | **推荐区间**：平衡修正与动作保留 |
| **0.6** | **平衡** | **70%** | **80%** | **长视频任务验证值**：换皮充分且动作保留 |
| 0.7-0.8 | 强 | 50% | 90% | 明显瑕疵修复，动作可能偏离 |
| 0.8-1.0 | 极强 | 0% | 100% | 文生图模式，不适用于换皮场景 |

**关键禁忌**：
- `denoise < 0.3`：模型可操作空间不足，换皮无效
- `denoise > 0.7`：接近文生图，动作结构被破坏
- Flux2 换皮推荐区间 0.5-0.65（长视频任务验证 0.6 为最优平衡点）

**配套参数**：
- `SplitSigmasDenoise` 节点控制 denoise 参数
- A图（SVI末帧）缩放 0.5 MP，B图（参考图）缩放 1.0 MP
- 输出 Resize 至 SVI 分辨率（如 480×848），使用 lanczos + crop + center

#### 4.18.3 多段视频拼接模式选择

**适用场景**：SVI Pro 多段视频拼接、Flux2 修正后段间衔接

**核心问题**：`ImageBatchExtendWithOverlap` 的 `overlap_mode` 参数决定拼接方式，默认 `linear_blend` 产生渐变过渡

**overlap_mode 梯度分析**：

| overlap_mode | 效果 | 适用场景 | 帧数损失 | 用户感知 |
|-------------|------|---------|---------|---------|
| `linear_blend` | 渐变过渡，段间平滑融合 | 自然场景、动作连续 | overlap 帧 | 平滑过渡 |
| `cut` | 硬切拼接，无过渡 | 动作突变、用户要求直接拼接 | overlap-1 帧 | 直接切换 |
| `fade` | 淡入淡出，黑场过渡 | 场景切换、章节分隔 | overlap 帧 | 黑场过渡 |

**参数配置**：

| 参数 | 物理意义 | 推荐值 | 梯度建议 |
|------|---------|--------|---------|
| `overlap` | 重叠帧数 | 1（cut 模式）或 5（linear_blend） | 节点最小值为 1（不支持 0）；cut 模式下 overlap=1 等同直接拼接 |
| `overlap_side` | 重叠侧选择 | `new_images` | `new_images`: 新段；`source`: 前段 |
| `overlap_mode` | 拼接模式 | `cut`（直接拼接） | 根据用户需求选择 |

**关键禁忌**：
- `overlap=0` 不被节点支持（最小值为 1）
- 长视频分段拼接时，`overlap` 值过高会损失过多帧数（5 段 × overlap 5 = 损失 20 帧）

#### 4.18.4 长视频执行时间优化策略

**适用场景**：长视频工作流执行时间超出目标（如 >40 分钟）

**优化优先级**（按对画质影响从低到高排序）：

| 优先级 | 优化项 | 参数 | 影响维度 | 画质影响 |
|--------|--------|------|---------|---------|
| 1 | 旁路超分节点 | RealESRGAN | 耗时 -20% | 中间修正无影响，最终输出可再启用 |
| 2 | 降低 Flux2 修正步数 | `steps` 12→8 | 耗时 -15% | 轻微，修正力度略降 |
| 3 | 降低 SVI 采样步数 | `steps` 6→3 | 耗时 -30% | 蒸馏 LoRA 下可接受 |
| 4 | 降低每段帧数 | `length` 81→49 | 耗时 -25% + 时长 -25% | 需配合帧率调整保时长 |
| 5 | 降低帧率 | `frame_rate` 20→16 | 时长 +25% | 流畅度略降 |
| 6 | 降低分辨率 | 480×848 → 352×640 | 耗时 -30% | **最后手段**，画质显著下降 |

**关键禁忌**：
- 禁止降低分辨率保时长（分辨率直接影响画质）
- 禁止直接降帧数降时长（违反硬约束"禁止降级时长"）
- 优化后需验证视频时长是否达标（`总帧数 = 段数 × length - (段数-1) × overlap`）

#### 4.18.5 手部/肢体修复提示词方案

**适用场景**：Wan2.2 生成视频中人物手部变形、多余肢体、背景发红

**核心问题**：Wan2.2 模型在手部生成上存在固有缺陷，仅靠负向提示词无法完全避免

**双向约束原则**：
- 正向约束指定正确结构（"十指分明，两臂两腿"）
- 负向约束禁止错误结构（"多手指，三头六臂"）
- 肢体约束需明确数量（"两臂两腿"），避免模型生成中间状态

**SVI Pro 提示词模板**：
- 正向追加：`人物双手结构完整，十指分明，两臂两腿，肢体自然协调`
- 负向追加：`背景发红，红色色偏，多余的手指，手指融合，多臂，多余手臂，三头六臂，肢体残缺，手部变形，手指扭曲，关节反向，手掌融合`

**Flux2 修正提示词模板**：
- 正向追加：`修复手部结构确保十指完整分明关节自然，确保仅有两臂两腿无多余肢体；消除红色色偏禁止背景发红`
- 负向追加：`多手指，六指，手指扭曲，关节反向，手掌融合，手部变形，手指残缺；多余肢体，多臂，多余手臂，三头六臂，手臂残影，肢体残缺，肢体穿模，四肢扭曲；背景发红，红色色偏`

> **注**：本节提示词为针对特定问题修复的简单示例。完整的提示词编写方法论（含人物外貌 8 维度、场景物品 6 维度、动作控制 5 维度、镜头设计 18 种运镜、人物-场景-物品关系 5 层次描写）见 `EXPERIENCE.md` 第 24.7 节《提示词工程深度指南》。

#### 4.18.6 提示词工程完整方法论（引用）

> **本节为索引**，完整内容见 `EXPERIENCE.md` 第 24.7 节《提示词工程深度指南（Wan2.2 视频生成专用）》。

视频生成提示词质量直接决定画面表现力。本节提供完整的结构化提示词编写方法论，覆盖五大维度：

**维度一：提示词公式体系**（详见 `EXPERIENCE.md` 24.7.1）

| 公式类型 | 适用场景 | 公式 |
|---------|---------|------|
| 文生视频（T2V） | 从零生成 | 主体（描述）+ 场景（描述）+ 运动（描述）+ 美学控制 + 风格化 |
| 图生视频（I2V） | 基于参考图 | 运动 + 运镜 |
| 多镜头长视频 | 分段拼接 | [场景] + [镜头1](时长) + [镜头2](时长) + [转场] + [风格] |
| 运镜万能公式 | 所有类型 | 景别 + 运镜动作 + 速度方向 + 主体动作 + 环境细节 + 光影氛围 |

**核心方法论：分层写作法**（Wan2.2 实测最稳定，详见 `EXPERIENCE.md` 24.7.1）：

把混沌的一句话提示，拆解成三个可独立控制、又能协同发力的模块，三层之间有**主次、有逻辑、有视觉优先级**：

| 层级 | 核心问题 | 写作要求 |
|------|---------|---------|
| 第一层（主体） | 谁/什么在动？ | 唯一、具体、带基础动作的主谓结构短语 |
| 第二层（场景） | 它在哪？ | 单一空间+基础光照+简洁元素，不喧宾夺主 |
| 第三层（风格） | 它看起来像什么？ | 单一主导风格+1个强化项，不混搭 |

分层原则：①三层用英文逗号分隔，不加"和/与/以及"连接词；②主体层动作选"缓慢/轻柔/平稳"，避免"狂奔/爆炸"；③场景层光线词优先于装饰词；④风格层优先"设备+效果"组合（如"iPhone 15 Pro实拍"）；⑤中文四字短语触发准确率比英文高 35%。

**维度二：人物外貌描写**（详见 `EXPERIENCE.md` 24.7.2）

人物外貌需覆盖 8 个维度：面部五官、发型发色、服装服饰、体态身形、年龄气质、表情状态、配饰点缀、皮肤质感。每个维度提供梯度化描述词表。

**维度三：场景与物品描写**（详见 `EXPERIENCE.md` 24.7.3）

场景需覆盖 6 个维度：场景类型、时间段与光线、光源类型、光线质感、场景物品（含空间关系）、环境氛围。

**维度四：动作控制描写**（详见 `EXPERIENCE.md` 24.7.4）

动作需覆盖 5 个维度：动作幅度（静止→剧烈 6 级）、动作速率（极慢→极快 5 级）、动作连贯性（单一/连续/循环/过渡）、多人物动作关系（同步/互动/对抗/配合/独立）、动作与镜头配合（跟随/领先/环绕/固定）。

**动作描写进阶技巧**（解决动作不连贯、多人互动失败、首尾帧卡顿）：
- **时间逻辑词**：用"持续/缓缓/旋转着/被吹向"等带时间轴的动词短语替代"活泼/美丽/震撼"等抽象形容词，激活帧间变化建模
- **多人物分镜式描述**：Wan2.2 多人交互建模不完善，改用"特写：两只手从画面两侧伸入，击掌瞬间"聚焦局部，规避全身姿态建模
- **首尾帧稳定性**：提示词末尾追加"动作起始自然，结束平稳，无突兀跳变"，改善隐式扩散建模首尾帧弱的问题
- **单一动态焦点**：主体越少动作越细腻，多主体场景用"背景虚化"聚焦单一人物，还原布料褶皱等微观动态

**维度五：镜头设计**（详见 `EXPERIENCE.md` 24.7.5）

镜头设计包含三大要素：
- **景别**：大远景、远景、全景、中景、中近景、近景、特写、极特写（8 级）
- **机位角度**：平拍、仰拍、俯拍、鸟瞰、过肩、主观（6 种）
- **运镜动作**：18 种专业运镜（情绪推进、真相揭示、视线探索、平行追踪、沉浸跟随、空间升维、主角高光、压迫变焦、焦点转移、鹰眼俯冲、第一视角、一镜到底、纪录片、惊讶强化、对峙观察、极速追踪、失控眩晕、空间错位）

**核心方法论：人物-场景-物品关系描写**（详见 `EXPERIENCE.md` 24.7.6）

关系描写是提示词质量的核心区分点。初学者只描述"有什么"，专业提示词描述"之间有什么关系"。关系描写包含 5 个层次：

| 层次 | 类型 | 描写要点 | 示例 |
|------|------|---------|------|
| 1 | 空间关系 | 人物在场景中的方位、距离、朝向、相对高度 | 少女站在画面的右侧三分之一处 |
| 2 | 互动关系 | 人物与物品的物理交互（持有/接触/使用） | 右手轻轻扶着窗框，左手握着拿铁 |
| 3 | 情感关系 | 人物对场景/物品的情感投射 | 目光温柔地望向窗外的雨幕 |
| 4 | 因果关系 | 动作导致的环境变化 | 因为呼吸，玻璃窗凝结出雾气 |
| 5 | 多人物关系 | 人物之间的互动（主从/对等/对抗/阶层/情感） | 青年坐在角落安静地观察着她 |

**完整关系描写示例**（融合 5 个层次）：
```
中近景，平拍镜头。一位身着米白色丝绸连衣裙的少女站在复古咖啡馆的落地窗前（空间关系），右手轻轻扶着窗框，左手握着一杯尚冒热气的拿铁（互动关系）。她微微侧头，目光温柔地望向窗外的雨幕，嘴角带着淡淡的惆怅（情感关系）。因为她的呼吸，玻璃窗上凝结出一小片雾气，模糊了外面的街景（因果关系）。她身后三步远的地方，一位戴贝雷帽的青年正坐在角落的皮质沙发上，安静地观察着她（多人物关系），桌上摊开的书本已许久未翻动一页。暖黄色的吊灯在两人之间投下柔和的光晕，将这一刻定格成一幅静谧的油画。
```

**提示词编写禁忌**（详见 `EXPERIENCE.md` 24.7.8）

| 禁忌 | 原因 | 正确做法 |
|------|------|---------|
| 使用英文提示词 | Wan2.2 原生支持中文，英文理解不如中文 | 使用中文提示词 |
| 提示词超过 300 字 | 模型注意力分散，关键信息被稀释 | 图生视频≤100字，文生视频≤200字 |
| 包含 "360 orbit" 等运镜词 | 触发相机持续旋转，画面混乱 | 使用"镜头缓慢环绕"或"固定镜头" |
| 仅描述"有什么"不描述"关系" | 画面元素堆砌，缺乏叙事性 | 按 5 个层次描写关系 |
| 动作描述过于剧烈 | Wan2.2 对剧烈动作支持差，易变形 | 大幅度动作分段生成 |
| 正负向提示词冲突 | 模型收到矛盾信号 | 正向指定目标，负向禁止偏离 |
| 忽略景别描述 | 模型默认选择景别 | 明确指定景别 |
| 多人物未明确位置关系 | 位置混乱 | 明确"左边...右边..."或"前景...背景..." |
| 场景物品无空间锚定 | 物品漂浮感 | 描述物品与人物/场景的空间关系 |
| 忽略时间段与光源 | 色调不稳定 | 明确时间段和光源类型 |
| 词堆砌不分层 | 模型平权处理所有词，主体与背景抢焦点 | 按 24.7.1 分层写作法：主体层+场景层+风格层，英文逗号分隔 |
| 主体层用名词而非主谓结构 | 模型无法锁定焦点，主体漂移 | 主体必须是"带动作的主谓结构短语"（"蹲坐的橘猫，缓慢转头"） |
| 场景层堆砌装饰词 | 装饰词抢戏，光线词缺失致明暗混乱 | 场景层光线词优先，用"浅焦虚化"弱化背景 |
| 风格层混搭多种风格 | 逻辑冲突，无法统一视觉基调 | 单一主导+1个强化项（"胶片+轻微褪色"） |
| 用抽象形容词描述动作 | "活泼/美丽/震撼"不触发动作建模 | 用带时间轴的动词短语（"缓缓飘落""螺旋上升"） |
| 多人物直接写全身交互 | 多人交互建模不完善，人物消失或错位 | 改用分镜式局部描述（"特写：两只手击掌瞬间"） |
| 场景含动态干扰源 | 瀑布/喷泉/车流导致主体抖动 | 改为静态或远景（"瀑布远景""空旷街道"） |
| 忽略首尾帧稳定性 | 首尾帧弱，前 0.5 秒冻结或最后半秒跳变 | 末尾追加"动作起始自然，结束平稳，无突兀跳变" |

**完整提示词实战案例**（详见 `EXPERIENCE.md` 24.7.7）

5 个从零编写的完整案例，每个包含"失败提示词"与"优化提示词"对比，标注所用维度：
1. **文生视频·咖啡馆场景**：分层前后对比，激活时间维度建模
2. **文生视频·中国山水**：传统题材适配，东方美学权重
3. **图生视频·人物动作**：I2V 简化公式，运动+运镜
4. **多镜头长视频·产品展示**：分段公式 + 转场 + 连贯性锚点
5. **多人物互动·分镜式描述**：规避多人交互建模难点

## 5. 使用指南

### 5.1 技能模式使用示例

```bash
# 环境检查
python scripts/check_status.py

# 启动服务器
python scripts/start_server.py --port ${COMFYUI_PORT}

# 转换工作流格式
python scripts/workflow_converter.py --input web_format.json --output api_format.json

# 编辑工作流参数
python scripts/edit_workflow.py \
  --input api_format.json \
  --output edited.json \
  --positive-prompt "a beautiful landscape" \
  --width 1280 --height 720 \
  --steps 25 --cfg 7.5

# 执行工作流
python scripts/run_workflow.py --workflow edited.json --timeout 600

# 下载模型
python scripts/download_models.py \
  --base ~/ComfyUI \
  "https://huggingface.co/.../model.safetensors" \
  "https://civitai.com/api/download/models/12345 loras"

# 分析工作流依赖
python scripts/dependency_manager.py --workflow workflow.json --fix
```

### 5.2 CLI 模式使用示例

```bash
# 安装 ComfyUI
comfy install --gpu --fast-deps

# 启动服务器（后台）
comfy launch --background

# 执行工作流（NDJSON 输出）
comfy run workflow.json --json

# 安装自定义节点
comfy node install comfyui-manager --fast-deps

# 下载模型
comfy model download https://huggingface.co/.../model.safetensors

# 保存环境快照
comfy node save-snapshot my_snapshot.json

# 云端生成
comfy generate flux-pro --prompt "a cat"

# 依赖编译
comfy dependency --uv-compile
```

### 5.3 混合使用示例

```bash
# 1. 使用 CLI 安装 ComfyUI
comfy install --gpu

# 2. 使用技能脚本检查环境
python scripts/check_status.py

# 3. 使用 CLI 启动服务器
comfy launch --background

# 4. 使用技能脚本执行工作流
python scripts/run_workflow.py --workflow task.json --timeout 900

# 5. 使用 CLI 停止服务器
comfy stop
```

## 6. CLI 工作运行流程（标准操作程序）

### 6.1 完整 CLI 工作流执行流程

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: 环境检查                                                │
│  python scripts/check_status.py                                  │
│  - Python 版本 >= 3.10                                           │
│  - PyTorch + CUDA 可用                                           │
│  - GPU 显存 >= 8GB（视频生成）                                    │
│  - 所需自定义节点已安装                                           │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: 确认 ComfyUI 服务器状态                                  │
│  curl http://127.0.0.1:${COMFYUI_PORT}/system_stats                         │
│  - 如未运行，启动服务器                                           │
│  - 如端口冲突，使用 --port 指定新端口                              │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: 确认所需节点存在                                         │
│  curl http://127.0.0.1:${COMFYUI_PORT}/object_info | findstr "节点名"        │
│  - Wan 视频: 查找 "WanVideoSampler"                               │
│  - Flux 图片: 查找 "UNETLoader", "CLIPLoader"                     │
│  - 如缺失，安装对应自定义节点包                                    │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: 确认模型文件存在                                         │
│  ls ${COMFYUI_PATH}/models/checkpoints/ | findstr "模型关键词"    │
│  - 检查文件名是否完全匹配工作流中的 model 参数                      │
│  - 如使用 GGUF，确认 quantization: disabled                       │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: 工作流格式检查与转换                                      │
│  python -c "import json; json.load(open('workflow.json'))"       │
│  - 验证 JSON 格式合法                                             │
│  - 如为 UI 格式，先转换: python scripts/workflow_converter.py     │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5.5: 视频任务预检反问（强制不可跳过）                        │
│  仅视频任务需此步，图片任务可跳过                                  │
│  - 入口: scripts/pre_task_inquiry.py::run_pre_task_inquiry()     │
│  - 5 步反问: 模型查询→架构方案→生成参数→硬件检查→汇总确认         │
│  - 绕过路径警示: run_workflow.py 直接执行不经过预检                │
│  详见 4.9 节                                                     │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: 工作流参数编辑（可选）                                    │
│  python scripts/edit_workflow.py \                               │
│    --input workflow.json --output edited.json \                  │
│    --positive-prompt "新提示词" \                                 │
│    --width 480 --height 832 \                                    │
│    --steps 30 --cfg 5.0                                          │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 7: 执行工作流                                               │
│  视频任务推荐: python scripts/video_task_runner.py <task_type> \  │
│    --image input.png --prompt "..." (强制预检，结构化错误信息)     │
│                                                                  │
│  技能模式(无需结构化错误): python scripts/run_workflow.py \        │
│    --workflow edited.json --timeout 900                          │
│  注: run_workflow.py 默认 timeout=300s，视频任务需显式 --timeout   │
│      video_task_runner.py 默认 timeout=1800s                     │
│                                                                  │
│  CLI 模式: comfy run edited.json --json                          │
│                                                                  │
│  关键参数:                                                       │
│  - --timeout: 超时时间（秒），视频建议 900+                       │
│  - --poll: 轮询间隔（秒，默认 1.5）                               │
│  - --port: 服务器端口（默认 3198）                                │
│  注: run_workflow.py 默认等待完成，无需 --wait 参数               │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 8: 监控执行状态                                             │
│  - HTTP 轮询 /history/{prompt_id} 获取状态                        │
│    （run_workflow.py 内置，默认 poll 间隔 1.5 秒）                │
│  - 观察 GPU 显存占用（nvidia-smi）                                │
│  - 如卡死，检查: curl http://127.0.0.1:${COMFYUI_PORT}/queue                │
│  注: 项目脚本使用 HTTP 轮询而非 WebSocket                         │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 9: 结果验证                                                 │
│  - API 验证: curl http://127.0.0.1:${COMFYUI_PORT}/history/${PROMPT_ID}       │
│    校验 status.completed=true 且 outputs 含 images/gifs/videos   │
│  - 文件验证: 检查输出目录是否存在预期文件                         │
│  - 视频文件大小 > 0 且可播放                                     │
│  - 图片文件分辨率符合预期                                         │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 9.5: 服务清理与重启（连续任务硬约束）                        │
│  连续任务必须重启 ComfyUI，避免 30GB+ 显存残留导致下个任务 OOM      │
│  python scripts/controller.py stop                               │
│  python scripts/start_server.py --port ${COMFYUI_PORT}           │
│  - 硬约束: Consecutive tasks must restart ComfyUI                │
│  - 也可调用 /free API 清理历史与显存（次选）                      │
└──────────────────────────────────┬───────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 10: 错误处理与重试                                          │
│  如失败，按优先级调整（硬约束：禁止降级时长）:                     │
│  0. 重启 ComfyUI 服务（清除显存残留，OOM 类错误首选）              │
│  1. 降低步数 (30→20→15)                                          │
│  2. 启用/增加 BlockSwap                                          │
│  3. 降低分辨率（保持 16 倍数，可后续 X2 放大补偿）                  │
│  4. 降精度 (fp16_fast → bf16)                                    │
│  5. 分段生成+拼接（保持总时长，禁止直接降帧数）                     │
│  6. 更换更小模型（Q5_K_M → Q4_K_M）                               │
│  注: error_type=timeout 或服务无响应时强制重启服务                 │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 CLI 模式专用命令速查

| 任务 | 命令 | 说明 |
|------|------|------|
| 查看帮助 | `comfy --help` | 所有可用命令 |
| 环境信息 | `comfy env` | 打印 Python/CUDA/GPU 信息 |
| 安装 ComfyUI | `comfy install --gpu --fast-deps` | 自动检测 GPU，快速安装依赖 |
| 启动服务器 | `comfy launch --background` | 后台启动 |
| 停止服务器 | `comfy stop` | 停止后台进程 |
| 执行工作流 | `comfy run workflow.json --json` | NDJSON 输出 |
| 安装节点 | `comfy node install <name> --fast-deps` | 安装自定义节点 |
| 下载模型 | `comfy model download <url>` | 自动识别模型类型 |
| 保存快照 | `comfy node save-snapshot snap.json` | 保存环境状态 |
| 依赖编译 | `comfy dependency --uv-compile` | uv 编译依赖 |

### 6.3 关键 API 端点

| 端点 | 方法 | 用途 |
|------|------|------|
| `/prompt` | POST | 提交工作流 |
| `/queue` | GET/POST | 查看/清空队列 |
| `/history` | GET | 查看执行历史（含执行错误信息） |
| `/history/{prompt_id}` | GET | 查询特定任务状态和输出（视频输出可能出现在 `images`/`gifs`/`videos` 任一字段，**必须同时检查三个字段**，硬约束） |
| `/interrupt` | POST | 强制中断当前任务 |
| `/object_info` | GET | 获取所有节点类型信息 |
| `/object_info/{NodeType}` | GET | 查询特定节点的必需输入和枚举值（COMBO 参数必查） |
| `/system_stats` | GET | 获取系统状态（GPU 等） |
| `/upload/image` | POST | 上传文件到 input 目录（跨盘/权限受限时使用，multipart/form-data） |
| `/free` | POST | 释放模型缓存和显存（`{unload_models: true, free_memory: true}`） |

### 6.4 常见问题快速诊断

```bash
# 问题: 无法连接服务器
curl http://127.0.0.1:${COMFYUI_PORT}/system_stats
# 解决: 检查端口是否正确，服务器是否已启动

# 问题: 节点类型不存在
curl http://127.0.0.1:${COMFYUI_PORT}/object_info | findstr "WanVideo"
# 解决: 安装缺失的自定义节点包

# 问题: 模型不存在
ls ${COMFYUI_PATH}\models\checkpoints\
# 解决: 确认文件名完全匹配（含大小写）

# 问题: 显存不足
nvidia-smi
# 解决: 降低步数/帧数/分辨率，启用 offload

# 问题: 工作流卡死
curl http://127.0.0.1:${COMFYUI_PORT}/queue
curl -X POST http://127.0.0.1:${COMFYUI_PORT}/interrupt
# 解决: 强制中断后调整参数重试
```

## 7. 配置管理

### 7.1 环境变量
- `COMFYUI_PATH`: ComfyUI 安装路径
- `COMFYUI_HOST`: 服务器主机（默认 127.0.0.1）
- `COMFYUI_PORT`: 服务器端口（`run_workflow.py` 默认 3198；启动 ComfyUI 和执行工作流时端口必须一致）
- `COMFYUI_OUTPUT_DIR`: 输出目录

### 7.2 配置文件（CLI 模式）
- `config.ini`: 存储默认工作空间、Manager 模式、UV 编译默认值、后台进程信息
- `uv.lock`: uv 依赖锁定

### 7.3 工作空间管理
四级回退策略：
1. `--workspace` 参数指定
2. `--here` 当前目录
3. `--recent` 最近使用
4. 默认路径（`~/ComfyUI`）

## 8. 错误处理与故障排除

### 8.1 常见错误分类

| 错误类型 | 症状 | 解决方案 |
|----------|------|----------|
| `workflow_not_found` | 工作流文件不存在 | 检查文件路径 |
| `validation_error` | 节点参数错误 | 检查工作流 JSON |
| `execution_error` | 执行时出错 | 查看节点日志 |
| `timeout` | 执行超时 | 增加 `--timeout` 或降低参数 |
| `connection_error` | 无法连接服务器 | 检查服务器是否运行 |
| `out_of_memory` | 显存不足 | 降低步数/分辨率/启用 BlockSwap（禁止降帧数，见 8.2） |
| `model_not_found` | 模型不存在 | 检查模型路径或下载 |
| `node_not_found` | 节点类型不存在 | 安装缺失的自定义节点 |

### 8.2 OOM 处理策略（硬约束：禁止降级时长）
1. 降低采样步数（30→20→15）
2. 增加 BlockSwap blocks_to_swap
3. 降低分辨率（保持 16 的倍数，可后续 X2 放大补偿）
4. 降精度（fp16_fast → bf16）
5. 分段生成+拼接（保持总时长，禁止直接降帧数）
6. 最后手段：启用 CPU offload
7. **禁止**：直接降帧数（如 81→41→21），违反硬约束"禁止降级时长"

### 8.3 显存管理排错思路（C8 任务验证）

> 本节基于 C8 任务完整复盘（见 `EXPERIENCE.md` 第 23 章），针对显存管理问题的系统化排查方法。

#### 8.3.1 专用显存未充分利用（共享内存被大量使用）

**判断标准**：通过 `nvidia-smi` 监控，专用显存使用率低于 60% 但任务仍在执行，且共享 GPU 内存使用量持续增长。

**排查步骤**（按优先级）：

1. **检查 `blocks_to_swap` 参数**：值过高会导致 GPU 保留 block 过少。按硬件档位选择：
   - L1（8-12GB）：40-42
   - L2（12-16GB）：38-40
   - L3（16-24GB）：20-36（推荐 20，专用显存利用率 75%+）
   - L4（≥24GB）：20-24

2. **检查显存清理节点**：双模型架构必须在 HIGH→LOW 切换点插入显式清理节点（如 `PurgeVRAM V2`），仅依赖 `force_offload` 无法彻底释放显存。

3. **检查启动参数**：移除 `--disable-smart-memory` 和 `--disable-cuda-malloc`，使用默认智能内存管理。

4. **检查 `load_device` 参数**：模型加载器应设置 `load_device="offload_device"`，模型初始加载到 CPU，按需载入 GPU。

**三层显存管理防线**（必须同时启用）：
- **第一层**：`load_device="offload_device"` + `force_offload=true`（模型初始加载到 CPU，采样后强制卸载）
- **第二层**：显式显存清理节点 `PurgeVRAM V2`（在模型切换点彻底释放显存）
- **第三层**：`WanVideoBlockSwap` 分块卸载（采样过程中动态交换 transformer blocks）

#### 8.3.2 双模型同时加载导致 OOM

**判断标准**：HIGH 模型执行后显存未释放，LOW 模型加载时两个模型同时驻留显存。

**排查步骤**：

1. **检查节点链顺序**：确保 HIGH 采样器 → `PurgeVRAM V2` → LOW 采样器的串行执行顺序
2. **检查 `force_offload` 参数**：HIGH 和 LOW 采样器均设置 `force_offload=true`
3. **检查清理节点参数**：`PurgeVRAM V2` 的 `purge_cache` 和 `purge_models` 均设置为 `true`
4. **连续任务间重启**：单次任务完成后必须重启 ComfyUI 服务，避免显存残留

#### 8.3.3 采样器卡死判断

**判断标准**：采样器进度长时间无更新，无法区分正常计算与真正卡死。

**监控指标**（通过 `nvidia-smi` 或 GPU 监控工具）：

| 状态 | GPU 利用率 | 功耗 | 显存 | 判断 |
|------|-----------|------|------|------|
| 正常计算 | 100% | 接近满载（如 313W/320W） | 稳定 | 继续等待 |
| 真正卡死 | 0% 或波动大 | 低 | 持续不变 | 终止任务 |
| 内存碎片化 | 100% 但进度极慢 | 接近满载 | 持续增长 | 降低 `blocks_to_swap` |

**等待超时阈值**：单个采样步骤超过 5 分钟无进度更新才判定为卡死。

### 8.4 多图视频排错思路（C8 任务验证）

#### 8.4.1 视频只有单个人物（缺少第二张图元素）

**根本原因**：`WanVideoImageToVideoEncode` 的 `start_image` 只连接了单张图，而 `WanVideoClipVisionEncode` 的 `combine_embeds="concat"` 仅合并语义特征向量，非像素合并。

**关键认知**：
- `start_image`：决定视频起始帧的视觉内容（像素级锚定）
- `WanVideoClipVisionEncode`：提供语义引导（告诉模型画面里有什么人物/物体）
- `combine_embeds="concat"`：拼接的是 CLIP 视觉嵌入向量，不是像素

**解决方案**：使用 `ImageConcatMulti` 节点（来自 `ComfyUI-KJNodes`）将多张图水平/垂直拼接成一张，作为 `start_image`。

**节点链架构**：
```
LoadImage(1.png) → ImageScale ─┐
                               ├─→ ImageConcatMulti(direction="right") ──→ WanVideoImageToVideoEncode.start_image
LoadImage(2.png) → ImageScale ─┘
                               (同时仍分别送入 WanVideoClipVisionEncode.image_1/image_2)
```

**分辨率调整原则**：两张图水平拼接后宽度翻倍，`WanVideoImageToVideoEncode` 的 `width`/`height` 必须设置为拼接后的实际尺寸，否则会被强制缩放导致变形。

#### 8.4.2 多图视频中人物位置混乱

**根本原因**：提示词未明确每个人物的位置关系。

**解决方案**：提示词明确描述位置关系，如"左边女孩来自参考图1，右边女孩来自参考图2"。

**多图视频提示词原则**：
- 明确每个人物的位置（左/右/前/后）
- 明确人物间的关系（手拉手/面对面/并排）
- 保持 CLIP Vision 双图编码（提供角色一致性引导）

### 8.5 提示词排错思路（C8 任务验证）

#### 8.5.1 画面混乱/相机乱转

**根本原因**：提示词包含 "360 orbit"、"slow orbit camera shot" 等运镜词，Wan2.2 对运镜描述极敏感。

**解决方案**：删除所有运镜词，改为"固定镜头"或"画面稳定"。

**运镜描述选择指南**：
- **静态场景**：固定镜头、画面稳定
- **推进场景**：镜头缓慢推进
- **禁止使用**：360 orbit、camera spin、rotating shot（会导致画面混乱）

#### 8.5.2 提示词过于冗长

**根本原因**：误认为描述越详细生成质量越高，实际相反，冗长的提示词会让模型困惑。

**解决方案**：精简到 60 字符以内，遵循图生视频公式：`运动 + 运镜`。

**Wan2.2 提示词公式**：
- **基础公式**：`主体 + 场景 + 运动`
- **进阶公式**：`主体（主体描述）+ 场景（场景描述）+ 运动（运动描述）+ 美学控制 + 风格化`
- **图生视频公式**：`运动 + 运镜`（图已确定主体、场景与风格，提示词主要描述动态过程）

#### 8.5.3 负面提示词不完整

**解决方案**：按任务类型补充完整负面提示词，覆盖以下类别：
- **相机运动**（固定相机场景）：`camera movement, camera pan, camera tilt, camera zoom, camera dolly, camera shake, 360 orbit, spinning, rotating, 视角突变, 镜头移动, 运镜`
- **人物一致性**（多图视频）：`face changing, character drift, inconsistent appearance, 人物消失, 人物突变`
- **画面问题**：`motion blur, frame skipping, distorted body, deformed limbs, 单人镜头, 背景变化, 场景切换, 多余人物, 缺失人物`
- **基础负面**：`静态, 模糊, 低质量, 最差质量, JPEG压缩残留, 丑陋, 残缺, 畸形, 毁容`

### 8.6 启动脚本排错思路（C8 任务验证）

#### 8.6.1 白名单参数格式错误

**现象**：`--whitelist-custom-nodes` 参数使用逗号分隔字符串，导致白名单未生效。

**解决方案**：每个节点名作为独立参数传入，使用空格分隔。

#### 8.6.2 sageattention DLL 加载失败

**现象**：`Windows fatal exception: code 0xc0000139`，DLL 加载失败。

**解决方案**：将 `attention_mode` 从 `sageattn` 改为 `sdpa`（PyTorch 原生注意力机制）。

#### 8.6.3 自定义节点加载崩溃

**现象**：Manager 联网超时崩溃、Impact-Pack 加载卡住。

**解决方案**：使用 `--disable-all-custom-nodes` + `--whitelist-custom-nodes` 白名单模式，仅加载任务必需节点。

**白名单节点清单**（按任务必需性分级）：
- **视频任务必需**：`ComfyUI-WanVideoWrapper`（核心视频节点）、`ComfyUI-VideoHelperSuite`（视频合成）、`ComfyUI-KJNodes`（辅助节点，提供 `ImageConcatMulti` 等）
- **视频任务推荐**：`comfyui-frame-interpolation`（插帧）、`comfyui-essentials`（图像处理）
- **显存管理必需**：`ComfyUI_LayerStyle`（提供 `PurgeVRAM V2` 节点）

### 8.7 通用排错流程（C8 任务验证的 6 步法）

> 基于 C8 任务完整复盘，针对任何 ComfyUI 任务执行问题的系统化排查方法。

**Step 1：确认问题现象**
- 明确问题的具体表现（卡死/OOM/画面错误/执行超时）
- 记录问题发生时的节点和参数

**Step 2：检查硬件资源**
- `nvidia-smi` 查看 GPU 利用率、显存使用、功耗
- 判断是显存不足、专用显存未利用、还是真正卡死

**Step 3：检查工作流参数**
- 对照硬件档位表确认参数合理性（参考 `EXPERIENCE.md` 第 21 章参数梯度表）
- 重点检查：`blocks_to_swap`、`steps`、`num_frames`、`cfg`、`resolution`

**Step 4：检查节点链架构**
- 确认节点链顺序正确（如 `WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler`）
- 检查必填参数是否完整（如 `riflex_freq_index`、`precision`）

**Step 5：检查显存管理**
- 确认三层显存管理防线是否启用（`force_offload` + `PurgeVRAM` + `blocks_to_swap`）
- 双模型架构是否串行执行（HIGH→PurgeVRAM→LOW）

**Step 6：借鉴本地成熟工作流**
- 查找本地已有的成熟工作流作为参考
- 不要从零开始配置，先复用验证过的配置

**详细排错案例参考**：`EXPERIENCE.md` 第 23 章 C8 多图视频生成完整任务复盘。

### 8.8 长视频排错思路（2026-07-29 长视频任务验证）

> 本节基于 SVI Pro 长视频工作流完整迭代验证，针对长视频（>5秒/多段拼接）场景的色调漂移、动作偏离、拼接渐变三大问题的系统化排查方法。完整复盘见 `EXPERIENCE.md` 第 24 章。

#### 8.8.1 色调逐渐变冷/变白/偏离参考图

**判断标准**：视频生成过程中色调随时间逐渐偏离原始参考图，或 Flux2 修正后颜色比参考图加深。

**排查步骤**：

1. **检查提示词约束**：
   - 正向提示词是否指定目标色调（如"保持暖色调，与参考图B色温一致"）
   - 负向提示词是否禁止偏离方向（如"禁止变冷变白"）
   - 正负向是否冲突（如正向暖色 + 负向禁止暖色溢色 = 冲突）

2. **检查 ColorMatch 节点部署**：
   - 长视频（>5秒/多段）必须部署 `ColorMatch` 节点
   - 每个 SVI VAEDecode 输出后、每个 Flux2 ImageResize 输出后各部署 1 个
   - 所有节点的 `image_ref` 必须指向同一张原始参考图（禁止使用生成帧）

3. **检查 ColorMatch 参数**：
   - `method` 推荐 `reinhard`（平滑过渡，适合视频序列）
   - `strength` 推荐 0.8-0.9（强锚定，防止多段累积漂移）
   - L1-L2 硬件可降至 0.7-0.8（减少计算开销）

#### 8.8.2 Flux2 换皮后动作偏离原始截图

**判断标准**：Flux2 修正后角色动作未完全参照 SVI Pro 生成的原始截图动作。

**排查步骤**：

1. **检查 denoise 参数**：
   - `SplitSigmasDenoise` 的 `denoise` 值是否在推荐区间 0.5-0.65
   - 长视频任务验证最优值为 0.6
   - `denoise > 0.7` 会导致动作结构被破坏

2. **检查 A/B 图来源**：
   - A图应为 SVI Pro 末帧（动作来源）
   - B图应为原始参考图（外貌来源）
   - A图缩放 0.5 MP，B图缩放 1.0 MP

3. **检查提示词约束**：
   - 正向提示词是否包含"严格保留输入帧中人物的动作姿态"
   - 负向提示词是否包含"改变动作姿态，改变面部表情"

#### 8.8.3 视频段拼接处存在渐变过渡

**判断标准**：多段视频拼接处出现明显的渐变过渡，用户要求直接拼接。

**排查步骤**：

1. **检查 ImageBatchExtendWithOverlap 参数**：
   - `overlap_mode` 是否为 `cut`（直接切换，无渐变）
   - `overlap` 是否为 1（节点最小值，不支持 0）
   - 默认 `linear_blend` 会产生渐变过渡

2. **检查 overlap 值合理性**：
   - `overlap` 过高会损失过多帧数（5 段 × overlap 5 = 损失 20 帧）
   - `cut` 模式下 `overlap=1` 等同直接拼接

3. **根据场景选择模式**：
   - `linear_blend`：自然场景、动作连续（渐变过渡）
   - `cut`：动作突变、用户要求直接拼接（硬切）
   - `fade`：场景切换、章节分隔（黑场过渡）

#### 8.8.4 长视频执行时间过长

**判断标准**：长视频工作流执行时间超出目标（如 >40 分钟）。

**排查步骤**（按优化优先级）：

1. **旁路超分节点**：RealESRGAN 等超分节点在中间修正阶段旁路，最终输出再启用
2. **降低 Flux2 修正步数**：`steps` 从 12 降至 8（轻量修正）
3. **降低 SVI 采样步数**：`steps` 从 6 降至 3（蒸馏 LoRA 下可接受）
4. **调整帧数/帧率（需用户确认目标时长）**：`length` 从 81 降至 49，`frame_rate` 从 20 降至 16
   - ⚠️ **此操作会降低时长约 25%（20.05s → 15.06s），非"保时长"**
   - 必须先与用户确认目标时长可接受后方可执行
   - 计算公式：`总时长 = (段数 × length - (段数-1) × overlap) / frame_rate`
5. **最后手段：降低分辨率**：仅在以上优化仍不达标时使用

**关键禁忌**：
- 禁止降低分辨率保时长（分辨率直接影响画质）
- 禁止直接降帧数降时长（违反硬约束"禁止降级时长"）—— 如需降低时长必须经用户明确授权
- 优化后需验证视频时长：`总帧数 = 段数 × length - (段数-1) × overlap`

#### 8.8.5 工作流加载报错 `TypeError: can't convert undefined to object`

**判断标准**：ComfyUI 0.27.0+ 加载工作流时报此错误。

**排查步骤**：

1. **检查 group 格式**：
   - 是否使用 `bounding: [x, y, w, h]` 数组格式（旧版 `pos+size` 不兼容）
   - 是否包含 `id` 字段（唯一标识）
   - 是否包含 `flags: {}` 字段

2. **group 格式规范**（ComfyUI 0.27.0+）：
   ```json
   {
     "id": 1,
     "title": "段1-SVI Pro",
     "bounding": [100, 200, 300, 400],
     "flags": {}
   }
   ```

3. **批量转换**：编写脚本自动将所有 group 从旧格式转换为新格式

**详细排错案例参考**：`EXPERIENCE.md` 第 24 章长视频工作流优化与三大问题修复复盘。

## 9. 扩展与开发

### 9.1 添加新脚本
在 `scripts/` 目录下创建新的 Python 脚本，遵循以下规范：
- 使用 `argparse` 处理命令行参数
- 输出 JSON 格式结果（`{"ok": true/false, ...}`）
- 支持环境变量配置
- 包含详细的错误处理

### 9.2 添加新 CLI 命令
在 `cli/command/` 目录下创建新的子模块，遵循以下规范：
- 使用 `typer` 框架定义命令
- 继承 `ClickException` 处理错误
- 支持 `--json` 输出
- 集成追踪分析（Mixpanel/PostHog）

### 9.3 注册表发布
使用 `comfy node publish` 将自定义节点发布到 ComfyUI Registry：
- 需要注册表 API Token
- 自动验证节点结构
- 支持版本管理

## 10. 测试

### 10.1 测试方式
本项目不设独立 tests/ 目录，测试通过以下方式验证：
- 脚本内联断言验证（如 `build_workflow_library.py` 的 `--update` 自检）
- 实际任务执行验证（C2-C6 系列任务脚本作为端到端验证）
- `docs_cli/TESTING-e2e.md` 记录 E2E 测试要点

### 10.2 E2E 测试要点（参考文档）
- 使用真实包和冲突 fixture 包
- 渐进式冲突测试
- 配置默认测试
- 环境变量隔离

## 11. 资源下载

### 11.1 ComfyUI 资源获取

ComfyUI 资源（整合包、模型、自定义节点、工作流模板）请通过以下官方渠道获取：
- ComfyUI 官方仓库（见 11.2 节）
- ComfyUI-Manager 内置安装器
- HuggingFace / CivitAI 模型库

**注**：本技能文档不绑定特定整合包或网盘资源，避免链接失效和设备特定依赖。

### 11.2 官方资源

- ComfyUI 官方仓库: https://github.com/comfyanonymous/ComfyUI
- ComfyUI-Manager: https://github.com/ltdrdata/ComfyUI-Manager
- ComfyUI-WanVideoWrapper: https://github.com/kijai/ComfyUI-WanVideoWrapper

## 12. 许可证与归属

- 本项目融合了 `comfy-cli`（ComfyUI 官方 CLI）和 `comfyui-controller`（社区自动化工具）的功能
- `comfy-cli` 相关代码遵循其原始许可证
- `comfyui-controller` 相关代码遵循其原始许可证
- 融合后的架构文档和 README 为原创内容

**作者**：liuda1999
**QQ 群**：336439290
