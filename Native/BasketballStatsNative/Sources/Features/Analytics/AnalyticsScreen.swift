import SwiftUI

struct AnalyticsScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var selectedPlayer = ""

    var body: some View {
        HSPage {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    AnalyticsOverviewSection(overview: appModel.teamOverview)
                    UsageSection(usages: appModel.usageSnapshots)
                    PlayerProgressionSection(
                        availablePlayers: Array(Set(appModel.games.flatMap(\.allPlayers))).sorted(),
                        selectedPlayer: $selectedPlayer,
                        progression: appModel.playerProgression(for: selectedPlayer)
                    )
                    LineupRankingsSection(rankings: appModel.lineupRankings)
                }
                .padding(24)
                .frame(maxWidth: 1100, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Analytics")
            .onAppear {
                if selectedPlayer.isEmpty {
                    selectedPlayer = Array(Set(appModel.games.flatMap(\.allPlayers))).sorted().first ?? ""
                }
            }
        }
    }
}

private struct AnalyticsOverviewSection: View {
    let overview: TeamOverview

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Team Overview", icon: "chart.bar.fill")
            HStack(spacing: 16) {
                HSMetricCard(title: "PPG", value: overview.pointsPerGame.formatted(.number.precision(.fractionLength(1))), tint: HSToken.accent)
                HSMetricCard(title: "PAPG", value: overview.pointsAllowedPerGame.formatted(.number.precision(.fractionLength(1))), tint: HSToken.loss)
                HSMetricCard(title: "Margin", value: overview.averageMargin.formatted(.number.precision(.fractionLength(1))), tint: HSToken.cool)
            }
        }
    }
}

private struct UsageSection: View {
    let usages: [UsageSnapshot]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Usage And PPS", icon: "bolt.fill")
            VStack(spacing: 8) {
                ForEach(usages.prefix(8)) { snapshot in
                    HStack {
                        Text(snapshot.playerName)
                            .font(.outfit(size: 14, weight: .semibold))
                        Spacer()
                        Text("USG \(snapshot.usageRate.formatted(.percent.precision(.fractionLength(1))))")
                            .font(.outfit(size: 13, weight: .medium))
                        Text("PPS \(snapshot.pointsPerShot.formatted(.number.precision(.fractionLength(2))))")
                            .font(.outfit(size: 13, weight: .medium))
                            .foregroundStyle(HSToken.cool)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSCardRow())
                }
            }
        }
    }
}

private struct PlayerProgressionSection: View {
    let availablePlayers: [String]
    @Binding var selectedPlayer: String
    let progression: [PlayerProgressPoint]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Player Progression", icon: "chart.line.uptrend.xyaxis")
            Picker("Player", selection: $selectedPlayer) {
                ForEach(availablePlayers, id: \.self) { player in
                    Text(player).tag(player)
                }
            }
            .pickerStyle(.menu)
            VStack(spacing: 8) {
                ForEach(progression) { point in
                    HStack {
                        Text(point.date)
                            .font(.outfit(size: 13, weight: .semibold))
                        Spacer()
                        Text("PTS \(point.points)").foregroundStyle(HSToken.accent)
                        Text("REB \(point.rebounds)").foregroundStyle(HSToken.cool)
                        Text("AST \(point.assists)").foregroundStyle(HSToken.gold)
                    }
                    .font(.outfit(size: 13, weight: .medium))
                    .monospacedDigit()
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSCardRow())
                }
            }
        }
    }
}

private struct LineupRankingsSection: View {
    let rankings: [LineupRanking]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Lineup Rankings", icon: HSIcon.lineups)
            VStack(spacing: 8) {
                ForEach(rankings.prefix(8)) { lineup in
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(lineup.players.joined(separator: ", "))
                                .font(.outfit(size: 13, weight: .semibold))
                            Text("Poss \(lineup.possessions)")
                                .font(.outfit(size: 11))
                                .foregroundStyle(HSToken.inkMuted)
                        }
                        Spacer()
                        Text("Net \(lineup.netRating.formatted(.number.precision(.fractionLength(1))))")
                            .font(.bebas(size: 20))
                            .foregroundStyle(lineup.netRating >= 0 ? HSToken.win : HSToken.loss)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSCardRow())
                }
            }
        }
    }
}

/// Cream card row background + border used by list rows.
private struct HSCardRow: View {
    var body: some View {
        RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
            .fill(HSToken.surface)
            .overlay(
                RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
                    .stroke(HSToken.line, lineWidth: 1)
            )
    }
}
