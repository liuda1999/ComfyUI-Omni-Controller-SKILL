"""
查询 SVI Pro 工作流所需关键节点的 object_info，确认参数格式。
"""
import json
import urllib.request

SERVER = "http://127.0.0.1:3198"

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
