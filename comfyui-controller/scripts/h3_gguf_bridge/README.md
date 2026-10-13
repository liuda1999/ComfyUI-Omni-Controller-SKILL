# h3_gguf_bridge — 让不支持 H3 的 GGUF 加载器环境可加载 MiniMax-H3 量化模型

## 背景

ComfyUI 环境里常见**两个包注册同名 GGUF 加载器节点**（`UnetLoaderGGUF` / `UnetLoaderGGUFAdvanced`）：

| 包 | H3 支持 | 说明 |
| --- | --- | --- |
| `ComfyUI-GGUF`（city96 上游） | ❌ | `tools/convert.py: detect_arch` 无 H3 条目 → 加载 H3 GGUF 报 `Unknown model architecture!` |
| `comfyui-gguf-loader`（较新分支） | ✅ | `tools/convert.py` 有 `ModelLTX2`（按张量签名识别 H3），`loader.py` 映射为 `minimax_h3` |

同名冲突时**后加载者覆盖前者**；很多环境里恰好是 `ComfyUI-GGUF` 生效，于是 `UnetLoaderGGUF`
无法加载 H3 量化文件（即使环境里已装了支持 H3 的那个包）。

## 本桥接做什么

以**唯一节点名**重新暴露 `comfyui-gguf-loader` 的加载器：

- `UnetLoaderGGUF_H3`
- `UnetLoaderGGUFAdvanced_H3`

**纯新增**：不修改任何现有包；删除本目录即完全移除。
**与加载顺序无关**：目标包在 `INPUT_TYPES`/调用时**延迟解析**（彼时所有自定义节点已导入完毕）。

## 安装

把本目录整个复制到 ComfyUI 的自定义节点目录（目录名任意，建议 `zz_h3_gguf_bridge` 以便靠后加载）：

```bash
cp -r h3_gguf_bridge /path/to/ComfyUI/custom_nodes/zz_h3_gguf_bridge
# 重启 ComfyUI 后，节点列表出现 UNET Loader (GGUF, H3 bridge)
```

## 使用

1. 打开一个原本使用 `UnetLoaderGGUF` 的 H3 工作流（例如工作流仓库的 `minimax_h3_*`）；
2. 把该节点换成 `UnetLoaderGGUF_H3`，`unet_name` 选你的 H3 量化 GGUF（如 `*Q6_K.gguf`）；
3. 其余连线不变，正常提交。

成功时日志会出现：

```
This gguf model file is loaded in compatibility mode 'sd.cpp' [arch:minimax_h3]
```

## 前置条件

- 环境里已安装 **`comfyui-gguf-loader`**（本桥接只是"改名暴露"，不含加载逻辑）；
- 该包自身具备 H3 的 `ModelLTX2` 定义（较新版本才有）。

## 注意（实测结论）

- **GGUF 量化未必省显存**：H3 Q6_K 以兼容模式反量化为 `bfloat16` 运行，显存占用可能**高于** fp8 safetensors
  （实测 Q6 ≈19.5 GB vs fp8 ≈15.9 GB）。量化的主要收益是**磁盘体积**（16.55 GB vs 18.6 GB）与加载灵活性。
- 若目标环境的 `ComfyUI-GGUF` 已升级并支持 H3，则**无需本桥接**，直接用官方 `UnetLoaderGGUF` 即可。
