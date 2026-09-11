import SwiftUI

struct PlayersScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var selectedPlayer: String?

    private struct PlayerSelection: Identifiable {
        let name: String
        var id: String { name }
    }

    var body: some View {
        HSPage {
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 250), spacing: 16)], spacing: 16) {
                    teamTotalCard()
                    ForEach(summaries) { summary in
                        playerCard(summary)
                    }
                }
                .padding()
            }
            .scrollContentBackground(.hidden)
            .navigationTitle("Players")
        }
        .sheet(item: playerSelection) { selection in
            PlayerDetailScreen(playerName: selection.name)
        }
    }

    private var summaries: [PlayerSummary] {
        PlayerStatsComputer.summaries(for: appModel.games)
    }

    private var teamTotal: PlayerSummary {
        PlayerStatsComputer.teamSummary(from: appModel.games)
    }

    private var playerSelection: Binding<PlayerSelection?> {
        Binding(
            get: { selectedPlayer.map(PlayerSelection.init) },
            set: { selectedPlayer = $0?.name }
        )
    }

    private func teamTotalCard() -> some View {
        Button {
            selectedPlayer = "__team_total__"
        } label: {
            HSPlayerCard(summary: teamTotal)
        }
        .buttonStyle(.plain)
    }

    private func playerCard(_ summary: PlayerSummary) -> some View {
        Button {
            selectedPlayer = summary.playerName
        } label: {
            HSPlayerCard(summary: summary)
        }
        .buttonStyle(.plain)
    }
}

struct HSPlayerCard: View {
    let summary: PlayerSummary

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(LinearGradient(colors: [HSToken.accent, HSToken.cool], startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: 56, height: 56)
                    Text(initials)
                        .font(.bebas(size: 20))
                        .foregroundStyle(HSToken.surface)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(summary.playerName)
                        .font(.outfit(size: 15, weight: .bold))
                        .foregroundStyle(HSToken.ink)
                        .lineLimit(1)
                    Text("\(summary.gamesPlayed) Games • \(summary.mpg.formatted(.number.precision(.fractionLength(1)))) MPG")
                        .font(.outfit(size: 12))
                        .foregroundStyle(HSToken.inkMuted)
                }
                Spacer()
            }
            .padding(14)

            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 4), spacing: 6) {
                statCell("PPG", summary.ppg, .ppgColor)
                statCell("RPG", summary.rpg, HSToken.ink)
                statCell("APG", summary.apg, HSToken.ink)
                statCell("EFF", summary.eff, HSToken.ink)
                statCell("ORtg", summary.ortg, summary.ortg > 110 ? .statGood : (summary.ortg < 90 ? .statPoor : HSToken.ink))
                statCell("PPP", summary.ppp, summary.ppp > 1.1 ? .statGood : (summary.ppp < 0.8 ? .statPoor : HSToken.ink))
                statCell("TS%", summary.tsPct, .statGood)
                statCell("Poss/40", summary.possPer40, HSToken.ink)
            }
            .padding(.horizontal, 14)
            .padding(.bottom, 14)
        }
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.08), radius: 8, y: 2)
    }

    private var initials: String {
        guard summary.playerName.count > 1 else { return "TT" }
        let parts = summary.playerName.split(separator: " ")
        if parts.count >= 2 {
            return "\(parts[0].prefix(1))\(parts[1].prefix(1))".uppercased()
        }
        return String(summary.playerName.prefix(2)).uppercased()
    }

    private func statCell(_ label: String, _ value: Double, _ color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value.formatted(.number.precision(.fractionLength(1))))
                .font(.bebas(size: 18))
                .foregroundStyle(color)
            Text(label)
                .font(.outfit(size: 9, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(HSToken.bgElevated.opacity(0.5), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
    }
}

extension String: @retroactive Identifiable {
    public var id: String { self }
}

private extension Color {
    static let statGood = Color(hex: 0x2F855A)
    static let statPoor = Color(hex: 0xC53030)
    static let ppgColor = Color(hex: 0x667EEA)
}
