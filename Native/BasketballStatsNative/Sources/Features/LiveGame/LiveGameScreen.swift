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
    @State private var pendingSheet: PendingSheet?
    @State private var pendingDialog: PendingDialog?
    @State private var recentPlayIDs: [UUID] = []

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
                            recentPlayIDs: recentPlayIDs,
                            onToggleClock: appModel.toggleClock,
                            onAdvanceQuarter: advanceQuarter,
                            onUndo: appModel.undoLiveEvent,
                            onShowSubs: showSubs,
                            onShowStats: { showStatsSheet = true },
                            onComplete: { pendingDialog = .finishGame },
                            onOppShot: { pendingDialog = .oppShot(kind: $0) },
                            onRemoveOppAction: { pendingSheet = .removeOppAction },
                            onSelectPlay: appModel.selectPlay,
                            onShootingAction: shootingAction,
                            onStatAction: statAction,
                            onFT: { pendingSheet = .ftTrip(player: $0) },
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
        .sheet(item: $pendingSheet) { action in
            sheetContent(for: action)
        }
        .confirmationDialog(dialogTitle, isPresented: dialogIsPresented, titleVisibility: .visible) {
            dialogButtons
        } message: {
            Text(dialogMessage)
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

    // MARK: - Sheets & dialogs

    @ViewBuilder
    private func sheetContent(for action: PendingSheet) -> some View {
        switch action {
        case .assistPicker(let shooter, let kind, let points):
            PlayerPickerSheet(
                title: "Assist?",
                subtitle: "\(shooter) \(points)PT MADE",
                tag: "AST",
                players: appModel.liveSession.activeLineup.filter { $0 != shooter },
                skipOption: (label: "No Assist", subtitle: "Unassisted", tag: "SKIP"),
                onPick: { assister in
                    pickAssister(shooter: shooter, kind: kind, points: points, assister: assister)
                }
            )
            .presentationDetents([.medium, .large])
        case .shotLocation(let player, let kind, let points, let assister, _):
            NavigationStack {
                ShotLocationPicker(
                    title: kind.isMiss ? "\(player) \(kind.ptsLabel) MISS" : "\(player) (\(points)PT) MADE",
                    shotType: kind.shotType
                ) { x, y in
                    recordShot(player: player, kind: kind, points: points, assister: assister, xLocation: x, yLocation: y)
                } onSkip: {
                    recordShot(player: player, kind: kind, points: points, assister: assister, xLocation: nil, yLocation: nil)
                }
                .frame(maxWidth: 560)
            }
            .presentationDetents([.medium, .large])
        case .playSelection(let eventID, _):
            PlaySelectionSheet(
                plays: appModel.plays,
                recentPlayIDs: recentPlayIDs,
                selectedPlayID: appModel.liveSession.selectedPlayID,
                onSelect: finishPlaySelection,
                onSkip: skipPlaySelection
            )
            .presentationDetents([.medium, .large])
        case .orebPicker(let shooter, let kind):
            PlayerPickerSheet(
                title: "Offensive Rebound?",
                subtitle: shooter.isEmpty ? "\(kind.title) — defensive possession" : "\(shooter) \(kind.ptsLabel) MISS",
                tag: "OREB",
                players: appModel.liveSession.activeLineup,
                skipOption: (label: "No O-Reb", subtitle: "Defensive possession change", tag: "DEF"),
                onPick: { rebounder in
                    guard let rebounder else { return }
                    appModel.addEvent(.offensiveRebound, playerName: rebounder)
                }
            )
            .presentationDetents([.medium, .large])
        case .ftTrip(let player):
            FTSheet(player: player) { totalFt, made in
                recordFT(player: player, totalFt: totalFt, made: made)
            }
            .presentationDetents([.medium, .large])
        case .oppShotLocation(let kind, let eventID):
            NavigationStack {
                ShotLocationPicker(
                    title: "OPP \(kind.ptsLabel) MADE (\(kind.pointsValue)PT)",
                    shotType: kind.shotType
                ) { x, y in
                    appModel.attachOpponentShotLocation(x: x, y: y, toEventID: eventID)
                } onSkip: {}
                .frame(maxWidth: 560)
            }
            .presentationDetents([.medium, .large])
        case .drebPlayer:
            PlayerPickerSheet(
                title: "Defensive Rebound",
                subtitle: "Who grabbed the rebound?",
                tag: "DREB",
                players: appModel.liveSession.activeLineup,
                skipOption: (label: "Team", subtitle: "Unknown rebounder", tag: "TEAM"),
                onPick: { player in
                    guard let player else { return }
                    appModel.addEvent(.rebound, playerName: player)
                }
            )
            .presentationDetents([.medium, .large])
        case .removeOppAction:
            RemoveOppActionSheet(
                actions: appModel.liveSession.oppRecentActions,
                onRemove: { eventID in
                    appModel.removeOpponentAction(eventID: eventID)
                    pendingSheet = nil
                }
            )
            .presentationDetents([.medium, .large])
        }
    }

    private var dialogIsPresented: Binding<Bool> {
        Binding(
            get: { pendingDialog != nil },
            set: { if !$0 { pendingDialog = nil } }
        )
    }

    private var dialogTitle: String {
        guard let pendingDialog else { return "" }
        switch pendingDialog {
        case .oppShot(let kind): return "Opponent \(kind.ptsLabel)"
        case .oppRebound: return "Rebound?"
        case .finishGame: return "Finish Game"
        case .halftimePDF: return "End of Q2"
        }
    }

    private var dialogMessage: String {
        guard let pendingDialog else { return "" }
        switch pendingDialog {
        case .oppShot: return "Did the opponent make the shot?"
        case .oppRebound: return "Who got the rebound?"
        case .finishGame: return "Are you sure you want to finish and save the game against \(appModel.liveSession.opponent)?"
        case .halftimePDF: return "Generate a Half-Time Summary PDF?"
        }
    }

    @ViewBuilder
    private var dialogButtons: some View {
        switch pendingDialog {
        case .oppShot(let kind):
            Button("Made") { oppShotMade(kind) }
            Button("Missed") { oppShotMissed(kind) }
            Button("Cancel", role: .cancel) { pendingDialog = nil }
        case .oppRebound(let kind):
            Button("Offensive (Opp kept it)") { oppReboundOffensive() }
            Button("Defensive (We rebounded)") { pendingSheet = .drebPlayer }
            Button("Cancel", role: .cancel) { pendingDialog = nil }
        case .finishGame:
            Button("Finish and Save") {
                appModel.completeLiveGame()
                resetDraftState()
            }
            Button("Cancel", role: .cancel) { pendingDialog = nil }
        case .halftimePDF:
            Button("Generate PDF") {
                appModel.generateHalftimePDF()
                appModel.nextQuarter()
            }
            Button("Skip") {
                appModel.nextQuarter()
            }
            Button("Cancel", role: .cancel) { pendingDialog = nil }
        case nil:
            EmptyView()
        }
    }

    // MARK: - Draft flow

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
        pendingSheet = nil
        pendingDialog = nil
        recentPlayIDs = []
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

    private func showSubs() {
        if appModel.liveSession.isClockRunning {
            appModel.toggleClock()
        }
        showSubstitutionSheet = true
    }

    private func advanceQuarter() {
        if appModel.liveSession.quarter == 2 {
            pendingDialog = .halftimePDF
        } else {
            appModel.nextQuarter()
        }
    }

    // MARK: - Action chains

    private func statAction(_ kind: LiveGameEventKind, player: String) {
        if kind == .turnover {
            let eventID = appModel.addEvent(.turnover, playerName: player)
            if showPlaySelector, let eventID {
                pendingSheet = .playSelection(eventID: eventID, nextAfter: nil)
            }
            return
        }
        appModel.addEvent(kind, playerName: player)
    }

    private func shootingAction(_ kind: LiveGameEventKind, player: String) {
        if kind.isMiss {
            missedShot(player, kind)
        } else {
            madeShot(player, kind, kind.pointsValue)
        }
    }

    private func madeShot(_ player: String, _ kind: LiveGameEventKind, _ points: Int) {
        pendingSheet = .assistPicker(shooter: player, kind: kind, points: points)
    }

    private func missedShot(_ player: String, _ kind: LiveGameEventKind) {
        if showShotPosition {
            pendingSheet = .shotLocation(player: player, kind: kind, points: 0, assister: nil, isMiss: true)
        } else {
            recordShot(player: player, kind: kind, points: 0, assister: nil, xLocation: nil, yLocation: nil)
        }
    }

    private func pickAssister(shooter: String, kind: LiveGameEventKind, points: Int, assister: String?) {
        if showShotPosition {
            pendingSheet = .shotLocation(player: shooter, kind: kind, points: points, assister: assister, isMiss: false)
        } else {
            recordShot(player: shooter, kind: kind, points: points, assister: assister, xLocation: nil, yLocation: nil)
        }
    }

    private func recordShot(player: String, kind: LiveGameEventKind, points: Int, assister: String?, xLocation: Double?, yLocation: Double?) {
        if let assister, !assister.isEmpty {
            appModel.addEvent(.assist, playerName: assister)
        }
        let eventID = appModel.addEvent(kind, playerName: player, xLocation: xLocation, yLocation: yLocation)
        var nextAfter: PendingSheet?
        if kind.isMiss {
            nextAfter = .orebPicker(shooter: player, kind: kind)
        }
        if showPlaySelector, let eventID {
            pendingSheet = .playSelection(eventID: eventID, nextAfter: nextAfter)
        } else {
            pendingSheet = nextAfter
        }
    }

    private func finishPlaySelection(playID: UUID?) {
        guard case let .playSelection(eventID, nextAfter)? = pendingSheet else { return }
        appModel.attachPlay(playID, toEventID: eventID)
        if let playID {
            recentPlayIDs.removeAll { $0 == playID }
            recentPlayIDs.insert(playID, at: 0)
            if recentPlayIDs.count > 3 { recentPlayIDs.removeLast() }
        }
        pendingSheet = nextAfter
    }

    private func skipPlaySelection() {
        finishPlaySelection(playID: nil)
    }

    private func recordFT(player: String, totalFt: Int, made: Int) {
        appModel.recordFreeThrowTrip(player: player, totalFt: totalFt, made: made)
        let eventID = appModel.liveSession.events.last?.id
        if showPlaySelector, let eventID {
            pendingSheet = .playSelection(eventID: eventID, nextAfter: nil)
        }
    }

    private func oppShotMade(_ kind: LiveGameEventKind) {
        let eventID = appModel.addEvent(kind, playerName: nil)
        guard kind != .awayFreeThrowMade, let eventID else { return }
        pendingSheet = .oppShotLocation(kind: kind, eventID: eventID)
    }

    private func oppShotMissed(_ kind: LiveGameEventKind) {
        appModel.addEvent(kind, playerName: nil)
        pendingDialog = .oppRebound(kind: kind)
    }

    private func oppReboundOffensive() {
        appModel.addEvent(.opponentOffensiveRebound, playerName: nil)
    }
}

private enum DraftStage {
    case setup
    case lineup
    case tracker
}

private indirect enum PendingSheet: Identifiable {
    case assistPicker(shooter: String, kind: LiveGameEventKind, points: Int)
    case shotLocation(player: String, kind: LiveGameEventKind, points: Int, assister: String?, isMiss: Bool)
    case playSelection(eventID: UUID, nextAfter: PendingSheet?)
    case orebPicker(shooter: String, kind: LiveGameEventKind)
    case ftTrip(player: String)
    case oppShotLocation(kind: LiveGameEventKind, eventID: UUID)
    case drebPlayer
    case removeOppAction

    var id: String {
        switch self {
        case .assistPicker(let shooter, let kind, _): "assist-\(shooter)-\(kind.rawValue)"
        case .shotLocation(let player, let kind, _, _, _): "shotloc-\(player)-\(kind.rawValue)"
        case .playSelection(let eventID, _): "play-\(eventID.uuidString)"
        case .orebPicker(let shooter, _): "oreb-\(shooter)"
        case .ftTrip(let player): "ft-\(player)"
        case .oppShotLocation(_, let eventID): "opploc-\(eventID.uuidString)"
        case .drebPlayer: "dreb"
        case .removeOppAction: "removeopp"
        }
    }
}

private enum PendingDialog: Identifiable {
    case oppShot(kind: LiveGameEventKind)
    case oppRebound(kind: LiveGameEventKind)
    case finishGame
    case halftimePDF

    var id: String {
        switch self {
        case .oppShot(let kind): "oppshot-\(kind.rawValue)"
        case .oppRebound(let kind): "oppreb-\(kind.rawValue)"
        case .finishGame: "finish"
        case .halftimePDF: "halftime"
        }
    }
}

private enum LiveGamePalette {
    static let page = HSToken.bgMain
    static let card = HSToken.surface
    static let dark = Color(hex: 0x1A2029)
    static let blue = HSToken.accent
    static let yellow = HSToken.gold
    static let red = HSToken.loss
    static let green = HSToken.win
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
                .font(.bebas(size: 28))
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
                .font(.bebas(size: 28))
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
    let recentPlayIDs: [UUID]
    let onToggleClock: () -> Void
    let onAdvanceQuarter: () -> Void
    let onUndo: () -> Void
    let onShowSubs: () -> Void
    let onShowStats: () -> Void
    let onComplete: () -> Void
    let onOppShot: (LiveGameEventKind) -> Void
    let onRemoveOppAction: () -> Void
    let onSelectPlay: (UUID?) -> Void
    let onShootingAction: (LiveGameEventKind, String) -> Void
    let onStatAction: (LiveGameEventKind, String) -> Void
    let onFT: (String) -> Void
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
                onOppShot: onOppShot,
                onRemoveOppAction: onRemoveOppAction
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
                        session: session,
                        summary: LivePlayerSummary(player: player, session: session),
                        isSelected: selectedPlayer == player,
                        selectedPlayName: selectedPlayName,
                        onSelectPlayer: {
                            selectedPlayer = player
                            onSelectPlayer(player)
                        },
                        onShootingAction: { kind in
                            selectedPlayer = player
                            onSelectPlayer(player)
                            onShootingAction(kind, player)
                        },
                        onStatAction: { kind in
                            selectedPlayer = player
                            onSelectPlayer(player)
                            onStatAction(kind, player)
                        },
                        onFT: {
                            selectedPlayer = player
                            onSelectPlayer(player)
                            onFT(player)
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
    let onOppShot: (LiveGameEventKind) -> Void
    let onRemoveOppAction: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(session.homeScore) - \(session.awayScore)")
                        .font(.bebas(size: 44))
                        .foregroundStyle(LiveGamePalette.yellow)
                    Text("vs \(session.opponent)")
                        .font(.headline)
                        .foregroundStyle(.white.opacity(0.86))
                    TimelineView(.periodic(from: .now, by: 1)) { context in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Q Clock \(LiveGameSession.clockString(seconds: session.displayedQuarterSeconds(at: context.date))) / 10:00")
                            Text("Game \(LiveGameSession.clockString(seconds: session.displayedGameSeconds(at: context.date)))")
                        }
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.white.opacity(0.7))
                    }
                }
                Spacer()
                VStack(spacing: 6) {
                    Text(session.isClockRunning ? "LIVE" : "PAUSED")
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(session.isClockRunning ? LiveGamePalette.green : .white.opacity(0.14), in: Capsule())
                    Text("Q\(session.quarter)")
                        .font(.bebas(size: 26))
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
                        Button("Undo Opp", action: onRemoveOppAction)
                            .buttonStyle(TrackerButtonStyle(fill: .white.opacity(0.16)))
                            .disabled(session.oppRecentActions.isEmpty)
                    }
                }
            }

            Divider().overlay(.white.opacity(0.15))

            HStack(alignment: .center, spacing: 16) {
                HStack(spacing: 8) {
                    OpponentActionButton(label: "OPP 2PT", tint: LiveGamePalette.red) {
                        onOppShot(.awayTwoMade)
                    }
                    OpponentActionButton(label: "OPP 3PT", tint: LiveGamePalette.red) {
                        onOppShot(.awayThreeMade)
                    }
                    OpponentActionButton(label: "OPP FT", tint: LiveGamePalette.red) {
                        onOppShot(.awayFreeThrowMade)
                    }
                }

                Spacer()

                HStack(spacing: 10) {
                    TogglePill(title: "Play Selector", isOn: $showPlaySelector)
                    TogglePill(title: "Shot Position", isOn: $showShotPosition)
                    Button("Stats", action: onShowStats)
                        .buttonStyle(TrackerButtonStyle(fill: LiveGamePalette.blue))
                    Button("Next Q", action: onAdvanceQuarter)
                        .buttonStyle(TrackerButtonStyle(fill: .white.opacity(0.16)))
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
    let session: LiveGameSession
    let summary: LivePlayerSummary
    let isSelected: Bool
    let selectedPlayName: String?
    let onSelectPlayer: () -> Void
    let onShootingAction: (LiveGameEventKind) -> Void
    let onStatAction: (LiveGameEventKind) -> Void
    let onFT: () -> Void

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

            HStack(spacing: 10) {
                Text("FT")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.white.opacity(0.88))
                    .frame(width: 36, alignment: .leading)
                Spacer()
                Text("\(summary.freeThrowMade)/\(summary.freeThrowAttempts)")
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(.white)
                Spacer()
                Button("FT", action: onFT)
                    .buttonStyle(SmallActionStyle(fill: LiveGamePalette.yellow))
            }

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

            TimelineView(.periodic(from: .now, by: 1)) { context in
                HStack {
                    Text("TOTAL: \(LiveGameSession.clockString(seconds: session.displayedSeconds(for: player, at: context.date)))")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.white.opacity(0.78))
                    Spacer()
                    Button(isSelected ? "Current Player" : "Select Player", action: onSelectPlayer)
                        .buttonStyle(TrackerButtonStyle(fill: isSelected ? LiveGamePalette.blue : .white.opacity(0.12)))
                }
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
                Button("Miss") { onShootingAction(missKind) }
                    .buttonStyle(SmallActionStyle(fill: .white.opacity(0.14)))
                Button(makeLabel) { onShootingAction(makeKind) }
                    .buttonStyle(SmallActionStyle(fill: LiveGamePalette.green))
            }
        }
    }

    private func statButtonRow(items: [(String, Int, LiveGameEventKind, Color)]) -> some View {
        HStack(spacing: 8) {
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                Button {
                    onStatAction(item.2)
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
                .background(Color.hsSecondarySystemBackground, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
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
                        .background(Color.hsSecondarySystemBackground, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
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
                        .background(Color.hsSecondarySystemBackground, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
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

// MARK: - Popup sheets

private struct PlayerPickerSheet: View {
    let title: String
    let subtitle: String
    let tag: String
    let players: [String]
    let skipOption: (label: String, subtitle: String, tag: String)?
    let onPick: (String?) -> Void

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    Text(subtitle)
                        .font(.subheadline.weight(.bold))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.bottom, 4)
                    if let skipOption {
                        OptionRow(
                            label: skipOption.label,
                            subtitle: skipOption.subtitle,
                            tag: skipOption.tag,
                            tint: Color.hsSecondarySystemBackground
                        ) {
                            dismiss()
                            onPick(nil)
                        }
                    }
                    ForEach(players, id: \.self) { player in
                        OptionRow(
                            label: player,
                            subtitle: "\(tag) recorded",
                            tag: tag,
                            tint: LiveGamePalette.blue
                        ) {
                            dismiss()
                            onPick(player)
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle(title)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}

private struct OptionRow: View {
    let label: String
    let subtitle: String
    let tag: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(label)
                        .font(.headline)
                        .foregroundStyle(.primary)
                    Text(subtitle)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text(tag)
                    .font(.caption2.weight(.bold))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(tint, in: Capsule())
            }
            .padding(14)
            .background(Color.hsSecondarySystemBackground, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(tint, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct FTSheet: View {
    let player: String
    let onConfirm: (Int, Int) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var totalFt = 2
    @State private var made = 0

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text("\(player)")
                    .font(.title2.weight(.bold))

                VStack(alignment: .leading, spacing: 8) {
                    Text("Free Throw Attempts")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.secondary)
                    Picker("Attempts", selection: $totalFt) {
                        Text("2 Attempts").tag(2)
                        Text("3 Attempts").tag(3)
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: totalFt) { _, newValue in
                        if made > newValue { made = newValue }
                    }
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Made")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(.secondary)
                    HStack(spacing: 10) {
                        ForEach(0...totalFt, id: \.self) { n in
                            Button("\(n)") { made = n }
                                .buttonStyle(
                                    FTCountStyle(isSelected: made == n)
                                )
                        }
                    }
                }

                Text("\(made)/\(totalFt) made • +\(made) points")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            .padding(24)
            .frame(maxWidth: 420)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Confirm") {
                        dismiss()
                        onConfirm(totalFt, made)
                    }
                }
            }
        }
    }
}

private struct FTCountStyle: ButtonStyle {
    let isSelected: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.title3.weight(.bold))
            .frame(minWidth: 56, minHeight: 48)
            .foregroundStyle(isSelected ? .white : .primary)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(isSelected ? LiveGamePalette.blue : Color.hsSecondarySystemBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(isSelected ? LiveGamePalette.blue : Color.hsSeparator, lineWidth: 1)
            )
    }
}

private struct PlaySelectionSheet: View {
    let plays: [Play]
    let recentPlayIDs: [UUID]
    let selectedPlayID: UUID?
    let onSelect: (UUID?) -> Void
    let onSkip: () -> Void

    @State private var showSpecial = false

    private let columns = [GridItem(.adaptive(minimum: 150), spacing: 10)]

    private var filteredPlays: [Play] {
        plays.filter { $0.playType == (showSpecial ? "Special" : "Offense") }
    }

    private var recentPlays: [Play] {
        recentPlayIDs.compactMap { id in plays.first { $0.id == id } }
    }

    private struct PlayGroup: Identifiable {
        let name: String
        let plays: [Play]
        var id: String { name }
    }

    private var grouped: [PlayGroup] {
        var map: [String: [Play]] = [:]
        for play in filteredPlays {
            let parts = play.name.split(separator: "-")
            let macro = parts.count > 1 ? String(parts[0]).trimmingCharacters(in: .whitespaces) : play.name
            map[macro, default: []].append(play)
        }
        return map.keys.sorted().map { PlayGroup(name: $0, plays: map[$0] ?? []) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    if !showSpecial, !recentPlays.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("RECENT")
                                .font(.caption.weight(.bold))
                                .foregroundStyle(.secondary)
                            LazyVGrid(columns: columns, spacing: 10) {
                                ForEach(recentPlays) { play in
                                    PlayCard(play: play, isMacro: false, isRecent: true, isSelected: play.id == selectedPlayID) {
                                        onSelect(play.id)
                                    }
                                }
                            }
                        }
                    }

                    if !showSpecial, !recentPlays.isEmpty {
                        Divider()
                    }

                    ForEach(grouped) { group in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                Text(group.name)
                                    .font(.headline)
                                if group.plays.count > 1 {
                                    Text("Group")
                                        .font(.caption2.weight(.bold))
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.hsSecondarySystemBackground, in: Capsule())
                                }
                            }
                            LazyVGrid(columns: columns, spacing: 10) {
                                ForEach(group.plays) { play in
                                    PlayCard(play: play, isMacro: group.plays.count > 1, isRecent: false, isSelected: play.id == selectedPlayID) {
                                        onSelect(play.id)
                                    }
                                }
                            }
                        }
                    }

                    if filteredPlays.isEmpty {
                        Text("No \(showSpecial ? "Special" : "Offense") plays found")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 24)
                    }
                }
                .padding(16)
            }
            .navigationTitle("Select Play")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Skip") { onSkip() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(showSpecial ? "Hide Special" : "Show Special") {
                        showSpecial.toggle()
                    }
                }
            }
        }
    }
}

private struct PlayCard: View {
    let play: Play
    let isMacro: Bool
    let isRecent: Bool
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 6) {
                Text(play.name)
                    .font(.subheadline.weight(.bold))
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .frame(minHeight: 36)
                HStack(spacing: 4) {
                    if isMacro {
                        Image(systemName: "layer.3d")
                            .font(.caption2)
                    }
                    if isRecent {
                        Image(systemName: "star.fill")
                            .font(.caption2)
                            .foregroundStyle(LiveGamePalette.yellow)
                    }
                    if isSelected {
                        Text("SELECTED")
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(.white)
                    }
                }
            }
            .frame(maxWidth: .infinity, minHeight: 66)
            .foregroundStyle(isSelected ? .white : .primary)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(isSelected ? LiveGamePalette.blue : Color.hsSecondarySystemBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(isSelected ? LiveGamePalette.blue : Color.hsSeparator, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct RemoveOppActionSheet: View {
    let actions: [OpponentAction]
    let onRemove: (UUID) -> Void

    @Environment(\.dismiss) private var dismiss

    private var recent: [OpponentAction] {
        Array(actions.suffix(3).reversed())
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    if recent.isEmpty {
                        Text("No recent opponent actions to remove.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 24)
                    } else {
                        ForEach(recent) { action in
                            Button {
                                onRemove(action.eventID)
                                dismiss()
                            } label: {
                                HStack(spacing: 12) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(action.label)
                                            .font(.headline)
                                            .foregroundStyle(.primary)
                                        Text(action.subtitle)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text("REMOVE")
                                        .font(.caption2.weight(.bold))
                                        .padding(.horizontal, 8)
                                        .padding(.vertical, 4)
                                        .background(LiveGamePalette.red, in: Capsule())
                                        .foregroundStyle(.white)
                                }
                                .padding(14)
                                .background(Color.hsSecondarySystemBackground, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle("Remove Opp. Action")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Existing sheets

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
                            statPill("MIN", row.displayMinutes)
                            statPill("PTS", "\(row.points)")
                            statPill("REB", "\(row.totalRebounds)")
                            statPill("AST", "\(row.assists)")
                            statPill("STL", "\(row.steals)")
                            statPill("BLK", "\(row.blocks)")
                            statPill("TOV", "\(row.turnovers)")
                            statPill("PF", "\(row.personalFouls)")
                            Text("\(row.twoPointMade + row.threePointMade)/\(row.twoPointAttempts + row.threePointAttempts) FG")
                                .font(.caption.monospacedDigit())
                                .frame(width: 90)
                        }
                        .padding(14)
                        .background(Color.hsSecondarySystemBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    }
                }
                .padding(20)
            }
            .navigationTitle("Current Game Stats")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }

    @Environment(\.dismiss) private var dismiss

    private func statPill(_ label: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.caption2.weight(.bold))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.subheadline.monospacedDigit())
        }
        .frame(width: 44)
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
                        .fill(isSelected ? tint : Color.hsSecondarySystemBackground)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(isSelected ? tint : Color.hsSeparator, lineWidth: 1)
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
                    .fill(isSelected ? LiveGamePalette.blue : Color.hsSecondarySystemBackground)
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
    var displayMinutes = "0:00"

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
            case .freeThrowTrip:
                let parts = event.detail.split(separator: "/")
                let made = Int(parts.first ?? "") ?? 0
                let total = Int((parts.last ?? "").trimmingCharacters(in: CharacterSet(charactersIn: " FT"))) ?? 0
                points += made
                freeThrowMade += made
                freeThrowAttempts += total
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

        displayMinutes = LiveGameSession.clockString(seconds: session.displayedSeconds(for: player, at: .now))
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
        return Color.hsSystemGray4
    }
}

private extension OpponentAction {
    var label: String {
        if kind.isScoringEvent {
            return "OPP \(kind.pointsValue)PT \(result.rawValue.uppercased())"
        }
        if kind == .opponentOffensiveRebound {
            return "OPP OREB"
        }
        return kind.title
    }

    var subtitle: String {
        if kind.isScoringEvent, result == .made {
            return "Subtract \(points) points"
        }
        if kind == .opponentOffensiveRebound {
            return "Remove offensive rebound"
        }
        return "Remove event"
    }
}

private extension LiveGameEventKind {
    var isMiss: Bool {
        switch self {
        case .homeTwoMissed, .homeThreeMissed, .homeFreeThrowMissed, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed:
            true
        default:
            false
        }
    }

    var ptsLabel: String {
        switch self {
        case .homeThreeMade, .homeThreeMissed, .awayThreeMade, .awayThreeMissed:
            "3PT"
        case .homeFreeThrowMade, .homeFreeThrowMissed, .awayFreeThrowMade, .awayFreeThrowMissed:
            "FT"
        default:
            "2PT"
        }
    }

    var shotType: ShotType {
        switch self {
        case .homeThreeMade, .homeThreeMissed, .awayThreeMade, .awayThreeMissed:
            .threePoint
        case .homeFreeThrowMade, .homeFreeThrowMissed, .awayFreeThrowMade, .awayFreeThrowMissed:
            .freeThrow
        default:
            .twoPoint
        }
    }

    var requiresPlayerTag: Bool {
        switch self {
        case .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed, .opponentOffensiveRebound:
            false
        case .substitution, .freeThrowTrip:
            false
        default:
            true
        }
    }
}
