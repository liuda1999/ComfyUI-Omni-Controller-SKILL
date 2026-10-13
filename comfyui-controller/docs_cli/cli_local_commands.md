# CLI 本地命令参考（按官方 comfy-cli 语义原生移植）

> **背景**：本项目 `cli/` 是 comfy-cli 的本地定制分支。官方
> [Comfy-Org/comfy-cli](https://github.com/Comfy-Org/comfy-cli) 1.22.0 已是一次
> **架构级重写**（引入 `comfy_client` / `target·where` 云-本地路由 / `output` 渲染器 /
> `jobs_state` / `cloud`+`auth` 等基础设施），本项目基于旧架构（`ui.py` /
> `config_manager` / `env_checker`），故官方命令**无法逐字照搬**。
>
> **做法**：按官方**语义**、用本项目既有架构**原生实现**其中的本地可行命令；
> 纯云端子系统（`cloud` / `auth` / `build` / `deploy` / `assets` / `agent` /
> `skills` / `knowledge` / `workflow` / `preview` / `discover` / `models search`）
> **不在移植范围**。
>
> 所有新命令均面向**本地 ComfyUI**，且均支持 `--json`（机器可读），
> JSON 输出统一经 `cli/output.py` 的 `emit_json()` **绕过 rich 换行**（见 25.2）。

***

## 1. 命令总览

| 命令 | 对应官方语义 | 状态 |
| --- | --- | --- |
| `comfy system-stats` | 设备 VRAM / 系统内存 | ✅ 已实现并实测 |
| `comfy free` | 释放显存 / 卸载模型 | ✅ 已实现并实测 |
| `comfy download <prompt_id>` | 下载产物 | ✅ 已实现并实测 |
| `comfy upload <file>` | 上传到 input 目录 | ✅ 已实现并实测 |
| `comfy logs` | 查看捕获的 ComfyUI 日志 | ✅ 已实现并实测 |
| `comfy jobs ls/status/wait/watch` | 作业查看与等待 | ✅ 本地子集 |
| `comfy templates ls` | 官方模板画廊列表 | ✅ 已实现 |
| `comfy run-template <name>` | 取画廊模板并运行 | ✅ 已实现 |
| `comfy setup` | 环境向导（本地版） | ✅ 已实现 |
| `comfy update cli` | 升级 CLI 自身 | ✅（`update all\|comfy\|cli`） |

***

## 2. 命令详情

### 2.1 `comfy system-stats`

GET `/system_stats`，输出各设备 VRAM 与系统内存表。

```bash
comfy system-stats [--host H] [--port P] [--json]
```

`--json` 时整包原样透传 `/system_stats` 响应，便于脚本消费。

### 2.2 `comfy free`

POST `/free`，在队列 worker 下次迭代时生效（空闲立即生效，忙碌时在当前任务之后，**不中断**运行中任务）。

```bash
comfy free [--host H] [--port P] [--unload-models/--no-unload-models] [--free-memory] [--json]
```

### 2.3 `comfy download <prompt_id>`

读取 `GET /history/{prompt_id}`，将其产物（images / gifs / videos）经 `/view` 下载到本地。

```bash
comfy download <prompt_id> [-o DIR] [--host H] [--port P] [--json]
```

### 2.4 `comfy upload <file>`

POST `/upload/image`，返回服务器端文件名（可被 `LoadImage` 等节点引用）。

```bash
comfy upload <file> [--host H] [--port P] [--json]
```

### 2.5 `comfy logs` ⭐ 后台日志查看

显示被捕获的 ComfyUI 日志。日志来源有两类：`comfy launch --background` 捕获的
日志文件，以及 ComfyUI-Manager 自己的日志文件。

```bash
comfy logs [-n/--tail N] [-p/--port P] [--path FILE] [-f/--follow] [--json]
```

**日志文件位置**：`<workspace>/user/comfyui_<port>.log`（每次 `launch --background`
启动会**截断重写**，即每次启动一份新日志）。

**解析顺序**（`candidate_log_paths`，命中即用）：

| 顺序 | 候选 | source 标记 |
| --- | --- | --- |
| 1 | config 中记录的 `background_log`（若其指向的实例仍存活，或路径属于当前工作区） | `recorded` |
| 2 | `<workspace>/user/comfyui_<live_port>.log`（无存活实例时用默认端口 8188） | `derived_port` / `default_port` |
| 3 | `<workspace>/user/comfyui.log`（Manager 无 `--port` 时的日志） | `fallback_unsuffixed` |
| 4 | `<workspace>/user/comfyui_*.log` 中 mtime 最新者（**跳过** `.prev*.log` 轮转档） | `fallback_glob` |

显式 `--port N` 时只查该端口的日志 + 无后缀 `comfyui.log`；显式 `--path` 时只查该文件。

**要点**：

- `background_log` 键在 `comfy stop` 后**刻意保留** —— 这样启动失败/崩溃后仍能
  用 `comfy logs` 看到失败日志（crash-log 语义）。
- `--follow` 先打印末尾 N 行，再持续流式输出新行，Ctrl+C 退出。
- `--json` 输出 `{ok, path, source, served_port, count, truncated, lines[]}`；
  `--follow` 时为 `{...,follow:true,initial:[...]}` 并以 NDJSON 流式输出 `{"line": ...}`。
- 行数/字节上限：`LOGS_MAX_LINES=2000` / `LOGS_MAX_BYTES=256 KiB`（防 JSON 载荷失控）。
- 日志内容**原样回放**，因此可能包含 ComfyUI 核心 `app/logger.py` 写入的 ANSI 色码
  （在 `--json` 中表现为 `\u001b[32m` 等转义），这是与官方一致的刻意行为。

### 2.6 `comfy jobs`

本地作业子集（不依赖 websocket，便于脚本 / 无显卡环境）。数据来源：`GET /queue` 与 `GET /history`。

```bash
comfy jobs ls      [--host H] [--port P] [--json]
comfy jobs status <prompt_id> [--host H] [--port P] [--json]
comfy jobs wait    <prompt_id> [--timeout S] [--json]
comfy jobs watch   [--interval S]
```

> 官方 `jobs` 为 2700+ 行且深度耦合云端与渲染器框架，此处仅取本地语义。

### 2.7 `comfy templates ls` / `comfy run-template <name>`

数据源为**公共模板画廊** `raw.githubusercontent.com/Comfy-Org/workflow_templates`。

```bash
comfy templates ls [--name FILTER] [--limit N] [--refresh] [--gallery URL] [--json]
comfy run-template <name> [--wait] [--verbose] [--host H] [--port P] [--timeout S] [--json]
```

### 2.8 `comfy setup`

环境向导（本地版）：检查 Python / 工作区 / 服务。

```bash
comfy setup [--where ...] [--skip-verify]
```

### 2.9 `comfy update cli`

`update` 目标由 `all|comfy` 扩展为 `all|comfy|cli`：

```bash
comfy update cli     # 先走 PyPI 升级，必要时源码重装兜底
```

***

## 3. 本地 HTTP 约定（本组命令共性）

1. **绕过代理**：`cli/cmdline.py` 在进程启动即把 `127.0.0.1,localhost,::1` 写入
   `NO_PROXY/no_proxy`；新命令的 HTTP 统一走 `cli/command/net.py`（无代理 opener）。
   否则环境变量里的 `HTTP_PROXY` 会把本地 127.0.0.1 请求也送进代理并返回 502，
   表现为"服务未运行"的误判。
2. **地址解析**：`--host/--port` > 后台实例（config `background`）> `COMFYUI_HOST/PORT` > `127.0.0.1:8188`。
3. **机器可读输出**：JSON 一律经 `cli/output.py:emit_json()`，**不可**用 rich 的 `print`。

***

## 4. 关联文档

- [EXPERIENCE.md](EXPERIENCE.md) 第 25 章 —— 本轮修复复盘（rich 换行缺陷、后台启动 PATH 依赖、日志落盘设计）
- [json-output.md](json-output.md) —— `comfy run --json` 的 NDJSON 事件流格式
- [workflow_library_layout.md](workflow_library_layout.md) —— 工作流仓库布局
