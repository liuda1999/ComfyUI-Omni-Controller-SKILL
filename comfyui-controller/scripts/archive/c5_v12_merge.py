"""v12最终拼接脚本"""
import os
import subprocess
import sys

video_paths = [
    "E:/comfyui-cli/output/c5_v12_seg1_1784665984_00001.mp4",
    "E:/comfyui-cli/output/c5_v12_seg2_1784666214_00001.mp4",
    "E:/comfyui-cli/output/c5_v12_seg3_1784666434_00001.mp4",
]

# 验证文件存在
for vp in video_paths:
    if not os.path.exists(vp):
        print(f"错误: 文件不存在 {vp}")
        sys.exit(1)
    size = os.path.getsize(vp) / 1048576
    print(f"  {os.path.basename(vp)}: {size:.2f}MB")

# 使用concat filter (filter_complex方式, 不需要-safe选项)
print("\n使用concat filter拼接...")
merged_path = "E:/comfyui-cli/output/c5_v12_merged_final.mp4"

# 方法1: concat demuxer (不用-safe)
concat_file = "E:/comfyui-cli/temp/concat_v12_final.txt"
with open(concat_file, "w", encoding="utf-8") as f:
    for vp in video_paths:
        f.write(f"file '{vp}'\n")

# 尝试方法1: concat demuxer + copy
cmd1 = ["ffmpeg", "-y", "-f", "concat", "-i", concat_file, "-c", "copy", merged_path]
r1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=120)
if r1.returncode == 0 and os.path.exists(merged_path):
    size = os.path.getsize(merged_path) / 1048576
    print(f"\n拼接成功(copy模式)!")
    print(f"  输出: {merged_path} ({size:.2f}MB)")
    sys.exit(0)

# 方法2: concat filter (重新编码)
print("copy模式失败, 使用concat filter重新编码...")
inputs = []
for vp in video_paths:
    inputs.extend(["-i", vp])

cmd2 = ["ffmpeg", "-y"] + inputs + [
    "-filter_complex",
    "[0:v][1:v][2:v]concat=n=3:v=1:a=0[outv]",
    "-map", "[outv]",
    "-c:v", "libx264",
    "-crf", "14",
    "-pix_fmt", "yuv420p10le",
    "-r", "24",
    merged_path
]
r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
if r2.returncode == 0 and os.path.exists(merged_path):
    size = os.path.getsize(merged_path) / 1048576
    print(f"\n拼接成功(重新编码)!")
    print(f"  输出: {merged_path} ({size:.2f}MB)")
else:
    print(f"拼接失败: {r2.stderr[-500:]}")
    sys.exit(1)
