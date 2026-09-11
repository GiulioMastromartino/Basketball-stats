import SwiftUI

struct AdvancedScreen: View {
    @Environment(AppModel.self) private var appModel

    enum Tab: String, CaseIterable, Identifiable {
        case shotCharts = "Shot Charts"
        case fourFactors = "Four Factors"
        case playerStats = "Player Stats"
        var id: String { rawValue }
    }

    @State private var tab: Tab = .fourFactors
    @State private var gameType: LineupsScreen.GameTypeFilter = .season
    @State private var selectedPlayer: String?
    @State private var fourFactors: WebFourFactorsValues?
    @State private var shotChart: WebShotChart?
    @State private var advancedPlayer: WebAdvancedPlayer?
    @State private var isLoading = false
    @State private var loadError: String?

    var body: some View {
        HSPage {
            VStack(spacing: 0) {
                controls
                Picker("Tab", selection: $tab) {
                    ForEach(Tab.allCases) { t in
                        Text(t.rawValue).tag(t)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 12)
                .padding(.bottom, 10)
                content
            }
            .navigationTitle("Advanced Analytics")
        }
        .task(id: loadKey) { await load() }
    }

    private var loadKey: String { "\(tab)-\(gameType.rawValue)-\(selectedPlayer ?? "")" }

    private var controls: some View {
        HStack(spacing: 16) {
            Picker("Game Type", selection: $gameType) {
                ForEach(LineupsScreen.GameTypeFilter.allCases) { type in
                    Text(type.rawValue == "ALL" ? "ALL" : type.rawValue).tag(type)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 140)

            if tab == .shotCharts || tab == .playerStats {
                Picker("Player", selection: $selectedPlayer) {
                    Text("All Players").tag(String?.none)
                    ForEach(playerNames, id: \.self) { name in
                        Text(name).tag(Optional(name))
                    }
                }
                .pickerStyle(.menu)
                .frame(width: 180)
            }

            Spacer()

            if isLoading {
                ProgressView().controlSize(.small)
            } else if let loadError {
                Text(loadError)
                    .font(.outfit(size: 11))
                    .foregroundStyle(HSToken.loss)
            }
        }
        .padding(12)
        .background(HSToken.bgElevated, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
        .padding(12)
    }

    private var playerNames: [String] {
        Array(Set(appModel.games.flatMap(\.playerStats).map(\.playerName))).sorted()
    }

    @ViewBuilder
    private var content: some View {
        switch tab {
        case .fourFactors:
            fourFactorsView
        case .shotCharts:
            shotChartView
        case .playerStats:
            playerStatsView
        }
    }

    private var fourFactorsView: some View {
        ScrollView {
            if let fourFactors {
                LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], spacing: 12) {
                    factorCard("eFG%", fourFactors.efgPct)
                    factorCard("TOV%", fourFactors.tovPct)
                    factorCard("ORB%", fourFactors.orbPct)
                    factorCard("FT Rate", fourFactors.ftRate)
                }
                .padding(12)
            } else {
                emptyState("No four factors data. Connect to the Flask API server or record games first.")
            }
        }
        .scrollContentBackground(.hidden)
    }

    private func factorCard(_ label: String, _ value: Double) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(value.formatted(.number.precision(.fractionLength(1))))
                    .font(.bebas(size: 30))
                    .foregroundStyle(HSToken.ink)
                Text("%").font(.bebas(size: 18)).foregroundStyle(HSToken.inkMuted)
                Spacer()
                Text(label)
                    .font(.outfit(size: 11, weight: .bold))
                    .foregroundStyle(HSToken.inkMuted)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(HSToken.bgElevated)
                    Capsule()
                        .fill(LinearGradient(colors: [Color(hex: 0x1E3C72), HSToken.cool], startPoint: .leading, endPoint: .trailing))
                        .frame(width: geo.size.width * min(max(value, 0), 100) / 100)
                }
            }
            .frame(height: 8)
        }
        .padding(16)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
    }

    private var shotChartView: some View {
        ScrollView {
            VStack(spacing: 14) {
                if let shotChart {
                    HStack(spacing: 20) {
                        Label("\(shotChart.shots.filter { $0.result == "made" }.count) Makes", systemImage: "circle.fill")
                            .foregroundStyle(Color(hex: 0x28A745))
                        Label("\(shotChart.shots.filter { $0.result != "made" }.count) Misses", systemImage: "circle")
                            .foregroundStyle(Color(hex: 0xDC3545))
                        Text("\(shotChart.totalShots) Total")
                            .foregroundStyle(HSToken.inkMuted)
                        Spacer()
                    }
                    .font(.outfit(size: 13, weight: .semibold))
                    .padding(.horizontal, 12)

                    HSCard {
                        ShotChartView(shots: shotChart.shots)
                            .frame(height: 460)
                    }
                } else {
                    emptyState("No shot data. Connect to the Flask API server.")
                }
            }
            .padding(12)
        }
        .scrollContentBackground(.hidden)
    }

    private var playerStatsView: some View {
        ScrollView {
            if let advancedPlayer {
                VStack(spacing: 14) {
                    LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10), count: 4), spacing: 10) {
                        playerStatCard("PPG", advancedPlayer.seasonStats.ppg)
                        playerStatCard("RPG", advancedPlayer.seasonStats.rpg)
                        playerStatCard("APG", advancedPlayer.seasonStats.apg)
                        playerStatCard("FG%", advancedPlayer.seasonStats.fgPct)
                        playerStatCard("TS%", advancedPlayer.seasonStats.tsPct)
                        playerStatCard("eFG%", advancedPlayer.seasonStats.efgPct)
                        playerStatCard("PPS", advancedPlayer.seasonStats.pps)
                        playerStatCard("USG%", advancedPlayer.seasonStats.usageRate)
                    }
                    HSDataRow(label: "Games Played", value: String(advancedPlayer.seasonStats.games))
                        .padding(.horizontal, 12)
                }
                .padding(12)
            } else {
                emptyState("Select a player to view advanced stats.")
            }
        }
        .scrollContentBackground(.hidden)
    }

    private func playerStatCard(_ label: String, _ value: Double) -> some View {
        VStack(spacing: 2) {
            Text(value.formatted(.number.precision(.fractionLength(1))))
                .font(.bebas(size: 26))
                .foregroundStyle(HSToken.ink)
            Text(label)
                .font(.outfit(size: 10, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
    }

    private func emptyState(_ message: String) -> some View {
        VStack(spacing: 10) {
            Image(systemName: "chart.line.downtrend.xyaxis")
                .font(.system(size: 34))
                .foregroundStyle(HSToken.inkMuted)
            Text(message)
                .font(.outfit(size: 13))
                .foregroundStyle(HSToken.inkMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 60)
    }

    private func load() async {
        isLoading = true
        loadError = nil
        do {
            switch tab {
            case .fourFactors:
                let result = try await appModel.webClient.fourFactors(gameType: gameType.rawValue)
                fourFactors = result.fourFactors
            case .shotCharts:
                let result = try await appModel.webClient.shotChart(gameType: gameType.rawValue, player: selectedPlayer)
                shotChart = result
            case .playerStats:
                if let selectedPlayer {
                    advancedPlayer = try await appModel.webClient.advancedPlayer(selectedPlayer, gameType: gameType.rawValue)
                } else {
                    advancedPlayer = nil
                }
            }
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }
}

struct ShotChartView: View {
    let shots: [WebShot]

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let h = geo.size.height
            ZStack {
                court(w: w, h: h)
                ForEach(Array(shots.enumerated()), id: \.element.id) { index, shot in
                    let made = shot.result == "made"
                    Circle()
                        .fill(made ? Color(hex: 0x28A745) : Color.clear)
                        .stroke(made ? Color.clear : Color(hex: 0xDC3545), lineWidth: 1.5)
                        .frame(width: 7, height: 7)
                        .position(x: w * shot.xLoc / 100, y: h * shot.yLoc / 100)
                }
            }
        }
    }

    private func court(w: CGFloat, h: CGFloat) -> some View {
        ZStack {
            Color(hex: 0xF0E6D2)
            Path { path in
                path.move(to: CGPoint(x: 0, y: h * 0.12))
                path.addLine(to: CGPoint(x: w, y: h * 0.12))
                path.addLine(to: CGPoint(x: w, y: h))
                path.addLine(to: CGPoint(x: 0, y: h))
                path.closeSubpath()
            }
            .fill(Color(hex: 0xF0E6D2))
            Path { path in
                path.move(to: CGPoint(x: 0, y: h * 0.30))
                path.addLine(to: CGPoint(x: w, y: h * 0.30))
            }
            .stroke(Color.black.opacity(0.3), lineWidth: 1.5)
            Path { path in
                path.move(to: CGPoint(x: 0, y: h * 0.55))
                path.addLine(to: CGPoint(x: w, y: h * 0.55))
            }
            .stroke(Color.black.opacity(0.3), lineWidth: 1.5)
            Path { path in
                path.move(to: CGPoint(x: w * 0.42, y: 0))
                path.addLine(to: CGPoint(x: w * 0.42, y: h * 0.12))
            }
            .stroke(Color.black.opacity(0.3), lineWidth: 1.5)
            Path { path in
                path.move(to: CGPoint(x: w * 0.58, y: 0))
                path.addLine(to: CGPoint(x: w * 0.58, y: h * 0.12))
            }
            .stroke(Color.black.opacity(0.3), lineWidth: 1.5)
            Circle()
                .stroke(Color.black.opacity(0.3), lineWidth: 1.5)
                .frame(width: w * 0.16, height: w * 0.16)
                .position(x: w * 0.5, y: h * 0.12)
            Circle()
                .stroke(Color.red, lineWidth: 2)
                .frame(width: w * 0.06, height: w * 0.06)
                .position(x: w * 0.5, y: h * 0.12)
            Circle()
                .stroke(Color.red.opacity(0.6), lineWidth: 1.5)
                .frame(width: w * 0.36, height: w * 0.36)
                .position(x: w * 0.5, y: h * 0.12)
            Path { path in
                let r = w * 0.24
                path.addArc(
                    center: CGPoint(x: w * 0.5, y: h * 0.12),
                    radius: r,
                    startAngle: .degrees(180),
                    endAngle: .degrees(360),
                    clockwise: false
                )
            }
            .stroke(Color.black.opacity(0.3), lineWidth: 1.5)
        }
        .clipShape(RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
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
