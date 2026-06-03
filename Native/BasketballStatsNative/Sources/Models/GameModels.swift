import Foundation

struct Game: Identifiable, Codable, Hashable {
    let id: UUID
    var externalReference: String?
    var date: Date
    var sortDate: String
    var opponent: String
    var teamScore: Int
    var opponentScore: Int
    var gameType: GameType
    var source: GameSource
    var playerStats: [PlayerStat]
    var shotEvents: [ShotEvent]
    var events: [RecordedGameEvent]
    var lineupSegments: [LineupSegment]
    var notes: String
    var syncState: SyncState
    var schemaVersion: Int
    var createdAt: Date
    var updatedAt: Date

    var result: GameResult {
        if teamScore > opponentScore { return .win }
        if teamScore < opponentScore { return .loss }
        return .draw
    }

    var scoreDisplay: String {
        "\(teamScore) - \(opponentScore)"
    }

    var displayDate: String {
        date.formatted(date: .abbreviated, time: .omitted)
    }

    var allPlayers: [String] {
        let names = playerStats.map(\.playerName)
        return Array(Set(names)).sorted()
    }
}

struct PlayerStat: Identifiable, Codable, Hashable {
    let id: UUID
    var playerName: String
    var points: Int
    var minutes: Int
    var rebounds: Int
    var assists: Int
    var steals: Int
    var blocks: Int
    var turnovers: Int
    var fouls: Int
    var fieldGoalsMade: Int
    var fieldGoalAttempts: Int
    var threePointsMade: Int
    var threePointAttempts: Int
    var freeThrowsMade: Int
    var freeThrowAttempts: Int
    var offensiveRebounds: Int
    var defensiveRebounds: Int
    var plusMinus: Int
    var reboundsConceded: Int

    var usagePossessions: Double {
        Double(fieldGoalAttempts) + 0.44 * Double(freeThrowAttempts) + Double(turnovers)
    }

    var shootingPercentage: Double {
        guard fieldGoalAttempts > 0 else { return 0 }
        return Double(fieldGoalsMade) / Double(fieldGoalAttempts)
    }

    var threePointPercentage: Double {
        guard threePointAttempts > 0 else { return 0 }
        return Double(threePointsMade) / Double(threePointAttempts)
    }

    var trueShootingPercentage: Double {
        let denominator = 2 * (Double(fieldGoalAttempts) + 0.44 * Double(freeThrowAttempts))
        guard denominator > 0 else { return 0 }
        return Double(points) / denominator
    }

    static let empty = PlayerStat(
        id: UUID(),
        playerName: "",
        points: 0,
        minutes: 0,
        rebounds: 0,
        assists: 0,
        steals: 0,
        blocks: 0,
        turnovers: 0,
        fouls: 0,
        fieldGoalsMade: 0,
        fieldGoalAttempts: 0,
        threePointsMade: 0,
        threePointAttempts: 0,
        freeThrowsMade: 0,
        freeThrowAttempts: 0,
        offensiveRebounds: 0,
        defensiveRebounds: 0,
        plusMinus: 0,
        reboundsConceded: 0
    )
}

struct RecordedGameEvent: Identifiable, Codable, Hashable {
    let id: UUID
    var quarter: Int
    var eventIndex: Int
    var playerName: String?
    var kind: LiveGameEventKind
    var timestamp: Date
    var timeRemaining: String?
    var scoreMargin: Int?
    var detail: String
    var playID: UUID?
    var lineupSegmentID: UUID?
    var taggedLineup: [String]
}

struct ShotEvent: Identifiable, Codable, Hashable {
    let id: UUID
    var gameID: UUID?
    var playerName: String?
    var shotType: ShotType
    var result: ShotResult
    var points: Int
    var xLocation: Double?
    var yLocation: Double?
    var zone: ShotZone
    var quarter: Int
    var playID: UUID?
}

struct Possession: Identifiable, Codable, Hashable {
    let id: UUID
    var gameID: UUID?
    var number: Int
    var quarter: Int
    var startingLineup: [String]
    var result: PossessionResult
}

struct LineupSegment: Identifiable, Codable, Hashable {
    let id: UUID
    var quarter: Int
    var players: [String]
    var startEventIndex: Int
    var endEventIndex: Int?
    var pointsScored: Int
    var pointsAllowed: Int
    var possessions: Int
    var displayName: String?

    var netRatingValue: Double {
        guard possessions > 0 else { return Double(pointsScored - pointsAllowed) }
        return Double(pointsScored - pointsAllowed) / Double(possessions) * 100
    }
}

struct Play: Identifiable, Codable, Hashable {
    let id: UUID
    var name: String
    var description: String
    var playType: String
    var difficulty: String
    var personnelRequired: String
    var tags: [String]
    var source: String
    var canvasScene: PlayCanvasScene
    var frames: [PlayFrame]
    var createdAt: Date
    var updatedAt: Date
}

struct PlayCanvasScene: Codable, Hashable {
    var width: Double
    var height: Double
    var tokens: [PlayToken]
    var connectors: [PlayConnector]
    var labels: [PlayLabel]

    static let empty = PlayCanvasScene(width: 500, height: 470, tokens: [], connectors: [], labels: [])
}

struct PlayToken: Identifiable, Codable, Hashable {
    let id: UUID
    var number: String
    var role: String
    var x: Double
    var y: Double
}

struct PlayConnector: Identifiable, Codable, Hashable {
    let id: UUID
    var kind: PlayConnectorKind
    var fromX: Double
    var fromY: Double
    var toX: Double
    var toY: Double
}

struct PlayLabel: Identifiable, Codable, Hashable {
    let id: UUID
    var text: String
    var x: Double
    var y: Double
}

struct PlayFrame: Identifiable, Codable, Hashable {
    let id: UUID
    var sequenceNumber: Int
    var caption: String
    var focusPlayers: [String]
    var annotations: [String]
}

struct PlayType: Identifiable, Codable, Hashable {
    let id: UUID
    var name: String
}

struct User: Identifiable, Codable, Hashable {
    let id: UUID
    var username: String
    var email: String
    var role: UserRole
    var isAdmin: Bool
    var emailVerified: Bool
    var authProvider: String
}

struct SystemSetting: Identifiable, Codable, Hashable {
    let id: UUID
    var key: String
    var value: String
    var description: String
    var updatedAt: Date
}

struct SyncIssue: Identifiable, Codable, Hashable {
    let id: UUID
    var entityName: String
    var entityID: UUID
    var reason: String
    var createdAt: Date
}

struct AppDataBundle: Codable, Hashable {
    var games: [Game]
    var liveSession: LiveGameSession
    var plays: [Play]
    var playTypes: [PlayType]
    var users: [User]
    var currentUserID: UUID?
    var systemSettings: [SystemSetting]
    var syncIssues: [SyncIssue]

    static let empty = AppDataBundle(
        games: [],
        liveSession: .empty,
        plays: [],
        playTypes: [],
        users: [],
        currentUserID: nil,
        systemSettings: [],
        syncIssues: []
    )
}

enum GameType: String, Codable, CaseIterable, Hashable {
    case season = "Season"
    case friendly = "Friendly"
    case playoff = "Playoff"
}

enum GameSource: String, Codable, Hashable, CaseIterable {
    case live = "LIVE"
    case imported = "IMPORT"
    case manual = "MANUAL"
}

enum GameResult: String, Codable, Hashable {
    case win = "W"
    case loss = "L"
    case draw = "D"
}

enum SyncState: String, Codable, Hashable, CaseIterable {
    case localOnly
    case pendingUpload
    case synced
    case conflict
}

enum ShotType: String, Codable, Hashable, CaseIterable {
    case twoPoint
    case threePoint
    case freeThrow
}

enum ShotResult: String, Codable, Hashable, CaseIterable {
    case made
    case missed
}

enum ShotZone: String, Codable, Hashable, CaseIterable, Identifiable {
    case rim = "Rim"
    case paint = "Paint"
    case midrange = "Midrange"
    case aboveBreakThree = "Above Break 3"
    case cornerThree = "Corner 3"
    case freeThrow = "Free Throw"
    case unknown = "Unknown"

    var id: String { rawValue }
}

enum PossessionResult: String, Codable, Hashable {
    case score
    case miss
    case turnover
    case foul
    case deadBall
}

enum PlayConnectorKind: String, Codable, Hashable, CaseIterable {
    case cut
    case pass
    case dribble
    case screen
}

enum UserRole: String, Codable, Hashable, CaseIterable, Identifiable {
    case admin
    case editor
    case viewer

    var id: String { rawValue }
}

struct TeamOverview: Hashable {
    var totalGames: Int
    var wins: Int
    var losses: Int
    var pointsPerGame: Double
    var pointsAllowedPerGame: Double
    var averageMargin: Double
    var topScorers: [PlayerAverage]
}

struct PlayerAverage: Identifiable, Hashable {
    var id: String { playerName }
    var playerName: String
    var points: Double
    var assists: Double
    var rebounds: Double
    var trueShooting: Double
}

struct PlayerProgressPoint: Identifiable, Hashable {
    var id: String { "\(date)-\(playerName)" }
    var date: String
    var playerName: String
    var points: Int
    var assists: Int
    var rebounds: Int
}

struct UsageSnapshot: Identifiable, Hashable {
    var id: String { playerName }
    var playerName: String
    var usageRate: Double
    var pointsPerShot: Double
}

struct LineupRanking: Identifiable, Hashable {
    var id: UUID
    var players: [String]
    var netRating: Double
    var possessions: Int
}
