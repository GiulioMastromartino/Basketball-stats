import SwiftUI

struct ShotLocationPicker: View {
    let title: String
    let shotType: ShotType
    let onConfirm: (Double, Double) -> Void
    let onSkip: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var marker: CGPoint?

    var body: some View {
        VStack(spacing: 16) {
            Text(title)
                .font(.headline)
                .frame(maxWidth: .infinity, alignment: .leading)

            GeometryReader { geo in
                let w = geo.size.width
                let h = geo.size.height
                ZStack {
                    HalfCourtDrawing()
                    if let marker {
                        Circle()
                            .fill(Color(hex: 0xDC3545))
                            .stroke(.white, lineWidth: 3)
                            .frame(width: 16, height: 16)
                            .position(
                                x: w * marker.x / 500,
                                y: h * marker.y / 470
                            )
                    }
                }
                .contentShape(Rectangle())
                .gesture(
                    DragGesture(minimumDistance: 0)
                        .onEnded { value in
                            let x = max(0, min(500, value.location.x / w * 500))
                            let y = max(0, min(470, value.location.y / h * 470))
                            marker = CGPoint(x: x, y: y)
                        }
                )
            }
            .aspectRatio(500.0 / 470.0, contentMode: .fit)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            if let marker {
                HStack(spacing: 10) {
                    Text("(\(Int(marker.x)), \(Int(marker.y)))")
                        .font(.subheadline.monospacedDigit())
                    Text(inferShotZone(x: marker.x, y: marker.y, shotType: shotType).rawValue)
                        .font(.subheadline.weight(.bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.hsSecondarySystemBackground, in: Capsule())
                }
            } else {
                Text("Tap the court to mark the shot location")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                Button("Skip") {
                    dismiss()
                    onSkip()
                }
                .buttonStyle(.bordered)
                Button("Confirm Location") {
                    guard let marker else { return }
                    dismiss()
                    onConfirm(marker.x, marker.y)
                }
                .buttonStyle(.borderedProminent)
                .disabled(marker == nil)
            }
            .frame(maxWidth: .infinity)
        }
        .padding(20)
    }
}

private struct HalfCourtDrawing: View {
    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            let x: (CGFloat) -> CGFloat = { $0 * w / 500 }
            let y: (CGFloat) -> CGFloat = { $0 * h / 470 }

            ZStack {
                Color(hex: 0xF0E6D2)

                Path { path in
                    path.move(to: CGPoint(x: x(30), y: y(0)))
                    path.addLine(to: CGPoint(x: x(30), y: y(140)))
                    path.addArc(
                        center: CGPoint(x: x(250), y: y(140)),
                        radius: w * 220 / 500,
                        startAngle: .degrees(180),
                        endAngle: .degrees(0),
                        clockwise: false
                    )
                    path.addLine(to: CGPoint(x: x(470), y: y(0)))
                }
                .stroke(Color.black.opacity(0.75), lineWidth: 3)

                Path { path in
                    path.addRect(CGRect(x: x(170), y: y(0), width: w * 160 / 500, height: h * 190 / 470))
                }
                .stroke(Color.black.opacity(0.75), lineWidth: 3)

                Circle()
                    .stroke(Color.black.opacity(0.75), lineWidth: 3)
                    .frame(width: w * 120 / 500, height: w * 120 / 500)
                    .position(x: x(250), y: y(190))

                Path { path in
                    path.move(to: CGPoint(x: x(220), y: y(40)))
                    path.addLine(to: CGPoint(x: x(280), y: y(40)))
                }
                .stroke(Color.black.opacity(0.75), lineWidth: 3)

                Circle()
                    .stroke(Color(hex: 0xDC3545), lineWidth: 2)
                    .frame(width: 15, height: 15)
                    .position(x: x(250), y: y(55))

                Path { path in
                    path.move(to: CGPoint(x: 0, y: 0))
                    path.addLine(to: CGPoint(x: w, y: 0))
                }
                .stroke(Color.black.opacity(0.9), lineWidth: 5)
            }
        }
    }
}

private extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}
