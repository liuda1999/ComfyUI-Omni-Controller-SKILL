import json
with open('e:/comfyui-cli/comfyui-controller/assets/wan22_svi_pro_long_video.json', 'r', encoding='utf-8') as f:
    wf = json.load(f)

print(f"顶层keys: {list(wf.keys())[:10]}")
print(f"类型: nodes={type(wf.get('nodes'))}")

# UI格式，nodes是列表
nodes = wf.get('nodes', [])
print(f"节点总数: {len(nodes)}")
print()

# 关键节点分析
for node in nodes:
    ct = node.get('type', '')
    nid = node.get('id', '')
    if ct in ['UNETLoader', 'ModelPatchTorchSettings', 'PathchSageAttentionKJ']:
        print(f"节点{nid}: {ct}")
        wv = node.get('widgets_values', [])
        if ct == 'UNETLoader':
            print(f"  widgets: {wv}")
        elif ct == 'ModelPatchTorchSettings':
            print(f"  widgets: {wv}")
        elif ct == 'PathchSageAttentionKJ':
            print(f"  widgets: {wv}")
        print()
