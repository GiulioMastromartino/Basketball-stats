import SwiftUI

struct GameDetailScreen: View {
    let gameID: UUID
    @Environment(AppModel.self) private var appModel
    @State private var isEditing = false

    private var game: Game? {
        appModel.games.first(where: { $0.id == gameID })
    }

    var body: some View {
        Group {
            if let game {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        ScoreHeader(game: game)
                        PlayerStatsSection(playerStats: game.playerStats)
                        ShotProfileSection(shots: game.shotEvents)
                        LineupSegmentSection(segments: game.lineupSegments)
                        NotesSection(notes: game.notes)
                    }
                    .padding(24)
                }
                .navigationTitle(game.opponent)
                .background(Color(.systemGroupedBackground))
                .toolbar {
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        Button("Edit") { isEditing = true }
                        Button(role: .destructive, action: appModel.deleteSelectedGame) {
                            Image(systemName: "trash")
                        }
                    }
                }
                .sheet(isPresented: $isEditing) {
                    GameEditorSheet(game: game) { updated in
                        appModel.updateGame(updated)
                    }
                }
            } else {
                ContentUnavailableView("Game Missing", systemImage: "exclamationmark.triangle")
            }
        }
    }
}

private struct ScoreHeader: View {
    let game: Game

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(game.date.formatted(date: .complete, time: .omitted))
                .font(.headline)
                .foregroundStyle(.secondary)
            HStack(alignment: .firstTextBaseline) {
                Text(game.scoreDisplay)
                    .font(.system(size: 42, weight: .bold, design: .rounded))
                Text(game.result.rawValue)
                    .font(.title.weight(.bold))
                    .foregroundStyle(game.result == .win ? .green : .red)
            }
            Label("\(game.gameType.rawValue) • \(game.source.rawValue) • schema \(game.schemaVersion)", systemImage: "chart.bar.doc.horizontal")
                .font(.subheadline)
        }
        .padding(24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
    }
}

private struct PlayerStatsSection: View {
    let playerStats: [PlayerStat]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Player Stats")
                .font(.title2.weight(.bold))
            ForEach(playerStats) { stat in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(stat.playerName)
                            .font(.headline)
                        Text("TS \(stat.trueShootingPercentage.formatted(.percent.precision(.fractionLength(0))))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    StatPill(title: "PTS", value: "\(stat.points)")
                    StatPill(title: "REB", value: "\(stat.rebounds)")
                    StatPill(title: "AST", value: "\(stat.assists)")
                }
                .padding(16)
                .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }
        }
    }
}

private struct StatPill: View {
    let title: String
    let value: String

    var body: some View {
        VStack(spacing: 4) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.headline.monospacedDigit())
        }
        .frame(width: 56)
    }
}

private struct ShotProfileSection: View {
    let shots: [ShotEvent]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Shot Profile")
                .font(.title2.weight(.bold))
            if shots.isEmpty {
                EmptyCard(text: "No shot chart data captured for this game.")
            } else {
                let grouped = Dictionary(grouping: shots, by: \.zone)
                ForEach(grouped.keys.sorted(by: { $0.rawValue < $1.rawValue }), id: \.self) { zone in
                    let made = grouped[zone]?.filter { $0.result == .made }.count ?? 0
                    let attempts = grouped[zone]?.count ?? 0
                    HStack {
                        Text(zone.rawValue)
                        Spacer()
                        Text("\(made)/\(attempts)")
                            .font(.headline.monospacedDigit())
                    }
                    .padding(16)
                    .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
            }
        }
    }
}

private struct LineupSegmentSection: View {
    let segments: [LineupSegment]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Lineup Segments")
                .font(.title2.weight(.bold))
            if segments.isEmpty {
                EmptyCard(text: "No lineup data captured for this game.")
            } else {
                ForEach(segments) { segment in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(segment.displayName ?? "Quarter \(segment.quarter)")
                            .font(.headline)
                        Text(segment.players.joined(separator: ", "))
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        HStack {
                            Label("\(segment.pointsScored) scored", systemImage: "plus.circle")
                            Label("\(segment.pointsAllowed) allowed", systemImage: "minus.circle")
                            Label("\(segment.possessions) poss.", systemImage: "arrow.left.arrow.right")
                            Label(segment.netRatingValue.formatted(.number.precision(.fractionLength(1))), systemImage: "chart.line.uptrend.xyaxis")
                        }
                        .font(.caption.weight(.semibold))
                    }
                    .padding(16)
                    .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
            }
        }
    }
}

private struct NotesSection: View {
    let notes: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Coach Notes")
                .font(.title2.weight(.bold))
            EmptyCard(text: notes.isEmpty ? "No notes" : notes)
        }
    }
}

private struct EmptyCard: View {
    let text: String

    var body: some View {
        Text(text)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(18)
            .background(.background, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}

private struct GameEditorSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var draft: Game
    let onSave: (Game) -> Void

    init(game: Game, onSave: @escaping (Game) -> Void) {
        _draft = State(initialValue: game)
        self.onSave = onSave
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Game") {
                    TextField("Opponent", text: $draft.opponent)
                    Picker("Type", selection: $draft.gameType) {
                        ForEach(GameType.allCases, id: \.self) { type in
                            Text(type.rawValue).tag(type)
                        }
                    }
                    Stepper("Team Score \(draft.teamScore)", value: $draft.teamScore, in: 0...200)
                    Stepper("Opponent Score \(draft.opponentScore)", value: $draft.opponentScore, in: 0...200)
                }
                Section("Players") {
                    ForEach(Array(draft.playerStats.indices), id: \.self) { index in
                        VStack(alignment: .leading) {
                            TextField("Player", text: $draft.playerStats[index].playerName)
                            Stepper("Points \(draft.playerStats[index].points)", value: $draft.playerStats[index].points, in: 0...80)
                            Stepper("Rebounds \(draft.playerStats[index].rebounds)", value: $draft.playerStats[index].rebounds, in: 0...30)
                            Stepper("Assists \(draft.playerStats[index].assists)", value: $draft.playerStats[index].assists, in: 0...20)
                        }
                    }
                }
                Section("Notes") {
                    TextEditor(text: $draft.notes)
                        .frame(minHeight: 120)
                }
            }
            .navigationTitle("Edit Game")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(draft)
                        dismiss()
                    }
                }
            }
        }
    }
}
