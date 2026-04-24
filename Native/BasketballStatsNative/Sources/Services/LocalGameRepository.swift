import Foundation
import UIKit

struct LocalPersistenceService: PersistenceService {
    private let store = JSONFileStore()

    func loadBundle() async throws -> AppDataBundle {
        if let stored: AppDataBundle = try await store.load(AppDataBundle.self, from: .appData) {
            return stored
        }

        let seeded = SampleData.bundle
        try await saveBundle(seeded)
        return seeded
    }

    func saveBundle(_ bundle: AppDataBundle) async throws {
        try await store.save(bundle, to: .appData)
    }
}

struct LocalImportExportService: ImportExportService {
    func importGames(from urls: [URL]) async throws -> [Game] {
        var games: [Game] = []
        for url in urls {
            let didAccess = url.startAccessingSecurityScopedResource()
            defer {
                if didAccess { url.stopAccessingSecurityScopedResource() }
            }

            let data = try Data(contentsOf: url)
            switch url.pathExtension.lowercased() {
            case "json":
                games.append(try parseJSONGame(data: data, filename: url.lastPathComponent))
            case "csv":
                games.append(try parseCSVGame(data: data, filename: url.deletingPathExtension().lastPathComponent))
            default:
                continue
            }
        }
        return games.sorted { $0.date > $1.date }
    }

    func exportRawGame(_ game: Game) async throws -> URL {
        let export = RawGameExport.from(game: game)
        let data = try JSONEncoder.exportEncoder.encode(export)
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("game_raw_\(game.sortDate)_\(game.opponent.sanitizedFileName)")
            .appendingPathExtension("json")
        try data.write(to: url, options: .atomic)
        return url
    }

    private func parseJSONGame(data: Data, filename: String) throws -> Game {
        if let export = try? JSONDecoder.exportDecoder.decode(RawGameExport.self, from: data) {
            return export.toGame()
        }
        if let game = try? JSONDecoder.exportDecoder.decode(Game.self, from: data) {
            return game
        }
        throw ImportExportError.unsupportedJSON(filename)
    }

    private func parseCSVGame(data: Data, filename: String) throws -> Game {
        guard let content = String(data: data, encoding: .utf8) else {
            throw ImportExportError.invalidText(filename)
        }
        let rows = content
            .split(whereSeparator: \.isNewline)
            .map { String($0) }
            .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        guard rows.count >= 2 else {
            throw ImportExportError.invalidCSV(filename)
        }

        let metadata = CSVFilenameMetadata.parse(filename: filename)
        let headers = rows[0].split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
        let playerStats: [PlayerStat] = rows.dropFirst().compactMap { row in
            let cells = row.split(separator: ",", omittingEmptySubsequences: false).map(String.init)
            guard cells.count == headers.count else { return nil }
            let dict = Dictionary(uniqueKeysWithValues: zip(headers, cells))
            let minutes = Self.minutesValue(dict["MIN"])
            let points = Int(dict["PTS"] ?? "0") ?? 0
            let fgm = Int(dict["FGM"] ?? "0") ?? 0
            let fga = Int(dict["FGA"] ?? "0") ?? 0
            let tpm = Int(dict["3PM"] ?? "0") ?? 0
            let tpa = Int(dict["3PA"] ?? "0") ?? 0
            let ftm = Int(dict["FTM"] ?? "0") ?? 0
            let fta = Int(dict["FTA"] ?? "0") ?? 0
            let oreb = Int(dict["OREB"] ?? "0") ?? 0
            let dreb = Int(dict["DREB"] ?? "0") ?? 0

            return PlayerStat(
                id: UUID(),
                playerName: dict["Name"] ?? "Unknown",
                points: points,
                minutes: minutes,
                rebounds: Int(dict["REB"] ?? "0") ?? (oreb + dreb),
                assists: Int(dict["AST"] ?? "0") ?? 0,
                steals: Int(dict["STL"] ?? "0") ?? 0,
                blocks: Int(dict["BLK"] ?? "0") ?? 0,
                turnovers: Int(dict["TOV"] ?? "0") ?? 0,
                fouls: Int(dict["PF"] ?? "0") ?? 0,
                fieldGoalsMade: fgm,
                fieldGoalAttempts: fga,
                threePointsMade: tpm,
                threePointAttempts: tpa,
                freeThrowsMade: ftm,
                freeThrowAttempts: fta,
                offensiveRebounds: oreb,
                defensiveRebounds: dreb,
                plusMinus: 0,
                reboundsConceded: 0
            )
        }

        return Game(
            id: UUID(),
            externalReference: filename,
            date: metadata.date,
            sortDate: metadata.sortDate,
            opponent: metadata.opponent,
            teamScore: metadata.teamScore,
            opponentScore: metadata.opponentScore,
            gameType: metadata.gameType,
            source: .imported,
            playerStats: playerStats,
            shotEvents: [],
            events: [],
            lineupSegments: [],
            notes: "Imported from CSV on iPad",
            syncState: .localOnly,
            schemaVersion: 1,
            createdAt: .now,
            updatedAt: .now
        )
    }

    static func minutesValue(_ raw: String?) -> Int {
        guard let raw else { return 0 }
        let parts = raw.split(separator: ":")
        if parts.count == 2 {
            let minutes = Int(parts[0]) ?? 0
            let seconds = Int(parts[1]) ?? 0
            return minutes + seconds / 60
        }
        return Int(raw) ?? 0
    }
}

struct LocalLiveGameService: LiveGameService {
    func startNewGame(opponent: String, roster: [String], startingLineup: [String], gameType: GameType) -> LiveGameSession {
        LiveGameSession.newGame(opponent: opponent, roster: roster, startingLineup: startingLineup, gameType: gameType)
    }

    func recordEvent(in session: LiveGameSession, kind: LiveGameEventKind, playerName: String?, detail: String, playID: UUID?) -> LiveGameSession {
        var session = session
        session.recordEvent(kind, playerName: playerName, detail: detail, playID: playID, createsPossession: kind.createsPossession, shotEvent: shotEvent(for: kind, playerName: playerName, quarter: session.quarter, playID: playID))
        return session
    }

    func substitute(in session: LiveGameSession, outgoing: String, incoming: String) -> LiveGameSession {
        var session = session
        session.substitute(outgoing: outgoing, incoming: incoming)
        return session
    }

    func undoLastEvent(in session: LiveGameSession) -> LiveGameSession {
        var session = session
        session.undoLastEvent()
        return session
    }

    func complete(session: LiveGameSession) -> Game {
        session.makeCompletedGame()
    }

    private func shotEvent(for kind: LiveGameEventKind, playerName: String?, quarter: Int, playID: UUID?) -> ShotEvent? {
        guard kind.isShotEvent else { return nil }
        let shotType: ShotType
        let result: ShotResult
        let zone: ShotZone

        switch kind {
        case .homeTwoMade, .homeTwoMissed, .awayTwoMade, .awayTwoMissed:
            shotType = .twoPoint
            result = [.homeTwoMade, .awayTwoMade].contains(kind) ? .made : .missed
            zone = .paint
        case .homeThreeMade, .homeThreeMissed, .awayThreeMade, .awayThreeMissed:
            shotType = .threePoint
            result = [.homeThreeMade, .awayThreeMade].contains(kind) ? .made : .missed
            zone = .aboveBreakThree
        default:
            shotType = .freeThrow
            result = [.homeFreeThrowMade, .awayFreeThrowMade].contains(kind) ? .made : .missed
            zone = .freeThrow
        }

        return ShotEvent(
            id: UUID(),
            gameID: nil,
            playerName: playerName,
            shotType: shotType,
            result: result,
            points: kind.pointsValue,
            xLocation: nil,
            yLocation: nil,
            zone: zone,
            quarter: quarter,
            playID: playID
        )
    }
}

struct LocalAnalyticsService: AnalyticsService {
    func teamOverview(for games: [Game]) -> TeamOverview {
        let totalGames = games.count
        let wins = games.filter { $0.result == .win }.count
        let losses = games.filter { $0.result == .loss }.count
        let scored = games.map(\.teamScore).reduce(0, +)
        let allowed = games.map(\.opponentScore).reduce(0, +)
        let grouped = Dictionary(grouping: games.flatMap(\.playerStats), by: \.playerName)
        let averages = grouped.map { playerName, stats -> PlayerAverage in
            let count = Double(stats.count)
            let points = stats.reduce(0) { $0 + $1.points }
            let assists = stats.reduce(0) { $0 + $1.assists }
            let rebounds = stats.reduce(0) { $0 + $1.rebounds }
            let ts = stats.map(\.trueShootingPercentage).reduce(0, +)
            return PlayerAverage(
                playerName: playerName,
                points: count > 0 ? Double(points) / count : 0,
                assists: count > 0 ? Double(assists) / count : 0,
                rebounds: count > 0 ? Double(rebounds) / count : 0,
                trueShooting: count > 0 ? ts / count : 0
            )
        }
        .sorted { $0.points > $1.points }

        return TeamOverview(
            totalGames: totalGames,
            wins: wins,
            losses: losses,
            pointsPerGame: totalGames > 0 ? Double(scored) / Double(totalGames) : 0,
            pointsAllowedPerGame: totalGames > 0 ? Double(allowed) / Double(totalGames) : 0,
            averageMargin: totalGames > 0 ? Double(scored - allowed) / Double(totalGames) : 0,
            topScorers: Array(averages.prefix(5))
        )
    }

    func playerProgression(for games: [Game], playerName: String) -> [PlayerProgressPoint] {
        games
            .sorted { $0.date < $1.date }
            .compactMap { game in
                guard let stat = game.playerStats.first(where: { $0.playerName == playerName }) else { return nil }
                return PlayerProgressPoint(
                    date: game.displayDate,
                    playerName: playerName,
                    points: stat.points,
                    assists: stat.assists,
                    rebounds: stat.rebounds
                )
            }
    }

    func usageSnapshots(for games: [Game]) -> [UsageSnapshot] {
        let grouped = Dictionary(grouping: games.flatMap(\.playerStats), by: \.playerName)
        return grouped.map { playerName, stats in
            let totalUsage = stats.map(\.usagePossessions).reduce(0, +)
            let teamUsage = games.flatMap(\.playerStats).map(\.usagePossessions).reduce(0, +)
            let totalPoints = stats.map(\.points).reduce(0, +)
            let fga = stats.map(\.fieldGoalAttempts).reduce(0, +)
            return UsageSnapshot(
                playerName: playerName,
                usageRate: teamUsage > 0 ? totalUsage / teamUsage : 0,
                pointsPerShot: fga > 0 ? Double(totalPoints) / Double(fga) : 0
            )
        }
        .sorted { $0.usageRate > $1.usageRate }
    }
}

struct LocalLineupAnalyticsService: LineupAnalyticsService {
    func lineupRankings(for games: [Game]) -> [LineupRanking] {
        let allSegments = games.flatMap(\.lineupSegments)
        let grouped = Dictionary(grouping: allSegments, by: { $0.players.sorted().joined(separator: "|") })
        return grouped.compactMap { _, segments in
            guard let first = segments.first else { return nil }
            let possessions = segments.reduce(0) { $0 + $1.possessions }
            let scored = segments.reduce(0) { $0 + $1.pointsScored }
            let allowed = segments.reduce(0) { $0 + $1.pointsAllowed }
            let net = possessions > 0 ? Double(scored - allowed) / Double(possessions) * 100 : Double(scored - allowed)
            return LineupRanking(id: first.id, players: first.players, netRating: net, possessions: possessions)
        }
        .sorted { $0.netRating > $1.netRating }
    }
}

struct LocalPlaybookService: PlaybookService {
    func blankPlay() -> Play {
        Play(
            id: UUID(),
            name: "New Play",
            description: "",
            playType: "Offense",
            difficulty: "Medium",
            personnelRequired: "5 players",
            tags: [],
            source: "native",
            canvasScene: .empty,
            frames: [PlayFrame(id: UUID(), sequenceNumber: 1, caption: "Start", focusPlayers: [], annotations: [])],
            createdAt: .now,
            updatedAt: .now
        )
    }

    func save(play: Play, in plays: [Play]) -> [Play] {
        var plays = plays
        if let index = plays.firstIndex(where: { $0.id == play.id }) {
            plays[index] = play
        } else {
            plays.insert(play, at: 0)
        }
        return plays.sorted { $0.updatedAt > $1.updatedAt }
    }

    func delete(playID: UUID, from plays: [Play]) -> [Play] {
        plays.filter { $0.id != playID }
    }
}

struct LocalReportService: ReportService {
    func summaryText(for game: Game) -> String {
        let header = "\(game.opponent) • \(game.displayDate)\nScore: \(game.scoreDisplay)\nResult: \(game.result.rawValue)\n"
        let players = game.playerStats.map { stat in
            "\(stat.playerName): \(stat.points) pts, \(stat.rebounds) reb, \(stat.assists) ast"
        }.joined(separator: "\n")
        let notes = game.notes.isEmpty ? "No notes" : game.notes
        return "\(header)\nPlayers\n\(players)\n\nNotes\n\(notes)\n"
    }

    func summaryPDF(for game: Game) async throws -> URL {
        let text = summaryText(for: game)
        let renderer = UIGraphicsPDFRenderer(bounds: CGRect(x: 0, y: 0, width: 595, height: 842))
        let data = renderer.pdfData { context in
            context.beginPage()
            let attributes: [NSAttributedString.Key: Any] = [
                .font: UIFont.monospacedSystemFont(ofSize: 14, weight: .regular)
            ]
            text.draw(in: CGRect(x: 40, y: 40, width: 515, height: 762), withAttributes: attributes)
        }

        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("report_\(game.sortDate)_\(game.opponent.sanitizedFileName)")
            .appendingPathExtension("pdf")
        try data.write(to: url, options: .atomic)
        return url
    }
}

struct LocalAuthService: AuthService {
    func defaultUsers() -> [User] {
        [
            User(id: UUID(), username: "admin", email: "admin@team.local", role: .admin, isAdmin: true, emailVerified: true, authProvider: "local"),
            User(id: UUID(), username: "coach", email: "coach@team.local", role: .editor, isAdmin: false, emailVerified: true, authProvider: "local"),
            User(id: UUID(), username: "viewer", email: "viewer@team.local", role: .viewer, isAdmin: false, emailVerified: true, authProvider: "local"),
        ]
    }
}

struct LocalSyncService: SyncService {
    func syncSummary(for bundle: AppDataBundle) -> String {
        let pendingGames = bundle.games.filter { $0.syncState == .pendingUpload || $0.syncState == .localOnly }.count
        let issues = bundle.syncIssues.count
        return "\(pendingGames) local game(s), \(issues) sync issue(s)"
    }
}

actor JSONFileStore {
    private let encoder = JSONEncoder.exportEncoder
    private let decoder = JSONDecoder.exportDecoder

    func load<Value: Decodable>(_ type: Value.Type, from file: StoreFile) throws -> Value? {
        let url = try url(for: file)
        guard FileManager.default.fileExists(atPath: url.path) else { return nil }
        let data = try Data(contentsOf: url)
        return try decoder.decode(type, from: data)
    }

    func save<Value: Encodable>(_ value: Value, to file: StoreFile) throws {
        let url = try url(for: file)
        let data = try encoder.encode(value)
        try data.write(to: url, options: .atomic)
    }

    private func url(for file: StoreFile) throws -> URL {
        let root = try FileManager.default.url(
            for: .applicationSupportDirectory,
            in: .userDomainMask,
            appropriateFor: nil,
            create: true
        ).appendingPathComponent("BasketballStatsNative", isDirectory: true)

        if !FileManager.default.fileExists(atPath: root.path) {
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        }

        return root.appendingPathComponent(file.rawValue)
    }
}

enum StoreFile: String {
    case appData = "app-data.json"
}

enum ImportExportError: Error, LocalizedError {
    case unsupportedJSON(String)
    case invalidText(String)
    case invalidCSV(String)

    var errorDescription: String? {
        switch self {
        case .unsupportedJSON(let file):
            return "Unsupported JSON file: \(file)"
        case .invalidText(let file):
            return "Could not read text from \(file)"
        case .invalidCSV(let file):
            return "Invalid CSV format in \(file)"
        }
    }
}

private struct CSVFilenameMetadata {
    var opponent: String
    var teamScore: Int
    var opponentScore: Int
    var date: Date
    var sortDate: String
    var gameType: GameType

    static func parse(filename: String) -> CSVFilenameMetadata {
        let trimmed = filename.replacingOccurrences(of: ".csv", with: "")
        let parts = trimmed.split(separator: "_").map(String.init)
        guard parts.count >= 4 else {
            return CSVFilenameMetadata(opponent: trimmed, teamScore: 0, opponentScore: 0, date: .now, sortDate: Date.now.isoSortDate, gameType: .season)
        }

        let opponent = parts[0]
        let scores = parts[1].split(separator: "-").map(String.init)
        let teamScore = Int(scores.first ?? "0") ?? 0
        let opponentScore = Int(scores.dropFirst().first ?? "0") ?? 0
        let date = Self.parseDate(parts[2]) ?? .now
        let gameType = parts[3].uppercased() == "F" ? GameType.friendly : (parts[3].uppercased() == "P" ? .playoff : .season)

        return CSVFilenameMetadata(
            opponent: opponent,
            teamScore: teamScore,
            opponentScore: opponentScore,
            date: date,
            sortDate: date.isoSortDate,
            gameType: gameType
        )
    }

    private static func parseDate(_ raw: String) -> Date? {
        let formatter = DateFormatter()
        formatter.dateFormat = "dd-MM-yyyy"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        return formatter.date(from: raw)
    }
}

private struct RawGameExport: Codable {
    struct SourceBlock: Codable {
        var app: String
        var branch: String
    }

    struct GameBlock: Codable {
        var id: Int?
        var date: String?
        var opponent: String
        var team_score: Int
        var opponent_score: Int
        var game_type: String?
        var sort_date: String?
        var source: String?
        var schema_version: Int?
    }

    struct PlayerBlock: Codable {
        var player_name: String
        var points: Int?
        var minutes: String?
        var reb: Int?
        var ast: Int?
        var stl: Int?
        var blk: Int?
        var tov: Int?
        var pf: Int?
        var fgm: Int?
        var fga: Int?
        var tpm: Int?
        var tpa: Int?
        var ftm: Int?
        var fta: Int?
        var oreb: Int?
        var dreb: Int?
        var plus_minus: Int?
        var reb_conceded: Int?
    }

    struct EventBlock: Codable {
        var player_name: String?
        var event_type: String?
        var quarter: Int?
        var timestamp: Int?
        var detail: String?
        var time_remaining: String?
        var score_margin: Int?
    }

    struct ShotBlock: Codable {
        var player_name: String?
        var shot_type: String?
        var result: String?
        var points: Int?
        var x_loc: Double?
        var y_loc: Double?
        var zone: String?
        var quarter: Int?
    }

    var schema_version: String?
    var exported_at: String?
    var source: SourceBlock?
    var game: GameBlock
    var player_stats: [PlayerBlock]
    var shot_events: [ShotBlock]
    var game_events: [EventBlock]

    static func from(game: Game) -> RawGameExport {
        RawGameExport(
            schema_version: String(game.schemaVersion),
            exported_at: ISO8601DateFormatter().string(from: .now),
            source: SourceBlock(app: "BasketballStatsNative", branch: "iPad"),
            game: GameBlock(
                id: nil,
                date: game.displayDate,
                opponent: game.opponent,
                team_score: game.teamScore,
                opponent_score: game.opponentScore,
                game_type: game.gameType.rawValue,
                sort_date: game.sortDate,
                source: game.source.rawValue,
                schema_version: game.schemaVersion
            ),
            player_stats: game.playerStats.map {
                PlayerBlock(
                    player_name: $0.playerName,
                    points: $0.points,
                    minutes: "\($0.minutes)",
                    reb: $0.rebounds,
                    ast: $0.assists,
                    stl: $0.steals,
                    blk: $0.blocks,
                    tov: $0.turnovers,
                    pf: $0.fouls,
                    fgm: $0.fieldGoalsMade,
                    fga: $0.fieldGoalAttempts,
                    tpm: $0.threePointsMade,
                    tpa: $0.threePointAttempts,
                    ftm: $0.freeThrowsMade,
                    fta: $0.freeThrowAttempts,
                    oreb: $0.offensiveRebounds,
                    dreb: $0.defensiveRebounds,
                    plus_minus: $0.plusMinus,
                    reb_conceded: $0.reboundsConceded
                )
            },
            shot_events: game.shotEvents.map {
                ShotBlock(
                    player_name: $0.playerName,
                    shot_type: $0.shotType.rawValue,
                    result: $0.result.rawValue,
                    points: $0.points,
                    x_loc: $0.xLocation,
                    y_loc: $0.yLocation,
                    zone: $0.zone.rawValue,
                    quarter: $0.quarter
                )
            },
            game_events: game.events.map {
                EventBlock(
                    player_name: $0.playerName,
                    event_type: $0.kind.rawValue,
                    quarter: $0.quarter,
                    timestamp: $0.eventIndex,
                    detail: $0.detail,
                    time_remaining: $0.timeRemaining,
                    score_margin: $0.scoreMargin
                )
            }
        )
    }

    func toGame() -> Game {
        let formatter = DateFormatter()
        formatter.dateFormat = "dd/MM/yyyy"
        formatter.locale = Locale(identifier: "en_US_POSIX")
        let date = formatter.date(from: game.date ?? "") ?? .now
        let playerStats = player_stats.map { item in
            PlayerStat(
                id: UUID(),
                playerName: item.player_name,
                points: item.points ?? 0,
                minutes: LocalImportExportService.minutesValue(item.minutes),
                rebounds: item.reb ?? 0,
                assists: item.ast ?? 0,
                steals: item.stl ?? 0,
                blocks: item.blk ?? 0,
                turnovers: item.tov ?? 0,
                fouls: item.pf ?? 0,
                fieldGoalsMade: item.fgm ?? 0,
                fieldGoalAttempts: item.fga ?? 0,
                threePointsMade: item.tpm ?? 0,
                threePointAttempts: item.tpa ?? 0,
                freeThrowsMade: item.ftm ?? 0,
                freeThrowAttempts: item.fta ?? 0,
                offensiveRebounds: item.oreb ?? 0,
                defensiveRebounds: item.dreb ?? 0,
                plusMinus: item.plus_minus ?? 0,
                reboundsConceded: item.reb_conceded ?? 0
            )
        }
        let shotEvents = shot_events.map { shot in
            ShotEvent(
                id: UUID(),
                gameID: nil,
                playerName: shot.player_name,
                shotType: ShotType(rawValue: shot.shot_type ?? "") ?? .twoPoint,
                result: ShotResult(rawValue: shot.result ?? "") ?? .made,
                points: shot.points ?? 0,
                xLocation: shot.x_loc,
                yLocation: shot.y_loc,
                zone: ShotZone(rawValue: shot.zone ?? "") ?? .unknown,
                quarter: shot.quarter ?? 1,
                playID: nil
            )
        }
        let events = game_events.enumerated().map { index, item in
            RecordedGameEvent(
                id: UUID(),
                quarter: item.quarter ?? 1,
                eventIndex: item.timestamp ?? (index + 1),
                playerName: item.player_name,
                kind: LiveGameEventKind(rawValue: item.event_type ?? "") ?? .turnover,
                timestamp: .now,
                timeRemaining: item.time_remaining,
                scoreMargin: item.score_margin,
                detail: item.detail ?? "",
                playID: nil,
                lineupSegmentID: nil,
                taggedLineup: []
            )
        }
        return Game(
            id: UUID(),
            externalReference: source?.app,
            date: date,
            sortDate: game.sort_date ?? date.isoSortDate,
            opponent: game.opponent,
            teamScore: game.team_score,
            opponentScore: game.opponent_score,
            gameType: GameType(rawValue: game.game_type ?? "") ?? .season,
            source: GameSource(rawValue: game.source ?? "") ?? .imported,
            playerStats: playerStats,
            shotEvents: shotEvents,
            events: events,
            lineupSegments: [],
            notes: "Imported from JSON archive",
            syncState: .localOnly,
            schemaVersion: game.schema_version ?? Int(schema_version ?? "1") ?? 1,
            createdAt: .now,
            updatedAt: .now
        )
    }
}

private extension JSONEncoder {
    static var exportEncoder: JSONEncoder {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }
}

private extension JSONDecoder {
    static var exportDecoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}

private extension FileManager {
    var temporaryExportDirectory: URL {
        temporaryDirectory
    }
}

private extension String {
    var sanitizedFileName: String {
        replacingOccurrences(of: " ", with: "_")
            .filter { $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" }
    }
}

private extension Date {
    var isoSortDate: String {
        ISO8601DateFormatter().string(from: self).prefix(10).description
    }
}
