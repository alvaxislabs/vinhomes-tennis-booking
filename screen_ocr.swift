import Foundation
import Vision
import ImageIO

struct TextBox: Encodable {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
request.recognitionLanguages = ["vi-VN", "en-US"]

func recognize(_ path: String) throws -> Data {
    guard let imageData = try? Data(contentsOf: URL(fileURLWithPath: path)),
          let source = CGImageSourceCreateWithData(imageData as CFData, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "ScreenReader", code: 2)
    }

    try VNImageRequestHandler(cgImage: image).perform([request])
    var boxes = (request.results ?? []).flatMap { observation -> [TextBox] in
        guard let candidate = observation.topCandidates(1).first else { return [] }
        let text = candidate.string
        let box = observation.boundingBox
        var result = [TextBox(text: text, x: box.minX, y: box.minY, width: box.width, height: box.height)]
        // Vision sometimes merges adjacent buttons into one line. Locate the
        // actual substring, rather than tapping the centre of the entire line.
        let pattern = #"Sân Tennis|Tiện ích|Tiếp tục|\d{2}:\d{2}\s*-\s*\d{2}:\d{2}"#
        let regex = try! NSRegularExpression(pattern: pattern, options: [.caseInsensitive])
        for match in regex.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            guard let range = Range(match.range, in: text), String(text[range]) != text,
                  let rect = try? candidate.boundingBox(for: range) else { continue }
            let b = rect.boundingBox
            result.append(TextBox(text: String(text[range]), x: b.minX, y: b.minY, width: b.width, height: b.height))
        }
        return result
    }
    // Locate the terms checkbox relative to its visible text. Sample its
    // orange fill so the runner can verify acceptance before submitting.
    if let terms = boxes.first(where: { $0.text.hasPrefix("Tôi đã hiểu") }) {
        let cx = terms.x - 0.05
        let cy = terms.y + terms.height / 2
        let w = image.width, h = image.height
        var pixels = [UInt8](repeating: 0, count: w * h * 4)
        let rendered = pixels.withUnsafeMutableBytes { raw -> Bool in
            guard let ctx = CGContext(data: raw.baseAddress, width: w, height: h,
                bitsPerComponent: 8, bytesPerRow: w * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return false }
            ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
            return true
        }
        if rendered && cx > 0.03 {
            var orange = 0, count = 0
            for dy in -8...8 {
                for dx in -12...12 {
                    let x = min(w-1, max(0, Int(cx * Double(w)) + dx))
                    let y = min(h-1, max(0, Int((1-cy) * Double(h)) + dy))
                    let i = (y*w+x)*4
                    if pixels[i] > 220 && pixels[i+1] > 50 && pixels[i+1] < 180 && pixels[i+2] < 100 {
                        orange += 1
                    }
                    count += 1
                }
            }
            boxes.append(TextBox(text: orange * 3 > count ? "__terms_checked__" : "__terms_unchecked__",
                x: cx-0.02, y: cy-0.01, width: 0.04, height: 0.02))
        }
    }
    return try JSONEncoder().encode(boxes)
}

// Keep Vision loaded between screenshots. Each line is a local image path;
// responses contain boxes or a generic error, never the path or input data.
if CommandLine.arguments.dropFirst().first == "--server" {
    FileHandle.standardOutput.write(Data("READY\n".utf8))
    while let path = readLine() {
        autoreleasepool {
            do {
                let output = try recognize(path)
                FileHandle.standardOutput.write(output + Data([10]))
            } catch {
                FileHandle.standardOutput.write(Data("{\"error\":\"Screen recognition failed\"}\n".utf8))
            }
        }
    }
} else {
    do {
        guard CommandLine.arguments.count == 2 else {
            throw NSError(domain: "ScreenReader", code: 1)
        }
        let output = try recognize(CommandLine.arguments[1])
        FileHandle.standardOutput.write(output + Data([10]))
    } catch {
        fputs("Screen recognition failed\n", stderr)
        exit(3)
    }
}
