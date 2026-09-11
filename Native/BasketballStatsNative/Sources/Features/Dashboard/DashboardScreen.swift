import SwiftUI

struct DashboardScreen: View {
    @Environment(AppModel.self) private var appModel

    var body: some View {
        HSPage {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    hero
                    metrics
                    TopScorersSection(players: appModel.teamOverview.topScorers)
                    RecentGamesSection(games: Array(appModel.games.prefix(6)))
                }
                .padding(24)
                .frame(maxWidth: 1100, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
        }
        .background(HSToken.bgMain)
        .navigationTitle("Dashboard")
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Dashboard")
                .font(.bebas(size: 44))
                .foregroundStyle(HSToken.ink)
            HStack(spacing: 8) {
                Text("Signed in as \(appModel.currentUser?.username ?? "unknown") • \(appModel.currentUser?.role.rawValue.capitalized ?? "viewer")")
                    .font(.outfit(size: 13, weight: .semibold))
                Spacer()
                HSBadge(text: appModel.syncSummary, color: .cool)
            }
        }
        .padding(22)
        .background(HSToken.bgElevated, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
        .overlay(alignment: .topTrailing) {
            LinearGradient(colors: HSToken.accentGradient, startPoint: .topLeading, endPoint: .bottomTrailing)
                .frame(width: 120, height: 6)
                .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                .padding(.top, 0)
        }
    }

    private var metrics: some View {
        let summary = appModel.dashboardSummary
        let overview = appModel.teamOverview
        return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
            HSMetricCard(title: "Games", value: "\(summary.totalGames)", tint: HSToken.accent)
            HSMetricCard(title: "Win Rate", value: summary.winRateText, tint: HSToken.win)
            HSMetricCard(title: "Avg Points", value: summary.averagePointsText, tint: HSToken.cool)
            HSMetricCard(title: "Avg Margin", value: overview.averageMargin.formatted(.number.precision(.fractionLength(1))), tint: HSToken.gold)
        }
    }
}

private struct TopScorersSection: View {
    let players: [PlayerAverage]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Top Scorers", icon: "trophy.fill")
            VStack(spacing: 8) {
                ForEach(players.prefix(5)) { player in
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(player.playerName)
                                .font(.outfit(size: 14, weight: .semibold))
                            Text("TS \(player.trueShooting.formatted(.percent.precision(.fractionLength(0))))")
                                .font(.outfit(size: 12))
                                .foregroundStyle(HSToken.inkMuted)
                        }
                        Spacer()
                        Text(player.points.formatted(.number.precision(.fractionLength(1))))
                            .font(.bebas(size: 24))
                            .foregroundStyle(HSToken.accent)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
                            .stroke(HSToken.line, lineWidth: 1)
                    )
                }
            }
        }
    }
}

private struct RecentGamesSection: View {
    let games: [Game]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Recent Games", icon: HSIcon.games)
            VStack(spacing: 8) {
                ForEach(games) { game in
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(game.opponent)
                                .font(.outfit(size: 14, weight: .semibold))
                            Text(game.displayDate)
                                .font(.outfit(size: 12))
                                .foregroundStyle(HSToken.inkMuted)
                        }
                        Spacer()
                        Text(game.scoreDisplay)
                            .font(.bebas(size: 22))
                            .foregroundStyle(HSToken.ink)
                        HSBadge(text: game.result.rawValue, color: game.result == .win ? .win : .loss)
                            .frame(width: 56)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
                            .stroke(HSToken.line, lineWidth: 1)
                    )
                }
            }
        }
    }
}
