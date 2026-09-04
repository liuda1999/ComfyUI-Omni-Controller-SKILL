# ComfyUI Omni-Controller 项目经验与问题排查记录

> 记录使用 CLI 运行项目过程中遇到的所有问题、原因分析与解决方案，供后续高效参考。
> 作者：liuhongxiang | QQ群：336439290

---

## 目录

1. [模块导入与命名冲突](#1-模块导入与命名冲突)
2. [依赖缺失问题](#2-依赖缺失问题)
3. [HTTP 请求与 API 调用问题](#3-http-请求与-api-调用问题)
4. [工作流执行卡死/无响应](#4-工作流执行卡死无响应)
5. [模型加载与量化问题](#5-模型加载与量化问题)
6. [节点类型不匹配问题](#6-节点类型不匹配问题)
7. [显存不足 (OOM) 问题](#7-显存不足-oom-问题)
8. [CLI 交互式命令问题](#8-cli-交互式命令问题)
9. [工作流参数与质量问题](#9-工作流参数与质量问题)
10. [通用排查流程](#10-通用排查流程)
11. [C2 任务启动问题总结（2026-07-21）](#11-c2-任务启动问题总结2026-07-21)
12. [C5 多图视频生成迭代经验（2026-07-22）](#12-c5-多图视频生成迭代经验2026-07-22)
13. [基础功能验证经验（2026-07-22）](#13-基础功能验证经验2026-07-22)
14. [C6 单图视频生成排查经验与问题解决流程（2026-07-23）](#14-c6-单图视频生成排查经验与问题解决流程2026-07-23)
15. [SVI Pro 长视频工作流架构分析（2026-07-24）](#15-svi-pro-长视频工作流架构分析2026-07-24)
16. [C7 任务低噪声画质模糊根因分析（2026-07-24）](#16-c7-任务低噪声画质模糊根因分析2026-07-24)
17. [C7 v12 Flux2 双图修正工作流优化经验（2026-07-25）](#17-c7-v12-flux2-双图修正工作流优化经验2026-07-25)
18. [C7 SVI Pro 段间连贯性与色调优化（2026-07-25）](#18-c7-svi-pro-段间连贯性与色调优化2026-07-25)
19. [KSamplerAdvanced 参数对齐问题（2026-07-25）](#19-ksampleradvanced-参数对齐问题2026-07-25)
20. [文件操作与环境恢复经验（2026-07-25）](#20-文件操作与环境恢复经验2026-07-25)
21. [参数梯度分析与场景化选择指南（2026-07-26）](#21-参数梯度分析与场景化选择指南2026-07-26)
22. [多图/长视频节点详解与场景化分析（2026-07-26）](#22-多图长视频节点详解与场景化分析2026-07-26)
23. [C8 多图视频生成完整任务复盘（2026-07-28）](#23-c8-多图视频生成完整任务复盘2026-07-28)
24. [长视频工作流优化与三大问题修复复盘（2026-07-29）](#24-长视频工作流优化与三大问题修复复盘2026-07-29)

---

## 1. 模块导入与命名冲突

### 1.1 `comfy_cli` 包名未适配

**现象**：
```
ModuleNotFoundError: No module named 'comfy_cli'
```

**原因**：从 comfy-cli 拷贝的代码使用 `comfy_cli` 作为包名，但项目目录命名为 `cli`。

**解决**：全局替换 `comfy_cli` → `cli`，涉及 30+ 个文件。

**关键文件**：
- `cli/cmdline.py`
- `cli/command/run.py`
- `cli/config_manager.py`
- `cli/workspace_manager.py`
- 所有子模块的 import 语句

---

### 1.2 `typing.py` 与 Python 标准库冲突

**现象**：
```
ImportError: cannot import name 'Annotated' from 'typing'
```

**原因**：`cli/typing.py` 与 Python 标准库 `typing` 同名，导致导入时优先加载本地文件而非标准库。

**解决**：
1. 将 `cli/typing.py` 重命名为 `cli/typing_compat.py`
2. 更新所有引用：`from cli.typing import ...` → `from cli.typing_compat import ...`

**涉及文件**：
- `cli/typing_compat.py`（原 typing.py）
- `cli/cmdline.py`
- `cli/ui.py`
- `cli/env_checker.py`
- 其他引用 `cli.typing` 的模块

---

### 1.3 `logging.py` 与 Python 标准库冲突

**现象**：
```
AttributeError: module 'logging' has no attribute 'getLogger'
```

**原因**：`cli/logging.py` 与 Python 标准库 `logging` 同名。

**解决**：
1. 将 `cli/logging.py` 重命名为 `cli/logging_utils.py`
2. 更新所有导入引用
3. **注意**：`logging_utils.py` 内部不能引用自身，需将内部调用改回 `logging.debug()` 等标准库调用

**涉及文件**：
- `cli/logging_utils.py`（原 logging.py）
- `cli/cmdline.py`（Line 12, 30）
- `cli/update.py`

---

### 1.4 循环引用问题

**现象**：
```
NameError: name 'logging_utils' is not defined
```

**原因**：`logging_utils.py` 内部尝试引用自身模块。

**解决**：将 `logging_utils.py` 内部的日志调用改为直接使用 Python 标准库 `logging` 模块。

---

## 2. 依赖缺失问题

### 2.1 未安装 comfy-cli 包导致元数据获取失败

**现象**：
```
importlib.metadata.PackageNotFoundError: No package metadata was found for comfy-cli
```

**原因**：代码尝试通过 `metadata("comfy-cli")` 获取版本，但 comfy-cli 未作为包安装。

**解决**：在 `cli/update.py` 和 `cli/config_manager.py` 中添加 try/except 保护：

```python
def get_version_from_pyproject():
    try:
        package_metadata = metadata("comfy-cli")
        return package_metadata["Version"]
    except Exception:
        return "0.0.0"
```

---

### 2.2 第三方依赖缺失

**现象**：
```
ModuleNotFoundError: No module named 'questionary'
ModuleNotFoundError: No module named 'mixpanel'
ModuleNotFoundError: No module named 'pathspec'
ModuleNotFoundError: No module named 'tomlkit'
ModuleNotFoundError: No module named 'semver'
ModuleNotFoundError: No module named 'websocket'
```

**解决**：逐个安装缺失依赖：

```bash
pip install questionary mixpanel pathspec tomlkit semver websocket-client
```

**建议**：项目应维护完整的 `requirements.txt`，包含所有 CLI 模式依赖。

---

## 3. HTTP 请求与 API 调用问题

### 3.1 POST 请求缺少 headers 和 method

**现象**：
```
HTTP Error 400: Bad Request
```

**原因**：`cli/command/run.py` 的 `queue()` 方法中，`urllib.request.Request` 未设置 `Content-Type: application/json` 和 `method="POST"`。

**解决**：修复 `cli/command/run.py` Line 584-587：

```python
def queue(self):
    data: dict = {"prompt": self.workflow, "client_id": self.client_id}
    if self.api_key:
        data["extra_data"] = {"api_key_comfy_org": self.api_key}
    payload = json.dumps(data).encode("utf-8")
    req = request.Request(
        f"http://{self.host}:{self.port}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
```

---

## 4. 工作流执行卡死/无响应

### 4.1 工作流长时间无响应，后台资源无调度

**现象**：提交工作流后，ComfyUI 服务器接受请求但无执行进度，GPU/CPU 无负载。

**可能原因与排查**：

1. **节点类型错误**：使用了通用节点（如 `KSamplerAdvanced`）而不是视频模型专用节点（如 `WanVideoSampler`）
2. **模型路径错误**：模型文件名不匹配，导致节点无法加载模型
3. **节点缺失**：ComfyUI 实例未安装所需的自定义节点包（如 `ComfyUI-WanVideoWrapper`）
4. **服务器假死**：ComfyUI 前端卡住，后端实际仍在运行

**排查步骤**：
```bash
# 1. 检查服务器是否真正运行
curl http://127.0.0.1:3198/system_stats

# 2. 查看当前队列状态
curl http://127.0.0.1:3198/queue

# 3. 检查节点是否可用
curl http://127.0.0.1:3198/object_info | findstr "WanVideo"

# 4. 强制中断当前任务
curl -X POST http://127.0.0.1:3198/interrupt
```

---

### 4.2 命令执行后无后续输出

**现象**：执行 PowerShell 命令后卡住，无返回。

**示例**：
```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:3198/object_info" -UseBasicParsing -TimeoutSec 10
```

**原因**：
1. 服务器端口不匹配（配置了 3198，但服务器运行在其他端口）
2. 服务器未启动或已崩溃
3. 防火墙/安全软件拦截

**解决**：
1. 确认服务器实际运行端口
2. 使用 `-TimeoutSec` 限制等待时间
3. 优先使用 Python 脚本而非 PowerShell 进行 API 调用

---

## 5. 模型加载与量化问题

### 5.1 GGUF 模型量化冲突

**现象**：
```
Quantization should be disabled when loading GGUF models
```

**原因**：GGUF 格式模型已经过量化，如果在加载时再次启用量化（如 `fp8`），会导致冲突。

**解决**：对于 GGUF 模型，必须设置 `quantization: disabled`：

```json
"3": {
    "class_type": "WanVideoModelLoader",
    "inputs": {
        "model": "Wan2.2-T2V-A14B-LowNoise-Q5_K_M.gguf",
        "base_precision": "bf16",
        "quantization": "disabled",
        "load_device": "offload_device",
        "attention_mode": "sdpa"
    }
}
```

**规则**：
- `.gguf` 模型 → `quantization: disabled`
- `.safetensors` / `.fp8` 模型 → 可按需启用量化
- `attention_mode` 默认使用 `sdpa`（C8 验证：sageattn 在部分环境触发 DLL 加载失败）

---

### 5.2 模型文件格式选择

| 格式 | 扩展名 | 适用场景 | 显存占用 | 质量 |
|------|--------|----------|----------|------|
| BF16 | `.safetensors` | 24GB+ 显存 | 高 | 最佳 |
| FP8 | `.fp8.safetensors` | 16-24GB 显存 | 中 | 良好 |
| Q8_0 GGUF | `.gguf` | 10-12GB 显存 | 低 | 接近 fp16 |
| Q5_K_M GGUF | `.gguf` | 8-10GB 显存 | 很低 | 可接受 |
| Q4_K_M GGUF | `.gguf` | <8GB 显存 | 最低 | 一般 |

**建议**：
- L4 专业级 (≥24GB)：使用 bf16/fp16
- L3 高性能级 (16-24GB)：使用 fp8
- L2 标准级 (12-16GB)：使用 Q8_0 GGUF
- L1 入门级 (8-12GB)：使用 Q5_K_M 或 Q8_0 GGUF

---

## 6. 节点类型不匹配问题

### 6.1 MODEL vs WANVIDEOMODEL 类型不匹配

**现象**：
```
Return type mismatch between linked nodes: MODEL vs WANVIDEOMODEL
```

**原因**：`ModelSamplingSD3` 节点输出 `MODEL` 类型，但 `WanVideoSampler` 需要 `WANVIDEOMODEL` 类型。

**解决**：移除 `ModelSamplingSD3` 节点，直接将 `WanVideoModelLoader` 的输出连接到 `WanVideoSampler`。

**错误连接**：
```
WanVideoModelLoader → ModelSamplingSD3 → WanVideoSampler ❌
```

**正确连接**：
```
WanVideoModelLoader → WanVideoSampler ✅
```

---

## 7. 显存不足 (OOM) 问题

### 7.1 低显存设备运行 Wan 2.2 14B 模型 OOM

**现象**：工作流执行到采样阶段时，显存暴涨导致 CUDA out of memory。

**原因**：
- Wan 2.2 14B 模型本身占用约 8-9GB 显存
- 加上 VAE、T5 编码器、潜在空间，10GB 显存严重不足
- 帧数过多（81帧）或分辨率过高（720x1440）会进一步加剧

**解决策略**（按优先级）：

1. **降低采样步数**：30 → 20 → 15（加速 LoRA 可降至 4-6）
2. **启用 BlockSwap**：按硬件档位选择 `blocks_to_swap`（L3 推荐 20，值过高反而导致专用显存闲置）
3. **降低分辨率**：保持 16 的倍数（如 480x832 而非 720x1440）
4. **使用 GGUF 量化模型**：Q5_K_M 或 Q8_0
5. **启用 CPU offload**：`load_device: offload_device`, `force_offload: true`
6. **插入显存清理节点**：双模型架构在 HIGH→LOW 切换点插入 `PurgeVRAM V2`
7. **分段生成+拼接**：保持总时长，禁止直接降帧数（见 8.2 节硬约束）
8. **最后手段**：使用 CPU 模式（极慢）

**关键原则**（C8 验证）：
- 专用显存未被充分利用前不使用共享内存
- `blocks_to_swap` 值过高会导致专用显存闲置，转而使用共享内存
- 双模型架构必须串行执行，HIGH 卸载后才能加载 LOW

---

### 7.2 严禁使用共享 GPU 显存

**规则**：当专用 GPU 显存足够时，禁止使用共享显存（系统内存）。共享显存会导致性能急剧下降。

**检查方法**：
```bash
nvidia-smi
# 关注 "Dedicated GPU memory" 和 "Shared GPU memory" 的使用情况
```

---

## 8. CLI 交互式命令问题

### 8.1 `comfy install` 需要交互确认

**现象**：
```
click.exceptions.Abort
```

**原因**：`comfy install` 命令需要用户交互式确认（Y/N），在非交互环境（如脚本、AI Agent）中失败。

**解决**：
1. 使用脚本模式安装：`python scripts/start_server.py --install`
2. 或修改 CLI 代码添加 `--yes` 标志跳过确认
3. 或使用 `echo "Y" | comfy install` 管道输入

---

## 9. 工作流参数与质量问题（V1-V19 验证经验）

### 9.1 视频生成质量太差

**可能原因**：

1. **节点链架构错误（最严重）**
   - **症状**：角色旋转、抖动、动作不自然
   - **根因**：直接将 block_swap_args 传给 ModelLoader，未使用 WanVideoSetBlockSwap 和 WanVideoSetLoRAs 独立节点
   - **解决**：使用正确节点链 `WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler`

2. **调度器选择错误**
   - **症状**：动作卡住旋转，缺乏自然变化
   - **根因**：使用 unipc 确定性调度器
   - **解决**：使用 `dpm++_sde` 随机性调度器

3. **CFG 配置错误**
   - **症状**：引导过强或不足，动作僵硬或模糊
   - **根因**：静态 CFG=5.0
   - **解决**：使用 CreateCFGScheduleFloatList 动态 CFG 调度[2,1,1,1,1,1]

4. **shift 值错误**
   - **症状**：高曝光或画面异常
   - **根因**：shift=3.0 或 5.0（非源工作流值）
   - **解决**：shift=8.0

5. **LoRA 未正确应用**
   - **症状**：采样步数需求高，或旋转问题
   - **根因**：未使用 WanVideoSetLoRAs 节点应用 LoRA
   - **解决**：通过 WanVideoLoraSelect + WanVideoSetLoRAs 正确应用 lightx2v LoRA

6. **分辨率非16整除**
   - **症状**：`tensor size mismatch` 错误
   - **根因**：如 360 非 16 倍数（360/16=22.5）
   - **解决**：使用 352(22×16)、480(30×16)、640(40×16) 等 16 倍数值

7. **步数太少（无 LoRA 加速时）**
   - **症状**：严重噪点和模糊
   - **根因**：无 lightx2v LoRA 时，4-8 步不足
   - **解决**：使用 lightx2v LoRA 后单段短视频 4 步即可（C8验证），分段长视频 6-8 步；无 LoRA 时需 20-30 步

### 9.2 Wan 2.2 参数梯度参考（V18/V19 + C5 v14 + C8 验证）

> **重要**：以下为梯度参考，不可作为固定模板复制。每个参数都需根据 LoRA 类型、硬件档位、任务需求动态选择。详细梯度分析见第 21 章。

**核心参数梯度速查**：

| 参数 | L1(8-12GB) | L2(12-16GB) | L3(16-24GB) | L4(≥24GB) | 约束 |
|------|-----------|------------|------------|----------|------|
| steps | 4-6(lightx2v) / 20(无LoRA) | 4-8 / 20-25 | 4-8 / 20-30 | 8-15 / 25-30 | lightx2v 单段短视频 4 步足够（C8验证） |
| cfg | 动态调度[2,1,1,1] | 同L1 | 同L1 | 动态调度或固定5.0 | lightx2v必须用动态调度 |
| shift | 8.0 | 8.0 | 8.0 | 8.0 | Wan2.2固定值 |
| scheduler | dpm++_sde | dpm++_sde | dpm++_sde | dpm++_sde | lightx2v验证值 |
| base_precision | bf16 | bf16 | bf16 | fp16_fast | L4可升精度 |
| blocks_to_swap | 40-42 | 38-40 | 20-24（C8验证） | 20-24 | L3 档值过高会导致专用显存闲置 |
| rope_function | comfy_chunked | comfy_chunked | comfy_chunked | comfy_chunked | ≥480×848必须 |
| noise_aug_strength | 0.1 | 0.1 | 0.1 | 0.1 | 禁止0 |
| lightx2v HIGH | 1.0 | 1.0 | 1.0 | 1.0 | 官方推荐，禁止>2.0 |
| lightx2v LOW | 1.0 | 1.0 | 1.0 | 1.0 | 官方推荐 |

### 9.3 多种可尝试方向（OOM 处理）

**方向1: 降分辨率保帧数（推荐）**
- 优点: 保持时长，动作连贯性不受影响
- 缺点: 画质下降
- 示例: 480x848 → 352x640
- V18 验证: 352x640 + 6步耗时 7.5 分钟

**方向2: 降帧数保分辨率**
- 优点: 保持画质
- 缺点: 时长缩短，需后续 RIFE 插帧补足
- 示例: 241帧 → 121帧（5秒）

**方向3: 降精度保帧数和分辨率**
- 优点: 保持时长和分辨率
- 缺点: 画质轻微下降，bf16 比 fp16_fast 慢约 1.5 倍
- 示例: fp16_fast → bf16
- V18 验证: bf16 + 352x640 成功；fp16_fast + 480x848 OOM

**方向4: 增加 BlockSwap**
- 优点: 不降低任何质量参数
- 缺点: CPU↔GPU 数据搬运增加，速度变慢
- 示例: blocks_to_swap 36 → 38

### 9.4 显存物理限制公式

```
FFN激活值 ≈ (帧数 × 宽 × 高 / 4096) × 20480 × 2bytes
```

**示例计算（RTX 3080 20GB）**：
- 241帧@480x848: FFN约15.7GB（可行）
- 241帧@576x1024: FFN约22.8GB（不可行）
- 241帧@720x1280: FFN约35.4GB（不可行）

### 9.5 V1-V19 迭代经验总结

**成功版本**：
- V18: 352x640 + 6步 + bf16 + lightx2v LoRA，耗时 7.5 分钟，效果良好
- V19: 480x848 + 8步 + bf16 + lightx2v LoRA + 完整提示词，耗时 27.2 分钟，效果完美

**失败版本与教训**：
- V3: KSampler 架构，shift/VAE/scheduler 全部不匹配，高曝光+模糊
- V9-V14: 分段拼接架构，段间累积损失、段内清晰度崩塌、超分方案失败
- V16: lightx2v LoRA + 错误节点链，LoRA 破坏 CFG 引导一致性，角色持续旋转
- V17: 移除 LoRA + unipc 调度器，确定性导致动作卡住旋转
- V18 首版: fp16_fast + 480x848，OOM 崩溃

**关键经验**：
1. 必须使用 WanVideoSetBlockSwap 和 WanVideoSetLoRAs 独立节点
2. 必须使用 dpm++_sde 调度器（非 unipc）
3. 必须使用动态 CFG 调度（非静态 CFG=5.0）
4. shift 必须为 8.0（非 3.0 或 5.0）
5. base_precision 按硬件档位选择（L1/L2/L3:bf16, L4:fp16_fast），低显存+lightx2v时bf16更稳定
6. 分辨率必须 16 整除
7. 必须学会选用 LoRA，不能跳过

---

## 10. 通用排查流程

### 10.1 工作流执行前检查清单

```bash
# 1. 环境检查
python scripts/check_status.py

# 2. 确认服务器运行
curl http://127.0.0.1:${COMFYUI_PORT}/system_stats

# 3. 确认所需节点存在
curl http://127.0.0.1:${COMFYUI_PORT}/object_info | findstr "WanVideo"

# 4. 确认模型文件存在
ls ${COMFYUI_PATH}\models\checkpoints\ | findstr "Wan"

# 5. 验证工作流 JSON 格式
python -c "import json; json.load(open('workflow.json'))"

# 6. 检查显存是否足够
nvidia-smi
```

### 10.2 工作流执行中监控

```bash
# 查看队列状态
curl http://127.0.0.1:${COMFYUI_PORT}/queue

# 查看历史记录
curl http://127.0.0.1:${COMFYUI_PORT}/history

# 强制中断
curl -X POST http://127.0.0.1:${COMFYUI_PORT}/interrupt

# 清空队列
curl -X POST http://127.0.0.1:${COMFYUI_PORT}/queue
```

### 10.3 工作流执行后检查

```bash
# 检查输出目录
ls ${OUTPUT_DIR}\

# 检查 ComfyUI 日志
tail -n 100 ${COMFYUI_PATH}\comfyui.log
```

---

## 11. C2 任务启动问题总结（2026-07-21）

### 11.1 问题现象

C2 视频生成任务在启动 ComfyUI 阶段耗时过长，经历 10 次启动尝试，涉及大量错误和绕过方案。最终通过白名单模式成功启动。

### 11.2 问题根因与解决方案

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| venv 环境失效 | `${COMFYUI_PATH}/venv/pyvenv.cfg` 指向其他用户路径（venv跨机器不可移植） | 使用嵌入式 Python `.\python\python.exe` |
| Manager 联网超时崩溃 | config.ini 的 network_mode=public，启动时从 GitHub 获取节点列表超时 | 白名单模式自动跳过 Manager（而非修改 config.ini，修改可能不生效） |
| config.ini 修改不生效 | 两个 config.ini 都改为 local，但启动日志仍显示 public | 放弃修改 config.ini，改用白名单模式 |
| --disable-manager-ui 参数错误 | ComfyUI 0.27.0 无此参数 | 不使用此参数 |
| 重命名目录绕过 | 重命名 comfyui-manager/.disabled 可禁用但影响后续 | 使用白名单模式，不重命名目录 |
| Impact-Pack 加载卡住 | Impact-Pack 依赖 timm，加载完成后服务无响应 | 白名单模式自动跳过 Impact-Pack |
| --whitelist-custom-nodes 单独使用无效 | 该参数必须与 --disable-all-custom-nodes 同时使用 | 组合使用：`--disable-all-custom-nodes --whitelist-custom-nodes ...` |
| --disable-all-custom-nodes 无 WanVideo 节点 | 禁用所有节点后 WanVideo 不可用 | 添加 --whitelist-custom-nodes 指定所需节点 |
| VHS_VideoCombine 权限错误 | ComfyUI 进程对安装目录的 output/temp 子目录写入权限不足 | 启动时 `--output-directory ${OUTPUT_DIR} --temp-directory ${TEMP_DIR}` 重定向到可写目录 |

### 11.3 ComfyUI 启动标准命令（验证成功）

```powershell
.\python\python.exe -u main.py --port ${COMFYUI_PORT} --listen 127.0.0.1 `
  --disable-all-custom-nodes `
  --whitelist-custom-nodes ComfyUI-WanVideoWrapper ComfyUI-VideoHelperSuite ComfyUI-KJNodes comfyui-frame-interpolation comfyui-essentials `
  --output-directory ${OUTPUT_DIR} `
  --temp-directory ${TEMP_DIR}
```

**启动耗时**：约 90 秒（WanVideoWrapper 加载 timm/DeepSpeed 需 6.9 秒）

### 11.4 工作流节点必填参数（踩坑记录）

| 节点 | 必填参数 | 值 | 缺失后果 |
|------|---------|-----|---------|
| WanVideoSampler | riflex_freq_index | 0 | 工作流验证失败 |
| WanVideoVAELoader | precision | bf16 | 工作流验证失败 |

### 11.5 连续任务内存释放问题

单次长视频任务（241 帧）完成后，ComfyUI 进程内存占用可达 30GB+ 且不自动释放，导致 HTTP 请求超时。

**解决方案**：连续执行多个任务时，在任务间重启 ComfyUI 服务：
1. `Stop-Process -Id <PID> -Force`
2. 重新执行标准启动命令

### 11.6 HTTP 查询超时处理

采样进行时 ComfyUI 的 HTTP 接口响应缓慢（/history 查询可能超时 30 秒），这是正常现象。

**解决方案**：
- 脚本中使用 try-except 捕获超时并重试
- 或通过检查 ComfyUI 控制台日志的 `Prompt executed in 00:XX:XX` 判断完成状态
- 不要将 HTTP 超时误判为任务失败

---

## 12. C5 多图视频生成迭代经验（2026-07-22）

### 12.1 任务背景

使用两张参考图（`1.png` 走廊场景角色、`2.png` 教室场景）生成 10 秒视频，包含 6 阶段动作：360°旋转 → 深蹲 → 起身 → 走向教室门口 → 进入教室 → 拉椅落座。任务经历 v3-v14 共 12 次迭代，逐步解决提示词执行两遍、折返、角色不一致、细节丢失等问题。

### 12.2 核心问题与根因总结

#### 12.2.1 提示词执行两遍（v3-v8）

**现象**：10秒视频内角色执行两遍完整动作序列。

**根因（排查过程）**：
1. **初判 RIFLEX 问题**：v3 使用 `riflex_freq_index=0`，v8 启用 `riflex_freq_index=6`，问题仍存在 → 排除 RIFLEX
2. **排查 RoPE 匹配**：源码确认 `rope_function="comfy_chunked"` 匹配 `elif "comfy" in rope_function` 分支，RIFLEX 确实生效 → 排除 RoPE 匹配问题
3. **最终根因**：**帧数超出模型训练长度**。Wan2.2-I2V-A14B 训练于 81 帧（约3.4秒@24fps），241帧（10秒）是训练长度的3倍。RIFLEX 只能防止 RoPE 数学循环，无法改变模型对长视频的语义理解，模型通过重复动作序列填充时间

**关键教训**：
- Wan2.2 I2V 模型**不建议单次生成超过 81 帧**（约3.4秒@24fps）
- 超过训练长度时，RIFLEX 防数学循环但**不防语义重复**
- 长视频必须使用分段生成+拼接，或官方 Context Window 方案

#### 12.2.2 角色折返（v10-v11）

**现象**：角色在视频末尾折返回起点重复动作。

**根因**：动作密度与时长不匹配。5秒内塞入4个动作（旋转→深蹲→起身→走到门口），模型执行完后剩余时间触发重复。

**解决**：让最后一个动作成为持续性动作（如"持续走向门口到末帧"），避免角色提前到达后停下触发重复。

#### 12.2.3 分段拼接段间问题（v9-v13）

**现象**：
- 段间转场突兀（段1末尾与段2开头无衔接）
- 后续段角色外貌变化（发型、脸部脱离1.png参考）

**根因与解决**：

| 问题 | 根因 | 解决方案 |
|------|------|----------|
| 转场突兀 | 段2 start_image 与段1末帧无关联 | 提取段1末帧作为段2的 start_image |
| 角色外貌变化 | CLIP concat 双图权重相同（1.0/1.0），末帧场景特征干扰角色 | 调整权重：1.png=1.5（强约束角色），末帧=0.5（弱化场景） |
| 段3角色瞬移 | 提示词缺少"从门口进入"的过渡描述 | 明确描述"standing at the doorway → pushes the door open → steps into the classroom" |

#### 12.2.4 细节丢失（v13-v14）

**现象**：发型、皮肤质感、衣服质感严重丢失。

**根因（三大主因）**：

| 根因 | 影响程度 | 说明 |
|------|----------|------|
| HIGH LoRA strength=3.0 过高 | 极高 | 过度强化高噪声专家，破坏 MoE 自然去噪曲线，细节在早期被锁死 |
| 480p LoRA + 非标准分辨率 | 高 | LoRA 训练于 480p（16:9），用于竖屏分辨率属分布外推理 |
| 6步采样不匹配 | 中 | lightx2v 设计为4步，8步是实测最优，6步处于不匹配区间 |

**解决**：HIGH strength 3.0→1.0，步数 6→8。

### 12.3 LoRA 类型与正确使用

#### 12.3.1 LoRA 类型分类

| 类型 | 用途 | 本地文件示例 | 是否可叠加 |
|------|------|-------------|-----------|
| 加速蒸馏 | 减少步数和CFG计算 | `lightx2v_I2V_14B_480p_cfg_step_distill` | 不可与其他LoRA叠加 |
| 画质增强 | 提升细节和质感 | `SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH`、`Wan2.2-Fun-A14B-InP-low-noise-HPS2.1` | 可与其他类型叠加 |
| 重新打光 | 调整场景光线 | `WanAnimate_relight` | 可与其他类型叠加 |

#### 12.3.2 lightx2v LoRA 关键认知

- **全称**：cfg_step_distill（CFG蒸馏+步数蒸馏）
- **用途**：加速推理，**非画质增强**
- **不能为场景提供额外画质加成**
- **strength 推荐值**：HIGH=1.0, LOW=1.0（官方标准，非3.0）
- **步数匹配**：设计为4步，C8 任务验证 4 步（HIGH:2+LOW:2）质量足够；早期文档推荐 8 步是 C5 任务（分段生成）的经验值，单段短视频 4 步即可
- **分辨率匹配**：480p版本必须配合480p分辨率（832×480或接近）

#### 12.3.3 画质 LoRA 选择

若需提升画质，应在加速 LoRA 和画质 LoRA 之间二选一：
- **加速优先**：lightx2v（strength=1.0，8步，速度快）
- **画质优先**：SVI_v2_PRO 或 HPS2.1（需增加步数到20-30步，速度慢但细节最佳）

### 12.4 验证成功的最终架构（v14）

#### 12.4.1 架构设计

```
分段策略：3段×81帧 = 10秒（每段3.4秒，在模型训练长度内）
段1: start_image=1.png, CLIP单图(1.png), 动作: 旋转→深蹲→起身
段2: start_image=段1末帧, CLIP concat(1.png=1.5 + 末帧=0.5), 动作: 走向门口
段3: start_image=段2末帧, end_image=2.png参考, CLIP concat(1.png=1.5 + 末帧=0.5), 动作: 进入教室→落座
ffmpeg concat filter 拼接3段
```

**说明**：帧数和段数根据硬件档位调整。L1档位可能需要更多段数（如4段×81帧），L4档位可减少段数（如2段×121帧）。

#### 12.4.2 关键参数（动态调整，不写死）

| 参数 | 推荐值 | 调整依据 |
|------|--------|----------|
| num_frames | 81（4k+1格式） | Wan2.2训练原生长度，超过触发语义重复 |
| 宽×高 | 遵从参考图比例，16的整数倍 | 避免VAE latent mismatch |
| steps | 4-8（lightx2v）/ 20-30（无LoRA） | lightx2v 单段短视频 4 步足够（C8验证），分段长视频可用 8 步 |
| split_step | steps/2 | HIGH/LOW阶段均分 |
| shift | 8.0 | 官方源工作流值 |
| HIGH LoRA strength | 1.0 | 官方推荐，过高破坏细节 |
| LOW LoRA strength | 1.0 | 官方推荐 |
| blocks_to_swap | 按硬件档位动态选择 | L1:40-42, L2:38-40, L3:20-24（C8验证，非36-38）, L4:20-24 |
| rope_function | "comfy_chunked" | 480x848 及以上必须使用，降低显存峰值（C8验证，非"comfy"） |
| riflex_freq_index | 0（81帧）/ 6（>81帧时） | 训练范围内无需RIFLEX |
| scheduler | dpm++_sde | 随机性产生自然动作 |
| base_precision | 按硬件档位选择 | L1/L2/L3:bf16, L4:fp16_fast |
| CLIP strength_1(1.png) | 1.5 | 强约束角色外貌 |
| CLIP strength_2(末帧) | 0.5 | 弱化场景干扰 |
| combine_embeds | "concat" | 保留双图独立特征 |
| noise_aug_strength | 0.1 | C8验证标准值（禁止 0，会导致亮度锚定缺失） |
| crf | 14 | 高质量编码 |
| pix_fmt | yuv420p10le | 10bit色彩深度 |

> **注**：本表为 C5 分段长视频任务（v14）的参数配置，C8 单段多图短视频任务对此表部分参数进行了更新（如 steps=4、blocks_to_swap=20、rope_function=comfy_chunked、noise_aug_strength=0.1）。详见第 23 章 C8 任务完整复盘。

#### 12.4.4 硬件梯度档位参考

| 档位 | VRAM范围 | 推荐分辨率 | 单次最大帧数 | blocks_to_swap | base_precision | 说明 |
|------|---------|-----------|------------|----------------|----------------|------|
| L1 入门级 | 8-12GB | 352×640 | 81帧 | 40-42 | bf16 | 训练原生长度，最安全 |
| L2 标准级 | 12-16GB | 480×640 | 121帧 | 38-40 | bf16 | 5秒视频，兼顾画质与显存 |
| L3 高性能级 | 16-24GB | 480×848 | 121-241帧 | 20-24（C8验证） | bf16 | 可尝试10秒，超121帧注意语义重复 |
| L4 专业级 | ≥24GB | 576×1024 | 241帧 | 20-24 | fp16_fast | 单次10秒可行 |

> **C8 验证更新**：L3 档 blocks_to_swap 从 36-38 修正为 20-24，专用显存利用率从 40% 提升至 75%+，避免使用共享 GPU 内存。

**路径变量约定**（本文档使用以下变量替代绝对路径）：
- `${COMFYUI_PATH}`: ComfyUI安装目录
- `${PROJECT_PATH}`: 本项目根目录
- `${COMFYUI_PORT}`: ComfyUI服务端口（默认3198，可通过环境变量配置）
- `${OUTPUT_DIR}`: 视频输出目录
- `${TEMP_DIR}`: 临时文件目录

#### 12.4.3 多图控制模式选择

| 模式 | fun_or_fl2v_model | 适用模型 | end_image作用 |
|------|-------------------|---------|--------------|
| 标准I2V（推荐） | false | Wan2_2-I2V-A14B标准模型 | 末尾参考（不强制末帧=该图） |
| FLF2V专用 | true | FLF2V专用模型（如Wan2_1-FLF2V-14B-720P） | 强制末帧=该图 |

**关键**：标准 I2V 模型不应启用 FLF2V 模式。FLF2V 是专用模型功能，不是通用 I2V 模型的可选开关。

### 12.5 分段生成操作流程

```
1. 段1生成 → ffmpeg提取末帧 → 复制到ComfyUI input目录（${COMFYUI_PATH}/input/）
2. 段2生成（start_image=段1末帧）→ ffmpeg提取末帧 → 复制到ComfyUI input目录
3. 段3生成（start_image=段2末帧, end_image=2.png参考）
4. ffmpeg concat filter拼接所有段
```

**末帧提取命令**（帧索引从0开始，81帧视频末帧索引=80）：
```bash
ffmpeg -y -i video.mp4 -vf "select=eq(n\,80)" -vframes 1 lastframe.png
# 备用（reverse模式，较慢）：
ffmpeg -y -i video.mp4 -vf "reverse" -vframes 1 lastframe.png
```

**ffmpeg拼接命令**（concat filter，避免-safe兼容性问题）：
```bash
ffmpeg -y -i seg1.mp4 -i seg2.mp4 -i seg3.mp4 \
  -filter_complex "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]" \
  -map "[outv]" -c:v libx264 -crf 14 -pix_fmt yuv420p10le -r 24 output.mp4
```

### 12.6 沙箱文件复制问题

ComfyUI 运行目录与脚本输出目录可能不同盘符，Python 脚本的 `shutil.copy` 可能被沙箱拦截。解决：使用 PowerShell `Copy-Item` 通过 RunCommand 工具执行：

```powershell
# 将末帧从输出目录复制到ComfyUI input目录
Copy-Item "${OUTPUT_DIR}/lastframe.png" "${COMFYUI_PATH}/input/lastframe.png" -Force
```

### 12.7 迭代版本对照表

| 版本 | 核心修改 | 结果 |
|------|---------|------|
| v3 | 241帧单次生成，FLF2V双图 | 提示词执行两遍 |
| v8 | v3+riflex=6 | 仍执行两遍（RIFLEX不防语义重复） |
| v9 | 2段×121帧拼接 | 段间无转场，角色不一致 |
| v10 | 段1末尾"走动持续到末帧" | 仍折返（121帧仍超训练长度） |
| v11 | 单段81帧 | 不折返但时长不足（3.4秒） |
| v12 | 3段×81帧拼接 | 角色外貌变化，段3瞬移 |
| v13 | CLIP权重1.5/0.5+段3提示词优化 | 效果基本可以，细节丢失 |
| v14 | HIGH strength 3.0→1.0, steps 6→8 | 勉强可以，细节小问题待调 |

### 12.8 关键教训清单

1. **单次生成帧数与硬件配置相关**：Wan2.2 I2V 模型训练原生长度约81帧（3.4秒@24fps），但实际单次可生成的最大帧数受显存和模型语义理解双重约束。高显存（≥24GB）可尝试241帧单次生成，中低显存（16-24GB）建议121帧，低显存（<16GB）建议81帧。**超过模型训练长度时，RIFLEX防数学循环但不防语义重复**，模型会通过重复动作序列填充时间。此时应采用分段生成+拼接，或使用官方Context Window方案
2. **LoRA类型多样需甄别挑选**：LoRA不仅用于加速，还有画质增强、角色一致性、重新打光等多种类型。使用前必须：
   - 检查本地`models/loras/`目录已有文件
   - 根据任务需求选择合适类型（加速用lightx2v，画质用HPS2.1/SVI_v2_PRO，打光用relight）
   - 注意LoRA间是否可叠加（加速LoRA通常不可与其他LoRA叠加）
   - 确认LoRA的分辨率匹配（480p LoRA应用于480p分辨率）
3. **动作密度匹配时长**：3.4秒内最多2-3个核心动作，末尾动作应为持续性动作
4. **CLIP权重调整角色一致性**：1.png高权重(1.5)约束角色，末帧低权重(0.5)弱化场景
5. **加速LoRA的strength需遵循官方推荐**：lightx2v是加速蒸馏LoRA非画质LoRA，strength=1.0是官方推荐值，过高（如3.0）会破坏MoE自然去噪曲线导致细节丢失
6. **标准I2V不启用FLF2V**：FLF2V是专用模型功能，标准模型用fun_or_fl2v_model=false
7. **分段生成末帧继承**：提取前段末帧作为后段start_image，保证转场连贯
8. **ffmpeg concat filter**：避免-safe选项兼容性问题，用filter_complex方式拼接
9. **沙箱文件复制**：用PowerShell Copy-Item替代Python shutil.copy
10. **先调研后试错**：盲目试错浪费多轮迭代，应先查阅官方文档和示例工作流

---

## 13. 基础功能验证经验（2026-07-22）

### 13.1 任务背景

经过多轮视频任务迭代后，回归项目基础功能验证，依次完成四件事并追加一项图片放大任务：
1. 关闭当前运行的 ComfyUI
2. 正常启动 ComfyUI
3. 核查工作流仓库管理功能
4. 文生图（Flux 2.0，720P 4:3，玻璃瓶内微型银河）
5. X2 放大器将图片分辨率翻倍

本节总结执行过程中的关键经验，补充前述章节未涵盖的基础功能踩坑点。

### 13.2 ComfyUI 关闭方式选择

#### 问题：comfy-cli 的 `comfy stop` 命令限制

`comfy stop`（位于 `cli/cmdline.py`）**仅能停止通过 `comfy launch --background` 启动的后台实例**，实现机制是从配置中读取 `(listen, port, pid)` 元组，再用 `psutil` 终止该 PID。若实例是直接通过 `python main.py` 启动的（项目文档标准启动方式），`comfy stop` 会报 "No ComfyUI is running in the background"。

#### 问题：`comfy launch --background` 无法启动 ComfyUI

`cli/resolve_python.py` 的 `resolve_workspace_python()` 只识别标准 venv 结构（`.venv\Scripts\python.exe` 或 `venv\Scripts\python.exe`），**不认识 ComfyUI 嵌入式 Python**（`${COMFYUI_PATH}\python\python.exe`）。导致 `comfy launch --background` 报 "Execution error: failed to launch ComfyUI"。

#### 验证成功的关闭方式

当实例通过文档标准命令直接启动时，使用 psutil 按命令行特征匹配并终止进程：

```python
import psutil
for p in psutil.process_iter(['pid', 'cmdline']):
    if p.info.get('cmdline') and any('main.py' in str(c) for c in p.info['cmdline']):
        p.kill()
```

#### 经验清单

1. **`comfy stop` 适用范围有限**：仅停止 background 模式实例，不适用于直接启动的进程
2. **嵌入式 Python 不被 comfy-cli 识别**：`resolve_workspace_python()` 只查找 `.venv`/`venv`，无法用于启动嵌入式 Python 部署的 ComfyUI
3. **关闭非 background 实例用 psutil**：按 `main.py` 命令行特征匹配进程最可靠

### 13.3 ComfyUI 启动标准命令（再次验证）

依据 11.3 节文档，使用嵌入式 Python + 白名单模式启动：

```powershell
Set-Location "${COMFYUI_PATH}"
.\python\python.exe -u main.py --port ${COMFYUI_PORT} --listen 127.0.0.1 `
  --disable-all-custom-nodes `
  --whitelist-custom-nodes ComfyUI-WanVideoWrapper ComfyUI-VideoHelperSuite ComfyUI-KJNodes comfyui-frame-interpolation comfyui-essentials `
  --output-directory ${OUTPUT_DIR} `
  --temp-directory ${TEMP_DIR}
```

验证结果：ComfyUI 0.27.0 成功启动，HTTP 200 响应正常。该命令在 11.3、13 节中已多次验证，可作为稳定启动方案。

### 13.4 工作流仓库管理功能验证

#### 功能可用性结论

项目内 `scripts/build_workflow_library.py` 和 `scripts/query_library.py` 功能完整可用，无需依赖外部工具。

#### 查询器 `query_library.py`

支持 6 种查询维度，均验证正常：

| 参数 | 用途 | 示例 |
|------|------|------|
| `--stats` | 仓库统计（总数、类别分布、模型系列、Top 10 节点、模型清单） | `python query_library.py --stats` |
| `--list` | 列出所有工作流名称和路径 | `python query_library.py --list` |
| `--category` | 按类别过滤（文生图/图生视频/图片编辑等） | `python query_library.py --category 文生图` |
| `--model-family` | 按模型系列过滤（Flux/Wan2.2/SDXL 等） | `python query_library.py --model-family Flux` |
| `--node-type` | 按节点类型过滤（部分匹配） | `python query_library.py --node-type KSampler` |
| `--model` | 按模型文件名过滤（部分匹配） | `python query_library.py --model flux-2-klein` |

默认仓库路径：`.trae/skills/comfyui-controller/assets/workflow_library.json`

#### 构建器 `build_workflow_library.py`

- 全量构建：`python build_workflow_library.py --input ${WORKFLOW_DIR} --output ${LIBRARY_PATH} --host 127.0.0.1 --port ${COMFYUI_PORT}`
- 增量更新：追加 `--update` 参数，基于 file_index 的 mtime/size 比对，仅重新分析变更文件
- 需 ComfyUI 服务在线：构建器从 `/object_info` 获取节点 schema 用于 widget 名称映射

#### 经验清单

1. **查询器默认路径相对工作目录**：在项目根目录执行时无需 `--library` 参数；其他目录需显式指定
2. **构建器需 ComfyUI 在线**：增量更新和全量构建都依赖 `/object_info` 端点，启动 ComfyUI 后再运行
3. **模型系列识别可修复 unknown**：若增量更新后大量工作流 model_family 为 unknown，检查 `detect_model_family()` 规则是否覆盖工作流中实际使用的模型命名

### 13.5 文生图工作流（Flux 2.0 架构）

#### 问题：SD1.5 生成结果与提示词严重不符

首次使用 SD1.5（v1-5-pruned-emaonly）+ 中文提示词生成"玻璃瓶内微型银河"，结果生成树林。
- 根因 1：SD1.5 训练分辨率 512×512，无法支持 960×720 高分辨率生成
- 根因 2：SD1.5 的 CLIP 文本编码器对复杂中文场景描述理解能力弱
- 根因 3：SD1.5 模型整体语义理解能力远逊于 Flux 2.0

#### Flux 2.0 工作流架构（验证成功）

基于工作流仓库中的 `Flux2+Klein+文生图.json` 模板，核心架构：

| 节点 | 类型 | 关键参数 |
|------|------|---------|
| UNETLoader | 模型加载 | `weight_dtype=default`（无 type 参数） |
| CLIPLoader | 文本编码器 | `type=flux2`（必填），`device=default` |
| VAELoader | VAE | `flux2-vae.safetensors` |
| EmptyFlux2LatentImage | 潜在空间 | **非 EmptyLatentImage**，Flux2 专用 |
| CLIPTextEncode | 正向条件 | 英文提示词（Flux2 对中文支持有限） |
| ConditioningZeroOut | 负向条件 | **零化正向条件**，非 CLIPTextEncode 负面文本 |
| KSampler | 采样 | `cfg=1`，`sampler=euler`，`scheduler=simple` |
| VAEDecode | 解码 | - |
| SaveImage | 保存 | - |

#### Flux 2.0 vs SD1.5 关键差异

| 项目 | Flux 2.0 | SD1.5 |
|------|----------|-------|
| 潜在空间节点 | `EmptyFlux2LatentImage` | `EmptyLatentImage` |
| 文本编码器 | `CLIPLoader`（独立加载 qwen_3_8b，type=flux2） | Checkpoint 内置 CLIP |
| 负向条件 | `ConditioningZeroOut`（零化正向） | `CLIPTextEncode`（负面文本） |
| CFG | 1（Distill 模型特性） | 7-8 |
| sampler/scheduler | euler / simple | euler_ancestral / karras |
| 训练原生分辨率 | 2048+（支持高分辨率直出） | 512（高分辨率需 Hires.fix） |

#### 经验清单

1. **复杂场景优先用 Flux 2.0**：SD1.5 仅适合简单场景，复杂语义（微型银河、梦幻氛围）必须用 Flux 2.0 或以上模型
2. **Flux2 提示词用英文**：qwen_3_8b 编码器对英文理解优于中文，复杂场景描述应转英文
3. **Flux2 负向条件用 ConditioningZeroOut**：不用 CLIPTextEncode 写负面词，cfg=1 时零化正向即可
4. **Flux2 潜在空间用 EmptyFlux2LatentImage**：误用 EmptyLatentImage 会导致 latent 维度不匹配
5. **CLIPLoader 必须带 type=flux2**：缺失会导致文本编码方式错误

### 13.6 模型名动态查询（关键踩坑）

#### 问题：工作流模板中的模型名与本地实际文件不符

工作流仓库中的 `Flux2+Klein+文生图.json` 模板记录 `unet_name: "flux-2-klein-9b-fp8.safetensors"`，但本地实际文件名为 `F2K-9b-kleinova_10FP8.safetensors`。直接执行 API 工作流报错：

```
value_not_in_list: unet_name: 'flux-2-klein-9b-fp8.safetensors' not in ['F2K-9b-kleinova_10FP8.safetensors', ...]
```

#### 解决方案：从 object_info 动态查询

执行工作流前，必须从 ComfyUI `/object_info/{NodeType}` 端点查询模型实际可用列表：

```powershell
# 查询 UNETLoader 可用模型
$resp = Invoke-WebRequest -Uri "http://127.0.0.1:${COMFYUI_PORT}/object_info/UNETLoader"
$json = $resp.Content | ConvertFrom-Json
$json.UNETLoader.input.required.unet_name[1].options
```

同理查询 `VAELoader.vae_name`、`CLIPLoader.clip_name`、`UpscaleModelLoader.model_name` 等。

#### 经验清单

1. **模型名不可硬编码**：工作流模板记录的模型名可能因版本更迭或重命名与本地不符
2. **执行前必查 object_info**：所有 COMBO 类型参数（模型选择）都应从 `/object_info/{NodeType}` 动态获取
3. **`get_available_models.py` 的 type 映射不完整**：该脚本 `--type upscale` 错误映射到 CheckpointLoaderSimple，upscale 模型应直接查 `/object_info/UpscaleModelLoader`

### 13.7 UI 格式转 API 格式的节点清理

#### 问题：转换后的 API 工作流包含无关节点

`workflow_converter.py` 将 UI 工作流转为 API 格式时，会保留所有节点（包括 UI 辅助节点）。以下节点在 API 格式中无意义或导致执行错误，需手动删除：

| 节点类型 | 问题 | 处理 |
|---------|------|------|
| `MarkdownNote` | UI 注释节点，API 格式无输出 | 删除 |
| `LoadImage`（未连接的参考图） | 引用不存在的图片文件导致报错 | 删除所有未连接的 LoadImage |
| `Note` | 同 MarkdownNote | 删除 |

#### 经验清单

1. **UI 转 API 后必须清理节点**：MarkdownNote、Note、未连接的 LoadImage 等节点在 API 格式中无作用
2. **未连接的 LoadImage 会报错**：即使未被其他节点引用，API 执行时仍会尝试加载图片，文件不存在即报错
3. **清理后验证节点引用完整性**：确保所有 `[node_id, output_index]` 引用的目标节点都存在

### 13.8 X2 图片放大器使用经验

#### 放大模型选择

本地可用 X2 放大模型：

| 模型 | 适用场景 | 选择建议 |
|------|---------|---------|
| `2x_StarSample_V2.0.safetensors` | AI 生成内容超分 | **推荐**，对 AI 生成图片细节保留好 |
| `RealESRGAN_x2.pth` | 真实照片超分 | 不适合 AI 生成内容，产生伪影（见 9.1 节） |

#### 标准放大工作流节点链

```
LoadImage → UpscaleModelLoader → ImageUpscaleWithModel → SaveImage
```

API 格式示例：

```json
{
  "1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
  "2": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": "2x_StarSample_V2.0.safetensors"}},
  "3": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
  "4": {"class_type": "SaveImage", "inputs": {"filename_prefix": "upscaled", "images": ["3", 0]}}
}
```

#### 验证结果

| 项目 | 原图 | 放大后 |
|------|------|--------|
| 分辨率 | 960×720 | 1920×1440 |
| 文件大小 | 826 KB | 2752 KB |
| 放大倍数 | - | 2× |

#### 经验清单

1. **AI 生成图片放大选 2x_StarSample_V2.0**：RealESRGAN_x2 对 AI 生成内容产生伪影（9.1 节已记录，本次再次验证）
2. **放大前需将图片复制到 input 目录**：LoadImage 节点从 `${COMFYUI_PATH}\input\` 加载，输出目录的图片需先复制
3. **ImageUpscaleWithModel 而非 ImageUpscale**：前者使用模型超分（画质好），后者仅像素插值（画质差）

### 13.9 综合教训清单

1. **基础功能验证不可跳过**：项目迭代多次后，回归基础功能验证能发现文档遗漏和工具缺陷（如 stop_server.py Windows 实现不完整、get_available_models.py type 映射错误）
2. **关闭 ComfyUI 用 psutil 按命令行匹配**：`comfy stop` 仅适用 background 实例，嵌入式 Python 部署下 `comfy launch --background` 不可用
3. **启动用文档标准命令**：嵌入式 Python + 白名单模式，已在 C2/C3/C5/基础验证多轮验证成功
4. **工作流仓库管理功能完整可用**：query_library.py 6 种查询维度 + build_workflow_library.py 增量更新，无需外部工具
5. **复杂场景文生图用 Flux 2.0**：SD1.5 仅适合简单场景，复杂语义必须用 Flux 2.0，提示词转英文
6. **模型名动态查询**：所有 COMBO 参数（模型选择）执行前必查 `/object_info/{NodeType}`，不可硬编码
7. **UI 转 API 后清理无关节点**：MarkdownNote、Note、未连接的 LoadImage 必须删除
8. **AI 图片放大用 2x_StarSample_V2.0**：RealESRGAN_x2 对 AI 内容产生伪影
9. **执行流程标准化**：启动服务 → 查询可用模型 → 准备工作流（转换+清理+参数核对） → 执行 → 验证输出

---

## 14. C6 单图视频生成排查经验与问题解决流程（2026-07-23）

### 14.1 任务背景

使用 Wan2.2 I2V 模型将单张参考图生成 5 秒视频（720P 原图比例、20fps），随后用 X2 放大器翻倍分辨率。本任务从首次执行到最终完成共经历 7 轮迭代排查，暴露了工作流架构、参数调优、节点规格、文件传输、输出识别等多个层面的问题。本节系统盘点所有问题，并提炼出通用的问题分析解决流程。

### 14.2 问题盘点（按迭代顺序）

#### 问题 1：首次生成全黑白噪点（结果完全偏离）

**现象**：视频全是密密麻麻黑白噪点，与参考图片毫无关系。

**思考过程**：
- 结果完全偏离预期 → 不是参数微调能解决的问题
- 怀疑工作流架构设计本身存在缺陷（节点连接、数据流向）
- 决定：不再调参，重新审视工作流架构

**解决方案**：重新设计工作流，先用低分辨率+低参数快速测试（2 分钟内）验证方向是否正确。

**核心教训**：当结果完全偏离预期时，**不要继续调参**，应重新审视工作流架构。低参数快速测试是验证方向的有效手段。

---

#### 问题 2：低分辨率测试画面高度模糊（调参无效）

**现象**：噪点过高，画面高度模糊，只能看见人物大致轮廓。

**第一轮思考**：CFG 过低导致文本引导不足 → 提高 CFG 和 steps。

**第二轮测试**：参数调整后画面与第一轮无区别。

**关键转折思考**：
- 调参无效 → 问题不在参数，在架构
- 检查工作流后半部分：**是否使用了 LOW 模型？**
- 发现：只有 HIGH 阶段，缺少 LOW 阶段细化

**根因**：双阶段架构不完整，缺少 LOW 阶段细化，画面停留在粗糙状态。

**解决方案**：改用双阶段 HIGH+LOW 架构（HIGH 主结构 + LOW 细化）。

**核心教训**：当调参无效时，**立即检查架构完整性**。Wan2.2 双阶段架构中 LOW 阶段不可省略，否则画面无法从粗糙状态收敛。

---

#### 问题 3：正式生成不遵循提示词（耗时异常过短）

**现象**：视频内容完全没有参照提示词，生成耗时仅 6 分钟（明显异常过短）。

**思考过程**：
- 耗时过短 → 引导不足的信号（采样步数不够）
- 检查参数：steps 过少，文本引导不充分
- 模型在有限步数内无法充分理解提示词语义

**根因**：steps 太少导致文本引导不足，模型无法充分理解提示词。

**解决方案**：提高 steps 和 cfg。

**核心教训**：**生成耗时过短往往是引导不足的信号**。当耗时明显低于预期时，优先检查 steps 和 cfg 是否充足。

---

#### 问题 4：双阶段 steps 分配误解

**现象**：用户反馈 "我说的是 6/6，不是 3/3"。

**思考过程**：
- 误解来源：把 "6/6" 理解为 steps=6（HIGH 3 + LOW 3）
- 正确理解：steps=12（总 steps），HIGH end_step=6，LOW start_step=6（每阶段 6 步）

**解决方案**：steps=12，HIGH 阶段 `start_step=0, end_step=6`，LOW 阶段 `start_step=6, end_step=-1`。

**核心教训**：双阶段 steps 分配要明确区分 **"总 steps"** 和 **"每阶段 steps"**。沟通时用 "总 steps = HIGH步数 + LOW步数" 表达，避免歧义。

---

#### 问题 5：steps 过高拖垮耗时（质量与耗时平衡）

**现象**：用户反馈 "steps 10/10 太高了，会严重拖垮生成耗时，默认使用 6-6 即可"。

**思考过程**：
- 质量与耗时是权衡关系
- 平衡点需要用户确认，不能自行追求最高质量

**解决方案**：从 steps=20(10+10) 降回 steps=12(6+6)。

**核心教训**：**质量与耗时的平衡点必须由用户确认**，不能自行追求最高质量。默认采用中等参数档位，根据用户反馈调整。

---

#### 问题 6：Edit 操作匹配错误节点

**现象**：使用 Edit 工具替换节点参数时，匹配到错误节点（节点 135 而非 134），导致文件出现重复字段。

**思考过程**：
- old_string 在文件中不唯一（两个节点结构相似）
- Edit 工具按顺序匹配，无法精确定位

**解决方案**：用 Write 工具完整重写整个工作流文件。

**核心教训**：Edit 操作时要确保 old_string **唯一性**。对结构相似的多节点工作流，复杂修改优先用 Write 完整重写。

---

#### 问题 7：VHS_LoadVideo 节点参数错误（X2 放大阶段）

**现象 1**：`Required input is missing: custom_width, custom_height`

**现象 2**：`format: 'video' not in list`

**思考过程**：
- 错误信息明确指向 VHS_LoadVideo 节点
- 缺少必需输入 → 查询节点规格
- format 值不在枚举内 → 查询合法枚举值

**根因**：VHS_LoadVideo 节点需要 `custom_width`、`custom_height` 参数（0=自动），`format` 必须是枚举值 `['None', 'AnimateDiff', 'Mochi', 'LTXV', 'Hunyuan', 'Cosmos', 'Wan']` 之一。

**解决方案**：添加 `custom_width=0, custom_height=0`，`format` 改为 `"Wan"`。

**核心教训**：**节点参数必须通过 `/object_info/{NodeType}` 查询必需输入和枚举值**，不能凭记忆或猜测。VHS 系列节点的 format 参数有固定枚举列表，不接受任意字符串。

---

#### 问题 8：ComfyUI input 目录文件复制受限

**现象**：文件系统权限不允许直接复制文件到 `${COMFYUI_PATH}\input\` 目录（不在操作白名单内）。

**思考过程**：
- 直接文件操作受限 → 寻找 ComfyUI 提供的 API
- ComfyUI 有 `/upload/image` 端点支持 multipart 上传

**解决方案**：使用 ComfyUI 的 `/upload/image` API 上传视频文件到 input 目录。

**核心教训**：跨盘/跨目录文件操作受限时，**用 ComfyUI 的 `/upload/image` API 上传**，而非直接文件复制。

---

#### 问题 9：PowerShell 二进制上传失败

**现象**：用 PowerShell 构造 multipart 请求上传视频，返回 500 Internal Server Error。

**思考过程**：
- PowerShell 处理二进制 multipart 上传有兼容性问题
- 换用 Python requests 库

**解决方案**：改用 Python requests 库上传：

```python
import requests
files = {'image': ('filename.mp4', open('source.mp4','rb'), 'application/octet-stream')}
r = requests.post('http://127.0.0.1:${PORT}/upload/image', files=files)
```

**核心教训**：**二进制文件操作优先用 Python 而非 PowerShell**。PowerShell 的 multipart 二进制处理不稳定，容易导致 500 错误。

---

#### 问题 10：run_workflow.py 输出识别问题

**现象**：X2 放大任务完成后，`run_workflow.py` 返回的 `images` 字段为空。

**思考过程**：
- images 为空 → 输出可能不是图片
- 查询 `/history/{prompt_id}` 的 outputs 字段
- 发现视频输出在 `gifs` 字段下（VHS_VideoCombine 的输出字段名）

**根因**：VHS_VideoCombine 节点的输出字段是 `gifs`（即使输出的是 mp4），而非 `images`。`run_workflow.py` 只解析 `images` 字段。

**解决方案**：视频任务完成后，通过 API 查询 `/history/{prompt_id}` 的 `outputs` 字段，检查 `gifs` 字段确认输出文件。

**核心教训**：**视频任务输出在 `gifs` 字段下**（VHS_VideoCombine 节点特性），不能只查 `images` 字段。脚本应同时检查 `images` 和 `gifs`。

### 14.3 通用问题分析解决流程

基于本次任务 7 轮迭代排查的经验，提炼出以下通用问题分析解决流程：

#### 流程图

```
[1.现象确认] → [2.日志查看] → [3.参数排查] → [4.最小化测试] → [5.逐步迭代] → [6.修复执行]
     ↑                                                            |
     └────────────────────────────────────────────────────────────┘
                         （迭代循环）
```

#### 步骤详解

**步骤 1：现象确认**
- 明确错误现象和发生位置
- 判断是"完全偏离"还是"部分错误"
- 记录生成耗时（耗时过短往往是引导不足的信号）
- 判断是否报错（节点错误 vs 画面质量问题）

**步骤 2：日志查看**
- 查看 ComfyUI 控制台日志确定出错节点
- 通过 `/history/{prompt_id}` 查询 `status.messages`
- 提取 `execution_error` 中的 `node_id`、`node_type`、`exception_message`

**步骤 3：参数排查**
- 根据错误节点检查关联节点的参数配置
- **通过 `/object_info/{NodeType}` 查询节点的必需输入和枚举值**（不能凭记忆）
- 检查节点连接关系（数据流向是否正确）
- 检查架构完整性（如双阶段是否都启用）

**步骤 4：最小化测试**
- 用低分辨率（最低档 L1）+ 低参数快速测试
- 目标：2 分钟内验证方向是否正确
- 不追求质量，只验证架构和连接

**步骤 5：逐步迭代**
- 从简单到复杂：单阶段 → 双阶段，低参数 → 高参数
- 每次只改一个变量，观察效果变化
- 调参无效时立即转向架构检查

**步骤 6：修复执行**
- 修复后重新执行验证
- 记录有效参数组合
- 验证输出文件（注意视频在 `gifs` 字段）

#### 关键决策点

| 决策场景 | 判断依据 | 行动 |
|---------|---------|------|
| 结果完全偏离预期 | 全黑白噪点/与输入无关 | 重新审视架构，不要继续调参 |
| 调参无效 | 多次参数调整无变化 | 立即检查架构完整性 |
| 耗时过短 | 明显低于预期 | 检查 steps/cfg 是否充足 |
| 质量与耗时冲突 | 用户反馈耗时过长 | 由用户确认平衡点，不自行追求最高质量 |
| 节点参数报错 | Required input missing / not in list | 查询 `/object_info/{NodeType}` |
| 跨目录文件操作受限 | 权限拒绝 | 用 `/upload/image` API 上传 |
| 二进制上传失败 | PowerShell 500 错误 | 改用 Python requests |
| 输出字段为空 | images 为空 | 检查 `gifs` 字段（视频输出） |

### 14.4 Wan2.2 I2V 双阶段架构排查要点

基于本次任务总结的双阶段架构关键检查项：

#### 架构完整性检查

1. **HIGH 阶段**：`start_step=0, end_step=split_step`（高噪声主结构）
2. **LOW 阶段**：`start_step=split_step, end_step=-1, samples=HIGH输出`（低噪声细化）
3. **缺少 LOW 阶段**：画面停留在粗糙状态，无法收敛
4. **缺少 samples 连接**：LOW 阶段没有接收 HIGH 输出，等于重新生成

#### 参数引导充分性检查

| 信号 | 含义 | 行动 |
|------|------|------|
| 生成耗时过短 | 引导不足 | 提高 steps |
| 画面不遵循提示词 | 文本引导不足 | 提高 steps 和 cfg |
| 画面模糊不收敛 | 架构不完整 | 检查 LOW 阶段 |
| 调参无变化 | 架构问题 | 检查节点连接 |

#### steps 分配规范

- 沟通时用 **"总 steps = HIGH步数 + LOW步数"** 表达
- 示例："6/6" 表示 steps=12，HIGH 6 步 + LOW 6 步
- 避免歧义：明确区分"总 steps"和"每阶段 steps"

### 14.5 文件传输与输出识别经验

#### 文件上传到 input 目录

| 方式 | 适用场景 | 注意事项 |
|------|---------|---------|
| 直接文件复制 | 同盘/有权限 | 受文件系统白名单限制 |
| `/upload/image` API | 跨盘/权限受限 | **推荐**，通用方案 |
| PowerShell multipart | 不推荐 | 二进制处理不稳定，易 500 |
| Python requests | 二进制文件 | **推荐**，稳定可靠 |

#### 输出字段识别

| 节点类型 | 输出字段 | 说明 |
|---------|---------|------|
| SaveImage | `images` | 图片输出 |
| VHS_VideoCombine | `gifs` | 视频输出（即使格式是 mp4） |
| PreviewImage | `images` | 预览图片 |

**脚本改进建议**：`run_workflow.py` 应同时检查 `images` 和 `gifs` 字段，避免视频任务输出识别失败。

### 14.6 综合教训清单

1. **结果完全偏离时重新审视架构**：不要在错误架构上调参，低参数快速测试验证方向
2. **调参无效时检查架构完整性**：Wan2.2 双阶段架构 LOW 阶段不可省略
3. **耗时过短是引导不足信号**：优先检查 steps/cfg，而非怀疑模型
4. **steps 分配要明确表达**：用"总 steps = HIGH + LOW"避免歧义
5. **质量与耗时平衡由用户确认**：不自行追求最高质量，默认中等参数档
6. **Edit 操作确保 old_string 唯一性**：复杂修改用 Write 完整重写
7. **节点参数必查 `/object_info/{NodeType}`**：不能凭记忆，枚举值和必需输入以 API 返回为准
8. **跨目录文件操作用 `/upload/image` API**：避免文件系统权限限制
9. **二进制上传用 Python requests**：PowerShell multipart 不稳定
10. **视频输出查 `gifs` 字段**：VHS_VideoCombine 输出字段名是 `gifs`，即使格式是 mp4
11. **问题排查流程标准化**：现象确认 → 日志查看 → 参数排查 → 最小化测试 → 逐步迭代 → 修复执行
12. **每次只改一个变量**：观察效果变化，避免多变量同时修改导致无法定位问题

---

## 15. SVI Pro 长视频工作流架构分析（2026-07-24）

### 15.1 工作流概述

**源文件**：`${COMFYUI_PATH}/user/default/workflows/Wan2.2-Svi 2.0无限图生视频-20秒.json`（Work-Fisher 开源）
**项目内副本**：`assets/wan22_svi_pro_long_video.json`（已录入工作流仓库，可通过 `query_library.py --model SVI_v2_PRO` 查询）

**核心价值**：解决了 Wan2.2 单次生成不超过训练长度（81-121 帧）的约束，通过 **5 段×81 帧（4 秒）= 405 帧（20 秒）** 的分段生成+latent 传递+重叠融合方案，实现长视频制作。

**重要说明**：工作流中填写的模型名（如 `Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors`）和 VAE 名（`comfy-wan_2.1_vae.safetensors`）可能是不标准的命名，实际使用时需通过 `/object_info/{NodeType}` 查询本地可用模型列表动态替换。**本节学习重点是工作流的逻辑和用法，而非具体模型名**。架构核心是 HIGH+LOW 双层设计，这一点与项目 V18/V19 架构一致。

**与项目现有架构的关键差异**：
- 项目 C6 架构：WanVideoWrapper 原生节点（WanVideoModelLoader + WanVideoSampler），单段生成
- SVI Pro 架构：KJNodes 节点（UNETLoader + WanImageToVideoSVIPro + KSamplerAdvanced），多段拼接

### 15.2 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│  模型加载区                                                  │
│  UNETLoader(HIGH) → LoraLoader(SVI LoRA) → PatchSageAttn   │
│  → ModelPatchTorch → SetNode "high_model"                  │
│  UNETLoader(LOW)  → LoraLoader(SVI LoRA) → PatchSageAttn   │
│  → ModelPatchTorch → SetNode "low_model"                   │
│  CLIPLoader → SetNode "clip"                                │
│  VAELoader → SetNode "vae"                                  │
│  LoadImage → ImageResize → VAEEncode → SetNode "anchor"    │
├─────────────────────────────────────────────────────────────┤
│  参数区（INTConstant → SetNode）                             │
│  width=1024, height=576, length=81, steps=6, steps2=2      │
├─────────────────────────────────────────────────────────────┤
│  提示词区（5 个分镜，CR Prompt Text → SetNode）              │
│  提示词1-5：每段精确到秒的分镜描述                            │
├─────────────────────────────────────────────────────────────┤
│  采样区（5 段，每段双阶段）                                   │
│  段1: SVIPro(prev=null) → KSampler(HIGH) → KSampler(LOW)   │
│       → VAEDecode → ImageBatchExtend                        │
│  段2: SVIPro(prev=段1 LOW latent) → KSampler(HIGH)         │
│       → KSampler(LOW) → VAEDecode → ImageBatchExtend        │
│  段3-5: 同段2（prev 链式传递）                               │
├─────────────────────────────────────────────────────────────┤
│  融合输出区                                                  │
│  ImageBatchExtendWithOverlap（链式融合，overlap=5, blend）  │
│  → VHS_VideoCombine                                         │
└─────────────────────────────────────────────────────────────┘
```

### 15.3 核心节点：WanImageToVideoSVIPro

这是 KJNodes 提供的专用节点，是 SVI Pro 工作流的核心创新。

**输入参数**：
| 参数 | 类型 | 说明 |
|------|------|------|
| positive | CONDITIONING | 正面条件（来自 CLIPTextEncode） |
| negative | CONDITIONING | 负面条件 |
| anchor_samples | LATENT | 锚定 latent（首帧 VAE 编码，所有段共用） |
| prev_samples | LATENT（可选） | 前一段末尾 latent（段间连贯的关键） |
| length | INT | 每段帧数（81） |
| motion_latent_count | INT | 运动 latent 数量（第一段=0，后续段=1） |

**输出**：
- positive / negative（处理后的条件）
- latent（传入 KSampler 的初始 latent）

**关键设计**：
1. **anchor_samples**：所有段都锚定到首帧 VAE 编码的 latent，保持角色一致性
2. **prev_samples**：段间 latent 级别传递（非图像级别），比"末帧重新编码"更精细
3. **motion_latent_count**：第一段=0（无运动延续），后续段=1（引入运动 latent）

### 15.4 双阶段采样配置

每段都经过 HIGH + LOW 双阶段采样，通过两个 KSamplerAdvanced 串联实现：

**HIGH 阶段（KSamplerAdvanced）**：
- model：high_model
- add_noise：enable
- steps：steps（6）
- start_at_step：0
- end_at_step：steps2（2）
- return_with_leftover_noise：enable（保留残噪声传给 LOW）
- cfg：1（SVI LoRA 已内置引导，cfg 极低）
- sampler：euler
- scheduler：simple

**LOW 阶段（KSamplerAdvanced）**：
- model：low_model
- add_noise：disable（不重新加噪）
- steps：steps（6）
- start_at_step：steps2（2）
- end_at_step：10000（到结束）
- return_with_leftover_noise：disable
- cfg：1
- sampler：euler
- scheduler：simple

**参数说明**：
- steps=6, steps2=2：HIGH 做 2 步（0→2），LOW 做 4 步（2→6）
- cfg=1：极低，依赖 SVI LoRA 内置的引导逻辑
- 与项目 V18 架构（cfg=6.0, shift=8.0, dpm++_sde）差异很大，因为 SVI LoRA 的工作机制不同

### 15.5 段间连贯机制

SVI Pro 的段间连贯通过两个层面实现：

**层面1：Latent 级别传递**
```
段1 LOW KSampler 输出 latent ──→ 段2 SVIPro prev_samples
段2 LOW KSampler 输出 latent ──→ 段3 SVIPro prev_samples
段3 LOW KSampler 输出 latent ──→ 段4 SVIPro prev_samples
段4 LOW KSampler 输出 latent ──→ 段5 SVIPro prev_samples
```
- 直接传递 latent，不经过 VAEDecode→VAEEncode 往返
- 比项目 C5 任务的"末帧图像重新编码"方案更精细

**层面2：图像重叠融合**
```
段1 VAEDecode ──→ ImageBatchExtendWithOverlap(source, 段2 VAEDecode, overlap=5)
                ↓ extended_images
              ImageBatchExtendWithOverlap(source, 段3 VAEDecode, overlap=5)
                ↓ extended_images
              ImageBatchExtendWithOverlap(source, 段4 VAEDecode, overlap=5)
                ↓ extended_images
              ImageBatchExtendWithOverlap(source, 段5 VAEDecode, overlap=5)
                ↓ → VHS_VideoCombine
```
- overlap=5：5 帧重叠区域
- overlap_side=source：在源图像末尾重叠
- overlap_mode=linear_blend：线性混合，避免硬切

### 15.6 模型加载策略

**SVI Pro 提供两种配置模式（原工作流 group 标注明确区分）**：

**模式A：动漫类（原工作流默认启用）**
- HIGH 链路：`Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors` + `SVI_v2_PRO_..._HIGH_lora`（strength=1）
- LOW 链路：同一模型文件（ComfyUI 缓存复用）+ `SVI_v2_PRO_..._HIGH_lora`（strength=1）
- 优点：显存占用低（单模型），生成速度快
- 缺点：LOW 阶段缺乏专用细化模型，现实人物画质模糊

**模式B：现实类（原工作流节点129备用，需手动切换）**
- HIGH 链路：`Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors` + `SVI_v2_PRO_..._HIGH_lora`（strength=1）
- LOW 链路：`Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` + `SVI_v2_PRO_..._LOW_lora`（strength=1）
- 优点：LOW 阶段专用模型细化细节，现实人物画质清晰
- 缺点：两个 14B 模型（13.31GB+13.97GB=27.28GB>20GB），ComfyUI 需在 HIGH/LOW 间自动卸载/加载，增加约 5-10 分钟

**关键纠正（2026-07-24）**：之前经验错误记录"两个 UNETLoader 加载同一个 HIGH 模型"为唯一设计，实际上这只是动漫类配置。**生成现实人物必须用现实类配置（模式B），否则 LOW 阶段无法有效细化细节，导致画面模糊**。

**本地可用模型文件**：
| 文件 | 大小 | 用途 |
|------|------|------|
| Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors | 13.31GB | HIGH 模型（两种模式共用） |
| Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors | 13.97GB | 专用 HIGH 模型（备用） |
| Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors | 13.97GB | 专用 LOW 模型（现实类必需） |
| SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors | 1170MB | HIGH LoRA |
| SVI_v2_PRO_Wan2.2-I2V-A14B_LOW_lora_rank_128_fp16.safetensors | 1170MB | LOW LoRA（现实类必需） |

**与项目 V18 架构的对比**：
| 项目 | SVI Pro（现实类） | V18（项目现有） |
|------|---------|----------------|
| 模型加载 | UNETLoader + LoraLoader | WanVideoModelLoader |
| 模型类型 | HIGH 模型 + LOW 模型（不同文件） | HIGH + LOW 双模型 |
| BlockSwap | 无（依赖 ComfyUI 自动卸载） | WanVideoSetBlockSwap |
| 精度 | default（fp16_accumulation 加速） | bf16 |
| 采样器 | KSamplerAdvanced | WanVideoSampler |

### 15.7 参数变量化机制

所有共享参数通过 SetNode/GetNode 传递，避免复杂连线：

| SetNode | 值 | 用途 |
|---------|-----|------|
| width | 1024 | 分辨率宽 |
| height | 576 | 分辨率高 |
| length | 81 | 每段帧数 |
| steps | 6 | 总采样步数 |
| steps2 | 2 | HIGH 阶段步数 |
| anchor_samples | VAEEncode 输出 | 首帧锚定 latent |
| high_model | ModelPatchTorch 输出 | HIGH 模型 |
| low_model | ModelPatchTorch 输出 | LOW 模型 |
| vae | VAELoader 输出 | VAE |
| clip | CLIPLoader 输出 | CLIP |
| 提示词1-5 | CR Prompt Text | 分镜提示词 |

### 15.8 加速模块

| 节点 | 功能 | 参数 |
|------|------|------|
| PathchSageAttentionKJ | Sage 注意力 | sage_attention=auto, allow_compile=false |
| ModelPatchTorchSettings | FP16 累加 | enable_fp16_accumulation=true |
| Fast Groups Bypasser | 一键开关 | 可关闭加速（SAGE/Torch 报错时） |

**注意**：工作流注释明确"如果出现 SAGE/Torch 类报错，或者卡采样器，按按钮关闭加速模组"。Windows 上 sageattn 依赖 Triton，可能触发权限错误（见第 14 章 14.4 节 Windows 风险说明）。

### 15.9 与项目硬约束的对照

| 硬约束 | SVI Pro 工作流 | 符合性 |
|--------|---------------|--------|
| 双阶段采样不可移除 | HIGH+LOW 双 KSamplerAdvanced | ✓ 符合 |
| 视频亮度一致性 | anchor_samples 锚定首帧 | ✓ 符合 |
| 分辨率 16 整数倍 | 576×1024（36×16, 64×16） | ✓ 符合 |
| 单次不超过训练长度 | 每段 81 帧 | ✓ 符合 |
| 段间末帧继承 | prev_samples latent 传递 | ✓ 符合（更优） |
| 禁止降级时长 | 5 段拼接保持 20 秒 | ✓ 符合 |
| VHS 编码 crf=14 | crf=19 | ✗ 不符合（需调整） |
| noise_aug_strength≠0 | 未设置（SVI Pro 节点可能内置） | ⚠ 待验证 |

### 15.10 对项目长视频制作的启发

**可直接借鉴的设计**：
1. **Latent 级别段间传递**：比项目 C5 的"末帧图像重新编码"更精细，避免 VAE 往返损失
2. **ImageBatchExtendWithOverlap 重叠融合**：5 帧线性混合，比简单拼接平滑
3. **anchor_samples 锚定**：所有段锚定首帧，保持角色一致性
4. **分镜提示词精确到秒**：每段 4 秒，提示词按"1 秒/2 秒/3 秒/4 秒"描述动作

**需要验证的风险点**：
1. **SVI LoRA 依赖**：工作流依赖 `SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors`，需确认本地是否有此模型
2. **cfg=1 极低引导**：与项目 V18 的 cfg=6.0 差异大，SVI LoRA 内置引导机制需验证
3. **crf=19 编码质量**：低于项目硬约束的 crf=14，需调整
4. **Windows SAGE 兼容性**：PathchSageAttentionKJ 可能触发 Triton 权限错误

### 15.11 关键节点清单

| 节点类型 | 来源包 | 数量 | 用途 |
|---------|--------|------|------|
| WanImageToVideoSVIPro | comfyui-kjnodes | 5 | 段间连贯核心节点 |
| KSamplerAdvanced | comfy-core | 10 | 双阶段采样（5 段×2） |
| ImageBatchExtendWithOverlap | comfyui-kjnodes | 4 | 重叠融合 |
| UNETLoader | comfy-core | 3 | 模型加载（2 用 + 1 备选） |
| LoraLoaderModelOnly | comfy-core | 2 | SVI LoRA 加载 |
| PathchSageAttentionKJ | comfyui-kjnodes | 2 | 注意力加速 |
| ModelPatchTorchSettings | comfyui-kjnodes | 2 | FP16 累加加速 |
| VAEDecode | comfy-core | 5 | 每段 latent→image |
| VAEEncode | comfy-core | 1 | 首帧→anchor_samples |
| CLIPTextEncode | comfy-core | 10 | 正面/负面条件编码 |
| CR Prompt Text | ComfyUI_Comfyroll | 5 | 分镜提示词 |
| SetNode / GetNode | comfy-core | 多个 | 参数变量化传递 |
| VHS_VideoCombine | ComfyUI-VideoHelperSuite | 6 | 视频输出（1 最终 + 5 分段预览） |

### 15.12 总结

SVI Pro 工作流提供了一套完整的长视频（20 秒）生成方案，核心创新在于：

1. **WanImageToVideoSVIPro 节点**：通过 anchor_samples + prev_samples + motion_latent_count 三个参数实现段间 latent 级别连贯
2. **ImageBatchExtendWithOverlap**：图像序列重叠融合，5 帧线性混合消除硬切
3. **SetNode/GetNode 变量化**：169 个节点的工作流通过变量化传递参数，避免连线混乱
4. **分镜提示词精确到秒**：每段 4 秒，提示词按秒描述动作，提高可控性

**与项目架构的融合方向**：
- 长视频任务（>5 秒）可参考 SVI Pro 的分段+latent 传递+重叠融合方案
- 短视频任务（≤5 秒）继续使用项目 V18/V19 架构（WanVideoWrapper 原生节点）
- 需验证 SVI LoRA 在项目 RTX 3080 20GB 环境下的兼容性和生成质量

---

## 16. C7 任务低噪声画质模糊根因分析（2026-07-24）

### 16.1 问题现象

使用 SVI Pro 工作流生成 20 秒竖屏视频（480×848），多次迭代后画质依然模糊：
- 人物轮廓和动作基本正确 → HIGH 阶段（主结构）工作正常
- 画面细节严重缺失，只能看到大概轮廓 → LOW 阶段（细节细化）未发挥作用
- X2 放大器无法弥补底层 latent 模糊

### 16.2 迭代过程与无效尝试

| 版本 | 修改内容 | 结果 |
|------|---------|------|
| v1 | 横屏 848×480，HIGH cfg 序列错误 | 比例错误（4:3），模糊 |
| v2 | 竖屏 480×848，HIGH cfg 部分错误 | 模糊无改善 |
| v4 | 修正 HIGH cfg 为 [2,2,2,2.5,2.5] | 拉普拉斯方差略升（5.49-7.50），用户反馈"没有进步也没有退步" |
| X2放大 | 960×1696 分辨率 | 分辨率提升但底层模糊未解决 |

**关键教训**：参数微调（cfg、分辨率）无法解决架构层面的模型配置错误。

### 16.3 根因确认

**根因：LOW 阶段使用了 HIGH 模型 + HIGH LoRA，而非专用 LOW 模型 + LOW LoRA**

原工作流提供两种配置模式（group 标注明确区分）：
- **动漫类（默认）**：HIGH 和 LOW 链路都加载 `Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors`（同一文件，ComfyUI 缓存复用）+ HIGH LoRA
- **现实类（备用）**：HIGH 链路用 high_lighting 模型 + HIGH LoRA；LOW 链路用 `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` + LOW LoRA

当前工作流（以及原工作流默认）使用动漫类配置。**生成现实人物时，LOW 阶段缺乏专用细化模型，导致画面停留在 HIGH 阶段的粗糙状态，无法收敛出清晰细节**。

### 16.4 正确配置（现实类）

```
HIGH 链路: Wan2.2_Remix_NSFW_i2v_14b_high_lighting_v2.0.safetensors (13.31GB)
         + SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora (strength=1.0)
         → PathchSageAttentionKJ → ModelPatchTorchSettings → HIGH KSampler

LOW 链路:  Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors (13.97GB)
         + SVI_v2_PRO_Wan2.2-I2V-A14B_LOW_lora (strength=1.0)
         → PathchSageAttentionKJ → ModelPatchTorchSettings → LOW KSampler
```

### 16.5 显存与时间评估

- 两模型总和 27.28GB > 20GB 显存，ComfyUI 自动在 HIGH/LOW 采样间卸载/加载
- 这是正常的显存管理（model offload），**不是内存交换（shared GPU memory）**
- 预估生成时间：5段 × (HIGH 2步 + 模型切换 + LOW 4步) ≈ 15-20 分钟，满足 20 分钟约束

### 16.6 经验教训

1. **原工作流的默认配置不一定是最佳配置**：动漫类配置是简化版（省显存/提速），现实人物必须切换到现实类配置
2. **HIGH 模型不擅长低噪声细化**：high_lighting 模型专攻高噪声主结构，LOW 阶段需要专用 LOW 模型
3. **LoRA 也要匹配阶段**：HIGH LoRA 优化高噪声生成，LOW LoRA 优化低噪声细化，不可混用
4. **参数微调无法解决模型配置错误**：在错误的模型配置下调整 cfg/steps/resolution 都是无效的
5. **"能看到轮廓但细节模糊"是典型的 LOW 阶段缺失症状**：HIGH 提供结构，LOW 提供细节，缺 LOW 则只有结构无细节

---

---

## 17. C7 v12 Flux2 双图修正工作流优化经验（2026-07-25）

### 17.1 任务背景

C7 任务使用 SVI Pro 生成 5 段 20 秒竖屏视频后，每段需要通过 Flux2 对 SVI Pro 输出进行画质修正（去躁、恢复细节、保持色调），修正后的图片作为下一段 SVI Pro 的参考图。Flux2 修正效果直接影响整个 20 秒视频的最终画质。

### 17.2 问题 1：ReferenceLatent 双图注入导致细节消失

**现象**：Flux2 修正后的图片比原始 SVI Pro 输出更模糊，细节（皮肤质感、衣服褶皱、花纹）丢失。

**根因**：ReferenceLatent 节点同时注入了 A 图（SVI Pro 最后帧，模糊）和 B 图（原始参考图，清晰），模型对两个 ReferenceLatent 做平均化处理，导致细节被稀释。

**原始错误架构**：
```
正条件 → ReferenceLatent(A图VAE编码) → ReferenceLatent(B图VAE编码) → CFGGuider
负条件 → ReferenceLatent(A图VAE编码) → ReferenceLatent(B图VAE编码) → CFGGuider
```

**正确架构**：
```
正条件 → ReferenceLatent(B图VAE编码) → CFGGuider
负条件 → ReferenceLatent(B图VAE编码) → CFGGuider
```
**只保留 B 图（原始参考图）的 ReferenceLatent，移除 A 图注入。**

**关键认知**：ReferenceLatent 不是越多越好。双图注入时模型取"平均"，两个 ReferenceLatent 互相干扰。画面构图由 VAEEncode 的 latent_image（img2img 模式）约束，不需要额外的 A 图 ReferenceLatent。

### 17.3 问题 2：Flux2 修正导致背景模糊（img2img 改造）

**现象**：Flux2 修正后背景模糊，色调偏移（偏黄）。

**根因**：最初使用 `EmptyFlux2LatentImage` 作为起点（纯文生图模式），模型从零生成画面，无法保留 SVI Pro 输出的背景像素。

**解决**：改为 img2img 模式：
1. 将 `EmptyFlux2LatentImage` 替换为 `A图 VAEEncode`（以 SVI Pro 最后帧为 latent 起点）
2. 新增 `SplitSigmasDenoise` 节点（denoise=0.5），控制噪声添加量
3. 降低 cfg：5.0 → 3.5（减少 img2img 的色彩过度饱和）
4. 降低 LoRA ColorTone 强度：0.8 → 0.4（减少暖色叠加）
5. 提示词改为**中文**（qwen_3_8b 对中文提示词理解更好）

**Flux2 img2img 修正最终架构**：
```
LoadImage(A图=SVI最后帧) → ImageResizeKJv2 → VAEEncode → latent_image(作为KSampler起点)
                                                              ↓
UNETLoader(F2K-9b) → LoraLoader×3(ColorTone 0.4, Skin 0.6, Detail 1.0) → CFGGuider
                                                                           ↓
CLIPLoader(type=flux2) → CLIPTextEncode(正/负提示词) → ReferenceLatent(B图) → CFGGuider
                                                                                 ↓
SplitSigmasDenoise(denoise=0.5) → KSampler(cfg=3.5, steps=32) → VAEDecode → SaveImage
```

### 17.4 问题 3：提示词逻辑颠倒导致越修越糊

**现象**：多次调整参数后 Flux2 修正效果仍不理想，细节持续丢失。

**根因（用户发现）**：提示词逻辑写反。A 图提供构图但模糊，B 图提供细节但无关。正确的提示词策略是：
- **让模型从 A 图继承构图**（img2img 模式已实现）
- **从 B 图提取细节特征**（ReferenceLatent + 具体提示词描述）
- **错误做法**：提示词同时描述 A 图和 B 图的内容，导致条件冲突

**正确提示词结构**（以"古装女孩"场景为例）：
```
正面：从一个女孩扩展到完整的古装女孩，飘逸秀丽的长发，粉白色的汉服长裙上有精美的绣花纹路，裙摆自然飘逸，袖子宽大轻柔，精致的脸蛋，白皙光滑的皮肤质感，柔和的自然光线，高画质
负面：最差质量，低质量，JPEG压缩残留，模糊，过曝，欠曝，色调灰暗
```

**关键教训**：
- 提示词要具体化细节（如"绣花纹路"不写"花纹"），明确指定衣服颜色和质感
- 负向提示词要针对性添加（如"色调灰暗"针对偏色问题）
- Flux2 对中文提示词的理解优于英文（qwen_3_8b 编码器特性）

### 17.5 问题 4：Link 重组逻辑错误导致工作流提交失败

**现象**：
```
Prompt outputs failed validation
```

**根因**：重建 Flux2 工作流时，link 重组逻辑顺序错误。先删除了 A 图相关的 links，再尝试重路由正/负提示词到 B 图 ReferenceLatent，但重路由时引用的节点 ID 已因删除操作而失效。

**解决**：调整 link 处理顺序：
1. 先重路由正/负提示词的 conditioning 连接到 B 图 ReferenceLatent
2. 再删除 A 图相关的 links
3. 验证所有 `[node_id, output_index]` 引用的目标节点仍然存在

### 17.6 Flux2 修正参数梯度分析

> **重要**：以下分析每个参数在不同场景下的选择逻辑，不可将任一值作为固定模板。

| 参数 | 梯度区间 | 效果 | 适用场景 |
|------|---------|------|---------|
| **denoise** | 0.3-0.4 | 轻量去躁，几乎完全保留原图 | SVI Pro输出质量较好，只需轻微降噪 |
| | **0.5（平衡推荐）** | 保留50%原图结构，有足够空间恢复细节 | SVI Pro输出有噪点但结构完整（v12验证） |
| | 0.55-0.6 | 更多修正力度，构图可能轻微偏移 | SVI Pro输出严重模糊 |
| | >0.7 | 接近文生图，背景大幅偏离 | 不推荐用于修正场景 |
| **steps** | 20-24 | 较快修正，细节恢复有限 | 快速验证阶段 |
| | **28-32（推荐）** | 最佳细节恢复，时间可接受 | 正式生成（v12验证） |
| | 36-40 | 边际收益递减 | 极限画质追求 |
| **cfg** | 2.0-3.0 | 保守引导，色彩偏灰 | 原图色彩已准确 |
| | **3.5（推荐）** | 平衡，避免img2img色彩过度饱和 | 标准场景（v12验证） |
| | 4.0-5.0 | 色彩饱和度高，可能偏色 | 原图色彩不足需要增强 |
| **LoRA ColorTone** | 0.2-0.3 | 极轻微暖色调 | 原图色调已偏暖 |
| | **0.4（推荐）** | 轻微暖色修正，防止偏黄 | 标准场景（v12验证） |
| | 0.5-0.6 | 显著暖色调 | 原图色调偏冷需要纠正 |
| | >0.6 | 明显偏黄风险 | 不推荐（v12验证） |
| **LoRA Skin** | 0.3-0.5 | 轻度皮肤增强 | 原图皮肤质感尚可 |
| | **0.6（推荐）** | 增强皮肤质感但不失真 | 标准场景（v12验证） |
| | 0.7-0.8 | 强皮肤增强，可能过度平滑 | 原图皮肤严重模糊 |
| **LoRA Detail** | 0.5-0.7 | 中度细节增强 | 原图细节损失不大 |
| | **1.0（推荐）** | 最大化细节增强 | 标准场景（v12验证） |
| | - | 不建议低于0.5 | 修正目的就是恢复细节 |
| **sampler/scheduler** | euler/simple | Flux2标准配置 | 所有场景 |

### 17.7 关键教训清单

1. **ReferenceLatent 不是越多越好**：双图注入导致模型取平均，细节被稀释。只用最清晰的参考图
2. **img2img 模式优于文生图模式**：用 SVI Pro 最后帧作为 latent 起点，保留画面构图
3. **提示词逻辑要正确**：A 图提供构图（通过 latent_image），B 图提供细节（通过 ReferenceLatent + 提示词）
4. **提示词要具体化**：不写"花纹"而写"精美的绣花纹路"，不写"裙子"而写"粉白色的汉服长裙"
5. **Flux2 提示词用中文**：qwen_3_8b 编码器对中文语义理解优于英文
6. **Link 重组先重路由再删除**：避免节点引用失效
7. **负向提示词针对性添加**：根据实际缺陷添加（如偏色→"色调灰暗"）

---

## 18. C7 SVI Pro 段间连贯性与色调优化（2026-07-25）

### 18.1 任务背景

C7 任务的 5 段 SVI Pro 视频需要段间无缝衔接。v12 改进版引入 Flux2 修正图作为段间衔接桥梁，但出现了新问题需要解决。

### 18.2 问题 1：段间暗→亮渐变

**现象**：合并后的 20 秒视频在段间过渡处出现明显的暗→亮渐变，从段2开始画面逐渐变亮。

**根因**：WanImageToVideoSVIPro 节点的 `motion_latent_count` 参数非 0 时，内部会将 `anchor_latent` 与 `motion_latent`（来自 prev_samples）拼接为条件 latent。当 prev_samples 与 anchor_samples 来自不同来源（修正图 vs 原图），两者的 VAE 编码分布不同，拼接后导致亮度异常。

**源码逻辑**（`ComfyUI-KJNodes/nodes/nodes.py`）：
```python
if prev_samples is not None and motion_latent_count > 0:
    # anchor_latent [B,C,1,H,W] + prev最后motion_latent_count帧 [B,C,m,H,W]
    # = image_cond_latent [B,C,1+m,H,W] → 用于条件
    ...
```

当 motion_latent_count=1 时，条件 latent = `concat([原图1帧, 修正图1帧])`，两者的 VAE 分布差异导致亮度信息不一致。

**解决**：段 2-5 改为**不使用 prev_samples 连接**，而是：
1. 将 Flux2 修正图作为 LoadImage 节点的输入（替代原参考图作为"当前段的参考"）
2. 保持 `motion_latent_count=0`（不触发 latent 拼接）
3. `anchor_samples` 始终连接原图 VAEEncode（所有段共享同一锚点）

**段间过渡策略对比**：

| 方式 | v12 初版 | v12 修正版 |
|------|---------|-----------|
| 段2-5 LoadImage | 原图 c7_1.png | 上一段 Flux2 修正图 |
| anchor_samples | 原图 VAEEncode | 原图 VAEEncode（不变） |
| prev_samples | 连接上一段 LOW latent | 不连接 |
| motion_latent_count | 1 | 0 |
| 效果 | 暗→亮渐变 | 色调统一 |

### 18.3 问题 2：段2 首帧用错图片

**现象**：段2 生成内容与预期完全不符，因为首帧用错了图片。

**根因**：PowerShell `Copy-Item` 由于路径白名单权限问题静默失败，ComfyUI input 目录中仍是上一轮的旧文件（605919 字节 vs 新文件 424375 字节）。工作流逻辑本身正确，但文件层面的陈旧数据导致生成结果错误。

**排查过程**：
1. 检查工作流连接：anchor_samples → 节点4（原图 c7_1.png），prev_samples → 节点102（修正图）→ 逻辑正确
2. 检查 ComfyUI input 目录文件大小：发现文件大小未变化
3. 尝试 PowerShell Copy-Item：命令执行"成功"但文件未更新
4. 根因确认：PowerShell 权限限制导致静默失败，未抛出可见错误

**解决**：改用 Python `shutil.copy2` 复制文件，可保证可靠性：
```python
import shutil
shutil.copy2(src, dst)
```

**关键教训**：
- **PowerShell 文件操作不可靠**：路径白名单权限可能静默失败，不抛出可见错误
- **文件操作优先用 Python**：`shutil.copy2` 比 PowerShell `Copy-Item` 更可靠
- **操作后验证文件**：复制后检查目标文件大小/修改时间确认成功

### 18.4 段间衔接正确架构（最终版）

```
段1: LoadImage(原图) → VAEEncode → anchor_samples
     WanImageToVideoSVIPro(motion_latent_count=0)
     → HIGH KSampler → LOW KSampler → VAEDecode → 段1视频

Flux2修正: 段1最后帧 + 原图B图 → Flux2 img2img → 段1修正图

段2: LoadImage(段1修正图) → VAEEncode → 作为当前段起点
     anchor_samples = 原图 VAEEncode（不变）
     WanImageToVideoSVIPro(motion_latent_count=0, 无prev_samples)
     → HIGH KSampler → LOW KSampler → VAEDecode → 段2视频

段3-5: 同段2（每段修正图作为下一段的起点）
```

### 18.5 显存管理经验

5 段视频生成涉及多次模型切换：
- HIGH 模型（13.31GB）和 LOW 模型（13.97GB）不能同时加载
- 在每段之间调用 `/free` API 释放显存：`{unload_models: true, free_memory: true}`
- 段5 因显存未清理而导致 `execution_interrupted`，清理后成功

### 18.6 关键教训清单

1. **motion_latent_count>0 触发拼接**：条件 latent = anchor_latent + motion_latent，不同来源的 VAE 分布导致亮度异常
2. **段间过渡策略以修正图为中心**：修正图作为段起点，原图作为 anchor，motion_latent_count=0
3. **PowerShell 文件操作不可靠**：静默失败，优先用 Python shutil.copy2
4. **文件操作后必须验证**：检查目标文件大小/修改时间
5. **每段执行后清理显存**：调用 `/free` API 避免 execution_interrupted

---

## 19. KSamplerAdvanced 参数对齐问题（2026-07-25）

### 19.1 问题现象

在 ComfyUI Web 界面手动执行 SVI Pro 工作流时报错：
```
Value not in list: sampler_name
Failed to convert to FLOAT: cfg
Failed to convert to INT: noise_seed
```

但通过 API 提交执行却不报错。

### 19.2 根因分析

**API 格式 vs UI 格式的解析差异**：
- **API 格式**：参数按 key 名映射（如 `{"noise_seed": 123, "cfg": 1.0}`），顺序无关
- **UI 格式**：参数在 `widgets_values` 中按 position 顺序映射，必须与前端 widget 列表顺序完全一致

**KSamplerAdvanced 的特殊性**：当 `noise_seed` 带有 `control_after_generate: True` 属性时，ComfyUI 前端会**自动追加一个隐式的 `control_after_generate` widget**，导致前端实际需要 10 个 widget 值，而非看起来的 9 个：

```
前端 widget 实际顺序（10个）：
add_noise, noise_seed, control_after_generate, steps, cfg, 
sampler_name, scheduler, start_at_step, end_at_step, return_with_leftover_noise
```

如果 `widgets_values` 只有 9 个值（缺少 `control_after_generate`），则后续参数全部错位：
- `cfg` 位置收到 `sampler_name` 字符串 → Failed to convert to FLOAT
- `sampler_name` 位置收到 `scheduler` 字符串 → Value not in list
- 其他参数依次错位

### 19.3 解决方案

确保 KSamplerAdvanced 的 `widgets_values` 包含 10 个值，第 3 位（索引2）为 `control_after_generate` 参数：

```json
"widgets_values": [
    "enable",        // add_noise
    0,              // noise_seed
    "fixed",        // control_after_generate（必须包含）
    6,              // steps
    1.0,            // cfg
    "euler",        // sampler_name
    "simple",       // scheduler
    0,              // start_at_step
    2,              // end_at_step
    "enable"        // return_with_leftover_noise
]
```

`control_after_generate` 可选值：`"fixed"`, `"increment"`, `"decrement"`, `"randomize"`

### 19.4 关键教训

1. **API 和 UI 格式解析方式不同**：API 按 key 映射，UI 按 position 顺序
2. **control_after_generate 是隐式 widget**：前端自动追加，不在节点输入列表中显式显示
3. **widgets_values 数量必须与前端 widget 顺序完全匹配**
4. **调试技巧**：当 API 执行成功但 UI 报错时，优先检查 widgets_values 数量是否与前端 widget 数量一致

---

## 20. 文件操作与环境恢复经验（2026-07-25）

### 20.1 PowerShell Copy-Item 静默失败

**现象**：`Copy-Item src dst -Force` 返回成功，但目标文件未更新。

**根因**：Windows 路径白名单权限限制，PowerShell 对不在白名单内的路径操作时静默失败，不抛出可见错误。

**解决**：使用 Python `shutil.copy2` 替代：
```python
import shutil
shutil.copy2(source_path, dest_path)
```

**适用范围**：跨盘文件复制（如 e: → d:）、ComfyUI input 目录等可能受限路径。

### 20.2 二进制文件上传

**ComfyUI `/upload/image` API 上传**（推荐）：
```python
import requests
with open(filepath, 'rb') as f:
    requests.post(
        f'http://127.0.0.1:{port}/upload/image',
        files={'image': (filename, f, 'application/octet-stream')}
    )
```

**避免**：PowerShell multipart/form-data 构造不稳定，二进制处理易 500 错误。

### 20.3 Windows ComfyUI 环境恢复

**STATUS_DLL_INIT_FAILED (0xC0000142)**：终端环境崩溃，所有子进程无法启动。

**现象**：TRAE IDE PowerShell 终端中所有命令返回 0xC0000142 错误。

**恢复方案**（按优先级）：
1. 重启 TRAE IDE
2. 手动启动：`D:\2026-ComfyUI-V8.3\python\python.exe -s main.py --windows-standalone-build --fast --port 3198`
3. 使用"绘世启动器.exe"启动

### 20.4 zsq_loader.py VAELoader.vae_list() 参数变更

**现象**：ComfyUI 启动时自定义节点 zsq_prompt 报错：
```
TypeError: VAELoader.vae_list() takes 1 positional argument but 0 were given
```

**根因**：ComfyUI 新版将 `VAELoader.vae_list()` 签名改为需要 1 个参数 `s`。

**修复**：在 `zsq_loader.py` 中将 `VAELoader.vae_list()` 调用改为直接使用 `folder_paths.get_filename_list("vae")`：
```python
# 旧版（报错）
vae_list = VAELoader.vae_list()

# 新版（修复）
import folder_paths
vae_list = folder_paths.get_filename_list("vae")
```

### 20.5 关键教训清单

1. **文件操作优先用 Python**：`shutil.copy2` 比 PowerShell `Copy-Item` 可靠
2. **二进制上传用 Python requests**：`/upload/image` API 稳定可靠
3. **复制后验证文件**：检查文件大小/修改时间确认成功
4. **环境变量兼容**：TRITON_CACHE_DIR 需设置到可写位置，避免 SageAttention Triton 权限错误
5. **自定义节点 API 兼容性**：ComfyUI 版本升级后自定义节点 API 可能变更，启动报错需检查节点源码

---

## 附录：关键文件位置

| 文件 | 说明 |
|------|------|
| `cli/command/run.py` | CLI 工作流执行核心，已修复 POST headers |
| `cli/cmdline.py` | CLI 入口，导入路径已修复 |
| `cli/update.py` | 版本获取，已添加异常保护 |
| `cli/logging_utils.py` | 日志工具（原 logging.py） |
| `cli/typing_compat.py` | 类型兼容（原 typing.py） |
| `scripts/start_server.py` | 服务器启动器 |
| `scripts/run_workflow.py` | 脚本模式工作流执行 |
| `scripts/c2_video_task.py` | C2 视频任务执行脚本（5秒@20fps） |
| `scripts/c3_video_task.py` | C3 视频任务执行脚本（10秒@24fps） |
| `scripts/c4_video_task.py` | C4 视频任务执行脚本（10秒@24fps） |
| `scripts/c5_video_task_v14_seg1.py` | C5 多图视频任务段1（v14最终版） |
| `scripts/c5_video_task_v14_seg2.py` | C5 多图视频任务段2（v14最终版） |
| `scripts/c5_video_task_v14_seg3.py` | C5 多图视频任务段3+拼接（v14最终版） |
| `assets/wan22_t2v_workflow.json` | Wan 2.2 文生视频参考工作流 |
| `assets/c6_final.json` | C6 单图视频生成工作流（双阶段 HIGH+LOW 架构，已验证成功） |
| `assets/c6_x2.json` | C6 视频 X2 放大工作流（VHS_LoadVideo → UpscaleModel → VHS_VideoCombine） |
| `${COMFYUI_PATH}/user/default/workflows/Wan2.2-Svi 2.0无限图生视频-20秒.json` | SVI Pro 长视频工作流参考（Work-Fisher 开源，5 段拼接 20 秒，含 WanImageToVideoSVIPro 段间 latent 传递） |
| `${COMFYUI_PATH}/user/default/workflows/v12_flux2_双图修正.json` | v12 Flux2 双图修正工作流（ReferenceLatent 单 B 图注入 + img2img 模式，已验证） |
| `${COMFYUI_PATH}/user/default/workflows/v12_svi_pro_段1.json` | v12 SVI Pro 段1工作流（KSamplerAdvanced 10 值 widgets_values，已验证） |
| `${COMFYUI_PATH}/user/default/workflows/v12f_合并_20s.json` | v12 5段合并工作流（ImageBatchExtendWithOverlap + VHS_VideoCombine） |

---

*最后更新：2026-07-26（v12 完整迭代经验：Flux2双图修正优化、SVI Pro段间连贯性、KSamplerAdvanced参数对齐、文件操作最佳实践）*

---

## 21. 参数梯度分析与场景化选择指南（2026-07-26）

> **核心原则**：任何参数都不存在"万能最优值"。所有参数必须根据模型系列、LoRA类型、硬件档位、任务需求四个维度动态选择。以下为各关键参数的梯度分层分析和场景化推荐。

### 21.1 采样步数（steps）梯度分析

**物理意义**：控制去噪过程的迭代次数。步数越多，模型有更多机会修正细节，但耗时线性增长。

**梯度分层**：

| 梯度区间 | 步数值 | 适用场景 | 决策依据 |
|---------|--------|---------|---------|
| 极低步数 | 4-6 | lightx2v加速LoRA + L1入门级硬件(8-12GB) | 蒸馏模型设计步数，速度快但细节受限 |
| 低步数 | 6-8 | lightx2v加速LoRA + L2/L3硬件(12-24GB) | 蒸馏模型最优区间，速度与质量平衡 |
| 中步数 | 8-10 | lightx2v + L4专业级硬件(≥24GB) | 蒸馏模型上限，边际收益递减 |
| 标准步数 | 14-20 | 无加速LoRA + 简单动作视频 | 原生模型标准配置 |
| 高步数 | 20-30 | 无加速LoRA + 复杂场景/画质优先 | 细节丰富场景，画质LoRA需此区间 |
| 极进步数 | 30-40 | Flux2 img2img修正 / 极限画质 | Flux2修正推荐28-32，超过40边际收益极低 |

**场景化建议**：
- **场景A（速度优先）**：lightx2v加速LoRA，steps=6-8，适合快速验证和迭代
- **场景B（质量优先）**：画质LoRA替代加速LoRA，steps=20-30，适合最终交付
- **场景C（Flux2修正）**：steps=28-32，需要足够步数恢复被SVI Pro丢失的细节
- **场景D（OOM降级）**：优先降分辨率保步数，而非降步数（步数过低导致质量崩溃）

**关键禁忌**：
- 有lightx2v时4步可工作且质量足够（C8任务验证：HIGH:2+LOW:2 单段短视频）；分段长视频建议 6-8 步
- 无加速LoRA时低于14步画面严重模糊（Wan2.2特性）
- 超过30步收益递减，不建议单纯堆步数

### 21.2 CFG（引导系数）梯度分析

**物理意义**：控制文本提示词对生成过程的引导强度。CFG越高，生成结果越遵从提示词但可能过度锐化/饱和；CFG越低，模型自由度越高但可能偏离提示词。

**梯度分层（按LoRA类型）**：

| LoRA类型 | CFG策略 | 值 | 原理 |
|---------|--------|-----|------|
| 加速蒸馏LoRA(lightx2v) | 动态调度 | [2,1,1,1,1,1] | 第一步CFG=2建立结构锚定，后续CFG=1让蒸馏模型自由发挥 |
| 加速蒸馏LoRA(lightx2v) | 动态调度(保守) | [2.5,1,1,1,1,1] | 提示词跟随度不足时略微提高第一步 |
| 画质增强LoRA | 固定 | 4.0-5.0 | 画质LoRA已内置引导逻辑，CFG不宜过高 |
| 无LoRA(原生Wan2.2) | 固定 | 5.0-7.0 | 标准原生模型配置 |
| Flux2 img2img | 固定 | 3.0-3.5 | img2img模式降低CFG避免色彩过度饱和 |
| Flux2 txt2img | 固定 | 1.0 | Distill模型特性，cfg=1 |

**场景化建议**：
- **场景A（lightx2v + 标准动作）**：动态调度[2,1,1,1,1,1]，第一步CFG=2
- **场景B（lightx2v + 提示词跟随度不足）**：动态调度[2.5,1,1,1,1,1]或[3,1,1,1,1,1]
- **场景C（画质LoRA）**：固定CFG=4.0-5.0，过高会导致过饱和
- **场景D（无LoRA原生）**：固定CFG=6.0，这是原生Wan2.2的平衡点

**关键禁忌**：
- lightx2v下静态CFG=5.0会导致引导过强或不足（V18已验证）
- 画质LoRA下CFG>7.0会导致画面过度锐化/饱和
- Flux2 img2img下CFG>5.0会导致色彩严重偏离（v12验证）

### 21.3 denoise（去噪强度）梯度分析

**物理意义**（img2img模式）：控制添加噪声的比例。denoise=1.0表示完全重新生成（纯文生图），denoise=0表示完全保留原图。

**梯度分层**：

| 梯度区间 | denoise值 | 适用场景 | 效果 |
|---------|----------|---------|------|
| 极低修正 | 0.2-0.3 | 轻微色调调整 | 几乎完全保留原图，修正力度弱 |
| 低修正 | 0.35-0.45 | 降噪+色调统一 | 保留70%原图结构，色调小幅调整 |
| 平衡修正 | 0.5 | 去躁+细节恢复（推荐） | 保留50%原图，有足够空间恢复细节 |
| 高修正 | 0.6-0.7 | 明显瑕疵修复 | 保留30%原图，可能偏离原始构图 |
| 完全重生成 | 0.8-1.0 | 文生图模式 | 几乎不保留原图，不适用于修正场景 |

**场景化建议（Flux2修正专用）**：
- **场景A（SVI Pro输出质量较好）**：denoise=0.4，轻量去躁
- **场景B（SVI Pro输出有噪点但结构完整）**：denoise=0.5，平衡修正（v12验证推荐）
- **场景C（SVI Pro输出严重模糊）**：denoise=0.55-0.6，但需接受构图可能偏移

**关键禁忌**：
- denoise<0.3时模型可操作空间不足，修正无效
- denoise>0.7时接近文生图，背景和构图大幅偏离
- Flux2修正推荐区间0.4-0.55（v12验证）

### 21.4 LoRA强度（strength）梯度分析

**物理意义**：控制LoRA对基础模型的影响程度。strength=1.0表示完全应用LoRA效果，strength=0表示不使用LoRA。

**梯度分层（按LoRA类型）**：

| LoRA类型 | 梯度区间 | strength | 效果 |
|---------|---------|---------|------|
| 加速蒸馏(lightx2v) | 官方推荐 | 1.0 | 标准蒸馏效果，8步达到20-30步质量 |
| 加速蒸馏(lightx2v) | 过高 | >2.0 | 破坏MoE去噪曲线，细节丢失（C5 v13验证：strength=3.0导致发型/皮肤/衣服质感丢失） |
| 加速蒸馏(lightx2v) | 过低 | <0.5 | 蒸馏不足，仍需较多步数 |
| 画质增强(SVI_v2_PRO) | 标准 | 1.0 | 官方推荐值 |
| 色调控制(ColorTone) | 低 | 0.2-0.4 | 轻微暖色修正，防止偏黄（v12验证：0.4） |
| 色调控制(ColorTone) | 中 | 0.4-0.6 | 显著暖色调整 |
| 色调控制(ColorTone) | 高 | >0.6 | 明显偏色风险（v12验证） |
| 皮肤质感(Skin) | 推荐 | 0.6 | 增强皮肤质感但不失真（v12验证） |
| 细节增强(Detail) | 推荐 | 1.0 | 最大化细节增强（v12验证） |

**场景化建议**：
- **场景A（加速优先+Wan2.2）**：lightx2v strength=1.0，8步高质量
- **场景B（画质优先+Wan2.2）**：SVI_v2_PRO strength=1.0，20-30步
- **场景C（Flux2色调修正）**：ColorTone=0.2-0.4，Skin=0.6，Detail=1.0

**关键禁忌**：
- 加速LoRA strength过高(>2)会严重破坏细节（C5验证）
- 色调LoRA strength>0.6会导致明显偏色（v12验证）
- 不同LoRA类型的strength含义不同，不可跨类型参考

### 21.5 分辨率梯度分析

**物理意义**：直接影响生成画面细节量和显存占用。分辨率翻倍，FFN激活值约翻4倍。

**梯度分层（按硬件档位 + 任务类型）**：

| 档位 | VRAM | 视频推荐分辨率 | 图片推荐分辨率 | 约束 |
|------|------|-------------|-------------|------|
| L1入门级 | 8-12GB | 352×640 | 512×768(SD1.5) | 视频必须16整除 |
| L2标准级 | 12-16GB | 480×640 | 960×720(Flux2) | 垂直9:16竖屏优先 |
| L3高性能 | 16-24GB | 480×848 | 1200×900(Flux2) | RTX 3080 20GB实测可行 |
| L4专业级 | ≥24GB | 576×1024 | 2048+(Flux2原生) | 14B fp8约14GB，有余量 |

**场景化建议**：
- **场景A（竖屏视频+20GB）**：480×848（L3档），9:16比例
- **场景B（OOM降级）**：480×848→352×640（降分辨率保所有其他参数）
- **场景C（Flux2图片+20GB）**：1200×900到1920×1440均可
- **场景D（SD1.5图片）**：严格512×512或512×768，超出训练分辨率质量崩溃

**关键禁忌**：
- 视频分辨率必须能被16整除（360不是16倍数，用352或368）
- 图片分辨率应匹配模型训练分辨率（SD1.5=512, Flux2=2048+原生）
- 降分辨率是OOM时的首选（保步数和帧数），可后续X2放大补偿

### 21.6 帧数（num_frames）梯度分析

**物理意义**：控制视频时长。Wan2.2训练原生长度约81帧（3.4秒@24fps），超过训练长度触发语义重复。

**梯度分层**：

| 梯度区间 | 帧数 | 时长@24fps | 适用场景 | 风险 |
|---------|------|-----------|---------|------|
| 短视频 | 41 | ~1.7秒 | 单动作，L1/L2硬件 | 动作表达受限 |
| 标准视频 | 81 | ~3.4秒 | 单段标准，训练原生长度 | 无风险 |
| 中视频 | 121 | ~5秒 | 单段较长，L3/L4硬件 | 轻微语义重复风险 |
| 长视频(不推荐) | 241 | ~10秒 | L4专业级 | 明确语义重复（C5 v3-v8验证） |
| 超长视频(分段) | 3×81=243 | ~10秒 | 所有硬件 | 分段生成+拼接，无重复风险 |

**场景化建议**：
- **场景A（3秒短视频）**：单段81帧，最安全
- **场景B（5秒中视频+L4）**：单段121帧，需接受轻微重复风险
- **场景C（10秒长视频+任意硬件）**：3段×81帧拼接，段间末帧继承
- **场景D（20秒超长视频）**：5段×81帧拼接+Flux2修正图传递

**关键禁忌**：
- 绝对禁止单次241帧（C5验证：角色执行两遍动作）
- RIFLEX只防数学循环，不防语义重复
- 长视频唯一正确方案：分段生成+拼接

### 21.7 shift（调度器偏移）梯度分析

**物理意义**：控制Flow Matching调度器的时间步分布。shift越高，更多步数分配给高噪声阶段（主结构），低噪声阶段步数减少。

**梯度分层**：

| shift值 | 适用场景 | 效果 |
|---------|---------|------|
| 3.0-5.0 | 旧版/通用设置 | 已被V18/V19验证推翻，高曝光+动作不自然 |
| 6.0-7.0 | 保守值 | 较少步数分配给主结构 |
| 8.0 | Wan2.2官方源工作流值 | 推荐，V18/V19验证通过 |
| 9.0-12.0 | 高shift实验值 | 更多步数给主结构，细节可能不足 |

**关键禁忌**：
- Wan2.2的shift=8.0来自官方源工作流，不可随意修改
- 其他模型系列（HunyuanVideo/CogVideoX）需查对应官方文档
- shift值与scheduler强绑定，不可跨scheduler套用

### 21.8 scheduler（调度器）场景化选择

| scheduler | 特性 | Wan2.2验证 | 适用场景 |
|-----------|------|-----------|---------|
| dpm++_sde | 随机性，产生自然动作变化 | 验证通过（V18/V19） | 动作丰富的视频生成 |
| unipc | 确定性，结果可复现 | 验证失败（动作卡住旋转） | 静态/微动作，需要可复现 |
| euler | 简单稳定 | Flux2图片推荐 | Flux2 img2img/txt2img |
| euler_ancestral | 带随机性的euler | - | SD1.5/SDXL图片生成 |
| simple | 标准调度 | Flux2推荐 | Flux2配合euler使用 |

### 21.9 blocks_to_swap（显存换出块数）梯度分析

**物理意义**：控制多少模型 Block 被卸载到 CPU 内存。值越大，GPU显存占用越低，但CPU↔GPU数据传输增加导致采样变慢。

**梯度分层（按硬件档位 + 模型类型）**：

| 档位 | VRAM | 单模型 blocks_to_swap | 双模型(串行) blocks_to_swap | 速度影响 |
|------|------|---------------------|--------------------------|---------|
| L4专业级 | ≥24GB | 20-24 | 不需要(同时加载2个fp8模型) | 零影响 |
| L3高性能 | 16-24GB | 20-24（C8验证） | 同一模型文件被缓存复用 | 约减慢10-15% |
| L2标准级 | 12-16GB | 38-40 | 需卸载前一个模型才能加载下一个 | 约减慢20-30% |
| L1入门级 | 8-12GB | 40-42 | 必须卸载+换出大量block | 约减慢40-50% |

**场景化建议**：
- **场景A（单段生成+L3档）**：blocks_to_swap=20，专用显存利用率 75%+（C8验证，非36）
- **场景B（OOM降级）**：递增blocks_to_swap 2-4个单位，不降分辨率/步数（优先保质量）
- **场景C（SVI Pro分段+L3档）**：段间需切换HIGH/LOW模型，L3档HIGH+LOW使用同一文件被缓存，blocks_to_swap=20-24可行
- **场景D（双模型同时加载+L4档）**：blocks_to_swap=0（两个fp8模型各约7-8GB，24GB足够）

**关键禁忌**：
- blocks_to_swap 值过高会导致专用显存闲置，转而使用共享内存（C8验证：36 导致专用显存仅用 40%）
- 专用显存未被充分利用前不使用共享内存（硬约束）
- 递增策略：每次+2-4，不跳跃式增加到最大值
- SVI Pro HIGH和LOW使用不同模型文件时（如现实人物配置），L3档需增加blocks_to_swap或改为顺序加载

### 21.10 base_precision（基础精度）梯度分析

**物理意义**：控制模型推理的数据精度。bf16（Brain Float16）保持7位有效数字适合推理，fp16_fast更快但精度略低，fp8更小更快但有量化损失。

**梯度分层**：

| 精度 | 模型大小 | 显存占用 | 相对速度 | 适用硬件 | 质量影响 |
|------|---------|---------|---------|---------|---------|
| fp16_fast | 14GB | ~14GB | 1.5×基准 | L4(≥24GB) | 最佳质量 |
| bf16 | 14GB | ~14GB | 1.0×基准 | L1/L2/L3(8-24GB) | 标准质量，已验证稳定 |
| fp8_e4m3fn | 7-8GB | ~8GB | 1.8×基准 | L3/L4(≥16GB) | 轻微质量损失，大多数场景无感知 |
| fp8_scaled | 7-8GB | ~8GB | 1.8×基准 | L3/L4(≥16GB) | scaled版本对某些模型更友好 |

**场景化建议**：
- **场景A（追求质量+L4档）**：fp16_fast，所有其他参数可设上限
- **场景B（标准+L2/L3档）**：bf16，已验证稳定，兼容性最好
- **场景C（加速+L3/L4档+lightx2v）**：fp8_e4m3fn，与lightx2v蒸馏LoRA配合效果更好
- **场景D（OOM降级+L3档）**：bf16→fp8_e4m3fn，可释放约6GB显存

**关键禁忌**：
- fp16_fast在L1/L2档(8-16GB)可能导致OOM
- bf16比fp16_fast慢约1.5倍（实测验证）
- fp8_scaled格式需要模型本身支持，不兼容会导致加载失败
- 降精度不影响参数梯度，所有其他参数策略保持不变

### 21.11 rope_function（RoPE函数）场景化选择

**物理意义**：控制位置编码计算方式。Wan2.2使用RoPE(Rotary Position Embedding)编码帧位置。

| rope_function | 显存占用 | 适用分辨率 | 说明 |
|--------------|---------|-----------|------|
| comfy_chunked | 低（分块计算） | ≥480×848 | **推荐**，分块计算RoPE降低显存峰值 |
| default | 高（全量计算） | <480×848 | 低分辨率可用，高清必须切换到chunked |

**关键禁忌**：
- 480×848及以上分辨率不使用comfy_chunked会显著增加OOM风险
- 两种模式生成的视频质量无差异，仅影响显存

### 21.12 noise_aug_strength（噪声增强强度）梯度分析

**物理意义**：向首帧条件注入微量噪声，增强模型对条件变化的鲁棒性。值为0时完全锁定首帧。

| 值 | 效果 | 适用场景 |
|----|------|---------|
| 0 | 完全锁定首帧，无噪声注入 | 静态场景，不需要运动变化 |
| 0.05 | 微量噪声，轻微运动自由度 | 微动作视频 |
| **0.1** | 标准值 | 所有标准视频生成（V18/V19验证） |
| 0.15-0.2 | 更多运动自由度 | 大幅动作场景 |
| >0.2 | 可能过度扰动 | 不推荐，首帧锚定被削弱 |

**关键禁忌**：
- 设为0会导致亮度锚定缺失（V18/V19验证：禁止为0）
- I2V（图生视频）必须 >0，T2V（文生视频）可为0

### 21.13 split_step（双阶段分割步）梯度分析

**物理意义**：控制HIGH/LOW双阶段的分割点。split_step=N表示前N步由HIGH模型处理（主结构），剩余步数由LOW模型处理（细节细化）。

**梯度分层（按总步数）**：

| 总步数 | split_step 推荐 | HIGH处理步数 | LOW处理步数 | 原理 |
|--------|---------------|------------|------------|------|
| 6(lightx2v) | 3 | 3 | 3 | 均衡分配，各一半 |
| 8(lightx2v) | 4 | 4 | 4 | 均衡分配 |
| 20(画质LoRA) | 10 | 10 | 10 | 均衡分配 |
| 30(Flux2) | N/A | N/A | N/A | Flux2无HIGH/LOW分割 |

**场景化建议**：
- **场景A（lightx2v 8步+L3档）**：split_step=4，前4步主结构后4步细化
- **场景B（画质LoRA 20步+L3档）**：split_step=10，各10步
- **场景C（快速验证 6步+L2档）**：split_step=3，各3步

**关键禁忌**：
- split_step应约为总步数的一半（均衡策略）
- 不可设split_step=0（跳过高噪声阶段，缺失主结构）
- 不可设split_step=总步数（跳过细化阶段，导致模糊，C6验证）

### 21.14 综合场景参数矩阵

**使用方式**：根据任务类型和硬件档位，从下表查找起始参数，然后根据实际效果微调。

| 场景 | 型号/LoRA | VRAM档位 | steps | CFG | shift | scheduler | 帧数 | 分辨率 |
|------|----------|---------|-------|-----|-------|-----------|------|--------|
| 快速验证 | Wan2.2+lightx2v | L2(12-16G) | 4 | [2,1,1,1] | 8.0 | dpm++_sde | 41 | 352×640 |
| 标准生成 | Wan2.2+lightx2v | L3(16-24G) | 4-8 | [2,1,1,1] | 8.0 | dpm++_sde | 81 | 480×848 |
| 高质量 | Wan2.2+lightx2v | L4(≥24G) | 8-10 | [2,1,1,1,1,1,1,1,1,1] | 8.0 | dpm++_sde | 121 | 576×1024 |
| 画质优先 | Wan2.2+画质LoRA | L3(16-24G) | 20 | 5.0 | 8.0 | dpm++_sde | 81 | 480×848 |
| Flux2修正 | F2K-9b+3LoRA | L3(16-24G) | 30 | 3.5 | - | euler/simple | 1帧 | 480×848 |
| SVI Pro分段 | Wan2.2 SVI | L3(16-24G) | 6(2+4) | 1.0 | - | euler/simple | 81×5段 | 480×848 |

**重要**：上表为参考起始点，不可作为模板直接复制。执行前必须：
1. 通过 `/object_info` 确认模型/LoRA实际可用名称
2. 检查当前VRAM空闲量，按实际余量选择档位
3. 第一批生成后根据效果微调（模糊→加步数，偏色→调LoRA强度，语义重复→降帧数分段）

> **C8 任务验证更新**：L3 档单段短视频使用 steps=4（HIGH:2+LOW:2）质量足够，blocks_to_swap=20（非36）。详见第 23 章 C8 任务完整复盘。

### 21.15 CLIP 图像编码强度（多图场景）梯度分析

**物理意义**：在多图视频生成中，CLIP Vision 编码器将参考图像编码为条件向量。每张参考图的 `strength` 控制其对生成的影响力权重。`combine_embeds` 控制多图向量的融合方式。

**使用场景**：仅当工作流包含多张参考图（如 C5 任务的 `1.png` + 末帧）时使用。单图视频不需要此参数。

**梯度分层（strength 值）**：

| 梯度区间 | strength值 | 适用场景 | 效果 |
|---------|-----------|---------|------|
| 低约束 | 0.3-0.5 | 末帧场景参考（弱化干扰） | 模型参考该图但不被其主导（C5验证：末帧=0.5） |
| 标准约束 | 1.0 | 单图参考 / 等权重多图 | 标准参考强度 |
| 强约束 | 1.2-1.5 | 锁定角色外貌的主参考图 | 强约束角色外观不变（C5验证：1.png=1.5） |
| 过强约束 | >2.0 | 不推荐 | 过度锁定导致动作僵硬、场景不自然 |

**combine_embeds 模式选择**：

| 模式 | 适用场景 | 说明 |
|------|---------|------|
| concat | 多图参考（推荐） | 保留每张图的独立特征向量，不混合稀释（C5验证） |
| average | 单图或极相似多图 | 取平均会稀释每张图的特征，不推荐用于异构多图 |
| normed_concat | 需要归一化时 | 对concat结果做L2归一化 |

**场景化建议**：
- **场景A（单图视频）**：strength=1.0, combine_embeds=concat，单图无权重选择问题
- **场景B（双图视频+角色主图+场景辅助）**：主图strength=1.5 + 辅助图strength=0.5, combine_embeds=concat
- **场景C（双图权重相等）**：两张图strength都=1.0, combine_embeds=concat
- **场景D（不需要辅助图）**：只传一张图的CLIP编码，不给辅助图

**关键禁忌**：
- concat 模式下总 strength 无上限（各图特征独立），但单张图 strength>2.0 会过度锁定
- average 模式下 strength 过高会淹没问题特定特征
- 多段分段生成时，末帧 strength 应始终低于主角参考图（C5验证：0.5 vs 1.5）

---

## 22. 多图/长视频节点详解与场景化分析（2026-07-26）

> **核心原则**：同一节点在短视频（≤5秒）和长视频（>5秒/分段拼接）场景下的用法可能完全不同。本章按节点逐一分析其在短/长视频、多图/单图场景下的使用差异和梯度选择，基于 C5（多图10秒）和 C7（SVI Pro 20秒）完整迭代验证。

### 22.1 WanVideoClipVisionEncode（CLIP 图像编码器）

**功能**：将参考图像通过 CLIP Vision 模型编码为条件向量，注入到视频扩散模型的 cross-attention 层，控制生成内容的外观和场景。

**所属系列**：Wan2.2（ComfyUI-WanVideoWrapper）

**梯度分析**：

| 参数 | 短视频（≤5秒） | 长视频（>5秒/分段） | 多图视频（C5模式） | 单图视频 |
|------|-------------|-----------------|-----------------|---------|
| clip_strength | 1.0（默认） | 1.0（默认） | 主图1.5 + 辅助0.5 | 1.0 |
| combine_embeds | concat | concat | concat | concat |
| 是否必需 | 可选 | 可选 | **必需**（否则无参考图控制） | 推荐 |

**短视频 vs 长视频差异**：
- **短视频**：单图参考通常足够，不需要多图权重平衡
- **长视频（分段）**：每段都需要 CLIP 参考。段1只用主参考图，段2-5同时参考主图（锁定角色）+ 末帧（场景延续），通过权重倾斜（1.5/0.5）避免末帧场景特征侵蚀角色外貌

**容易出问题的场景**：
- **多段拼接时末帧 strength 过高**：C5 v12 段间角色外貌变化（发型、脸部脱离参考），根因是末帧 strength=1.0 与主图等权，末帧的场景特征干扰了角色外貌。修复：主图 strength=1.5，末帧=0.5
- **单图场景传了无意义的辅助图**：多一张无关参考图会稀释主图特征，降低生成质量

### 22.2 WanVideoImageToVideoEncode（首尾帧编码器）

**功能**：为视频生成提供 start_image（首帧）和可选的 end_image（尾帧参考）。这是 I2V（图生视频）和首尾帧模式的核心入口节点。

**所属系列**：Wan2.2（ComfyUI-WanVideoWrapper）

**梯度分析**：

| 参数 | 标准I2V | FLF2V模式 | 首尾帧(I2V) | 纯文生视频(T2V) |
|------|---------|----------|-----------|--------------|
| start_image | 必需 | 必需 | 必需 | 不需要 |
| end_image | 可选（弱参考） | **强制末帧锚定** | 必需（弱参考） | 不需要 |
| fun_or_fl2v_model | **false** | **true** | false | N/A |
| clip_vision | 必需 | 必需 | 必需 | N/A |
| noise_aug_strength | 0.1 | 0.1 | 0.1 | 0 |
| 适用模型 | Wan2.2-I2V-A14B | FLF2V专用模型 | Wan2.2-I2V-A14B | Wan2.2-T2V |

**FLF2V vs 标准I2V 关键区别**：
- **标准 I2V（fun_or_fl2v_model=false）**：end_image 仅作为弱参考，不强制末帧 = end_image。适合"角色走向某场景"类的叙事视频（C5验证）
- **FLF2V（fun_or_fl2v_model=true）**：end_image 强制末帧锚定（等于该图），适合"精确首尾帧过渡"（如 A 图变形到 B 图）
- **混用后果**：标准 I2V 模型启用 FLF2V 模式会破坏生成质量（模型未训练此行为）

**短视频 vs 长视频差异**：
- **短视频**：单次调用，start_image 为原始参考图
- **长视频（分段）**：段1 start_image 为原始参考图；段2-5 start_image 为前段修正图（C7 v12 架构）。这是段间画面连贯的核心

**容易出问题的场景**：
- **SVI Pro 分段模式下不需要此节点**：SVI Pro 有自己的 start_image 处理逻辑（通过 anchor_samples），使用 SVI Pro 时此节点不参与
- **noise_aug_strength=0 的陷阱**：设为0会导致首帧亮度锚定缺失（V18/V19验证），I2V模式必须 >0

### 22.3 WanImageToVideoSVIPro（SVI Pro 分段核心节点）

**功能**：SVI Pro 长视频工作流的段间连贯核心。通过 anchor_samples（首帧锚定）+ prev_samples（前段 latent 传递）+ motion_latent_count（运动延续控制）三个参数实现段间无缝衔接。

**所属插件**：comfyui-kjnodes

**核心参数梯度分析**：

#### 22.3.1 anchor_samples 梯度分析

**物理意义**：所有段共用的首帧 VAE 编码 latent，锚定角色外貌、场景构图和色调。

| 值 | 适用场景 | 效果 |
|----|---------|------|
| 1帧（原图 VAEEncode） | 所有 SVI Pro 场景（推荐） | 所有段锚定到同一个角色外观，保持一致性 |
| 不设置 | 不推荐 | 段间角色外貌漂移 |

**与 prev_samples 的配合**：anchor_samples 负责"是什么角色/场景"，prev_samples 负责"上一段结束时的状态"，两者不冲突。

#### 22.3.2 motion_latent_count 梯度分析（核心参数）

**物理意义**：控制当前段是否携带上一段的运动状态 latent。值=0 表示不加运动延续（从静止开始），值=1 表示携带1帧上一段末尾的运动 latent。

**梯度分层**：

| motion_latent_count | 适用段 | 效果 | 风险 |
|-------------------|--------|------|------|
| **0** | 段1（强制） + 推荐段2-5 | 每段从静止/修正图开始，无运动状态传递 | 段间动作可能有微停顿 |
| **1** | 段2-5（可选） | 携带上一段末尾的运动状态，动作更连贯 | **高概率导致暗→亮渐变**（C7 v12验证） |
| >1 | 不推荐 | 多帧运动 latent 叠加，增加不稳定性 | 色调漂移放大 |

**关键教训（C7 v12 2026-07-25）**：

motion_latent_count=1 时，anchor_latent（1帧原图）和 motion_latent（1帧prev）被拼接成 2 帧条件 latent。两种 VAE 编码的分布差异导致每段亮度逐渐增加（暗→亮渐变）。修复方案：段2-5 全部 motion_latent_count=0，用 Flux2 修正图作为 start_image 传递连贯性。

**场景化建议**：
- **场景A（Flux2修正桥接 + SVI Pro）**：motion_latent_count=0（全段），通过修正图传递画面状态，避免 latent 拼接的色调漂移（C7 v12 验证）
- **场景B（纯 SVI Pro 无外部修正）**：段1 motion_latent_count=0，段2-5 motion_latent_count=1，接受轻微的亮度变化（参考 SVI Pro 官方源工作流设计）
- **场景C（追求绝对色调一致）**：全段 motion_latent_count=0 + 每段前 Flux2 修正

#### 22.3.3 prev_samples 传递策略

**物理意义**：将上一段 SVI Pro 生成的末尾 latent 传递给下一段，提供时序上的连贯信息。

**梯度分层**：

| prev_samples 来源 | 传递精度 | 累积误差 | 推荐场景 |
|------------------|---------|---------|---------|
| 上一段 LOW 阶段输出 latent（原始设计） | 高 | 5段累积 | SVI Pro 官方设计 |
| 上一段最后一帧 VAEEncode（C7改进） | 中 | 低（每段独立编码） | 修正后传递，避免 latent 分布漂移 |
| 不传递（null） | 无 | 无 | 每段独立，段间无关联 |

**短视频 vs 长视频差异**：
- **短视频（≤5秒/单段）**：prev_samples 为 null，不需要传递
- **长视频（5-20秒/多段）**：
  - SVI Pro 方案：prev_samples 传上一段 LOW latent（latent 级别传递）
  - C5 方案：prev_samples 不适用，改用末帧图像重新编码为 start_image

**容易出问题的场景**：
- **prev_samples 直接传整个 latent（非最后一帧）**：会携带完整的段时序信息而非末帧状态，导致后段画面融合了前段的中间帧特征（C7 实测：后段画面越来越模糊/磨皮）
- **修复方式**：用 ImageFromBatch(idx=-1) 提取最后1帧 → VAEEncode作为 prev_samples

### 22.4 ImageBatchExtendWithOverlap（图像重叠融合）

**功能**：将两段视频的图像批次以重叠区域线性混合的方式拼接，消除段间硬切。

**所属插件**：comfyui-kjnodes

**梯度分析**：

| 参数 | 梯度区间 | 效果 | 适用场景 |
|------|---------|------|---------|
| **overlap（重叠帧数）** | 3 | 极短过渡 | 帧率低(<16fps)、段间差异极小的场景 |
| | **5（推荐）** | 平衡过渡，消除硬切感 | 标准场景（SVI Pro官方 + C7验证） |
| | 7 | 更长过渡 | 段间动作差异大，需要更长融合区 |
| | 10 | 最长过渡 | 段间风格差异明显，但末尾质量损失更多帧 |
| **overlap_mode** | **linear_blend** | 线性混合，过渡均匀 | 所有标准场景（唯一推荐） |
| | none | 无混合，直接拼接 | 不推荐（硬切） |
| **overlap_side** | **source** | 在源末尾重叠 | 标准链式拼接（段1+段2+段3...） |
| | destination | 在目标开头重叠 | 不常用 |

**短视频 vs 长视频差异**：
- **短视频（≤5秒/单段）**：不需要此节点
- **长视频（5-20秒/3-5段）**：链式调用4次（5段需4次融合）

**链式调用模式**（C7 验证）：
```
段1 decoded ──→ ImageBatchExtendWithOverlap(source, 段2 decoded, overlap=5)
              ↓ extended_images
            ImageBatchExtendWithOverlap(source, 段3 decoded, overlap=5)
              ↓ extended_images
            ImageBatchExtendWithOverlap(source, 段4 decoded, overlap=5)
              ↓ extended_images
            ImageBatchExtendWithOverlap(source, 段5 decoded, overlap=5)
              ↓ → VHS_VideoCombine（最终输出）
```

**容易出问题的场景**：
- **overlap 过大（>10）**：浪费段末尾的有效帧，5段×10帧=50帧被"吃掉"，20秒视频变18秒
- **overlap 过小（<3）**：无法消除硬切，段间可见跳跃
- **混合模式用 none**：等于硬拼接，失去使用此节点的意义

### 22.5 KSamplerAdvanced（高级采样器）

**功能**：ComfyUI 核心采样器，支持分步采样（start_at_step/end_at_step），是 SVI Pro 双阶段（HIGH→LOW）串联的关键节点。

**所属**：comfy-core

**参数陷阱（最重要）**：

#### 22.5.1 widgets_values 10值对齐陷阱

**问题**：API 格式工作流通过 key 映射参数（无顺序概念），但 UI 格式工作流通过 `widgets_values` 的 position 顺序映射参数。KSamplerAdvanced 的前端渲染有 **10 个 widget**（含隐式 widget），但常见构建只传 9 个值。

| 位置 | widget名 | 是否显式 | 示例值 |
|------|---------|---------|--------|
| 0 | model | 显式 | [节点ID, output_index] |
| 1 | add_noise | 显式 | "enable" 或 "disable" |
| 2 | noise_seed | 显式 | 123456 |
| 3 | **control_after_generate** | **隐式（UI独有）** | **"fixed"** / "increment" / "decrement" / "randomize" |
| 4 | steps | 显式 | 20 |
| 5 | start_at_step | 显式 | 0 |
| 6 | end_at_step | 显式 | 10 |
| 7 | return_with_leftover_noise | 显式 | "enable" |
| 8 | cfg | 显式 | 5.0 |
| 9 | sampler_name | 显式 | "euler" |

**错误症状**：
- API 执行正常但 Web 端报错 → 参数缺了第3位 control_after_generate
- "Value not in list" 错误 → 参数类型错位（如把 "enable" 填到了 control_after_generate 位置）
- "expected float but got str" 错误 → 参数顺序完全错位

**修复**：始终确保 `widgets_values` 包含 `[model_ref, add_noise, seed, "fixed", steps, start, end, return_noise, cfg, sampler, scheduler]` 共 11 个值（部分版本scheduler也是独立widget）。

**短视频 vs 长视频差异**：
- **短视频（单段）**：2个 KSamplerAdvanced（HIGH+LOW 各1）
- **长视频（SVI Pro 5段）**：10个 KSamplerAdvanced（5段×2阶段）
- **Flux2 修正**：1个 KSamplerAdvanced（非双阶段）

### 22.6 ReferenceLatent（Flux2 参考潜空间注入）

**功能**：将参考图像的 VAE 编码 latent 注入 Flux2 的 CFGGuider，提供画面细节参考。

**所属**：comfy-core（Flux2 专用）

**梯度分析**：

| 注入策略 | 效果 | 适用场景 |
|---------|------|---------|
| **单图注入（B图）** ✅ | 模型专注从清晰参考图提取细节 | 标准修正场景（C7 v12验证） |
| 双图注入（A+B） ❌ | 模型取平均，细节被稀释 | 不推荐 |

**关键教训（C7 v12 2026-07-25）**：

ReferenceLatent 同时注入 A 图（SVI Pro 输出，模糊）和 B 图（原始参考图，清晰）时，Flux2 对两个 ReferenceLatent 做平均化处理，导致细节被稀释——皮肤质感、衣服褶皱、花纹全部消失。

**正确架构**：
```
正条件 → ReferenceLatent(B图VAE编码 only) → CFGGuider
负条件 → ReferenceLatent(B图VAE编码 only) → CFGGuider
```

**画面构图靠什么**：靠 img2img 模式的 VAEEncode(A图) 提供的 latent_image（作为采样起点），不需要 A 图 ReferenceLatent。

**短视频 vs 长视频差异**：
- **短视频**：修正1次（单段输出→Flux2修正→最终视频）
- **长视频（分段+Flux2桥接）**：修正5次（每段SVI Pro输出→Flux2修正→作为下段start_image），这是 C7 v12 的核心创新

### 22.7 LoraLoaderModelOnly（LoRA 加载器）

**功能**：加载 LoRA 权重并应用到基础模型。

**所属**：comfy-core

**多 LoRA 叠加策略**：

在 Flux2 修正工作流中，需要叠加 3 个 LoRA（ColorTone + Skin + Detail），通过串联实现：

```
UNETLoader → LoraLoaderModelOnly(ColorTone 0.4) → LoraLoaderModelOnly(Skin 0.6) → LoraLoaderModelOnly(Detail 1.0) → CFGGuider
```

**叠加顺序注意**：
- 色调 LoRA 通常放最前面（影响全局色彩分布）
- 皮肤/细节 LoRA 放后面（叠加在色调调整后的结果上）
- 不同顺序效果有差异，但当前验证顺序可用

**SVI Pro LoRA 加载**：
- HIGH 链路：LoraLoaderModelOnly(SVI_HIGH_lora, strength=1.0)
- LOW 链路：LoraLoaderModelOnly(SVI_LOW_lora, strength=1.0)（现实人物配置）

**容易出问题的场景**：
- 在 WanVideoWrapper 原生节点流程中加载 LoRA：不兼容！WanVideoModelLoader 没有 LoraLoader 输入。SVI Pro 必须用 UNETLoader + LoraLoaderModelOnly
- 用错 LoRA 类型：加速蒸馏 LoRA（lightx2v）和画质 LoRA（SVI_v2_PRO）不可互换

### 22.8 VHS_VideoCombine（视频编码输出）

**功能**：将图像帧序列合并编码为视频文件。

**所属**：ComfyUI-VideoHelperSuite

**梯度分析**：

| 参数 | 入门级 | 标准级 | 高质量级 |
|------|--------|--------|---------|
| crf | 19-23（快速预览） | 14-17（标准输出） | **14**（项目硬约束） |
| pix_fmt | yuv420p | yuv420p10le | **yuv420p10le**（10bit） |
| frame_rate | 16（省帧） | 24（标准） | 24（项目硬约束） |
| format | video/h264-mp4 | video/h264-mp4 | video/h264-mp4 |

**关键约束**：
- crf=14 是项目硬约束（高质量编码）
- pix_fmt=yuv420p10le 是项目硬约束（10bit色彩深度）
- frame_rate=24 是项目标准

**短视频 vs 长视频差异**：
- 无本质差异，参数完全一致
- SVI Pro 工作流中每个分段可能有独立的 VHS_VideoCombine（用于预览），最终只有一个用于合并输出

### 22.9 长视频 vs 短视频方案决策矩阵

| 维度 | 短视频（≤5秒） | 长视频（>5秒） |
|------|-------------|-------------|
| **典型场景** | 单动作/单场景（3秒转圈/5秒走路） | 多动作/多场景（20秒连续剧情） |
| **生成方式** | 单段 HIGH+LOW 双阶段 | 分段生成（SVI Pro）+ 拼接 |
| **帧数策略** | 41-121帧（训练原生长度内） | 每段81帧×3-5段 = 243-405帧 |
| **模型架构** | WanVideoWrapper 原生节点 | SVI Pro（UNETLoader + KSamplerAdvanced） |
| **段间衔接** | 不需要 | anchor_samples + prev_samples / Flux2修正图 |
| **拼接方式** | 不需要 | ImageBatchExtendWithOverlap（overlap=5线性混合） |
| **FLF2V模式** | 可用（5秒首尾帧） | 不推荐（多段不适合强制末帧锚定） |
| **提示词策略** | 单一连续动作描述 | 分镜提示词（每段独立，精确到秒） |
| **SVI Pro 专属** | 不需要 | WanImageToVideoSVIPro + anchor_samples |
| **Flux2修正** | 可选（1次修正） | 推荐（每段SVI Pro后修正，作为下段传递） |

### 22.10 图片工作流容易出问题的节点注解

以下节点在图片生成工作流中虽然功能简单，但有特定陷阱：

| 节点 | 陷阱 | 后果 | 正确做法 |
|------|------|------|---------|
| **EmptyFlux2LatentImage** | 文生图模式从零生成 | 与img2img修正冲突，丢失原图构图 | 修正任务用VAEEncode替代 |
| **SplitSigmasDenoise** | denoise值不匹配任务 | <0.3修正无效，>0.7构图偏离 | Flux2修正推荐0.4-0.55 |
| **VAEEncode**（图片） | 分辨率不匹配模型 | SD1.5用1024×1024会导致质量崩溃 | 匹配模型训练分辨率 |
| **ImageResizeKJv2** | widget名不是"width"和"height" | 参数无法通过inputs设置 | 使用正确widget名 "resize_width" / "resize_height" |
| **SaveImage** | filename_prefix含中文或特殊字符 | Windows路径报错 | 仅用英文字母数字下划线 |

### 22.11 综合场景节点配置速查

| 场景 | 必需节点 | SVI Pro专属 | 多图专属 | Flux2修正 |
|------|---------|-----------|--------|----------|
| 3秒单图短视频 | WanVideoI2V Encode + Sampler + Decode + VHS | 不需要 | 不需要 | 可选 |
| 10秒多图视频（C5模式） | + WanVideoClipVisionEncode（双图） + 末帧提取 | 不需要 | CLIP concat 1.5/0.5 | 可选 |
| 20秒长视频（SVI Pro） | + UNETLoader×2 + WanImageToVideoSVIPro×5 + KSamplerAdvanced×10 | anchor_samples + prev_samples | 不需要（靠SVI Pro） | **每段必须** |
| 5秒首尾帧视频 | WanVideoI2V Encode（end_image）+ fun_or_fl2v_model=false | 不需要 | 不需要 | 可选 |

---

## 23. C8 多图视频生成完整任务复盘（2026-07-28）

> **核心目的**：本章完整记录从项目解压学习到多图视频生成成功的全流程问题盘点，覆盖项目启动、工作流构建、参数配置、显存管理、多图识别、提示词、任务监控七大阶段。所有问题均经实际验证修复，作为后续任务执行的避坑指南。
> **硬约束提醒**：本章所有参数推荐均基于 RTX 3080 20GB VRAM（L3 高性能级）验证，其他硬件档位需参考第21章参数梯度表进行等价换算。

### 23.1 阶段一：项目解压与学习问题

#### 23.1.1 文档阅读不完整导致定位偏差

**现象**：解压项目包后未一次性通读全部 12 个 `.md` 文档，特别是 1957 行的 `EXPERIENCE.md` 迭代经验只做了粗略浏览，导致对项目"AI agent 驱动 ComfyUI 全能控制器"的核心定位理解不透彻，后续任务执行偏离项目设计初衷。

**原因分析**：文档量庞大，急于进入实操阶段，忽视了经验文档中已沉淀的避坑方案。

**解决方案**：强制要求首次接触项目时完整阅读所有 `.md` 文档，并生成项目简报确认理解一致性。

**验证结果**：完成文档通读后，明确项目采用脚本模式 + CLI 模式融合架构，通过强制预检反问、硬件自适应、工业级视频架构实现端到端自动化。

---

### 23.2 阶段二：项目审计与 P0 修复问题

#### 23.2.1 SKILL.md 文档与代码存在冲突

**现象**：审计发现 `SKILL.md` 描述的流程、排错思路与实际代码实现存在冲突，无法保证完全准确。

**原因分析**：文档迭代滞后于代码迭代，部分描述基于早期版本未同步更新。

**解决方案**：审计 SKILL.md 与相关所有文件，严查逻辑性错误和数据安全风险，修复后通过真实测试验证。

#### 23.2.2 进程停止脚本误杀问题

**现象**：`stop_server.py` 进程匹配逻辑过于简单，仅匹配进程名 `python.exe`，导致误杀其他 Python 进程。

**原因分析**：未使用多条件精准匹配，缺少命令行参数特征识别。

**解决方案**：改为多条件匹配（`main.py` + python 进程特征），使用 `psutil` 配合 `wmic`/`pgrep` 回退机制，确保只停止 ComfyUI 主进程。

**验证结果**：通过实际启动/停止 ComfyUI 验证，无误杀情况。

#### 23.2.3 视频任务执行器错误检测不完整

**现象**：`video_task_runner.py` 无法区分任务成功/失败/超时，错误分类不清晰。

**原因分析**：`wait_for_completion` 缺乏 `success`/`error`/`error_type`/`error_node` 字段，无法区分执行错误、验证错误、超时、无输出四种情况。

**解决方案**：
- 增加 `success`/`error`/`error_type`/`error_node` 字段区分成功失败
- 错误分类改为 `execution_error`/`validation_error`/`timeout`/`no_output` 四类
- 增加 `wait_for_completion` 服务存活检测，服务崩溃时终止空轮询

#### 23.2.4 工作流执行脚本输出识别错误

**现象**：`run_workflow.py` 无法正确识别视频输出，漏检 `gifs` 和 `videos` 字段。

**原因分析**：仅检查 `images` 字段，未覆盖 VHS_VideoCombine 节点的所有输出字段。

**解决方案**：同时检查 `images`/`gifs`/`videos` 三个字段，确保正确识别所有视频输出。

**验证结果**：通过图片和视频工作流双重验证，输出识别正确。

---

### 23.3 阶段三：ComfyUI 启动问题（反复出现）

#### 23.3.1 白名单参数格式错误

**现象**：`--whitelist-custom-nodes` 参数使用逗号分隔字符串，导致白名单未生效，所有自定义节点被禁用。

**原因分析**：ComfyUI 启动参数要求空格分隔的多个独立参数，而非逗号分隔的单个字符串。

**解决方案**：将逗号分隔改为列表形式，每个节点名作为独立参数传入。

**反复出现原因**：首次修复后未在启动脚本中固化正确格式，重启时再次使用错误格式。

#### 23.3.2 sageattention DLL 兼容性问题

**现象**：使用 `attention_mode=sageattn` 时触发 `Windows fatal exception: code 0xc0000139`，DLL 加载失败。

**原因分析**：sageattention 的 C++/CUDA 扩展与当前 PyTorch 2.9.1+cu128 版本不兼容，DLL 入口点缺失。

**解决方案**：将 `attention_mode` 从 `sageattn` 改回 `sdpa`（PyTorch 原生注意力机制），牺牲少量速度换取稳定性。

**验证结果**：使用 `sdpa` 后无 DLL 错误，任务正常执行。

#### 23.3.3 智能内存管理参数冲突

**现象**：启动参数 `--disable-smart-memory` + `--disable-cuda-malloc` 组合导致内存分配问题，采样器在模型参数加载阶段卡死。

**原因分析**：禁用智能内存管理和 `cudaMallocAsync` 后，ComfyUI 无法有效管理显存分配，导致大模型加载时内存碎片化严重。

**解决方案**：移除这两个启动参数，使用默认的智能内存管理和 `cudaMallocAsync`。

#### 23.3.4 连续任务间显存不释放

**现象**：单次任务完成后显存占用 30GB+ 不释放，导致下次任务 T5 编码时 OOM。

**原因分析**：ComfyUI 的模型缓存机制保留模型引用，`force_offload` 仅将模型移到 CPU 但不释放内存。

**解决方案**：连续任务间必须重启 ComfyUI 服务，确保显存完全释放。

**硬性规则**：在 `SKILL.md` 中明确"连续任务间必须重启 ComfyUI"。

#### 23.3.5 自定义节点加载崩溃

**现象**：ComfyUI 启动器非白名单模式会加载全部自定义节点，导致 Manager 联网超时崩溃、Impact-Pack 加载卡住。

**原因分析**：部分节点插件存在联网请求或重量级初始化逻辑，在无网络环境下卡死。

**解决方案**：使用 `--disable-all-custom-nodes` + `--whitelist-custom-nodes` 白名单模式，仅加载任务必需节点。

**白名单节点清单**（按任务必需性分级）：
- **视频任务必需**：`ComfyUI-WanVideoWrapper`（核心视频节点）、`ComfyUI-VideoHelperSuite`（视频合成）、`ComfyUI-KJNodes`（辅助节点）
- **视频任务推荐**：`comfyui-frame-interpolation`（插帧）、`comfyui-essentials`（图像处理）
- **显存管理必需**：`ComfyUI_LayerStyle`（提供 `PurgeVRAM V2` 节点）

---

### 23.4 阶段四：工作流构建问题（反复出现）

#### 23.4.1 工作流文件格式不兼容

**现象**：工作流文件在 ComfyUI web 端无法查看，提示格式错误。

**原因分析**：文件保存为 API 格式（节点 ID 映射结构 `{node_id: {class_type, inputs}}`），而非 UI 格式（含 `nodes` 数组、`links` 数组、`id`、`pos` 等字段）。

**解决方案**：编写格式转换脚本，将 API 格式转换为 UI 格式，添加必要的 UI 元素字段。

**关键区别**：
- **API 格式**：用于通过 HTTP API 提交任务，结构紧凑
- **UI 格式**：用于在 ComfyUI 界面查看和编辑，包含布局信息

#### 23.4.2 UI 与 API 参数映射误解

**现象**：误将 UI 工作流中 `widgets_values[0]` 认为是 `cfg` 参数，实际对应 `shift` 参数。

**原因分析**：UI 格式中 `widgets_values` 数组的顺序与节点定义中 `INPUT_TYPES` 的顺序不一致，需要对照节点源码确认。

**解决方案**：明确 UI 与 API 参数映射关系，通过查询节点源码的 `INPUT_TYPES` 确定 `widgets_values` 数组的实际顺序。

**通用规则**：UI 格式的 `widgets_values` 顺序 = 节点 `INPUT_TYPES` 中 `required` 字段的定义顺序，而非字母序。

#### 23.4.3 节点链架构错误导致旋转问题

**现象**：生成的视频中人物持续旋转，动作卡住。

**原因分析**：错误架构将 `WanVideoBlockSwap` 的输出直接传入 `WanVideoModelLoader` 的 `block_swap_args` 输入，跳过了 `WanVideoSetBlockSwap` 节点，导致 BlockSwap 配置未正确应用。

**解决方案**：使用正确的节点链架构：
```
WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler
```

**错误架构**（禁止使用）：
```
WanVideoBlockSwap(生成args) → WanVideoModelLoader(直接接收block_swap_args) → WanVideoSampler
```

**原理分析**：`WanVideoSetBlockSwap` 是一个中间件节点，负责将 BlockSwap 配置正确应用到模型对象上，跳过它会导致模型使用默认的显存管理策略，无法有效分块卸载。

#### 23.4.4 必填参数缺失导致工作流验证失败

**现象**：工作流提交时返回参数验证错误。

**原因分析**：部分节点有必填参数未填写，如 `WanVideoSampler` 的 `riflex_freq_index`、`WanVideoVAELoader` 的 `precision`。

**解决方案**：对照节点源码的 `INPUT_TYPES` 确认所有必填参数，补充缺失值。

**必填参数清单**（踩坑记录）：
- `WanVideoSampler`：`riflex_freq_index`（默认 0，防止 RoPE 数学循环）
- `WanVideoVAELoader`：`precision`（必须显式指定，不能依赖默认值）

#### 23.4.5 双模型同时加载导致 OOM

**现象**：HIGH 和 LOW 模型同时加载到显存，导致 OOM 或被迫使用共享 GPU 内存。

**原因分析**：仅依赖 `force_offload=true`，但 ComfyUI 的模型缓存机制保留模型引用，导致 HIGH 模型执行后显存未完全释放，LOW 模型加载时两个模型同时驻留。

**解决方案**：在 HIGH→LOW 切换点插入显式显存清理节点（`PurgeVRAM V2`），彻底卸载 HIGH 模型后再加载 LOW 模型。

**三层显存管理防线**（必须同时启用）：
1. **第一层**：`load_device="offload_device"` + `force_offload=true`（模型初始加载到 CPU，采样后强制卸载）
2. **第二层**：显式显存清理节点 `PurgeVRAM V2`（在模型切换点彻底释放显存）
3. **第三层**：`WanVideoBlockSwap` 分块卸载（采样过程中动态交换 transformer blocks）

#### 23.4.6 误删 LOW 模型节点改为单采样器

**现象**：为简化配置，删除了 LOW 模型相关 5 个节点，改为单采样器架构。

**原因分析**：误认为可以简化为单采样器，忽视了双模型架构的设计初衷。

**解决方案**：恢复双采样器（HIGH+LOW）架构，这是项目硬约束，不可更改。

**原理分析**：双模型架构通过 `start_step`/`end_step` 参数控制双阶段采样，HIGH 模型处理高噪声主结构，LOW 模型处理低噪声细化，两者分工明确，单采样器无法达到同等质量。

---

### 23.5 阶段五：参数配置问题（反复出现）

#### 23.5.1 low 采样器 cfg 参数错误

**现象**：用户检查发现 UI 工作流中 low 采样器 `cfg=8`，远超合理范围。

**原因分析**：UI 格式中 `widgets_values` 数组顺序误解，将 `shift` 参数的值误认为 `cfg` 参数。

**解决方案**：明确 `cfg` 参数位置，LOW 采样器 `cfg=1.0`（蒸馏 LoRA 模式下，LOW 阶段不需要 CFG 引导）。

**cfg 参数选择指南**（基于加速 LoRA 蒸馏模式）：
- **HIGH 采样器**：使用 `CreateCFGScheduleFloatList` 动态调度，第一步 `cfg=2.0`，其余步 `cfg=1.0`
- **LOW 采样器**：固定 `cfg=1.0`（LOW 阶段处理低噪声细化，不需要 CFG 引导）
- **最大值限制**：任何阶段 `cfg` 不超过 6.0，过高会导致画面过曝

#### 23.5.2 steps 参数设置过高

**现象**：任务执行时间过长，20 分钟未完成。

**原因分析**：`steps=8` 在加速 LoRA 蒸馏模式下过高，蒸馏 LoRA 已将所需步数降至 6-8 步。

**解决方案**：`steps=4`（HIGH:2 + LOW:2），配合 `lightx2v` 蒸馏 LoRA 使用。

**steps 参数选择指南**（基于加速 LoRA）：
- **L3 高性能级（16-24GB VRAM）**：`steps=4`（HIGH:2 + LOW:2）
- **L4 专业级（≥24GB VRAM）**：`steps=6-8`（HIGH:3-4 + LOW:3-4）
- **无加速 LoRA**：`steps=20-30`（不推荐，耗时过长）

#### 23.5.3 num_frames 设置过高导致卡死

**现象**：`num_frames=121` 导致任务卡死，帧数自动降至 81。

**原因分析**：Wan2.2 I2V 模型训练原生长度约 81 帧（3.4秒@24fps），超过训练长度时模型通过重复动作序列填充时间，且显存需求激增。

**解决方案**：`num_frames=81`（训练原生长度，最稳定）。

**num_frames 选择指南**（按显存档位）：
- **L1 入门级（8-12GB）**：81 帧（3.4秒）
- **L2 标准级（12-16GB）**：81-121 帧
- **L3 高性能级（16-24GB）**：81-121 帧（推荐 81，超过易触发语义重复）
- **L4 专业级（≥24GB）**：121-241 帧

#### 23.5.4 分辨率不符合用户要求比例

**现象**：生成视频画面变形，不符合用户要求的 3:4 比例。

**原因分析**：分辨率设置为 832x480（16:9），与用户要求的 3:4 比例不匹配。

**解决方案**：根据任务类型选择正确分辨率：
- **单图 3:4 比例**：640x848
- **双图水平拼接 3:2 比例**：960x640（每张图 480x640）

**分辨率选择原则**：分辨率必须与 `start_image` 的实际比例一致，否则 VAE 编码后 latent 尺寸不匹配会导致 `tensor size mismatch` 错误或画面变形。

#### 23.5.5 LoRA strength 配置错误

**现象**：HIGH 模型 LoRA strength=3.0，导致 MoE 自然去噪曲线被破坏，细节丢失。

**原因分析**：误认为提高 strength 可以增强加速效果，实际会破坏蒸馏 LoRA 的数学特性。

**解决方案**：HIGH 和 LOW 均 `strength=1.0`（官方推荐值）。

**LoRA strength 选择指南**：
- **加速蒸馏 LoRA**（`lightx2v_I2V_14B_480p_cfg_step_distill`）：HIGH=1.0, LOW=1.0
- **画质增强 LoRA**（`SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH`）：1.0（不可与加速 LoRA 叠加）
- **重新打光 LoRA**（`WanAnimate_relight`）：0.5-1.0

#### 23.5.6 blocks_to_swap 参数反复调整

**现象**：`blocks_to_swap=36` 时专用显存几乎不利用，大量使用共享内存；`blocks_to_swap=40` 时采样器卡死。

**原因分析**：
- `blocks_to_swap` 过高：GPU 保留的 block 过少，无法利用专用显存优势
- `blocks_to_swap` 过低：显存不足导致 OOM 或卡死

**解决方案**：`blocks_to_swap=20`（L3 高性能级推荐值）。

**blocks_to_swap 选择指南**（按显存档位）：
- **L1 入门级（8-12GB）**：40-42（激进卸载）
- **L2 标准级（12-16GB）**：38-40
- **L3 高性能级（16-24GB）**：20-36（推荐 20，专用显存利用率 75%+）
- **L4 专业级（≥24GB）**：20-24

**关键原则**：在专用显存未被充分利用前，不使用共享 GPU 内存。`blocks_to_swap` 的作用是控制有多少 transformer blocks 在 CPU/GPU 间交换，值越大 GPU 保留的 block 越少。

#### 23.5.7 其他参数配置错误汇总

| 参数 | 错误值 | 正确值 | 原因分析 |
|------|--------|--------|---------|
| `noise_aug_strength` | 0 | 0.1 | 为 0 会导致亮度锚定缺失，画面亮度漂移 |
| `rope_function` | `comfy` | `comfy_chunked` | 480x848 及以上分辨率必须使用 chunked 模式降低显存峰值 |
| `scheduler` | `unipc` | `dpm++_sde` | unipc 会导致动作卡住旋转，dpm++_sde 产生自然动作变化 |
| `shift` | 3.0/5.0 | 8.0 | shift 值控制噪声调度曲线，8.0 是 Wan2.2 I2V 的最佳值 |

---

### 23.6 阶段六：显存管理问题（核心问题，反复出现 6 次）

#### 23.6.1 专用 GPU 显存未利用，大量使用共享内存

**现象**：任务执行时专用显存仅使用 8GB（共 20GB 可用），但大量使用共享 GPU 内存，导致生成速度极慢。

**原因分析**：
- `blocks_to_swap=36` 过高，GPU 保留的 block 过少
- 未启用显式显存清理节点，模型残留显存
- 启动参数禁用了智能内存管理

**解决方案**（综合）：
1. 降低 `blocks_to_swap` 到 20（L3 级推荐值）
2. 在 HIGH→LOW 切换点插入 `PurgeVRAM V2` 节点
3. 移除 `--disable-smart-memory` 和 `--disable-cuda-malloc` 启动参数
4. 确保 `load_device="offload_device"` + `force_offload=true`

**验证结果**：专用显存使用率从 40% 提升到 75-79%，未使用共享 GPU 内存。

#### 23.6.2 用户反复强调专用显存优先原则

**现象**：用户 3 次强调"在专用 GPU 显存未被尽可能利用前，尽量不使用共享 GPU 内存"，但执行中反复出现共享内存使用。

**原因分析**：
- 未严格遵循用户硬约束
- 没有借鉴本地成熟工作流的显存管理方案
- 对 `blocks_to_swap` 参数的物理意义理解不透彻

**解决方案**：借鉴本地 `KJ极速版` 和 `首尾帧加速版` 工作流的显存管理方案：
- `KJ极速版`：在 HIGH→LOW 切换点部署 `easy clearCacheAll` + `easy cleanGpuUsed` 链
- `首尾帧加速版`：部署 5 个 `PurgeVRAM` 节点全程清理
- 最终方案：采用 `PurgeVRAM V2` 节点（来自 `ComfyUI_LayerStyle`），在 HIGH 后和 LOW 后各部署一个

#### 23.6.3 采样器在模型参数加载阶段卡死

**现象**：HIGH 采样器在加载模型参数（如 100/1095）时卡住，GPU 利用率 100% 但无进度更新。

**原因分析**：
- `blocks_to_swap` 过高（36/40），显存管理策略激进
- 启动参数禁用了智能内存管理
- dpm++_sde 调度器的某些步骤计算量大，进度更新不频繁但仍在计算

**解决方案**：
1. 降低 `blocks_to_swap` 到 20
2. 移除 `--disable-smart-memory` 和 `--disable-cuda-malloc`
3. 增加显存监控，确认 GPU 利用率和功耗（100% + 313W 表示仍在计算，非卡死）

**判断卡死 vs 正常计算的方法**：
- **正常计算**：GPU 利用率 100%，功耗接近满载（313W/320W），显存稳定
- **真正卡死**：GPU 利用率 0% 或波动大，功耗低，显存持续不变

---

### 23.7 阶段七：多图识别问题（核心问题）

#### 23.7.1 视频只有单个人物，缺少第二张图的元素

**现象**：生成的视频只有 1.png 的人物，完全没有 2.png 的任何元素。

**原因分析**：`WanVideoImageToVideoEncode` 节点的 `start_image` 只连接了 1.png，而 `WanVideoClipVisionEncode` 的 `combine_embeds="concat"` 只是语义特征合并，不会让两张图的像素同时出现在起始帧里。

**关键认知**：
- `start_image`：决定视频起始帧的视觉内容（像素级锚定）
- `WanVideoClipVisionEncode`：提供语义引导（告诉模型画面里有什么人物/物体）
- `combine_embeds="concat"`：拼接的是 CLIP 视觉嵌入向量（语义特征），不是像素

**解决方案**：使用 `ImageConcatMulti` 节点（来自 `ComfyUI-KJNodes`）将两张图水平拼接成一张，作为 `start_image`。

**节点链架构**：
```
LoadImage(1.png) → ImageScale(480x640) ─┐
                                         ├─→ ImageConcatMulti(direction="right") ──→ WanVideoImageToVideoEncode.start_image
LoadImage(2.png) → ImageScale(480x640) ─┘
                                         (同时仍分别送入 WanVideoClipVisionEncode.image_1/image_2)
```

**分辨率调整**：两张 480x640 的图水平拼接后为 960x640，`WanVideoImageToVideoEncode` 的 `width` 和 `height` 必须设置为 960x640，否则会被强制缩放导致变形。

#### 23.7.2 提示词未明确人物位置关系

**现象**：即使拼接了 start_image，生成的视频中两个女孩的位置仍然混乱。

**原因分析**：提示词只描述"两个女孩跳舞"，没有明确左右位置关系。

**解决方案**：提示词明确描述位置关系："两个女孩并排站立同框跳舞，左边女孩来自参考图1，右边女孩来自参考图2"。

**多图视频提示词原则**：
- 明确每个人物的位置（左/右/前/后）
- 明确人物间的关系（手拉手/面对面/并排）
- 保持 CLIP Vision 双图编码（提供角色一致性引导）

---

### 23.8 阶段八：提示词问题（反复出现）

#### 23.8.1 提示词过于冗长

**现象**：提示词超过 300 字符，堆砌大量控制词，模型难以抓住重点。

**原因分析**：误认为描述越详细生成质量越高，实际相反，冗长的提示词会让模型困惑。

**解决方案**：精简到 60 字符以内，遵循图生视频公式：`运动 + 运镜`。

**Wan2.2 提示词公式**：
- **基础公式**：`主体 + 场景 + 运动`
- **进阶公式**：`主体（主体描述）+ 场景（场景描述）+ 运动（运动描述）+ 美学控制 + 风格化`
- **图生视频公式**：`运动 + 运镜`（图已确定主体、场景与风格，提示词主要描述动态过程）

#### 23.8.2 运镜描述导致画面混乱

**现象**：提示词包含 "360 orbit"、"slow orbit camera shot"，导致相机乱转，画面混乱。

**原因分析**：Wan2.2 对运镜描述非常敏感，"orbit" 类描述会直接触发相机旋转。

**解决方案**：删除所有运镜词，改为"固定镜头"。

**运镜描述选择指南**：
- **静态场景**：固定镜头、画面稳定
- **推进场景**：镜头缓慢推进
- **禁止使用**：360 orbit、camera spin、rotating shot（会导致画面混乱）

#### 23.8.3 使用英文提示词而非中文

**现象**：使用英文提示词，生成效果不理想。

**原因分析**：Wan2.2 原生支持中文，中文提示词理解更准确。

**解决方案**：改用中文提示词，遵循三段式结构。

**三段式结构要求**：
1. **画质前缀 + 镜头语言 + 场景描述**：`双人镜头，中心构图，[场景描述]`
2. **主体外观 + 状态**：`两个女孩并排站立同框跳舞`
3. **时序动作 + 控制词**：`手拉手，同步舞步，身体自然摆动，固定镜头`

#### 23.8.4 负面提示词不完整

**现象**：负面提示词缺少相机运动、人物不一致等关键项。

**解决方案**：补充完整负面提示词，覆盖以下类别：
- **相机运动**：`camera movement, camera pan, camera tilt, camera zoom, camera dolly, camera shake, 360 orbit, spinning, rotating, 视角突变, 镜头移动, 运镜`
- **人物一致性**：`face changing, character drift, inconsistent appearance, 人物消失, 人物突变`
- **画面问题**：`motion blur, frame skipping, distorted body, deformed limbs, 单人镜头, 背景变化, 场景切换, 多余人物, 缺失人物`
- **基础负面**：`静态, 模糊, 低质量, 最差质量, JPEG压缩残留, 丑陋, 残缺, 畸形, 毁容`

---

### 23.9 阶段九：任务执行监控问题

#### 23.9.1 ComfyUI 主线程阻塞

**现象**：任务执行中 ComfyUI 主线程阻塞，TCP 连通但无 HTTP 响应。

**原因分析**：任务执行时间过长，主线程被采样器占用，无法处理 HTTP 请求。

**解决方案**：使用 `curl -v` 诊断连通性，优化参数降低执行时间。

#### 23.9.2 任务执行时间过长

**现象**：480P 24帧 5秒视频执行 8-20 分钟未完成。

**原因分析**：
- 显存未充分利用（仅 8GB/20GB）
- 参数过高（steps=8, num_frames=121）
- blocks_to_swap 过高导致专用显存未利用

**解决方案**（综合优化）：
- 优化显存管理（blocks_to_swap=20 + PurgeVRAM）
- 降低参数（steps=4, num_frames=81）
- 使用加速 LoRA（lightx2v 蒸馏）

**优化后执行时间**：8-10 分钟（可接受范围）

#### 23.9.3 采样器长时间无进度更新

**现象**：HIGH 采样器在 600/1095 进度后 170 秒无进度更新。

**原因分析**：dpm++_sde 调度器的随机性计算特性，某些步骤计算量大但进度不频繁更新。

**解决方案**：增加显存监控，通过 GPU 利用率和功耗判断是否仍在计算。

**监控指标**（判断任务是否卡死）：
- **正常计算**：GPU 利用率 100%，功耗 313W（接近满载 320W），显存稳定在 72-79%
- **真正卡死**：GPU 利用率 0% 或波动大，功耗低，显存持续不变
- **等待超时阈值**：单个采样步骤超过 5 分钟无进度更新才判定为卡死

---

### 23.10 阶段十：视频输出问题

#### 23.10.1 视频画面比例错误

**现象**：生成视频为 16:9 比例，不符合用户要求的 3:4。

**原因分析**：分辨率设置为 832x480（16:9）。

**解决方案**：根据任务要求设置正确分辨率，确保与 `start_image` 比例一致。

#### 23.10.2 视频画面混乱

**现象**：视频画面混乱，人物动作不协调。

**原因分析**：提示词包含 "360 orbit" 等运镜词，导致相机乱转。

**解决方案**：删除运镜词，改为"固定镜头"。

#### 23.10.3 视频只有单个人物

**现象**：多图视频任务生成的视频只有 1.png 的人物。

**原因分析**：`start_image` 只连接 1.png，CLIP Vision 的 concat 只是语义引导。

**解决方案**：使用 `ImageConcatMulti` 水平拼接两张图作为 `start_image`。

---

### 23.11 反复出现问题汇总与根因分析

#### 23.11.1 反复出现 3 次以上的问题

| 问题类别 | 出现次数 | 根本原因 | 最终解决方案 |
|---------|---------|---------|------------|
| **显存管理问题** | 6 次 | 没有严格遵循用户硬约束，没有借鉴本地成熟方案 | blocks_to_swap=20 + PurgeVRAM V2 + 移除 disable 参数 |
| **参数配置错误** | 5 次 | 没有严格对照硬件梯度档位表 | 严格对照 L3 级参数表配置 |
| **工作流构建错误** | 4 次 | 没有充分理解节点链架构和参数映射 | 借鉴本地成熟工作流，明确节点链架构 |
| **提示词问题** | 4 次 | 没有学习 Wan2.2 官方提示词教程 | 遵循图生视频公式，简洁中文描述 |
| **启动脚本问题** | 3 次 | 参数格式和节点兼容性问题 | 固化正确参数格式，添加必需节点到白名单 |

#### 23.11.2 关键教训

1. **先借鉴本地成熟工作流**：不要从零开始配置，先查找本地已有的成熟工作流作为参考
2. **显存管理需要多层防线**：`force_offload` + `PurgeVRAM` + `blocks_to_swap` 三层同时启用
3. **多图视频必须拼接 start_image**：CLIP Vision 的 concat 只是语义引导，不是像素合并
4. **提示词要简洁明了**：遵循图生视频公式（运动+运镜），中文描述，60 字符以内
5. **参数配置要严格对照硬件档位表**：不能凭感觉调整，参考第 21 章参数梯度表
6. **连续任务间必须重启 ComfyUI**：避免显存残留导致 OOM
7. **项目文档与代码可能存在冲突**：需要实际验证修复，不能盲信文档
8. **必须严格遵循用户硬约束**：专用显存优先、双模型串行执行、不使用共享内存

---

### 23.12 最终验证成功的工作流参数配置

基于完整任务复盘，以下是验证成功的多图视频工作流参数配置（L3 高性能级，RTX 3080 20GB VRAM）：

#### 23.12.1 模型加载参数

| 节点 | 参数 | 值 | 原因分析 |
|------|------|-----|---------|
| `WanVideoModelLoader` (HIGH) | `model` | `Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors` | 高噪声阶段专用模型 |
| `WanVideoModelLoader` (HIGH) | `base_precision` | `bf16` | L3 级推荐精度 |
| `WanVideoModelLoader` (HIGH) | `quantization` | `fp8_e4m3fn_scaled` | 显存优化量化 |
| `WanVideoModelLoader` (HIGH) | `load_device` | `offload_device` | 模型初始加载到 CPU，按需载入 GPU |
| `WanVideoModelLoader` (HIGH) | `attention_mode` | `sdpa` | PyTorch 原生注意力，避免 sageattention DLL 问题 |
| `WanVideoModelLoader` (LOW) | 同 HIGH，模型改为 `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` | - | 低噪声细化阶段专用模型 |

#### 23.12.2 显存管理参数

| 节点 | 参数 | 值 | 原因分析 |
|------|------|-----|---------|
| `WanVideoBlockSwap` | `blocks_to_swap` | `20` | L3 级推荐值，专用显存利用率 75%+ |
| `WanVideoBlockSwap` | `use_non_blocking` | `true` | 异步传输，提高效率 |
| `WanVideoBlockSwap` | `prefetch_blocks` | `1` | 预取一个 block 减少等待 |
| `WanVideoSampler` (HIGH) | `force_offload` | `true` | 采样后强制卸载模型 |
| `WanVideoSampler` (LOW) | `force_offload` | `true` | 采样后强制卸载模型 |
| `PurgeVRAM V2` (HIGH 后) | `purge_cache` + `purge_models` | `true` + `true` | 彻底清理 HIGH 模型显存 |
| `PurgeVRAM V2` (LOW 后) | `purge_cache` + `purge_models` | `true` + `true` | 彻底清理 LOW 模型显存 |

#### 23.12.3 采样参数

| 节点 | 参数 | 值 | 原因分析 |
|------|------|-----|---------|
| `INTConstant` (steps) | `value` | `4` | 加速 LoRA 蒸馏模式，4 步足够 |
| `INTConstant` (split_step) | `value` | `2` | HIGH 处理前 2 步，LOW 处理后 2 步 |
| `CreateCFGScheduleFloatList` | `cfg_scale_start`/`end` | `2.0`/`2.0` | 第一步 CFG=2，其余步 CFG=1 |
| `WanVideoSampler` (HIGH) | `cfg` | 连接到 `cfg_schedule` | 动态 CFG 调度 |
| `WanVideoSampler` (LOW) | `cfg` | `1.0` | LOW 阶段不需要 CFG 引导 |
| `WanVideoSampler` (both) | `shift` | `8.0` | Wan2.2 I2V 最佳值 |
| `WanVideoSampler` (both) | `scheduler` | `dpm++_sde` | 随机性调度器，产生自然动作 |
| `WanVideoSampler` (both) | `rope_function` | `comfy_chunked` | 降低显存峰值 |
| `WanVideoSampler` (both) | `riflex_freq_index` | `0` | 防止 RoPE 数学循环 |

#### 23.12.4 LoRA 参数

| 节点 | 参数 | 值 | 原因分析 |
|------|------|-----|---------|
| `WanVideoLoraSelect` (HIGH) | `lora` | `lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors` | 加速蒸馏 LoRA |
| `WanVideoLoraSelect` (HIGH) | `strength` | `1.0` | 官方推荐值，过高会破坏 MoE 去噪曲线 |
| `WanVideoLoraSelect` (LOW) | `lora` | 同 HIGH | 加速蒸馏 LoRA |
| `WanVideoLoraSelect` (LOW) | `strength` | `1.0` | 官方推荐值 |

#### 23.12.5 多图识别参数

| 节点 | 参数 | 值 | 原因分析 |
|------|------|-----|---------|
| `ImageScale` (1) | `width`/`height` | `480`/`640` | 单张图 3:4 比例 |
| `ImageScale` (2) | `width`/`height` | `480`/`640` | 单张图 3:4 比例 |
| `ImageConcatMulti` | `direction` | `right` | 水平拼接，符合人物同框视觉直觉 |
| `ImageConcatMulti` | `match_image_size` | `true` | 自动匹配图片尺寸 |
| `WanVideoImageToVideoEncode` | `width`/`height` | `960`/`640` | 拼接后尺寸，避免变形 |
| `WanVideoImageToVideoEncode` | `num_frames` | `81` | 训练原生长度，最稳定 |
| `WanVideoImageToVideoEncode` | `noise_aug_strength` | `0.1` | 亮度锚定，禁止 0 |
| `WanVideoImageToVideoEncode` | `start_image` | 连接到 `ImageConcatMulti` | 拼接后的图片作为起始帧 |
| `WanVideoClipVisionEncode` | `image_1`/`image_2` | 分别连接两张缩放后的图 | 提供双图语义引导 |
| `WanVideoClipVisionEncode` | `strength_1`/`strength_2` | `1.5`/`1.0` | 主图权重略高 |
| `WanVideoClipVisionEncode` | `combine_embeds` | `concat` | 语义特征拼接 |

#### 23.12.6 提示词配置

| 类型 | 内容 | 原因分析 |
|------|------|---------|
| **正面提示词** | `双人镜头，两个女孩并排站立同框跳舞，左边女孩来自参考图1，右边女孩来自参考图2，两人手拉手，同步舞步，身体自然摆动，面带微笑，动作协调一致，固定镜头，画面稳定，背景一致` | 中文简洁描述，明确位置关系，遵循图生视频公式 |
| **负面提示词** | `camera movement, camera pan, camera tilt, camera zoom, camera dolly, camera shake, 360 orbit, spinning, rotating, 视角突变, 镜头移动, 运镜, 单人镜头, 背景变化, 场景切换, 人物消失, 人物突变, face changing, character drift, inconsistent appearance, motion blur, frame skipping, distorted body, deformed limbs, 多余人物, 缺失人物, 动作僵硬, 动作断裂, 静态, 模糊, 低质量, 最差质量, JPEG压缩残留, 丑陋, 残缺, 畸形, 毁容` | 覆盖相机运动、人物一致性、画面问题、基础负面四类 |

#### 23.12.7 验证结果

| 指标 | 结果 | 达标 |
|------|------|------|
| 总耗时 | 10.6 分钟 | ✅ |
| 专用显存使用率 | 77-79% | ✅ |
| 共享 GPU 内存使用 | 未使用 | ✅ |
| 双模型串行执行 | HIGH→PurgeVRAM→LOW | ✅ |
| 视频包含两个女孩 | 是 | ✅ |
| 画面比例正确 | 3:2（拼接后） | ✅ |
| 时长 | 3.4 秒（81帧@24fps） | ✅ |

---

## 24. 长视频工作流优化与三大问题修复复盘（2026-07-29）

> **核心目的**：本章完整记录 SVI Pro 长视频工作流（`long_video_svi_pro_wan22_v1.0.0.json`）从执行时间优化到色调/动作/拼接三大问题修复的完整迭代过程。所有问题均经实际执行验证修复，作为后续长视频任务的避坑指南。
> **硬约束提醒**：本章所有参数推荐均基于 RTX 3080 20GB VRAM（L3 高性能级）验证，其他硬件档位需参考第 21 章参数梯度表进行等价换算。所有路径使用 `${PROJECT_PATH}`、`${COMFYUI_PATH}`、`${COMFYUI_PORT}` 变量替代绝对路径。

### 24.1 任务背景

基于 C8 多图视频任务（第 23 章）的成功经验，本章针对 SVI Pro 长视频工作流进行深度优化。源工作流为 `${COMFYUI_PATH}/user/default/workflows/wan2.2 长视频高质量生成（24秒）.json`，采用 5 段 SVI Pro + 4 段 Flux2 换皮架构，目标生成 14.81 秒（237 帧@16fps）竖屏长视频。

**初始问题**：源工作流执行时间约 58 分钟，超出目标 30-40 分钟；执行后存在动作偏离、色调漂移、拼接渐变三大质量问题。

### 24.2 阶段一：执行时间优化（3 个问题）

#### 24.2.1 初始执行时间过长（58 分钟）

**现象**：源工作流执行约 58 分钟，超出 30-40 分钟目标。

**根因分析**：
- SVI Pro 每段帧数过高（`length=81`，5 段共 405 帧）
- SVI Pro 采样步数过多（`steps=6`，HIGH:3 + LOW:3）
- Flux2 修正步数过多（`steps=12`）
- RealESRGAN 超分节点启用，增加额外耗时

**修复方案**（参数梯度选择）：

| 参数 | 原值 | 优化值 | 物理意义 | 梯度建议 |
|------|------|--------|---------|---------|
| `length`（SVI 每段帧数） | 81 | 49 | 单段生成帧数，影响耗时线性 | L1-L2: 25-33；L3: 49-81；L4: 81-121 |
| `steps`（SVI 采样步数） | 6 | 3 | HIGH+LOW 总步数，蒸馏 LoRA 可低至 3 | 加速 LoRA: 3-6；画质 LoRA: 14-20；无 LoRA: 20-30 |
| `steps`（Flux2 修正步数） | 12 | 8 | img2img 修正迭代次数 | 轻量修正: 4-6；平衡修正: 8-10；深度修正: 12-16 |
| RealESRGAN | 启用 | 旁路 | 超分增加耗时但画质提升有限 | 最终输出启用；中间修正旁路 |

**验证结果**：执行时间从 58 分钟降至约 22 分钟（L3 级硬件）。

#### 24.2.2 视频时长不足

**现象**：首次优化后视频仅 9.75 秒，未达预期。

**根因分析**：`length` 从 81 降至 25 后，总帧数 = 5 × 25 - 4 × overlap = 121 帧，@16fps 仅 7.56 秒。

**修复方案**：
- 调整 `length=49`，5 段总帧数 = 5 × 49 - 4 × 1 = 241 帧（实际 237 帧）
- 帧率 `frame_rate=16`，视频时长 = 237 / 16 ≈ 14.81 秒

**帧数/帧率/时长关系公式**：
```
总帧数 = 段数 × 每段帧数 - (段数-1) × overlap
视频时长(秒) = 总帧数 / frame_rate
```

**帧率梯度建议**：
- `frame_rate=16`：长视频推荐，平衡流畅度与耗时
- `frame_rate=20`：源工作流默认，画质更流畅但耗时增加 25%
- `frame_rate=24`：短视频标准，训练原生帧率，单段 81 帧 = 3.4 秒

#### 24.2.3 工作流 group 格式不兼容

**现象**：ComfyUI 加载工作流时报错 `TypeError: can't convert undefined to object`。

**根因分析**：工作流中 28 个 group 使用旧版格式（`pos+size` 数组），缺少 ComfyUI 0.27.0 要求的 `id`、`flags` 字段和 `bounding` 数组格式。

**修复方案**：
- 将所有 group 的 `pos+size` 转换为 `bounding: [x, y, w, h]` 格式
- 为每个 group 添加 `id`（唯一标识）和 `flags: {}` 字段

**group 格式规范**（ComfyUI 0.27.0+）：
```json
{
  "id": 1,
  "title": "段1-SVI Pro",
  "bounding": [100, 200, 300, 400],
  "flags": {}
}
```

### 24.3 阶段二：动作偏离修复

#### 24.3.1 Flux2 换皮后动作偏离原始截图

**现象**：Flux2 修正后角色动作偏离 SVI Pro 生成的原始截图动作，虽然角色外貌、画面细节约束得到提高，但动作未完全参照截图画面。

**根因分析**：`SplitSigmasDenoise` 节点的 `denoise=0.75` 过高，Flux2 对输入帧的修改强度过大，破坏了 SVI Pro 生成的动作结构。

**关键认知**：`denoise` 参数在 img2img 模式下控制添加噪声的比例：
- `denoise=1.0`：完全重新生成（纯文生图），不保留原图动作
- `denoise=0.0`：完全保留原图，不进行任何修正
- Flux2 换皮场景需要平衡"外貌替换"与"动作保留"

**修复方案**：`denoise` 从 0.75 下调至 0.6。

**denoise 梯度分析（Flux2 换皮专用）**：

| denoise 值 | 修正力度 | 动作保留 | 外貌替换 | 适用场景 |
|-----------|---------|---------|---------|---------|
| 0.3-0.4 | 极弱 | 100% | 20% | 轻微色调调整 |
| 0.4-0.5 | 弱 | 90% | 50% | 降噪+色调统一 |
| 0.5-0.6 | 平衡 | 80% | 70% | **推荐区间**：平衡修正与动作保留 |
| **0.6** | **平衡** | **70%** | **80%** | **本任务验证值**：换皮充分且动作保留 |
| 0.7-0.8 | 强 | 50% | 90% | 明显瑕疵修复，动作可能偏离 |
| 0.8-1.0 | 极强 | 0% | 100% | 文生图模式，不适用于换皮场景 |

**关键禁忌**：
- `denoise < 0.3`：模型可操作空间不足，换皮无效
- `denoise > 0.7`：接近文生图，动作结构被破坏
- Flux2 换皮推荐区间 0.5-0.65（本任务验证 0.6 为最优平衡点）

### 24.4 阶段三：色调漂移修复（两层防线）

#### 24.4.1 色调逐渐变冷、变白（提示词层防线）

**现象**：5 秒视频中色调随时间逐渐变冷、变白，偏离原始参考图色调。

**根因分析**：
1. SVI Pro 正向提示词仅"无红色色偏"，缺乏暖色调正向约束
2. SVI Pro 负向提示词含"暖色溢色"，与正向约束冲突，导致模型在避免暖色溢出的同时过度倾向冷色

**修复方案**（提示词层）：
- 5 段正向提示词追加："整体保持暖色调，与参考图B的色温保持一致，禁止画面逐渐变冷、变白"
- 5 段负向提示词移除"暖色溢色"，追加"画面变冷，画面变白"
- Flux2 正向提示词追加："色彩饱和度严格参照B图"
- Flux2 负向提示词追加："画面变冷，画面变白，色调跑偏，色彩偏移"

**提示词色调约束原则**：
- 正向约束指定目标色调（"保持暖色调"），负向约束禁止偏离方向（"禁止变冷变白"）
- 正负向提示词不可冲突（如正向要求暖色，负向禁止暖色溢色）
- 色调约束需明确参考基准（"与参考图B的色温保持一致"）

#### 24.4.2 色调全程不稳定 + Flux2 颜色加深（ColorMatch 硬性锚定）

**现象**：
1. 提示词约束后，视频生成过程中色调仍逐渐偏离原参考图
2. Flux2 修正的画面颜色比原参考图加深

**根因分析**：
1. SVI Pro 段间累积漂移：每段 SVI 生成的色调在前段基础上累积偏移，提示词约束无法硬性锚定
2. Flux2 换皮时改变色彩：LoRA-ColorTone（`strength=0.3`）强度不足以完全校正 Flux2 引入的色彩偏移

**修复方案**（ColorMatch 硬性锚定层）：插入 9 个 `ColorMatch` 节点进行算法级颜色锚定。

**节点部署架构**：
```
参考图B(LoadImage) ─────────────────────────┐
                                            ↓ (image_ref)
SVI Pro 段N VAEDecode 输出 → ColorMatch_N → 下游节点
Flux2 段N ImageResize 输出 → ColorMatch_N → 下游节点
```

**ColorMatch 节点参数配置**：

| 参数 | 值 | 物理意义 | 梯度建议 |
|------|-----|---------|---------|
| `method` | `reinhard` | Reinhard 颜色迁移算法，平滑过渡 | `mkl`: 强烈迁移，可能局部失真；`reinhard`: 平滑，适合视频序列；`idt-matrix`: 精确但耗时 |
| `strength` | `0.85` | 颜色锚定强度，0=不锚定，1=完全匹配参考 | 0.6-0.7: 轻度锚定，保留自然变化；0.8-0.9: 强锚定，适合长视频防漂移；1.0: 完全匹配，可能丢失场景细节 |
| `image_ref` | 参考图B LoadImage | 颜色参考源（所有 9 个节点共用同一参考） | 必须选择色调稳定的参考图，避免使用生成帧作为参考 |
| `image_target` | SVI/Flux2 输出 | 待锚定的目标图像 | 支持 batch 输入，自动逐帧锚定 |

**部署位置**（共 9 个节点）：
- 5 个 SVI ColorMatch：每个 SVI Pro 段的 VAEDecode 输出后、分叉前
- 4 个 Flux2 ColorMatch：每个 Flux2 段的 ImageResizeKJv2 输出后

**两层防线对比**：

| 防线 | 机制 | 优点 | 缺点 | 适用场景 |
|------|------|------|------|---------|
| 提示词约束 | 通过文本引导控制色调 | 简单，无额外节点 | 约束弱，无法防止累积漂移 | 短视频（≤5秒），色调偏移轻微 |
| ColorMatch 锚定 | 算法级颜色迁移 | 硬性锚定，防止任何漂移 | 增加计算开销 | 长视频（>5秒），多段拼接，Flux2 换皮 |

**验证结果**：色调全程稳定，Flux2 输出色调与参考图B一致，不再加深。

### 24.5 阶段四：拼接渐变修复

#### 24.5.1 视频段拼接处存在渐变过渡

**现象**：5 段视频在拼接处存在明显的渐变过渡，用户要求直接拼接。

**根因分析**：`ImageBatchExtendWithOverlap` 节点使用 `linear_blend` 模式，`overlap=5`，在段间重叠区域进行线性混合，产生渐变效果。

**关键认知**：`ImageBatchExtendWithOverlap` 的 `overlap_mode` 参数控制段间拼接方式：
- `linear_blend`：线性混合重叠区域，产生渐变过渡
- `cut`：直接切换帧，无混合，硬切拼接

**修复方案**：`overlap_mode` 从 `linear_blend` 改为 `cut`，`overlap` 从 5 降至 1。

**参数配置**：

| 参数 | 修复前 | 修复后 | 物理意义 |
|------|--------|--------|---------|
| `overlap` | 5 | 1 | 重叠帧数（节点最小值为 1，不支持 0） |
| `overlap_side` | `new_images` | `new_images` | 重叠侧选择新段图像 |
| `overlap_mode` | `linear_blend` | `cut` | 拼接模式：线性混合 → 直接切换 |

**overlap_mode 梯度分析**：

| overlap_mode | 效果 | 适用场景 | 帧数损失 |
|-------------|------|---------|---------|
| `linear_blend` | 渐变过渡，段间平滑融合 | 自然场景、动作连续 | overlap 帧 |
| `cut` | 硬切拼接，无过渡 | 动作突变、用户要求直接拼接 | overlap-1 帧 |
| `fade` | 淡入淡出，黑场过渡 | 场景切换、章节分隔 | overlap 帧 |

**关键禁忌**：
- `overlap=0` 不被节点支持（最小值为 1），但 `overlap=1` + `cut` 模式实际无混合帧，等同于直接拼接
- 长视频分段拼接时，`overlap` 值过高会损失过多帧数（5 段 × overlap 5 = 损失 20 帧）

### 24.6 阶段五：手部变形与多余肢体修复

#### 24.6.1 生成视频中人物手部变形、背景发红、多余肢体

**现象**：C8 阶段遗留问题，生成视频中人物手部变形、背景发红、出现多余肢体（两臂变四臂）。

**根因分析**：SVI Pro 提示词缺乏对手部结构和色偏的显式约束，Wan2.2 模型在手部生成上存在固有缺陷。

**修复方案**（提示词增强）：

**SVI Pro 正向提示词追加**：
```
人物双手结构完整，十指分明，两臂两腿，肢体自然协调
```

**SVI Pro 负向提示词追加**：
```
背景发红，红色色偏，多余的手指，手指融合，多臂，多余手臂，三头六臂，肢体残缺，手部变形，手指扭曲，关节反向，手掌融合
```

**Flux2 正向提示词追加**：
```
修复手部结构确保十指完整分明关节自然，确保仅有两臂两腿无多余肢体；消除红色色偏禁止背景发红
```

**Flux2 负向提示词追加**：
```
多手指，六指，手指扭曲，关节反向，手掌融合，手部变形，手指残缺；多余肢体，多臂，多余手臂，三头六臂，手臂残影，肢体残缺，肢体穿模，四肢扭曲；背景发红，红色色偏
```

**手部/肢体修复提示词原则**：
- 正向约束指定正确结构（"十指分明，两臂两腿"），负向约束禁止错误结构（"多手指，三头六臂"）
- Flux2 修正提示词需同时包含"修复正确结构"和"禁止错误结构"双向约束
- 肢体约束需明确数量（"两臂两腿"），避免模型生成中间状态

### 24.7 提示词工程深度指南（Wan2.2 视频生成专用）

> **本节目的**：基于 Wan2.2 官方提示词教程、多镜头设计方法论、AI 视频运镜术语体系，系统化梳理视频生成提示词的编写方法。前述 24.3-24.6 节中的提示词示例均为针对特定问题修复的**简单示例**，本节提供完整的结构化提示词编写方法论，覆盖人物外貌、场景物品、动作控制、镜头设计、关系描写五大维度。

#### 24.7.1 Wan2.2 提示词公式体系

Wan2.2 原生支持中文提示词理解，无需翻译为英文。根据任务类型选择对应公式：

**文生视频公式**（T2V，从零生成）：
```
提示词 = 主体（主体描述）+ 场景（场景描述）+ 运动（运动描述）+ 美学控制 + 风格化
```

**图生视频公式**（I2V，基于参考图生成）：
```
提示词 = 运动 + 运镜
```
图生视频时，图像已确定主体、场景与风格，提示词主要描述动态过程及镜头运动。

**多镜头公式**（分段长视频）：
```
提示词 = [场景描述], [镜头1描述](时长), [镜头2描述](时长), [转场效果], [整体风格要求]
```

**运镜万能公式**（适用于所有视频类型）：
```
提示词 = 景别 + 运镜动作 + 速度方向 + 主体动作 + 环境细节 + 光影氛围
```

**分层写作法**（Wan2.2 实测最稳定的方法论，源自 SDXL Prompt 风格实操）：

Wan2.2 的理解力高度依赖语言结构，它不像聊天模型能兜底推理，而更像一位经验丰富的导演——指令越清晰、越有层次，生成越精准。分层写作法把混沌的一句话提示，拆解成三个可独立控制、又能协同发力的模块。三层之间不是并列关系，而是有**主次、有逻辑、有视觉优先级**的组合。

| 层级 | 核心问题 | 写作要求 | 错误示范 | 正确写法 |
|------|---------|---------|---------|---------|
| **第一层（主体）** | 谁/什么在动？ | 必须唯一、具体、带基础动作的主谓结构短语 | "一只猫"、"橘猫" | "一只蹲坐的橘猫，缓慢转头看向镜头" |
| **第二层（场景）** | 它在哪？ | 单一空间+基础光照+简洁元素，不喧宾夺主 | "花园里有蝴蝶、蒲公英、喷泉、长椅" | "浅焦虚化的日式庭院，午后柔和侧光" |
| **第三层（风格）** | 它看起来像什么？ | 单一主导风格+1个强化项，不混搭 | "胶片颗粒+赛博朋克+水墨风+8K超高清" | "电影胶片质感，24fps胶片扫描噪点" |

**分层写作核心原则**：
1. **视觉阅读顺序**：模型按"主体→场景→风格"顺序解析，第一层决定焦点，第二层提供舞台，第三层统一基调
2. **分隔规则**：三层之间用**英文逗号**隔开，**不加"和""与""以及"等连接词**（模型不解析语法，只识别关键词块）
3. **主体层动作动词**：选"缓慢""轻柔""平稳""匀速"，避免"狂奔""爆炸""瞬间"等 Wan2.2 难以建模的强动态
4. **场景层光线词优先**："柔光""侧光""逆光"比装饰词重要，直接决定画面明暗节奏；用"浅焦虚化""纯白""单色墙"主动弱化背景干扰
5. **风格层单一主导**：优先"设备+效果"组合（如"iPhone 15 Pro实拍""佳能EOS R5"），比抽象词更稳定
6. **中文四字短语优势**：Wan2.2 对中文四字短语（如"回眸一笑""振翅欲飞""垂眸浅笑"）做了 token 对齐优化，触发准确率比英文短语高 35%

**分层前后对比示例**（主题：雨中撑伞的女生）：

❌ **未分层（失败提示词）**：
```
一个漂亮的中国女孩，穿着白色连衣裙，打着透明雨伞，站在雨中，雨水滴落，霓虹灯闪烁，城市街道，赛博朋克，高清，电影感，广角镜头
```
→ 生成结果：女孩脸模糊、雨丝断续、霓虹光斑吞噬伞沿、画面抖动严重（模型把所有词平权处理，猫毛细节和蝴蝶翅膀抢焦点）

✅ **分层后（稳定可用）**：
```
穿白裙的年轻女子，一手轻握透明伞柄，微微仰头感受雨滴, 现代都市人行道，细密雨丝斜向飘落，湿滑柏油路面反光, iPhone 15 Pro雨天模式实拍，冷调氛围，雨滴微距特写感
```
→ 生成结果：人物姿态清晰、雨丝方向一致、路面反光自然、整体色调统一偏蓝灰（模型按顺序执行：先确定"谁在做什么"，再布置"在哪发生"，最后统一"用什么方式呈现"）

#### 24.7.2 人物外貌描写维度

> **本节内容为详细指南**，前述 24.6 节手部修复提示词仅为简单示例。

人物外貌描写需覆盖以下 8 个维度，每个维度提供梯度化描述词：

**维度 1：面部五官**

| 细分维度 | 描述词示例 | 物理意义 | 使用场景 |
|---------|-----------|---------|---------|
| 脸型 | 鹅蛋脸、瓜子脸、圆脸、方脸、心形脸 | 面部轮廓形状 | 人物辨识度锚定 |
| 眉毛 | 柳叶眉、剑眉、一字眉、弯月眉、剑眉星目 | 眉毛形状与气质 | 气质塑造 |
| 眼睛 | 杏眼、桃花眼、丹凤眼、深邃蓝眼、琥珀色瞳孔 | 眼睛形状与颜色 | 情绪表达核心 |
| 鼻子 | 高挺鼻梁、小巧鼻头、希腊鼻、鹰钩鼻 | 鼻部轮廓 | 侧脸角度重要 |
| 嘴唇 | 樱桃小嘴、丰润红唇、薄唇、M字唇 | 嘴唇形状与厚度 | 表情与气质 |
| 皮肤质感 | 白皙透亮、健康麦色、细腻毛孔、雀斑肌、古铜色 | 肤色与质感 | 真实感关键 |

**描写示例**：
```
一位年轻女性，鹅蛋脸型，柳叶眉下是一双桃花眼，瞳孔呈琥珀色，高挺鼻梁，樱桃小嘴，白皙透亮的皮肤上可见细腻毛孔
```

**维度 2：发型发色**

| 细分维度 | 描述词示例 | 物理意义 |
|---------|-----------|---------|
| 长度 | 齐耳短发、齐肩中发、及腰长发、超长发 | 发长视觉比例 |
| 质感 | 柔顺直发、蓬松卷发、波浪大卷、麻花辫、高马尾 | 发型结构 |
| 颜色 | 乌黑、栗棕、亚麻金、银白、挑染 | 发色色温 |
| 光泽 | 哑光、丝缎光泽、阳光下泛金光 | 光线交互 |

**描写示例**：
```
乌黑及腰长发编成松散麻花辫垂于右肩，几缕碎发垂落在耳侧，发丝在阳光下泛着丝缎光泽
```

**维度 3：服装服饰**

| 细分维度 | 描述词示例 | 物理意义 |
|---------|-----------|---------|
| 款式 | 碎花连衣裙、汉服襦裙、西装三件套、运动套装 | 服装类型 |
| 材质 | 丝绸、棉麻、皮革、蕾丝、针织、雪纺 | 面料质感 |
| 颜色 | 米白色、藏青色、复古红、莫兰迪粉、大地色系 | 服装色彩 |
| 配饰 | 珍珠耳环、银质项链、复古胸针、贝雷帽、丝巾 | 点缀饰品 |
| 细节 | 蕾丝花边、刺绣纹样、金属纽扣、褶皱设计 | 工艺细节 |

**描写示例**：
```
身着米白色丝绸连衣裙，领口点缀精致蕾丝花边，腰间系一条浅棕色皮带，脚穿裸色高跟鞋，耳垂悬挂珍珠耳环，左手腕佩戴银质细链手表
```

**维度 4：体态身形**

| 细分维度 | 描述词示例 | 物理意义 |
|---------|-----------|---------|
| 身高 | 娇小玲珑、中等身材、高挑修长 | 视觉比例 |
| 体型 | 纤细、匀称、丰满、健美 | 身体轮廓 |
| 姿态 | 挺拔端庄、慵懒倚靠、优雅站姿 | 静态气质 |
| 动作习惯 | 轻抚发丝、托腮思考、双手交叠 | 习惯性小动作 |

**维度 5：年龄气质**

| 细分维度 | 描述词示例 | 物理意义 |
|---------|-----------|---------|
| 年龄感 | 十一二岁少女、二十出头青年、三十而立、暮年长者 | 年龄锚定 |
| 气质 | 清纯可爱、知性优雅、冷艳高贵、温婉贤淑 | 整体氛围 |
| 表情 | 浅笑盈盈、眉眼弯弯、若有所思、嘴角上扬 | 情绪状态 |

**跨维度综合描写示例**（将 8 个维度融合为完整段落，按气质类型分类）：

> 以下示例展示如何把表格词库组合成有叙事感的描写段落，而非词罗列。

**示例 1：知性优雅型**（融合面部/发型/服装/体态/年龄气质）：
```
一位三十岁出头的知性女子，鹅蛋脸型，柳叶眉下是一双深邃的桃花眼，瞳孔呈琥珀色，高挺鼻梁，丰润红唇微抿，白皙透亮的皮肤上可见细腻毛孔。乌黑齐肩中发柔顺垂落，几缕碎发垂在耳侧，发丝在光线下泛着丝缎光泽。她身着藏青色西装三件套，领口点缀银质胸针，腕戴细链手表，挺拔端庄地站在落地窗前，眉眼弯弯，嘴角带着若有若无的浅笑
```

**示例 2：清纯可爱型**：
```
一位十一二岁的少女，圆润的脸庞配弯月眉，杏眼清澈明亮，小巧鼻头，樱桃小嘴，健康麦色皮肤透着青春光泽。栗棕色齐耳短发扎成双麻花辫，辫尾系着米色丝带。她穿着碎花棉质连衣裙，脚踩白色帆布鞋，脖颈挂着一颗珍珠吊坠，娇小玲珑的身形微微前倾，双手背在身后，脸上洋溢着天真烂漫的笑容
```

**示例 3：冷艳高贵型**：
```
一位二十出头的年轻女子，心形脸配剑眉星目，丹凤眼眸色深邃，希腊鼻挺拔，薄唇紧抿，白皙冷调皮肤如瓷器般光洁。银白色及腰长发烫成大波浪，垂落于右肩，哑光质感衬得发色如月光。她身着黑色丝绸长裙配蕾丝手套，耳垂悬挂水滴形钻石耳环，高挑修长的身形优雅侧立，单手轻抚发丝，神情冷艳而疏离
```

**综合描写编写要点**：
- **从整体到细节**：先年龄气质（定性），再面部（辨识度），再发型服装（风格化），最后体态表情（动态感）
- **避免词罗列**：用"配""系着""悬挂""戴着"等动词连接配饰，而非"有珍珠耳环+有项链+有手表"
- **气质统一性**：知性优雅型不可配"夸张大笑"，冷艳高贵型不可配"碎花裙+帆布鞋"，所有维度需服务于同一气质基调
- **动态暗示**：在静态描写中埋入动作伏笔（"微微前倾""单手轻抚发丝""背在身后"），为后续动作描写铺垫

#### 24.7.3 场景与物品描写维度

> **本节内容为详细指南**，前述章节中的场景描述仅为简单示例。

场景描写需覆盖以下 6 个维度：

**维度 1：场景类型**

| 类型 | 描述词示例 | 物理意义 |
|------|-----------|---------|
| 自然场景 | 田野、森林、海滩、雪山、草原、峡谷 | 自然环境 |
| 室内场景 | 复古咖啡馆、现代办公室、日式榻榻米、欧式书房 | 室内空间 |
| 城市场景 | 繁华街道、霓虹夜市、老城胡同、摩天大楼顶层 | 城市景观 |
| 虚构场景 | 赛博朋克都市、废土遗迹、奇幻城堡、太空站 | 想象空间 |

**维度 2：时间段与光线**

| 时间段 | 光线描述词示例 | 光线特征 |
|--------|--------------|---------|
| 黎明 | 晨曦微露、天际泛白、薄雾笼罩 | 冷色调，低对比度 |
| 日出 | 金色阳光、霞光万丈、暖色调 | 暖色调，边缘光 |
| 白天 | 明亮日光、晴空万里、阳光直射 | 高对比度，硬光 |
| 黄昏 | 夕阳西下、余晖洒落、暖橘色调 | 暖色调，侧光，长影 |
| 日落 | 晚霞绚烂、天际渐暗、紫红色调 | 混合色调，边缘光 |
| 夜晚 | 月光皎洁、星光点点、城市霓虹 | 冷色调，实用光 |
| 阴天 | 漫射光、低对比度、灰蓝色调 | 柔光，低饱和度 |

**维度 3：光源类型**

| 光源 | 描述词示例 | 适用场景 |
|------|-----------|---------|
| 日光 | 晴天光、阳光透过树叶、斑驳光影 | 户外白天 |
| 月光 | 月光斜射、银白月光、月光下的剪影 | 夜晚户外 |
| 人工光 | 台灯、吊灯、霓虹灯、路灯 | 室内或城市夜景 |
| 火光 | 壁炉火光、篝火、烛光 | 温暖氛围 |
| 荧光 | 紫外线灯、荧光灯管、赛博朋克霓虹 | 科技感场景 |
| 混合光 | 日光+人工光、火光+月光 | 复杂光线环境 |

**维度 4：光线质感**

| 光线类型 | 描述词示例 | 视觉效果 |
|---------|-----------|---------|
| 柔光 | 柔和光线、漫射光、无强烈阴影 | 温柔、自然 |
| 硬光 | 强烈直射光、锐利阴影、高对比度 | 戏剧性、力量感 |
| 边缘光 | 轮廓光、发丝边缘泛光、逆光剪影 | 分离主体与背景 |
| 侧光 | 侧面打光、半边脸阴影、伦勃朗光 | 立体感、情绪 |
| 底光 | 仰角打光、诡异氛围、恐怖片光效 | 悬疑、不安 |
| 顶光 | 顶光照射、眼窝阴影、舞台聚光 | 戏剧性、神圣感 |

**维度 5：场景物品**

物品描写需明确其与人物的空间关系：

| 关系类型 | 描写模板 | 示例 |
|---------|---------|------|
| 人物持有 | "手中拿着/提着/抱着" | 手中拿着一束向日葵 |
| 人物接触 | "指尖轻触/双手扶着/倚靠在" | 指尖轻触花瓣，双手扶着栏杆 |
| 人物周围 | "身旁/身后/脚下/头顶" | 身后是一面斑驳的砖墙，脚下是铺满落叶的小径 |
| 环境装饰 | "背景中/远处/画面边缘" | 背景中隐约可见复古路灯，远处是连绵山峦 |
| 互动关系 | "正在使用/正在观察/正在靠近" | 正在使用相机拍摄，正在观察橱窗内的展品 |

**维度 6：环境氛围**

| 氛围类型 | 描述词示例 | 适用场景 |
|---------|-----------|---------|
| 温馨 | 温暖、舒适、宁静、家庭感 | 日常生活、亲情场景 |
| 神秘 | 幽暗、深邃、未知、悬念 | 悬疑、探险 |
| 史诗 | 宏大、壮阔、史诗感、电影级 | 大片、战争 |
| 文艺 | 复古、怀旧、诗意、文艺感 | 文艺片、回忆 |
| 科技 | 未来感、赛博朋克、霓虹、全息 | 科幻、未来 |

**场景层稳定框架原则**（源自分层写作法，场景层必须提供"不抢戏的舞台"）：

场景不是背景描述，而是**锚定空间关系与光线基调的稳定框架**。它要让主体"站得住、看得清、不飘"。

| 原则 | 错误示范 | 正确写法 | 原因 |
|------|---------|---------|------|
| 单一空间 | "花园+咖啡馆+街道" | "浅焦虚化的日式庭院" | 多空间并列导致模型注意力分散，主体边缘模糊 |
| 基础光照优先 | "霓虹灯+喷泉+鸽子+长椅" | "午后柔和侧光" | 装饰词抢戏，光线词决定明暗节奏 |
| 主动弱化背景 | "繁华街道，人来人往" | "纯白摄影棚，均匀柔光箱照明" | 动态干扰源（瀑布/喷泉/车流）导致主体抖动 |
| 简洁元素 | "桌上有杯子+花瓶+书本+台灯+时钟" | "老上海石库门弄堂口，青砖墙面微反光" | 多物体并列，模型平均分配注意力 |

**场景描写综合示例**（融合 6 个维度，按场景类型分类）：

**示例 1：自然场景·清晨田野**（类型+时间+光源+光线+物品+氛围）：
```
清晨的田野，晨曦微露，天际泛白，薄雾笼罩在稻穗上。日光从东方斜射，形成柔和的侧光，露珠在稻叶上泛着金边。一位少女站在田埂上，身旁是齐腰高的稻穗，脚下是湿润的泥土小径。远处是连绵的青山，几只白鹭掠过水面。整体氛围宁静而充满生机，暖色调的低对比度画面
```

**示例 2：室内场景·复古咖啡馆**：
```
黄昏时分的复古咖啡馆，夕阳透过落地窗斜射进来，形成暖橘色的边缘光。人工光源来自角落的铜质吊灯，散发着昏黄暖光。吧台上整齐摆放着铜质咖啡机、几只白瓷杯和一罐白糖，空气中弥漫着咖啡香气。皮质沙发上散落着几本翻开的旧书，窗外的雨幕模糊了街景。整体氛围温馨怀旧，暖色调，柔光
```

**示例 3：城市场景·雨夜霓虹**：
```
夜晚的繁华街道，霓虹灯闪烁着蓝紫色光芒，雨水打湿的柏油路面反射出斑斓光轨。人工光与霓虹光混合，形成高对比度的硬光。街边停着一辆黄色出租车，橱窗里透出暖黄灯光，远处是模糊的摩天大楼剪影。冷色调的赛博朋克氛围，雨丝斜向飘落，路面水洼倒映着霓虹
```

**示例 4：虚构场景·废土遗迹**：
```
末日废土的废弃城市，阴天漫射光笼罩，灰蓝色调的低饱和度画面。残破的高楼被藤蔓覆盖，锈蚀的钢筋从混凝土中裸露，地面上散落着碎石和锈铁罐。一缕阳光穿过云层缝隙，斜射在广场中央的倒塌雕塑上，形成戏剧性的顶光。整体氛围荒凉而神秘，冷色调，低对比度
```

#### 24.7.4 动作控制描写维度

> **本节内容为详细指南**，前述 24.3-24.5 节中的动作描述仅为简单示例。

动作描写需覆盖以下 5 个维度：

**维度 1：动作幅度**

| 幅度等级 | 描述词示例 | 适用场景 | Wan2.2 表现 |
|---------|-----------|---------|-----------|
| 静止 | 静止不动、保持姿势、凝视远方 | 肖像、特写 | 最稳定 |
| 微动作 | 轻微转头、眨眼、嘴角上扬、发丝飘动 | 情绪表达 | 稳定 |
| 小幅度 | 缓慢转身、轻抚发丝、抬手整理衣物 | 日常场景 | 稳定 |
| 中幅度 | 行走、坐下、挥手、弯腰、转身 | 常规动作 | 较稳定 |
| 大幅度 | 奔跑、跳跃、旋转、舞蹈、搏击 | 运动场景 | 易变形，需多段生成 |
| 剧烈 | 快速翻滚、激烈打斗、极限运动 | 动作戏 | 不推荐单次生成，分段处理 |

**维度 2：动作速率**

| 速率 | 描述词示例 | 视觉效果 |
|------|-----------|---------|
| 极慢 | 缓缓、缓慢地、几乎察觉不到 | 诗意、文艺 |
| 慢速 | 慢慢地、不紧不慢 | 自然、日常 |
| 中速 | 平稳地、从容地 | 正常节奏 |
| 快速 | 迅速、敏捷、利落 | 紧凑、活力 |
| 极快 | 猛然、瞬间、疾速 | 冲击力、戏剧性 |

**维度 3：动作连贯性**

| 连贯类型 | 描写模板 | 示例 |
|---------|---------|------|
| 单一动作 | "主语 + 动词 + 宾语" | 少女抬头望向天空 |
| 连续动作 | "先...然后...接着...最后" | 先低头整理裙摆，然后抬头微笑，接着转身走向窗边 |
| 循环动作 | "持续地、不断重复" | 持续地翻动书页，不断重复编织动作 |
| 过渡动作 | "从A状态过渡到B状态" | 从坐姿优雅地起身，过渡到站立姿态 |

**维度 4：多人物动作关系**

| 关系类型 | 描写模板 | 示例 |
|---------|---------|------|
| 同步动作 | "两人同时/并肩" | 两人同时转身，并肩走向远方 |
| 互动动作 | "A向B做某动作，B回应" | 男孩向女孩伸出手，女孩微笑着将手放上 |
| 对抗动作 | "A对抗B/互相拉扯" | 两人双手交握，互相用力拉扯 |
| 配合动作 | "A负责...B负责...配合完成" | 一人负责撑伞，另一人负责提裙摆，配合穿越雨中 |
| 独立动作 | "A做某事，同时B做另一件事" | 母亲在厨房切菜，孩子在客厅玩积木 |

**维度 5：动作与镜头配合**

| 配合类型 | 描写模板 | 示例 |
|---------|---------|------|
| 镜头跟随 | "镜头跟随主体做某动作" | 镜头跟随少女穿过花海，始终保持中景构图 |
| 镜头领先 | "镜头先于主体到达某位置" | 镜头先到达终点，等待奔跑者冲入画面 |
| 镜头环绕 | "镜头环绕主体，主体做某动作" | 镜头360度环绕，主角站在原地释放能量 |
| 镜头固定 | "镜头固定，主体在画面内活动" | 镜头固定，舞者在画面中央完成一段独舞 |

**动作描写进阶技巧**（源自 Wan2.2 实战经验，解决动作不连贯、多人互动失败、首尾帧卡顿）：

**技巧 1：时间逻辑词暗示运动节奏**

Wan2.2 把"持续""缓缓""旋转着""被吹向"等词解析为帧间变化的关键锚点。抽象形容词（活泼、美丽、震撼）不触发动作建模，必须用带时间轴的动词短语。

| ❌ 抽象描述 | ✅ 时间逻辑描述 | 触发效果 |
|-----------|--------------|---------|
| "风吹动树叶" | "微风持续吹过，银杏叶从枝头缓缓飘落，一片叶子旋转着下坠，另一片被吹向镜头" | 自带时间轴和空间关系，生成连贯物理运动 |
| "小狗很活泼" | "小狗原地跳跃三次，耳朵上下抖动，舌头伸出来喘气" | "跳跃""抖动""伸舌头"成为帧间变化锚点 |
| "咖啡师在制作咖啡" | "咖啡师将奶泡缓缓注入浓缩咖啡，拉花图案逐渐成型，蒸汽从杯口螺旋上升" | "缓缓注入""逐渐成型""螺旋上升"激活时间维度建模 |

**技巧 2：多人物场景改用分镜式描述**

Wan2.2 对多人交互的空间约束建模尚不完善，直接写"两位朋友击掌"会导致只有一人或动作错位。解法是**改用分镜式描述**，聚焦局部动作，规避全身姿态建模难点。

| ❌ 全身描述（易失败） | ✅ 分镜式局部描述 | 原理 |
|-------------------|----------------|------|
| "两位朋友击掌" | "特写：两只手从画面两侧伸入，击掌瞬间，掌心相触，汗珠飞溅" | 聚焦手部局部，规避全身姿态建模 |
| "情侣拥抱" | "中景：男子伸出手臂环绕女子肩头，女子侧头靠向男子胸膛" | 分解为两个独立动作，降低交互复杂度 |
| "两人对打" | "近景：拳头从右侧挥入，击中左侧人物面颊，头部向左偏转" | 聚焦击打瞬间，避免全身搏斗建模 |

**技巧 3：首尾帧稳定性增强**

Wan2.2 采用隐式扩散建模，首尾帧稳定性弱于中间帧，易出现前 0.5 秒画面冻结或最后半秒突然跳变。在提示词末尾追加稳定性约束可显著改善。

```
（原提示词）... ，动作起始自然，结束平稳，无突兀跳变
```

**技巧 4：单一动态焦点原则**

视频生成需分配计算资源给每个运动对象，主体越少，动作越细腻。Wan2.2 在单主体 3 秒视频中能还原布料褶皱形变、光影移动轨迹等微观动态，多主体场景难以兼顾。

| ❌ 多主体并列 | ✅ 单一焦点+虚化背景 | 效果 |
|------------|-------------------|------|
| "公园里有老人打太极、孩子放风筝、情侣拍照、鸽子飞过" | "一位穿灰布衫的老人缓慢推掌，衣袖随动作鼓起，背景虚化，晨光勾勒手臂轮廓" | 布料褶皱、光影轨迹等微观动态得以还原 |

#### 24.7.5 镜头设计完整术语库

> **本节内容为详细指南**，前述章节中的镜头描述仅为简单示例。

**景别术语**（控制人物在画面中的占比）：

| 景别 | 英文缩写 | 人物占比 | 描述词 | 适用场景 |
|------|---------|---------|--------|---------|
| 大远景 | ELS | 极小 | 大远景、超广角全景 | 展现宏大环境、定场镜头 |
| 远景 | LS | 较小 | 远景、全景环境 | 人物与环境关系 |
| 全景 | WS | 全身 | 全景、全身景 | 展现完整身形与动作 |
| 中景 | MS | 腰部以上 | 中景、半身景 | 日常对话、动作 |
| 中近景 | MCU | 胸部以上 | 中近景、近半身 | 情绪表达、对话 |
| 近景 | CU | 肩膀以上 | 近景、胸部以上 | 面部表情、细节 |
| 特写 | BCU | 面部 | 面部特写、大特写 | 情绪强化、细节 |
| 极特写 | ECU | 局部 | 极特写、眼部特写 | 极致细节、冲击力 |

**机位角度术语**：

| 角度 | 描述词 | 视觉效果 | 适用场景 |
|------|--------|---------|---------|
| 平拍 | 平拍、平视角度 | 自然、客观 | 日常场景、对话 |
| 仰拍 | 仰拍、低角度拍摄 | 伟岸、压迫、权威感 | 英雄登场、反派 |
| 俯拍 | 俯拍、高角度拍摄 | 渺小、无助、全貌 | 环境展示、弱势 |
| 鸟瞰 | 鸟瞰、俯瞰、航拍 | 宏大、地理关系 | 城市宣传片、战争 |
| 过肩 | 过肩镜头、越肩 | 对话感、参与感 | 双人对话 |
| 主观 | 第一人称视角、主观镜头 | 沉浸感、代入感 | 游戏、探险 |

**运镜动作术语**（18 种专业运镜）：

**第一类：聚焦情绪（3种）**

| 编号 | 名称 | 运镜描述 | 完整提示词示例 |
|------|------|---------|--------------|
| 01 | 情绪推进镜头 | 远景→中景→面部特写，镜头持续向前推进 | 镜头从远景开始，摄像机缓慢向前推进，逐渐靠近站在古桥上的年轻剑客。画面从全景过渡到中景，最终停留在面部特写。雨水划过脸颊，远处灯火在雨幕中晕染开来，电影级情绪光影 |
| 02 | 真相揭示镜头 | 特写→中景→全景，镜头向后拉远 | 镜头从泛黄照片特写开始，摄像机缓慢向后拉远。逐渐露出女孩身影，最终展现被废弃的未来城市。残破高楼与荒草覆盖街道形成强烈反差 |
| 03 | 视线探索镜头 | 超广角全景，镜头水平从左向右移动 | 镜头从山谷左侧缓慢移动至右侧。画面依次经过瀑布、森林和未来城市。飞行器穿过晨雾，阳光从云层间洒落 |

**第二类：制造运动感（3种）**

| 编号 | 名称 | 运镜描述 | 完整提示词示例 |
|------|------|---------|--------------|
| 04 | 平行追踪镜头 | 侧面中景，镜头与主体平行移动 | 摄像机从侧面同步跟随高速骑行的机车骑士。主体始终位于画面中央，背景霓虹灯形成横向光轨，展现极强速度感 |
| 05 | 沉浸跟随镜头 | 背面跟拍，镜头持续跟随主体 | 摄像机位于主角身后持续跟拍。主角快速穿过拥挤市场，两侧摊位和人群不断后退，形成强烈沉浸式追逐体验 |
| 06 | 空间升维镜头 | 近景→鸟瞰全景，镜头持续升高 | 镜头从广场中央开始缓慢升空。随着高度不断增加，整座未来都市逐渐展现在画面中，巨型建筑群延伸至地平线 |

**第三类：电影感最强（3种）**

| 编号 | 名称 | 运镜描述 | 完整提示词示例 |
|------|------|---------|--------------|
| 07 | 主角高光镜头 | 中景，镜头360度环绕主体旋转 | 摄像机围绕角色进行360度平滑环绕。能量粒子围绕身体流动，背景光效不断变化，营造主角登场的史诗感 |
| 08 | 压迫变焦镜头 | 全身景，镜头后退同时变焦推进 | 摄像机缓慢后退，同时镜头持续变焦推进。角色始终保持相同大小，背景山谷被不断拉伸压缩，营造强烈不安感 |
| 09 | 焦点转移镜头 | 双人近景，镜头固定，焦点平滑转移 | 镜头保持固定。开始时背景人物清晰，前景人物虚化。随后焦点缓慢转移至前景角色，引导观众关注剧情变化 |

**第四类：大片专属（3种）**

| 编号 | 名称 | 运镜描述 | 完整提示词示例 |
|------|------|---------|--------------|
| 10 | 鹰眼俯冲镜头 | 超高空鸟瞰→中景→广角全景 | 镜头从高空鸟瞰开始。无人机快速向下俯冲，贴近河面高速飞行，跟随飞行摩托穿越峡谷。随后镜头迅速拉升至高空，全景展示壮阔山脉与河流地貌 |
| 11 | 第一视角镜头 | 第一人称主观视角，自然晃动 | 第一人称视角。镜头模拟角色双眼所看到的画面，随着脚步产生轻微上下起伏。角色穿过废弃实验室，双手偶尔进入画面 |
| 12 | 一镜到底镜头 | 远中近连续变化，组合运镜无剪辑 | 单一连续镜头。摄像机跟随主角穿过走廊、下楼梯、跃过障碍物、穿越大厅并进入电梯。镜头连续完成推进、跟拍和转向动作，全程无任何剪辑切换 |

**第五类：风格化镜头（6种）**

| 编号 | 名称 | 运镜描述 | 适用场景 |
|------|------|---------|---------|
| 13 | 纪录片镜头 | 模拟手持摄影，轻微抖动 | 纪录片、战争、写实风格 |
| 14 | 惊讶强化镜头 | 快速变焦推进再恢复 | 喜剧、悬疑、反转时刻 |
| 15 | 对峙观察镜头 | 过肩中景，缓慢平移 | 审讯、谈判、对话 |
| 16 | 极速追踪镜头 | 侧面中景，横向同步跟拍 | 体育竞技、追逐戏 |
| 17 | 失控眩晕镜头 | 第一人称，不规律晃动旋转 | 受伤、醉酒、惊恐 |
| 18 | 空间错位镜头 | 双人中景，跨越空间轴线 | 悬疑、心理惊悚 |

**Wan2.2 运镜禁忌词**（会导致画面混乱）：

| 禁忌词 | 原因 | 替代方案 |
|--------|------|---------|
| 360 orbit | 触发相机持续旋转，画面混乱 | "镜头缓慢环绕"或"固定镜头" |
| camera spin | 同上，相机自旋 | "镜头平滑转向" |
| rotating shot | 旋转镜头导致主体变形 | "镜头弧形移动" |
| dolly zoom | 模型难以模拟变焦效果 | "镜头推进"或"镜头拉远" |

#### 24.7.6 人物-场景-物品关系描写方法论

> **本节内容为详细指南**，前述章节未涉及关系描写，本节为完整方法论。

关系描写是提示词质量的核心区分点。初学者只描述"有什么"，专业提示词描述"之间有什么关系"。

**关系描写的 5 个层次**：

**层次 1：空间关系**（人物在场景中的位置）

| 描写模板 | 示例 |
|---------|------|
| 人物位于场景的[方位] | 少女站在画面的右侧三分之一处 |
| 人物与物体的距离 | 少女距离复古路灯约两步远 |
| 人物的朝向 | 少女面朝镜头，背对繁华街道 |
| 人物的相对高度 | 少女站在台阶上方，俯视镜头 |

**层次 2：互动关系**（人物与物品的物理交互）

| 描写模板 | 示例 |
|---------|------|
| [身体部位] + [动作] + [物品] | 右手轻轻抚弄裙摆，左手提着藤编篮子 |
| 人物 + [使用方式] + [物品] | 少女正用画笔在画布上勾勒轮廓 |
| 物品 + [状态] + [人物] | 微风吹起少女的裙摆，几片落叶停在她的肩头 |
| 人物 + [接触程度] + [环境] | 赤脚踩在温热的沙滩上，脚趾陷入细沙 |

**层次 3：情感关系**（人物对场景/物品的情感投射）

| 描写模板 | 示例 |
|---------|------|
| 人物 + [情感动词] + [对象] | 少女深情地凝望远处的灯塔 |
| 人物 + [情绪状态] + [因为] | 嘴角不自觉上扬，因为想起童年的夏日 |
| 环境 + [烘托] + [人物情绪] | 昏黄的灯光烘托出少女眼底的忧伤 |
| 物品 + [象征] + [人物心境] | 手中紧握的旧照片象征着对过去的眷恋 |

**层次 4：因果关系**（动作导致的环境变化）

| 描写模板 | 示例 |
|---------|------|
| 因为[动作]，所以[环境变化] | 因为少女快速转身，裙摆在空中划出优美的弧线 |
| [动作]导致[物品状态改变] | 轻轻吹气，蒲公英种子四散飘落 |
| [动作]引发[连锁反应] | 脚步惊起一群白鸽，扑棱棱飞向天空 |
| [环境因素]促使[人物动作] | 突如其来的细雨促使少女撑开油纸伞 |

**层次 5：多人物关系**（人物之间的互动）

| 关系类型 | 描写模板 | 示例 |
|---------|---------|------|
| 主从关系 | A引导B，B跟随A | 母亲牵着女儿的手，女儿亦步亦趋地跟随 |
| 对等关系 | A与B并排/面对面 | 两人面对面站立，双手相握 |
| 对抗关系 | A对抗B | 两人背靠背，警惕地环顾四周 |
| 阶层关系 | A高于B/低于B | 老师站在讲台上，俯视坐着的弟子 |
| 情感关系 | A对B表达[情感] | 少女依偎在恋人肩头，嘴角带着甜蜜微笑 |

**完整关系描写示例**（融合 5 个层次）：

> 以下 4 个示例覆盖不同场景类型，展示如何把空间/互动/情感/因果/多人物 5 个层次编织成有叙事感的描写段落。

**示例 1：室内场景·咖啡馆**（温情叙事）：
```
中近景，平拍镜头。一位身着米白色丝绸连衣裙的少女站在复古咖啡馆的落地窗前（空间关系），右手轻轻扶着窗框，左手握着一杯尚冒热气的拿铁（互动关系）。她微微侧头，目光温柔地望向窗外的雨幕，嘴角带着淡淡的惆怅（情感关系）。因为她的呼吸，玻璃窗上凝结出一小片雾气，模糊了外面的街景（因果关系）。她身后三步远的地方，一位戴贝雷帽的青年正坐在角落的皮质沙发上，安静地观察着她（多人物关系），桌上摊开的书本已许久未翻动一页。暖黄色的吊灯在两人之间投下柔和的光晕，将这一刻定格成一幅静谧的油画。
```

**示例 2：自然场景·田野**（人物与自然互动）：
```
远景，轻微仰拍。一位穿碎花裙的少女站在齐腰高的麦田中央（空间关系），双手轻抚过麦穗，指尖划过金黄的麦芒（互动关系）。她闭上眼，脸上洋溢着满足的微笑，仿佛在聆听大地的呼吸（情感关系）。因为她的手拂过，麦穗向两侧倒伏，惊起几只蚂蚱跃向远方（因果关系）。她身后五步远的田埂上，一位戴草帽的老农拄着锄头站立，目光慈祥地望向她（多人物关系）。夕阳从地平线斜射，将两人的影子拉长，交织在金色的麦浪上。
```

**示例 3：城市场景·雨夜街头**（人物与环境张力）：
```
中景，低角度仰拍。一位穿黑色风衣的男子站在雨夜的十字路口中央（空间关系），右手紧握着一把黑色雨伞的伞柄，左手插在风衣口袋里（互动关系）。他眉头紧锁，目光坚定地望向街道尽头，嘴角微微下撇，透出一丝决绝（情感关系）。因为雨势渐大，雨水顺着他风衣的下摆滴落，在地面积水中溅起细碎的水花（因果关系）。他左侧三米远的人行道上，一位撑红伞的女子快步走过，两人擦肩而过的瞬间，她的红伞被风吹翻，露出惊讶的面容（多人物关系）。霓虹灯牌的蓝紫色光芒映在湿滑的路面上，与两人的身影形成冷暖对比。
```

**示例 4：虚构场景·废土遗迹**（多人物协作）：
```
全景，平拍。一位身披破旧斗篷的少女站在倒塌的雕塑旁（空间关系），右手握着一柄锈迹斑斑的长剑，左手轻触着雕塑残存的石臂（互动关系）。她眼神警惕而坚毅，紧抿的嘴唇透露出面对未知的紧张与勇气（情感关系）。因为她的触碰，雕塑石臂上的尘土簌簌落下，在地面激起一小片烟尘（因果关系）。她身后两步远的断墙后，一位背箭囊的青年正半蹲着警戒，目光扫视四周废墟，手势示意她保持安静（多人物关系）。阴云缝隙中漏下一缕阳光，斜射在少女的剑刃上，泛起一道冷光，与周围的荒凉形成戏剧性对比。
```

**关系描写编写要点**：
- **5 层次不必全部出现**：根据场景需要选择 3-4 个层次即可，强行凑齐 5 层会显得臃肿
- **层次之间用因果串联**：空间关系→互动关系→情感关系→因果关系→多人物关系，形成叙事链
- **物品是关系的媒介**：通过"扶着窗框""握着拿铁""轻触石臂"等物品互动，把人物锚定在场景中
- **多人物关系明确空间位置**：必须说明"身后三步远""左侧三米远""身后两步远"，避免模型无法确定相对位置

#### 24.7.7 提示词编写完整流程

**Step 1：确定视频类型与公式**
- 文生视频（T2V）→ 使用完整公式：主体+场景+运动+美学+风格
- 图生视频（I2V）→ 使用简化公式：运动+运镜
- 多镜头长视频 → 使用分段公式：[场景]+[镜头1]+[镜头2]+[转场]+[风格]

**Step 2：按维度填充内容**
- 人物：8 个维度（面部/发型/服装/体态/年龄/气质/表情/配饰）
- 场景：6 个维度（类型/时间/光源/光线/物品/氛围）
- 动作：5 个维度（幅度/速率/连贯/多人关系/镜头配合）
- 镜头：景别+角度+运镜动作

**Step 3：描写关系**
- 从 5 个层次描写人物-场景-物品关系
- 空间关系 → 互动关系 → 情感关系 → 因果关系 → 多人物关系

**Step 4：添加美学控制**
- 光源类型、光线质感、时间段、色调
- 构图方式（中心构图、三分构图、对称构图、短边构图）

**Step 5：添加风格化**
- 整体风格（电影感、纪录片、赛博朋克、水墨风）
- 画质要求（4K、高清、低饱和度、高对比度）

**Step 6：验证与优化**
- 检查是否包含禁忌运镜词（360 orbit 等）
- 检查动作幅度是否超出模型能力（剧烈动作需分段）
- 检查人物/场景/物品关系是否完整
- 精简到合理长度（图生视频≤100字，文生视频≤200字）

**完整提示词实战案例**（从零编写，展示分层写作法 + 5 大维度 + 关系描写的综合应用）：

> 以下 5 个案例覆盖不同任务类型，每个案例均包含"失败提示词"与"优化提示词"对比，标注所用维度。

**案例 1：文生视频·咖啡馆场景**（分层前后对比，激活时间维度建模）：

❌ **失败提示词**（词堆砌，无层次）：
```
一家温馨的咖啡馆，木桌，拿铁，绿植
```
→ 生成结果：固定机位，桌面静物，无任何运动，像一张高清照片

✅ **优化提示词**（分层 + 时间逻辑词 + 关系描写）：
```
咖啡师将奶泡缓缓注入浓缩咖啡，拉花图案逐渐成型，蒸汽从杯口螺旋上升, 窗外阳光斜射在吧台木纹上，浅焦虚化的现代咖啡馆, iPhone 15 Pro实拍，暖色调，浅景深，动作起始自然结束平稳
```
→ 生成结果：3 秒内完整呈现注奶、拉花、升腾三阶段，蒸汽轨迹清晰，光影随角度微移
→ **应用维度**：分层写作法（主体+场景+风格）+ 时间逻辑词（缓缓/逐渐/螺旋上升）+ 场景层光线优先

**案例 2：文生视频·中国山水**（传统题材适配，东方美学权重）：

❌ **失败提示词**：
```
水墨江南，小桥流水，乌篷船
```
→ 生成结果：画面偏写实，缺乏水墨晕染感，船体僵硬

✅ **优化提示词**：
```
一艘乌篷船从桥洞缓缓驶出，船尾划开细碎水波, 宣纸质感背景，墨色由浓转淡晕染出远山，岸边柳枝随风轻摆, 宫崎骏手绘动画风格，柔和水彩边缘，水墨肌理
```
→ 生成结果：明显水墨肌理，船体运动带动水波扩散，柳枝摆动频率自然
→ **应用维度**：分层写作法 + 时间逻辑词（缓缓驶出/划开/轻摆）+ 风格层单一主导（手绘+水彩边缘）

**案例 3：图生视频·人物动作**（I2V 简化公式，运动+运镜）：

❌ **失败提示词**（描述过多，与图像信息冲突）：
```
一位穿着白色连衣裙的少女站在花园里，阳光明媚，她微笑着看向镜头，微风吹动她的裙摆和头发
```
→ 生成结果：图像已确定主体和场景，多余描述导致模型困惑，动作不自然

✅ **优化提示词**（I2V 公式，仅描述运动+运镜）：
```
少女缓慢转身，裙摆随之轻扬，镜头匀速推进至中近景，动作起始自然结束平稳
```
→ 生成结果：动作流畅自然，裙摆物理运动合理，镜头推进平稳
→ **应用维度**：图生视频公式（运动+运镜）+ 时间逻辑词（缓慢/匀速）+ 首尾帧稳定性约束

**案例 4：多镜头长视频·产品展示**（分段公式 + 转场）：

✅ **优化提示词**（多镜头分段 + 连贯性锚点）：
```
[纯白真无线耳机平放于哑光黑丝绒布，镜头缓慢环绕，指示灯规律闪烁蓝光](3秒), [镜头切至耳机充电仓开盖特写，金属触点反光](2秒), [手持耳机佩戴入耳特写，耳廓轮廓被柔和勾勒](3秒), [包装盒开启动画，耳机落入海绵凹槽](2秒), 流畅转场，纯白背景，iPhone 15 Pro实拍质感
```
→ 生成结果：360° 环绕运镜感强烈，指示灯明暗节奏准确，丝绒布反光随角度渐变
→ **应用维度**：多镜头公式（[镜头]+时长+转场）+ 连贯性锚点（纯白背景贯穿）+ 运镜万能公式（景别+运镜+速度+主体+环境+光影）

**案例 5：多人物互动·分镜式描述**（规避多人交互建模难点）：

❌ **失败提示词**（全身描述，多人交互）：
```
两位朋友在公园击掌庆祝，背景是喷泉和鸽子
```
→ 生成结果：只有一人，或击掌动作错位，背景喷泉导致主体抖动

✅ **优化提示词**（分镜式局部描述 + 单一动态焦点 + 场景弱化）：
```
特写：两只手从画面两侧伸入，击掌瞬间掌心相触，汗珠飞溅, 浅焦虚化的公园草坪，午后柔和侧光, iPhone 15 Pro实拍，动作起始自然结束平稳
```
→ 生成结果：击掌瞬间清晰，汗珠飞溅细节还原，背景虚化无干扰
→ **应用维度**：分镜式描述（聚焦局部）+ 单一动态焦点原则 + 场景层主动弱化背景 + 分层写作法

#### 24.7.8 提示词编写禁忌清单

| 禁忌 | 原因 | 正确做法 |
|------|------|---------|
| 使用英文提示词 | Wan2.2 原生支持中文，英文理解不如中文 | 使用中文提示词（Flux2 使用 qwen_3_8b 同样中文更优） |
| 提示词超过 300 字 | 模型注意力分散，关键信息被稀释 | 图生视频≤100字，文生视频≤200字 |
| 包含 "360 orbit" 等运镜词 | 触发相机持续旋转，画面混乱 | 使用"镜头缓慢环绕"或"固定镜头" |
| 仅描述"有什么"不描述"关系" | 画面元素堆砌，缺乏叙事性 | 按 24.7.6 节 5 个层次描写关系 |
| 动作描述过于剧烈 | Wan2.2 对剧烈动作支持差，易变形 | 大幅度动作分段生成，单段保持中小幅度 |
| 正负向提示词冲突 | 模型收到矛盾信号，效果不可控 | 正向指定目标，负向禁止偏离，不冲突 |
| 忽略景别描述 | 模型默认选择景别，可能不符合预期 | 明确指定景别（远景/中景/特写等） |
| 多人物未明确位置关系 | 模型无法确定人物相对位置，位置混乱 | 明确描述"左边...右边..."或"前景...背景..." |
| 场景物品无空间锚定 | 物品漂浮感，缺乏真实感 | 描述物品与人物/场景的空间关系 |
| 忽略时间段与光源 | 光线不确定，色调不稳定 | 明确时间段和光源类型（如"黄昏，侧光，暖色调"） |
| 词堆砌不分层 | 模型把所有词平权处理，主体与背景抢焦点，画面模糊抖动 | 按 24.7.1 节分层写作法：主体层+场景层+风格层，英文逗号分隔，不加连接词 |
| 主体层用名词而非主谓结构 | 模型无法锁定焦点，主体漂移 | 主体必须是"带动作的主谓结构短语"（"蹲坐的橘猫，缓慢转头"而非"一只猫"） |
| 场景层堆砌装饰词 | 装饰词抢戏，光线词缺失导致明暗节奏混乱 | 场景层光线词优先于装饰词，用"浅焦虚化""纯白"主动弱化背景 |
| 风格层混搭多种风格 | 逻辑冲突，模型无法统一视觉基调 | 风格层单一主导+1个强化项（"胶片+轻微褪色"而非"胶片+赛博朋克+水墨"） |
| 使用抽象形容词描述动作 | "活泼""美丽""震撼"不触发动作建模 | 用带时间轴的动词短语（"缓缓飘落""旋转着下坠""螺旋上升"） |
| 多人物直接写全身交互 | Wan2.2 多人交互空间约束建模不完善，人物消失或动作错位 | 改用分镜式局部描述（"特写：两只手从画面两侧伸入，击掌瞬间"） |
| 多主体并列分配注意力 | 计算资源分散，每个主体都粗糙 | 单一动态焦点原则，背景虚化（"一位老人缓慢推掌，背景虚化"） |
| 场景含动态干扰源 | 瀑布/喷泉/车流等强运动元素导致主体抖动 | 改为静态或远景（"瀑布远景""空旷街道"） |
| 忽略首尾帧稳定性 | 隐式扩散建模首尾帧弱，前 0.5 秒冻结或最后半秒跳变 | 提示词末尾追加"动作起始自然，结束平稳，无突兀跳变" |
| 风格术语与感官细节脱节 | "赛博朋克"太宽泛，模型响应不精准 | 用感官细节替代（"霓虹灯管在雨夜街道投下蓝紫色倒影，全息广告牌闪烁"） |

### 24.8 关键技术决策与参数选择

#### 24.8.1 Flux2 denoise=0.6 的平衡点选择

**决策背景**：Flux2 换皮需要平衡"外貌替换彻底性"与"动作保留度"。

**梯度测试结果**：
- `denoise=0.75`：换皮彻底，但动作结构被破坏，角色偏离原始截图动作
- `denoise=0.5`：动作保留度高，但换皮不彻底，部分外貌特征未替换
- `denoise=0.6`：平衡点，换皮充分（80%）且动作保留（70%）

**选择依据**：用户反馈"角色、画面、细节约束得到大幅提高"，但"没有完全参照截图画面的动作"，说明 0.75 过高；下调至 0.6 后动作保留度提升至可接受范围。

#### 24.8.2 ColorMatch reinhard + strength=0.85 的选择

**决策背景**：需要硬性锚定色调，同时保留少量自然变化避免画面呆板。

**method 选择**：
- `mkl`：颜色迁移过于强烈，可能导致局部色彩失真，不适合视频序列
- `reinhard`：基于 Reinhard 颜色迁移算法，过渡平滑，适合视频序列的逐帧锚定
- `idt-matrix`：精确但计算耗时，性价比不高

**strength 选择**：
- `0.6-0.7`：轻度锚定，长视频仍会出现累积漂移
- `0.85`：强锚定，有效防止 5 段累积漂移，保留 15% 自然变化
- `1.0`：完全匹配，场景细节色彩丢失，画面呆板

#### 24.8.3 ImageBatchExtendWithOverlap cut 模式的选择

**决策背景**：用户明确要求"视频直接拼接即可"，禁止渐变过渡。

**选择依据**：
- `linear_blend` 产生渐变，不符合用户要求
- `cut` 直接切换帧，符合"直接拼接"要求
- `overlap=1` 是节点最小值（不支持 0），但配合 `cut` 模式实际无混合帧

### 24.9 最终验证成功的工作流参数配置

基于完整任务复盘，以下是验证成功的长视频工作流参数配置（L3 高性能级，RTX 3080 20GB VRAM）。

#### 24.9.1 工作流架构

```
参考图(LoadImage) → SVI Pro 段1(49帧) → ColorMatch → 末帧
                                              ↓
                                          Flux2换皮 → ColorMatch → 修正帧
                                              ↓
                                          SVI Pro 段2(49帧) → ColorMatch → 末帧
                                              ↓
                                          ... (共5段SVI + 4段Flux2)
                                              ↓
                                          ImageBatchExtendWithOverlap(cut) × 4
                                              ↓
                                          VHS_VideoCombine → MP4
```

#### 24.9.2 模型加载参数

**SVI Pro 模型（每段相同）**：

| 节点 | 参数 | 值 | 物理意义 |
|------|------|-----|---------|
| `UNETLoader` (HIGH) | `model` | `Wan2.2_Remix_NS-FW_i2v_14b_high_lighting_v2.0.safetensors` | 高噪声阶段专用模型 |
| `LoraLoaderModelOnly` (HIGH) | `lora` | `SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors` | SVI Pro HIGH LoRA |
| `LoraLoaderModelOnly` (HIGH) | `strength` | `1.0` | 官方推荐值，过高破坏 MoE 去噪曲线 |
| `UNETLoader` (LOW) | `model` | `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` | 低噪声细化阶段专用模型 |
| `LoraLoaderModelOnly` (LOW) | `lora` | `SVI_v2_PRO_Wan2.2-I2V-A14B_LOW_lora_rank_128_fp16.safetensors` | SVI Pro LOW LoRA |
| `LoraLoaderModelOnly` (LOW) | `strength` | `1.0` | 官方推荐值 |
| `VAELoader` | `vae` | `comfy-wan_2.1_vae.safetensors` | Wan2.2 专用 VAE |
| `CLIPLoader` | `clip` | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | Wan2.2 文本编码器 |

**Flux2 模型**：

| 节点 | 参数 | 值 | 物理意义 |
|------|------|-----|---------|
| `UNETLoader` | `model` | `F2K-9b-kleinova_10FP8.safetensors` | Flux2 修正模型 |
| `LoraLoaderModelOnly` (ColorTone) | `lora` | `F2K_9b-滑块工具-质量quality.safetensors` | 质量增强 LoRA |
| `LoraLoaderModelOnly` (ColorTone) | `strength` | `0.3` | 轻度增强，过高导致颜色加深 |
| `LoraLoaderModelOnly` (Skin) | `lora` | `F2K_9b-滑块工具-皮肤skin.safetensors` | 皮肤质感 LoRA |
| `LoraLoaderModelOnly` (Skin) | `strength` | `0.3` | 轻度增强 |
| `LoraLoaderModelOnly` (Detail) | `lora` | `F2K_9b-滑块工具-背光和正光front&back.safetensors` | 光影细节 LoRA |
| `LoraLoaderModelOnly` (Detail) | `strength` | `0.2` | 轻度增强 |
| `CLIPLoader` | `clip` | `qwen_3_8b_fp8mixed.safetensors` | Flux2 文本编码器（中文理解更优） |
| `VAELoader` | `vae` | `flux2-vae.safetensors` | Flux2 专用 VAE |

#### 24.9.3 SVI Pro 采样参数

| 参数 | 值 | 物理意义 | 梯度建议 |
|------|-----|---------|---------|
| `length` | 49 | 每段生成帧数 | L1-L2: 25-33；L3: 49-81；L4: 81-121 |
| `motion_latent_count` | 1 | 从前段携带的运动 latent 帧数 | 段1=0；段2-5=1 |
| 总帧数 | 237 | 5段×49 - 4×1(overlap) | - |
| 分辨率 | 480 × 848 | 9:16 竖屏 | 必须为 16 的倍数 |
| `frame_rate` | 16 | 输出帧率 | 16: 长视频推荐；20: 源工作流默认；24: 短视频标准 |
| 视频时长 | 14.81 秒 | 237 / 16 | - |

#### 24.9.4 Flux2 采样参数

| 参数 | 值 | 物理意义 | 梯度建议 |
|------|-----|---------|---------|
| `steps` | 8 | 调度器内部步数 | 轻量修正: 4-6；平衡修正: 8-10；深度修正: 12-16 |
| 宽度/高度 | 1024 × 1024 | 内部计算分辨率 | Flux2 标准分辨率 |
| `sampler` | `euler` | 采样器 | euler: 通用；dpm++_sde: 随机性强 |
| `cfg` | 5 | CFG 引导系数 | img2img: 3-5；txt2img: 1 |
| `denoise` | 0.6 | 去噪强度（换皮平衡点） | 0.5-0.65: 推荐区间；>0.7: 动作破坏 |
| A图缩放 | 0.5 MP | A图（SVI末帧）缩放 | 保持低分辨率减少计算量 |
| B图缩放 | 1.0 MP | B图（参考图）缩放 | 保持高分辨率确保细节 |
| 输出Resize | 480 × 848 | 输出分辨率（与SVI一致） | lanczos, crop, center |

#### 24.9.5 ColorMatch 参数（9个节点统一配置）

| 参数 | 值 | 物理意义 | 梯度建议 |
|------|-----|---------|---------|
| `method` | `reinhard` | Reinhard 颜色迁移算法 | mkl: 强烈；reinhard: 平滑；idt-matrix: 精确 |
| `strength` | 0.85 | 颜色锚定强度 | 0.6-0.7: 轻度；0.8-0.9: 强锚定；1.0: 完全匹配 |
| `image_ref` | 参考图B | 颜色参考源 | 所有 9 个节点共用同一参考 |
| 插入位置 | SVI VAEDecode后 + Flux2 ImageResize后 | - | 5个SVI + 4个Flux2 |

#### 24.9.6 ImageBatchExtendWithOverlap 参数（4个节点统一配置）

| 参数 | 值 | 物理意义 | 梯度建议 |
|------|-----|---------|---------|
| `overlap` | 1 | 重叠帧数 | 节点最小值为 1（不支持 0） |
| `overlap_side` | `new_images` | 重叠侧选择 | new_images: 新段；source: 前段 |
| `overlap_mode` | `cut` | 拼接模式 | linear_blend: 渐变；cut: 硬切；fade: 淡入淡出 |

#### 24.9.7 其他关键参数

| 节点 | 参数 | 值 | 物理意义 |
|------|------|-----|---------|
| `ModelPatchTorchSettings` × 10 | `enable_fp16_accumulation` | `true` | 启用 fp16 累积，降低显存峰值 |
| `VHS_VideoCombine` | `frame_rate` | 16 | 输出帧率 |
| `VHS_VideoCombine` | `format` | `video/h264-mp4` | 输出格式 |
| `VHS_VideoCombine` | `pix_fmt` | `yuv420p` | 像素格式 |
| `VHS_VideoCombine` | `crf` | 19 | 质量系数（越小质量越高） |
| `VHS_VideoCombine` | `filename_prefix` | `WanVideo2_2_I2V_20s` | 文件名前缀 |

#### 24.9.8 验证结果

| 指标 | 结果 | 达标 |
|------|------|------|
| 总耗时 | 约 22 分钟 | ✅（目标 30-40 分钟） |
| 专用显存使用率 | 76.0% (15.5GB / 20GB) | ✅ |
| 共享 GPU 内存使用 | 未使用 | ✅ |
| 双模型串行执行 | HIGH→PurgeVRAM→LOW | ✅ |
| Flux2 动作保留 | 70%（denoise=0.6） | ✅ |
| 色调全程稳定 | ColorMatch 锚定 | ✅ |
| Flux2 颜色一致 | 与参考图B一致 | ✅ |
| 拼接无渐变 | cut 模式直接切换 | ✅ |
| 视频时长 | 14.81 秒（237帧@16fps） | ✅ |
| 节点数 | 178 | - |
| 输出节点数 | 9 | - |

### 24.10 综合教训清单

1. **长视频色调需要两层防线**：提示词约束（软性引导）+ ColorMatch 锚定（硬性锚定），仅靠提示词无法防止多段累积漂移
2. **Flux2 denoise 必须平衡换皮与动作**：0.6 是验证最优值，>0.7 破坏动作结构，<0.5 换皮不彻底
3. **拼接模式需根据用户需求选择**：`linear_blend` 适合自然过渡，`cut` 适合直接拼接，不可默认使用 linear_blend
4. **执行时间优化优先降步数和帧数**：保持分辨率（影响画质），降低 steps（线性影响耗时）和 length（线性影响耗时和时长）
5. **group 格式需兼容 ComfyUI 版本**：0.27.0+ 要求 `bounding` 数组格式 + `id` + `flags` 字段
6. **手部/肢体修复需双向提示词约束**：正向指定正确结构（"十指分明，两臂两腿"），负向禁止错误结构（"多手指，三头六臂"）
7. **ColorMatch 的 image_ref 必须稳定**：所有节点共用同一参考图，避免使用生成帧作为参考导致二次漂移
8. **帧率选择影响视频时长和流畅度**：16fps 适合长视频平衡，24fps 适合短视频标准

