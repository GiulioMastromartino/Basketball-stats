import SwiftUI
import UniformTypeIdentifiers

struct GamesSplitScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var showingImporter = false
    @State private var showingExporter = false

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
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("Import") { showingImporter = true }
                    if appModel.selectedGame != nil {
                        Button("Export") {
                            appModel.exportSelectedGame()
                            showingExporter = true
                        }
                    }
                }
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
                .font(.headline)
            HStack {
                Text(game.displayDate)
                Text(game.gameType.rawValue)
                Text(game.source.rawValue)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
            Text(game.scoreDisplay)
                .font(.body.monospacedDigit())
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
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if let url {
                        ShareLink(item: url) {
                            Label("Share Raw Export", systemImage: "square.and.arrow.up")
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    Text(summary)
                        .font(.body.monospaced())
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
                .padding(24)
            }
            .navigationTitle("Export Game")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
