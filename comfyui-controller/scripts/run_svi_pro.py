"""
SVI Pro 逐段执行编排脚本 v2
HIGH/LOW 拆分执行，每段2步 + 融合 = 11步
用法: python run_svi_pro.py
"""
import json
import os
import sys
import time
import shutil
import urllib.request
import urllib.error

COMFYUI_URL = "http://127.0.0.1:3198"
ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
COMFYUI_OUTPUT = "E:/comfyui-cli/output"
COMFYUI_INPUT = "D:/2026-ComfyUI-V8.3/input"
NUM_SEGMENTS = 5


def submit_workflow(workflow):
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFYUI_URL}/prompt",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    if "error" in result:
        raise RuntimeError(f"工作流验证失败: {result['error']}")
    return result["prompt_id"]


def wait_for_completion(prompt_id, timeout=600):
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"{COMFYUI_URL}/history/{prompt_id}"
            with urllib.request.urlopen(url, timeout=30) as resp:
                history = json.loads(resp.read().decode())
            if prompt_id in history:
                status = history[prompt_id].get("status", {})
                if status.get("completed", False):
                    return history[prompt_id]
                if status.get("status_str") == "error":
                    raise RuntimeError(f"工作流执行失败: {status}")
        except urllib.error.URLError as e:
            print(f"  轮询超时，重试... ({e})")
        time.sleep(5)
    raise TimeoutError(f"工作流 {prompt_id} 超时 ({timeout}s)")


def free_memory():
    payload = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFYUI_URL}/free",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print("  显存已释放")
    except Exception as e:
        print(f"  显存释放失败: {e}")


def extract_latent(history_entry):
    """从history中提取latent文件名"""
    outputs = history_entry.get("outputs", {})
    for node_id, node_output in outputs.items():
        if "latents" in node_output:
            for lat in node_output["latents"]:
                fname = lat["filename"]
                if lat.get("subfolder"):
                    fname = f"{lat['subfolder']}/{fname}"
                return fname
    return None


def extract_video(history_entry):
    """从history中提取视频文件名"""
    outputs = history_entry.get("outputs", {})
    for node_id, node_output in outputs.items():
        if "gifs" in node_output:
            for gif in node_output["gifs"]:
                fname = gif["filename"]
                if gif.get("subfolder"):
                    fname = f"{gif['subfolder']}/{fname}"
                return fname
    return None


def replace_latent_in_workflow(wf, latent_filename):
    """替换工作流中所有LoadLatent节点的latent输入"""
    found = False
    for nid, node in wf.items():
        if node["class_type"] == "LoadLatent":
            node["inputs"]["latent"] = latent_filename
            print(f"  替换 LoadLatent: {latent_filename}")
            found = True
    return found


def replace_videos_in_merge(wf, video_filenames):
    idx = 0
    for nid, node in wf.items():
        if node["class_type"] == "VHS_LoadVideo":
            if idx < len(video_filenames):
                node["inputs"]["video"] = video_filenames[idx]
                print(f"  替换 VHS_LoadVideo[{idx}]: {video_filenames[idx]}")
                idx += 1
    return idx == len(video_filenames)


def copy_to_input(filename):
    src = os.path.join(COMFYUI_OUTPUT, filename)
    dst = os.path.join(COMFYUI_INPUT, filename)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  复制视频到input: {filename}")
        return filename
    print(f"  警告: 视频文件不存在 {src}")
    return None


def run_step(step_name, wf_path, latent_replacements=None, timeout=600):
    """执行单步工作流"""
    print(f"\n{'='*50}")
    print(f"执行: {step_name}")
    print(f"{'='*50}")

    with open(wf_path, "r", encoding="utf-8") as f:
        wf = json.load(f)

    if latent_replacements:
        for lat in latent_replacements:
            replace_latent_in_workflow(wf, lat)

    try:
        prompt_id = submit_workflow(wf)
        print(f"  已提交, prompt_id: {prompt_id[:16]}...")
    except Exception as e:
        print(f"  提交失败: {e}")
        return None

    try:
        history = wait_for_completion(prompt_id, timeout=timeout)
        print(f"  完成")
    except Exception as e:
        print(f"  执行失败: {e}")
        return None

    latent_file = extract_latent(history)
    video_file = extract_video(history)
    if latent_file:
        print(f"  latent: {latent_file}")
    if video_file:
        print(f"  video: {video_file}")

    free_memory()
    return {"latent": latent_file, "video": video_file, "history": history}


def main():
    print("=" * 60)
    print("SVI Pro 逐段执行编排脚本 v2 (HIGH/LOW 拆分)")
    print("=" * 60)

    video_files = []
    prev_low_latent = None

    for seg in range(NUM_SEGMENTS):
        # HIGH 步骤
        high_wfp = os.path.join(ASSETS_DIR, f"c7_svi_seg{seg+1}_high.json")
        high_replacements = [prev_low_latent] if prev_low_latent else None
        high_result = run_step(f"段{seg+1} HIGH", high_wfp, high_replacements)

        if not high_result or not high_result["latent"]:
            print(f"\n段{seg+1} HIGH 执行失败，终止")
            sys.exit(1)
        high_latent = high_result["latent"]

        # LOW 步骤
        low_wfp = os.path.join(ASSETS_DIR, f"c7_svi_seg{seg+1}_low.json")
        low_result = run_step(f"段{seg+1} LOW", low_wfp, [high_latent])

        if not low_result or not low_result["video"]:
            print(f"\n段{seg+1} LOW 执行失败，终止")
            sys.exit(1)

        video_files.append(low_result["video"])
        prev_low_latent = low_result["latent"]

    # 融合
    print(f"\n{'='*50}")
    print(f"执行融合")
    print(f"{'='*50}")

    input_videos = []
    for vf in video_files:
        iv = copy_to_input(vf)
        if iv:
            input_videos.append(iv)

    if len(input_videos) < NUM_SEGMENTS:
        print(f"  错误: 只有 {len(input_videos)} 个视频，需要 {NUM_SEGMENTS} 个")
        sys.exit(1)

    merge_wfp = os.path.join(ASSETS_DIR, "c7_svi_merge.json")
    with open(merge_wfp, "r", encoding="utf-8") as f:
        wf = json.load(f)
    replace_videos_in_merge(wf, input_videos)

    try:
        prompt_id = submit_workflow(wf)
        print(f"  已提交, prompt_id: {prompt_id[:16]}...")
    except Exception as e:
        print(f"  提交失败: {e}")
        sys.exit(1)

    try:
        history = wait_for_completion(prompt_id, timeout=300)
        print(f"  完成")
    except Exception as e:
        print(f"  执行失败: {e}")
        sys.exit(1)

    final_video = extract_video(history)
    if final_video:
        print(f"\n{'='*60}")
        print(f"✓ 20秒长视频生成完成!")
        print(f"  输出: {COMFYUI_OUTPUT}/{final_video}")
        print(f"{'='*60}")
    else:
        print(f"\n融合失败：未找到输出视频")


if __name__ == "__main__":
    main()
