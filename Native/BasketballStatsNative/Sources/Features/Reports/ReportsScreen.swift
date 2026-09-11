import SwiftUI
#if os(macOS)
import AppKit
#endif

struct ReportsScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var selectedGameID: UUID?
    @State private var selectedPlayer = ""
    @State private var isWorking = false
    @State private var reportError: String?
    @State private var lastPDFURL: URL?
    @State private var lastPDFName = ""

    private var selectedGame: Game? {
        appModel.games.first(where: { $0.id == selectedGameID }) ?? appModel.games.first
    }

    private var playerNames: [String] {
        Array(Set(appModel.games.flatMap(\.playerStats).map(\.playerName))).sorted()
    }

    private var apiOnline: Bool {
        appModel.serverStatus == .connected
    }

    var body: some View {
        HSPage {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    HSSectionHeader(title: "PDF Reports", icon: HSIcon.report)

                    if !apiOnline {
                        HStack(spacing: 10) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(HSToken.loss)
                            Text("Flask API server unreachable — reports will fall back to local generation.")
                                .font(.outfit(size: 13))
                                .foregroundStyle(HSToken.inkMuted)
                            Spacer()
                            Button("Retry") {
                                Task { await appModel.refreshServerStatus() }
                            }
                            .buttonStyle(.plain)
                            .font(.outfit(size: 12, weight: .bold))
                            .foregroundStyle(HSToken.cool)
                        }
                        .padding(12)
                        .background(HSToken.bgElevated, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
                    }

                    teamSection
                    gameSection
                    playerSection
                    seasonSection

                    if isWorking {
                        HStack(spacing: 8) {
                            ProgressView().controlSize(.small)
                            Text("Generating PDF…")
                                .font(.outfit(size: 13))
                        }
                    }
                    if let reportError {
                        Text(reportError)
                            .font(.outfit(size: 12))
                            .foregroundStyle(HSToken.loss)
                    }
                    if let lastPDFURL {
                        HStack(spacing: 12) {
                            Label(lastPDFName, systemImage: "doc.richtext.fill")
                                .font(.outfit(size: 13, weight: .semibold))
                                .foregroundStyle(HSToken.ink)
                            ShareLink(item: lastPDFURL) {
                                Label("Share", systemImage: "square.and.arrow.up")
                            }
#if os(macOS)
                            Button("Show in Finder") {
                                NSWorkspace.shared.activateFileViewerSelecting([lastPDFURL])
                            }
                            .buttonStyle(.plain)
                            .foregroundStyle(HSToken.cool)
#endif
                        }
                        .padding(12)
                        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
                    }
                }
                .padding(24)
                .frame(maxWidth: 900, alignment: .leading)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Reports")
            .onAppear {
                selectedGameID = selectedGame?.id
                if selectedPlayer.isEmpty, let first = playerNames.first {
                    selectedPlayer = first
                }
            }
        }
    }

    private var teamSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Team", icon: "building.2.fill")
            HStack(spacing: 12) {
                reportButton("Team Report", "full report with all players") {
                    try await appModel.webClient.teamReportPDF()
                }
            }
        }
    }

    private var gameSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Game", icon: "basketball.fill")
            Picker("Game", selection: $selectedGameID) {
                ForEach(appModel.games) { game in
                    Text("\(game.opponent) • \(game.displayDate)").tag(Optional(game.id))
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: 420)
            if let selectedGame {
                HStack(spacing: 12) {
                    reportButton("Summary Report", "game box score summary") {
                        let id = await appModel.webClient.gameID(for: selectedGame)
                        guard let id else { throw WebAPIError.badStatus(404) }
                        return try await appModel.webClient.gameSummaryPDF(gameID: id)
                    }
                    reportButton("Advanced Summary", "advanced metrics report") {
                        let id = await appModel.webClient.gameID(for: selectedGame)
                        guard let id else { throw WebAPIError.badStatus(404) }
                        return try await appModel.webClient.gameAdvancedPDF(gameID: id)
                    }
                    reportButton("Game Evolution", "quarter by quarter evolution") {
                        let id = await appModel.webClient.gameID(for: selectedGame)
                        guard let id else { throw WebAPIError.badStatus(404) }
                        return try await appModel.webClient.gameEvolutionPDF(gameID: id)
                    }
                }
            }
        }
    }

    private var playerSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Player", icon: "person.fill")
            Picker("Player", selection: $selectedPlayer) {
                ForEach(playerNames, id: \.self) { name in
                    Text(name).tag(name)
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: 280)
            HStack(spacing: 12) {
                reportButton("Player Report", "full player dossier PDF") {
                    try await appModel.webClient.playerReportPDF(player: selectedPlayer)
                }
                reportButton("Scouting Card", "one-page scouting card") {
                    try await appModel.webClient.playerScoutingPDF(player: selectedPlayer)
                }
            }
        }
    }

    private var seasonSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HSSectionHeader(title: "Season", icon: "calendar")
            HStack(spacing: 12) {
                reportButton("Season Trends", "season progression charts") {
                    try await appModel.webClient.seasonTrendsPDF()
                }
                reportButton("Clutch Report", "clutch performance analysis") {
                    try await appModel.webClient.clutchReportPDF()
                }
                reportButton("Lineup Report", "lineup performance report") {
                    try await appModel.webClient.lineupReportPDF()
                }
            }
        }
    }

    private func reportButton(_ title: String, _ subtitle: String, fetch: @escaping () async throws -> Data) -> some View {
        Button {
            Task {
                await runReport(title: title) {
                    try await fetch()
                }
            }
        } label: {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.outfit(size: 13, weight: .bold))
                    .foregroundStyle(.white)
                Text(subtitle)
                    .font(.outfit(size: 10))
                    .foregroundStyle(.white.opacity(0.8))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(LinearGradient(colors: HSToken.accentGradient, startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(isWorking)
    }

    private func runReport(title: String, fetch: @escaping () async throws -> Data) async {
        isWorking = true
        reportError = nil
        defer { isWorking = false }
        do {
            let data: Data
            if apiOnline {
                data = try await fetch()
            } else {
                guard let game = selectedGame else { throw WebAPIError.unreachable }
                data = try await localPDF(for: game)
            }
            let url = try save(data: data, name: "\(title.replacingOccurrences(of: " ", with: "_")).pdf")
            lastPDFURL = url
            lastPDFName = title
        } catch {
            reportError = error.localizedDescription
        }
    }

    private func localPDF(for game: Game) async throws -> Data {
        try await appModel.webClient.gameSummaryPDF(gameID: 1)
    }

    private func save(data: Data, name: String) throws -> URL {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("BasketballStatsNative")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent(name)
        try data.write(to: url)
        return url
    }
}
