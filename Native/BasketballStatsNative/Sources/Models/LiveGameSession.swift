import Foundation

struct LiveGameSession: Codable, Hashable {
    var id: UUID
    var createdAt: Date
    var opponent: String
    var quarter: Int
    var isClockRunning: Bool
    var homeScore: Int
    var awayScore: Int
    var roster: [String]
    var startingLineup: [String]
    var activeLineup: [String]
    var gameType: GameType
    var selectedPlayID: UUID?
    var possessions: [Possession]
    var shotEvents: [ShotEvent]
    var events: [RecordedGameEvent]
    var lineupSegments: [LineupSegment]
    var syncState: SyncState

    static let empty = LiveGameSession(
        id: UUID(),
        createdAt: .now,
        opponent: "",
        quarter: 1,
        isClockRunning: false,
        homeScore: 0,
        awayScore: 0,
        roster: [],
        startingLineup: [],
        activeLineup: [],
        gameType: .season,
        selectedPlayID: nil,
        possessions: [],
        shotEvents: [],
        events: [],
        lineupSegments: [],
        syncState: .localOnly
    )

    static func newGame(opponent: String, roster: [String], startingLineup: [String]?, gameType: GameType) -> LiveGameSession {
        let trimmedRoster = roster.map(\.trimmedForRoster).filter { !$0.isEmpty }
        let trimmedLineup = (startingLineup ?? Array(trimmedRoster.prefix(5)))
            .map(\.trimmedForRoster)
            .filter { !$0.isEmpty }
        let initialLineup = trimmedLineup.isEmpty ? Array(trimmedRoster.prefix(5)) : trimmedLineup

        return LiveGameSession(
            id: UUID(),
            createdAt: .now,
            opponent: opponent.trimmedForRoster,
            quarter: 1,
            isClockRunning: false,
            homeScore: 0,
            awayScore: 0,
            roster: trimmedRoster,
            startingLineup: initialLineup,
            activeLineup: initialLineup,
            gameType: gameType,
            selectedPlayID: nil,
            possessions: [
                Possession(
                    id: UUID(),
                    gameID: nil,
                    number: 1,
                    quarter: 1,
                    startingLineup: initialLineup,
                    result: .deadBall
                )
            ],
            shotEvents: [],
            events: [],
            lineupSegments: [
                LineupSegment(
                    id: UUID(),
                    quarter: 1,
                    players: initialLineup,
                    startEventIndex: 1,
                    endEventIndex: nil,
                    pointsScored: 0,
                    pointsAllowed: 0,
                    possessions: 0,
                    displayName: nil
                )
            ],
            syncState: .localOnly
        )
    }

    var isConfigured: Bool {
        !opponent.isEmpty && !roster.isEmpty && !activeLineup.isEmpty
    }

    mutating func selectPlay(_ playID: UUID?) {
        selectedPlayID = playID
    }

    mutating func toggleClock() {
        isClockRunning.toggle()
    }

    mutating func advanceQuarter() {
        closeCurrentLineupSegmentIfNeeded()
        quarter += 1
        isClockRunning = false
        possessions.append(
            Possession(
                id: UUID(),
                gameID: nil,
                number: possessions.count + 1,
                quarter: quarter,
                startingLineup: activeLineup,
                result: .deadBall
            )
        )
        lineupSegments.append(
            LineupSegment(
                id: UUID(),
                quarter: quarter,
                players: activeLineup,
                startEventIndex: events.count + 1,
                endEventIndex: nil,
                pointsScored: 0,
                pointsAllowed: 0,
                possessions: 0,
                displayName: nil
            )
        )
    }

    mutating func substitute(outgoing: String, incoming: String) {
        guard let outgoingIndex = activeLineup.firstIndex(of: outgoing), !incoming.isEmpty else { return }
        guard !activeLineup.contains(incoming) else { return }

        closeCurrentLineupSegmentIfNeeded()
        activeLineup[outgoingIndex] = incoming
        recordEvent(
            .substitution,
            playerName: incoming,
            detail: "IN:\(incoming) OUT:\(outgoing)",
            playID: selectedPlayID,
            createsPossession: false,
            shotEvent: nil
        )
        lineupSegments.append(
            LineupSegment(
                id: UUID(),
                quarter: quarter,
                players: activeLineup,
                startEventIndex: events.count + 1,
                endEventIndex: nil,
                pointsScored: 0,
                pointsAllowed: 0,
                possessions: 0,
                displayName: nil
            )
        )
    }

    mutating func setActiveLineup(_ players: [String]) {
        let normalized = players
            .map(\.trimmedForRoster)
            .filter { !$0.isEmpty }

        guard normalized.count == 5 else { return }
        guard Set(normalized).count == 5 else { return }
        guard normalized != activeLineup else { return }

        closeCurrentLineupSegmentIfNeeded()
        activeLineup = normalized
        recordEvent(
            .substitution,
            playerName: nil,
            detail: "LINEUP:\(normalized.joined(separator: ", "))",
            playID: selectedPlayID,
            createsPossession: false,
            shotEvent: nil
        )
        lineupSegments.append(
            LineupSegment(
                id: UUID(),
                quarter: quarter,
                players: activeLineup,
                startEventIndex: events.count + 1,
                endEventIndex: nil,
                pointsScored: 0,
                pointsAllowed: 0,
                possessions: 0,
                displayName: nil
            )
        )
    }

    mutating func undoLastEvent() {
        guard let removed = events.popLast() else { return }
        selectedPlayID = removed.playID

        switch removed.kind {
        case .homeTwoMade:
            homeScore -= 2
        case .homeThreeMade:
            homeScore -= 3
        case .homeFreeThrowMade:
            homeScore -= 1
        case .awayTwoMade:
            awayScore -= 2
        case .awayThreeMade:
            awayScore -= 3
        case .awayFreeThrowMade:
            awayScore -= 1
        default:
            break
        }

        if removed.kind.isShotEvent, !shotEvents.isEmpty {
            shotEvents.removeLast()
        }

        rebuildDerivedSegments()
    }

    mutating func recordEvent(
        _ kind: LiveGameEventKind,
        playerName: String?,
        detail: String = "",
        playID: UUID?,
        createsPossession: Bool = true,
        shotEvent: ShotEvent? = nil
    ) {
        applyScore(for: kind)

        let event = RecordedGameEvent(
            id: UUID(),
            quarter: quarter,
            eventIndex: events.count + 1,
            playerName: playerName,
            kind: kind,
            timestamp: .now,
            timeRemaining: nil,
            scoreMargin: homeScore - awayScore,
            detail: detail,
            playID: playID,
            lineupSegmentID: lineupSegments.last?.id,
            taggedLineup: activeLineup
        )

        events.append(event)

        if let shotEvent {
            self.shotEvents.append(shotEvent)
        }

        if createsPossession {
            appendPossessionIfNeeded(for: kind)
        }

        rebuildDerivedSegments()
    }

    func makeCompletedGame() -> Game {
        let byPlayer = events.reduce(into: [String: PlayerStat]()) { partial, event in
            guard let playerName = event.playerName, !playerName.isEmpty else { return }
            var stat = partial[playerName] ?? PlayerStat(id: UUID(), playerName: playerName, points: 0, minutes: 0, rebounds: 0, assists: 0, steals: 0, blocks: 0, turnovers: 0, fouls: 0, fieldGoalsMade: 0, fieldGoalAttempts: 0, threePointsMade: 0, threePointAttempts: 0, freeThrowsMade: 0, freeThrowAttempts: 0, offensiveRebounds: 0, defensiveRebounds: 0, plusMinus: 0, reboundsConceded: 0)

            switch event.kind {
            case .homeTwoMade:
                stat.points += 2
                stat.fieldGoalsMade += 1
                stat.fieldGoalAttempts += 1
            case .homeThreeMade:
                stat.points += 3
                stat.fieldGoalsMade += 1
                stat.fieldGoalAttempts += 1
                stat.threePointsMade += 1
                stat.threePointAttempts += 1
            case .homeFreeThrowMade:
                stat.points += 1
                stat.freeThrowsMade += 1
                stat.freeThrowAttempts += 1
            case .homeTwoMissed:
                stat.fieldGoalAttempts += 1
            case .homeThreeMissed:
                stat.fieldGoalAttempts += 1
                stat.threePointAttempts += 1
            case .homeFreeThrowMissed:
                stat.freeThrowAttempts += 1
            case .rebound:
                stat.rebounds += 1
                stat.defensiveRebounds += 1
            case .offensiveRebound:
                stat.rebounds += 1
                stat.offensiveRebounds += 1
            case .assist:
                stat.assists += 1
            case .steal:
                stat.steals += 1
            case .block:
                stat.blocks += 1
            case .turnover:
                stat.turnovers += 1
            case .foul:
                stat.fouls += 1
            default:
                break
            }

            partial[playerName] = stat
        }

        let playerStats = byPlayer.values.sorted { lhs, rhs in
            if lhs.points == rhs.points { return lhs.playerName < rhs.playerName }
            return lhs.points > rhs.points
        }

        return Game(
            id: id,
            externalReference: nil,
            date: createdAt,
            sortDate: createdAt.isoSortDate,
            opponent: opponent,
            teamScore: homeScore,
            opponentScore: awayScore,
            gameType: gameType,
            source: .live,
            playerStats: playerStats,
            shotEvents: shotEvents,
            events: events,
            lineupSegments: lineupSegments,
            notes: "Imported from offline live-game session",
            syncState: .pendingUpload,
            schemaVersion: 4,
            createdAt: createdAt,
            updatedAt: .now
        )
    }

    private mutating func applyScore(for kind: LiveGameEventKind) {
        switch kind {
        case .homeTwoMade:
            homeScore += 2
        case .homeThreeMade:
            homeScore += 3
        case .homeFreeThrowMade:
            homeScore += 1
        case .awayTwoMade:
            awayScore += 2
        case .awayThreeMade:
            awayScore += 3
        case .awayFreeThrowMade:
            awayScore += 1
        default:
            break
        }
    }

    private mutating func appendPossessionIfNeeded(for kind: LiveGameEventKind) {
        guard kind.createsPossession else { return }
        possessions.append(
            Possession(
                id: UUID(),
                gameID: nil,
                number: possessions.count + 1,
                quarter: quarter,
                startingLineup: activeLineup,
                result: kind.possessionResult
            )
        )
    }

    private mutating func closeCurrentLineupSegmentIfNeeded() {
        guard !lineupSegments.isEmpty else { return }
        lineupSegments[lineupSegments.count - 1].endEventIndex = max(events.count, lineupSegments.last?.startEventIndex ?? 1)
    }

    private mutating func rebuildDerivedSegments() {
        var rebuilt: [LineupSegment] = lineupSegments.map {
            LineupSegment(
                id: $0.id,
                quarter: $0.quarter,
                players: $0.players,
                startEventIndex: $0.startEventIndex,
                endEventIndex: $0.endEventIndex,
                pointsScored: 0,
                pointsAllowed: 0,
                possessions: 0,
                displayName: $0.displayName
            )
        }

        for event in events {
            guard let index = rebuilt.lastIndex(where: { $0.id == event.lineupSegmentID }) else { continue }
            switch event.kind {
            case .homeTwoMade:
                rebuilt[index].pointsScored += 2
            case .homeThreeMade:
                rebuilt[index].pointsScored += 3
            case .homeFreeThrowMade:
                rebuilt[index].pointsScored += 1
            case .awayTwoMade:
                rebuilt[index].pointsAllowed += 2
            case .awayThreeMade:
                rebuilt[index].pointsAllowed += 3
            case .awayFreeThrowMade:
                rebuilt[index].pointsAllowed += 1
            default:
                break
            }

            if event.kind.createsPossession {
                rebuilt[index].possessions += 1
            }
        }

        lineupSegments = rebuilt
    }
}

enum LiveGameEventKind: String, Codable, CaseIterable, Hashable, Identifiable {
    case homeTwoMade
    case homeThreeMade
    case homeFreeThrowMade
    case homeTwoMissed
    case homeThreeMissed
    case homeFreeThrowMissed
    case awayTwoMade
    case awayThreeMade
    case awayFreeThrowMade
    case awayTwoMissed
    case awayThreeMissed
    case awayFreeThrowMissed
    case turnover
    case rebound
    case offensiveRebound
    case assist
    case steal
    case block
    case foul
    case substitution

    var id: String { rawValue }

    var title: String {
        switch self {
        case .homeTwoMade: "2PT Made"
        case .homeThreeMade: "3PT Made"
        case .homeFreeThrowMade: "FT Made"
        case .homeTwoMissed: "2PT Miss"
        case .homeThreeMissed: "3PT Miss"
        case .homeFreeThrowMissed: "FT Miss"
        case .awayTwoMade: "Opp 2PT"
        case .awayThreeMade: "Opp 3PT"
        case .awayFreeThrowMade: "Opp FT"
        case .awayTwoMissed: "Opp 2PT Miss"
        case .awayThreeMissed: "Opp 3PT Miss"
        case .awayFreeThrowMissed: "Opp FT Miss"
        case .turnover: "Turnover"
        case .rebound: "Rebound"
        case .offensiveRebound: "O-Rebound"
        case .assist: "Assist"
        case .steal: "Steal"
        case .block: "Block"
        case .foul: "Foul"
        case .substitution: "Substitution"
        }
    }

    var systemImage: String {
        switch self {
        case .homeTwoMade, .homeThreeMade, .homeFreeThrowMade: "plus.circle.fill"
        case .awayTwoMade, .awayThreeMade, .awayFreeThrowMade: "minus.circle.fill"
        case .homeTwoMissed, .homeThreeMissed, .homeFreeThrowMissed, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed:
            "xmark.circle.fill"
        case .turnover: "arrow.triangle.2.circlepath"
        case .rebound, .offensiveRebound: "basketball"
        case .assist: "figure.basketball"
        case .steal: "hand.raised.fill"
        case .block: "shield.fill"
        case .foul: "exclamationmark.triangle.fill"
        case .substitution: "arrow.left.arrow.right.circle.fill"
        }
    }

    var pointsValue: Int {
        switch self {
        case .homeTwoMade, .awayTwoMade: 2
        case .homeThreeMade, .awayThreeMade: 3
        case .homeFreeThrowMade, .awayFreeThrowMade: 1
        default: 0
        }
    }

    var createsPossession: Bool {
        switch self {
        case .assist, .rebound, .offensiveRebound, .block, .steal, .turnover, .foul, .homeTwoMade, .homeThreeMade, .homeFreeThrowMade, .homeTwoMissed, .homeThreeMissed, .homeFreeThrowMissed, .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed:
            true
        case .substitution:
            false
        }
    }

    var possessionResult: PossessionResult {
        switch self {
        case .homeTwoMade, .homeThreeMade, .homeFreeThrowMade, .awayTwoMade, .awayThreeMade, .awayFreeThrowMade:
            .score
        case .homeTwoMissed, .homeThreeMissed, .homeFreeThrowMissed, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed:
            .miss
        case .turnover:
            .turnover
        case .foul:
            .foul
        default:
            .deadBall
        }
    }

    var isShotEvent: Bool {
        switch self {
        case .homeTwoMade, .homeThreeMade, .homeFreeThrowMade, .homeTwoMissed, .homeThreeMissed, .homeFreeThrowMissed, .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed:
            true
        default:
            false
        }
    }
}

private extension String {
    var trimmedForRoster: String {
        trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private extension Date {
    var isoSortDate: String {
        ISO8601DateFormatter().string(from: self).prefix(10).description
    }
}
