import Foundation
import Vision
import AppKit

// 对目录内所有 jpg 逐帧检测人脸，输出像素坐标（左上角原点）JSON。
// 用法: detect_faces <frames_dir> <out.json>

let args = CommandLine.arguments
guard args.count >= 3 else {
    fputs("usage: detect_faces <dir> <out.json>\n", stderr)
    exit(2)
}
let dir = args[1]
let outPath = args[2]
let fm = FileManager.default
let files = (try? fm.contentsOfDirectory(atPath: dir))?
    .filter { $0.hasSuffix(".jpg") || $0.hasSuffix(".png") }
    .sorted() ?? []

var result: [String: Any] = [:]

for name in files {
    let path = (dir as NSString).appendingPathComponent(name)
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let W = Double(cg.width)
    let H = Double(cg.height)
    let req = VNDetectFaceRectanglesRequest()
    req.revision = VNDetectFaceRectanglesRequestRevision3
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    do { try handler.perform([req]) } catch { continue }
    var faces: [[String: Any]] = []
    if let obs = req.results as? [VNFaceObservation]? {
        for o in obs ?? [] {
            let b = o.boundingBox
            // Vision 归一化坐标原点在左下；转换为左上角原点的像素坐标
            let x = b.origin.x * W
            let yTop = (1.0 - b.origin.y - b.height) * H
            let w = b.width * W
            let h = b.height * H
            faces.append([
                "x": x, "y": yTop, "w": w, "h": h,
                "conf": o.confidence
            ])
        }
    }
    result[name] = faces
}

let data = try! JSONSerialization.data(withJSONObject: result, options: [])
try! data.write(to: URL(fileURLWithPath: outPath))
print("detected \(files.count) frames -> \(outPath)")
