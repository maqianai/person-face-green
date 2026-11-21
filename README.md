# person-face-green

对视频中**人物肩膀以上的头颈区域自动打纯绿幕**，输出同目录的新 mp4，供换头 / 后期色键抠像使用。只覆盖人物镜头，肩膀以下与无人空镜保持原样。

内置于 WorkBuddy 的标准 Skill，也可作为独立命令行工具使用。

## 效果示意

| 原片 | 打绿幕后 |
|------|----------|
| 人物头部清晰可见 | 头发+脸+脖子被纯绿 `(0,255,0)` 覆盖，肩膀与背景不变 |
| 蝴蝶/水晶等空镜 | 完全不动，不出现绿色 |

## 特性

- 自动检测人脸（macOS Vision 框架，离线、无需联网、无需第三方模型）
- 由人脸框推导覆盖「头发+脸+脖」的椭圆，下沿停在肩线
- 人物忽远忽近时绿幕随脸框自动缩放
- 背影 / 侧脸 / 运动模糊等检测不到脸的镜头，可用 `anchors.json` 手动补位
- 保留原视频音频；修正 JPEG 帧序列色彩，避免 yuvj420p 色偏
- 可指定时间段、自定义绿幕颜色、调整覆盖区域

## 目录结构

```
person-face-green/
├── SKILL.md                        # WorkBuddy Skill 定义（触发词 + 工作流）
├── README.md                       # 本文件
├── references/
│   └── usage.md                    # 详细参数、排错、锚点标定方法
└── scripts/
    ├── person_face_green.py        # 主入口（自包含整条流水线）
    ├── detect_faces.swift          # macOS Vision 人脸检测源码
    ├── detect_faces                # 已编译二进制（macOS arm64，可现场重编）
    └── anchors.example.json        # 手动锚点格式示例
```

## 一、作为 WorkBuddy Skill 接入

把本仓库放到 WorkBuddy 的用户级 skills 目录（开箱即用）：

```bash
git clone https://github.com/maqianai/person-face-green.git \
  ~/.workbuddy/skills/person-face-green
```

重启 / 刷新 WorkBuddy 后，用自然语言即可触发：

> 「给 `/path/video.mp4` 的人物肩膀上方打绿幕，准备换头」
> 「把这段视频 4~13s 的人物头部做成绿幕」

WorkBuddy 会加载 `SKILL.md`，调用脚本并按工作流自验证。

项目级共享：把仓库放到 `<项目>/.workbuddy/skills/person-face-green` 即可。

## 二、作为命令行工具使用

### 依赖

- **macOS**（人脸检测依赖系统 Swift + Vision 框架）
- Python 3 + Pillow：`pip install pillow`
- ffmpeg：自动查找 `PATH` / `imageio-ffmpeg` / 常见路径

### 基本用法

```bash
PY=python3
S=scripts/person_face_green.py

# 整段视频
$PY "$S" input.mp4

# 指定 4~13s，默认绿幕色
$PY "$S" input.mp4 4 13

# 指定输出与颜色（洋红键）
$PY "$S" input.mp4 4 13 --color 255,0,255 -o out_green.mp4

# 检测不到的镜头用手动锚点补齐
$PY "$S" input.mp4 --anchors anchors.json
```

### 参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `input` | 必填 | 源视频 |
| `start` / `end` | 整段 | 可选时间段 |
| `-o/--output` | `<stem>_green.mp4` | 输出路径（同目录） |
| `--color R,G,B` | `0,255,0` | 绿幕颜色 |
| `--pad-x` | `0.50` | 左右扩展系数 |
| `--pad-top` | `0.85` | 向上扩展系数 |
| `--pad-bottom` | `0.30` | 向下扩展系数 |
| `--crf` | `18` | 编码质量 |
| `--fps` | `30` | 导出帧率 |
| `--no-detect` | 关 | 跳过人脸检测，仅用 anchors |
| `--anchors` | 无 | 手动锚点 JSON |
| `--keep-frames` | 关 | 保留中间帧调试 |

更多细节见 [`references/usage.md`](references/usage.md)。

## 三、工作原理

```
输入视频
  → ffmpeg 按区间导出帧
  → Vision 逐帧检测人脸框（左上角像素坐标）
  → 合并 anchors.json（补检不到的帧）
  → 由人脸框推导椭圆：[x±0.5w, y-0.85h, y+h+0.3h]
  → Pillow 画纯绿
  → ffmpeg 帧序列编码（full→limited 修色）+ 合入原音频
  → 输出 mp4
```

## 四、自验证

已在一条 1298×720 / 30fps 的 9s 混剪视频（蝴蝶空镜 + 人物正面/背影镜头）上验证：

- 有脸帧 **174 / 270** 自动打绿，抽帧确认头部完整覆盖、肩膀以下保留；
- 空镜（0s、2.5s）无绿色；
- 输出规格 `9.00s / 1298x720 / 30fps / H.264 yuv420p / AAC 音频`，与源片段一致；
- 传入 anchors 后打绿帧增至 **181**，转场帧补齐。

复现：

```bash
python3 scripts/person_face_green.py your.mp4 4 13 -o verify.mp4
# 抽帧检查
ffmpeg -ss 3.5 -i verify.mp4 -frames:v 1 /tmp/chk.png
```

## 五、限制

- 绿幕是**椭圆几何覆盖**，不是发丝级语义分割。若换头对边缘精度要求极高，需另用分割模型重抠。
- 非 macOS 无 Vision 检测，需用 `--no-detect --anchors` 自行提供人脸框。
- `detect_faces` 二进制为 macOS arm64；Intel Mac 请用 `swiftc -O detect_faces.swift -o detect_faces` 重编。

## License

MIT
