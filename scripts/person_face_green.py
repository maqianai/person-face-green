#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
person_face_green.py — 对视频中人物肩膀以上的头颈区域打绿幕，生成新 mp4 到同目录。

用途：换头 / 后期抠像。只覆盖人物头部区域，肩膀以下与无人空镜保持原样。

依赖：
  - ffmpeg（自动查找 PATH / imageio-ffmpeg / 常见路径）
  - Pillow（pip install pillow）
  - macOS 自带 Swift + Vision 框架（人脸检测，仅 macOS 需要；无则可用 --no-detect + anchors.json）

典型用法：
  python3 person_face_green.py 输入.mp4                    # 默认静音（去音轨）
  python3 person_face_green.py 输入.mp4 4 13 --color 0,255,0 -o 输出.mp4
  python3 person_face_green.py 输入.mp4 --keep-audio       # 仅此情形保留原音频
  python3 person_face_green.py 输入.mp4 --no-detect --anchors anchors.json

原理：逐帧检测人脸框 -> 由人脸框推导覆盖头发+脸+脖子的椭圆区域（下沿停在肩线）
      -> 画纯绿色 -> 帧序列编码回视频。音频默认静音（-an）；仅 --keep-audio 时合入原音频。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("错误：需要 Pillow。请 pip install pillow", file=sys.stderr)
    sys.exit(2)

HERE = os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            return p
    except Exception:
        pass
    for c in [
        os.path.expanduser("~/Library/Python/3.9/lib/python/site-packages/"
                           "imageio_ffmpeg/binaries/ffmpeg-macos-aarch64-v7.1"),
        "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg",
    ]:
        if os.path.exists(c):
            return c
    return None


def find_vision_binary():
    """优先用已编译的 detect_faces，否则现场 swiftc 编译。"""
    exe = os.path.join(HERE, "detect_faces")
    swift = os.path.join(HERE, "detect_faces.swift")
    if os.path.exists(exe) and os.access(exe, os.X_OK):
        return exe
    if os.path.exists(swift) and shutil.which("swiftc"):
        print("现场编译 detect_faces.swift ...")
        ret = subprocess.run(["swiftc", "-O", swift, "-o", exe]).returncode
        if ret == 0:
            return exe
    return None


def parse_time(s):
    s = str(s).strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        raise ValueError(f"无法解析时间: {s}")
    return float(s)


def probe_duration(ffmpeg, path):
    out = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True).stdout
    for line in out.splitlines():
        if "Duration:" in line:
            try:
                t = line.split("Duration:")[1].split(",")[0].strip()
                hh, mm, ss = t.split(":")
                return int(hh) * 3600 + int(mm) * 60 + float(ss)
            except Exception:
                pass
    return None


def load_anchors(path):
    """加载手动锚点 JSON: { "f_0084.jpg": [x,y,w,h], ... }"""
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def face_to_green_box(face, pad_x=0.50, pad_top=0.85, pad_bottom=0.30):
    """由人脸框推导绿幕区域（覆盖头发+脸+脖，下沿到肩线）。"""
    x, y, w, h = face["x"], face["y"], face["w"], face["h"]
    return (
        x - pad_x * w,
        y - pad_top * h,
        x + w + pad_x * w,
        y + h + pad_bottom * h,
    )


def main():
    ap = argparse.ArgumentParser(description="视频人物肩膀以上打绿幕，输出新 mp4 到同目录。")
    ap.add_argument("input", help="源视频路径")
    ap.add_argument("start", nargs="?", help="开始时间（秒或 HH:MM:SS），可选")
    ap.add_argument("end", nargs="?", help="结束时间，可选")
    ap.add_argument("-o", "--output", help="输出路径（默认同目录 <stem>_green.mp4）")
    ap.add_argument("--color", default="0,255,0", help="绿幕颜色 R,G,B（默认 0,255,0）")
    ap.add_argument("--pad-x", type=float, default=0.50, help="左右扩展系数（默认 0.50）")
    ap.add_argument("--pad-top", type=float, default=0.85, help="向上扩展系数（默认 0.85）")
    ap.add_argument("--pad-bottom", type=float, default=0.30, help="向下扩展系数（默认 0.30）")
    ap.add_argument("--crf", type=int, default=18, help="编码质量 CRF（默认 18）")
    ap.add_argument("--fps", type=float, default=30, help="导出帧率（默认 30）")
    ap.add_argument("--no-detect", action="store_true", help="跳过人脸检测，仅用 anchors.json")
    ap.add_argument("--anchors", help="手动锚点 JSON 文件（帧名->[x,y,w,h]）")
    ap.add_argument("--keep-frames", action="store_true", help="保留中间帧目录（调试用）")
    ap.add_argument("--keep-audio", action="store_true",
                    help="保留原视频音频（默认静音去音轨；仅用户明确要求不静音时才加此参数）")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("错误：未找到 ffmpeg。", file=sys.stderr)
        sys.exit(2)

    src = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.exists(src):
        print(f"错误：源文件不存在: {src}", file=sys.stderr)
        sys.exit(2)

    # 截取区间
    ss_args = []
    if args.start is not None:
        start = parse_time(args.start)
        end = parse_time(args.end) if args.end is not None else None
        if end is None or end <= start:
            print("错误：需提供有效的结束时间（> 开始时间）。", file=sys.stderr)
            sys.exit(2)
        ss_args = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"]

    rgb = tuple(int(v) for v in args.color.split(","))
    if len(rgb) != 3 or any(v < 0 or v > 255 for v in rgb):
        print("错误：--color 格式应为 R,G,B（每通道 0-255）。", file=sys.stderr)
        sys.exit(2)

    out = os.path.abspath(os.path.expanduser(
        args.output or os.path.splitext(src)[0] + "_green.mp4"))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    tmp = tempfile.mkdtemp(prefix="pfg_")
    frames = os.path.join(tmp, "frames")
    painted = os.path.join(tmp, "painted")
    os.makedirs(frames)
    os.makedirs(painted)
    try:
        dur = probe_duration(ffmpeg, src)
        print(f"源视频: {src}" + (f" ({dur:.2f}s)" if dur else ""))
        print("导出帧 ...")
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        cmd += ss_args
        cmd += ["-i", src, "-vf", f"fps={args.fps}", "-q:v", "2",
                os.path.join(frames, "f_%04d.jpg")]
        ret = subprocess.run(cmd).returncode
        if ret != 0:
            print(f"错误：导出帧失败 ({ret})", file=sys.stderr)
            sys.exit(ret)

        names = sorted(n for n in os.listdir(frames) if n.endswith(".jpg"))
        if not names:
            print("错误：没有导出任何帧。", file=sys.stderr)
            sys.exit(3)
        print(f"共 {len(names)} 帧。")

        # 人脸检测
        faces = {}
        if not args.no_detect:
            exe = find_vision_binary()
            if exe:
                faces_json = os.path.join(tmp, "faces.json")
                subprocess.run([exe, frames, faces_json])
                if os.path.exists(faces_json):
                    with open(faces_json) as f:
                        faces = json.load(f)
                print(f"检测到有脸帧: {sum(1 for n in names if faces.get(n))}")
            else:
                print("警告：无 Vision 检测能力，仅使用手动锚点。", file=sys.stderr)

        anchors = load_anchors(args.anchors)
        hit = 0
        for name in names:
            im = Image.open(os.path.join(frames, name)).convert("RGB")
            face = None
            fl = faces.get(name, [])
            if fl:
                face = max(fl, key=lambda f: f["conf"] * f["w"] * f["h"])
            if face is None and name in anchors:
                a = anchors[name]
                face = {"x": a[0], "y": a[1], "w": a[2], "h": a[3], "conf": 1.0}
            if face:
                L, T, R, B = face_to_green_box(face, args.pad_x, args.pad_top, args.pad_bottom)
                W, H = im.size
                L, R = max(0, L), min(W, R)
                T, B = max(0, T), min(H, B)
                ImageDraw.Draw(im).ellipse((L, T, R, B), fill=rgb)
                hit += 1
            im.save(os.path.join(painted, name))

        print(f"已打绿幕帧: {hit}/{len(names)}")
        print(f"音频: {'保留原音频' if args.keep_audio else '静音（去音轨）'}")
        print("编码 ...")
        # 用 filter 修正 JPEG 序列的 full-range -> limited，避免 yuvj420p 色偏
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
               "-framerate", str(args.fps), "-i", os.path.join(painted, "f_%04d.jpg")]
        if args.keep_audio:
            # 合入原音频：所有 -i 必须排在 -map/-filter_complex 等输出选项之前
            # （若有截取区间需对源视频同步 -ss/-to 偏移）
            cmd += ss_args + ["-i", src]
        cmd += ["-filter_complex", "[0:v]scale=in_range=full:out_range=limited,format=yuv420p[v]",
                "-map", "[v]"]
        if args.keep_audio:
            cmd += ["-map", "1:a:0?", "-c:a", "aac", "-b:a", "128k", "-shortest"]
        else:
            # 默认静音：只输出视频流，不产生音轨
            cmd += ["-an"]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
        ret = subprocess.run(cmd).returncode
        if ret != 0:
            print(f"错误：编码失败 ({ret})", file=sys.stderr)
            sys.exit(ret)

        size = os.path.getsize(out) / 1024 / 1024
        audio_tag = "含原音频" if args.keep_audio else "静音无音轨"
        print(f"完成: {out} ({size:.2f} MB, {audio_tag})")
    finally:
        if args.keep_frames:
            print(f"调试帧保留在: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
