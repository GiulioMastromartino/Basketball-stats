import Foundation

protocol PersistenceService: Sendable {
    func loadBundle() async throws -> AppDataBundle
    func saveBundle(_ bundle: AppDataBundle) async throws
}

protocol ImportExportService: Sendable {
    func importGames(from urls: [URL]) async throws -> [Game]
    func exportRawGame(_ game: Game) async throws -> URL
}

protocol LiveGameService: Sendable {
    func startNewGame(opponent: String, roster: [String], startingLineup: [String], gameType: GameType) -> LiveGameSession
    func recordEvent(in session: LiveGameSession, kind: LiveGameEventKind, playerName: String?, detail: String, playID: UUID?) -> LiveGameSession
    func substitute(in session: LiveGameSession, outgoing: String, incoming: String) -> LiveGameSession
    func undoLastEvent(in session: LiveGameSession) -> LiveGameSession
    func complete(session: LiveGameSession) -> Game
}

protocol AnalyticsService: Sendable {
    func teamOverview(for games: [Game]) -> TeamOverview
    func playerProgression(for games: [Game], playerName: String) -> [PlayerProgressPoint]
    func usageSnapshots(for games: [Game]) -> [UsageSnapshot]
}

protocol LineupAnalyticsService: Sendable {
    func lineupRankings(for games: [Game]) -> [LineupRanking]
}

protocol PlaybookService: Sendable {
    func blankPlay() -> Play
    func save(play: Play, in plays: [Play]) -> [Play]
    func delete(playID: UUID, from plays: [Play]) -> [Play]
}

protocol ReportService: Sendable {
    func summaryText(for game: Game) -> String
    func summaryPDF(for game: Game) async throws -> URL
}

protocol AuthService: Sendable {
    func defaultUsers() -> [User]
}

protocol SyncService: Sendable {
    func syncSummary(for bundle: AppDataBundle) -> String
}

struct AppServices: Sendable {
    let persistence: PersistenceService
    let importExport: ImportExportService
    let liveGame: LiveGameService
    let analytics: AnalyticsService
    let lineupAnalytics: LineupAnalyticsService
    let playbook: PlaybookService
    let reports: ReportService
    let auth: AuthService
    let sync: SyncService

    static let live = AppServices(
        persistence: LocalPersistenceService(),
        importExport: LocalImportExportService(),
        liveGame: LocalLiveGameService(),
        analytics: LocalAnalyticsService(),
        lineupAnalytics: LocalLineupAnalyticsService(),
        playbook: LocalPlaybookService(),
        reports: LocalReportService(),
        auth: LocalAuthService(),
        sync: LocalSyncService()
    )
}
