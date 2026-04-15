import SwiftUI

struct ReportsScreen: View {
    @Environment(AppModel.self) private var appModel
    @State private var selectedGameID: UUID?

    private var selectedGame: Game? {
        appModel.games.first(where: { $0.id == selectedGameID }) ?? appModel.games.first
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Picker("Game", selection: $selectedGameID) {
                        ForEach(appModel.games) { game in
                            Text("\(game.opponent) • \(game.displayDate)").tag(Optional(game.id))
                        }
                    }
                    .pickerStyle(.menu)

                    if let selectedGame {
                        Button("Generate Summary Report") {
                            appModel.generateReport(for: selectedGame)
                        }
                        .buttonStyle(.borderedProminent)

                        if let url = appModel.lastReportURL {
                            ShareLink(item: url) {
                                Label("Share PDF", systemImage: "square.and.arrow.up")
                            }
                        }

                        Text(appModel.generatedReportText.isEmpty ? "Generate a report to preview it." : appModel.generatedReportText)
                            .font(.body.monospaced())
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(16)
                            .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    } else {
                        ContentUnavailableView("No Games Available", systemImage: "doc.richtext")
                    }
                }
                .padding(24)
            }
            .background(Color(.systemGroupedBackground))
            .navigationTitle("Reports")
            .onAppear {
                selectedGameID = selectedGame?.id
            }
        }
    }
}
