# 工作流仓库布局与同步（workflow_library layout）

> 本文说明项目里**两份 `workflow_library.json`** 的关系、各自作用，以及如何保持同步。
> 判定依据：`scripts/*.py` 中 `_SKILL_ASSETS = <repo>/skills/comfyui-controller/assets`。

## 1. 两份库文件

| 文件 | 角色 | 是否入 git | 内容 |
|---|---|---|---|
| `comfyui-controller/assets/workflow_library.json` | **规范库（canonical）** | 是 | 仓库自带工作流：22 个顶层样例（含 **6 个 MiniMax H3**）+ 55 个归档旧工作流条目；共 **77** 条。**不含任何个人工作流** |
| `skills/comfyui-controller/assets/workflow_library.json` | **技能库（live）** | 视情况 | 规范库 **+ 本机个人工作流**；技能脚本实际加载的即此文件 |

> 技能脚本（`query_library.py` / `workflow_generator.py` / `advanced_workflow_builder.py` 等）默认加载 **技能库**（`skills/.../assets/workflow_library.json`）。

## 2. 为什么分两份

- **规范库**随仓库分发，必须干净、可公开（不含个人工作流名/NSFW 等隐私内容）。
- **技能库**是本机运行态，需包含用户自己的全部工作流，供智能体检索/复用。

## 3. 同步方式（`scripts/sync_skill_library.py`）

```bash
# 规范库 + 本机个人工作流 合并 → 写入技能库（推荐）
python comfyui-controller/scripts/sync_skill_library.py

# 只用规范库覆盖技能库（丢弃个人工作流）
python comfyui-controller/scripts/sync_skill_library.py --no-merge
```

机制要点：

- 个人条目会写入技能库 `workflows`，但**刻意不写入 `file_index`**。
  这样 `build_workflow_library.py` 的增量更新（`compute_file_changes` 会把 `file_index` 中"磁盘上已不存在"的条目判为删除）**不会误删个人条目**。
- 个人条目标记 `source_root`，规范库条目标记 `source_roots`（见 `metadata`）。
- 每次同步会自动把旧技能库备份为 `workflow_library.json.bak.<时间戳>`。

## 4. 重新构建规范库（可选）

规范库由 `build_workflow_library.py` 从 `comfyui-controller/assets/` 构建：

```bash
python comfyui-controller/scripts/build_workflow_library.py \
  --input  comfyui-controller/assets \
  --object-info comfyui-controller/assets/object_info.json \
  --output comfyui-controller/assets/workflow_library.json
```

> ⚠️ 注意：`--input` 必须是**工作流目录**（本例为 `comfyui-controller/assets`）。若误用 `$COMFYUI_PATH/user` 之类的大目录，会把 `ComfyUI-Manager` 缓存、`comfy.settings.json` 等非工作流文件也索引进来（历史遗留问题，已清理）。默认 `--input` 为 `$COMFYUI_PATH/user/default/workflows`。

## 5. 相关文件

- 节点依赖来源：`assets/node_registry.json`（39 包 / 177 节点）、`assets/legacy_workflow_index.json`（70 个旧工作流）
- 文档：[legacy_workflow_nodes.md](legacy_workflow_nodes.md)（旧工作流节点依赖）、[third_party_nodes.md](third_party_nodes.md)（MiniMax H3 节点索引）
