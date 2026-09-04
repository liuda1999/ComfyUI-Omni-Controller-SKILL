"""v13最终拼接: 段1(v12) + 段2(v13) + 段3(v13)"""
import os
import subprocess
import sys

video_paths = [
    "E:/comfyui-cli/output/c5_v12_seg1_1784665984_00001.mp4",  # 段1(v12, 已验证正确)
    "E:/comfyui-cli/output/c5_v13_seg2_1784666955_00001.mp4",  # 段2(v13)
    "E:/comfyui-cli/output/c5_v13_seg3_1784667175_00001.mp4",  # 段3(v13)
]

for vp in video_paths:
    if not os.path.exists(vp):
        print(f"错误: {vp}")
        sys.exit(1)
    print(f"  {os.path.basename(vp)}: {os.path.getsize(vp)/1048576:.2f}MB")

merged_path = "E:/comfyui-cli/output/c5_v13_merged_final.mp4"
inputs = []
for vp in video_paths:
    inputs.extend(["-i", vp])

print("\nconcat filter拼接...")
cmd = ["ffmpeg", "-y"] + inputs + [
    "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]",
    "-map", "[outv]",
    "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p10le", "-r", "24",
    merged_path
]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
if r.returncode == 0 and os.path.exists(merged_path):
    size = os.path.getsize(merged_path) / 1048576
    print(f"\nv13拼接成功!")
    print(f"  输出: {merged_path} ({size:.2f}MB)")
else:
    print(f"失败: {r.stderr[-500:]}")
