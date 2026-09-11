import SwiftUI
#if os(macOS)
import AppKit
#else
import UIKit
#endif

// MARK: - Hex color helper

extension Color {
    init(hex: UInt32, alpha: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: alpha
        )
    }

    /// Adaptive color: light scheme + dark scheme values.
    init(light: Color, dark: Color) {
        #if os(macOS)
        self.init(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return isDark ? NSColor(dark) : NSColor(light)
        })
        #else
        self.init(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? UIColor(dark) : UIColor(light)
        })
        #endif
    }

    init(light: UInt32, dark: UInt32, lightAlpha: Double = 1.0, darkAlpha: Double = 1.0) {
        self.init(light: Color(hex: light, alpha: lightAlpha), dark: Color(hex: dark, alpha: darkAlpha))
    }
}

// MARK: - Hoops Stats design tokens (mirrors web/static/css/style.css --hs-*)

enum HSToken {
    // Surfaces
    static let bgMain = Color(light: 0xF3EFE6, dark: 0x12161D)            // --hs-bg-main
    static let bgDeep = Color(light: 0xE8E2D6, dark: 0x0B0E12)             // --hs-bg-deep
    static let bgElevated = Color(light: 0xFFFFFF, dark: 0x1A2029)         // --hs-bg-elevated
    static let surface = Color(light: 0xFFFFFF, dark: 0xF3EFE6)            // --hs-surface (cream)
    static let surface2 = Color(light: 0xE8E2D6, dark: 0xE8E2D6)           // --hs-surface-2

    // Text
    static let ink = Color(light: 0x1A1714, dark: 0xF3EFE6)                // --hs-ink
    static let inkMuted = Color(light: 0x4F4A43, dark: 0xB8B0A1)           // --hs-ink-muted

    // Lines
    static let line = Color(light: 0x1A1714, dark: 0xFFF8EB, lightAlpha: 0.12, darkAlpha: 0.08)   // --hs-line
    static let lineStrong = Color(light: 0x1A1714, dark: 0xFFF8EB, lightAlpha: 0.20, darkAlpha: 0.14) // --hs-line-strong

    // Brand accents
    static let accent = Color(hex: 0xFF4D00)                               // --hs-accent
    static let accentDim = Color(hex: 0xFF7849)                            // --hs-accent-dim
    static let accentGradient = [Color(hex: 0xFF4D00), Color(hex: 0xFF8A5C)]
    static let accentGradientDeep = [Color(hex: 0xFF6A2E), Color(hex: 0xFF4D00)]
    static let cool = Color(hex: 0x2EC4B6)                                 // --hs-cool
    static let coolGradient = [Color(hex: 0x2EC4B6), Color(hex: 0x26A89C)]

    // Status
    static let win = Color(hex: 0x3D9A5C)                                  // --hs-win
    static let loss = Color(hex: 0xC94C5C)                                 // --hs-loss
    static let gold = Color(hex: 0xE8B86D)                                 // --hs-gold

    // Sidebar (always dark, mirrors web sidebar gradient)
    static let sidebarBackground = Color(hex: 0x0D1015)
    static let sidebarGradient = [Color(hex: 0x151A22), Color(hex: 0x0D1015)]

    // Metrics
    static let radius: CGFloat = 14
    static let radiusSmall: CGFloat = 10
    static let shadow = Color.black.opacity(0.35)

    // Page glow layers (style.css:103-105)
    static func pageBackground(colorScheme: ColorScheme) -> some View {
        ZStack {
            if colorScheme == .dark {
                RadialGradient(colors: [Color(hex: 0xFF4D00).opacity(0.09), .clear], center: .topTrailing, startRadius: 0, endRadius: 700)
                RadialGradient(colors: [Color(hex: 0x2EC4B6).opacity(0.06), .clear], center: .bottomLeading, startRadius: 0, endRadius: 700)
            } else {
                RadialGradient(colors: [Color(hex: 0xFF4D00).opacity(0.06), .clear], center: .topTrailing, startRadius: 0, endRadius: 700)
                RadialGradient(colors: [Color(hex: 0x2EC4B6).opacity(0.05), .clear], center: .bottomLeading, startRadius: 0, endRadius: 700)
            }
        }
        .ignoresSafeArea()
    }
}

// MARK: - Fonts (bundled: BebasNeue-Regular.ttf, Outfit-Variable.ttf)

extension Font {
    static func bebas(size: CGFloat) -> Font {
        .custom("BebasNeue-Regular", size: size)
    }

    static func outfit(size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .custom("Outfit", size: size).weight(weight)
    }
}

// MARK: - Icon mapping (web Font Awesome → SF Symbols)

enum HSIcon {
    static let brand = "basketball.fill"              // fa-basketball-ball
    static let dashboard = "square.grid.2x2.fill"     // fa-th-large
    static let games = "calendar"                     // fa-calendar
    static let liveGame = "dot.radiowaves.left.and.right" // fa-tower-broadcast
    static let players = "person.3.fill"              // fa-users
    static let lineups = "person.2.fill"              // fa-people-group
    static let analytics = "chart.bar.fill"           // fa-chart-column
    static let advanced = "chart.line.uptrend.xyaxis" // fa-chart-line
    static let plays = "list.clipboard.fill"          // fa-clipboard-list
    static let glossary = "book.fill"                 // fa-book
    static let gm = "building.2.fill"                 // fa-building
    static let admin = "gearshape.2.fill"             // fa-user-gear
    static let upload = "icloud.and.arrow.up.fill"    // fa-cloud-arrow-up
    static let signOut = "arrow.right.from.bracket"   // fa-arrow-right-from-bracket
    static let report = "doc.richtext.fill"           // fa-file-lines
}
