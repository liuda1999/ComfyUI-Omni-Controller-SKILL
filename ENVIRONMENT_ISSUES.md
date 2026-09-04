# ⚠️ 历史存档 — ComfyUI 环境问题记录（D:\2026-ComfyUI-V8.3）

> **本文件为历史存档（2026-07-08 早期记录）。切勿以本文档中的端口、启动参数指导当前任务执行。**
>
> 当前环境标准：
> - 端口：**3198**
> - 启动模式：白名单模式（`--whitelist-custom-nodes` + `--disable-all-custom-nodes`）
> - output目录：`--output-directory E:\comfyui-cli\output`
> - 标准启动命令：见 `.trae/skills/video-task-execution-guide/SKILL.md` 检查1
>
> 本文档中"可用资源"一节（SAM3模型清单等）可能仍有参考价值，但环境配置和启动参数已全部过时。

测试日期：2026-07-08（原始记录）
服务器：ComfyUI v0.27.0, Python 3.12.9, 端口 8189（因 8188 被占用，**当前标准端口为 3198**）
启动参数：`--disable-all-custom-nodes --port 8189`（**已过时，当前使用白名单模式**）

## 环境问题（按用户要求不修改 ComfyUI，仅记录）

### 1. output 目录权限拒绝
- **现象**：SaveImage 节点报 `[Errno 13] Permission denied: 'D:\2026-ComfyUI-V8.3\output\CLI_TEST_00001_.png'`
- **影响**：所有需要保存图片的工作流无法完成
- **原因**：output 目录权限配置问题
- **解决方案（2026-07-21 验证）**：启动时添加 `--output-directory E:\comfyui-cli\output --temp-directory E:\comfyui-cli\temp`

### 2. ComfyUI 数据库权限错误
- **现象**：启动时报 `[ERROR] Failed to initialize database... [Errno 13] Permission denied: 'D:\2026-ComfyUI-V8.3\user\comfyui.db.bkp'`
- **影响**：数据库备份失败，但服务器仍可正常运行

### 3. SAM3 模型不是标准 SD checkpoint
- **现象**：`sam3.1_multiplex_fp16.safetensors` 作为 CheckpointLoaderSimple 加载后，KSampler 报 `SAM3Model.forward() takes 2 positional arguments but 3 were given`
- **影响**：该模型不能用于标准 txt2img/img2img 工作流
- **可用 checkpoint**：仅 `v1-5-pruned-emaonly.safetensors` 可用于标准 SD 工作流

### 4. 端口 8188 被占用
- **现象**：默认端口 8188 被进程 102100 (python.exe) 占用且无响应
- **处理**：使用端口 8189 启动新实例（**当前项目标准端口为 3198**）

## 可用资源
- checkpoints: sam3.1_multiplex_fp16.safetensors, v1-5-pruned-emaonly.safetensors
- 本地模型文件总数: 35
- 自定义节点: 已用 --disable-all-custom-nodes 跳过（**当前使用白名单模式加载 WanVideo 节点**）
