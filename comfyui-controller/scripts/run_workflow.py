#!/usr/bin/env python3
"""Queue a ComfyUI workflow (API-format JSON) and poll until done. Prints prompt_id and output images."""
import argparse
import json
import time
import uuid
import urllib.request
import urllib.error


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
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", default="3198")  # comfyui-cli项目标准端口
    ap.add_argument("--workflow", required=True, help="Path to API workflow JSON (already edited; script does not modify it)")
    ap.add_argument("--timeout", type=int, default=300, help="Seconds to wait for completion")
    ap.add_argument("--poll", type=float, default=1.5, help="Seconds between history polls")
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
                images = find_output_images(item)
                print(json.dumps({"prompt_id": prompt_id, "images": images}))
                return
        time.sleep(args.poll)

    raise SystemExit("Timed out waiting for completion")


if __name__ == "__main__":
    main()
