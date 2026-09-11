import SwiftUI

// MARK: - Card

struct HSCard<Content: View>: View {
    var tone: HSCardTone = .surface
    var padding: CGFloat = 20
    @ViewBuilder var content: Content

    enum HSCardTone {
        case surface        // cream/white card
        case elevated       // dark elevated card (live console, hero)
    }

    var body: some View {
        content
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                    .fill(cardFill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                    .stroke(HSToken.line, lineWidth: 1)
            )
    }

    private var cardFill: Color {
        switch tone {
        case .surface: HSToken.surface
        case .elevated: HSToken.bgElevated
        }
    }
}

// MARK: - Buttons

enum HSButtonStyle {
    case accent      // orange gradient (primary)
    case accentDeep  // deeper orange gradient
    case cool        // teal gradient (secondary)
    case plain       // neutral filled
}

struct HSButton: View {
    let title: String
    var icon: String?
    var style: HSButtonStyle = .accent
    var fullWidth: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if let icon {
                    Image(systemName: icon)
                        .font(.outfit(size: 13, weight: .bold))
                }
                Text(title)
                    .font(.outfit(size: 14, weight: .bold))
            }
            .foregroundStyle(foreground)
            .padding(.horizontal, 18)
            .padding(.vertical, 10)
            .frame(maxWidth: fullWidth ? .infinity : nil)
            .background(gradient, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private var gradient: LinearGradient {
        LinearGradient(colors: colors, startPoint: .topLeading, endPoint: .bottomTrailing)
    }

    private var colors: [Color] {
        switch style {
        case .accent: HSToken.accentGradient
        case .accentDeep: HSToken.accentGradientDeep
        case .cool: HSToken.coolGradient
        case .plain: [HSToken.bgElevated]
        }
    }

    private var foreground: Color {
        switch style {
        case .plain: HSToken.ink
        default: .white
        }
    }
}

// MARK: - Badges / pills

struct HSBadge: View {
    let text: String
    var color: HSBadgeColor = .neutral

    enum HSBadgeColor {
        case win, loss, gold, neutral, accent, cool

        var color: Color {
            switch self {
            case .win: HSToken.win
            case .loss: HSToken.loss
            case .gold: HSToken.gold
            case .accent: HSToken.accent
            case .cool: HSToken.cool
            case .neutral: HSToken.inkMuted
            }
        }
    }

    var body: some View {
        Text(text)
            .font(.outfit(size: 11, weight: .semibold))
            .foregroundStyle(color.color)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(color.color.opacity(0.14), in: Capsule())
    }
}

// MARK: - Section headers

struct HSSectionHeader: View {
    let title: String
    var icon: String?
    var trailing: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            if let icon {
                Image(systemName: icon)
                    .font(.outfit(size: 15, weight: .semibold))
                    .foregroundStyle(HSToken.accent)
            }
            Text(title)
                .font(.bebas(size: 22))
                .foregroundStyle(HSToken.ink)
            Spacer()
            if let trailing {
                Text(trailing)
                    .font(.outfit(size: 12, weight: .semibold))
                    .foregroundStyle(HSToken.inkMuted)
            }
        }
    }
}

// MARK: - Metric card (web metric cards, Bebas display value)

struct HSMetricCard: View {
    let title: String
    let value: String
    var tint: Color = HSToken.accent
    var minHeight: CGFloat = 100

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.outfit(size: 11, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
            Text(value)
                .font(.bebas(size: 34))
                .foregroundStyle(tint)
        }
        .frame(maxWidth: .infinity, minHeight: minHeight, alignment: .leading)
        .padding(18)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
    }
}

// MARK: - Page scaffold

struct HSPage<Content: View>: View {
    @Environment(\.colorScheme) private var colorScheme
    @ViewBuilder var content: Content

    var body: some View {
        ZStack {
            HSToken.pageBackground(colorScheme: colorScheme)
            content
        }
    }
}

// MARK: - Data row (key/value pair used across tables)

struct HSDataRow: View {
    let label: String
    let value: String
    var valueColor: Color = HSToken.ink

    var body: some View {
        HStack {
            Text(label)
                .font(.outfit(size: 13, weight: .regular))
                .foregroundStyle(HSToken.inkMuted)
            Spacer()
            Text(value)
                .font(.outfit(size: 13, weight: .semibold))
                .foregroundStyle(valueColor)
                .monospacedDigit()
        }
        .padding(.vertical, 6)
    }
}
