#!/usr/bin/env python3
"""Queue a ComfyUI workflow (API-format JSON) and poll until done.

Prints a JSON result describing every output emitted by the workflow.
Each output carries its `/view` URL — the only contractual way to fetch
the bytes (see docs_cli/json-output.md, "Fetching output bytes").

Pass `--output-dir` (or set `$COMFYUI_OUTPUT_DIR`) to have every output
downloaded to disk; each downloaded entry then also carries a `path`
field pointing at the local file.
"""
import argparse
import json
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

# 本机 ComfyUI 位于回环地址，必须绕过 HTTP_PROXY/HTTPS_PROXY 环境变量，
# 否则请求会被本地代理拦截并返回 502，表现为"服务不可用"的假故障。
urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({}))
)


# SKILL.md 6.3 硬约束：这三个字段必须同时检查（VHS_VideoCombine 输出在 gifs
# 字段，即使实际产物是 mp4）。注意这里是"必查"而非"仅查" —— json-output.md
# 明确 category 是开放集（audio/3d/latents 等也可能出现），因此实际实现遍历
# 全部 category，这里保留常量用于缺项告警。
REQUIRED_OUTPUT_CATEGORIES = ("images", "gifs", "videos")

# 端口/host 解析优先级（见 SKILL.md 7.1）：命令行参数 > COMFYUI_PORT/COMFYUI_HOST 环境变量 > 默认值。
# 默认值跟随 ComfyUI 官方约定（8188）。3198 是历史单一部署环境的端口，非通用标准；
# 需沿用请显式设置 COMFYUI_PORT=3198。
DEFAULT_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1")
DEFAULT_PORT = os.environ.get("COMFYUI_PORT", "8188")


def http_json(url, method="GET", payload=None, timeout=30):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        raise SystemExit(f"HTTP Error {e.code}: {error_body}")


def http_bytes(url, timeout=120):
    """Fetch raw bytes (used for /view downloads)."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", "replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP Error {e.code}: {error_body}")


def load_workflow(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_output_images(history_obj):
    """从执行历史中提取输出文件信息。

    同时检查多种输出字段,避免视频任务被误判为无输出:
    - images: 图片类输出(SaveImage 节点)
    - gifs:   VHS_VideoCombine 节点的视频输出字段(SKILL.md 4.11.1 明确禁忌漏检)
    - videos: 部分视频节点的输出字段(兼容新版本 VHS)

    返回扁平化的输出项列表,每项含 filename/type 等字段。
    """
    outputs = history_obj.get("outputs", {})
    images = []
    for node_id, node_out in outputs.items():
        # 按 SKILL.md 3.1.3 / 4.11.1 要求,同时检查多种输出字段
        for key in ("images", "gifs", "videos"):
            for item in (node_out.get(key) or []):
                images.append(item)
    return images


def _view_url(base, filename, subfolder, file_type):
    """Build the /view URL — the contractual byte-retrieval path."""
    params = {"filename": filename, "subfolder": subfolder, "type": file_type}
    return f"{base}/view?{urllib.parse.urlencode(params)}"


def collect_outputs(history_obj, base, workflow=None):
    """Build the structured Output list from a /history entry.

    Field names follow the Output object contract in docs_cli/json-output.md
    (category / node_id / class_type / title / filename / subfolder / type / url).

    `node_out` is iterated over *all* keys rather than the three known ones,
    because the contract declares `category` an open set (audio/3d/latents …).
    The three required categories are still always scanned — see
    REQUIRED_OUTPUT_CATEGORIES.
    """
    workflow = workflow if isinstance(workflow, dict) else {}
    results = []
    seen_categories = set()

    for node_id, node_out in (history_obj.get("outputs") or {}).items():
        if not isinstance(node_out, dict):
            continue
        node_id = str(node_id)
        node_def = workflow.get(node_id)
        if not isinstance(node_def, dict):
            node_def = {}
        # 与 cli/command/run.py 的 get_class_type / get_title 保持一致的契约：
        #   class_type: 缺失时用 ""（不是 null）
        #   title:      _meta.title → class_type → node_id（三级兜底，永不为空）
        raw_class = node_def.get("class_type")
        class_type = raw_class if isinstance(raw_class, str) and raw_class else ""
        meta = node_def.get("_meta")
        meta_title = meta.get("title") if isinstance(meta, dict) else None
        title = meta_title if isinstance(meta_title, str) and meta_title else (class_type or node_id)

        for category, items in node_out.items():
            if not isinstance(items, list):
                continue
            seen_categories.add(category)
            for item in items:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                filename = item.get("filename")
                subfolder = item.get("subfolder") or ""
                file_type = item.get("type") or "output"
                results.append({
                    "category": category,
                    "node_id": node_id,
                    "class_type": class_type,
                    "title": title,
                    "filename": filename,
                    "subfolder": subfolder,
                    "type": file_type,
                    "url": _view_url(base, filename, subfolder, file_type),
                })

    missing = [c for c in REQUIRED_OUTPUT_CATEGORIES if c not in seen_categories]
    return results, missing


def _safe_join(output_dir, subfolder, filename):
    """Join output_dir + server-supplied subfolder/filename, refusing escapes.

    Server-supplied names are untrusted input: custom save nodes can emit
    arbitrary paths, so anything resolving outside `output_dir` is flattened
    to its basename.
    """
    root = os.path.abspath(output_dir)

    def _clean(value):
        value = (value or "").replace("\\", "/")
        parts = [p for p in value.split("/") if p not in ("", ".", "..")]
        return parts

    sub_parts = _clean(subfolder)
    name_parts = _clean(filename)
    if not name_parts:
        raise ValueError("empty filename from server")
    target = os.path.abspath(os.path.join(root, *sub_parts, *name_parts))
    if target != root and not target.startswith(root + os.sep):
        # Should be unreachable given _clean(), kept as a defensive guard.
        raise ValueError(f"refusing path outside output dir: {filename}")
    return target


def download_outputs(outputs, output_dir, timeout=120):
    """Fetch every output through its /view URL into output_dir.

    Download failures are collected in `errors` instead of aborting, so a
    single bad output never loses the whole batch.
    """
    downloaded = []
    errors = []
    root = os.path.abspath(output_dir)
    os.makedirs(root, exist_ok=True)

    for out in outputs:
        try:
            target = _safe_join(root, out.get("subfolder"), out.get("filename"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            data = http_bytes(out["url"], timeout=timeout)
            with open(target, "wb") as f:
                f.write(data)
            entry = dict(out)
            entry["path"] = target
            downloaded.append(entry)
        except Exception as e:
            errors.append({
                "filename": out.get("filename"),
                "node_id": out.get("node_id"),
                "category": out.get("category"),
                "error": str(e),
            })
    return downloaded, errors


def extract_error_message(status):
    """从 history status 中提取执行错误信息。
    ComfyUI 执行失败时 status_str='error'，messages 中含 execution_error 条目。
    注意：失败时 completed 可能为 False，不能依赖 completed 判断是否结束。
    """
    messages = status.get("messages", [])
    for msg in messages:
        if not isinstance(msg, list) or len(msg) < 2:
            continue
        msg_type, msg_data = msg[0], msg[1]
        if msg_type == "execution_error" and isinstance(msg_data, dict):
            node_id = msg_data.get("node_id", "?")
            node_type = msg_data.get("node_type", "?")
            exception = msg_data.get("exception_message", "未知错误")
            exception_type = msg_data.get("exception_type", "")
            detail = f"节点 {node_id} ({node_type}): {exception}"
            if exception_type:
                detail += f" [{exception_type}]"
            return detail
    # 回退：取第一条非 execution_start/cached 的消息
    for msg in messages:
        if isinstance(msg, list) and len(msg) >= 2:
            if msg[0] not in ("execution_start", "execution_cached"):
                return f"{msg[0]}: {msg[1]}"
    return "执行失败（无详细错误信息）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", default=DEFAULT_PORT)
    ap.add_argument("--workflow", required=True, help="Path to API workflow JSON (already edited; script does not modify it)")
    ap.add_argument("--timeout", type=int, default=300, help="Seconds to wait for completion")
    ap.add_argument("--poll", type=float, default=1.5, help="Seconds between history polls")
    # 默认等待完成（无需 --wait），显式 --wait 仅为兼容 README 示例中的写法
    ap.add_argument("--wait", action="store_true",
                    help="(no-op) waiting for completion is already the default behaviour")
    ap.add_argument("--output-dir", default=os.environ.get("COMFYUI_OUTPUT_DIR"),
                    help="Download outputs to this directory (default: $COMFYUI_OUTPUT_DIR, "
                         "no download when unset)")
    args = ap.parse_args()

    base = f"http://{args.host}:{args.port}"
    workflow = load_workflow(args.workflow)

    payload = {
        "client_id": str(uuid.uuid4()),
        "prompt": workflow,
    }

    resp = http_json(f"{base}/prompt", method="POST", payload=payload)
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        raise SystemExit(f"No prompt_id returned: {resp}")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        hist = http_json(f"{base}/history/{prompt_id}")
        item = hist.get(prompt_id)
        if item:
            status = item.get("status", {})
            status_str = status.get("status_str", "")
            # 优先检测执行失败：status_str='error' 时 completed 可能为 False
            if status_str == "error":
                error_msg = extract_error_message(status)
                raise SystemExit(f"Task failed: {error_msg}")
            if status.get("completed"):
                outputs, missing = collect_outputs(item, base, workflow)
                result = {
                    "prompt_id": prompt_id,
                    "outputs": outputs,
                    "images": outputs,  # 向后兼容旧字段名（内容同 outputs）
                    "output_dir": None,
                    "downloaded": [],
                    "warnings": [],
                }
                if missing:
                    result["warnings"].append(
                        "未出现以下输出字段（部分任务可能确实不产生）: " + ", ".join(missing)
                    )
                if args.output_dir:
                    downloaded, dl_errors = download_outputs(outputs, args.output_dir)
                    result["output_dir"] = os.path.abspath(args.output_dir)
                    result["downloaded"] = downloaded
                    for err in dl_errors:
                        result["warnings"].append(
                            f"下载失败 {err['filename']} ({err['category']}): {err['error']}"
                        )
                print(json.dumps(result))
                return
        time.sleep(args.poll)

    raise SystemExit("Timed out waiting for completion")


if __name__ == "__main__":
    main()
