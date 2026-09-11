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
                HSPage {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 20) {
                            ScoreHeader(game: game)
                            PlayerStatsSection(playerStats: game.playerStats)
                            ShotProfileSection(shots: game.shotEvents)
                            LineupSegmentSection(segments: game.lineupSegments)
                            NotesSection(notes: game.notes)
                        }
                        .padding(24)
                        .frame(maxWidth: 1000, alignment: .leading)
                        .frame(maxWidth: .infinity)
                    }
                    .navigationTitle(game.opponent)
                    .toolbar {
                        ToolbarItemGroup(placement: .primaryAction) {
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
            HStack {
                Text(game.date.formatted(date: .complete, time: .omitted))
                    .font(.outfit(size: 13, weight: .semibold))
                    .foregroundStyle(HSToken.inkMuted)
                Spacer()
                HSBadge(text: game.result.rawValue, color: game.result == .win ? .win : .loss)
            }
            HStack(alignment: .firstTextBaseline, spacing: 14) {
                Text(game.scoreDisplay)
                    .font(.bebas(size: 52))
                    .foregroundStyle(HSToken.ink)
                Text(game.result == .win ? "WIN" : "LOSS")
                    .font(.bebas(size: 24))
                    .foregroundStyle(game.result == .win ? HSToken.win : HSToken.loss)
            }
            Label("\(game.gameType.rawValue) • \(game.source.rawValue) • schema \(game.schemaVersion)", systemImage: "chart.bar.doc.horizontal")
                .font(.outfit(size: 12))
                .foregroundStyle(HSToken.inkMuted)
        }
        .padding(22)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(HSToken.bgElevated, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                .stroke(HSToken.line, lineWidth: 1)
        )
        .overlay(alignment: .topTrailing) {
            LinearGradient(colors: game.result == .win ? HSToken.coolGradient : [HSToken.loss], startPoint: .leading, endPoint: .trailing)
                .frame(width: 120, height: 6)
                .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
        }
    }
}

private struct PlayerStatsSection: View {
    let playerStats: [PlayerStat]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Player Stats", icon: HSIcon.players)
            VStack(spacing: 8) {
                ForEach(playerStats) { stat in
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(stat.playerName)
                                .font(.outfit(size: 14, weight: .semibold))
                            Text("TS \(stat.trueShootingPercentage.formatted(.percent.precision(.fractionLength(0))))")
                                .font(.outfit(size: 12))
                                .foregroundStyle(HSToken.inkMuted)
                        }
                        Spacer()
                        StatPill(title: "PTS", value: "\(stat.points)")
                        StatPill(title: "REB", value: "\(stat.rebounds)")
                        StatPill(title: "AST", value: "\(stat.assists)")
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSCardRow())
                }
            }
        }
    }
}

private struct StatPill: View {
    let title: String
    let value: String

    var body: some View {
        VStack(spacing: 3) {
            Text(title)
                .font(.outfit(size: 10, weight: .semibold))
                .foregroundStyle(HSToken.inkMuted)
            Text(value)
                .font(.bebas(size: 18))
                .foregroundStyle(HSToken.accent)
        }
        .frame(width: 56)
        .padding(.vertical, 4)
        .background(HSToken.accent.opacity(0.08), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
    }
}

private struct ShotProfileSection: View {
    let shots: [ShotEvent]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Shot Profile", icon: "scope")
            if shots.isEmpty {
                HSCard { Text("No shot chart data captured for this game.").foregroundStyle(HSToken.inkMuted) }
            } else {
                let grouped = Dictionary(grouping: shots, by: \.zone)
                ForEach(grouped.keys.sorted(by: { $0.rawValue < $1.rawValue }), id: \.self) { zone in
                    let made = grouped[zone]?.filter { $0.result == .made }.count ?? 0
                    let attempts = grouped[zone]?.count ?? 0
                    HStack {
                        Text(zone.rawValue)
                            .font(.outfit(size: 13, weight: .semibold))
                        Spacer()
                        Text("\(made)/\(attempts)")
                            .font(.bebas(size: 18))
                            .foregroundStyle(HSToken.accent)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(HSCardRow())
                }
            }
        }
    }
}

private struct LineupSegmentSection: View {
    let segments: [LineupSegment]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Lineup Segments", icon: HSIcon.lineups)
            if segments.isEmpty {
                HSCard { Text("No lineup data captured for this game.").foregroundStyle(HSToken.inkMuted) }
            } else {
                ForEach(segments) { segment in
                    VStack(alignment: .leading, spacing: 8) {
                        Text(segment.displayName ?? "Quarter \(segment.quarter)")
                            .font(.outfit(size: 14, weight: .semibold))
                        Text(segment.players.joined(separator: ", "))
                            .font(.outfit(size: 12))
                            .foregroundStyle(HSToken.inkMuted)
                        HStack(spacing: 16) {
                            Label("\(segment.pointsScored) scored", systemImage: "plus.circle").foregroundStyle(HSToken.win)
                            Label("\(segment.pointsAllowed) allowed", systemImage: "minus.circle").foregroundStyle(HSToken.loss)
                            Label("\(segment.possessions) poss.", systemImage: "arrow.left.arrow.right")
                            Label(segment.netRatingValue.formatted(.number.precision(.fractionLength(1))), systemImage: "chart.line.uptrend.xyaxis").foregroundStyle(HSToken.cool)
                        }
                        .font(.outfit(size: 12, weight: .semibold))
                    }
                    .padding(16)
                    .background(HSCardRow())
                }
            }
        }
    }
}

private struct NotesSection: View {
    let notes: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HSSectionHeader(title: "Coach Notes", icon: "note.text")
            HSCard { Text(notes.isEmpty ? "No notes" : notes).foregroundStyle(HSToken.inkMuted) }
        }
    }
}

/// Cream card row background + border used by list rows.
private struct HSCardRow: View {
    var body: some View {
        RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
            .fill(HSToken.surface)
            .overlay(
                RoundedRectangle(cornerRadius: HSToken.radiusSmall, style: .continuous)
                    .stroke(HSToken.line, lineWidth: 1)
            )
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
