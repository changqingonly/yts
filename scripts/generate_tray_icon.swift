import AppKit
import Foundation

guard CommandLine.arguments.count == 2 else {
    fatalError("usage: swift scripts/generate_tray_icon.swift OUTPUT.png")
}

let size = 36
guard let bitmap = NSBitmapImageRep(
    bitmapDataPlanes: nil,
    pixelsWide: size,
    pixelsHigh: size,
    bitsPerSample: 8,
    samplesPerPixel: 4,
    hasAlpha: true,
    isPlanar: false,
    colorSpaceName: .deviceRGB,
    bytesPerRow: 0,
    bitsPerPixel: 0
) else {
    fatalError("failed to create tray icon bitmap")
}

guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
    fatalError("failed to create tray icon graphics context")
}

NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
NSColor.clear.setFill()
NSRect(x: 0, y: 0, width: size, height: size).fill()

func drawSpark(points: [NSPoint], lineWidth: CGFloat) {
    let path = NSBezierPath()
    path.move(to: points[0])
    for point in points.dropFirst() {
        path.line(to: point)
    }
    path.close()
    path.lineWidth = lineWidth
    path.lineJoinStyle = .round
    NSColor.black.setStroke()
    path.stroke()
}

drawSpark(
    points: [
        NSPoint(x: 20, y: 33), NSPoint(x: 22.5, y: 24.3),
        NSPoint(x: 31, y: 21.7), NSPoint(x: 22.5, y: 19.2),
        NSPoint(x: 20, y: 10.5), NSPoint(x: 17.5, y: 19.2),
        NSPoint(x: 9, y: 21.7), NSPoint(x: 17.5, y: 24.3),
    ],
    lineWidth: 2.8
)
drawSpark(
    points: [
        NSPoint(x: 9, y: 14.5), NSPoint(x: 10.4, y: 9.8),
        NSPoint(x: 15, y: 8.5), NSPoint(x: 10.4, y: 7.1),
        NSPoint(x: 9, y: 2.5), NSPoint(x: 7.6, y: 7.1),
        NSPoint(x: 3, y: 8.5), NSPoint(x: 7.6, y: 9.8),
    ],
    lineWidth: 2.2
)

context.flushGraphics()
NSGraphicsContext.restoreGraphicsState()

guard let png = bitmap.representation(using: .png, properties: [:]) else {
    fatalError("failed to encode tray icon PNG")
}

do {
    try png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]), options: .atomic)
} catch {
    fatalError("failed to write tray icon PNG: \(error)")
}
