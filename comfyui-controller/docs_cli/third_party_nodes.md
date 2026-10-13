# MiniMax H3 工作流 · 节点依赖索引

> **用途**：本索引登记项目内 6 个 MiniMax H3 工作流所引用的**全部 88 种节点类型**，
> 标注每类节点的所属节点包、GitHub 仓库、功能说明与安装方式。
> 其他智能体/使用者据此装齐节点包与模型，即可把工作流加载进 ComfyUI 直接运行。

> 生成日期：2026-10-13 (updated)｜节点类型 88 种（已确认 86，待确认 2）｜节点包 24 个

> 📎 **旧工作流（MiniMax 之外）的节点依赖索引见 [legacy_workflow_nodes.md](legacy_workflow_nodes.md)**（**70 个历史工作流**：顶层 16 + `archive/` 54；19 个第三方包；11 个不在 object_info 中的节点：7 个前端虚拟节点 + 4 个后端缺失节点）。
> 两个索引共用同一份机器可读来源 **`assets/node_registry.json`**（共 **39 个包 / 177 个节点类型**）。

***

## 1. 一键安装节点包

在 `ComfyUI/custom_nodes/` 下执行（核心包 `ComfyUI-Core` 无需安装）：

```bash
cd <你的 ComfyUI>/custom_nodes
# AraneaQwQ/ComfyUI-H3-ClipStream  （需 ComfyUI ≥ 0.34.0）
git clone https://github.com/AraneaQwQ/ComfyUI-H3-ClipStream.git  &&  pip install -r ComfyUI-H3-ClipStream/requirements.txt
# Derfuu/Derfuu_ComfyUI_ModdedNodes
git clone https://github.com/Derfuu/Derfuu_ComfyUI_ModdedNodes.git
# HM-RunningHub/ComfyUI_RH_MinMaxH3
git clone https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3.git  &&  pip install -r ComfyUI_RH_MinMaxH3/requirements.txt
# Kosinkadink/ComfyUI-VideoHelperSuite
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
# LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler
git clone https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler.git；权重 hf download LBH-123-AI/Minimax_h3_latent_Upscaler → models/latent_upscale_models/
# Larryvrh/ComfyUI-MiniMax-H3-Turbo
git clone https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo.git
# MieMieeeee/ComfyUI-MieNodes
git clone https://github.com/MieMieeeee/ComfyUI-MieNodes.git
# NikoDemon80/ComfyUI-H3-Motion-Context  （需 ComfyUI ≥ 0.34.0）
git clone https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context.git
# Suzie1/ComfyUI_Comfyroll_CustomNodes
git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git
# Windecay/ComfyUI-ReservedVRAM
git clone https://github.com/Windecay/ComfyUI-ReservedVRAM.git
# beijinren/ComfyUI-H3-Context-Noise
git clone https://github.com/beijinren/ComfyUI-H3-Context-Noise.git
# cubiq/ComfyUI_essentials
git clone https://github.com/cubiq/ComfyUI_essentials.git
# facok/comfyui-SelfLift
git clone https://github.com/facok/comfyui-SelfLift.git
# kijai/ComfyUI-KJNodes
git clone https://github.com/kijai/ComfyUI-KJNodes.git  &&  pip install -r ComfyUI-KJNodes/requirements.txt
# knoic/ComfyUI-MiniMaxH3-PrefixStream
git clone https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream.git  &&  pip install -r requirements.txt
# ltdrdata/ComfyUI-Impact-Pack
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git
# ooizj/ComfyUI-H3-Long-Video  （需 ComfyUI ≥ 0.36.0；与原版 H3 Motion Context 冲突，二者只装其一）
git clone https://github.com/ooizj/ComfyUI-H3-Long-Video.git comfyui-h3-long-video
# pythongosssss/ComfyUI-Custom-Scripts
git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git
# rgthree/rgthree-comfy
git clone https://github.com/rgthree/rgthree-comfy.git
# tl2012tl/TE_MAN
git clone https://github.com/tl2012tl/TE_MAN.git
# vrgamegirl19/comfyui-vrgamedevgirl
git clone https://github.com/vrgamegirl19/comfyui-vrgamedevgirl.git  &&  pip install -r requirements.txt
# yichengup/ComfyUI-YCNodes-MiniMax-H3
git clone https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3.git
# yolain/ComfyUI-Easy-Use
git clone https://github.com/yolain/ComfyUI-Easy-Use.git
```

> 也可用 ComfyUI-Manager 按包名搜索安装。个别包有**互斥关系**：
> `ComfyUI-H3-Motion-Context` 与 `ooizj/ComfyUI-H3-Long-Video` 注册同名节点 ID，**二者只装其一**。

***

## 2. 节点包清单

| 节点包 | GitHub 仓库 | 功能 | 许可证 |
|-------|------------|------|--------|
| `AraneaQwQ/ComfyUI-H3-ClipStream` | https://github.com/AraneaQwQ/ComfyUI-H3-ClipStream | H3 长视频片段库(Clip Bin) + 运动上下文续接(Motion Context)，含双采(一采/二采)卡片管理 | GPL-3.0（整合 NikoDemon80 Motion-Context GPLv3 + knoic PrefixStream MIT） |
| `ComfyUI-Core` | https://github.com/comfyanonymous/ComfyUI | ComfyUI 官方核心节点 | GPL-3.0 |
| `Derfuu/Derfuu_ComfyUI_ModdedNodes` | https://github.com/Derfuu/Derfuu_ComfyUI_ModdedNodes | 数学/类型转换节点（DF_Int_to_Float） | MIT |
| `HM-RunningHub/ComfyUI_RH_MinMaxH3` | https://github.com/HM-RunningHub/ComfyUI_RH_MinMaxH3 | RunningHub 的 MiniMax-H3 本地音视频扩散节点（T2VA/FL2VA/Ref2VA 三路径），24GB 单卡可跑 | Apache-2.0（权重另循 H3 社区许可） |
| `Kosinkadink/ComfyUI-VideoHelperSuite` | https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite | 视频加载/合成（VHS_VideoCombine 输出 MP4+音频） | GPL-3.0 |
| `LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler` | https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler | H3 24 通道 VAE latent 的 3D 学习式放大 + MMH3 分块拼接上采样 | 见仓库 |
| `Larryvrh/ComfyUI-MiniMax-H3-Turbo` | https://github.com/Larryvrh/ComfyUI-MiniMax-H3-Turbo | 4 步 Turbo LoRA + 双调度采样器（H3 加速） | Apache-2.0 |
| `MieMieeeee/ComfyUI-MieNodes` | https://github.com/MieMieeeee/ComfyUI-MieNodes | 工具节点包（ShowAnything 调试显示） | MIT |
| `NikoDemon80/ComfyUI-H3-Motion-Context` | https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context | H3 片段链式续接：把上一段尾部 latent 与音频钉入下一段，画面/声音真正连续 | GPL-3.0 |
| `Suzie1/ComfyUI_Comfyroll_CustomNodes` | https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes | 文本/提示词工具（CR Prompt Text、CR Text Concatenate） | GPL-3.0 |
| `Windecay/ComfyUI-ReservedVRAM` | https://github.com/Windecay/ComfyUI-ReservedVRAM | 预留显存设置节点（ReservedVRAMSetter，低显存环境防止 OOM） | 见仓库 |
| `beijinren/ComfyUI-H3-Context-Noise` | https://github.com/beijinren/ComfyUI-H3-Context-Noise | H3 上下文潜空间渐隐加噪（长视频/多段续接时平滑上下文尾帧），实验性 | MIT |
| `cubiq/ComfyUI_essentials` | https://github.com/cubiq/ComfyUI_essentials | 常用工具节点（ImageResize+ 等） | MIT |
| `facok/comfyui-SelfLift` | https://github.com/facok/comfyui-SelfLift | 渐进式分辨率采样（低分辨率前缀→提升→高分辨率收尾），含 H3 实验性适配 | 见仓库 |
| `kijai/ComfyUI-KJNodes` | https://github.com/kijai/ComfyUI-KJNodes | KJ 实用节点集；含 MiniMax H3 实验性补丁（低显存三件套） | Apache-2.0 |
| `knoic/ComfyUI-MiniMaxH3-PrefixStream` | https://github.com/knoic/ComfyUI-MiniMaxH3-PrefixStream | H3 片段素材池（Clip Bin Saver/Picker 带评分与预览卡片） | MIT |
| `ltdrdata/ComfyUI-Impact-Pack` | https://github.com/ltdrdata/ComfyUI-Impact-Pack | Impact 节点包（ImpactSwitch 分支开关） | GPL-3.0 |
| `ooizj/ComfyUI-H3-Long-Video` | https://github.com/ooizj/ComfyUI-H3-Long-Video | 一句话+总时长直出 H3 长视频：自动分段、逐段续接、裁重叠、24fps 拼接（基于 H3 Motion Context 改造） | 见仓库 |
| `pythongosssss/ComfyUI-Custom-Scripts` | https://github.com/pythongosssss/ComfyUI-Custom-Scripts | 前端增强与实用节点（Text Multiline、玩声音提示等） | MIT |
| `rgthree/rgthree-comfy` | https://github.com/rgthree/rgthree-comfy | 分组开关/种子等实用节点（Fast Groups Bypasser、Seed） | MIT |
| `tl2012tl/TE_MAN` | https://github.com/tl2012tl/TE_MAN | 文本/条件显示与调试节点（TE_text_display 等） | 见仓库（含 LICENSE 文件） |
| `vrgamegirl19/comfyui-vrgamedevgirl` | https://github.com/vrgamegirl19/comfyui-vrgamedevgirl | 视频对比/增强工具（VRGDG_VideoCompareSlider 前后对比滑块） | VRGameDevGirl Community/Commercial |
| `yichengup/ComfyUI-YCNodes-MiniMax-H3` | https://github.com/yichengup/ComfyUI-YCNodes-MiniMax-H3 | H3 Sigma Refiner：在低 sigma 段加局部微雕，缓解高速运动物体边缘颗粒/闪烁 | 见仓库 |
| `yolain/ComfyUI-Easy-Use` | https://github.com/yolain/ComfyUI-Easy-Use | easy 系列实用节点（清缓存/清显存/显示/浮点/布尔） | MIT |

***

## 3. 第三方节点 → 节点包 对照表

| 节点类名 | 所属包 | 功能说明 |
|---------|--------|---------|
| `1e83e52d-c4d4-4071-be6f-2ad81c64b715` | `yolain/ComfyUI-Easy-Use` | ComfyUI-Easy-Use 的 If else 布尔任意类型开关：boolean, on_true(*), on_false(*) → (*)。本工作流中 ComfyUI 因源环境缺包将其 class_type 替换为 UUID。 |
| `7a522690-eadb-45bc-b4b8-4fbf5b09e1a0` | `yolain/ComfyUI-Easy-Use` | ComfyUI-Easy-Use 的 If else 布尔任意类型开关：boolean, on_true(*), on_false(*) → (*)。本工作流中 ComfyUI 因源环境缺包将其 class_type 替换为 UUID。 |
| `CR Prompt Text` | `Suzie1/ComfyUI_Comfyroll_CustomNodes` | 提示词文本节点 |
| `CR Text Concatenate` | `Suzie1/ComfyUI_Comfyroll_CustomNodes` | 文本拼接 |
| `DF_Int_to_Float` | `Derfuu/Derfuu_ComfyUI_ModdedNodes` | 整数→浮点转换 |
| `EasyCache` | `yolain/ComfyUI-Easy-Use` | 易用缓存（加速） |
| `Fast Groups Bypasser (rgthree)` | `rgthree/rgthree-comfy` | 分组旁路开关 |
| `GetNode` | `kijai/ComfyUI-KJNodes` | 按名称取回 SetNode 存入的值 |
| `H3 Long Video Manager` | `ooizj/ComfyUI-H3-Long-Video` | 长视频统一编排管理器：一句话+总时长直出 H3 长视频（自动分段、逐段续接、裁重叠、拼接） |
| `H3 Segment Picker` | `ooizj/ComfyUI-H3-Long-Video` | 长视频分段选择节点：挑选/定位已生成的分段片段 |
| `H3SigmaRefiner` | `yichengup/ComfyUI-YCNodes-MiniMax-H3` | H3 sigma 精修（缓解边缘颗粒/闪烁） |
| `ImageResize+` | `cubiq/ComfyUI_essentials` | 图片缩放 |
| `ImpactSwitch` | `ltdrdata/ComfyUI-Impact-Pack` | 条件分支开关 |
| `MMH3TemporalSplitParams` | `LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler` | MMH3 分块上采样-时间切分参数 |
| `MiniMaxChunkFeedForward` | `kijai/ComfyUI-KJNodes` | H3 分块前馈（降低激活峰值，输出等价） |
| `MiniMaxClipBinDualPicker` | `AraneaQwQ/ComfyUI-H3-ClipStream` | 双采片段选择(可视化卡片) |
| `MiniMaxClipBinDualSaver` | `AraneaQwQ/ComfyUI-H3-ClipStream` | 双采片段入库(一采+二采) |
| `MiniMaxH3ContextLatentTaperNoise` | `beijinren/ComfyUI-H3-Context-Noise` | H3 上下文潜空间渐隐加噪（长视频/多段续接时平滑上下文尾帧），实验性节点 |
| `MiniMaxH3MemoryEfficientSageAttentionPatch` | `kijai/ComfyUI-KJNodes` | H3 显存友好的 SageAttention 补丁 |
| `MiniMaxH3MotionContextClipStream` | `AraneaQwQ/ComfyUI-H3-ClipStream` | 运动上下文续接（尾部 latent+音频钉入） |
| `MiniMaxH3TurboLoRA` | `Larryvrh/ComfyUI-MiniMax-H3-Turbo` | Turbo LoRA（4 步加速） |
| `MiniMaxH3TurboSampler` | `Larryvrh/ComfyUI-MiniMax-H3-Turbo` | Turbo 双调度采样器 |
| `MiniMaxLowVRAMAttention` | `kijai/ComfyUI-KJNodes` | H3 低显存注意力（头分组） |
| `MinimaxH3LatentUpscaler3D` | `LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler` | H3 latent 3D 学习式放大 |
| `ModelPreviewOverrideKJ` | `kijai/ComfyUI-KJNodes` | 覆盖模型预览 |
| `PathchSageAttentionKJ` | `kijai/ComfyUI-KJNodes` | Patch SageAttention 加速 |
| `RHMiniMaxH3DecodeAV` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | 解码视频 + 音频 |
| `RHMiniMaxH3DualSigmaSampler` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | 双 sigma 采样器（视频/音频独立调度） |
| `RHMiniMaxH3EmptyAVLatent` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | 空 AV 潜空间 |
| `RHMiniMaxH3FL2VAEncode` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | FL2VA 条件编码 |
| `RHMiniMaxH3FL2VAFirstFrameCondition` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | FL2VA 首帧 / 首+尾帧条件 |
| `RHMiniMaxH3FL2VAModelLoader` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | FL2VA 模型加载器（DiT） |
| `RHMiniMaxH3FL2VATarget` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | FL2VA 目标（AV 潜空间初始化） |
| `RHMiniMaxH3FL2VATextEncoderLoader` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | FL2VA Qwen3-VL 文本编码器加载器 |
| `RHMiniMaxH3FL2VAVAELoader` | `HM-RunningHub/ComfyUI_RH_MinMaxH3` | FL2VA 双 VAE 加载器（视频+音频） |
| `ReservedVRAMSetter` | `Windecay/ComfyUI-ReservedVRAM` | 预留显存设置节点：为其他进程预留固定显存，低显存环境防止 OOM |
| `Seed (rgthree)` | `rgthree/rgthree-comfy` | 固定种子节点 |
| `SelfLiftH3Sampler` | `facok/comfyui-SelfLift` | H3 渐进式分辨率采样（实验） |
| `SetNode` | `kijai/ComfyUI-KJNodes` | 按名称暂存值 |
| `ShowAnything|Mie` | `MieMieeeee/ComfyUI-MieNodes` | 显示任意输入为字符串（调试） |
| `TE_text_display` | `tl2012tl/TE_MAN` | 文本/条件显示调试节点（在画布上显示文本或条件内容） |
| `Text Multiline` | `pythongosssss/ComfyUI-Custom-Scripts` | 多行文本输入 |
| `VHS_LoadVideo` | `Kosinkadink/ComfyUI-VideoHelperSuite` | 加载视频为帧序列 |
| `VHS_VideoCombine` | `Kosinkadink/ComfyUI-VideoHelperSuite` | 合成 MP4（含音频） |
| `VRGDG_VideoCompareSlider` | `vrgamegirl19/comfyui-vrgamedevgirl` | 视频前后对比滑块 |
| `d9bc6b7f-16bd-40f7-8c53-729f89091fea` | `LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler` | H3 3D latent 学习式放大 + 重采样 + 双 VAE(video+audio)解码：输入 av_latent, model, conditioning, sigmas, temporal_split_param(H3_TEMPORAL_PARAM), spatial_split_param(H3_SPATIAL_PARAM), vae, vae_1, model_name=minimax_h3_latent_upscaler_3d_fp16.safetensors, device, precision, sampler_name → 输出 latent/latent_1/IMAGE/images/audio。ComfyUI 因源环境缺包将 class_type 替换为 UUID。 |
| `easy boolean` | `yolain/ComfyUI-Easy-Use` | 布尔输入 |
| `easy cleanGpuUsed` | `yolain/ComfyUI-Easy-Use` | 清理 GPU 显存 |
| `easy clearCacheAll` | `yolain/ComfyUI-Easy-Use` | 清理全部缓存 |
| `easy float` | `yolain/ComfyUI-Easy-Use` | 浮点输入 |
| `easy showAnything` | `yolain/ComfyUI-Easy-Use` | 显示任意值 |
| `忽略多组孤海` | `rgthree/rgthree-comfy` | rgthree Fast Groups Muter 的汉化/魔改重命名版（分组旁路开关，『孤海』为汉化署名）；功能等同 Fast Groups Muter / Fast Groups Bypasser |

***

## 4. ComfyUI 内置节点（无需安装）

> 需 ComfyUI **0.30.0+**；MiniMax H3 原生支持于 PR #15224（2026-08-03）合并。

| 节点类名 | 功能 |
|---------|------|
| `BasicGuider` | 基础引导器（CFG） |
| `BasicScheduler` | 基础调度器（sigma 计划） |
| `CLIPLoader` | 加载文本编码器（Qwen3-VL） |
| `ComfyMathExpression` | 数学表达式（帧数/时长推算） |
| `ConditioningZeroOut` | 条件置零 |
| `CreateVideo` | 帧+音频封装为视频 |
| `FloatConstant` | 浮点常量 |
| `GetVideoComponents` | 拆分视频为帧/帧率/音频 |
| `INTConstant` | 整数常量 |
| `Int` | 整数 |
| `KSamplerSelect` | 选择采样算法 |
| `LTXVConcatAVLatent` | 拼接 AV 潜空间 |
| `LTXVSeparateAVLatent` | 拆分 AV 潜空间 |
| `LoadAudio` | 加载音频 |
| `LoadImage` | 加载图片 |
| `LoadVideo` | 加载视频 |
| `LoraLoaderModelOnly` | 加载 LoRA（仅模型） |
| `MiniMaxH3ImageToVideo` | MiniMax H3 图生视频（官方原生节点） |
| `MiniMaxH3ReferenceToVideo` | MiniMax H3 参考生视频（多模态参考+AV 潜空间，官方原生节点） |
| `MiniMaxH3SigmaShift` | MiniMax H3 sigma 偏移（视频/音频双调度，官方原生节点） |
| `ModelAttentionBackend` | 注意力后端选择 |
| `PreviewImage` | 预览图片 |
| `PrimitiveFloat` | 浮点原始值 |
| `PrimitiveStringMultiline` | 多行字符串原始值 |
| `RandomNoise` | 随机噪声（seed 源） |
| `ResolutionSelector` | 分辨率选择器（16:9/32 对齐） |
| `SamplerCustomAdvanced` | 高级自定义采样器（去噪主循环） |
| `SaveVideo` | 保存视频 |
| `SplitSigmas` | 拆分 sigma 计划（两阶段采样） |
| `Text` | 文本 |
| `UNETLoader` | 加载扩散模型（Load Diffusion Model） |
| `VAEDecode` | VAE 解码（视频潜空间→帧） |
| `VAEDecodeAudio` | 音频 VAE 解码（潜空间→立体声波形） |
| `VAELoader` | 加载 VAE |

***

## 5. 来源待确认清单（UUID 占位节点）

> 以下节点在当前联网溯源范围内**未能 100% 确认真实 class_type**，不作臆测，原样列出待补充。
> 它们因导出环境缺节点包，被 ComfyUI 替换为 UUID 占位。其中 `b38cb4d8` / `7c0dfa74` 是「人物替换/二采流」工作流的**关键节点**，补齐源包后方可加载该工作流。

### `7c0dfa74-7583-4d61-98d6-cae724dc6517`

- **性质**：【未解析·UUID占位】无输入、输出 4 路 SIGMAS(SIGMAS/SIGMAS_1/SIGMAS_2/SIGMAS_3) 的调度生成器节点。导出环境缺节点包，ComfyUI 将真实 class_type 替换为该 UUID。
- **功能角色（已从工作流连线确认）**：无输入、输出 4 路 SIGMAS 的调度生成器。本工作流仅将其 SIGMAS_2 经 Reroute#386 接入下游（应为二采采样的 sigma 调度）。功能等价于「为二采多阶段采样预生成 4 条 sigma 调度、按阶段择一使用」。
- **I/O 签名**：输入 [（无）] → 输出 [SIGMAS:SIGMAS，SIGMAS_1:SIGMAS，SIGMAS_2:SIGMAS，SIGMAS_3:SIGMAS]
- **候选来源包（二采/多阶段 H3 生态）**：二采/多阶段 H3 采样生态（同上列包）；或某 sigma 调度工具包（ManualSigmas 变体 / 预置多阶段 schedule 节点）。Viggle-Animate-H3 文档提及「4 sigma points」基线；FastH3 社区工作流使用「3 步二采 sigma: 0.9035/0.6316/0.3158/0.0000」—— 均指向 4 点 sigma 约定。
- **已排除的包**：RES4LYF/Sigmas Split（1 路）、sigmas_tools/Split-and-concatenate（2 路）、ComfyUI 内置 SplitSigmas（2 路）、rockerBOO/MiniMaxH3ShiftSigmas（1 路且需输入）—— 均不匹配「无输入 + 4 路输出」。
- **如何补全**：同上，需源环境确认真实 class_type。

### `b38cb4d8-b7ff-4df4-990e-876cf5cb5857`

- **性质**：【未解析·UUID占位·关键节点】双 VAE(视频+音频)的 H3 二采(second-pass)采样+解码节点。导出环境缺节点包，ComfyUI 将真实 class_type 替换为该 UUID。
- **功能角色（已从工作流连线确认）**：本工作流核心二采节点：接收一采 latent（MiniMaxH3ReferenceToVideo#261 的 latent_image）、运动上下文条件与 trim_frames（MiniMaxH3MotionContextClipStream#5358）、双 VAE（GetNode#240 视频 VAE + #241 音频 VAE），完成 H3 联合视频/音频采样（sampler_name 默认 er_sde、scheduler 默认 simple、denoise），并同时解码输出视频帧(IMAGE/images)与音频(audio)；其 LATENT 输出 output 还接入 3D latent 放大(d9bc6b7f)与 ClipBin 双流保存。
- **I/O 签名**：输入 [model:MODEL，conditioning:CONDITIONING，latent_image:LATENT，steps:INT，vae:VAE(视频)，vae_1:VAE(音频)，trim_frames:INT，sampler_name:COMBO[er_sde]，scheduler:COMBO[simple]，denoise:FLOAT] → 输出 [output:LATENT，IMAGE:IMAGE，images:IMAGE，audio:AUDIO]
- **候选来源包（二采/多阶段 H3 生态）**：二采/second-pass H3 生态：yichengup/ComfyUI-YCNodes-MiniMax-H3（本工作流已用其 H3SigmaRefiner，该包专攻二采条件注入/低噪精修）、Songssx/ComfyUI-MiniMaxH3-TimelineDirector（Two-Stage Sampler）、facok/comfyui-SelfLift（本工作流已用 SelfLiftH3Sampler）、rockerBOO/h3-latent-upscaler（二采上采样）。亦可能为工作流作者自写的群分享私有节点。
- **已排除的包**：ClipStream / IAMCCS / RunningHub(RHMiniMaxH3*) / Motion-Context / Motion-Director / Easy-Use / LBH-123-AI / KJNodes / Viggle-Animate-H3 / ethanfel / RES4LYF / LongTake / xiaolibai-sys/ComfyUI-MiniMaxH3 / 官方 ComfyUI-MiniMax-H3 —— 均不含「双 VAE 采样+解码+trim_frames」的单一节点。
- **如何补全**：在源 ComfyUI 环境用 Manager「缺失节点」提示或列出已安装 custom_nodes 包，定位定义此 class_type 的包；或直接提供工作流作者使用的节点包名。补全后即可加载本工作流。

