"""
查询 SVI Pro 工作流所需关键节点的 object_info，确认参数格式。
"""
import os
import json
import urllib.request

# 绕过本机代理：127.0.0.1 请求若经 HTTP_PROXY 会被拦截并返回 502（假故障），
# 表现为“服务不可用”。本脚本只访问本机 ComfyUI，故对所有请求禁用代理。
urllib.request.install_opener(
    urllib.request.build_opener(urllib.request.ProxyHandler({}))
)

# 端口/host 解析优先级（见 SKILL.md 7.1）：命令行参数 > COMFYUI_PORT/COMFYUI_HOST 环境变量 > 默认值。
# 默认值跟随 ComfyUI 官方约定（8188）。3198 是历史单一部署环境的端口，非通用标准；
# 需沿用请显式设置 COMFYUI_PORT=3198。
DEFAULT_HOST = os.environ.get("COMFYUI_HOST", "127.0.0.1")
DEFAULT_PORT = os.environ.get("COMFYUI_PORT", "8188")

SERVER = f"http://127.0.0.1:{DEFAULT_PORT}"

NODES_TO_CHECK = [
    "WanImageToVideoSVIPro",
    "KSamplerAdvanced",
    "ImageBatchExtendWithOverlap",
    "ImageResizeKJv2",
    "PathchSageAttentionKJ",
    "ModelPatchTorchSettings",
    "LoraLoaderModelOnly",
    "UNETLoader",
    "CLIPLoader",
    "VAELoader",
    "VAEEncode",
    "VAEDecode",
    "CLIPTextEncode",
    "LoadImage",
    "VHS_VideoCombine",
    "INTConstant",
]

def main():
    for node_type in NODES_TO_CHECK:
        try:
            url = f"{SERVER}/object_info/{node_type}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            info = data.get(node_type, {})
            inputs = info.get("input", {})
            required = inputs.get("required", {})
            optional = inputs.get("optional", {})
            print(f"\n=== {node_type} ===")
            print(f"  required: {list(required.keys())}")
            if optional:
                print(f"  optional: {list(optional.keys())}")
            # 打印关键参数类型
            for k, v in required.items():
                if isinstance(v, list) and len(v) > 0:
                    if isinstance(v[0], list):
                        print(f"    {k}: COMBO options={v[0][:5]}{'...' if len(v[0])>5 else ''}")
                    else:
                        print(f"    {k}: type={v[0]}")
        except Exception as e:
            print(f"[ERROR] {node_type}: {e}")

if __name__ == "__main__":
    main()
