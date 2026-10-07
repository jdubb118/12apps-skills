// lift-video.swift — per-frame Apple Vision subject lift for a folder of frames (macOS 14+).
// Reads every <dir>/f_NNNNNN.png, writes <dir>/m_NNNNNN.png (L8 mask, white = subject). One request
// handler per frame. No model download, no network, no cost.
//   swiftc -O lift-video.swift -o lift-video && ./lift-video <frames-dir> [--person]
// Default = foreground instances (every salient object, merged). --person = people only
// (VNGeneratePersonSegmentationRequest, .accurate): use it when a car or a chair is in shot,
// because the default lifts those too.
// Every input frame gets a mask, empty frames included (all black), so frame counts always match.
import Foundation
import Vision
import CoreImage
import AppKit

let args = CommandLine.arguments
guard args.count >= 2 else { print("usage: lift-video <frames-dir> [--person]"); exit(2) }
let dir = args[1]
let personOnly = args.contains("--person")
let fm = FileManager.default
let files = (try? fm.contentsOfDirectory(atPath: dir))?.filter { $0.hasPrefix("f_") && $0.hasSuffix(".png") }.sorted() ?? []
guard !files.isEmpty else { print("no f_*.png in \(dir)"); exit(3) }
let ctx = CIContext()
let cs = CGColorSpaceCreateDeviceGray()
var done = 0, empty = 0, failed = 0

func writeBlack(_ extent: CGRect, _ url: URL) throws {
    let black = CIImage(color: CIColor(red: 0, green: 0, blue: 0)).cropped(to: extent)
    try ctx.writePNGRepresentation(of: black, to: url, format: .L8, colorSpace: cs)
}

for f in files {
    let inURL = URL(fileURLWithPath: dir).appendingPathComponent(f)
    let outURL = URL(fileURLWithPath: dir).appendingPathComponent(f.replacingOccurrences(of: "f_", with: "m_"))
    if fm.fileExists(atPath: outURL.path) { done += 1; continue }
    guard let ci = CIImage(contentsOf: inURL) else { print("cannot read \(f)"); failed += 1; continue }
    let handler = VNImageRequestHandler(ciImage: ci)
    do {
        if personOnly {
            let preq = VNGeneratePersonSegmentationRequest()
            preq.qualityLevel = .accurate
            preq.outputPixelFormat = kCVPixelFormatType_OneComponent8
            try handler.perform([preq])
            guard let pobs = preq.results?.first else { try writeBlack(ci.extent, outURL); empty += 1; continue }
            var m = CIImage(cvPixelBuffer: pobs.pixelBuffer)
            let sx = ci.extent.width / m.extent.width, sy = ci.extent.height / m.extent.height
            m = m.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
            try ctx.writePNGRepresentation(of: m, to: outURL, format: .L8, colorSpace: cs)
            done += 1
        } else {
            let req = VNGenerateForegroundInstanceMaskRequest()
            try handler.perform([req])
            guard let obs = req.results?.first, !obs.allInstances.isEmpty else { try writeBlack(ci.extent, outURL); empty += 1; continue }
            let buf = try obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler)
            try ctx.writePNGRepresentation(of: CIImage(cvPixelBuffer: buf), to: outURL, format: .L8, colorSpace: cs)
            done += 1
        }
    } catch {
        print("frame \(f): \(error)"); failed += 1
    }
}
print("\(failed == 0 ? "ok" : "FAILED") \(done) masks, \(empty) empty, \(failed) failed, of \(files.count) frames")
exit(failed == 0 ? 0 : 1)
