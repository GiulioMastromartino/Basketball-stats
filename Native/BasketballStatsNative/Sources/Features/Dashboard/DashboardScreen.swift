import SwiftUI

struct DashboardScreen: View {
    @Environment(AppModel.self) private var appModel

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    DashboardHeader(summary: appModel.dashboardSummary, currentUser: appModel.currentUser, syncSummary: appModel.syncSummary)
                    DashboardHighlights(summary: appModel.dashboardSummary, overview: appModel.teamOverview)
                    TopScorersSection(players: appModel.teamOverview.topScorers)
                    RecentGamesSection(games: Array(appModel.games.prefix(5)))
                }
                .padding(24)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Basketball Stats")
        }
    }
}

private struct DashboardHeader: View {
    let summary: DashboardSummary
    let currentUser: User?
    let syncSummary: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Native iPad Control Room")
                .font(.system(.largeTitle, design: .rounded, weight: .bold))
            Text("Signed in as \(currentUser?.username ?? "unknown") • \(currentUser?.role.rawValue.capitalized ?? "viewer")")
                .font(.headline)
            Text(syncSummary)
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.85))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(24)
        .background(
            LinearGradient(
                colors: [.orange.opacity(0.85), .red.opacity(0.75)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 28, style: .continuous)
        )
        .foregroundStyle(.white)
    }
}

private struct DashboardHighlights: View {
    let summary: DashboardSummary
    let overview: TeamOverview

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
            MetricCard(title: "Games", value: "\(summary.totalGames)", tint: .blue)
            MetricCard(title: "Win Rate", value: summary.winRateText, tint: .green)
            MetricCard(title: "Avg Points", value: summary.averagePointsText, tint: .orange)
            MetricCard(title: "Avg Margin", value: overview.averageMargin.formatted(.number.precision(.fractionLength(1))), tint: .purple)
        }
    }
}

private struct MetricCard: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(.title, design: .rounded, weight: .bold))
                .foregroundStyle(tint)
        }
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
        .padding(20)
        .background(.background, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }
}

private struct TopScorersSection: View {
    let players: [PlayerAverage]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Top Scorers")
                .font(.title2.weight(.bold))
            ForEach(players) { player in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(player.playerName)
                            .font(.headline)
                        Text("TS \(player.trueShooting.formatted(.percent.precision(.fractionLength(0))))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(player.points.formatted(.number.precision(.fractionLength(1))))
                        .font(.title3.monospacedDigit().weight(.semibold))
                }
                .padding(16)
                .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
        }
    }
}

private struct RecentGamesSection: View {
    let games: [Game]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Recent Games")
                .font(.title2.weight(.bold))
            ForEach(games) { game in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(game.opponent)
                            .font(.headline)
                        Text(game.displayDate)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(game.scoreDisplay)
                        .font(.title3.monospacedDigit().weight(.semibold))
                    Text(game.result.rawValue)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(game.result == .win ? .green : .red)
                }
                .padding(18)
                .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
        }
    }
}
