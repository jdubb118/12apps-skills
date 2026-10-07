// lift.swift — Apple Vision "lift subject" (VNGenerateForegroundInstanceMaskRequest, macOS 14+): the same
// model behind "Copy Subject" in Photos.
// Writes a full-resolution grayscale MASK png (white = subject). Local, free, no model download.
//   swift lift.swift <in.jpg> <out-mask.png>
import Foundation
import Vision
import CoreImage
import AppKit

let args = CommandLine.arguments
guard args.count == 3 else { print("usage: lift <in> <out-mask.png>"); exit(2) }
let inURL = URL(fileURLWithPath: args[1]), outURL = URL(fileURLWithPath: args[2])
guard let ci = CIImage(contentsOf: inURL) else { print("cannot read \(args[1])"); exit(1) }
let handler = VNImageRequestHandler(ciImage: ci)
let req = VNGenerateForegroundInstanceMaskRequest()
try handler.perform([req])
guard let obs = req.results?.first, !obs.allInstances.isEmpty else { print("NO SUBJECT"); exit(3) }
let buf = try obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler)
let mask = CIImage(cvPixelBuffer: buf)
let ctx = CIContext()
let cs = CGColorSpaceCreateDeviceGray()
try ctx.writePNGRepresentation(of: mask, to: outURL, format: .L8, colorSpace: cs)
print("ok \(Int(mask.extent.width))x\(Int(mask.extent.height)) instances=\(obs.allInstances.count)")
