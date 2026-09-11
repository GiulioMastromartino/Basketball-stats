import Foundation
import Observation

@MainActor
@Observable
final class AppModel {
    private let services: AppServices
    let webClient = WebAPIClient()

    private(set) var games: [Game] = []
    private(set) var liveSession = LiveGameSession.empty
    private(set) var plays: [Play] = []
    private(set) var playTypes: [PlayType] = []
    private(set) var users: [User] = []
    private(set) var currentUserID: UUID?
    private(set) var settings: [SystemSetting] = []
    private(set) var syncIssues: [SyncIssue] = []
    private(set) var isBootstrapping = false
    private(set) var lastExportURL: URL?
    private(set) var lastReportURL: URL?
    private(set) var generatedReportText = ""
    var selectedGameID: UUID?
    var selectedPlayID: UUID?
    var selectedSidebarItem: SidebarItem = .dashboard
    var errorMessage: String?
    var importResultMessage: String?
    private(set) var isSyncing = false
    private(set) var lastSyncedAt: Date?
    private(set) var syncMessage: String?

    enum ServerStatus: Equatable {
        case checking
        case connected
        case unreachable(String)
    }

    private(set) var serverStatus: ServerStatus = .checking

    init(services: AppServices = .live) {
        self.services = services
    }

    var selectedGame: Game? {
        guard let selectedGameID else { return games.first }
        return games.first(where: { $0.id == selectedGameID })
    }

    var selectedPlay: Play? {
        guard let selectedPlayID else { return plays.first }
        return plays.first(where: { $0.id == selectedPlayID })
    }

    var currentUser: User? {
        guard let currentUserID else { return users.first }
        return users.first(where: { $0.id == currentUserID })
    }

    var dashboardSummary: DashboardSummary {
        DashboardSummary(games: games)
    }

    var teamOverview: TeamOverview {
        services.analytics.teamOverview(for: games)
    }

    var usageSnapshots: [UsageSnapshot] {
        services.analytics.usageSnapshots(for: games)
    }

    var lineupRankings: [LineupRanking] {
        services.lineupAnalytics.lineupRankings(for: games)
    }

    var syncSummary: String {
        services.sync.syncSummary(for: makeBundle())
    }

    func bootstrap() async {
        guard !isBootstrapping else { return }
        isBootstrapping = true
        defer { isBootstrapping = false }

        do {
            let bundle = try await services.persistence.loadBundle()
            apply(bundle: bundle)
        } catch {
            errorMessage = error.localizedDescription
            apply(bundle: SampleData.bundle)
        }
        await refreshServerStatus()
        if case .connected = serverStatus {
            await syncWithServer()
        }
    }

    func refreshServerStatus() async {
        serverStatus = .checking
        do {
            let _: WebTeamOverview = try await webClient.teamOverview()
            serverStatus = .connected
        } catch {
            serverStatus = .unreachable(error.localizedDescription)
        }
    }

    func syncWithServer() async {
        guard !isSyncing else { return }
        isSyncing = true
        defer { isSyncing = false }

        do {
            let pending = games.filter { $0.syncState == .pendingUpload }
            if !pending.isEmpty {
                let pushResult = try await webClient.importRawGames(pending)
                let realErrors = pushResult.errors.filter { !$0.contains("already exists") }
                if !realErrors.isEmpty {
                    syncMessage = realErrors.joined(separator: "\n")
                }
            }

            let payload = try await webClient.syncPayload()
            let syncedGames = services.importExport.games(fromSync: payload.games)
            let serverKeys = Set(syncedGames.map { "\($0.sortDate)-\($0.opponent)" })
            let localOnly = games.filter {
                !serverKeys.contains("\($0.sortDate)-\($0.opponent)")
            }
            games = (syncedGames + localOnly).sorted { $0.date > $1.date }
            plays = services.importExport.plays(fromSync: payload.plays)
            playTypes = services.importExport.playTypes(fromSync: payload.playTypes)
            syncIssues = []
            lastSyncedAt = .now
            if selectedGameID == nil { selectedGameID = games.first?.id }
            saveAll()
        } catch {
            errorMessage = "Sync failed: \(error.localizedDescription)"
        }
    }

    func selectGame(_ gameID: UUID?) {
        selectedGameID = gameID
    }

    func selectPlay(_ playID: UUID?) {
        selectedPlayID = playID
        liveSession.selectPlay(playID)
    }

    func saveAll() {
        let bundle = makeBundle()
        Task {
            do {
                try await services.persistence.saveBundle(bundle)
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    func importGames(from urls: [URL]) {
        Task {
            do {
                let imported = try await services.importExport.importGames(from: urls)
                await MainActor.run {
                    let existingRefs = Set(games.map { "\($0.sortDate)-\($0.opponent)" })
                    let deduped = imported.filter { !existingRefs.contains("\($0.sortDate)-\($0.opponent)") }
                    games = (games + deduped).sorted { $0.date > $1.date }
                    selectedGameID = games.first?.id
                    saveAll()
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    func webImport(from urls: [URL]) {
        Task {
            do {
                let result = try await webClient.importFiles(urls)
                await MainActor.run {
                    var parts: [String] = []
                    if result.successCount > 0 {
                        parts.append("Imported \(result.successCount) game(s) to the server.")
                    }
                    if !result.errors.isEmpty {
                        parts.append(result.errors.joined(separator: "\n"))
                    }
                    importResultMessage = parts.isEmpty ? "Nothing to import." : parts.joined(separator: "\n")
                }
            } catch {
                await MainActor.run {
                    importResultMessage = "Web import failed: \(error.localizedDescription)"
                }
            }
        }
    }

    func exportSelectedGame() {
        guard let game = selectedGame else { return }
        Task {
            do {
                let url = try await services.importExport.exportRawGame(game)
                let reportText = services.reports.summaryText(for: game)
                await MainActor.run {
                    lastExportURL = url
                    generatedReportText = reportText
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    func generateReport(for game: Game) {
        generatedReportText = services.reports.summaryText(for: game)
        Task {
            do {
                let url = try await services.reports.summaryPDF(for: game)
                await MainActor.run {
                    lastReportURL = url
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    func startNewLiveGame(opponent: String, roster: [String], startingLineup: [String], gameType: GameType) {
        liveSession = services.liveGame.startNewGame(opponent: opponent, roster: roster, startingLineup: startingLineup, gameType: gameType)
        saveAll()
    }

    func toggleClock() {
        liveSession.toggleClock()
        saveAll()
    }

    func nextQuarter() {
        liveSession.advanceQuarter()
        saveAll()
    }

    @discardableResult
    func addEvent(_ event: LiveGameEventKind, playerName: String? = nil, detail: String = "", xLocation: Double? = nil, yLocation: Double? = nil) -> UUID? {
        liveSession = services.liveGame.recordEvent(
            in: liveSession,
            kind: event,
            playerName: playerName,
            detail: detail,
            playID: liveSession.selectedPlayID,
            xLocation: xLocation,
            yLocation: yLocation
        )
        saveAll()
        return liveSession.events.last?.id
    }

    func recordFreeThrowTrip(player: String, totalFt: Int, made: Int) {
        liveSession = services.liveGame.recordFreeThrowTrip(
            in: liveSession,
            player: player,
            totalFt: totalFt,
            made: made,
            playID: liveSession.selectedPlayID
        )
        saveAll()
    }

    func removeOpponentAction(eventID: UUID) {
        liveSession = services.liveGame.removeOpponentAction(in: liveSession, eventID: eventID)
        saveAll()
    }

    func attachPlay(_ playID: UUID?, toEventID: UUID) {
        liveSession = services.liveGame.attachPlay(in: liveSession, playID: playID, toEventID: toEventID)
        saveAll()
    }

    func attachOpponentShotLocation(x: Double, y: Double, toEventID: UUID) {
        liveSession = services.liveGame.attachOpponentShotLocation(in: liveSession, x: x, y: y, toEventID: toEventID)
        saveAll()
    }

    func generateHalftimePDF() {
        var session = liveSession
        let game = session.makeCompletedGame()
        Task {
            do {
                let url = try await services.reports.summaryPDF(for: game)
                await MainActor.run {
                    lastReportURL = url
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    func substitutePlayer(outgoing: String, incoming: String) {
        liveSession = services.liveGame.substitute(in: liveSession, outgoing: outgoing, incoming: incoming)
        saveAll()
    }

    func setLiveLineup(_ players: [String]) {
        liveSession.setActiveLineup(players)
        saveAll()
    }

    func undoLiveEvent() {
        liveSession = services.liveGame.undoLastEvent(in: liveSession)
        saveAll()
    }

    func completeLiveGame() {
        let completed = services.liveGame.complete(session: liveSession)
        games.insert(completed, at: 0)
        selectedGameID = completed.id
        liveSession = .empty
        saveAll()
    }

    func updateGame(_ game: Game) {
        guard let index = games.firstIndex(where: { $0.id == game.id }) else { return }
        var updated = game
        updated.updatedAt = .now
        games[index] = updated
        selectedGameID = updated.id
        saveAll()
    }

    func deleteSelectedGame() {
        guard let selectedGameID else { return }
        games.removeAll { $0.id == selectedGameID }
        self.selectedGameID = games.first?.id
        saveAll()
    }

    func playerProgression(for playerName: String) -> [PlayerProgressPoint] {
        services.analytics.playerProgression(for: games, playerName: playerName)
    }

    func blankPlay() -> Play {
        services.playbook.blankPlay()
    }

    func savePlay(_ play: Play) {
        var play = play
        play.updatedAt = .now
        plays = services.playbook.save(play: play, in: plays)
        selectedPlayID = play.id
        saveAll()
    }

    func deleteSelectedPlay() {
        guard let selectedPlayID else { return }
        plays = services.playbook.delete(playID: selectedPlayID, from: plays)
        self.selectedPlayID = plays.first?.id
        saveAll()
    }

    func switchUser(to userID: UUID?) {
        currentUserID = userID
        saveAll()
    }

    func updateSetting(key: String, value: String) {
        if let index = settings.firstIndex(where: { $0.key == key }) {
            settings[index].value = value
            settings[index].updatedAt = .now
        }
        saveAll()
    }

    private func apply(bundle: AppDataBundle) {
        games = bundle.games.sorted { $0.date > $1.date }
        liveSession = bundle.liveSession
        plays = bundle.plays.sorted { $0.updatedAt > $1.updatedAt }
        playTypes = bundle.playTypes.sorted { $0.name < $1.name }
        users = bundle.users.sorted { $0.username < $1.username }
        currentUserID = bundle.currentUserID ?? bundle.users.first?.id
        settings = bundle.systemSettings.sorted { $0.key < $1.key }
        syncIssues = bundle.syncIssues
        selectedGameID = games.first?.id
        selectedPlayID = plays.first?.id
    }

    private func makeBundle() -> AppDataBundle {
        AppDataBundle(
            games: games,
            liveSession: liveSession,
            plays: plays,
            playTypes: playTypes,
            users: users,
            currentUserID: currentUserID,
            systemSettings: settings,
            syncIssues: syncIssues
        )
    }
}

enum SidebarItem: String, CaseIterable, Hashable, Identifiable {
    case dashboard
    case games
    case liveGame
    case players
    case lineups
    case analytics
    case advanced
    case playbook
    case glossary
    case gm
    case admin
    case reports
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .dashboard: "Dashboard"
        case .games: "Games"
        case .liveGame: "Live Game"
        case .players: "Players"
        case .lineups: "Lineups"
        case .analytics: "Analytics"
        case .advanced: "Advanced"
        case .playbook: "Plays"
        case .glossary: "Glossary"
        case .gm: "GM Dashboard"
        case .admin: "Admin Panel"
        case .reports: "Reports"
        case .settings: "Settings"
        }
    }

    var systemImage: String {
        switch self {
        case .dashboard: HSIcon.dashboard
        case .games: HSIcon.games
        case .liveGame: HSIcon.liveGame
        case .players: HSIcon.players
        case .lineups: HSIcon.lineups
        case .analytics: HSIcon.analytics
        case .advanced: HSIcon.advanced
        case .playbook: HSIcon.plays
        case .glossary: HSIcon.glossary
        case .gm: HSIcon.gm
        case .admin: HSIcon.admin
        case .reports: HSIcon.report
        case .settings: "gearshape"
        }
    }
}
