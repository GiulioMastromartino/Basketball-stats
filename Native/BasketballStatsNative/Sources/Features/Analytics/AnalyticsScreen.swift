import SwiftUI

struct AnalyticsScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var selectedPlayer = ""

    var body: some View {
        NavigationStack {
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
            }
            .background(Color(.systemGroupedBackground))
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
            Text("Team Overview")
                .font(.title2.weight(.bold))
            HStack {
                AnalyticsMetric(title: "PPG", value: overview.pointsPerGame.formatted(.number.precision(.fractionLength(1))))
                AnalyticsMetric(title: "PAPG", value: overview.pointsAllowedPerGame.formatted(.number.precision(.fractionLength(1))))
                AnalyticsMetric(title: "Margin", value: overview.averageMargin.formatted(.number.precision(.fractionLength(1))))
            }
        }
    }
}

private struct AnalyticsMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.monospacedDigit().weight(.bold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

private struct UsageSection: View {
    let usages: [UsageSnapshot]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Usage And PPS")
                .font(.title2.weight(.bold))
            ForEach(usages.prefix(8)) { snapshot in
                HStack {
                    Text(snapshot.playerName)
                        .font(.headline)
                    Spacer()
                    Text("USG \(snapshot.usageRate.formatted(.percent.precision(.fractionLength(1))))")
                    Text("PPS \(snapshot.pointsPerShot.formatted(.number.precision(.fractionLength(2))))")
                }
                .padding(16)
                .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
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
            Text("Player Progression")
                .font(.title2.weight(.bold))
            Picker("Player", selection: $selectedPlayer) {
                ForEach(availablePlayers, id: \.self) { player in
                    Text(player).tag(player)
                }
            }
            .pickerStyle(.menu)
            ForEach(progression) { point in
                HStack {
                    Text(point.date)
                    Spacer()
                    Text("PTS \(point.points)")
                    Text("REB \(point.rebounds)")
                    Text("AST \(point.assists)")
                }
                .padding(16)
                .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
        }
    }
}

private struct LineupRankingsSection: View {
    let rankings: [LineupRanking]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Lineup Rankings")
                .font(.title2.weight(.bold))
            ForEach(rankings.prefix(8)) { lineup in
                VStack(alignment: .leading, spacing: 6) {
                    Text(lineup.players.joined(separator: ", "))
                        .font(.headline)
                    HStack {
                        Text("Net \(lineup.netRating.formatted(.number.precision(.fractionLength(1))))")
                        Text("Poss \(lineup.possessions)")
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                }
                .padding(16)
                .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
        }
    }
}
