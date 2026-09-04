# ComfyUI · Wan2.2 双实例视频生成 · 节点调参手册

> 面向对象：后续接手本项目并要对 Wan2.2 双卡工作流做参数调整的智能体 / 开发者。
> 本文只讲 ComfyUI 内的工作流、节点、参数与标定数据；不涉及远程设备/网络/传文件等环境操作。
>
> 核心结论：**双原生 ComfyUI 实例**（非 MultiGPU 扩展）按卡分工，HIGH/LOW 分阶段采样，CPU 块交换兜底，无 OOM。编排器用**双线程流水线**把不同档位的 Stage1( GPU0) 与 Stage2( GPU1) 重叠执行，做到**两张卡同时 100% 利用**；测试采用的画面为咖啡馆场景、主体清晰（非噪点）。

***

## 0. 硬件约束与架构（先读）

| 资源   | 数值                                             |
| ---- | ---------------------------------------------- |
| GPU  | 双 RTX 3080，各 **20GB VRAM**                     |
| 系统内存 | \~44GB（offload + 块交换兜底）                        |
| 模型   | `Wan2_2-I2V-A14B-HIGH/LOW` 各 \~19GiB FP8，单卡放不下 |

### 0.1 架构：双实例按卡分工

- **实例 A（8188，主设备 cuda:0=物理 GPU0）**：跑 **HIGH** 模型，采样 `[0, SPLIT)`，SaveLatent 中间 latent。启动参数 `--cuda-device 0,1`。

- **实例 B（8189，`CUDA_VISIBLE_DEVICES=1`=物理 GPU1）**：跑 **LOW** 模型，LoadLatent 续采样 `[SPLIT, END)`，VAE 解码出片。

- **关键点**：Wan2.2 每张卡都能单独放下一个 A14B FP8 模型（配合 CPU 块交换），**不需要 MultiGPU 扩展**。MultiGPU 扩展的 `get_torch_device_patched()` 会导致模型组件缓存到错误设备，引发 `Expected all tensors to be on the same device` 与 GPU1 空转——**已废弃**。

### 0.2 模型与参数速查

| 项       | 值                                                                                                                  |
| ------- | ------------------------------------------------------------------------------------------------------------------ |
| HIGH 模型 | `Wan2_2-I2V-A14B-HIGH_fp8_e4m3fn_scaled_KJ.safetensors`                                                            |
| LOW 模型  | `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors`                                                             |
| 加载      | `base_precision=fp16_fast`、`quantization=fp8_e4m3fn_scaled`、`load_device=offload_device`、`attention_mode=sageattn` |
| 文本编码    | `umt5-xxl-enc-bf16`，`WanVideoTextEncode(use_disk_cache=True)` —— **磁盘缓存消除跨档重复编码（每档省 \~3min）**                      |
| 采样      | `scheduler=unipc`、`shift=8.0`、`cfg=6.0`、`rope_function=comfy`、`batched_cfg=False`                                  |
| 块交换     | `WanVideoBlockSwap(blocks_to_swap=8)`，CPU/共享内存兜底                                                                   |
| 阶段切分    | `SPLIT = max(1, steps // 2)`                                                                                       |
| 分辨率     | 标定档 480×480×120 帧（5s\@24fps，fps24）                                                                                   |

***

## 1. 阶段拆分节点详解

### 1.1 Stage1（HIGH / GPU0）：`build_stage1.py`

| 节点                           | 关键字段                                                      | 说明                             |
| ---------------------------- | --------------------------------------------------------- | ------------------------------ |
| `WanVideoTextEncode`         | `use_disk_cache=True`                                     | 缓存 T5 embeds 到磁盘，后续档/阶段零重算     |
| `WanVideoImageToVideoEncode` | `start_latent_strength=1, end_latent_strength=1`          | 首帧图生视频                         |
| `WanVideoBlockSwap`          | `blocks_to_swap=BS`                                       | CPU 块交换安全垫，防 OOM               |
| `WanVideoModelLoader`        | 见 §0.2                                                    | HIGH 模型加载到 offload\_device     |
| `WanVideoSampler`            | `start_step=0, end_step=SPLIT, add_noise_to_samples=True` | 只做前半段去噪                        |
| `SaveLatent`                 | `filename_prefix=mid_latent`                              | 写 `output/mid_latent_*.latent` |

### 1.2 Stage2（LOW / GPU1）：`build_stage2.py`

| 节点                 | 关键字段                                                        | 说明                               |
| ------------------ | ----------------------------------------------------------- | -------------------------------- |
| `LoadLatent`       | `latent=<mid>`                                              | 读 Stage1 中间 latent（从 `input/` 读） |
| `WanVideoSampler`  | `start_step=SPLIT, end_step=-1, add_noise_to_samples=False` | 续采样后半段，**不重新加噪**                 |
| `WanVideoDecode`   | `enable_vae_tiling=False`                                   | 480p 不切片                         |
| `VHS_VideoCombine` | `frame_rate=24, format=video/h264-mp4`                      | 合成 5s 视频（120 帧）                |

> ⚠️ **latent 目录桥接**：`SaveLatent` 写 `output/`，`LoadLatent` 读 `input/`。编排器需在中间执行 `cp .../output/{mid} .../input/{mid}`（见 `tiers_native.py`）。

***

## 2. 三档标定数据（BS=8，480×480×120，5s@24fps，流水线并行实测）

> 运行器 `pipeline_tier.py`：两个线程分别推 Stage1( GPU0/HIGH) 与 Stage2( GPU1/LOW)，把**不同档位**的 stage1/stage2 重叠执行，因此多数时间段两卡同时满载。

| 档位                     | Stage1→Stage2(latent 接力)         | **总耗时**      | 目标      | 双卡并行峰值                             |
| ---------------------- | -------------------------------- | ------------ | ------- | ---------------------------------- |
| **6 步**（split 3+3）       | 1.70 → 2.16 min                  | **3.86min**  | \~3min✅ | 100% & 100%（~15.6/15.9GB）              |
| **12 步**（split 6+6）      | 3.43 → 3.82 min                  | **7.25min**  | \~6min✅ | 100% & 100%（~15.6/16.0GB）              |
| **30 步**（split 15+15）    | 8.57 → 9.07 min                  | **17.64min** | \~15min✅ | 100% & 100%（~15.6/16.0GB）              |

- 全程 **无 OOM**；关键点是**重叠窗口内两卡同为 100%**（此前 GPU1 空转的缺陷已消除）。
- 系统内存峰值 ~14GB（双模型驻留 + 块交换兜底，属预期，非泄露）。
- 输出：`wan22_native_00008/09/10.mp4`（6/12/30 步）。
- 三档总流水线耗时 22.93min（三个视频串行排队合成）。

### 2.1 耗时梯度（供其它步数推算）

- 流水线模式下 HIGH/GPU0 采样 ≈ **0.29 min/步**；LOW/GPU1 采样+解码 ≈ **0.31 min/步**（含线程排队 jitter）。

- 单档总耗时会比串行（stage1+stage2）略长，因首档 stage2 要等 stage1 产出 latent；步数越多无重叠边际越小。

### 2.2 ⚠️ 画面主体落地（内容稳定性）——必读

- 现象初查：**第 1 帧纯咖啡馆、无人物；人物从后面的帧才出现**，易被误判为"第二帧起模糊/闪烁"。
- 根因：**输入首帧图（`咖啡馆.png`）是空咖啡馆，不包含"年轻女性"**，而提示词要求女性在窗边比心。Wan2.2 图生视频**锁死首帧 = 输入图**，模型只能在后续帧"凭空造人"，过渡帧被迫重构画面 → 观感时序混乱/模糊。
- 修复（参数/工作流层）：**输入首帧图必须本身包含主体与目标姿态**（如把女性比心+金丝眼镜直接做进首帧图），使提示词与首帧语义一致；或在提示词中只描述首帧已有的内容。二者一致后，后续帧仅做镜头/微动，画面时序稳定、无闪现主体。

***

## 3. 编排器与关键文件

| 文件                | 职责                                                                    |
| ----------------- | --------------------------------------------------------------------- |
| `build_stage1.py` | 生成 Stage1 原生 API 工作流（HIGH/GPU0, SaveLatent）                           |
| `build_stage2.py` | 生成 Stage2 原生 API 工作流（LOW/GPU1, LoadLatent, 解码）                        |
| `pipeline_tier.py` | **双线程流水线编排**：stage1 线程(GPU0) 与 stage2 线程(GPU1) 重叠执行不同档位，latent 桥接复制，记录双卡峰值/耗时，产出 `pipeline_results.json` |
| `launch_gpu1.py`  | 启动实例 B（`CUDA_VISIBLE_DEVICES=1`、`--port 8189`、独立 user-directory 与 DB） |

> 复跑：`python pipeline_tier.py`（BS 已在 build 脚本内固定为 8）。GPU1 实例若掉线用 `launch_gpu1.py` 重启。
> 注意：编排器 `get_latent_name` 需兼容 `{pid: entry}` 与 `entry` 两种 history 结构（`h.get("outputs")` 在 entry 内层）。
> 三档双托时因两卡各自独占一模型，无跨设备张量问题；每日测试后如需完全释放 RAM，用 `launch_gpu1.py` 重启实例即可。

### 3.1 在 web 上查看生成的视频（容易踩坑）

- 视频文件**真实存在**于两实例共用输出目录 `/home/liuda/ComfyUI/output/`，但**右侧 Output 浏览面板依赖的列表接口在本版本返回 404**，所以面板里"看不见"是正常的。
- 可靠查看方式：直接访问 view 接口（同为 `type=output`，**不要带 `subfolder` 参数**）：
  `http://192.168.0.108:8188/view?filename=wan22_native_00008.mp4&type=output`
  （8188/8189 任一均可，`/view` 对 `output/*.mp4` 返回 200 `video/mp4`）
- 库内 8189 的 history 独立（`user_gpu1/comfyui.db`），8188 浏览器看不到 8189 跑的任务，属预期；以文件名直接取视频即可。

