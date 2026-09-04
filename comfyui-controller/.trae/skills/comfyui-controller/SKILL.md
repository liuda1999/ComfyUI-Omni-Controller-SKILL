---
name: "comfyui-controller"
description: "ComfyUI 全能控制器技能包。支持自然语言驱动的图片/视频生成工作流构建与执行、ComfyUI 生命周期管理（安装/启动/停止/环境检查）、节点与模型管理、工作流仓库。当用户需要通过命令行或 AI Agent 控制 ComfyUI 生成图片/视频、管理 ComfyUI 环境时调用。"
---

# ComfyUI 全能控制器 (ComfyUI Omni-Controller) — 技能入口

> **本文件是技能包的入口（SKILL.md）**。完整功能文档与知识库在主文档 [SKILL.md](../../../SKILL.md)，本入口用于技能加载与快速导航。

## 0. 智能体快速导航（AI Agent Quick Nav）

> **如果你是 AI 智能体，加载本技能后按以下路径使用。不要从头到尾通读。**

### 0.1 本技能能做什么

| 能力 | 一句话描述 | 详细入口 |
|------|-----------|---------|
| **图片生成** | Flux2/Flux1/SD1.5/SDXL 文生图、图生图、放大 | [主 SKILL.md §4.1/4.4](../../../SKILL.md) + [图片任务预检技能](../../../../.trae/skills/image-task-execution-guide/SKILL.md) |
| **视频生成** | 6 种任务类型（图生视频/首尾帧/多图/长视频/拼接/多参考） | [主 SKILL.md §4.2/4.3](../../../SKILL.md) + [视频任务预检技能](../../../../.trae/skills/video-task-execution-guide/SKILL.md) |
| **工作流执行** | UI/API 双格式提交、监控、错误分类 | [主 SKILL.md §6](../../../SKILL.md) |
| **生命周期管理** | 安装/启动/停止/环境检查/节点/模型 | [主 SKILL.md §3/§5](../../../SKILL.md) |
| **工作流仓库** | 扫描/分类/查询/模式复用 | [主 SKILL.md §3.1.9](../../../SKILL.md) + [assets/workflow_library.json](assets/workflow_library.json) |

### 0.2 使用三步法

1. **定位文档**：先查 [docs_cli/INDEX.md 快速索引](../../../docs_cli/INDEX.md)（主题速查 + 章节行号导航）
2. **查完整知识**：主文档 [SKILL.md](../../../SKILL.md)（功能映射 + 工作流知识库）
3. **查迭代经验**：[docs_cli/EXPERIENCE.md](../../../docs_cli/EXPERIENCE.md)（24 章问题排查 + 参数梯度）

### 0.3 安装为技能（两种方式）

**方式 A — 作为 Trae/IDE 技能使用**：将本仓库放入工作区，智能体自动扫描 `.trae/skills/` 识别本技能与图片/视频预检技能。

**方式 B — 作为 CLI 插件使用**：

```bash
git clone https://github.com/liuda1999/ComfyUI-Omni-Controller-SKILL.git
cd ComfyUI-Omni-Controller-SKILL/comfyui-controller
pip install -e cli/        # 安装 comfy-cli 命令
python scripts/check_status.py   # 环境检查
```

---

## 1. 技能包结构

```
.trae/skills/comfyui-controller/
├── SKILL.md                        # 本文件（技能入口）
└── assets/
    ├── workflow_library.json       # 工作流资源库（自动扫描/分类/模式）
    └── workflow_patterns.json      # 工作流模式库（任务类别×模型系列）
```

配套文档（位于本技能目录上层）：

| 文档 | 路径 | 说明 |
|------|------|------|
| 主文档 | [comfyui-controller/SKILL.md](../../../SKILL.md) | 完整功能映射 + 工作流知识库（图片/视频/参数/禁忌/排错） |
| 快速索引 | [docs_cli/INDEX.md](../../../docs_cli/INDEX.md) | 全量经验/技术文档统一检索入口 |
| 迭代经验 | [docs_cli/EXPERIENCE.md](../../../docs_cli/EXPERIENCE.md) | 24 章问题排查 + 参数梯度分析 + 提示词工程 |
| 采样器手册 | [SKILL.md §4.19](../../../SKILL.md) | K 采样器完全参考手册（ComfyUI 全家族，独立章节） |
| 双实例调参 | [docs_cli/wan22_dual_instance_tuning_guide.md](../../../docs_cli/wan22_dual_instance_tuning_guide.md) | Wan2.2 双卡视频生成调参 |
| 图片预检 | [.trae/skills/image-task-execution-guide/SKILL.md](../../../../.trae/skills/image-task-execution-guide/SKILL.md) | 图片任务 5 项强制预检 |
| 视频预检 | [.trae/skills/video-task-execution-guide/SKILL.md](../../../../.trae/skills/video-task-execution-guide/SKILL.md) | 视频任务 6 项强制预检 |

---

## 2. 核心工作流速查

### 2.1 图片生成（自然语言驱动）

1. 预检反问：[图片预检技能](../../../../.trae/skills/image-task-execution-guide/SKILL.md)（服务/模型/节点/硬件/提示词 5 项）
2. 架构选择：按模型系列（Flux2/Flux1/SD1.5/SDXL）→ [主 SKILL.md §4.4](../../../SKILL.md)
3. 构建工作流：[scripts/advanced_workflow_builder.py](../../../scripts/advanced_workflow_builder.py)
4. 执行：[scripts/run_workflow.py](../../../scripts/run_workflow.py)

### 2.2 视频生成（自然语言驱动）

1. 预检反问：[视频预检技能](../../../../.trae/skills/video-task-execution-guide/SKILL.md)（6 项强制检查）
2. 一键执行：[scripts/video_task_runner.py](../../../scripts/video_task_runner.py) `img2vid|first_last_frame|multi_image_video|long_video|video_concat|multi_ref_video`
3. 硬件自适应：显存四档（L1-L4）自动推荐参数

---

## 3. 强制约束（硬约束，不可违反）

- **预检反问不可跳过**：图片 5 项 / 视频 6 项，即使用户给出完整提示词
- **禁止共享 GPU 显存**：专用显存足够时严禁使用共享显存
- **禁止跨系列混用模型组件**（Wan2.2/Flux/SD1.5/SDXL）
- **连续任务必须重启 ComfyUI**，避免显存残留导致 OOM
- **视频输出识别**：/history 的 images/gifs/videos 三字段必须同时检查

---

## 4. 排错入口

| 问题 | 快速入口 |
|------|---------|
| 通用排查 | [docs_cli/INDEX.md §2.10](../../../docs_cli/INDEX.md) + [EXPERIENCE.md §10/14](../../../docs_cli/EXPERIENCE.md) |
| OOM/显存 | [EXPERIENCE.md §7/23.6](../../../docs_cli/EXPERIENCE.md) + [主 SKILL.md §8.2/8.3](../../../SKILL.md) |
| 参数选择 | [EXPERIENCE.md §21](../../../docs_cli/EXPERIENCE.md) 参数梯度矩阵 |
| 长视频问题 | [主 SKILL.md §8.8](../../../SKILL.md) + [EXPERIENCE.md §24](../../../docs_cli/EXPERIENCE.md) |

---

*技能版本：v0.1.0 | 许可证：Apache-2.0 | 配套工作流库见 [assets/workflow_library.json](assets/workflow_library.json)*
