import SwiftUI

struct LiveGameScreen: View {
    @Environment(AppModel.self) private var appModel

    @State private var stage: DraftStage = .setup
    @State private var gameDate = Date.now
    @State private var opponent = ""
    @State private var gameType: GameType = .season
    @State private var availablePlayers: [String] = []
    @State private var selectedRoster: [String] = []
    @State private var selectedStarters: [String] = []
    @State private var draftPlayerName = ""
    @State private var selectedPlayer = ""
    @State private var showSubstitutionSheet = false
    @State private var showStatsSheet = false
    @State private var showPlaySelector = true
    @State private var showShotPosition = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    switch currentStage {
                    case .setup:
                        SetupPanel(
                            gameDate: $gameDate,
                            opponent: $opponent,
                            gameType: $gameType,
                            availablePlayers: availablePlayers,
                            selectedRoster: selectedRoster,
                            draftPlayerName: $draftPlayerName,
                            onToggleRosterPlayer: toggleRosterPlayer,
                            onAddPlayer: addDraftPlayer,
                            onContinue: moveToLineupSelection
                        )
                    case .lineup:
                        LineupSelectionPanel(
                            roster: selectedRoster,
                            selectedStarters: selectedStarters,
                            opponent: opponent,
                            onToggleStarter: toggleStarter,
                            onBack: { stage = .setup },
                            onStart: startLiveGame
                        )
                    case .tracker:
                        TrackerConsole(
                            session: appModel.liveSession,
                            plays: appModel.plays,
                            selectedPlayer: $selectedPlayer,
                            showPlaySelector: $showPlaySelector,
                            showShotPosition: $showShotPosition,
                            onToggleClock: appModel.toggleClock,
                            onAdvanceQuarter: appModel.nextQuarter,
                            onUndo: appModel.undoLiveEvent,
                            onShowSubs: { showSubstitutionSheet = true },
                            onShowStats: { showStatsSheet = true },
                            onComplete: appModel.completeLiveGame,
                            onSelectPlay: appModel.selectPlay,
                            onRecordEvent: recordEvent,
                            onSelectPlayer: { selectedPlayer = $0 }
                        )
                    }
                }
                .padding(24)
            }
            .background(LiveGamePalette.page.ignoresSafeArea())
            .navigationTitle("Live Game")
        }
        .sheet(isPresented: $showSubstitutionSheet) {
            if appModel.liveSession.isConfigured {
                SubstitutionSheet(
                    roster: appModel.liveSession.roster,
                    currentLineup: appModel.liveSession.activeLineup,
                    onConfirm: { lineup in
                        appModel.setLiveLineup(lineup)
                        selectedPlayer = lineup.first ?? ""
                    }
                )
                .presentationDetents([.large])
            }
        }
        .sheet(isPresented: $showStatsSheet) {
            if appModel.liveSession.isConfigured {
                CurrentStatsSheet(session: appModel.liveSession)
                    .presentationDetents([.large])
            }
        }
        .onAppear(perform: bootstrapDraftState)
        .onChange(of: appModel.liveSession) { _, newValue in
            if newValue.isConfigured {
                stage = .tracker
                if selectedPlayer.isEmpty || !newValue.roster.contains(selectedPlayer) {
                    selectedPlayer = newValue.activeLineup.first ?? newValue.roster.first ?? ""
                }
            } else if stage == .tracker {
                resetDraftState()
            }
        }
    }

    private var currentStage: DraftStage {
        appModel.liveSession.isConfigured ? .tracker : stage
    }

    private func bootstrapDraftState() {
        let playersFromGames = appModel.games
            .flatMap(\.allPlayers)
            .sorted()
        let merged = Array(Set(playersFromGames + appModel.liveSession.roster)).sorted()
        if availablePlayers.isEmpty {
            availablePlayers = merged
        } else {
            availablePlayers = Array(Set(availablePlayers + merged)).sorted()
        }

        if appModel.liveSession.isConfigured {
            stage = .tracker
            selectedPlayer = appModel.liveSession.activeLineup.first ?? appModel.liveSession.roster.first ?? ""
            showPlaySelector = true
            showShotPosition = true
        }
    }

    private func resetDraftState() {
        stage = .setup
        opponent = ""
        gameType = .season
        selectedRoster = []
        selectedStarters = []
        draftPlayerName = ""
        selectedPlayer = ""
    }

    private func addDraftPlayer() {
        let trimmed = draftPlayerName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        availablePlayers = Array(Set(availablePlayers + [trimmed])).sorted()
        if !selectedRoster.contains(trimmed) {
            selectedRoster.append(trimmed)
        }
        draftPlayerName = ""
    }

    private func toggleRosterPlayer(_ player: String) {
        if let index = selectedRoster.firstIndex(of: player) {
            selectedRoster.remove(at: index)
            selectedStarters.removeAll { $0 == player }
        } else {
            selectedRoster.append(player)
        }
    }

    private func moveToLineupSelection() {
        let trimmedOpponent = opponent.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedOpponent.isEmpty, selectedRoster.count >= 5 else { return }
        opponent = trimmedOpponent
        if selectedStarters.isEmpty {
            selectedStarters = Array(selectedRoster.prefix(5))
        } else {
            selectedStarters = selectedStarters.filter { selectedRoster.contains($0) }
            if selectedStarters.count < 5 {
                for player in selectedRoster where !selectedStarters.contains(player) {
                    selectedStarters.append(player)
                    if selectedStarters.count == 5 { break }
                }
            }
        }
        stage = .lineup
    }

    private func toggleStarter(_ player: String) {
        if let index = selectedStarters.firstIndex(of: player) {
            selectedStarters.remove(at: index)
        } else if selectedStarters.count < 5 {
            selectedStarters.append(player)
        }
    }

    private func startLiveGame() {
        guard selectedStarters.count == 5 else { return }
        appModel.startNewLiveGame(
            opponent: opponent,
            roster: selectedRoster,
            startingLineup: selectedStarters,
            gameType: gameType
        )
        stage = .tracker
        selectedPlayer = selectedStarters.first ?? selectedRoster.first ?? ""
    }

    private func recordEvent(_ kind: LiveGameEventKind, playerName: String?) {
        let detail = appModel.liveSession.selectedPlayID == nil ? "" : "Tagged from playbook"
        let resolvedPlayer = kind.requiresPlayerTag ? playerName : nil
        appModel.addEvent(kind, playerName: resolvedPlayer, detail: detail)
        if let resolvedPlayer {
            selectedPlayer = resolvedPlayer
        }
    }
}

private enum DraftStage {
    case setup
    case lineup
    case tracker
}

private enum LiveGamePalette {
    static let page = Color(red: 0.94, green: 0.96, blue: 0.98)
    static let card = Color.white
    static let dark = Color(red: 0.10, green: 0.13, blue: 0.18)
    static let blue = Color(red: 0.12, green: 0.38, blue: 0.84)
    static let yellow = Color(red: 0.96, green: 0.75, blue: 0.16)
    static let red = Color(red: 0.82, green: 0.20, blue: 0.22)
    static let green = Color(red: 0.15, green: 0.60, blue: 0.33)
}

private struct SetupPanel: View {
    @Binding var gameDate: Date
    @Binding var opponent: String
    @Binding var gameType: GameType
    let availablePlayers: [String]
    let selectedRoster: [String]
    @Binding var draftPlayerName: String
    let onToggleRosterPlayer: (String) -> Void
    let onAddPlayer: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Game Setup")
                .font(.title2.weight(.bold))
            DatePicker("Date", selection: $gameDate, displayedComponents: .date)
                .datePickerStyle(.compact)
            Picker("Game Type", selection: $gameType) {
                ForEach(GameType.allCases, id: \.self) { type in
                    Text(type.rawValue).tag(type)
                }
            }
            .pickerStyle(.segmented)

            LabeledContent("Opponent") {
                TextField("Enter opponent team name", text: $opponent)
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 360)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Roster Selection")
                    .font(.headline)
                Text("Select players available for this game.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                HStack {
                    TextField("Add new player name", text: $draftPlayerName)
                        .textFieldStyle(.roundedBorder)
                    Button("Add", action: onAddPlayer)
                        .buttonStyle(.bordered)
                }
                SelectableChipGrid(
                    players: availablePlayers,
                    selectedPlayers: selectedRoster,
                    tint: LiveGamePalette.blue,
                    onToggle: onToggleRosterPlayer
                )
            }

            Button("Next: Select Starters", action: onContinue)
                .buttonStyle(.borderedProminent)
                .disabled(opponent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || selectedRoster.count < 5)
        }
        .padding(24)
        .frame(maxWidth: 620, alignment: .leading)
        .background(LiveGamePalette.card, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 18, y: 8)
    }
}

private struct LineupSelectionPanel: View {
    let roster: [String]
    let selectedStarters: [String]
    let opponent: String
    let onToggleStarter: (String) -> Void
    let onBack: () -> Void
    let onStart: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Select Starters (5)")
                .font(.title2.weight(.bold))
            Text("Choose the opening lineup for vs \(opponent).")
                .foregroundStyle(.secondary)
            SelectableChipGrid(
                players: roster,
                selectedPlayers: selectedStarters,
                tint: LiveGamePalette.green,
                onToggle: onToggleStarter
            )
            Text("Selected: \(selectedStarters.count)/5")
                .font(.headline)
            HStack {
                Button("Back", action: onBack)
                    .buttonStyle(.bordered)
                Button("Start Game", action: onStart)
                    .buttonStyle(.borderedProminent)
                    .disabled(selectedStarters.count != 5)
            }
        }
        .padding(24)
        .frame(maxWidth: 620, alignment: .leading)
        .background(LiveGamePalette.card, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 18, y: 8)
    }
}

private struct TrackerConsole: View {
    let session: LiveGameSession
    let plays: [Play]
    @Binding var selectedPlayer: String
    @Binding var showPlaySelector: Bool
    @Binding var showShotPosition: Bool
    let onToggleClock: () -> Void
    let onAdvanceQuarter: () -> Void
    let onUndo: () -> Void
    let onShowSubs: () -> Void
    let onShowStats: () -> Void
    let onComplete: () -> Void
    let onSelectPlay: (UUID?) -> Void
    let onRecordEvent: (LiveGameEventKind, String?) -> Void
    let onSelectPlayer: (String) -> Void

    private let grid = [GridItem(.adaptive(minimum: 300), spacing: 16)]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ScoreboardCard(
                session: session,
                showPlaySelector: $showPlaySelector,
                showShotPosition: $showShotPosition,
                onToggleClock: onToggleClock,
                onAdvanceQuarter: onAdvanceQuarter,
                onUndo: onUndo,
                onShowSubs: onShowSubs,
                onShowStats: onShowStats,
                onComplete: onComplete,
                onOpponentEvent: { onRecordEvent($0, nil) }
            )

            if showPlaySelector {
                PlaySelectorStrip(
                    plays: plays,
                    selectedPlayID: session.selectedPlayID,
                    onSelectPlay: onSelectPlay
                )
            }

            LazyVGrid(columns: grid, spacing: 16) {
                ForEach(session.activeLineup, id: \.self) { player in
                    PlayerActionCard(
                        player: player,
                        summary: LivePlayerSummary(player: player, session: session),
                        isSelected: selectedPlayer == player,
                        shotPositionEnabled: showShotPosition,
                        selectedPlayName: selectedPlayName,
                        onSelectPlayer: {
                            selectedPlayer = player
                            onSelectPlayer(player)
                        },
                        onAction: { kind in
                            selectedPlayer = player
                            onSelectPlayer(player)
                            onRecordEvent(kind, player)
                        }
                    )
                }

                LiveSidePanel(
                    session: session,
                    selectedPlayer: selectedPlayer,
                    selectedPlayName: selectedPlayName,
                    onSelectPlayer: { player in
                        selectedPlayer = player
                        onSelectPlayer(player)
                    }
                )
            }
        }
    }

    private var selectedPlayName: String? {
        guard let selectedPlayID = session.selectedPlayID else { return nil }
        return plays.first(where: { $0.id == selectedPlayID })?.name
    }
}

private struct ScoreboardCard: View {
    let session: LiveGameSession
    @Binding var showPlaySelector: Bool
    @Binding var showShotPosition: Bool
    let onToggleClock: () -> Void
    let onAdvanceQuarter: () -> Void
    let onUndo: () -> Void
    let onShowSubs: () -> Void
    let onShowStats: () -> Void
    let onComplete: () -> Void
    let onOpponentEvent: (LiveGameEventKind) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(session.homeScore) - \(session.awayScore)")
                        .font(.system(size: 40, weight: .bold, design: .rounded))
                        .foregroundStyle(LiveGamePalette.yellow)
                    Text("vs \(session.opponent)")
                        .font(.headline)
                        .foregroundStyle(.white.opacity(0.86))
                }
                Spacer()
                VStack(spacing: 6) {
                    Text(session.isClockRunning ? "LIVE" : "PAUSED")
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(session.isClockRunning ? LiveGamePalette.green : .white.opacity(0.14), in: Capsule())
                    Text("Q\(session.quarter)")
                        .font(.title2.weight(.bold))
                    Text(session.gameType.rawValue)
                        .font(.caption)
                        .foregroundStyle(.white.opacity(0.8))
                }
                .frame(minWidth: 120)
                VStack(alignment: .trailing, spacing: 8) {
                    HStack(spacing: 8) {
                        Button(session.isClockRunning ? "Pause" : "Start", action: onToggleClock)
                            .buttonStyle(TrackerButtonStyle(fill: LiveGamePalette.green))
                        Button("Subs", action: onShowSubs)
                            .buttonStyle(TrackerButtonStyle(fill: .white.opacity(0.16)))
                    }
                    HStack(spacing: 8) {
                        Button("Undo", action: onUndo)
                            .buttonStyle(TrackerButtonStyle(fill: .white.opacity(0.16)))
                            .disabled(session.events.isEmpty)
                        Button("Next Q", action: onAdvanceQuarter)
                            .buttonStyle(TrackerButtonStyle(fill: .white.opacity(0.16)))
                    }
                }
            }

            Divider().overlay(.white.opacity(0.15))

            HStack(alignment: .center, spacing: 16) {
                HStack(spacing: 8) {
                    OpponentActionButton(label: "OPP 2PT", tint: LiveGamePalette.red) {
                        onOpponentEvent(.awayTwoMade)
                    }
                    OpponentActionButton(label: "OPP 3PT", tint: LiveGamePalette.red) {
                        onOpponentEvent(.awayThreeMade)
                    }
                    OpponentActionButton(label: "OPP FT", tint: LiveGamePalette.red) {
                        onOpponentEvent(.awayFreeThrowMade)
                    }
                }

                Spacer()

                HStack(spacing: 10) {
                    TogglePill(title: "Play Selector", isOn: $showPlaySelector)
                    TogglePill(title: "Shot Position", isOn: $showShotPosition)
                    Button("Stats", action: onShowStats)
                        .buttonStyle(TrackerButtonStyle(fill: LiveGamePalette.blue))
                    Button("Finish Game", action: onComplete)
                        .buttonStyle(TrackerButtonStyle(fill: LiveGamePalette.yellow, foreground: .black))
                        .disabled(session.events.isEmpty)
                }
            }
        }
        .padding(20)
        .background(LiveGamePalette.dark, in: RoundedRectangle(cornerRadius: 26, style: .continuous))
        .foregroundStyle(.white)
        .shadow(color: .black.opacity(0.18), radius: 18, y: 10)
    }
}

private struct PlayerActionCard: View {
    let player: String
    let summary: LivePlayerSummary
    let isSelected: Bool
    let shotPositionEnabled: Bool
    let selectedPlayName: String?
    let onSelectPlayer: () -> Void
    let onAction: (LiveGameEventKind) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(player)
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.white)
                    if let selectedPlayName {
                        Text(selectedPlayName)
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(.white.opacity(0.16), in: Capsule())
                    }
                }
                Spacer()
                HStack(spacing: 6) {
                    StatBadge(text: "\(summary.plusMinusSigned)", fill: summary.plusMinusColor)
                    StatBadge(text: "\(summary.points) PTS", fill: .white)
                    StatBadge(text: "\(summary.personalFouls) PF", fill: LiveGamePalette.yellow)
                }
            }

            shootingRow(label: "2PT", value: "\(summary.twoPointMade)/\(summary.twoPointAttempts)", missKind: .homeTwoMissed, makeKind: .homeTwoMade, makeLabel: "+2")
            shootingRow(label: "3PT", value: "\(summary.threePointMade)/\(summary.threePointAttempts)", missKind: .homeThreeMissed, makeKind: .homeThreeMade, makeLabel: "+3")
            shootingRow(label: "FT", value: "\(summary.freeThrowMade)/\(summary.freeThrowAttempts)", missKind: .homeFreeThrowMissed, makeKind: .homeFreeThrowMade, makeLabel: "+1")

            VStack(spacing: 8) {
                statButtonRow(items: [
                    ("OREB", summary.offensiveRebounds, .offensiveRebound, LiveGamePalette.yellow),
                    ("DREB", summary.defensiveRebounds, .rebound, LiveGamePalette.blue),
                    ("AST", summary.assists, .assist, LiveGamePalette.green)
                ])
                statButtonRow(items: [
                    ("STL", summary.steals, .steal, LiveGamePalette.green),
                    ("BLK", summary.blocks, .block, LiveGamePalette.blue),
                    ("TOV", summary.turnovers, .turnover, LiveGamePalette.red)
                ])
                statButtonRow(items: [
                    ("PF", summary.personalFouls, .foul, LiveGamePalette.red)
                ])
            }

            HStack {
                Text(shotPositionEnabled ? "Shot map tagging ON" : "Shot map tagging OFF")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.78))
                Spacer()
                Button(isSelected ? "Current Player" : "Select Player", action: onSelectPlayer)
                    .buttonStyle(TrackerButtonStyle(fill: isSelected ? LiveGamePalette.blue : .white.opacity(0.12)))
            }
        }
        .padding(16)
        .background(
            LinearGradient(
                colors: isSelected
                    ? [LiveGamePalette.blue, Color(red: 0.12, green: 0.24, blue: 0.48)]
                    : [Color(red: 0.16, green: 0.36, blue: 0.78), Color(red: 0.12, green: 0.22, blue: 0.42)],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 22, style: .continuous)
        )
        .shadow(color: .black.opacity(0.12), radius: 14, y: 8)
    }

    private func shootingRow(label: String, value: String, missKind: LiveGameEventKind, makeKind: LiveGameEventKind, makeLabel: String) -> some View {
        HStack(spacing: 10) {
            Text(label)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.white.opacity(0.88))
                .frame(width: 36, alignment: .leading)
            Spacer()
            Text(value)
                .font(.headline.monospacedDigit())
                .foregroundStyle(.white)
            Spacer()
            HStack(spacing: 6) {
                Button("Miss") { onAction(missKind) }
                    .buttonStyle(SmallActionStyle(fill: .white.opacity(0.14)))
                Button(makeLabel) { onAction(makeKind) }
                    .buttonStyle(SmallActionStyle(fill: LiveGamePalette.green))
            }
        }
    }

    private func statButtonRow(items: [(String, Int, LiveGameEventKind, Color)]) -> some View {
        HStack(spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                Button {
                    onAction(item.2)
                } label: {
                    VStack(spacing: 4) {
                        Text(item.0)
                            .font(.caption.weight(.bold))
                        Text("\(item.1)")
                            .font(.headline.monospacedDigit())
                    }
                    .frame(maxWidth: .infinity, minHeight: 58)
                }
                .buttonStyle(SmallActionStyle(fill: item.3))
            }
        }
    }
}

private struct LiveSidePanel: View {
    let session: LiveGameSession
    let selectedPlayer: String
    let selectedPlayName: String?
    let onSelectPlayer: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Bench And Timeline")
                .font(.title3.weight(.bold))
            if !selectedPlayer.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Current Tag")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.secondary)
                    Text(selectedPlayer)
                        .font(.headline)
                    if let selectedPlayName {
                        Text("Play: \(selectedPlayName)")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(14)
                .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Bench")
                    .font(.headline)
                if benchPlayers.isEmpty {
                    Text("No bench players available.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(benchPlayers, id: \.self) { player in
                        Button(action: { onSelectPlayer(player) }) {
                            HStack {
                                Text(player)
                                Spacer()
                                Image(systemName: "person.badge.plus")
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 10)
                        }
                        .buttonStyle(.plain)
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Recent Actions")
                    .font(.headline)
                if session.events.isEmpty {
                    ContentUnavailableView("No Events Yet", systemImage: "clock.arrow.circlepath")
                } else {
                    ForEach(session.events.suffix(8).reversed()) { event in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(event.kind.title)
                                    .font(.subheadline.weight(.semibold))
                                Spacer()
                                Text("#\(event.eventIndex)")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            Text("Q\(event.quarter) • \(event.playerName ?? "Team")")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if !event.detail.isEmpty {
                                Text(event.detail)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(12)
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(LiveGamePalette.card, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 14, y: 8)
    }

    private var benchPlayers: [String] {
        session.roster.filter { !session.activeLineup.contains($0) }
    }
}

private struct PlaySelectorStrip: View {
    let plays: [Play]
    let selectedPlayID: UUID?
    let onSelectPlay: (UUID?) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Play Selector")
                .font(.headline)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    Button("None") { onSelectPlay(nil) }
                        .buttonStyle(PlayChipStyle(isSelected: selectedPlayID == nil))
                    ForEach(plays) { play in
                        Button(play.name) {
                            onSelectPlay(play.id)
                        }
                        .buttonStyle(PlayChipStyle(isSelected: selectedPlayID == play.id))
                    }
                }
            }
        }
        .padding(16)
        .background(LiveGamePalette.card, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .shadow(color: .black.opacity(0.06), radius: 12, y: 6)
    }
}

private struct SubstitutionSheet: View {
    let roster: [String]
    let currentLineup: [String]
    let onConfirm: ([String]) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var selection: [String] = []

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Select exactly 5 players for the lineup.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    SelectableChipGrid(
                        players: roster,
                        selectedPlayers: selection,
                        tint: LiveGamePalette.blue,
                        onToggle: togglePlayer
                    )
                }
                .padding(20)
            }
            .navigationTitle("Substitutions")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Confirm Lineup") {
                        onConfirm(selection)
                        dismiss()
                    }
                    .disabled(selection.count != 5)
                }
            }
        }
        .onAppear {
            selection = currentLineup
        }
    }

    private func togglePlayer(_ player: String) {
        if let index = selection.firstIndex(of: player) {
            selection.remove(at: index)
        } else if selection.count < 5 {
            selection.append(player)
        }
    }
}

private struct CurrentStatsSheet: View {
    let session: LiveGameSession

    private var rows: [LivePlayerSummary] {
        session.roster.map { LivePlayerSummary(player: $0, session: session) }
            .sorted { lhs, rhs in
                if lhs.points == rhs.points { return lhs.player < rhs.player }
                return lhs.points > rhs.points
            }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    ForEach(rows, id: \.player) { row in
                        HStack(spacing: 12) {
                            Text(row.player)
                                .font(.headline)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            statPill("PTS", row.points)
                            statPill("REB", row.totalRebounds)
                            statPill("AST", row.assists)
                            statPill("STL", row.steals)
                            statPill("BLK", row.blocks)
                            statPill("TOV", row.turnovers)
                            statPill("PF", row.personalFouls)
                            Text("\(row.twoPointMade + row.threePointMade)/\(row.twoPointAttempts + row.threePointAttempts) FG")
                                .font(.caption.monospacedDigit())
                                .frame(width: 90)
                        }
                        .padding(14)
                        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    }
                }
                .padding(20)
            }
            .navigationTitle("Current Game Stats")
        }
    }

    private func statPill(_ label: String, _ value: Int) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)
            Text("\(value)")
                .font(.subheadline.monospacedDigit())
        }
        .frame(width: 42)
    }
}

private struct SelectableChipGrid: View {
    let players: [String]
    let selectedPlayers: [String]
    let tint: Color
    let onToggle: (String) -> Void

    private let columns = [GridItem(.adaptive(minimum: 120), spacing: 10)]

    var body: some View {
        LazyVGrid(columns: columns, spacing: 10) {
            ForEach(players, id: \.self) { player in
                let isSelected = selectedPlayers.contains(player)
                Button(player) {
                    onToggle(player)
                }
                .font(.subheadline.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 46)
                .foregroundStyle(isSelected ? .white : .primary)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(isSelected ? tint : Color(.secondarySystemBackground))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(isSelected ? tint : Color(.separator), lineWidth: 1)
                )
            }
        }
    }
}

private struct TogglePill: View {
    let title: String
    @Binding var isOn: Bool

    var body: some View {
        Button {
            isOn.toggle()
        } label: {
            HStack(spacing: 8) {
                Text(title)
                Text(isOn ? "ON" : "OFF")
                    .fontWeight(.bold)
                    .foregroundStyle(isOn ? .green : .gray)
            }
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(.white.opacity(0.12), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

private struct OpponentActionButton: View {
    let label: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(label, action: action)
            .buttonStyle(TrackerButtonStyle(fill: tint))
    }
}

private struct StatBadge: View {
    let text: String
    let fill: Color

    var body: some View {
        Text(text)
            .font(.caption.weight(.bold))
            .foregroundStyle(fill == .white || fill == LiveGamePalette.yellow ? .black : .white)
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(fill, in: Capsule())
    }
}

private struct TrackerButtonStyle: ButtonStyle {
    let fill: Color
    var foreground: Color = .white

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.bold))
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .foregroundStyle(foreground.opacity(configuration.isPressed ? 0.8 : 1))
            .background(fill.opacity(configuration.isPressed ? 0.75 : 1), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct SmallActionStyle: ButtonStyle {
    let fill: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.caption.weight(.bold))
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(minWidth: 56)
            .foregroundStyle(.white)
            .background(fill.opacity(configuration.isPressed ? 0.78 : 1), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

private struct PlayChipStyle: ButtonStyle {
    let isSelected: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.subheadline.weight(.semibold))
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .foregroundStyle(isSelected ? .white : .primary)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(isSelected ? LiveGamePalette.blue : Color(.secondarySystemBackground))
            )
            .opacity(configuration.isPressed ? 0.8 : 1)
    }
}

private struct LivePlayerSummary {
    let player: String
    var points = 0
    var twoPointMade = 0
    var twoPointAttempts = 0
    var threePointMade = 0
    var threePointAttempts = 0
    var freeThrowMade = 0
    var freeThrowAttempts = 0
    var offensiveRebounds = 0
    var defensiveRebounds = 0
    var assists = 0
    var steals = 0
    var blocks = 0
    var turnovers = 0
    var personalFouls = 0
    var plusMinus = 0

    init(player: String, session: LiveGameSession) {
        self.player = player

        for event in session.events where event.playerName == player {
            switch event.kind {
            case .homeTwoMade:
                points += 2
                twoPointMade += 1
                twoPointAttempts += 1
            case .homeTwoMissed:
                twoPointAttempts += 1
            case .homeThreeMade:
                points += 3
                threePointMade += 1
                threePointAttempts += 1
            case .homeThreeMissed:
                threePointAttempts += 1
            case .homeFreeThrowMade:
                points += 1
                freeThrowMade += 1
                freeThrowAttempts += 1
            case .homeFreeThrowMissed:
                freeThrowAttempts += 1
            case .offensiveRebound:
                offensiveRebounds += 1
            case .rebound:
                defensiveRebounds += 1
            case .assist:
                assists += 1
            case .steal:
                steals += 1
            case .block:
                blocks += 1
            case .turnover:
                turnovers += 1
            case .foul:
                personalFouls += 1
            default:
                break
            }
        }

        for segment in session.lineupSegments where segment.players.contains(player) {
            plusMinus += segment.pointsScored - segment.pointsAllowed
        }
    }

    var totalRebounds: Int {
        offensiveRebounds + defensiveRebounds
    }

    var plusMinusSigned: String {
        plusMinus > 0 ? "+\(plusMinus)" : "\(plusMinus)"
    }

    var plusMinusColor: Color {
        if plusMinus > 0 { return LiveGamePalette.green }
        if plusMinus < 0 { return LiveGamePalette.red }
        return Color(.systemGray4)
    }
}

private extension LiveGameEventKind {
    var requiresPlayerTag: Bool {
        switch self {
        case .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed:
            false
        case .substitution:
            false
        default:
            true
        }
    }
}
