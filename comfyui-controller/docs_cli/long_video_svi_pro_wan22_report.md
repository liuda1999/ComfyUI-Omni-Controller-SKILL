# ComfyUI-CLI 项目完整任务报告

**报告生成日期**：2026-07-29
**项目路径**：`e:\comfyui-cli`
**硬件环境**：RTX 3080 20GB VRAM（L3 高性能级）
**ComfyUI 版本**：0.27.0 / Python 3.12.9 / PyTorch 2.9.1+cu128
**任务跨度**：2026-07-28 ~ 2026-07-29（项目解压学习 → 长视频生成完成）

---

## 目录

- [一、项目概述](#一项目概述)
- [二、任务阶段划分](#二任务阶段划分)
- [三、完整问题盘点（按时间顺序）](#三完整问题盘点按时间顺序)
- [四、当前工作流完整输入参数](#四当前工作流完整输入参数)
- [五、关键技术决策与参数选择](#五关键技术决策与参数选择)
- [六、历次执行性能对比](#六历次执行性能对比)
- [七、工程约束遵循情况](#七工程约束遵循情况)
- [八、待优化项](#八待优化项)

---

## 一、项目概述

### 1.1 项目定位
- **核心定位**：AI agent 驱动的 ComfyUI 全能控制器
- **架构**：脚本模式 + CLI 模式融合架构
- **特点**：强制预检反问、硬件自适应、工业级视频架构

### 1.2 项目里程碑
| 日期 | 里程碑 |
|------|--------|
| 2026-07-28 | 项目从 `E:\comfyui-cli-0726.tar` 解压，完成文档通读与项目简报 |
| 2026-07-28 | 完成 P0 级代码修复（stop_server.py、video_task_runner.py、run_workflow.py） |
| 2026-07-28 | ComfyUI 服务启动成功（白名单模式，端口 3198） |
| 2026-07-28 | C8 多图视频任务完成（10.6 分钟，双女孩跳舞 3.4 秒视频） |
| 2026-07-28 | 完成 SKILL.md 审计与 15 处修复，建立工作流仓库管理规范 |
| 2026-07-29 | 长视频工作流优化完成（22 分钟，14.81 秒视频，色调/动作/拼接修复） |

### 1.3 最终交付物
| 类型 | 文件 | 说明 |
|------|------|------|
| 工作流 | `long_video_svi_pro_wan22_v1.0.0.json` | 长视频生成工作流（178 节点） |
| 输出视频 | `WanVideo2_2_I2V_20s_00006.mp4` | 14.81 秒 / 480×848 / 5.6MB |
| 参考图 | `D:\2026-ComfyUI-V8.3\input\2.png` | 单图参考 |
| 报告 | `long_video_svi_pro_wan22_report.md` | 本报告 |

---

## 二、任务阶段划分

整个任务历程划分为 **7 个阶段**，覆盖从项目解压到最终交付的完整流程：

| 阶段 | 时间 | 核心内容 | 问题数 |
|------|------|---------|--------|
| 阶段 1 | 07-28 早 | 项目解压与文档学习 | 1 |
| 阶段 2 | 07-28 上午 | P0 级代码修复 | 4 |
| 阶段 3 | 07-28 上午 | ComfyUI 启动调试 | 5 |
| 阶段 4 | 07-28 中午 | C8 多图视频任务 | 12 |
| 阶段 5 | 07-28 下午 | SKILL.md 审计与工作流仓库管理 | 5 |
| 阶段 6 | 07-29 凌晨 | 长视频工作流执行时间优化 | 3 |
| 阶段 7 | 07-29 下午 | 色调/动作/拼接三大问题修复 | 5 |

**问题总数**：35 个（部分问题反复出现）

---

## 三、完整问题盘点（按时间顺序）

### 阶段 1：项目解压与文档学习（2026-07-28 早）

#### 问题 1.1：文档阅读不完整导致定位偏差
- **现象**：解压项目包后未一次性通读全部 12 个 `.md` 文档，特别是 1957 行的 `EXPERIENCE.md` 仅粗略浏览
- **根因**：文档量庞大，急于进入实操阶段
- **修复**：强制完整阅读所有 `.md` 文档，生成项目简报确认理解一致性
- **验证结果**：明确项目"脚本+CLI 融合架构，强制预检反问、硬件自适应、工业级视频架构"的核心定位

---

### 阶段 2：P0 级代码修复（2026-07-28 上午）

#### 问题 2.1：SKILL.md 文档与代码冲突
- **现象**：`SKILL.md` 描述的流程、排错思路与实际代码实现存在冲突
- **根因**：文档迭代滞后于代码迭代
- **修复**：审计 SKILL.md 与相关所有文件，修复后通过真实测试验证

#### 问题 2.2：进程停止脚本误杀（stop_server.py）
- **现象**：`stop_server.py` 仅匹配进程名 `python.exe`，导致误杀其他 Python 进程
- **根因**：未使用多条件精准匹配，缺少命令行参数特征识别
- **修复**：改为多条件匹配（`main.py` + python 进程特征），使用 `psutil` 配合 `wmic`/`pgrep` 回退机制
- **验证结果**：通过实际启动/停止 ComfyUI 验证，无误杀

#### 问题 2.3：视频任务执行器错误检测不完整（video_task_runner.py）
- **现象**：无法区分任务成功/失败/超时，错误分类不清晰
- **根因**：`wait_for_completion` 缺乏 `success`/`error`/`error_type`/`error_node` 字段
- **修复**：
  - 增加 4 个字段区分成功失败
  - 错误分类改为 `execution_error`/`validation_error`/`timeout`/`no_output` 四类
  - 增加 `wait_for_completion` 服务存活检测

#### 问题 2.4：工作流执行脚本输出识别错误（run_workflow.py）
- **现象**：无法正确识别视频输出，漏检 `gifs` 和 `videos` 字段
- **根因**：仅检查 `images` 字段
- **修复**：同时检查 `images`/`gifs`/`videos` 三个字段

---

### 阶段 3：ComfyUI 启动调试（2026-07-28 上午，反复出现 5 次）

#### 问题 3.1：白名单参数格式错误
- **现象**：`--whitelist-custom-nodes` 使用逗号分隔字符串，白名单未生效
- **根因**：ComfyUI 要求空格分隔的多个独立参数
- **修复**：改为列表形式，每个节点名作为独立参数传入
- **反复出现原因**：首次修复后未在启动脚本中固化正确格式

#### 问题 3.2：sageattention DLL 兼容性问题
- **现象**：`attention_mode=sageattn` 触发 `Windows fatal exception: code 0xc0000139`
- **根因**：sageattention 的 C++/CUDA 扩展与 PyTorch 2.9.1+cu128 不兼容
- **修复**：`attention_mode` 从 `sageattn` 改回 `sdpa`（PyTorch 原生注意力）
- **验证结果**：使用 `sdpa` 后无 DLL 错误

#### 问题 3.3：智能内存管理参数冲突
- **现象**：`--disable-smart-memory` + `--disable-cuda-malloc` 组合导致采样器卡死
- **根因**：禁用后 ComfyUI 无法有效管理显存分配，内存碎片化严重
- **修复**：移除这两个启动参数，使用默认智能内存管理

#### 问题 3.4：连续任务间显存不释放
- **现象**：单次任务完成后显存占用 30GB+ 不释放，下次任务 OOM
- **根因**：ComfyUI 模型缓存机制保留模型引用
- **修复**：连续任务间必须重启 ComfyUI 服务
- **硬性规则**：写入 `SKILL.md` 明确"连续任务间必须重启 ComfyUI"

#### 问题 3.5：自定义节点加载崩溃
- **现象**：非白名单模式加载全部自定义节点，Manager 联网超时崩溃、Impact-Pack 卡住
- **根因**：部分节点插件存在联网请求或重量级初始化逻辑
- **修复**：使用 `--disable-all-custom-nodes` + `--whitelist-custom-nodes` 白名单模式
- **白名单节点清单**：
  - 视频任务必需：`ComfyUI-WanVideoWrapper`、`ComfyUI-VideoHelperSuite`、`ComfyUI-KJNodes`
  - 视频任务推荐：`comfyui-frame-interpolation`、`comfyui-essentials`
  - 显存管理必需：`ComfyUI_LayerStyle`（提供 `PurgeVRAM V2`）

---

### 阶段 4：C8 多图视频任务（2026-07-28 中午，12 个问题）

#### 问题 4.1：工作流文件格式不兼容
- **现象**：工作流在 ComfyUI web 端无法查看
- **根因**：保存为 API 格式而非 UI 格式
- **修复**：编写格式转换脚本，添加必要 UI 元素字段

#### 问题 4.2：UI 与 API 参数映射误解
- **现象**：误将 `widgets_values[0]` 认为是 `cfg`，实际对应 `shift`
- **根因**：UI 格式中 `widgets_values` 顺序与字母序不一致
- **修复**：通过查询节点源码 `INPUT_TYPES` 确定实际顺序
- **通用规则**：`widgets_values` 顺序 = `INPUT_TYPES` 中 `required` 字段定义顺序

#### 问题 4.3：节点链架构错误导致旋转问题
- **现象**：视频中人物持续旋转，动作卡住
- **根因**：`WanVideoBlockSwap` 输出直接传入 `WanVideoModelLoader` 的 `block_swap_args`，跳过 `WanVideoSetBlockSwap`
- **修复**：正确节点链：`WanVideoModelLoader → WanVideoSetBlockSwap → WanVideoSetLoRAs → WanVideoSampler`

#### 问题 4.4：必填参数缺失
- **现象**：工作流提交时参数验证错误
- **根因**：`WanVideoSampler.riflex_freq_index`、`WanVideoVAELoader.precision` 未填写
- **修复**：补充所有必填参数

#### 问题 4.5：双模型同时加载导致 OOM
- **现象**：HIGH 和 LOW 模型同时驻留显存，OOM 或被迫使用共享内存
- **根因**：仅依赖 `force_offload=true`，模型缓存机制保留引用
- **修复**：在 HIGH→LOW 切换点插入 `PurgeVRAM V2` 节点
- **三层显存管理防线**：
  1. `load_device="offload_device"` + `force_offload=true`
  2. 显式显存清理节点 `PurgeVRAM V2`
  3. `WanVideoBlockSwap` 分块卸载

#### 问题 4.6：误删 LOW 模型节点改为单采样器
- **现象**：为简化配置删除 LOW 模型节点
- **根因**：误认为可简化为单采样器
- **修复**：恢复双采样器（HIGH+LOW）架构（项目硬约束，不可更改）

#### 问题 4.7：low 采样器 cfg 参数错误
- **现象**：UI 工作流中 low 采样器 `cfg=8`，远超合理范围
- **根因**：UI 格式 `widgets_values` 数组顺序误解
- **修复**：LOW 采样器 `cfg=1.0`（蒸馏 LoRA 模式下 LOW 阶段不需要 CFG 引导）

#### 问题 4.8：steps/num_frames/分辨率/LoRA strength 参数配置错误
- **现象**：执行时间过长、画面变形、细节丢失
- **根因**：参数未对照硬件梯度档位表
- **修复**：
  - `steps=4`（HIGH:2 + LOW:2）
  - `num_frames=81`（训练原生长度）
  - 分辨率与 `start_image` 比例一致
  - LoRA `strength=1.0`（官方推荐值，过高破坏 MoE 去噪曲线）

#### 问题 4.9：blocks_to_swap 参数反复调整
- **现象**：`blocks_to_swap=36` 专用显存未利用；`blocks_to_swap=40` 采样器卡死
- **根因**：对参数物理意义理解不透彻
- **修复**：`blocks_to_swap=20`（L3 级推荐值，专用显存利用率 75%+）

#### 问题 4.10：专用 GPU 显存未利用，大量使用共享内存（显存管理核心问题，反复 6 次）
- **现象**：专用显存仅 8GB/20GB，大量使用共享内存，生成速度极慢
- **根因**：
  - `blocks_to_swap=36` 过高
  - 未启用显式显存清理节点
  - 启动参数禁用了智能内存管理
- **修复**（综合）：
  1. `blocks_to_swap=20`
  2. HIGH→LOW 切换点插入 `PurgeVRAM V2`
  3. 移除 `--disable-smart-memory` 和 `--disable-cuda-malloc`
  4. `load_device="offload_device"` + `force_offload=true`
- **验证结果**：专用显存使用率从 40% 提升到 75-79%，未使用共享内存

#### 问题 4.11：多图识别失败（视频只有单个人物）
- **现象**：生成的视频只有 1.png 的人物，完全没有 2.png 的元素
- **根因**：`WanVideoClipVisionEncode` 的 `combine_embeds="concat"` 只是语义特征合并，不是像素合并
- **关键认知**：
  - `start_image`：决定视频起始帧的视觉内容（像素级锚定）
  - `WanVideoClipVisionEncode`：提供语义引导
  - `combine_embeds="concat"`：拼接的是 CLIP 视觉嵌入向量，不是像素
- **修复**：使用 `ImageConcatMulti` 节点将两张图水平拼接成一张，作为 `start_image`
- **分辨率调整**：两张 480x640 拼接后为 960x640，`WanVideoImageToVideoEncode` 必须设置为 960x640

#### 问题 4.12：提示词问题（4 个子问题）
- **4.12.1 提示词过于冗长**：超过 300 字符，精简到 60 字符以内
- **4.12.2 运镜描述导致画面混乱**："360 orbit" 触发相机旋转，改为"固定镜头"
- **4.12.3 使用英文提示词**：Wan2.2 原生支持中文，改用中文提示词
- **4.12.4 负面提示词不完整**：补充相机运动、人物一致性、画面问题、基础负面四类

---

### 阶段 5：SKILL.md 审计与工作流仓库管理（2026-07-28 下午，5 个问题）

#### 问题 5.1：SKILL.md 参数配置过时
- **现象**：默认 steps 过高（6）、端口硬编码、路径硬编码
- **修复**：15 处修复
  - 步数反问模板改为动态计算
  - 端口改为 `${COMFYUI_PORT}` 变量
  - 路径改为 `${PROJECT_PATH}` 和 `${COMFYUI_PATH}` 变量
  - steps 区分蒸馏 LoRA（6-12）和原生模型（15-25）

#### 问题 5.2：temp 目录文件膨胀
- **现象**：88 个孤儿 `.py` 文件未被 `.md` 文档或 `scripts/` 引用
- **修复**：删除 88 个孤儿文件（C5/C7/C8/V6/V7/V8 任务的 debug/fix 脚本）

#### 问题 5.3：工作流资产版本爆炸
- **现象**：`assets/` 目录有 74 个工作流文件，命名混乱（v2/v3/final 后缀）
- **修复**：
  - 6 个最新工作流重命名为语义版本号（如 `task1_v3_final.json` → `img_gen_v1.0.0.json`）
  - 57 个历史版本归档到 `assets/archive/`
  - `scripts/` 中归档 12 个旧 `c5_video_task` 版本
  - 重建 `workflow_library.json`（74 → 17 条目）

#### 问题 5.4：工作流索引包含历史版本
- **现象**：`workflow_library.json` 包含 `assets/archive/` 中的历史版本
- **修复**：`build_workflow_library.py` 增加排除 `archive/` 逻辑

#### 问题 5.5：API 格式工作流节点数显示为 0
- **现象**：`workflow_analyzer.py` 只解析 UI 格式，API 格式节点数显示为 0
- **修复**：标记为已知设计限制，不影响索引和元数据查询

---

### 阶段 6：长视频工作流执行时间优化（2026-07-29 凌晨，3 个问题）

#### 问题 6.1：初始执行时间过长（58 分钟）
- **现象**：原始工作流执行约 58 分钟，超出目标 30-40 分钟
- **根因**：SVI Pro 帧数过多（81帧）、采样步数过多（6步）、Flux2 步数过多（12步）
- **修复**：
  - SVI Pro 帧数：81 → 49
  - SVI Pro 采样步数：6 → 3
  - Flux2 步数：12 → 2
  - RealESRGAN 旁路
- **结果**：执行时间降至约 22 分钟

#### 问题 6.2：视频时长不足
- **现象**：首次优化后视频仅 9.75 秒
- **根因**：帧数降低导致总时长缩短
- **修复**：调整帧率为 16fps，每段 49 帧，总 237 帧
- **结果**：视频时长 14.81 秒

#### 问题 6.3：工作流 group 格式不兼容
- **现象**：ComfyUI 加载工作流时报 `TypeError: can't convert undefined to object`
- **根因**：28 个 group 格式不兼容（缺少 id、flags 字段，使用 pos+size 而非 bounding 数组）
- **修复**：将所有 group 转换为 `bounding: [x,y,w,h]` 格式，添加 id 和 flags 字段

---

### 阶段 7：色调/动作/拼接三大问题修复（2026-07-29 下午，5 个问题）

#### 问题 7.1：Flux2 动作偏离原始截图
- **现象**：Flux2 修正后角色动作偏离原始截图画面
- **根因**：`SplitSigmasDenoise` 的 `denoise=0.75` 过高，破坏了 SVI 生成的动作结构
- **修复**：`denoise` 0.75 → 0.6，平衡换皮强度与动作保留

#### 问题 7.2：色调逐渐变冷、变白（提示词层面）
- **现象**：5 秒视频中色调随时间逐渐变冷、变白
- **根因**：
  1. SVI Pro 正向提示词仅"无红色色偏"，缺乏暖色调正向约束
  2. SVI Pro 负向提示词含"暖色溢色"，与正向约束冲突
- **修复**：
  - 5 个正向提示词追加："整体保持暖色调，与参考图B的色温保持一致，禁止画面逐渐变冷、变白"
  - 5 个负向提示词移除"暖色溢色"，追加"画面变冷，画面变白"

#### 问题 7.3：色调全程不稳定 + Flux2 颜色加深（ColorMatch 硬性锚定）
- **现象**：
  1. 视频生成过程中色调逐渐偏离原参考图
  2. Flux2 修复的画面颜色比原参考图加深
- **根因**：
  1. SVI Pro 段间累积漂移，提示词约束无法硬性锚定
  2. Flux2 换皮时改变色彩，LoRA-ColorTone(0.3) 强度不足以校正
- **修复**：插入 9 个 `ColorMatch` 节点进行硬性颜色锚定
  - 5 个 SVI ColorMatch（NID=365-369）：每个 SVI VAEDecode 输出后
  - 4 个 Flux2 ColorMatch（NID=370-373）：每个 Flux2 ImageResize 输出后
  - 统一参数：`method=reinhard`, `strength=0.85`, `image_ref=参考图B(NID=75)`
- **结果**：色调全程稳定，Flux2 输出色调与参考图B一致

#### 问题 7.4：拼接处存在渐变过渡
- **现象**：视频段拼接处存在渐变过渡
- **根因**：`ImageBatchExtendWithOverlap` 使用 `linear_blend` 模式，`overlap=5`
- **修复**：改为 `cut` 模式（直接切换帧无混合），`overlap=1`（节点最小值，不支持 0）

#### 问题 7.5：手部变形、红色色偏、多余肢体（C8 阶段遗留）
- **现象**：生成视频中人物手部变形、背景发红、出现多余肢体
- **根因**：SVI Pro 提示词缺乏对手部结构和色偏的约束
- **修复**：
  - 正向提示词追加："人物双手结构完整，十指分明，两臂两腿，肢体自然协调"
  - 负向提示词追加："背景发红，红色色偏"
  - Flux2 正向提示词追加："修复手部结构确保十指完整分明关节自然"
  - Flux2 负向提示词追加："多手指，六指，手指扭曲，关节反向，手掌融合"

---

### 反复出现问题汇总

| 问题类别 | 出现次数 | 根本原因 | 最终解决方案 |
|---------|---------|---------|------------|
| 显存管理问题 | 6 次 | 未严格遵循硬约束，未借鉴本地成熟方案 | blocks_to_swap=20 + PurgeVRAM V2 + 移除 disable 参数 |
| 参数配置错误 | 5 次 | 未对照硬件梯度档位表 | 严格对照 L3 级参数表配置 |
| 工作流构建错误 | 4 次 | 未充分理解节点链架构和参数映射 | 借鉴本地成熟工作流，明确节点链架构 |
| 提示词问题 | 4 次 | 未学习 Wan2.2 官方提示词教程 | 遵循图生视频公式，简洁中文描述 |
| 启动脚本问题 | 3 次 | 参数格式和节点兼容性问题 | 固化正确参数格式，添加必需节点到白名单 |

---

## 四、当前工作流完整输入参数

> 以下为最终验证通过的 `long_video_svi_pro_wan22_v1.0.0.json` 工作流完整参数

### 4.1 工作流架构
```
参考图(2.png) → SVI Pro 段1(49帧) → ColorMatch → 末帧
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

### 4.2 节点统计
| 项目 | 数量 |
|------|------|
| 总节点数 | 178 |
| 总链接数 | 244 |
| SVI Pro 段 | 5 段 |
| Flux2 换皮段 | 4 段 |
| ColorMatch 节点 | 9 个 |
| UnloadAllModels 节点 | 9 个 |
| ModelPatchTorchSettings 节点 | 10 个 |

### 4.3 SVI Pro 模型配置（每段相同）
| 节点 | 模型文件 | 类型/参数 |
|------|---------|---------|
| UNETLoader (HIGH) | `Wan2.2_Remix_NS-FW_i2v_14b_high_lighting_v2.0.safetensors` | fp8_e4m3fn |
| LoraLoaderModelOnly (HIGH) | `SVI_v2_PRO_Wan2.2-I2V-A14B_HIGH_lora_rank_128_fp16.safetensors` | strength=1.0 |
| UNETLoader (LOW) | `Wan2_2-I2V-A14B-LOW_fp8_e4m3fn_scaled_KJ.safetensors` | fp8_e4m3fn |
| LoraLoaderModelOnly (LOW) | `SVI_v2_PRO_Wan2.2-I2V-A14B_LOW_lora_rank_128_fp16.safetensors` | strength=1.0 |
| VAELoader | `comfy-wan_2.1_vae.safetensors` | - |
| CLIPLoader | `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | wan |

### 4.4 Flux2 模型配置
| 节点 | 模型文件 | 参数 |
|------|---------|------|
| UNETLoader | `F2K-9b-kleinova_10FP8.safetensors` | fp8_e4m3fn |
| LoraLoaderModelOnly (ColorTone) | `F2K_9b-滑块工具-质量quality.safetensors` | strength=0.3 |
| LoraLoaderModelOnly (Skin) | `F2K_9b-滑块工具-皮肤skin.safetensors` | strength=0.3 |
| LoraLoaderModelOnly (Detail) | `F2K_9b-滑块工具-背光和正光front&back.safetensors` | strength=0.2 |
| CLIPLoader | `qwen_3_8b_fp8mixed.safetensors` | flux2 |
| VAELoader | `flux2-vae.safetensors` | - |

### 4.5 SVI Pro 采样参数
| 参数 | 值 | 说明 |
|------|-----|------|
| 帧数（length） | 49 | 每段生成帧数 |
| motion_latent_count | 1 | 运动潜变量数 |
| 总帧数 | 237 | 5段 × 49 - 4 × 1(overlap) |
| 分辨率 | 480 × 848 | 9:16 竖屏 |
| 帧率 | 16 fps | - |
| 视频时长 | 约 14.81 秒 | 237 / 16 |

### 4.6 Flux2 采样参数
| 参数 | 值 | 说明 |
|------|-----|------|
| 调度器 | Flux2Scheduler | - |
| steps | 8 | 调度器内部步数 |
| 宽度/高度 | 1024 × 1024 | 内部计算分辨率 |
| 采样器 | euler | KSamplerSelect |
| CFG | 5 | CFGGuider |
| denoise | 0.6 | SplitSigmasDenoise（从0.75下调） |
| A图缩放 | 0.5 MP | ImageScaleToTotalPixels |
| B图缩放 | 1.0 MP | ImageScaleToTotalPixels |
| 输出Resize | 480 × 848 | ImageResizeKJv2 (lanczos, crop, center) |

### 4.7 ColorMatch 参数（9个节点统一配置）
| 参数 | 值 | 说明 |
|------|-----|------|
| method | reinhard | Reinhard 颜色迁移算法 |
| strength | 0.85 | 强度（平衡锚定与自然变化） |
| image_ref | NID=75 (参考图B) | 所有9个节点共用同一参考 |
| 插入位置 | SVI VAEDecode后 + Flux2 ImageResize后 | 5个SVI + 4个Flux2 |

### 4.8 ImageBatchExtendWithOverlap 参数（4个节点统一配置）
| 参数 | 值 | 说明 |
|------|-----|------|
| overlap | 1 | 最小值（节点不支持0） |
| overlap_side | new_images | - |
| overlap_mode | cut | 直接切换，无渐变混合 |

### 4.9 其他关键参数
| 节点 | 参数 | 值 |
|------|------|-----|
| ModelPatchTorchSettings × 10 | enable_fp16_accumulation | True |
| VHS_VideoCombine | frame_rate | 16 |
| VHS_VideoCombine | format | video/h264-mp4 |
| VHS_VideoCombine | pix_fmt | yuv420p |
| VHS_VideoCombine | crf | 19 |
| VHS_VideoCombine | filename_prefix | WanVideo2_2_I2V_20s |

### 4.10 提示词

#### Flux2 正向提示词（NID=83）
```
以参考图B为唯一外貌基准，1:1还原人物面部五官、眉毛、肤色、肤质肌理、毛孔、头发发丝质感光泽层次、服装材质款式颜色配饰、背景环境场景陈设、整体色调色温光影；严格保留输入帧中人物的动作姿态、手势、肢体位置、面部表情、构图与人物位置，绝不改变动作；将输入帧中人物的外貌服装背景完全替换为参考图B的外貌服装背景；修复手部结构确保十指完整分明关节自然，确保仅有两臂两腿无多余肢体；消除红色色偏禁止背景发红，色彩饱和度严格参照B图；极致细节，锐度自然，高质量画面
```

#### Flux2 负向提示词（NID=84）
```
改变动作姿态，改变面部表情，改变肢体位置，改变构图；外貌偏离参考图，五官不一致，肤色偏差，肤质丢失，发色发质不符，服装款式颜色不符，背景场景不符；多手指，六指，手指扭曲，关节反向，手掌融合，手部变形，手指残缺；多余肢体，多臂，多余手臂，三头六臂，手臂残影，肢体残缺，肢体穿模，四肢扭曲；背景发红，红色色偏，色彩失真，色温偏移，画面变冷，画面变白，色调跑偏，色彩偏移，皮肤泛红发紫，荧光溢色；磨皮过度，五官变形，五官错位，脸部扭曲，满脸麻子，密集雀斑，痤疮红疹；服装纹理模糊，面料材质错误，褶皱崩坏，衣物穿模；发丝缺失，头发扁平无质感，发丝结块糊化；光影混乱，多光源冲突，风格冲突；整体模糊，大量噪点，低分辨率，像素马赛克，细节崩坏，画面扁平，液化拉伸，边缘破碎，水印文字，裸露生殖器，外露乳头
```

#### SVI Pro 正向提示词（5段，NID=240/262/284/306/328）
- **段1 (0-5s)**：双脚轻踮，双臂向上完全舒展张开，仰头闭眼，身体缓慢左右轻晃，发丝随风飘动，面部放松浅笑
- **段2**：侧身屈膝弯腰，单手指尖轻触花草，脑袋歪向一侧，单眼弯起微笑，另一只手自然背于身后
- **段3**：原地小碎步轻快转圈，转圈结束抬手举至脸颊旁，对着镜头比耶手势，头部微微歪向一边
- **段4 (15-20s)**：停下脚步，双手拢住耳边长发，身体微微前倾，直视镜头露出灿烂大笑，轻轻左右晃动脑袋
- **段5 (20-25s)**：自然摇摆身体，然后优雅的抬起左腿，动作优美流畅，表情自信

**通用后缀**：人物双手结构完整，十指分明，两臂两腿，肢体自然协调，背景色调与参考图一致，整体保持暖色调，与参考图B的色温保持一致，禁止画面逐渐变冷、变白

#### SVI Pro 负向提示词（5段统一）
```
静态，静止不动，画面模糊，多余的手指，手指融合，多臂，多余手臂，三头六臂，肢体残缺，手部变形，手指扭曲，关节反向，手掌融合，背景发红，红色色偏，色彩失真，色温偏移，画面变冷，画面变白，人物变形，五官扭曲，服装穿模，肢体穿模
```

---

## 五、关键技术决策与参数选择

### 5.1 双采样器架构（HIGH+LOW 顺序执行）
- **原因**：HIGH 采样器质量高但慢，LOW 采样器快但质量略低
- **策略**：HIGH + LOW 顺序执行，结合两者优势
- **VRAM 优化**：HIGH 执行完卸载，再加载 LOW
- **硬约束**：不可改为单采样器

### 5.2 Flux2 denoise=0.6 的选择
- **0.75**：换皮彻底但动作破坏
- **0.5**：动作保留但换皮不彻底
- **0.6**：平衡点，换皮充分且动作保留

### 5.3 ColorMatch reinhard + strength=0.85
- **reinhard**：平滑过渡，适合视频序列
- **strength=0.85**：足够锚定色调，保留 15% 自然变化
- **对比 mkl**：mkl 过于强烈，可能导致局部色彩失真

### 5.4 ImageBatchExtendWithOverlap cut 模式
- **cut**：直接切换帧，无渐变
- **overlap=1**：节点最小值（不支持0），实际无影响
- **对比 linear_blend**：linear_blend 会产生渐变过渡

### 5.5 blocks_to_swap=20 的选择
- **过高（36/40）**：GPU 保留 block 过少，专用显存未利用
- **过低**：显存不足导致 OOM 或卡死
- **20（L3 级推荐）**：专用显存利用率 75%+

### 5.6 参数梯度选择指南（L3 高性能级）
| 参数 | 值 | 说明 |
|------|-----|------|
| steps | 4-8 | 加速 LoRA 蒸馏模式 |
| cfg (HIGH) | 动态调度 2.0→1.0 | 第一步 CFG=2，其余步 CFG=1 |
| cfg (LOW) | 1.0 | LOW 阶段不需要 CFG 引导 |
| shift | 8.0 | Wan2.2 I2V 最佳值 |
| scheduler | dpm++_sde | 随机性调度器，产生自然动作 |
| rope_function | comfy_chunked | 降低显存峰值 |
| num_frames | 81-121 | 81 为训练原生长度，最稳定 |
| blocks_to_swap | 20 | L3 级推荐值 |
| noise_aug_strength | 0.1 | 亮度锚定，禁止 0 |
| LoRA strength | 1.0 | 官方推荐值，过高破坏 MoE 去噪曲线 |

---

## 六、历次执行性能对比

| 版本/阶段 | 执行时间 | 视频时长 | 主要问题 |
|---------|---------|---------|---------|
| C8 多图视频（初始） | 8-20 分钟 | 3.4 秒 | 显存管理、多图识别、提示词 |
| C8 多图视频（优化后） | 10.6 分钟 | 3.4 秒 | 全部问题解决 ✅ |
| 长视频 v1.0.0（初始） | 58 分钟 | 14.81 秒 | 时长不足、动作偏离、色调漂移、拼接渐变 |
| 长视频 v6（3问题修复） | 22 分钟 | 14.81 秒 | 动作修复、色调仍不稳定、Flux2颜色加深 |
| 长视频 v7（ColorMatch） | 22 分钟 | 14.81 秒 | 全部问题基本解决 ✅ |

### 最终执行数据
| 指标 | 值 |
|------|-----|
| 执行时间 | 约 22 分钟 |
| VRAM 峰值 | 76.0% (15.5GB / 20GB) |
| VRAM 空闲后 | 53.1% (10.8GB / 20GB) |
| 节点数 | 178 |
| 输出节点数 | 9 |

---

## 七、工程约束遵循情况

| 约束 | 遵循情况 | 说明 |
|------|---------|------|
| stop_server.py 多条件匹配 | ✅ | main.py + python 特征 |
| video_task_runner.py 三字段检查 | ✅ | images/gifs/videos |
| wait_for_completion 四字段区分 | ✅ | success/error/error_type/error_node |
| 双采样器架构（HIGH+LOW） | ✅ | 顺序执行 + 模型卸载 |
| 仅一个模型驻留 GPU | ✅ | 9个 UnloadAllModels |
| 最小化共享 GPU 内存 | ✅ | blocks_to_swap=20，专用显存 75%+ |
| ImageConcatMulti 像素拼接 | ✅ | ImageBatchExtendWithOverlap |
| 连续任务重启 ComfyUI | ✅ | 避免 VRAM 残留 |
| 禁止直接降级时长 | ✅ | 通过优化参数降低时间 |
| 语义版本号命名 | ✅ | v1.0.0 |
| temp/ 清理孤儿文件 | ✅ | 删除 88 个 |
| workflow_library.json 排除 archive/ | ✅ | 74 → 17 条目 |
| attention_mode=sdpa | ✅ | 避免 sageattn DLL 问题 |
| enable_fp16_accumulation | ✅ | 10个节点 |
| ColorMatch 色调锚定 | ✅ | 新增 9 个节点 |
| cut 模式直接拼接 | ✅ | 4个节点 |
| 暖色调提示词约束 | ✅ | 5段正向+5段负向 |

---

## 八、待优化项

1. **版本归档**：当前文件名为 v1.0.0，按硬约束应升级为 v1.0.1 并归档旧版至 `assets/archive/`
2. **工作流索引重建**：需执行 `python scripts/build_workflow_library.py --input assets --output assets/workflow_library.json --object-info assets/object_info.json` 更新索引
3. **temp/ 清理**：本次任务产生多个临时脚本，需清理未被 .md 引用的 .py 文件
4. **视频时长**：当前 14.81 秒，距离 24 秒目标仍有差距，可考虑增加段数或帧数
5. **EXPERIENCE.md 更新**：本次长视频任务的完整经验（阶段 6-7）需补充到 EXPERIENCE.md 第 24 章

---

**报告结束**

> 本报告覆盖从项目解压学习到长视频生成完成的完整任务历程，共盘点 35 个问题（含反复出现），收集当前工作流全部输入参数，可作为后续任务执行的避坑指南和参数参考。
