# 旧工作流（Legacy / 非 MiniMax）节点依赖总览

> 生成范围：`comfyui-controller/assets/` 顶层 + `assets/archive/` 下**全部 70 个**旧工作流（不含 12 个 MiniMax/H3 新增）。

> 数据来源：`legacy_workflow_index.json`（机器可读）、`workflow_library.json`（每条含 `node_dependencies`）、`node_registry.json`（包/节点索引）。

> 说明：本文件覆盖的节点依赖索引，是为了让智能体/使用者无需人工排查即可 `git clone` 对应包并把工作流加载进 ComfyUI。

## 0. 总览

- 旧工作流总数：**70**（顶层 16 + 归档 `archive/` 54）
- 被旧工作流实际引用的第三方节点包：**19** 个（见下表；另有若干包仅服务于 MiniMax/H3 新增工作流，未计入）
- 不在「本环境 object_info 快照」中的节点 class_type：**11** 个（其中 **7 个为前端/虚拟节点**（无需安装）、**4 个为后端缺失节点**（需装包），见第 3 节）

### 第三方包使用频次（被多少个工作流引用）

| 包 (owner/repo) | 许可 | 被引用数 | 仓库 |
|---|---|---|---|
| `Kosinkadink/ComfyUI-VideoHelperSuite` | GPL-3.0 | 30 | https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite |
| `kijai/ComfyUI-WanVideoWrapper` | Apache-2.0 | 29 | https://github.com/kijai/ComfyUI-WanVideoWrapper |
| `kijai/ComfyUI-KJNodes` | MIT | 28 | https://github.com/kijai/ComfyUI-KJNodes |
| `yolain/ComfyUI-Easy-Use` | GPL-3.0 | 6 | https://github.com/yolain/ComfyUI-Easy-Use |
| `cubiq/ComfyUI_essentials` | MIT | 5 | https://github.com/cubiq/ComfyUI_essentials |
| `shadowcz007/comfyui-mixlab-nodes` | MIT | 5 | https://github.com/shadowcz007/comfyui-mixlab-nodes |
| `chflame163/ComfyUI_LayerStyle` | MIT | 2 | https://github.com/chflame163/ComfyUI_LayerStyle |
| `rgthree/rgthree-comfy` | MIT | 2 | https://github.com/rgthree/rgthree-comfy |
| `Suzie1/ComfyUI_Comfyroll_CustomNodes` | MIT | 2 | https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes |
| `PGCRT/CRT-Nodes` | 见仓库 LICENSE | 2 | https://github.com/PGCRT/CRT-Nodes |
| `city96/ComfyUI-GGUF` | MIT（个别来源标 Apache-2.0，以仓库 LICENSE 为准） | 2 | https://github.com/city96/ComfyUI-GGUF |
| `kijai/ComfyUI-WanAnimatePreprocess` | Apache-2.0 | 1 | https://github.com/kijai/ComfyUI-WanAnimatePreprocess |
| `wuwukaka/ComfyUI-BodyRatioMapper` | GPL-3.0 | 1 | https://github.com/wuwukaka/ComfyUI-BodyRatioMapper |
| `SeanScripts/ComfyUI-Unload-Model` | MIT（fork 自 willblaschko/ComfyUI-Unload-Models，LICENSE 见仓库） | 1 | https://github.com/SeanScripts/ComfyUI-Unload-Model |
| `pythongosssss/ComfyUI-Custom-Scripts` | MIT | 1 | https://github.com/pythongosssss/ComfyUI-Custom-Scripts |
| `Fannovel16/ComfyUI-Frame-Interpolation` | MIT | 1 | https://github.com/Fannovel16/ComfyUI-Frame-Interpolation |
| `WASasquatch/was-node-suite-comfyui` | MIT | 1 | https://github.com/WASasquatch/was-node-suite-comfyui |
| `weekii8282/ComfyUI-PromptSelector` | 见仓库 LICENSE | 1 | https://github.com/weekii8282/ComfyUI-PromptSelector |
| `M1kep/ComfyLiterals` | 见仓库 LICENSE | 1 | https://github.com/M1kep/ComfyLiterals |

## 1. 按系列逐个工作流

每个工作流列出：格式、节点数、所用第三方包（含各自的具体节点类型）。`[!]` 表示含有本环境缺失、需额外确认的节点。

### 1.1 task1 系列（Wan2.2 文/图生视频初版） （8 个）

- **task1_api_workflow**  — `archive/task1_api_workflow.json` · api · 11 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **task1_final**  — `archive/task1_final.json` · api · 11 节点
  - 第三方包：`city96/ComfyUI-GGUF`（UnetLoaderGGUF）
- **task1_flux_workflow**  — `archive/task1_flux_workflow.json` · api · 9 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **task1_img_workflow**  — `archive/task1_img_workflow.json` · api · 12 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **task1_v2_final**  — `archive/task1_v2_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task1_wan22_img_workflow**  — `archive/task1_wan22_img_workflow.json` · api · 11 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **task1_wan22_native**  — `archive/task1_wan22_native.json` · api · 8 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task1_wan22_workflow**  — `archive/task1_wan22_workflow.json` · api · 27 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`PGCRT/CRT-Nodes`（SimpleKnobNode, SimpleToggleNode）；`kijai/ComfyUI-KJNodes`（GetImageSizeAndCount, INTConstant）；`kijai/ComfyUI-WanVideoWrapper`（CreateCFGScheduleFloatList, LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEasyCache, WanVideoEmptyEmbeds, WanVideoLoraSelect, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）；`shadowcz007/comfyui-mixlab-nodes`（TextInput_）；`yolain/ComfyUI-Easy-Use`（easy cleanGpuUsed, easy clearCacheAll）

### 1.2 task2 系列（Wan2.2 i2v / 多版本迭代） （12 个）

- **task2_api**  — `archive/task2_api.json` · prompt-api · 9 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_fast**  — `archive/task2_fast.json` · prompt-api · 12 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_final**  — `archive/task2_final.json` · api · 31 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`cubiq/ComfyUI_essentials`（ImageFromBatch+）；`kijai/ComfyUI-KJNodes`（GetImageSizeAndCount, INTConstant）；`kijai/ComfyUI-WanVideoWrapper`（CreateCFGScheduleFloatList, LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEasyCache, WanVideoImageToVideoEncode, WanVideoLoraSelect, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoSetLoRAs, WanVideoTextEncode, WanVideoVAELoader）；`shadowcz007/comfyui-mixlab-nodes`（TextInput_）；`yolain/ComfyUI-Easy-Use`（easy cleanGpuUsed, easy clearCacheAll）
- **task2_i2v_480x660_highquality**  — `archive/task2_i2v_480x660_highquality.json` · api · 31 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`cubiq/ComfyUI_essentials`（ImageFromBatch+）；`kijai/ComfyUI-KJNodes`（GetImageSizeAndCount, INTConstant）；`kijai/ComfyUI-WanVideoWrapper`（CreateCFGScheduleFloatList, LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEasyCache, WanVideoImageToVideoEncode, WanVideoLoraSelect, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoSetLoRAs, WanVideoTextEncode, WanVideoVAELoader）；`shadowcz007/comfyui-mixlab-nodes`（TextInput_）；`yolain/ComfyUI-Easy-Use`（easy cleanGpuUsed, easy clearCacheAll）
- **task2_i2v_480x660_video**  — `archive/task2_i2v_480x660_video.json` · api · 31 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`cubiq/ComfyUI_essentials`（ImageFromBatch+）；`kijai/ComfyUI-KJNodes`（GetImageSizeAndCount, INTConstant）；`kijai/ComfyUI-WanVideoWrapper`（CreateCFGScheduleFloatList, LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEasyCache, WanVideoImageToVideoEncode, WanVideoLoraSelect, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoSetLoRAs, WanVideoTextEncode, WanVideoVAELoader）；`shadowcz007/comfyui-mixlab-nodes`（TextInput_）；`yolain/ComfyUI-Easy-Use`（easy cleanGpuUsed, easy clearCacheAll）
- **task2_input_image**  — `archive/task2_input_image.json` · api · 9 节点
  - 第三方包：`city96/ComfyUI-GGUF`（UnetLoaderGGUF）
- **task2_light**  — `archive/task2_light.json` · prompt-api · 10 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_optimized**  — `archive/task2_optimized.json` · prompt-api · 10 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_t2v_final**  — `archive/task2_t2v_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_v2_final**  — `archive/task2_v2_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_v3_final**  — `archive/task2_v3_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task2_workflow_webui**  — `archive/task2_workflow_webui.json` · ui · 35 节点
  - 第三方包：`Fannovel16/ComfyUI-Frame-Interpolation`（RIFE VFI）；`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`Suzie1/ComfyUI_Comfyroll_CustomNodes`（CR Text）；`WASasquatch/was-node-suite-comfyui`（Text Concatenate）；`chflame163/ComfyUI_LayerStyle`（LayerUtility: ImageScaleByAspectRatio V2）；`cubiq/ComfyUI_essentials`（SimpleMath+）；`kijai/ComfyUI-KJNodes`（INTConstant, ModelPatchTorchSettings, PathchSageAttentionKJ）；`weekii8282/ComfyUI-PromptSelector`（Wan22PromptSelector）；`yolain/ComfyUI-Easy-Use`（easy cleanGpuUsed）

### 1.3 task3 系列（Wan2.2 t2v 多分辨率） （7 个）

- **task3_api_raw**  — `archive/task3_api_raw.json` · api · 20 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`M1kep/ComfyLiterals`（Int）；`kijai/ComfyUI-KJNodes`（INTConstant, PathchSageAttentionKJ）
- **task3_api_workflow**  — `archive/task3_api_workflow.json` · api · 14 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **task3_final**  — `archive/task3_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task3_t2v_480x960**  — `archive/task3_t2v_480x960.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task3_t2v_720x1440**  — `archive/task3_t2v_720x1440.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task3_v2_final**  — `archive/task3_v2_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **task3_v3_final**  — `archive/task3_v3_final.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）

### 1.4 c6 系列（Wan2.2 i2v 实验） （4 个）

- **c6_final**  — `archive/c6_final.json` · api · 14 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoTextEncode, WanVideoVAELoader）
- **c6_test_quick**  — `archive/c6_test_quick.json` · api · 14 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoTextEncode, WanVideoVAELoader）
- **c6_wan22_i2v_api**  — `archive/c6_wan22_i2v_api.json` · api · 35 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`PGCRT/CRT-Nodes`（FancyTimerNode）；`cubiq/ComfyUI_essentials`（ImageFromBatch+）；`kijai/ComfyUI-KJNodes`（GetImageSizeAndCount, INTConstant）；`kijai/ComfyUI-WanVideoWrapper`（CreateCFGScheduleFloatList, LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEasyCache, WanVideoImageToVideoEncode, WanVideoLoraSelect, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoSetLoRAs, WanVideoTextEncode, WanVideoVAELoader）；`shadowcz007/comfyui-mixlab-nodes`（TextInput_）；`yolain/ComfyUI-Easy-Use`（easy cleanGpuUsed, easy clearCacheAll）
- **c6_x2**  — `archive/c6_x2.json` · api · 4 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_LoadVideo, VHS_VideoCombine）

### 1.5 c7 系列（SVI 长视频分段 high/low） （18 个）

- **c7_svi_merge**  — `archive/c7_svi_merge.json` · api · 10 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_LoadVideo, VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageBatchExtendWithOverlap）
- **c7_svi_seg1**  — `archive/c7_svi_seg1.json` · api · 21 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg1_high**  — `archive/c7_svi_seg1_high.json` · api · 14 节点
  - 第三方包：`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg1_low**  — `archive/c7_svi_seg1_low.json` · api · 13 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ModelPatchTorchSettings, PathchSageAttentionKJ）
- **c7_svi_seg2**  — `archive/c7_svi_seg2.json` · api · 22 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg2_high**  — `archive/c7_svi_seg2_high.json` · api · 15 节点
  - 第三方包：`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg2_low**  — `archive/c7_svi_seg2_low.json` · api · 13 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ModelPatchTorchSettings, PathchSageAttentionKJ）
- **c7_svi_seg3**  — `archive/c7_svi_seg3.json` · api · 22 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg3_high**  — `archive/c7_svi_seg3_high.json` · api · 15 节点
  - 第三方包：`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg3_low**  — `archive/c7_svi_seg3_low.json` · api · 13 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ModelPatchTorchSettings, PathchSageAttentionKJ）
- **c7_svi_seg4**  — `archive/c7_svi_seg4.json` · api · 22 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg4_high**  — `archive/c7_svi_seg4_high.json` · api · 15 节点
  - 第三方包：`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg4_low**  — `archive/c7_svi_seg4_low.json` · api · 13 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ModelPatchTorchSettings, PathchSageAttentionKJ）
- **c7_svi_seg5**  — `archive/c7_svi_seg5.json` · api · 21 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg5_high**  — `archive/c7_svi_seg5_high.json` · api · 15 节点
  - 第三方包：`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_svi_seg5_low**  — `archive/c7_svi_seg5_low.json` · api · 13 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ModelPatchTorchSettings, PathchSageAttentionKJ）
- **c7_test_41f**  — `archive/c7_test_41f.json` · api · 20 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）
- **c7_x2_upscale**  — `archive/c7_x2_upscale.json` · api · 4 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_LoadVideo, VHS_VideoCombine）

### 1.6 galaxy_bottle 系列（FLUX.2 瓶身合成） （4 个）

- **galaxy_bottle_base**  — `archive/galaxy_bottle_base.json` · api · 7 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **galaxy_bottle_final**  — `archive/galaxy_bottle_final.json` · api · 7 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **galaxy_bottle_flux2_ui**  — `archive/galaxy_bottle_flux2_ui.json` · ui · 13 节点
  - 第三方包：无（仅 ComfyUI 核心节点）
- **galaxy_bottle_x2_api**  — `archive/galaxy_bottle_x2_api.json` · api · 4 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

### 1.7 generated（复杂合成示例） （1 个）

- **generated_complex_workflow**  — `archive/generated_complex_workflow.json` · ui · 18 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

### 1.8 animate（Wan2.2 threeview 动作） （1 个）

- **animate_wan22_threeview_v1.0.0**  — `animate_wan22_threeview_v1.0.0.json` · ui · 99 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_LoadVideo, VHS_VideoCombine, VHS_VideoInfoLoaded）；`chflame163/ComfyUI_LayerStyle`（LayerUtility: PurgeVRAM V2）；`kijai/ComfyUI-KJNodes`（GetNode, INTConstant, ImageResizeKJv2, SetNode）；`kijai/ComfyUI-WanAnimatePreprocess`（OnnxDetectionModelLoader, PoseAndFaceDetection）；`kijai/ComfyUI-WanVideoWrapper`（WanVideoAnimateEmbeds, WanVideoBlockSwap, WanVideoClipVisionEncode, WanVideoContextOptions, WanVideoDecode, WanVideoEncode, WanVideoLoraSelectMulti, WanVideoModelLoader, WanVideoSamplerFromSettings, WanVideoSamplerSettings, WanVideoSetBlockSwap, WanVideoSetLoRAs, WanVideoTextEncodeCached, WanVideoTorchCompileSettings, WanVideoUni3C_ControlnetLoader, WanVideoUni3C_embeds, WanVideoVAELoader）；`rgthree/rgthree-comfy`（Label (rgthree), Seed (rgthree)）；`wuwukaka/ComfyUI-BodyRatioMapper`（BodyRatioMapperProportionTransfer, BodyRatioMapperSDPoseRender）

### 1.9 i2v（Wan2.2 i2v 顶层） （2 个）

- **i2v_wan22_kj_v1.0.0**  — `i2v_wan22_kj_v1.0.0.json` · api · 18 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoLoraSelect, WanVideoModelLoader, WanVideoSampler, WanVideoSetBlockSwap, WanVideoSetLoRAs, WanVideoTextEncode, WanVideoVAELoader）
- **i2v_wan22_v1.0.0**  — `i2v_wan22_v1.0.0.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）

### 1.10 wan22（Wan2.2 顶层工作流） （4 个）

- **wan22_i2v_workflow**  — `wan22_i2v_workflow.json` · prompt-api · 9 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoDecode, WanVideoImageToVideoEncode, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **wan22_simple_t2i**  — `wan22_simple_t2i.json` · prompt-api · 8 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）
- **wan22_svi_pro_long_video**  — `wan22_svi_pro_long_video.json` · ui · 133 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`Suzie1/ComfyUI_Comfyroll_CustomNodes`（CR Prompt Text）；`kijai/ComfyUI-KJNodes`（GetNode, INTConstant, ImageBatchExtendWithOverlap, ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, SetNode, WanImageToVideoSVIPro）；`pythongosssss/ComfyUI-Custom-Scripts`（PlaySound|pysssss）；`rgthree/rgthree-comfy`（Fast Groups Bypasser (rgthree)）
- **wan22_t2v_workflow**  — `wan22_t2v_workflow.json` · prompt-api · 8 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）

### 1.11 wan2（Wan2.2 5B ti2v） （1 个）

- **wan2_2_5B_ti2v**  — `wan2_2_5B_ti2v.json` · ui · 14 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

### 1.12 svi（SVI Pro 长视频） （1 个）

- **svi_pro_long_video_v1.0.0**  — `svi_pro_long_video_v1.0.0.json` · api · 57 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`kijai/ComfyUI-KJNodes`（ImageBatchExtendWithOverlap, ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）

### 1.13 long（SVI Pro 长视频 Wan2.2） （1 个）

- **long_video_svi_pro_wan22_v1.0.0**  — `long_video_svi_pro_wan22_v1.0.0.json` · ui · 178 节点
  - 第三方包：`Kosinkadink/ComfyUI-VideoHelperSuite`（VHS_VideoCombine）；`SeanScripts/ComfyUI-Unload-Model`（UnloadAllModels）；`kijai/ComfyUI-KJNodes`（ColorMatch, ImageBatchExtendWithOverlap, ImageResizeKJv2, ModelPatchTorchSettings, PathchSageAttentionKJ, WanImageToVideoSVIPro）

### 1.14 t2v（Wan2.2 t2v 顶层） （1 个）

- **t2v_wan22_v1.0.0**  — `t2v_wan22_v1.0.0.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）

### 1.15 img（FLUX.2 生图） （1 个）

- **img_gen_v1.0.0**  — `img_gen_v1.0.0.json` · api · 11 节点
  - 第三方包：`kijai/ComfyUI-WanVideoWrapper`（LoadWanVideoT5TextEncoder, WanVideoBlockSwap, WanVideoDecode, WanVideoEmptyEmbeds, WanVideoModelLoader, WanVideoSampler, WanVideoTextEncode, WanVideoVAELoader）

### 1.16 img2img（FLUX.2 图生图） （1 个）

- **img2img_flux2_example_v1.0.0**  — `img2img_flux2_example_v1.0.0.json` · api · 9 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

### 1.17 flux2（FLUX.2 API） （1 个）

- **flux2_api_workflow**  — `flux2_api_workflow.json` · api · 9 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

### 1.18 api-workflow（通用 API 模板） （1 个）

- **api-workflow**  — `api-workflow.json` · api · 9 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

### 1.19 default-workflow（默认模板） （1 个）

- **default-workflow**  — `default-workflow.json` · api · 7 节点
  - 第三方包：无（仅 ComfyUI 核心节点）

## 2. 一键安装（按包）

以下命令在 ComfyUI 根目录下执行（`custom_nodes/` 为节点目录）。每张贴一个包；一个工作流用到多个包时依次执行对应命令即可。

### `Fannovel16/ComfyUI-Frame-Interpolation`  （许可 MIT）

- 仓库：https://github.com/Fannovel16/ComfyUI-Frame-Interpolation

```bash
git clone https://github.com/Fannovel16/ComfyUI-Frame-Interpolation.git custom_nodes/ComfyUI-Frame-Interpolation && pip install -r custom_nodes/ComfyUI-Frame-Interpolation/requirements.txt
```

### `Kosinkadink/ComfyUI-VideoHelperSuite`  （许可 GPL-3.0）

- 仓库：https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite

```bash
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git custom_nodes/ComfyUI-VideoHelperSuite && pip install -r custom_nodes/ComfyUI-VideoHelperSuite/requirements.txt
```

### `M1kep/ComfyLiterals`  （许可 见仓库 LICENSE）

- 仓库：https://github.com/M1kep/ComfyLiterals

```bash
git clone https://github.com/M1kep/ComfyLiterals.git custom_nodes/ComfyLiterals
```

### `PGCRT/CRT-Nodes`  （许可 见仓库 LICENSE）

- 仓库：https://github.com/PGCRT/CRT-Nodes

```bash
git clone https://github.com/PGCRT/CRT-Nodes.git custom_nodes/CRT-Nodes && pip install -r custom_nodes/CRT-Nodes/requirements.txt
```

### `SeanScripts/ComfyUI-Unload-Model`  （许可 MIT（fork 自 willblaschko/ComfyUI-Unload-Models，LICENSE 见仓库））

- 仓库：https://github.com/SeanScripts/ComfyUI-Unload-Model

```bash
git clone https://github.com/SeanScripts/ComfyUI-Unload-Model.git custom_nodes/comfyui-unload-model
```

### `Suzie1/ComfyUI_Comfyroll_CustomNodes`  （许可 MIT）

- 仓库：https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes

```bash
git clone https://github.com/Suzie1/ComfyUI_Comfyroll_CustomNodes.git custom_nodes/ComfyUI_Comfyroll_CustomNodes
```

### `WASasquatch/was-node-suite-comfyui`  （许可 MIT）

- 仓库：https://github.com/WASasquatch/was-node-suite-comfyui

```bash
git clone https://github.com/WASasquatch/was-node-suite-comfyui.git custom_nodes/was-node-suite-comfyui
```

### `chflame163/ComfyUI_LayerStyle`  （许可 MIT）

- 仓库：https://github.com/chflame163/ComfyUI_LayerStyle

```bash
git clone https://github.com/chflame163/ComfyUI_LayerStyle.git custom_nodes/ComfyUI_LayerStyle && (双击 install_requirements.bat 或 pip install -r custom_nodes/ComfyUI_LayerStyle/requirements.txt)
```

### `city96/ComfyUI-GGUF`  （许可 MIT（个别来源标 Apache-2.0，以仓库 LICENSE 为准））

- 仓库：https://github.com/city96/ComfyUI-GGUF

```bash
git clone https://github.com/city96/ComfyUI-GGUF.git custom_nodes/ComfyUI-GGUF && pip install --upgrade gguf
```

### `cubiq/ComfyUI_essentials`  （许可 MIT）

- 仓库：https://github.com/cubiq/ComfyUI_essentials

```bash
git clone https://github.com/cubiq/ComfyUI_essentials.git custom_nodes/ComfyUI_essentials
```

### `kijai/ComfyUI-KJNodes`  （许可 MIT）

- 仓库：https://github.com/kijai/ComfyUI-KJNodes

```bash
git clone https://github.com/kijai/ComfyUI-KJNodes.git custom_nodes/ComfyUI-KJNodes && pip install -r custom_nodes/ComfyUI-KJNodes/requirements.txt
```

### `kijai/ComfyUI-WanAnimatePreprocess`  （许可 Apache-2.0）

- 仓库：https://github.com/kijai/ComfyUI-WanAnimatePreprocess

```bash
git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess.git custom_nodes/ComfyUI-WanAnimatePreprocess && pip install -r custom_nodes/ComfyUI-WanAnimatePreprocess/requirements.txt
```

### `kijai/ComfyUI-WanVideoWrapper`  （许可 Apache-2.0）

- 仓库：https://github.com/kijai/ComfyUI-WanVideoWrapper

```bash
git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git custom_nodes/ComfyUI-WanVideoWrapper && pip install -r custom_nodes/ComfyUI-WanVideoWrapper/requirements.txt
```

### `pythongosssss/ComfyUI-Custom-Scripts`  （许可 MIT）

- 仓库：https://github.com/pythongosssss/ComfyUI-Custom-Scripts

```bash
git clone https://github.com/pythongosssss/ComfyUI-Custom-Scripts.git custom_nodes/ComfyUI-Custom-Scripts
```

### `rgthree/rgthree-comfy`  （许可 MIT）

- 仓库：https://github.com/rgthree/rgthree-comfy

```bash
git clone https://github.com/rgthree/rgthree-comfy.git custom_nodes/rgthree-comfy
```

### `shadowcz007/comfyui-mixlab-nodes`  （许可 MIT）

- 仓库：https://github.com/shadowcz007/comfyui-mixlab-nodes

```bash
git clone https://github.com/shadowcz007/comfyui-mixlab-nodes.git custom_nodes/comfyui-mixlab-nodes && pip install -r custom_nodes/comfyui-mixlab-nodes/requirements.txt
```

### `weekii8282/ComfyUI-PromptSelector`  （许可 见仓库 LICENSE）

- 仓库：https://github.com/weekii8282/ComfyUI-PromptSelector

```bash
git clone https://github.com/weekii8282/ComfyUI-PromptSelector.git custom_nodes/ComfyUI-PromptSelector
```

### `wuwukaka/ComfyUI-BodyRatioMapper`  （许可 GPL-3.0）

- 仓库：https://github.com/wuwukaka/ComfyUI-BodyRatioMapper

```bash
git clone https://github.com/wuwukaka/ComfyUI-BodyRatioMapper.git custom_nodes/ComfyUI-BodyRatioMapper && pip install -r custom_nodes/ComfyUI-BodyRatioMapper/requirements.txt
```

### `yolain/ComfyUI-Easy-Use`  （许可 GPL-3.0）

- 仓库：https://github.com/yolain/ComfyUI-Easy-Use

```bash
git clone https://github.com/yolain/ComfyUI-Easy-Use.git custom_nodes/ComfyUI-Easy-Use && pip install -r custom_nodes/ComfyUI-Easy-Use/requirements.txt
```

## 3. 缺失 / 前端 / 未定位节点

> 重要说明：ComfyUI 的 `object_info.json` 只包含**后端**节点。**前端/虚拟节点**（注解、Set/Get、控件类）本就不会出现在里面，`object_info` 查不到 ≠ 需要安装。以下按类型区分。

### 3.1 前端 / 虚拟节点（无需后端安装，随前端或对应包的前端扩展自动可用）— 共 7 个

| 节点 class_type | 所属（前端来源） | 功能/说明 |
|---|---|---|
| `Fast Groups Bypasser (rgthree)` | `rgthree/rgthree-comfy` | rgthree 按组快速 bypass 的前端控制节点 |
| `GetNode` | `kijai/ComfyUI-KJNodes` | KJNodes Set/Get 虚拟连接（前端 JS，web/js/setgetnodes.js），命名取值 |
| `Label (rgthree)` | `rgthree/rgthree-comfy` | rgthree 画布标签/分区注解（前端） |
| `MarkdownNote` | `ComfyUI-Core` | ComfyUI 核心前端 Markdown 注解节点（ComfyUI_frontend noteNode.ts 注册，与 Note 同源） |
| `Note` | `ComfyUI-Core` | ComfyUI 内置前端注解节点（无输入/输出，仅标注） |
| `PrimitiveNode` | `ComfyUI-Core` | ComfyUI 前端 Primitive/Widget 节点（连线挂参用，无计算） |
| `SetNode` | `kijai/ComfyUI-KJNodes` | KJNodes Set/Get 虚拟连接（前端 JS），按名称暂存任意类型值 |

### 3.2 后端缺失节点（本环境 object_info 不存在且为后端节点，加载会显示红色，需安装对应包）— 共 4 个

| 节点 class_type | 归属包（仓库） | 功能/说明 |
|---|---|---|
| `BodyRatioMapperProportionTransfer` | `wuwukaka/ComfyUI-BodyRatioMapper` — https://github.com/wuwukaka/ComfyUI-BodyRatioMapper | 姿势对齐+人体比例映射，输出变换后关键点（后端，需安装） |
| `BodyRatioMapperSDPoseRender` | `wuwukaka/ComfyUI-BodyRatioMapper` — https://github.com/wuwukaka/ComfyUI-BodyRatioMapper | 将 SDPose 关键点渲染为骨架图（供 ControlNet）（后端，需安装） |
| `UnloadAllModels` | `SeanScripts/ComfyUI-Unload-Model` — https://github.com/SeanScripts/ComfyUI-Unload-Model | 卸载全部已加载模型以释放显存（后端节点，需安装） |
| `Wan22PromptSelector` | `weekii8282/ComfyUI-PromptSelector` — https://github.com/weekii8282/ComfyUI-PromptSelector | Wan2.2 提示词选择器；近似替代实现（原名未精确定位，后端，需安装） |

#### 3.2.1 上述节点对应包的一键安装

**`SeanScripts/ComfyUI-Unload-Model`**  （许可 MIT（fork 自 willblaschko/ComfyUI-Unload-Models，LICENSE 见仓库）） 仓库：https://github.com/SeanScripts/ComfyUI-Unload-Model
```bash
git clone https://github.com/SeanScripts/ComfyUI-Unload-Model.git custom_nodes/comfyui-unload-model
```

**`weekii8282/ComfyUI-PromptSelector`**  （许可 见仓库 LICENSE） 仓库：https://github.com/weekii8282/ComfyUI-PromptSelector
```bash
git clone https://github.com/weekii8282/ComfyUI-PromptSelector.git custom_nodes/ComfyUI-PromptSelector
```

**`wuwukaka/ComfyUI-BodyRatioMapper`**  （许可 GPL-3.0） 仓库：https://github.com/wuwukaka/ComfyUI-BodyRatioMapper
```bash
git clone https://github.com/wuwukaka/ComfyUI-BodyRatioMapper.git custom_nodes/ComfyUI-BodyRatioMapper && pip install -r custom_nodes/ComfyUI-BodyRatioMapper/requirements.txt
```

### 3.3 名称易混但已定位的节点（在 object_info 中存在，属正常后端节点，无需处理）

`ComfyLiterals` 包的字面量节点（来源已核实为 `M1kep/ComfyLiterals`）：

- `Int`

## 4. 关联文件

- `assets/legacy_workflow_index.json` — 70 个旧工作流的机器可读索引（含每条 node_dependencies）
- `assets/workflow_library.json` — 每条旧工作流 entry 均含 `node_dependencies` 与 `legacy_scan` 元数据
- `assets/node_registry.json` — 全部节点/包索引（39 包 / 177 节点）
- `docs_cli/third_party_nodes.md` — 第三方节点总索引（含 MiniMax/H3 的 2 个 UUID 占位节点说明）
- MiniMax/H3 新增 6 个工作流见 `docs_cli/minimax_h3_workflow_params.md`