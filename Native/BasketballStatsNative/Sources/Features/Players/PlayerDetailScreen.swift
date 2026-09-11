import SwiftUI

struct PlayerDetailScreen: View {
    @Environment(AppModel.self) private var appModel
    let playerName: String

    private var detail: PlayerDetail {
        PlayerStatsComputer.detail(for: playerName, in: appModel.games)
    }

    private var isTeamTotal: Bool {
        playerName == "__team_total__"
    }

    var body: some View {
        HSPage {
            ScrollView {
                VStack(spacing: 20) {
                    header
                    quickOverview
                    advancedMetrics
                    seasonBestsAndDefense
                    gameLog
                }
                .padding()
            }
            .scrollContentBackground(.hidden)
            .navigationTitle(isTeamTotal ? "Team Detail" : playerName)
        }
    }

    private var header: some View {
        HStack(spacing: 16) {
            ZStack {
                Circle()
                    .fill(LinearGradient(colors: [Color(hex: 0x667EEA), Color(hex: 0x764BA2)], startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 72, height: 72)
                Text(initials)
                    .font(.bebas(size: 26))
                    .foregroundStyle(.white)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(isTeamTotal ? "Team Total" : playerName)
                    .font(.bebas(size: 30))
                Text("\(detail.summary.gamesPlayed) Games • \(detail.summary.mpg.formatted(.number.precision(.fractionLength(1)))) MIN")
                    .font(.outfit(size: 13))
                    .foregroundStyle(HSToken.inkMuted)
            }
            Spacer()
        }
        .padding(20)
        .background(
            LinearGradient(colors: [Color(hex: 0x667EEA), Color(hex: 0x764BA2)], startPoint: .topLeading, endPoint: .bottomTrailing),
            in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
        )
        .foregroundStyle(.white)
    }

    private var quickOverview: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Quick Overview", icon: "bolt.fill")
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 3), spacing: 10) {
                metricCard("Points", detail.averages.ppg)
                metricCard("Rebounds", detail.averages.rpg, sub: "\(fmt(detail.averages.orebpg)) Off · \(fmt(detail.averages.drebpg)) Def")
                metricCard("Assists", detail.averages.apg)
                metricCard("Plus/Minus", detail.averages.plusMinus, signed: true)
                metricCard("Off Rating", detail.averages.ortg)
                metricCard("True Shooting", detail.averages.tsPct, suffix: "%")
            }
        }
    }

    private var advancedMetrics: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Advanced Metrics", icon: "chart.xyaxis.line")
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                HSDataRow(label: "Points Per Possession", value: fmt(detail.averages.ppp))
                HSDataRow(label: "Possessions / 40", value: fmt(detail.averages.possPer40))
                HSDataRow(label: "Effective FG%", value: "\(fmt(detail.averages.efgPct))%")
                HSDataRow(label: "Consistency CV%", value: "\(fmt(detail.averages.consistency))%")
                HSDataRow(label: "AST/TOV", value: fmt(detail.averages.astTov))
                HSDataRow(label: "FT Rate", value: "\(fmt(detail.averages.ftaPct))%")
                HSDataRow(label: "2PT%", value: "\(fmt(detail.averages.twoPtPct))%")
                HSDataRow(label: "3PT%", value: "\(fmt(detail.averages.tpPct))%")
                HSDataRow(label: "FT%", value: "\(fmt(detail.averages.ftPct))%")
                HSDataRow(label: "OREB%", value: "\(fmt(detail.averages.orebPct))%")
            }
        }
    }

    private var seasonBestsAndDefense: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
            VStack(alignment: .leading, spacing: 10) {
                HSSectionHeader(title: "Season Bests", icon: "trophy.fill")
                HSDataRow(label: "Points", value: String(detail.careerHighs.points))
                HSDataRow(label: "Rebounds", value: String(detail.careerHighs.rebounds))
                HSDataRow(label: "Assists", value: String(detail.careerHighs.assists))
            }
            .padding(14)
            .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))

            VStack(alignment: .leading, spacing: 10) {
                HSSectionHeader(title: "Defense", icon: "shield.fill")
                HSDataRow(label: "Steals", value: fmt(detail.averages.spg))
                HSDataRow(label: "Blocks", value: fmt(detail.averages.bpg))
                HSDataRow(label: "Def Rebounds", value: fmt(detail.averages.drebpg))
                HSDataRow(label: "Fouls", value: fmt(detail.averages.pfpg))
            }
            .padding(14)
            .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        }
    }

    private var gameLog: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Game Log", icon: "list.bullet")
            HSCard {
                Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 8) {
                    GridRow {
                        headerCell("Date")
                        headerCell("Opp")
                        headerCell("R")
                        headerCell("MIN")
                        headerCell("PTS")
                        headerCell("+/-")
                        headerCell("REB")
                        headerCell("AST")
                        headerCell("STL")
                        headerCell("BLK")
                        headerCell("FG")
                        headerCell("3PT")
                        headerCell("FT")
                        headerCell("TOV")
                        headerCell("EFF")
                        headerCell("GmSc")
                    }
                    Divider().gridCellColumns(16)
                    ForEach(detail.gameLog) { entry in
                        GridRow {
                            cell(entry.game.displayDate)
                            cell(entry.game.opponent)
                            resultBadge(entry.game.result)
                            cell(String(entry.stat.minutes / 60))
                            cell(String(entry.stat.points))
                            cell(signed(entry.stat.plusMinus), signed: true)
                            cell(String(entry.stat.rebounds))
                            cell(String(entry.stat.assists))
                            cell(String(entry.stat.steals))
                            cell(String(entry.stat.blocks))
                            cell("\(entry.stat.fieldGoalsMade)-\(entry.stat.fieldGoalAttempts)")
                            cell("\(entry.stat.threePointsMade)-\(entry.stat.threePointAttempts)")
                            cell("\(entry.stat.freeThrowsMade)-\(entry.stat.freeThrowAttempts)")
                            cell(String(entry.stat.turnovers))
                            cell(fmt(entry.eff))
                            cell(fmt(entry.gmScore))
                        }
                    }
                }
                .font(.outfit(size: 11))
            }
        }
    }

    private func metricCard(_ label: String, _ value: Double, sub: String? = nil, suffix: String = "", signed: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(signed && value > 0 ? "+" : "")\(fmt(value))\(suffix)")
                .font(.bebas(size: 24))
                .foregroundStyle(HSToken.ink)
            Text(label)
                .font(.outfit(size: 10, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
            if let sub {
                Text(sub)
                    .font(.outfit(size: 10))
                    .foregroundStyle(HSToken.inkMuted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
    }

    private func headerCell(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.outfit(size: 9, weight: .bold))
            .foregroundStyle(HSToken.inkMuted)
    }

    private func cell(_ text: String, signed: Bool = false) -> some View {
        Text(text)
            .foregroundStyle(signed ? (text.hasPrefix("+") || text.first != "-" ? HSToken.win : HSToken.loss) : HSToken.ink)
    }

    private func resultBadge(_ result: GameResult) -> some View {
        HSBadge(text: result.rawValue, color: result == .win ? .win : .loss)
    }

    private var initials: String {
        guard !isTeamTotal else { return "TT" }
        let parts = playerName.split(separator: " ")
        if parts.count >= 2 {
            return "\(parts[0].prefix(1))\(parts[1].prefix(1))".uppercased()
        }
        return String(playerName.prefix(2)).uppercased()
    }

    private func fmt(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(1)))
    }

    private func signed(_ value: Int) -> String {
        value > 0 ? "+\(value)" : "\(value)"
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
