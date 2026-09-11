import SwiftUI

struct OpponentSummary: Identifiable, Hashable {
    var id: String { name }
    var name: String
    var games: Int
    var wins: Int
    var record: String
    var avgTeamScore: Double
    var avgOpponentScore: Double

    var winRate: Double {
        games > 0 ? Double(wins) / Double(games) * 100 : 0
    }

    var avgMargin: Double {
        avgTeamScore - avgOpponentScore
    }
}

struct OpponentsScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var selectedOpponent: OpponentSummary?

    private var opponents: [OpponentSummary] {
        let grouped = Dictionary(grouping: appModel.games, by: \.opponent)
        return grouped.map { name, games in
            let wins = games.filter { $0.result == .win }.count
            let avgTeam = Double(games.map(\.teamScore).reduce(0, +)) / Double(games.count)
            let avgOpp = Double(games.map(\.opponentScore).reduce(0, +)) / Double(games.count)
            return OpponentSummary(
                name: name,
                games: games.count,
                wins: wins,
                record: "\(wins)-\(games.count - wins)",
                avgTeamScore: avgTeam,
                avgOpponentScore: avgOpp
            )
        }
        .sorted { $0.name < $1.name }
    }

    var body: some View {
        HSPage {
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 240), spacing: 16)], spacing: 16) {
                    ForEach(opponents) { opponent in
                        Button {
                            selectedOpponent = opponent
                        } label: {
                            opponentCard(opponent)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding()
            }
            .scrollContentBackground(.hidden)
            .navigationTitle("Opponents")
        }
        .sheet(item: $selectedOpponent) { opponent in
            OpponentDetailScreen(opponent: opponent)
        }
    }

    private func opponentCard(_ opponent: OpponentSummary) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                ZStack {
                    Circle()
                        .fill(LinearGradient(colors: [HSToken.cool, Color(hex: 0x4A69BD)], startPoint: .topLeading, endPoint: .bottomTrailing))
                        .frame(width: 52, height: 52)
                    Text(initials(for: opponent.name))
                        .font(.bebas(size: 19))
                        .foregroundStyle(HSToken.surface)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(opponent.name)
                        .font(.outfit(size: 15, weight: .bold))
                        .foregroundStyle(HSToken.ink)
                        .lineLimit(1)
                    Text("\(opponent.games) Games")
                        .font(.outfit(size: 11))
                        .foregroundStyle(HSToken.inkMuted)
                }
                Spacer()
                HSBadge(text: opponent.record, color: opponent.wins >= opponent.games - opponent.wins ? .win : .loss)
            }
            HStack(spacing: 10) {
                miniStat("Wins", "\(opponent.wins)")
                miniStat("Losses", "\(opponent.games - opponent.wins)")
                miniStat("Avg Score", "\(opponent.avgTeamScore.formatted(.number.precision(.fractionLength(1)))) – \(opponent.avgOpponentScore.formatted(.number.precision(.fractionLength(1))))")
            }
        }
        .padding(14)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
    }

    private func miniStat(_ label: String, _ value: String) -> some View {
        VStack(spacing: 1) {
            Text(value)
                .font(.bebas(size: 17))
                .foregroundStyle(HSToken.ink)
            Text(label)
                .font(.outfit(size: 9, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
        .background(HSToken.bgElevated.opacity(0.5), in: RoundedRectangle(cornerRadius: 6, style: .continuous))
    }

    private func initials(for name: String) -> String {
        let parts = name.split(separator: " ")
        if parts.count >= 2 {
            return "\(parts[0].prefix(1))\(parts[1].prefix(1))".uppercased()
        }
        return String(name.prefix(2)).uppercased()
    }
}

struct OpponentDetailScreen: View {
    @Environment(AppModel.self) private var appModel
    let opponent: OpponentSummary

    private var games: [Game] {
        appModel.games.filter { $0.opponent == opponent.name }.sorted { $0.date > $1.date }
    }

    var body: some View {
        HSPage {
            ScrollView {
                VStack(spacing: 18) {
                    hero
                    kpiStrip
                    matchupHistory
                }
                .padding()
            }
            .scrollContentBackground(.hidden)
            .navigationTitle(opponent.name)
        }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("OPPONENT DOSSIER")
                .font(.outfit(size: 11, weight: .bold))
                .foregroundStyle(HSToken.gold.opacity(0.9))
            Text(opponent.name)
                .font(.bebas(size: 40))
            HStack(spacing: 12) {
                HSBadge(text: "\(opponent.record) Record", color: .win)
                HSBadge(text: "\(opponent.winRate.formatted(.number.precision(.fractionLength(0))))% Win Rate", color: .cool)
                HSBadge(text: "Avg \(opponent.avgTeamScore.formatted(.number.precision(.fractionLength(1)))) – \(opponent.avgOpponentScore.formatted(.number.precision(.fractionLength(1))))", color: .neutral)
                if opponent.games > 0 {
                    HSBadge(text: "Net \(opponent.avgMargin.formatted(.number.precision(.fractionLength(1))))", color: .accent)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .background(
            LinearGradient(colors: [Color(hex: 0x151A22), Color(hex: 0x1F1008), Color(hex: 0x2A1A10)], startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
        )
        .foregroundStyle(HSToken.surface)
    }

    private var kpiStrip: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
            kpiCard("Games", "\(opponent.games)", color: HSToken.ink)
            kpiCard("Record", opponent.record, color: opponent.wins >= opponent.games - opponent.wins ? HSToken.win : HSToken.loss)
            kpiCard("Avg Score", "\(opponent.avgTeamScore.formatted(.number.precision(.fractionLength(1)))) – \(opponent.avgOpponentScore.formatted(.number.precision(.fractionLength(1))))", color: HSToken.ink)
            kpiCard("Avg Margin", signed(opponent.avgMargin), color: opponent.avgMargin >= 0 ? HSToken.win : HSToken.loss)
        }
    }

    private func kpiCard(_ label: String, _ value: String, color: Color) -> some View {
        VStack(spacing: 2) {
            Text(value)
                .font(.bebas(size: 24))
                .foregroundStyle(color)
            Text(label)
                .font(.outfit(size: 10, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
    }

    private var matchupHistory: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Matchup History", icon: "clock.arrow.circlepath")
            ForEach(games) { game in
                HSCard {
                    HStack(spacing: 14) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 8)
                                .fill(game.result == .win ? HSToken.win : HSToken.loss)
                                .frame(width: 34, height: 34)
                            Text(game.result.rawValue)
                                .font(.outfit(size: 14, weight: .bold))
                                .foregroundStyle(.white)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(game.displayDate)
                                .font(.outfit(size: 13, weight: .semibold))
                            Text(game.gameType.rawValue)
                                .font(.outfit(size: 10))
                                .foregroundStyle(HSToken.inkMuted)
                        }
                        Spacer()
                        Text(game.scoreDisplay)
                            .font(.bebas(size: 22))
                            .foregroundStyle(HSToken.ink)
                    }
                }
            }
        }
    }

    private func signed(_ value: Double) -> String {
        value > 0 ? "+\(value.formatted(.number.precision(.fractionLength(1))))" : value.formatted(.number.precision(.fractionLength(1)))
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
