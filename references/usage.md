# person-face-green 详细使用与排错

## 完整流水线

```
输入视频
  └─ ffmpeg 导出帧 (jpg, fps 可调, 支持 -ss/-to 截取区间)
       └─ Vision 逐帧检测人脸 -> faces.json (左上角像素坐标)
            └─ 合并手动 anchors.json (补检不到的帧)
                 └─ 由人脸框推导椭圆 (pad-x/top/bottom)
                      └─ Pillow 画纯绿
                           └─ ffmpeg 帧序列编码 + filter 修色 + 合原音频 -> 输出 mp4
```

## 人脸框到绿幕椭圆的推导

给定人脸框 `(x, y, w, h)`（左上角原点）：

```
left   = x - pad_x * w
right  = x + w + pad_x * w
top    = y - pad_top * h
bottom = y + h + pad_bottom * h
```

默认值 `pad_x=0.50, pad_top=0.85, pad_bottom=0.30`：
- 左右各扩半个脸宽，盖住两侧头发；
- 向上扩 0.85 个脸高，盖住头顶发丝；
- 向下扩 0.30 个脸高，盖住脖子但停在肩线附近。

镜头里人物变近/变远时脸框自动缩放，椭圆随之缩放。

## anchors.json 格式

```json
{
  "f_0084.jpg": [620, 95, 105, 105],
  "f_0087.jpg": [612, 75, 100, 100]
}
```

- key：帧文件名（导出帧按 `f_%04d.jpg` 命名）。
- value：`[x, y, w, h]`，左上角原点的像素坐标（人脸框，不是绿幕框）。
- 只在检测不到或检测不准的帧写；写了会覆盖检测结果。
- 无人空镜不要写项，就不会被打绿幕。

### 如何定位锚点坐标

用 Pillow 给帧打 100px 网格后读坐标：

```python
from PIL import Image, ImageDraw
im = Image.open("f_0084.jpg").convert("RGB")
d = ImageDraw.Draw(im)
for x in range(0, im.width, 100):
    d.line((x,0,x,im.height), fill=(255,0,0)); d.text((x+2,2), str(x), fill="yellow")
for y in range(0, im.height, 100):
    d.line((0,y,im.width,y), fill=(255,0,0)); d.text((2,y+2), str(y), fill="yellow")
im.save("grid_f_0084.png")
```

## 常见问题

**Q: 输出变成 yuvj420p / 播放有色偏？**
脚本已用 `scale=in_range=full:out_range=limited,format=yuv420p` 修正。若手动改脚本，务必保留这条 filter。

**Q: 没有音频？**
若源视频无音轨，`-map 1:a:0?` 中的 `?` 会跳过音频，不影响视频输出。

**Q: Vision 报 `conditional downcast` 警告？**
无害，可忽略（Swift 5.9+ 对可选数组 downcast 的提示）。

**Q: 编译 detect_faces 失败？**
确认 `xcode-select --install` 已装命令行工具，`swiftc --version` 可用。或直接用 `--no-detect --anchors`。

**Q: 绿幕盖住了肩膀/衣服？**
调小 `--pad-bottom`（如 0.15）。若头顶没盖全，调大 `--pad-top`（如 1.0）。

**Q: 非 macOS 能用吗？**
主脚本的画绿幕和编码部分是跨平台的；只有人脸检测依赖 macOS Vision。Linux/Windows 下用 `--no-detect --anchors`，自行提供每帧人脸框即可。

## 自验证清单

- [ ] 有脸帧头部被纯绿完整覆盖，无原发丝/脸露出
- [ ] 肩膀以下、背景、空镜无绿色
- [ ] 输出时长 = 指定区间时长（精确模式）
- [ ] 分辨率/帧率与源一致
- [ ] 音频保留且同步
