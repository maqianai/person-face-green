---
name: person-face-green
description: 对视频中人物肩膀以上的头颈区域打纯绿幕并生成新的 mp4 文件到同目录，用于换头或后期抠像。当用户要求「给视频人物头部/脸上打绿幕」「肩膀上方打绿幕」「准备换头要绿底」「person face green screen」「给某段视频做绿幕抠像素材」时使用。支持指定视频、指定时间段、自定义绿幕颜色，只覆盖人物镜头、不影响无人空镜、不碰肩膀以下。
agent_created: true
---

# Person Face Green — 视频人物头部绿幕

## Overview

把视频里人物肩膀以上（头发+脸+脖子）的区域涂成纯绿色，输出同目录的新 mp4，供后期换头或色键抠像使用。肩膀以下画面、以及没有人物的空镜保持原样。

## When to use

- 用户说「给视频人物肩膀上方打绿幕」「头部打绿幕」「准备换头」「做绿幕素材」「green screen」。
- 输入是一个包含真人（正面或背影）的视频，需要把头部单独抠出来替换。

## 工作流程

### 1. 确认需求参数

向用户确认（能从上下文推断的就不问）：
- 源视频路径
- 时间段（默认整段）
- 绿幕颜色（默认纯绿 `0,255,0`）
- 输出文件名（默认 `<源文件名>_green.mp4`，同目录）

### 2. 运行主脚本

主脚本自包含：导出帧 → 人脸检测 → 画绿幕 → 编码合音频。

```bash
PY=/Users/fofo/.workbuddy/binaries/python/versions/3.13.12/bin/python3
S=~/.workbuddy/skills/person-face-green/scripts/person_face_green.py

# 整段视频
$PY "$S" /path/to/input.mp4

# 指定时间段 4~13s、自定义绿幕色、指定输出
$PY "$S" /path/to/input.mp4 4 13 --color 0,255,0 -o /path/to/out_green.mp4
```

脚本自动：
- 查找 ffmpeg（PATH / imageio-ffmpeg / 常见路径）；
- 首次运行现场用 `swiftc` 编译 `scripts/detect_faces.swift`（macOS Vision），后续复用；
- 用 `VNDetectFaceRectanglesRequest` 逐帧检测人脸框；
- 由人脸框推导覆盖「头发+脸+脖」的椭圆，下沿停在肩线附近（参数 `--pad-x/--pad-top/--pad-bottom` 可调）；
- 用 `scale=in_range=full:out_range=limited` 修正 JPEG 帧序列色彩，避免 yuvj420p 色偏；
- 保留原视频音频。

### 3. 人脸检测失效的镜头（背影 / 侧身 / 运动模糊）

Vision 对背影、侧脸或快速运动镜头可能检测不到人脸（表现为这些帧头部仍是原样）。处理办法：

1. 先用 `--keep-frames` 跑一遍，拿到中间帧目录；
2. 找出漏检帧，用带坐标网格的图确认头位；
3. 写一个 anchors JSON（`{"f_0084.jpg": [x, y, w, h], ...}`，坐标为左上角原点的像素），传入：
   ```bash
   $PY "$S" input.mp4 --anchors /path/to/anchors.json --keep-frames
   ```
   或用 `--no-detect` 完全依赖 anchors（无人空镜不写项即不打绿幕）。

### 4. 自验证（必做）

输出后抽几帧确认：

```bash
FF=<ffmpeg 路径>
for t in 0 3.5 6 8.9; do
  "$FF" -y -ss $t -i out_green.mp4 -frames:v 1 /tmp/chk_$t.png
done
```

- 有脸帧：头部应被纯绿完整覆盖，肩膀以下保留；
- 无人空镜：不应出现绿色；
- 时长、分辨率、帧率、音频与原片段一致。

## 参数速查

| 参数 | 默认 | 说明 |
|------|------|------|
| `input` | 必填 | 源视频 |
| `start` / `end` | 整段 | 可选时间段 |
| `-o/--output` | `<stem>_green.mp4` | 输出路径 |
| `--color R,G,B` | `0,255,0` | 绿幕颜色 |
| `--pad-x/--pad-top/--pad-bottom` | 0.5/0.85/0.30 | 绿幕区域扩展系数 |
| `--crf` | 18 | 编码质量 |
| `--fps` | 30 | 导出帧率 |
| `--no-detect` | 关 | 跳过人脸检测 |
| `--anchors` | 无 | 手动锚点 JSON |
| `--keep-frames` | 关 | 保留中间帧调试 |

## 依赖与限制

- **macOS**：依赖系统 Swift + Vision 框架做人脸检测（无第三方模型、无需联网）。
- **非 macOS**：用 `--no-detect --anchors` 手动提供头位，或用任意外部检测输出同格式 JSON。
- 绿幕是贴合头形的椭圆几何覆盖，不是发丝级语义分割；如需发丝级边缘，改用分割模型重抠。
- Python 需 Pillow（`pip install pillow`）。

## Resources

- `scripts/person_face_green.py`：主入口，自包含整条流水线。
- `scripts/detect_faces.swift`：macOS Vision 人脸检测，输出像素坐标 JSON。
- `references/usage.md`：完整参数与排错说明。
