import SwiftUI
import UniformTypeIdentifiers

struct GamesSplitScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var showingImporter = false
    @State private var showingExporter = false
    @State private var showingOpponents = false
    @State private var webImport = false
    @State private var showingImportResult = false

    var body: some View {
        NavigationSplitView {
            List(selection: selectedGameID) {
                ForEach(appModel.games) { game in
                    GameListRow(game: game)
                        .tag(Optional(game.id))
                }
            }
            .navigationTitle("Games")
            .toolbar {
                ToolbarItemGroup(placement: .primaryAction) {
                    Button("Opponents") { showingOpponents = true }
                    Menu("Import") {
                        Button("Local Import") { showingImporter = true }
                        Button("Web Import (Server)") { webImport = true }
                    }
                    if appModel.selectedGame != nil {
                        Button("Export") {
                            appModel.exportSelectedGame()
                            showingExporter = true
                        }
                    }
                }
            }
            .sheet(isPresented: $showingOpponents) {
                OpponentsScreen()
            }
            .fileImporter(
                isPresented: $showingImporter,
                allowedContentTypes: [.json, .commaSeparatedText],
                allowsMultipleSelection: true
            ) { result in
                if case .success(let urls) = result {
                    appModel.importGames(from: urls)
                }
            }
            .fileImporter(
                isPresented: $webImport,
                allowedContentTypes: [.json, .commaSeparatedText, .pdf],
                allowsMultipleSelection: true
            ) { result in
                if case .success(let urls) = result {
                    appModel.webImport(from: urls)
                }
            }
            .onChange(of: appModel.importResultMessage) {
                if appModel.importResultMessage != nil { showingImportResult = true }
            }
            .alert("Import Result", isPresented: $showingImportResult) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(appModel.importResultMessage ?? "Importing...")
            }
        } detail: {
            if let gameID = appModel.selectedGame?.id {
                GameDetailScreen(gameID: gameID)
            } else {
                ContentUnavailableView("No Game Selected", systemImage: "basketball", description: Text("Choose a game from the sidebar."))
            }
        }
        .sheet(isPresented: $showingExporter) {
            ExportSheet(url: appModel.lastExportURL, summary: appModel.generatedReportText)
        }
    }

    private var selectedGameID: Binding<UUID?> {
        Binding(
            get: { appModel.selectedGameID },
            set: { appModel.selectGame($0) }
        )
    }
}

private struct GameListRow: View {
    let game: Game

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(game.opponent)
                .font(.outfit(size: 14, weight: .semibold))
            HStack {
                Text(game.displayDate)
                Text(game.gameType.rawValue)
                Text(game.source.rawValue)
            }
            .font(.outfit(size: 11))
            .foregroundStyle(HSToken.inkMuted)
            Text(game.scoreDisplay)
                .font(.bebas(size: 20))
                .foregroundStyle(game.result == .win ? HSToken.win : HSToken.loss)
        }
        .padding(.vertical, 6)
    }
}

private struct ExportSheet: View {
    let url: URL?
    let summary: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            HSPage {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        if let url {
                            ShareLink(item: url) {
                                Label("Share Raw Export", systemImage: "square.and.arrow.up")
                                    .font(.outfit(size: 13, weight: .bold))
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 10)
                                    .background(LinearGradient(colors: HSToken.accentGradient, startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous))
                            }
                            .buttonStyle(.plain)
                        }
                        HSCard {
                            Text(summary)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(HSToken.ink)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(24)
                    .frame(maxWidth: 700, alignment: .leading)
                    .frame(maxWidth: .infinity)
                }
                .navigationTitle("Export Game")
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        Button("Done") { dismiss() }
                    }
                }
            }
        }
    }
}
