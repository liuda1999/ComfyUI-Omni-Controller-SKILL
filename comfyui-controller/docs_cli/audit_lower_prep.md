# 验收审计 · 下半部分 · 准备工作底稿（远程 GPU 设备）

> 目标设备：`liuda-API` / `192.168.0.108`（下半场视频生成测试环境）
> 盘点时间：2026-10-14 ｜ 盘点方式：SSH（免密密钥，见 §8）
>
> **本文档只记录环境事实与执行方案，不写入任何凭据。**

***

## 1. 硬件与系统

| 项目 | 值 |
| --- | --- |
| GPU | **2 × NVIDIA GeForce RTX 3080（改版 20GB）**，各 20480 MiB，compute capability 8.6 |
| 驱动 / CUDA | 550.107.02 / CUDA 12.4（`nvidia-smi`） |
| CPU / 内存 | 32 核 / 46 GiB（可用 ~39 GiB） |
| 系统盘 | `/dev/nvme0n1p3` 938G，**已用 688G，可用 203G（78%）** |
| 操作系统 | Ubuntu 22.04.5 LTS，内核 6.8.0-138-generic |

> ⚠️ 磁盘余量 203G 需关注：MiniMax H3 一次运行会产生数十 GB 临时/缓存文件。

## 2. 推理环境

| 项目 | 值 |
| --- | --- |
| ComfyUI | **0.34.5**（`/home/liuda/ComfyUI`）；备份 `ComfyUI_backup_0.33.4` |
| 是否 git 仓库 | **否**（无法 `git pull` 升级） |
| Python venv | `/home/liuda/ComfyUI/venv` → Python **3.12.13** |
| torch | **2.13.0+cu126**，`cuda_available=True`，`device_count=2` |
| xformers | **未安装** |
| sageattention | **已安装且实测可用**（`sageattn` 前向成功） |
| flash_attn | 未安装 |
| ComfyUI-Manager | 3.41（**已启用**，启动带 `--enable-manager`） |
| 前端 / 模板 | frontend 1.49.6 / templates 0.11.55 |
| 自定义节点 | **120 个目录**；`/object_info` 暴露 **6230 个节点类型 / 255 个模块** |

启动方式（当前实例 PID 68013）：
```bash
/home/liuda/ComfyUI/venv/bin/python /home/liuda/ComfyUI/main.py \
  --listen 0.0.0.0 --enable-manager --cuda-device 0,1
```
由 `~/桌面/启动ComfyUI.sh` 以 `nohup` 拉起，日志 `/home/liuda/comfyui_start.log`。
端口：**8188**（局域网可达）。另有 Web 网关 `node` @ 0.0.0.0:**8765**、3080（127.0.0.1）。

## 3. 模型资产（关键项）

| 目录 | 占用 | 说明 |
| --- | --- | --- |
| `models/diffusion_models` | **294G** | Wan2.2 全家桶 + MiniMax H3 + Qwen-Image |
| `models/text_encoders` | 90G | Qwen3-VL 32B（gguf / nvfp4）、umt5-xxl |
| `models/loras` | 26G（**141 个**） | MiniMax H3 turbo LoRA、SVI v2 PRO、Wan2.2 系列 |
| `models/vae` | 20G（13 个） | Wan / MiniMax H3 video+audio VAE |

**t2v_turbo 工作流所需 5 个权重 —— 全部在位（已逐一比对 `object_info` 选项）**：

| 用途 | 文件 | 状态 |
| --- | --- | --- |
| UNETLoader | `minimax_h3_ref2va_pruned_fp8_scaled.safetensors`（19.5G） | ✅ |
| CLIPLoader | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`（14.6G） | ✅ |
| VAELoader ×2 | `minimax_h3_video_vae_fp16` / `minimax_h3_audio_vae_fp32` | ✅ |
| Turbo LoRA | `minimax_h3_fl2v_turbo_4step_v1.2_768p_comfyui_resized_avg_rank_64_bf16` | ✅ 精确命中 |

## 4. 远程现存问题（本轮盘点新发现，均为真实告警）

| # | 现象 | 影响 | 备注 |
| --- | --- | --- | --- |
| 1 | `zsq_prompt/nodes/zsq_loader.py:767` 调 `VAELoader.vae_list()` 缺少位置参数 `s` → `checkpoint_sampler_unet` 节点 `INPUT_TYPES` 抛错 | 该节点在网页端显示为红色/不可用 | **ComfyUI 0.34.x 改了 `vae_list()` 签名**，属该节点包未跟进 |
| 2 | `ComfyUI-Apt_Preset` 反复报 `Excel文件不存在: .../NodeExcel/global/*.xlsx`（10+ 条） | 仅日志噪声，不影响其他节点 | 缺资源文件 |
| 3 | `[DEPRECATION WARNING] ... /scripts/ui/components/button.js` | 某节点用了废弃前端 API | 待定位是哪个包 |
| 4 | 非 git 仓库 | 无法 `git pull` 升级 ComfyUI | 升级需重新部署 |

## 5. 与本地（上半场）环境差异

| 维度 | 本地 Windows | 远程 Ubuntu |
| --- | --- | --- |
| GPU | 无（CPU 推理） | 2×3080 20G |
| ComfyUI | 0.32.0 | 0.34.5（更新，NodeInfo 字段/签名有变化） |
| Python / torch | 3.12.9 / 2.9.1（嵌入式） | 3.12.13 / 2.13.0+cu126 |
| 自定义节点 | 约 36 包被引用 | 120 包 / 6230 节点 |
| 本项目 CLI | 已安装（venv，含本程修复） | **未安装**（无 `cli` 模块、无 `comfy` 可执行） |
| 日志 | `user/comfyui_<port>.log` | 启动脚本重定向到 `~/comfyui_start.log` |

> 结论：下半场不需要在远程部署本项目——**由本地驱动远程**（见 §7）。

## 6. ⚠️ 关键前置：临时卸载 llama.cpp（`qwen.service`）

**现状**：远程常驻本地大模型服务，占满两张卡：

| GPU | 总显存 | 已用 | 空闲 | 占用者 |
| --- | --- | --- | --- | --- |
| 0 | 20480 MiB | 16346 MiB | **3836 MiB** | `llama-server` pid 1006 = 16112 MiB |
| 1 | 20480 MiB | 18222 MiB | **1957 MiB** | `llama-server` pid 1006 = 17968 MiB |

**服务身份（用于原样恢复）**：

| 项目 | 值 |
| --- | --- |
| systemd 单元 | **`qwen.service`**（`Qwen3.8-27B API Server`，`enabled`，自 2026-10-06 运行） |
| 启动脚本 | `/opt/start_qwen.sh`（root 所有，含多个 `.bak`） |
| 主进程 | pid 993 = `/bin/bash /opt/start_qwen.sh` → 子进程 1006 = `./build/bin/llama-server` |
| 监听 | `0.0.0.0:23456`（局域网可达） |
| 模型 | `/opt/models/Qwen3.8-27B-UD-Q6_K_M.gguf` + `--mmproj mmproj-BF16.gguf` |
| 健康端点 | `GET http://127.0.0.1:23456/health` → `{"status":"ok"}`；`/v1/models` 可列模型 |
| 运行用户 | **root**（`liuda` 无信号权限，`kill -0 1006` 失败） |
| sudo | `liuda` 属 `sudo` 组，但 **`sudo -n` 不可用，需密码** |

**处置方案（不改任何 llama.cpp 配置，仅停/起服务）**：

```bash
# 测试前：停止（释放约 34 GB 显存）
sudo systemctl stop qwen.service
# 校验已释放：nvidia-smi 应显示两卡空闲 ~20 GiB
# 校验服务已停：curl -s --max-time 3 http://127.0.0.1:23456/health 应失败

# 测试后：原样恢复（systemd 按原 unit 拉起，参数与配置完全不变）
sudo systemctl start qwen.service
# 校验恢复：systemctl is-active qwen.service == active
#           curl -s http://127.0.0.1:23456/health == {"status":"ok"}
#           /v1/models 能列出 Qwen3.8-27B
```

> 该服务同时是远程 Web 网关（8765）的模型后端，**停机期间 Web 侧 AI 能力不可用**。
> 另注：llama-server 带 `--sleep-idle-seconds 2100`（空闲 35 分钟自动释放显存），但不可依赖它来腾显存。

## 7. 主测试方案：MiniMax H3 生成 10 秒视频

### 7.1 选定工作流

`comfyui-controller/assets/minimax_h3_t2v_turbo_v1.0.0.json`（工作流仓库内 MiniMax H3 之一）

- 用途：**文生视频 T2V · FL2V Turbo 4 步快速版**，21 节点，UI 格式
- 同时产出**画面 + 音频**（`VAEDecodeAudio` → `CreateVideo(images, audio)` → `SaveVideo`）
- 输出：`ComfyUI/output/video/MiniMax_H3_0000N_.mp4`
  （该机 `output/video/` 下已有 9 月的 `MiniMax_H3_00001/2_.mp4`，说明此工作流在本机跑通过）

> ⚠️ **重要发现**：`*_api.json` 孪生版的 widget 输入为空（如 `VAELoader.inputs={}`），
> **不可直接提交**。必须提交 **UI 版**，由 CLI 的 UI→API 转换（依赖服务端 `/object_info`）生成可执行图。

### 7.2 10 秒参数的推导（已从工作流内部算法解出）

帧数由 `ComfyMathExpression`（节点 132）计算，输入为 `PrimitiveFloat`（节点 133 = 秒）：

```
length = max(5, round(a * 24)) + (5 - (max(5, round(a*24)) % 17)) % 17
```

即帧数被约束为 **17k+5**（H3 的时序压缩约束）：

| `PrimitiveFloat` a | 计算 | 帧数 | @24fps 时长 |
| --- | --- | --- | --- |
| 3（文档旧值） | 72→+1 | 73 | 3.04 s |
| 5（当前文件值） | 120→+4 | 124 | 5.17 s |
| **10（本次目标）** | 240→+3 | **243** | **10.125 s** ✅ |

**唯一改动**：把节点 133 `PrimitiveFloat` 从 `5` 改为 `10`。
其余保持默认：`CreateVideo.fps=24`、`ResolutionSelector=16:9 / 0.4MP / 32`（→ 约 832×480）、
`BasicScheduler=simple / 20 步 / denoise 1`、Turbo LoRA strength=1。

> 分辨率与长度都是**连线**输入（节点 131 的 `width/height/length` 有 link），
> 因此改 `PrimitiveFloat` 即可，不必动节点 131 里缓存的 1344/768/73 显示值。

### 7.3 依赖核对（已全部通过）

- **节点类型**：21 个全部存在。核心/`comfy_extras` 19 个 +
  `MiniMaxH3TurboLoRA`、`MiniMaxH3TurboSampler`（来自 `custom_nodes.comfyui-workflow-encrypt`）
- **权重**：见 §3，5 项全在位且文件名精确匹配

### 7.4 执行方式：**脚本部署到远程执行**（已采用；本地直连被沙箱拦截）

**实际情况与本节初稿不同，以实测为准**：

| 方式 | 结果 |
| --- | --- |
| 本地 CLI `comfy run --host 192.168.0.108` | ❌ **被沙箱网络拦截**：取 `/object_info` 返回 **HTTP 403**（沙箱对该地址有 intercept），见 §14 R6 |
| 本地脚本（`pre_task_inquiry.py` / `check_status.py`） | ✅ 可用（只读探测走 `/system_stats`），见 §11 |
| **把项目脚本部署到远程、在目标机执行** | ✅ **最终采用**：`scp scripts/run_workflow.py` 到 `~/audit_lower/`，以 `127.0.0.1:8188` 运行 |

```bash
# 实际执行方式（第 1/2 轮均如此）
scp scripts/run_workflow.py <workflow>.json liuda@192.168.0.108:~/audit_lower/
ssh liuda@192.168.0.108
cd ~/audit_lower && setsid nohup /home/liuda/ComfyUI/venv/bin/python run_workflow.py \
  --host 127.0.0.1 --port 8188 --workflow <workflow>.json \
  --timeout 3600 --poll 2.0 --output-dir ~/audit_lower/out \
  < /dev/null > run.log 2>&1 &
```

预检与环境检查（本地执行，指向远程）：

```bash
export COMFYUI_HOST=192.168.0.108 COMFYUI_PORT=8188
python scripts/pre_task_inquiry.py                     # 强制预检反问（已通过 —— 见 §11）
python scripts/check_status.py --host 192.168.0.108 --port 8188   # 目标机视角见返回的 target 块
```

**已备好的运行件**（均已干跑验证，见 §11）：

| 文件 | 说明 |
| --- | --- |
| `E:/comf/_ccu/minimax_h3_t2v_turbo_10s_UI.json` | 由库内 UI 工作流产出的 10 秒版：`PrimitiveFloat#133=10`、提示词已替换、`SaveVideo` 前缀 `video/audit_lower_10s` |
| `E:/comf/_ccu/minimax_h3_t2v_turbo_10s_API.json` | 上者的 API 版（用**远程** `object_info` 转换，18 节点，输出节点 `92 SaveVideo`）— **第 1 轮实际使用** |
| `E:/comf/_ccu/minimax_h3_t2v_turbo_10s_Q6_API.json` | Q6 变体（`UnetLoaderGGUF` + `minimax_h3_ref2va_pruned-Q6_K.gguf`）— 第 2 轮使用，因加载器缺口失败（§12.3） |
| `E:/comf/_ccu/make_10s.py` | 生成上述 UI/API 文件的脚本（可复现、可改参数） |
| `E:/comf/_ccu/verify_video.sh` | 成片核验脚本（ffprobe 指标 + 每 2 秒抽帧 + 音频轨检查） |

**目标提示词**（自由设计，取可逐帧核验的中性场景）：

> 一只棕色柴犬在雪地里奔跑，尾巴翘起，雪花飘落，镜头侧面跟拍，白天，自然光，写实摄影，高清晰度

核验点：① 主体是**狗**且毛色偏棕；② 场景是**雪地/降雪**；③ 有明显**奔跑**位移；
④ 白天自然光。计划从成片均匀抽 4–6 帧目视比对。

### 7.5 OOM 降级次序（已与你确认）

1. 先降 `ResolutionSelector.megapixels`（0.4 → 约 0.2，保持 16:9）；
2. 仍 OOM 再缩短时长（降 `PrimitiveFloat`，注意帧数必须是 17k+5）；
3. 每次降级后在报告中**明确标注实际分辨率与时长**。


## 8. SSH 访问（已就绪）

- 本机（Windows）已生成 ed25519 密钥并安装到远程 `~/.ssh/authorized_keys`
  （`~/.ssh` 700 / `authorized_keys` 600，已验证 `BatchMode=yes` 免密登录）
- 私钥仅存于本机 `~/.ssh/id_ed25519`，**未写入本项目任何文件**
- 远程 `authorized_keys` 现共 3 个公钥（含原有 agent 公钥）

## 9. 风险与对策

| 风险 | 对策 |
| --- | --- |
| **显存不足（首要）** | 必须先停 `qwen.service`；若仍 OOM → 降 `ResolutionSelector` megapixels 或缩短时长 |
| 环境代理干扰局域网访问 | 当前本机**无**代理变量，已实测直连远程成功；若后续出现 502，需把 LAN IP 加入 `NO_PROXY`（`run.py` 的 `/object_info`、`/prompt` 仍是默认 opener，属潜在薄弱点） |
| 首次加载耗时 | 需从磁盘读入 19.5G + 14.6G 权重，预计数分钟 |
| 生成耗时未知 | 243 帧 @832×480，双卡 4 步 turbo；预计 10–40 分钟（**决定 LLM 停机时长**） |
| 磁盘 203G 余量 | 运行前后检查 `df -h`，必要时清理 `temp/` |
| ComfyUI-Manager 日志冲突 | 远程以 `--enable-manager` 运行，Manager 会写 `user/comfyui_<port>.log`；若在远程用本项目 `launch --background` 会撞名（本程已列为待决项） |

## 10. 待确认 / 待办（测试后更新）

1. ~~LLM 停机窗口~~ → 已执行：停机 00:47:36 → 恢复 01:08:26（**20 分 50 秒**），配置未改。
2. ~~OOM 降级策略~~ → 已确认：先降分辨率，再降时长（见 §7.5）；**实测未触发 OOM**。
3. ~~产物核验~~ → **已完成**：时长 10.125 s / 243 帧 / 内容逐帧比对通过（见 §12.2）。
4. **Q6 第二轮**：受上游 `ComfyUI-GGUF` 架构表缺 H3 阻断（见 §12.3）；需你决定是否推进
   （升级加载器 / 换包 / 打补丁，三者均需单独评审）。
5. 审计收尾：§11 的 4 项修复与 §12/§13 的结论已并入经验文档（第 26 章）与本底稿。

***

## 11. 本程预检实测：发现的 4 个问题与修复

> 结论：**项目"不可跳过"的预检原本无法支撑 MiniMax H3**（工作流仓库里却有 6 个 H3 工作流），
> 且**在远程驱动场景下会误判**。以下 4 项已全部修复并实测通过。

### F1（阻断级）预检不认识 MiniMax H3 系列 → 硬失败

**实测证据**（指向远程、选 H3 主模型）：
```
已选择扩散模型: minimax_h3_ref2va_pruned_fp8_scaled.safetensors
识别模型系列: 其他
[错误] 模型系列 '其他' 无组件匹配规则，无法安全匹配 VAE/CLIP。
       已识别系列: ['Wan2.2', 'Flux', 'Flux2', 'SD1.5', 'SDXL']
```
根因：`FAMILY_KEYWORDS` / `FAMILY_MATCH_RULES` 只有 Wan2.2 / Flux2 / Flux / SDXL / SD1.5。

**修复**：新增 `MiniMaxH3` 系列
- 关键词：`minimax_h3` / `minimaxh3` / `minimax-h3`（置于最前，"最具体优先"）
- `vae` → `minimax_h3_video_vae`（音频 VAE 由 H3 工作流自身加载，不属预检单选）
- `clip` → `qwen3vl_32b_minimax_h3`（H3 用 Qwen3-VL 32B，不是 t5）
- `clip_vision` → 空（H3 不用）

**实测结果**：`vae: minimax_h3_video_vae_fp16.safetensors（自动匹配）`、
`clip: qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors（自动匹配）`、`clip_vision: 已跳过`。

### F2（阻断级）显存/内存探测用的是**本机**，不是目标机

`query_gpu_vram_mb()` 直接跑本机 `nvidia-smi`。本项目支持 `COMFYUI_HOST/COMFYUI_PORT`
指向远程，此时**模型列表来自远程、硬件却测本地**，在无 GPU 的调度机上必然判死：
```
[错误] 无法获取 GPU 显存信息，请确认已安装 NVIDIA 显卡及驱动。
```
（同项目的 `check_status.py` 反而是 host 感知的，两者口径不一致。）

**修复**：新增 `_vram_from_system_stats()` / `_ram_from_system_stats()`，
`query_gpu_vram_mb()` / `query_system_ram_mb()` 改为**优先读目标服务器的 `/system_stats`**
（多 CUDA 设备取 `vram_total` 最大值 = 单卡须放下主模型），服务器不可达才退回本地探测，
并打印数据来源。

**实测结果**：
```
[信息] 显存来源: 192.168.0.108:8188 /system_stats（目标服务器自我报告）
GPU 显存: 20181 MB (19.7 GB)
[信息] 内存来源: 192.168.0.108:8188 /system_stats（目标服务器自我报告）
系统内存: 48006 MB (46.9 GB)
```

### F3 预检的架构/参数语义是 Wan2.2 专属

- 方案 A/B（HIGH+LOW 双采集器）是 **Wan2.2 专有**；对 H3（单 DiT + Turbo LoRA）提问无意义，
  且误选 A 会把 `dual_serial` 往下游传、污染显存估算。
- H3 的**合法帧数被约束为 17k+5**，原预检按 121/241 的通用档位，会产出非法帧数；
  H3 工作流的 `CreateVideo` 固定 **24fps**，原预检默认 16。

**修复**：
- 非 Wan2.2 系列跳过方案 A/B，直接返回 `single` 并说明；
- 新增 `h3_align_length()`，H3 时把帧数吸附到最近 `17k+5`；fps 默认 24；补充换算提示；
- H3 时提示"实际采样器由工作流内 `MiniMaxH3TurboSampler` 提供"，避免 `dpmpp_sde` 口径误导。

**实测结果（正是"10 秒"目标）**：
```
[MiniMax H3] 帧数 240 非 17k+5，已吸附为 243 （10.125 s @24fps）
帧数/帧率:   243 帧 @ 24 fps
```

### F4 `check_status.py` 在远程场景下的口径歧义

顶层 `system` / `memory` / `gpu` / `capabilities` **描述的是本机**，但同一次输出里
`server_url` 指向远程、`status: online`。指向远程时会读到
`"os": "Windows", "cuda_available": false`，极易被误读成"目标机跑不了视频"。

**修复**（纯增补，不改任何既有字段，`controller.py` 仅消费 `ok` 故无影响）：
新增 `target` 块，把目标机 `/system_stats` 的自我上报摘出来——os、ComfyUI 版本、
RAM、每卡 VRAM 总量/空闲、最大单卡容量，并附 `note` 说明口径；
**只报事实、不臆造阈值**。

**实测结果**：
```json
"target": {"os": "linux", "comfyui_version": "0.34.5", "ram_total_gb": 46.88,
           "gpu_count": 2, "gpu_names": ["cuda:0 ... RTX 3080 ...", "cuda:1 ..."],
           "gpu_vram_total_gb": [19.71, 19.71], "gpu_vram_free_gb": [3.75, 1.91],
           "max_gpu_vram_total_gb": 19.71}
```
（顺带独立印证了 §6 的显存紧张：两卡仅 3.75 / 1.91 GiB 空闲。）

### 11.5 预检最终通过记录（10 秒 H3）

```
扩散模型:    minimax_h3_ref2va_pruned_fp8_scaled.safetensors
模型系列:    MiniMaxH3
架构方案:    方案B: 单一模型（简单模型 —— H3 无 HIGH/LOW 双采集器）
VAE:         minimax_h3_video_vae_fp16.safetensors
CLIP:        qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
CLIP_VISION: None
画面比例:    16:9横屏 / 分辨率 480P
目标尺寸:    832×480
帧数/帧率:   243 帧 @ 24 fps          ← 10.125 秒 ✅
优化步数:    8（L3 高性能档，基于目标机 19.7GB 单卡）
GPU 显存:    20181 MB (需要 19456 MB)  ← 通过
系统内存:    48006 MB
确认执行? (y/n，默认 y): y
```

> 关于 H3 显存阈值：`determine_vram_requirement` 对 H3 返回 **19456 MB（19 GiB）** 而非标称
> 20480 MB。依据：① ref2va fp8 主 DiT 文件 ≈19.5 GB(18627 MiB)，阈值须高于它；
> ② ComfyUI 上报的 `vram_total` 略低于标称（20 GiB 卡上报 20181 MiB，差额是 CUDA 上下文等保留显存），
> 按 20480 比对会把**实际跑得通**的 20 GiB 卡误杀（该机 `output/video` 下有 9 月的 H3 产出为证）；
> ③ 16 GiB 及以下单卡仍会被正确拒绝。**这是一处"临界通过"，运行前须先停 `qwen.service` 腾出显存。**


***

## 附：本轮盘点脚本

| 脚本 | 用途 |
| --- | --- |
| `E:/comf/_ccu/remote_inventory.sh` | GPU / 系统 / 目录 / 启动脚本 / 端口 |
| `E:/comf/_ccu/remote_inventory2.sh` | ComfyUI 版本 / 依赖 / 节点 / 模型 |
| `E:/comf/_ccu/remote_inventory3.sh` | 模型资产 / 工作流 / 日志 / CLI |
| `E:/comf/_ccu/remote_check_h3.sh` | H3 依赖核对 / llama 取证 |
| `E:/comf/_ccu/remote_check_final.sh` | sudo / 健康端点 / 产物目录 |

> 执行方式：`ssh -i ~/.ssh/id_ed25519 liuda@192.168.0.108 'bash -s' < 脚本`

***

## 12. 测试执行记录（2026-10-14）

### 12.1 停机与恢复（llama.cpp）

本次共**两段停机**（第 1 轮 fp8 前、第 2 轮 Q6 前），均由 `systemctl stop/start qwen.service` 完成：

| 轮次 | 停止（远程） | 恢复（远程） | 停机时长 |
| --- | --- | --- | --- |
| 第 1 轮（fp8） | 00:47:36 | 01:08:13 | **20 分 37 秒** |
| 第 2 轮（Q6） | 01:17:55 | 01:36:18 | **18 分 23 秒** |
| **合计** | — | — | **约 39 分 00 秒** |

| 项 | 值 |
| --- | --- |
| 恢复后终态 | `qwen.service: active` / `llama-server pid 352185` / `health={"status":"ok"}` |
| 恢复后显存 | GPU0 16478 MiB / GPU1 18204 MiB 已用（测试前 16346 / 18222，**已还原**） |
| 配置改动 | **无**（仅 `systemctl stop/start`，未触碰 `/opt/start_qwen.sh` 与任何 config） |
| 自愈行为 | `Restart=on-failure` —— 第 1 轮恢复时 GPU0 一度只剩 5.9 GB，llama-server 首次启动 OOM 退出（`allocating 9616.28 MiB ... cudaMalloc failed`），systemd 在显存释放后自动重启（01:08:13）成功 |

> **经验：恢复 LLM 前必须先释放 ComfyUI 占用的显存**（`POST /free`）。本程在两轮恢复时
> 都先执行了 `free_http=200`（显存回到 347/254 MiB）再 `start`，否则 27B 模型无法完整加载。

### 12.2 第 1 轮：fp8（工作流仓库原配置）—— ✅ 通过

| 项 | 值 |
| --- | --- |
| 执行方式 | 项目脚本 `scripts/run_workflow.py`（部署到远程，在目标机以 `127.0.0.1:8188` 执行） |
| prompt_id | `3583154e-1369-4e5e-872a-eaae44d01c29` |
| 耗时 | **`Prompt executed in 00:16:48`** |
| 产物 | `ComfyUI/output/video/audit_lower_10s_00001_.mp4`（1,506,001 B） |

**ffprobe 客观指标**：

| 指标 | 值 | 结论 |
| --- | --- | --- |
| 时长 | **10.125000 s** | ✅ 精确达成"10 秒" |
| 帧数 / 帧率 | **243 帧** / 24 fps | ✅ 与预检推导的 17k+5 一致 |
| 分辨率 / 编码 | 864×480 / h264 | ✅ |
| 音频 | **aac，32 kHz，立体声，10.125 s** | ✅ H3 同步产出音频 |
| 大小 / 码率 | 1.5 MB / ~1.19 Mbps | — |

**内容核验**（每 2 秒抽 1 帧，逐帧目视比对提示词）：

| 提示词要素 | 实际画面 | 结论 |
| --- | --- | --- |
| 棕色犬（柴犬型） | 棕/褐毛、白胸白面纹，柴犬/秋田体型 | ✅ |
| 雪地 + 雪花飘落 | 前景积雪 + 空中雪粒 | ✅ |
| 奔跑 | 连续帧腿部姿态明显位移（跨步→落地） | ✅ |
| 侧面跟拍 / 白天自然光 | 恒定左侧面构图，日间柔光 | ✅ |

> **结论：生成结果与提示词完全一致，主测试目标达成。**

### 12.3 第 2 轮：Q6 GGUF —— ✅ 通过（经"桥接加载器"修复后）

**首次失败**（原 `UnetLoaderGGUF`）：
```
Task failed: 节点 127 (UnetLoaderGGUF): This model is not currently supported
             - (Unknown model architecture!)  [ValueError]
```

**根因定位**（取证，见下表）：远程 GGUF 加载器的架构表都不含 H3。

| 证据 | 内容 |
| --- | --- |
| 远程 `ComfyUI-GGUF` 版本 | **v2.0.0**，`tools/convert.py: detect_arch` 支持 flux / sd3 / aura / hidream / cosmos / hyvid / wan / ltxv / sdxl / sd1 / lumina2 —— **无 H3** |
| 多卡 fork（`UnetLoaderGGUF*MultiGPU` 等） | 与 ComfyUI-GGUF 同源，**同缺 H3** |
| `comfyui-multigpu` / KJNodes 的 H3 节点 | 均为显存优化/提示词类，**无 unet 加载器** |
| Q6 文件本体 | **正常**：GGUF v3、532 张量、前缀 `blocks.N.*` 与 `token_refiner.blocks.*`；**`kv_count=0`（无架构元数据）**，须靠张量名推断 |

**找到可用加载器（本轮修复）**：远程已装 **`comfyui-gguf-loader`**，其自带
`tools/convert.py` **已内置 H3**：

```python
class ModelLTX2(ModelTemplate):
    """MiniMax-H3 DiT (and related LTX-2-family GGUFs tagged arch=ltx2)."""
    arch = "ltx2"
    # 签名键含 audio_patch_proj.weight / patch_proj.weight ...
```

它从**张量名**探测出 `ltx2`，再经 `image_architecture()` 判定为 `minimax_h3`（在允许表内），
且提供"无 arch 标签"的回退路径。**无需重新量化** —— 唯一障碍是它的同名节点被 `ComfyUI-GGUF` 覆盖。

**修复方式（纯新增，不改任何现有包）**：新增桥接节点包
`ComfyUI/custom_nodes/zz_h3_gguf_bridge/`（约 4 KB，`__init__.py` 单文件）：

- 以唯一名字暴露两个节点：**`UnetLoaderGGUF_H3`**（+ `UnetLoaderGGUFAdvanced_H3`）；
- **延迟 import** `comfyui-gguf-loader`（在其节点注册时按需解析，避免自定义节点加载顺序问题）；
- 安装后**用原启动命令重启 ComfyUI**（参数与原 `~/桌面/启动ComfyUI.sh` 完全一致：
  `--listen 0.0.0.0 --enable-manager --cuda-device 0,1`，日志同路径）。

**成功证据**：
```
[WARNING] This gguf model file is loaded in compatibility mode 'sd.cpp' [arch:minimax_h3]
[MiniMaxH3TurboLoRA] ... model=MiniMaxH3 weight_dtype=torch.bfloat16
[INFO] Model MiniMaxH3TEModel_ prepared for dynamic VRAM loading. 14956MB Staged. ...
[INFO] Model MiniMaxH3VideoVAE prepared for dynamic VRAM loading. 4965MB Staged. ...
[INFO] gguf qtypes: F32(10), F16(102), BF16(211), Q6_K(209)
[INFO] Prompt executed in 00:17:37
```

**第 2 轮结果**：

| 指标 | 值 | 结论 |
| --- | --- | --- |
| 执行方式 | 项目脚本 `run_workflow.py`（远程，`127.0.0.1:8188`） | — |
| prompt_id | `bee83fa5-afb4-4256-af94-fdcf26b83ca1` | — |
| 耗时 | **`Prompt executed in 00:17:37`** | — |
| 产物 | `output/video/audit_lower_10s_q6_00001_.mp4`（1,534,550 B） | — |
| **时长** | **10.125000 s** | ✅ 与 fp8 完全一致 |
| 帧数 / 帧率 | **243 帧 / 24 fps** | ✅ |
| 分辨率 / 编码 / 音频 | 864×480 / h264 / aac 立体声 10.125 s | ✅ |
| **内容核验** | 棕色犬 ✅ 雪地飘雪 ✅ 奔跑位移 ✅ 侧面跟拍/日间光 ✅ | ✅ 与提示词一致 |

> **两轮均达成 10 秒目标**（243 帧 @24fps），内容一致，Q6 出图细节同样正确。
> Q6 与 fp8 的综合对比见 §13 D5/D6。

***

## 13. 本轮实测新增发现

| # | 发现 | 说明 |
| --- | --- | --- |
| D1 | **工作流命名与配置不一致** | `minimax_h3_t2v_turbo`（名为"Turbo **4 步**快速版"）实际 `BasicScheduler.steps=20`，单次采样约 15 分钟；与"4 步 turbo"设计意图不符。本次**按原样执行**以保证可比性，未擅自改参数 |
| D2 | **双卡未形成显存分摊** | 实测仅在 **card0** 加载（text encoder 14956 MB + DiT 19983 MB 动态 staged），**card1 几乎闲置**（~300 MB）。`--cuda-device 0,1` 并未让两卡分担；若要真正分摊需换用 multi-GPU 节点（`UnetLoaderGGUF*MultiGPU` / DisTorch 系列） |
| D3 | 库内 `*_api.json` 不可直接提交 | 再次确认（见 §15 R3），必须走 UI 版 + UI→API 转换 |
| D4 | 单卡临界承载 | DiT 19983 MB staged 于 19.7 GiB 卡上、空闲仅 3.4 GB —— 依赖 ComfyUI 的动态加载；这正是必须停 LLM 腾显存的原因 |
| D5 | **Q6 的可用依赖是"包内自带、被同名节点覆盖"** | `comfyui-gguf-loader` 的 `tools/convert.py` 已内置 H3（`ModelLTX2`，arch=`ltx2`→判定 `minimax_h3`），但其加载器节点名与 `ComfyUI-GGUF` 冲突而被覆盖。**桥接一个唯一节点名即可解锁，无需重新量化**（见 §12.3） |
| D6 | **Q6 未必比 fp8 更省显存** | Q6 轮次 card0 峰值 **19441~19539 MiB**，fp8 轮次 **15919 MiB** —— 因 GGUF 以兼容模式（`sd.cpp`）加载、反量化为 `bfloat16`，反而**更占**。这与"显存不足就切 Q6"的直觉相反：**Q6 的价值在磁盘占用（16.55 GB vs 18.6 GB）与加载灵活性，而非显存** |
| D7 | **加载顺序敏感的节点需"延迟 import"** | 桥接节点若在 import 时立即 `import comfyui-gguf-loader`，会因自定义节点加载顺序而未就绪；实测日志 `[h3-gguf-bridge] note: 'comfyui-gguf-loader' not in sys.modules yet` 印证——按需解析（在 `INPUT_TYPES`/`NODE_CLASS_MAPPINGS` 访问时再导入）才稳妥 |
| D8 | **`comfyui-h3-upgrade-kit` 导入失败** | 远程该包因 `No module named 'comfy_extras.nodes_loop'`（ComfyUI 0.34.5 无此模块）整体导入失败，其 H3 节点（motion/loop/audio/latent-upscale）**当前不可用**。属第三方包的版本适配问题，不影响本次测试 |

***

## 14. 环境与流程残留（补充 §15）

| # | 项 | 影响 | 处置 |
| - | - | ---- | ---- |
| R6 | **本机沙箱对 `192.168.0.108:8188` 有网络拦截**（本地 CLI 取 `/object_info` 返回 **HTTP 403**） | 本地 CLI 无法直连远程 ComfyUI（`comfy run` 不可用） | 本次改为"把项目脚本 `run_workflow.py` 部署到远程、在目标机执行"绕过；若要本地直连，需在沙箱放行该地址 |
| R7 | 远程遗留文件 | `~/audit_lower/`（脚本 + 3 个工作流 + 日志 + `out/video/*.mp4` + `frames_fp8/` + `frames_q6/`）、`ComfyUI/output/video/audit_lower_10s_00001_.mp4` 与 `audit_lower_10s_q6_00001_.mp4` | 可保留或清理，请指示 |
| R13 | **远程新增桥接节点包** | `ComfyUI/custom_nodes/zz_h3_gguf_bridge/`（解锁 H3 GGUF 加载） | 属本轮修复产物，**建议保留**；若不需可删除该目录并重启 ComfyUI |
| R14 | 远程 ComfyUI 已由本程重启 | 当前进程由本程以**与原启动脚本一致的参数**启动（`--listen 0.0.0.0 --enable-manager --cuda-device 0,1`，日志同路径），用户下次用 `~/桌面/启动ComfyUI.sh` 时会提示已在运行 | 无影响；如需完全回归"用户启动"，可先停再执行原脚本 |
| R8 | 本机 `~/.ssh/authorized_keys` 之外 | 远程 `authorized_keys` 新增 1 个公钥（本机审计用） | 可保留；如需回收可删除对应行 |
| R9 | sudo 需密码 | 停止/恢复服务依赖用户提供的密码（经管道传入，未写入任何文件） | 建议长期改为 `NOPASSWD` 限定单元或改用专用账号，避免密码进入命令历史 |

***

## 15. 残留项（已记录，本程未改）

| # | 项 | 影响 | 建议 |
| - | - | ---- | ---- |
| R1 | `cli/command/run.py` 的 `/object_info`、`/prompt` 仍走默认 opener，websocket 亦可能读代理环境变量 | 当前本机无代理变量，已实测直连远程正常；若在有 `HTTP_PROXY` 的环境下驱动远程/局域网，会返回 502 误判"服务未运行" | 把这两处改走 `cli/command/net.py`（无代理 opener），或在连接前把目标 host 加入 `NO_PROXY` |
| R2 | 工作流仓库的**模型系列分类器不认 H3**（`query_library.py --stats` 显示 `unknown 99 个`） | `--model-family` 过滤不到 H3 条目 | 与预检同一批补 H3 家族规则并重建库。本次用 `--model minimax_h3`（命中 5 个）绕过 |
| R3 | `*_api.json` 孪生版的 widget 输入为空（如 `VAELoader.inputs={}`） | **不可直接提交**；必须提交 UI 版并由 CLI 做 UI→API 转换 | 修复导出器，或在文件旁标注"需经 UI→API 转换" |
| R4 | 远程 ComfyUI 以 `--enable-manager` 运行，Manager 会写 `user/comfyui_<port>.log` | 若在远程用本项目 `comfy launch --background`，会与该文件**撞名**（EXPERIENCE ch.25 已列） | 改用独立文件名（如 `comfyui_cli_<port>.log`） |
| R5 | H3 关键节点 `MiniMaxH3TurboLoRA` / `MiniMaxH3TurboSampler` 来自 `custom_nodes.comfyui-workflow-encrypt`（该包在远程暴露 **1293** 个节点类型，为全环境之首） | 是本次 H3 运行的**硬依赖**；该包来源/许可证未知 | 核实该包来源与许可证，补入节点注册表 |

***

## 16. 本程改动文件清单（供审计收尾核对）

| 文件 | 改动 |
| --- | --- |
| `scripts/pre_task_inquiry.py` | 新增 `MiniMaxH3` 家族与组件规则；新增 H3 显存需求 19456MB；新增 `_vram_from_system_stats`/`_ram_from_system_stats` 并把显存/内存探测改为目标机优先；非 Wan2.2 跳过双采集器方案；新增 `h3_align_length()` 与 H3 的 fps/帧数语义 |
| `scripts/check_status.py` | 新增 `summarize_target()` 与输出里的 `target` 块（纯增补） |
| `docs_cli/audit_lower_prep.md` | 本底稿（新增，含 §12 测试执行记录） |
| `docs_cli/EXPERIENCE.md` | 追加第 26 章（4628-4730 行）；第 27 章（本轮测试结论） |
| `docs_cli/INDEX.md` | 文档地图、速查表、§3.5 行号、新增 §3.6/§3.7、§4.0 条目、行数基准 |
| `E:/comf/_ccu/make_10s.py` | 10 秒工作流生成脚本（新增，仓库外工具） |
| `E:/comf/_ccu/verify_video.sh` | 成片核验脚本（新增，仓库外工具） |
| `E:/comf/_ccu/minimax_h3_t2v_turbo_10s_Q6b_API.json` | Q6 变体工作流（用桥接加载器，**本轮跑通**） |
| `E:/comf/_ccu/h3_gguf_bridge/__init__.py` | **H3 GGUF 桥接节点源码**（4 KB；解锁 `comfyui-gguf-loader` 的 H3 加载能力） |
| `scripts/h3_gguf_bridge/`（**项目内留档**） | 桥接节点源码 `__init__.py` + `README.md`（安装/使用/前置条件/实测注意） |
| `E:/comf/_ccu/audit_out/` | 两轮产物：2 个 mp4（1.5 MB / 1.53 MB）+ `frames_fp8/`（5 张）+ `frames_q6/`（5 张）抽帧 PNG |

**远程（`liuda-API`）新增内容**：

| 路径 | 内容 | 建议 |
| --- | --- | --- |
| `ComfyUI/custom_nodes/zz_h3_gguf_bridge/` | **H3 GGUF 桥接节点**（本轮修复产物） | **建议保留**（解锁 Q6 路径） |
| `~/audit_lower/` | `run_workflow.py`、3 个 API 工作流、`verify_video.sh`、`run1_fp8.log`、`run2_q6.log`、`run2_q6b.log`、`out/video/*.mp4`、`frames_fp8/`、`frames_q6/` | 可清理（见 §14 R7） |
| `~/ComfyUI/output/video/` | `audit_lower_10s_00001_.mp4`、`audit_lower_10s_q6_00001_.mp4` | 可清理 |
| `~/.ssh/authorized_keys` | **新增 1 行**（本机审计用公钥） | 可保留/回收 |
| `~/comfyui_start.log.run1_backup` | 第 1 轮前的启动日志备份 | 可清理 |


