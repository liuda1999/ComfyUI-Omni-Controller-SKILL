"""视频任务执行器：集成预检反问环节、节点校验、工作流生成与执行

流程:
1. 预检反问环节 (pre_task_inquiry.run_pre_task_inquiry) - 不可跳过
2. 节点完整性校验 (check_workflow_dependencies.check_video_nodes_available)
3. 工作流生成 (advanced_workflow_builder.WorkflowAssembler)
4. 工作流执行 (UI→API转换 + 提交 + 监控)
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

# 添加scripts目录到path，确保能导入同目录模块
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

# ComfyUI 服务器地址
BASE_URL = "http://127.0.0.1:3198"  # comfyui-cli项目标准端口

# 预检环节返回的 ratio 为整数(1=9:16, 2=16:9, 3=1:1)，
# 工作流构建器需要字符串比例，此处做映射
_RATIO_INT_TO_STR = {1: "9:16", 2: "16:9", 3: "1:1"}


def check_server_online():
    """检查ComfyUI服务器是否在线

    Returns:
        bool: True 表示服务器在线，False 表示不可用
    """
    try:
        url = f"{BASE_URL}/system_stats"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            json.loads(resp.read().decode("utf-8"))
        return True
    except Exception:
        return False


def _get_widget_order_from_object_info(obj_info, class_type):
    """从 object_info schema 获取节点的 widget 输入名顺序（required→optional，仅 widget 类型）。

    与 ComfyUI 前端 widgets_values 的序列化顺序一致：节点类定义中 required 再 optional、
    仅 widget 类型（COMBO/INT/FLOAT/STRING/BOOLEAN）输入按声明顺序排列。
    对第三方/自定义节点（Flux2 / Wan2.2 / QwenVL 等）同样适用。
    """
    node_schema = (obj_info or {}).get(class_type, {})
    inputs_def = node_schema.get("input", {})
    widget_types = ("INT", "FLOAT", "STRING", "COMBO", "BOOLEAN")
    order = []
    for section in ("required", "optional"):
        sec = inputs_def.get(section, {})
        if not isinstance(sec, dict):
            continue
        for name, type_info in sec.items():
            if isinstance(type_info, list) and len(type_info) > 0:
                t = type_info[0]
                if isinstance(t, list) or t in widget_types:
                    order.append(name)
    return order


def ui_to_api(ui_workflow):
    """将 ComfyUI UI 格式工作流转换为 API 格式。

    连线解析以全局 links 数组为准（标准 ComfyUI UI 格式），不依赖 inputs[].link：
    links 数组是连线的事实来源，按目标节点+目标插槽反查输入名，对任何节点类型通用。
    widget 值优先按节点 inputs 数组中声明的顺序映射；对未声明 widget 输入的节点
    （如 WanVideoModelLoader / WanVideoLoraSelect 等 inputs 为空的节点），
    回退到 object_info 的 schema widget 顺序映射，避免按 required 全量位置错位。

    Args:
        ui_workflow: UI 格式工作流 dict（含 nodes, links）

    Returns:
        dict: {"prompt": {node_id: {class_type, inputs}}}
    """
    web_nodes = ui_workflow.get("nodes", [])
    node_lookup = {n.get("id"): n for n in web_nodes}

    # 从 links 数组构建连接：target_node_id -> {input_name: [src_id, src_slot]}
    connections = {}
    for link in ui_workflow.get("links", []):
        if not isinstance(link, list) or len(link) < 5:
            continue
        _link_id, src_id, src_slot, tgt_id, tgt_slot = link[:5]
        tgt_node = node_lookup.get(tgt_id)
        if tgt_node is None:
            continue
        tgt_inputs = tgt_node.get("inputs", [])
        if tgt_slot >= len(tgt_inputs):
            continue
        inp_name = tgt_inputs[tgt_slot].get("name")
        if not inp_name:
            continue
        connections.setdefault(tgt_id, {})[inp_name] = [str(src_id), src_slot]

    nodes = {}
    for node in web_nodes:
        node_id = str(node["id"])
        class_type = node["type"]
        api_node = {"class_type": class_type, "inputs": {}}
        widgets_values = node.get("widgets_values", [])
        if not isinstance(widgets_values, list):
            widgets_values = []
        widget_idx = 0
        conn = connections.get(node.get("id"), {})

        for inp in node.get("inputs", []):
            inp_name = inp.get("name")
            if not inp_name:
                continue
            # 连线优先（被连接的 widget 输入以连线为准）
            if inp_name in conn:
                api_node["inputs"][inp_name] = conn[inp_name]
                continue
            # 未连接且有 widget 声明 → 按节点 inputs 数组声明顺序取值
            if "widget" in inp and widget_idx < len(widgets_values):
                api_node["inputs"][inp_name] = widgets_values[widget_idx]
                widget_idx += 1

        # 剩余 widget（inputs 数组未声明的节点）回退到 schema widget 顺序映射
        if widget_idx < len(widgets_values):
            try:
                url = f"{BASE_URL}/object_info/{class_type}"
                with urllib.request.urlopen(url, timeout=5) as resp:
                    obj_info = json.loads(resp.read())
                widget_order = _get_widget_order_from_object_info(obj_info, class_type)
                for inp_name in widget_order:
                    if widget_idx >= len(widgets_values):
                        break
                    if inp_name not in api_node["inputs"]:
                        api_node["inputs"][inp_name] = widgets_values[widget_idx]
                        widget_idx += 1
            except Exception:
                # 无法获取 object_info：跳过剩余 widget（保持原行为）
                pass

        nodes[node_id] = api_node

    return {"prompt": nodes}


def queue_prompt(api_workflow):
    """提交工作流到 ComfyUI

    Args:
        api_workflow: API 格式工作流 dict（含 prompt 键）

    Returns:
        dict: ComfyUI 返回的提交结果，含 prompt_id

    Raises:
        urllib.error.HTTPError: 提交失败时抛出
    """
    data = json.dumps(api_workflow).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/prompt",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_history(prompt_id):
    """获取指定 prompt_id 的执行历史

    Args:
        prompt_id: 工作流提交后返回的 ID

    Returns:
        dict: 历史记录，失败返回空 dict
    """
    try:
        url = f"{BASE_URL}/history/{prompt_id}"
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def wait_for_completion(prompt_id, timeout=1800):
    """等待工作流执行完成（超时30分钟）

    轮询 /queue 和 /history 接口，直到任务出现在历史记录中或超时。
    同时检测执行错误，避免任务实际失败时被误判为成功。

    按 SKILL.md 3.1.3 节要求:
    - 失败时 status.status_str='error', status.completed 可能为 False
    - 不能依赖 completed 字段判断是否结束,必须显式检查 status_str
    - 错误信息在 status.messages 中的 execution_error 条目

    Args:
        prompt_id: 工作流提交后返回的 ID
        timeout: 最大等待秒数，默认 1800（30分钟）

    Returns:
        dict: {"completed": bool, "outputs": dict, "status": dict,
               "success": bool, "error": str, "error_type": str}
        - completed: 任务已结束(无论成功失败)
        - success:   任务执行成功(无 execution_error)
        - error:     失败时的错误描述(成功时为空)
        - error_type: 错误分类(如 execution_error / validation_error / timeout)
    """
    start_time = time.time()
    last_status = None

    while time.time() - start_time < timeout:
        try:
            # 检查队列状态
            url = f"{BASE_URL}/queue"
            with urllib.request.urlopen(url, timeout=10) as resp:
                queue = json.loads(resp.read().decode("utf-8"))
            running = queue.get("queue_running", [])
            pending = queue.get("queue_pending", [])

            # 检查历史，任务完成后会出现在历史记录中
            history = get_history(prompt_id)
            if prompt_id in history:
                outputs = history[prompt_id].get("outputs", {})
                status = history[prompt_id].get("status", {})
                status_str = status.get("status_str", "")

                # 优先检测执行失败(按 SKILL.md 3.1.3 节要求)
                # 失败时 status_str='error',completed 可能为 False,不能依赖 completed
                if status_str == "error":
                    error_msg, error_node = _extract_execution_error(status)
                    return {
                        "completed": True, "success": False,
                        "outputs": outputs, "status": status,
                        "error": error_msg, "error_type": "execution_error",
                        "error_node": error_node,
                    }

                # 显式检测验证错误(工作流提交后校验失败)
                # status_str='validation_error' 时通常不会进入 history,但兜底检测
                if status_str == "validation_error":
                    error_msg = _extract_validation_error(status)
                    return {
                        "completed": True, "success": False,
                        "outputs": outputs, "status": status,
                        "error": error_msg, "error_type": "validation_error",
                    }

                # 成功完成
                if status.get("completed"):
                    return {
                        "completed": True, "success": True,
                        "outputs": outputs, "status": status,
                        "error": "", "error_type": "",
                    }

                # status_str 不是 error/validation_error 但 completed=False
                # 可能是异常中断,返回带警告的失败结果
                if status_str and status_str not in ("success", ""):
                    return {
                        "completed": True, "success": False,
                        "outputs": outputs, "status": status,
                        "error": f"任务异常结束: status_str={status_str}",
                        "error_type": status_str,
                    }

            current_status = f"running={len(running)}, pending={len(pending)}"
            if current_status != last_status:
                elapsed = int(time.time() - start_time)
                print(f"  [{elapsed}s] {current_status}")
                last_status = current_status

        except Exception as e:
            print(f"  查询状态错误: {e}")

        time.sleep(3)

    return {
        "completed": False, "success": False,
        "error": f"任务在 {timeout} 秒内未完成(超时)",
        "error_type": "timeout",
    }


def _extract_execution_error(status):
    """从 history status.messages 中提取 execution_error 详情。

    ComfyUI 执行失败时 messages 中含 ["execution_error", {node_id, node_type,
    exception_message, exception_type}] 条目。

    Returns:
        (error_description: str, node_info: dict)
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
            desc = f"节点 {node_id} ({node_type}) 执行失败: {exception}"
            if exception_type:
                desc += f" [{exception_type}]"
            return desc, {
                "node_id": node_id, "node_type": node_type,
                "exception_message": exception, "exception_type": exception_type,
            }
    # 回退:无法提取详细错误时返回通用描述
    return "执行失败(未提供详细错误信息)", {}


def _extract_validation_error(status):
    """从 history status 中提取验证错误信息。"""
    messages = status.get("messages", [])
    for msg in messages:
        if isinstance(msg, list) and len(msg) >= 2:
            if msg[0] == "validation_error":
                return f"工作流验证失败: {msg[1]}"
    return "工作流验证失败(未提供详细信息)"


def _extract_output_path(outputs):
    """从执行历史输出中提取输出文件路径

    Args:
        outputs: history[prompt_id]["outputs"] 字典

    Returns:
        str: 输出文件名，无输出时返回空字符串
    """
    for node_id, node_output in outputs.items():
        for key in ("videos", "images", "gifs"):
            if key in node_output:
                for item in node_output[key]:
                    fname = item.get("filename", "")
                    if fname:
                        return fname
    return ""


def _generate_workflow(builder, task_type, inquiry_result, image, prompt, kwargs):
    """根据任务类型调用构建器生成 UI 格式工作流

    使用预检收集的参数覆盖传入参数，根据 task_type 分派到对应的 _build_* 方法。

    Args:
        builder: WorkflowAssembler 实例
        task_type: 任务类型
        inquiry_result: 预检返回的参数字典
        image: 传入的输入图像路径（可被预检参数覆盖）
        prompt: 传入的提示词（可被预检参数覆盖）
        kwargs: 其他参数（first_image, last_image, image_names 等）

    Returns:
        dict: UI 格式工作流 JSON，失败返回 None
    """
    # 使用预检收集的参数覆盖传入参数
    final_prompt = inquiry_result.get("positive_prompt", prompt)
    # V19验证：lightx2v LoRA加速后6-8步即可，默认8步
    final_steps = inquiry_result.get("steps", 8)
    # 预检 ratio 为整数(1/2/3)，构建器需要字符串比例
    ratio_val = inquiry_result.get("ratio")
    final_ratio = _RATIO_INT_TO_STR.get(ratio_val, "9:16")
    seed = kwargs.get("seed", 12345)
    # 架构方案（方案A: dual_serial 生产环境推荐 / 方案B: single 简单场景）
    architecture_scheme = inquiry_result.get("architecture_scheme", "single")
    # 硬件自适应参数（预检 get_adaptive_params 按显存分档计算，此前未传递给 builder）
    # 使 builder 的 blocks_to_swap / attention_mode / base_precision / split_step
    # 不再使用硬编码默认值，而是使用预检推荐的硬件档位值
    adaptive = inquiry_result.get("adaptive_params") or {}
    blocks_to_swap = adaptive.get("blocks_to_swap", 20)
    attention_mode = adaptive.get("attention_mode", "sdpa")
    base_precision = adaptive.get("base_precision", "bf16")
    split_step = adaptive.get("split_step")

    if task_type == "img2vid":
        image_name = image or kwargs.get("image_name", "input_image.png")
        return builder._build_img2vid(
            image_name=image_name,
            user_prompt=final_prompt,
            ratio=final_ratio,
            steps=final_steps,
            seed=seed,
            filename_prefix="img2vid",
            architecture_scheme=architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision, split_step=split_step)

    elif task_type == "first_last_frame":
        first_image = kwargs.get("first_image", image or "first_frame.png")
        last_image = kwargs.get("last_image", "last_frame.png")
        return builder._build_first_last_frame(
            first_image=first_image,
            last_image=last_image,
            user_prompt=final_prompt,
            ratio=final_ratio,
            steps=final_steps,
            seed=seed,
            filename_prefix="first_last",
            architecture_scheme=architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision)

    elif task_type == "multi_image_video":
        image_names = kwargs.get("image_names")
        if not image_names:
            image_count = kwargs.get("image_count", 3)
            image_names = [f"image_{i+1}.png" for i in range(image_count)]
        return builder._build_multi_image_video(
            image_names=image_names,
            user_prompt=final_prompt,
            ratio=final_ratio,
            steps=final_steps,
            seed=seed,
            filename_prefix="multi_img",
            architecture_scheme=architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision, split_step=split_step)

    elif task_type == "long_video":
        image_name = image or kwargs.get("image_name", "input_image.png")
        segments = kwargs.get("segments", 2)
        return builder._build_long_video(
            image_name=image_name,
            user_prompt=final_prompt,
            ratio=final_ratio,
            steps=final_steps,
            seed=seed,
            segments=segments,
            filename_prefix="long_vid",
            architecture_scheme=architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision, split_step=split_step)

    elif task_type == "video_concat":
        video_paths = kwargs.get("video_paths")
        if not video_paths:
            video_count = kwargs.get("video_count", 2)
            video_paths = [f"input_video_{i+1}.mp4" for i in range(video_count)]
        return builder._build_video_concat(
            video_paths=video_paths,
            user_prompt=final_prompt,
            ratio=final_ratio,
            filename_prefix="vid_concat")

    elif task_type == "multi_ref_video":
        ref_images = kwargs.get("ref_images")
        if not ref_images:
            ref_count = kwargs.get("ref_count", 2)
            ref_images = [f"ref_image_{i+1}.png" for i in range(ref_count)]
        return builder._build_multi_ref_video(
            ref_images=ref_images,
            user_prompt=final_prompt,
            ratio=final_ratio,
            steps=final_steps,
            seed=seed,
            filename_prefix="multi_ref",
            architecture_scheme=architecture_scheme,
            blocks_to_swap=blocks_to_swap, attention_mode=attention_mode,
            base_precision=base_precision, split_step=split_step)

    else:
        print(f"[错误] 不支持的任务类型: {task_type}")
        return None


def run_video_task(task_type, image=None, prompt="", **kwargs):
    """视频任务执行主入口（强制预检，不可跳过）

    流程:
    1. 预检反问环节 (pre_task_inquiry.run_pre_task_inquiry)
    2. 节点完整性校验 (check_workflow_dependencies.check_video_nodes_available)
    3. 工作流生成 (advanced_workflow_builder.AdvancedWorkflowBuilder)
    4. 工作流执行 (UI→API转换 + 提交 + 监控)

    Args:
        task_type: 任务类型 (img2vid/first_last_frame/multi_image_video/
                   long_video/video_concat/multi_ref_video)
        image: 输入图像路径（可选，预检环节会让用户选择）
        prompt: 用户提示词（可选，预检环节会收集）
        **kwargs: 其他参数（first_image, last_image, image_names, seed 等）

    Returns:
        dict: {success: bool, output_path: str, error: str}
    """
    print("=" * 60)
    print("视频生成任务执行器")
    print(f"任务类型: {task_type}")
    print("=" * 60)

    # 前置检查：服务器是否在线
    if not check_server_online():
        return {"success": False, "output_path": "",
                "error": f"ComfyUI 服务器 {BASE_URL} 不可用，请先启动服务器"}

    # === 步骤1: 强制预检反问环节 ===
    print("\n[步骤1/4] 预检反问环节（不可跳过）")
    from pre_task_inquiry import run_pre_task_inquiry
    inquiry_result = run_pre_task_inquiry()
    if inquiry_result is None:
        # SubTask 6.2: 预检不通过时阻止执行
        print("[错误] 预检未通过，任务已终止")
        return {"success": False, "output_path": "", "error": "预检未通过，任务已终止"}

    # === 步骤2: 节点完整性校验 ===
    print("\n[步骤2/4] 节点完整性校验")
    from check_workflow_dependencies import (
        check_video_nodes_available, report_missing_video_nodes)
    node_check = check_video_nodes_available(BASE_URL)
    if not report_missing_video_nodes(node_check):
        # SubTask 6.3: 节点校验不通过时阻止执行
        print("[错误] 缺少必需节点，任务已终止")
        return {"success": False, "output_path": "",
                "error": "缺少必需视频节点，任务已终止"}

    # === 步骤3: 工作流生成 ===
    print("\n[步骤3/4] 生成工作流")
    # 实际类名为 WorkflowAssembler，此处别名以满足 AdvancedWorkflowBuilder 约定
    from advanced_workflow_builder import WorkflowAssembler as AdvancedWorkflowBuilder
    builder = AdvancedWorkflowBuilder()

    ui_workflow = _generate_workflow(
        builder, task_type, inquiry_result, image, prompt, kwargs)
    if ui_workflow is None:
        return {"success": False, "output_path": "",
                "error": f"工作流生成失败，不支持的任务类型: {task_type}"}

    node_count = len(ui_workflow.get("nodes", []))
    print(f"  工作流已生成: {node_count} 个节点")

    # === 步骤4: 工作流执行 ===
    print("\n[步骤4/4] 执行工作流")
    # UI→API 转换
    print("  转换 UI→API 格式...")
    api_workflow = ui_to_api(ui_workflow)
    print(f"  API 节点数: {len(api_workflow['prompt'])}")

    # 提交
    print("  提交到 ComfyUI...")
    try:
        result = queue_prompt(api_workflow)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"  提交失败 HTTP {e.code}: {error_body[:500]}")
        return {"success": False, "output_path": "",
                "error": f"提交失败 HTTP {e.code}: {error_body[:200]}"}
    except Exception as e:
        print(f"  提交异常: {e}")
        return {"success": False, "output_path": "", "error": f"提交异常: {e}"}

    if "error" in result:
        print(f"  工作流错误: {json.dumps(result['error'], ensure_ascii=False)[:500]}")
        return {"success": False, "output_path": "",
                "error": f"工作流错误: {json.dumps(result['error'], ensure_ascii=False)[:200]}"}

    prompt_id = result.get("prompt_id")
    if not prompt_id:
        print(f"  未获取到 prompt_id: {result}")
        return {"success": False, "output_path": "",
                "error": f"未获取到 prompt_id: {result}"}

    print(f"  prompt_id: {prompt_id}")

    # 等待完成(修复后同时返回 completed 和 success)
    completion = wait_for_completion(prompt_id, timeout=1800)

    # 任务未完成(超时或连接中断)
    if not completion.get("completed"):
        error = completion.get("error", "unknown")
        error_type = completion.get("error_type", "unknown")
        print(f"  执行未完成 [{error_type}]: {error}")
        return {"success": False, "output_path": "",
                "error": f"执行未完成 [{error_type}]: {error}",
                "error_type": error_type}

    # 任务完成但执行失败(关键修复:原代码漏检,会误报成功)
    if not completion.get("success"):
        error = completion.get("error", "未知执行错误")
        error_type = completion.get("error_type", "execution_error")
        error_node = completion.get("error_node", {})
        print(f"  执行失败 [{error_type}]: {error}")
        if error_node:
            print(f"  失败节点: {error_node.get('node_id')} ({error_node.get('node_type')})")
            print(f"  异常类型: {error_node.get('exception_type', 'N/A')}")
        return {"success": False, "output_path": "",
                "error": f"[{error_type}] {error}",
                "error_type": error_type, "error_node": error_node}

    # 任务真正成功
    outputs = completion.get("outputs", {})
    output_path = _extract_output_path(outputs)

    # 输出为空检查(避免"成功但无输出"的误判)
    if not output_path:
        print("  警告: 任务标记为成功,但未找到输出文件(可能输出字段未识别)")
        return {"success": False, "output_path": "",
                "error": "任务执行成功但无输出文件(检查 images/gifs/videos 字段)",
                "error_type": "no_output"}

    print(f"  输出文件: {output_path}")
    print("\n视频任务执行完成。")
    return {"success": True, "output_path": output_path, "error": ""}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="视频任务执行器（强制预检）")
    ap.add_argument("task_type",
                    choices=["img2vid", "first_last_frame", "multi_image_video",
                             "long_video", "video_concat", "multi_ref_video"],
                    help="视频任务类型")
    ap.add_argument("--image", default=None, help="输入图像路径")
    ap.add_argument("--prompt", default="", help="用户提示词")
    ap.add_argument("--first-image", dest="first_image", default=None,
                    help="首帧图像路径（first_last_frame 任务）")
    ap.add_argument("--last-image", dest="last_image", default=None,
                    help="尾帧图像路径（first_last_frame 任务）")
    ap.add_argument("--segments", type=int, default=2,
                    help="长视频段数（long_video 任务）")
    ap.add_argument("--seed", type=int, default=12345, help="随机种子")
    args = ap.parse_args()

    extra = {}
    if args.first_image:
        extra["first_image"] = args.first_image
    if args.last_image:
        extra["last_image"] = args.last_image
    extra["segments"] = args.segments
    extra["seed"] = args.seed

    result = run_video_task(args.task_type, image=args.image,
                            prompt=args.prompt, **extra)
    if result["success"]:
        print(f"\n任务成功，输出: {result['output_path']}")
        sys.exit(0)
    else:
        print(f"\n任务失败: {result['error']}")
        sys.exit(1)
