import SwiftUI

struct LineupsScreen: View {
    @Environment(AppModel.self) private var appModel

    enum Tab: String, CaseIterable, Identifiable {
        case units = "5-Man Units"
        case duos = "Top Duos"
        case trios = "Top Trios"
        var id: String { rawValue }
    }

    enum Mode: String, CaseIterable, Identifiable {
        case offensive = "Offense"
        case defensive = "Defense"
        var id: String { rawValue }
    }

    @State private var tab: Tab = .units
    @State private var mode: Mode = .offensive
    @State private var minPossessions = 5
    @State private var gameType: GameTypeFilter = .all
    @State private var units: [WebLineupRanking] = []
    @State private var duos: [WebCombination] = []
    @State private var trios: [WebCombination] = []
    @State private var isLoading = true
    @State private var loadError: String?

    enum GameTypeFilter: String, CaseIterable, Identifiable {
        case all = "ALL"
        case season = "Season"
        case friendly = "Friendly"
        var id: String { rawValue }
    }

    var body: some View {
        HSPage {
            VStack(spacing: 0) {
                controls
                tabs
                content
            }
            .navigationTitle("Lineup Analytics")
        }
        .task(id: loadKey) { await load() }
    }

    private var loadKey: String { "\(tab)-\(mode)-\(minPossessions)-\(gameType.rawValue)" }

    private var controls: some View {
        HStack(spacing: 16) {
            Picker("Game Type", selection: $gameType) {
                ForEach(GameTypeFilter.allCases) { type in
                    Text(type.rawValue == "ALL" ? "ALL" : type.rawValue).tag(type)
                }
            }
            .pickerStyle(.menu)
            .frame(width: 140)

            Stepper("Min Possessions: \(minPossessions)", value: $minPossessions, in: 1...50)

            Picker("Mode", selection: $mode) {
                ForEach(Mode.allCases) { m in
                    Text(m.rawValue).tag(m)
                }
            }
            .pickerStyle(.segmented)
            .frame(width: 200)

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

    private var tabs: some View {
        Picker("Tab", selection: $tab) {
            ForEach(Tab.allCases) { t in
                Text(t.rawValue).tag(t)
            }
        }
        .pickerStyle(.segmented)
        .padding(.horizontal, 12)
    }

    @ViewBuilder
    private var content: some View {
        if isLoading {
            Spacer()
            ProgressView("Loading performance data...")
            Spacer()
        } else {
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: 14)], spacing: 14) {
                    switch tab {
                    case .units:
                        ForEach(Array(sortedUnits.enumerated()), id: \.element.id) { index, unit in
                            lineupCard(unit, rank: index + 1)
                        }
                    case .duos:
                        ForEach(Array(sortedCombos(duos).enumerated()), id: \.element.id) { index, combo in
                            comboCard(combo, rank: index + 1)
                        }
                    case .trios:
                        ForEach(Array(sortedCombos(trios).enumerated()), id: \.element.id) { index, combo in
                            comboCard(combo, rank: index + 1)
                        }
                    }
                }
                .padding(12)
            }
            .scrollContentBackground(.hidden)
        }
    }

    private var sortedUnits: [WebLineupRanking] {
        switch mode {
        case .offensive: units.sorted { $0.ortg > $1.ortg }
        case .defensive: units.sorted { $0.drtg < $1.drtg }
        }
    }

    private func sortedCombos(_ combos: [WebCombination]) -> [WebCombination] {
        switch mode {
        case .offensive: combos.sorted { $0.impact.offenseDelta > $1.impact.offenseDelta }
        case .defensive: combos.sorted { $0.impact.defenseDelta > $1.impact.defenseDelta }
        }
    }

    private func lineupCard(_ unit: WebLineupRanking, rank: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                rankBadge(rank)
                Text("\(unit.totalMinutes.formatted(.number.precision(.fractionLength(0)))) min • \(unit.gamesPlayed) games")
                    .font(.outfit(size: 12))
                    .foregroundStyle(HSToken.inkMuted)
                Spacer()
            }
            playerPills(unit.players)
            HStack {
                heroValue(
                    mode == .offensive ? unit.ortg : unit.drtg,
                    label: mode == .offensive ? "ORtg" : "DRtg",
                    barCap: 1.5
                )
                heroValue(unit.netRating, label: "Net Rtg", barCap: 1.5, signed: true)
            }
        }
        .padding(14)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
    }

    private func comboCard(_ combo: WebCombination, rank: Int) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                rankBadge(rank)
                Text("\(Int(combo.on.minutes)) min ON")
                    .font(.outfit(size: 12))
                    .foregroundStyle(HSToken.inkMuted)
                Spacer()
            }
            playerPills(combo.players)
            HStack {
                heroValue(
                    mode == .offensive ? combo.impact.offenseDelta : combo.impact.defenseDelta,
                    label: mode == .offensive ? "Off Diff" : "Def Diff",
                    barCap: 0.5,
                    signed: true
                )
                heroValue(
                    mode == .offensive ? combo.on.ortg : combo.on.drtg,
                    label: mode == .offensive ? "ON ORtg" : "ON DRtg",
                    barCap: 1.5
                )
            }
        }
        .padding(14)
        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
    }

    private func rankBadge(_ rank: Int) -> some View {
        Text("#\(rank)")
            .font(.outfit(size: 11, weight: .bold))
            .foregroundStyle(rankColor(rank))
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(HSToken.bgElevated, in: Capsule())
    }

    private func rankColor(_ rank: Int) -> Color {
        switch rank {
        case 1: Color(hex: 0x92400E)
        case 2: Color(hex: 0x475569)
        case 3: Color(hex: 0x78716C)
        default: HSToken.inkMuted
        }
    }

    private func playerPills(_ players: [String]) -> some View {
        FlowLayout(spacing: 6) {
            ForEach(players, id: \.self) { player in
                Text(player)
                    .font(.outfit(size: 11, weight: .semibold))
                    .foregroundStyle(HSToken.ink)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(HSToken.bgElevated.opacity(0.6), in: Capsule())
            }
        }
    }

    private func heroValue(_ value: Double, label: String, barCap: Double, signed: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("\(signed && value > 0 ? "+" : "")\(value.formatted(.number.precision(.fractionLength(1))))")
                    .font(.bebas(size: 22))
                    .foregroundStyle(HSToken.ink)
                Text(label)
                    .font(.outfit(size: 9, weight: .semibold))
                    .foregroundStyle(HSToken.inkMuted)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(HSToken.bgElevated)
                    Capsule()
                        .fill(LinearGradient(colors: [HSToken.accent, HSToken.cool], startPoint: .leading, endPoint: .trailing))
                        .frame(width: geo.size.width * min(abs(value) / barCap, 1))
                }
            }
            .frame(height: 5)
        }
    }

    private func load() async {
        isLoading = true
        loadError = nil
        do {
            async let unitsTask = appModel.webClient.lineupRankings(gameType: gameType.rawValue, minPossessions: minPossessions)
            async let duosTask = appModel.webClient.combinations(type: "duo", gameType: gameType.rawValue, minPossessions: minPossessions)
            async let triosTask = appModel.webClient.combinations(type: "trio", gameType: gameType.rawValue, minPossessions: minPossessions)
            let (u, d, t) = try await (unitsTask, duosTask, triosTask)
            units = u.rankings
            duos = d.combinations
            trios = t.combinations
        } catch {
            loadError = error.localizedDescription
            units = []
            duos = []
            trios = []
        }
        isLoading = false
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > width, x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width == .infinity ? x : width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
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
