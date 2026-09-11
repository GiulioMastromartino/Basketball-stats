import Foundation

enum WebAPIError: Error, LocalizedError {
    case unreachable
    case redirect(URL?)
    case badStatus(Int)
    case decoding(String)

    var errorDescription: String? {
        switch self {
        case .unreachable:
            return "Flask API server unreachable. Start it with: DISABLE_AUTH=1 python run_local.py"
        case .redirect:
            return "API returned a redirect (auth required). Run the server with DISABLE_AUTH=1."
        case .badStatus(let code):
            return "API returned HTTP \(code)."
        case .decoding(let message):
            return "Could not decode API response: \(message)"
        }
    }
}

struct WebAPIClient: Sendable {
    var baseURL: URL = URL(string: "http://127.0.0.1:8080")!

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 20
        config.httpCookieStorage = .shared
        return URLSession(configuration: config)
    }()

    func fetch<T: Decodable>(_ path: String, query: [URLQueryItem] = []) async throws -> T {
        var url = baseURL.appendingPathComponent(path)
        if !query.isEmpty {
            url = url.appending(queryItems: query)
        }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw WebAPIError.unreachable }
        if http.statusCode == 302, let loc = http.value(forHTTPHeaderField: "Location"), loc != path {
            throw WebAPIError.redirect(URL(string: loc))
        }
        guard (200...299).contains(http.statusCode) else { throw WebAPIError.badStatus(http.statusCode) }
        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw WebAPIError.decoding(error.localizedDescription)
        }
    }

    func teamOverview(gameType: String = "ALL", limitTrend: Int = 0, topLimit: Int = 3) async throws -> WebTeamOverview {
        try await fetch("/api/analytics/team_overview", query: [
            URLQueryItem(name: "game_type", value: gameType),
            URLQueryItem(name: "limit_trend", value: String(limitTrend)),
            URLQueryItem(name: "top_limit", value: String(topLimit)),
        ])
    }

    func consistencyLeaderboard() async throws -> WebConsistency {
        try await fetch("/api/analytics/consistency_leaderboard")
    }

    func roleAnalysis() async throws -> WebRoleAnalysis {
        try await fetch("/api/analytics/role_analysis")
    }

    func shootingBreakdown(gameID: Int) async throws -> WebShootingBreakdown {
        try await fetch("/api/analytics/shooting_breakdown", query: [URLQueryItem(name: "game_id", value: String(gameID))])
    }

    func playerProgression(player: String, gameType: String = "ALL") async throws -> WebPlayerProgression {
        try await fetch("/api/analytics/player_progression", query: [
            URLQueryItem(name: "player", value: player),
            URLQueryItem(name: "game_type", value: gameType),
        ])
    }

    func multiCompare(players: [String], stats: [String] = ["ppg", "ortg", "ts_pct", "fg_pct"], includeMA: Bool = true) async throws -> WebMultiCompare {
        var items = players.map { URLQueryItem(name: "players", value: $0) }
        items += stats.map { URLQueryItem(name: "stats", value: $0) }
        items.append(URLQueryItem(name: "ma", value: includeMA ? "true" : "false"))
        return try await fetch("/api/analytics/multi_compare", query: items)
    }

    func plays() async throws -> [WebPlay] {
        try await fetch("/api/v1/plays")
    }

    func games() async throws -> [WebGameRef] {
        try await fetch("/api/v1/games")
    }

    func syncPayload() async throws -> WebSyncResponse {
        try await fetch("/api/v1/sync")
    }

    func gameID(for game: Game) async -> Int? {
        let webGames = (try? await games()) ?? []
        return webGames.first {
            $0.opponent == game.opponent && $0.sortDate == game.sortDate
        }?.id
    }

    struct ImportResult: Sendable {
        var successCount: Int
        var errors: [String]
    }

    func importFiles(_ urls: [URL]) async throws -> ImportResult {
        let boundary = "WebAPI-\(UUID().uuidString)"
        var body = Data()
        func appendField(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append(value.data(using: .utf8)!)
            body.append("\r\n".data(using: .utf8)!)
        }
        var importType = "csv"
        for url in urls {
            let ext = url.pathExtension.lowercased()
            if ext == "pdf" { importType = "pdf" }
            if ext == "json" { importType = "json" }
            let fileData = try Data(contentsOf: url)
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(url.lastPathComponent)\"\r\n".data(using: .utf8)!)
            body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
            body.append(fileData)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        return try await postMultipart(body: body, boundary: boundary)
    }

    func importRaw(data: Data, filename: String, importType: String) async throws -> ImportResult {
        let boundary = "WebAPI-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        return try await postMultipart(body: body, boundary: boundary)
    }

    func importRawGames(_ games: [Game]) async throws -> ImportResult {
        var result = ImportResult(successCount: 0, errors: [])
        for game in games {
            let exporter = RawGameExportBuilder()
            let data = try exporter.data(for: game)
            let outcome = try await importRaw(
                data: data,
                filename: "game_\(game.sortDate)_\(game.opponent).json",
                importType: "json"
            )
            result.successCount += outcome.successCount
            result.errors += outcome.errors
        }
        return result
    }

    private func postMultipart(body: Data, boundary: String) async throws -> ImportResult {
        var request = URLRequest(url: baseURL.appendingPathComponent("/api/v1/import"))
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw WebAPIError.unreachable }
        guard (200...299).contains(http.statusCode) else { throw WebAPIError.badStatus(http.statusCode) }
        struct ImportResponse: Decodable {
            let successCount: Int
            let errors: [String]

            enum CodingKeys: String, CodingKey {
                case errors
                case successCount = "success_count"
            }
        }
        let decoded = try JSONDecoder().decode(ImportResponse.self, from: data)
        return ImportResult(successCount: decoded.successCount, errors: decoded.errors)
    }

    func lineupRankings(gameType: String = "ALL", minPossessions: Int = 5) async throws -> WebLineupRankings {
        try await fetch("/api/advanced/lineup/rankings", query: [
            URLQueryItem(name: "game_type", value: gameType),
            URLQueryItem(name: "min_possessions", value: String(minPossessions)),
            URLQueryItem(name: "rank_by", value: "overall"),
        ])
    }

    func combinations(type: String, gameType: String = "ALL", minPossessions: Int = 5) async throws -> WebCombinations {
        try await fetch("/api/advanced/lineups/combinations", query: [
            URLQueryItem(name: "type", value: type),
            URLQueryItem(name: "game_type", value: gameType),
            URLQueryItem(name: "min_possessions", value: String(minPossessions)),
            URLQueryItem(name: "rank_by", value: "overall"),
        ])
    }

    func advancedPlayer(_ player: String, gameType: String = "ALL") async throws -> WebAdvancedPlayer {
        try await fetch("/api/advanced/player/\(player)/advanced", query: [URLQueryItem(name: "game_type", value: gameType)])
    }

    func fourFactors(gameType: String = "Season") async throws -> WebFourFactors {
        try await fetch("/api/advanced/four-factors", query: [URLQueryItem(name: "game_type", value: gameType)])
    }

    func shotChart(gameType: String = "ALL", player: String? = nil) async throws -> WebShotChart {
        var items = [URLQueryItem(name: "game_type", value: gameType)]
        if let player {
            items.append(URLQueryItem(name: "player", value: player))
        }
        return try await fetch("/api/advanced/shots/chart", query: items)
    }

    // MARK: - PDF reports

    func downloadPDF(_ path: String, query: [URLQueryItem] = []) async throws -> Data {
        var url = baseURL.appendingPathComponent(path)
        if !query.isEmpty {
            url = url.appending(queryItems: query)
        }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse else { throw WebAPIError.unreachable }
        if http.statusCode == 302, let loc = http.value(forHTTPHeaderField: "Location"), loc != path {
            throw WebAPIError.redirect(URL(string: loc))
        }
        guard (200...299).contains(http.statusCode) else { throw WebAPIError.badStatus(http.statusCode) }
        return data
    }

    func gameSummaryPDF(gameID: Int) async throws -> Data {
        try await downloadPDF("/reports/games/\(gameID)/summary.pdf")
    }

    func gameAdvancedPDF(gameID: Int) async throws -> Data {
        try await downloadPDF("/reports/games/\(gameID)/advanced_summary.pdf")
    }

    func gameEvolutionPDF(gameID: Int) async throws -> Data {
        try await downloadPDF("/reports/games/\(gameID)/evolution.pdf")
    }

    func teamReportPDF() async throws -> Data {
        try await downloadPDF("/reports/team/report.pdf")
    }

    func playerReportPDF(player: String) async throws -> Data {
        try await downloadPDF("/reports/player/\(player)/report.pdf")
    }

    func playerScoutingPDF(player: String) async throws -> Data {
        try await downloadPDF("/reports/player/\(player)/scouting.pdf")
    }

    func seasonTrendsPDF() async throws -> Data {
        try await downloadPDF("/reports/season/trends.pdf")
    }

    func clutchReportPDF() async throws -> Data {
        try await downloadPDF("/reports/clutch/report.pdf")
    }

    func lineupReportPDF() async throws -> Data {
        try await downloadPDF("/reports/lineup/report.pdf")
    }
}

struct WebGameRef: Decodable, Identifiable {
    let id: Int
    let date: String
    let sortDate: String
    let opponent: String
    let teamScore: Int
    let opponentScore: Int
    let result: String
    let gameType: String

    enum CodingKeys: String, CodingKey {
        case id, date, opponent, result
        case sortDate = "sort_date"
        case teamScore = "team_score"
        case opponentScore = "opponent_score"
        case gameType = "game_type"
    }
}

// MARK: - Sync payload models (GET /api/v1/sync)

struct WebSyncResponse: Decodable {
    let exportedAt: String?
    let games: [WebRawGame]
    let plays: [WebPlayFull]
    let playTypes: [WebPlayTypeRef]

    enum CodingKeys: String, CodingKey {
        case games, plays
        case exportedAt = "exported_at"
        case playTypes = "play_types"
    }
}

struct WebRawGame: Decodable {
    let game: WebRawGameHeader
    let playerStats: [WebRawPlayerStat]
    let shotEvents: [WebRawShotEvent]
    let gameEvents: [WebRawGameEvent]
    let startingLineup: [String]?
    let lineupSegments: [WebRawLineupSegment]

    enum CodingKeys: String, CodingKey {
        case game
        case playerStats = "player_stats"
        case shotEvents = "shot_events"
        case gameEvents = "game_events"
        case startingLineup = "starting_lineup"
        case lineupSegments = "lineup_segments"
    }
}

struct WebRawGameHeader: Decodable {
    let id: Int?
    let date: String?
    let opponent: String
    let teamScore: Int
    let opponentScore: Int
    let gameType: String?
    let sortDate: String?
    let source: String?
    let schemaVersion: Int?

    enum CodingKeys: String, CodingKey {
        case id, date, opponent, source
        case teamScore = "team_score"
        case opponentScore = "opponent_score"
        case gameType = "game_type"
        case sortDate = "sort_date"
        case schemaVersion = "schema_version"
    }
}

struct WebRawPlayerStat: Decodable {
    let playerName: String
    let points: Int?
    let minutes: String?
    let reb: Int?
    let ast: Int?
    let stl: Int?
    let blk: Int?
    let tov: Int?
    let pf: Int?
    let fgm: Int?
    let fga: Int?
    let tpm: Int?
    let tpa: Int?
    let ftm: Int?
    let fta: Int?
    let oreb: Int?
    let dreb: Int?
    let plusMinus: Int?
    let reboundsConceded: Int?

    enum CodingKeys: String, CodingKey {
        case points, minutes, reb, ast, stl, blk, tov, pf, fgm, fga, tpm, tpa, ftm, fta, oreb, dreb
        case playerName = "player_name"
        case plusMinus = "plus_minus"
        case reboundsConceded = "reb_conceded"
    }
}

struct WebRawShotEvent: Decodable {
    let playerName: String?
    let shotType: String?
    let result: String?
    let points: Int?
    let xLoc: Double?
    let yLoc: Double?
    let zone: String?
    let quarter: Int?

    enum CodingKeys: String, CodingKey {
        case points, result, zone, quarter
        case playerName = "player_name"
        case shotType = "shot_type"
        case xLoc = "x_loc"
        case yLoc = "y_loc"
    }
}

struct WebRawGameEvent: Decodable {
    let eventType: String?
    let playerName: String?
    let detail: String?
    let timestamp: Int?
    let quarter: Int?
    let timeRemaining: String?
    let scoreMargin: Int?

    enum CodingKeys: String, CodingKey {
        case detail, timestamp, quarter
        case eventType = "event_type"
        case playerName = "player_name"
        case timeRemaining = "time_remaining"
        case scoreMargin = "score_margin"
    }
}

struct WebRawLineupSegment: Decodable {
    let players: [String]?
    let quarter: Int?
    let lineupHash: String?
    let pointsScored: Int?
    let pointsAllowed: Int?
    let possessions: Int?
    let reboundsConceded: Int?
    let durationSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case players, quarter
        case lineupHash = "lineup_hash"
        case pointsScored = "points_scored"
        case pointsAllowed = "points_allowed"
        case possessions
        case reboundsConceded = "reb_conceded"
        case durationSeconds = "duration_seconds"
    }
}

struct WebPlayFrame: Decodable {
    let sequenceNumber: Int?
    let elementData: WebJSON?
    let caption: String?

    enum CodingKeys: String, CodingKey {
        case caption
        case sequenceNumber = "sequence_number"
        case elementData = "element_data"
    }
}

struct WebPlayFull: Decodable {
    let id: Int
    let name: String
    let playType: String?
    let description: String?
    let difficulty: String?
    let personnelRequired: String?
    let tags: String?
    let source: String?
    let canvasData: WebJSON?
    let frames: [WebPlayFrame]?

    enum CodingKeys: String, CodingKey {
        case id, name, description, difficulty, source, tags
        case playType = "play_type"
        case personnelRequired = "personnel_required"
        case canvasData = "canvas_data"
        case frames
    }
}

struct WebPlayTypeRef: Decodable {
    let id: Int?
    let name: String?
}

enum WebJSON: Decodable {
    case object([String: WebJSON])
    case array([WebJSON])
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: WebJSON].self) {
            self = .object(value)
        } else if let value = try? container.decode([WebJSON].self) {
            self = .array(value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    var asAny: Any {
        switch self {
        case .object(let dict):
            return dict.mapValues { $0.asAny }
        case .array(let items):
            return items.map { $0.asAny }
        case .string(let value):
            return value
        case .number(let value):
            return value
        case .bool(let value):
            return value
        case .null:
            return NSNull()
        }
    }
}

struct WebTeamOverview: Decodable {
    let metrics: WebTeamMetrics
    let topChart: WebTopChart
    let trend: WebTrend

    enum CodingKeys: String, CodingKey {
        case metrics
        case topChart = "top_chart"
        case trend
    }
}

struct WebTeamMetrics: Decodable {
    let ppg: Double
    let winPct: Double

    enum CodingKeys: String, CodingKey { case ppg, winPct = "win_pct" }
}

struct WebTopChart: Decodable {
    let data: [Double]
    let label: String
    let labels: [String]
}

struct WebTrend: Decodable {
    let labels: [String]
    let oppScore: [Double]
    let teamScore: [Double]

    enum CodingKeys: String, CodingKey {
        case labels
        case oppScore = "opp_score"
        case teamScore = "team_score"
    }
}

struct WebConsistency: Decodable {
    let consistent: [WebConsistencyEntry]
    let volatile: [WebConsistencyEntry]
}

struct WebConsistencyEntry: Decodable {
    let cv: Double
    let games: Int
    let player: String
    let ppg: Double
}

struct WebRoleAnalysis: Decodable {
    let players: [WebRoleEntry]
}

struct WebRoleEntry: Decodable {
    let ortg: Double
    let player: String
    let ppg: Double
    let role: String
    let usg: Double
}

struct WebShootingBreakdown: Decodable {
    let efgPct: Double
    let fg: WebShotSplit
    let ft: WebShotSplit
    let threePt: WebShotSplit
    let tsPct: Double
    let twoPt: WebShotSplit

    enum CodingKeys: String, CodingKey {
        case efgPct = "efg_pct"
        case fg, ft
        case threePt = "three_pt"
        case tsPct = "ts_pct"
        case twoPt = "two_pt"
    }
}

struct WebShotSplit: Decodable {
    let att: Int
    let made: Int
    let pct: Double
}

struct WebPlayerProgression: Decodable {
    let dates: [String]
    let ppg: [Double]
    let ortg: [Double]
    let tsPct: [Double]
    let fgPct: [Double]
    let seasonAvgPpg: Double

    enum CodingKeys: String, CodingKey {
        case dates, ppg, ortg
        case tsPct = "ts_pct"
        case fgPct = "fg_pct"
        case seasonAvgPpg = "season_avg_ppg"
    }
}

struct WebMultiCompare: Decodable {
    let datasets: [WebCompareDataset]
    let labels: [String]
}

struct WebCompareDataset: Decodable {
    let data: [Double?]
    let label: String
}

struct WebPlay: Decodable, Identifiable {
    let id: Int
    let name: String
    let type: String
    let description: String?
}

struct WebLineupRankings: Decodable {
    let rankings: [WebLineupRanking]
    let gameType: String?
    let minPossessions: Int?

    enum CodingKeys: String, CodingKey {
        case rankings
        case gameType = "game_type"
        case minPossessions = "min_possessions"
    }
}

struct WebLineupRanking: Decodable, Identifiable {
    let id: Int?
    let lineupHash: String
    let players: [String]
    let segments: Int
    let gamesPlayed: Int
    let possessions: Int
    let totalMinutes: Double
    let pointsScored: Int
    let pointsAllowed: Int
    let ortg: Double
    let drtg: Double
    let netRating: Double

    enum CodingKeys: String, CodingKey {
        case id
        case lineupHash = "lineup_hash"
        case players, segments
        case gamesPlayed = "games_played"
        case possessions
        case totalMinutes = "total_minutes"
        case pointsScored = "points_scored"
        case pointsAllowed = "points_allowed"
        case ortg, drtg
        case netRating = "net_rating"
    }
}

struct WebCombinations: Decodable {
    let combinations: [WebCombination]
    let gameType: String?
    let type: String?
    let total: Int?

    enum CodingKeys: String, CodingKey {
        case combinations
        case gameType = "game_type"
        case type, total
    }
}

struct WebCombination: Decodable, Identifiable {
    var id: String { players.joined(separator: "+") }
    let type: String
    let players: [String]
    let segments: Int
    let on: WebCombinationSide
    let off: WebCombinationSide
    let impact: WebCombinationImpact
}

struct WebCombinationSide: Decodable {
    let minutes: Double
    let possessions: Int
    let pointsScored: Int
    let pointsAllowed: Int
    let ortg: Double
    let drtg: Double
    let net: Double

    enum CodingKeys: String, CodingKey {
        case minutes, possessions
        case pointsScored = "points_scored"
        case pointsAllowed = "points_allowed"
        case ortg, drtg, net
    }
}

struct WebCombinationImpact: Decodable {
    let offenseDelta: Double
    let defenseDelta: Double
    let netDifferential: Double

    enum CodingKeys: String, CodingKey {
        case offenseDelta = "offense_delta"
        case defenseDelta = "defense_delta"
        case netDifferential = "net_differential"
    }
}

struct WebAdvancedPlayer: Decodable {
    let playerName: String
    let seasonStats: WebAdvancedSeasonStats

    enum CodingKeys: String, CodingKey {
        case playerName = "player_name"
        case seasonStats = "season_stats"
    }
}

struct WebAdvancedSeasonStats: Decodable {
    let games: Int
    let points: Int
    let ppg: Double
    let rpg: Double
    let apg: Double
    let fgPct: Double
    let tpPct: Double
    let ftPct: Double
    let tsPct: Double
    let efgPct: Double
    let pps: Double
    let usageRate: Double

    enum CodingKeys: String, CodingKey {
        case games, points, ppg, rpg, apg
        case fgPct = "fg_pct"
        case tpPct = "tp_pct"
        case ftPct = "ft_pct"
        case tsPct = "ts_pct"
        case efgPct = "efg_pct"
        case pps
        case usageRate = "usage_rate"
    }
}

struct WebFourFactors: Decodable {
    let fourFactors: WebFourFactorsValues

    enum CodingKeys: String, CodingKey {
        case fourFactors = "four_factors"
    }
}

struct WebFourFactorsValues: Decodable {
    let efgPct: Double
    let tovPct: Double
    let orbPct: Double
    let ftRate: Double

    enum CodingKeys: String, CodingKey {
        case efgPct = "efg_pct"
        case tovPct = "tov_pct"
        case orbPct = "orb_pct"
        case ftRate = "ft_rate"
    }
}

struct WebShotChart: Decodable {
    let totalShots: Int
    let shots: [WebShot]

    enum CodingKeys: String, CodingKey {
        case totalShots = "total_shots"
        case shots
    }
}

struct WebShot: Decodable, Identifiable {
    let id: Int
    let playerName: String
    let shotType: String
    let result: String
    let points: Int
    let xLoc: Double
    let yLoc: Double
    let zone: String

    enum CodingKeys: String, CodingKey {
        case id
        case playerName = "player_name"
        case shotType = "shot_type"
        case result, points
        case xLoc = "x_loc"
        case yLoc = "y_loc"
        case zone
    }
}
