import Foundation

struct OpponentAction: Codable, Hashable, Identifiable {
    let id: UUID
    var eventID: UUID
    var kind: LiveGameEventKind
    var points: Int
    var result: ShotResult
    var detail: String
}

func inferShotZone(x: Double, y: Double, shotType: ShotType) -> ShotZone {
    let dx = x - 250
    let dy = y - 50
    let distance = (dx * dx + dy * dy).squareRoot()
    if distance <= 40 { return .rim }
    if distance <= 100 { return .paint }
    if shotType == .threePoint {
        return y < 140 ? .cornerThree : .aboveBreakThree
    }
    return .midrange
}

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

    var quarterSeconds: Int = 0
    var gameSeconds: Int = 0
    var clockStartedAt: Date?
    var playerSeconds: [String: Int] = [:]
    var stintStartedAt: [String: Date] = [:]
    var oppRecentActions: [OpponentAction] = []

    static let quarterLengthSeconds = 600

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

    // MARK: - Clock

    mutating func toggleClock() {
        if isClockRunning {
            commitClockTime()
            commitPlayerMinutes()
            isClockRunning = false
            clockStartedAt = nil
        } else {
            let now = Date.now
            clockStartedAt = now
            for player in activeLineup { stintStartedAt[player] = now }
            isClockRunning = true
        }
    }

    mutating func commitClockTime() {
        guard isClockRunning, let start = clockStartedAt else { return }
        let delta = max(0, Int(Date.now.timeIntervalSince(start)))
        if delta > 0 {
            quarterSeconds += delta
            gameSeconds += delta
        }
        clockStartedAt = nil
    }

    mutating func commitPlayerMinutes() {
        for player in activeLineup {
            if let start = stintStartedAt[player] {
                playerSeconds[player, default: 0] += max(0, Int(Date.now.timeIntervalSince(start)))
            }
        }
        stintStartedAt.removeAll()
    }

    func displayedQuarterSeconds(at date: Date) -> Int {
        quarterSeconds + runningDelta(at: date)
    }

    func displayedGameSeconds(at date: Date) -> Int {
        gameSeconds + runningDelta(at: date)
    }

    func displayedSeconds(for player: String, at date: Date) -> Int {
        var total = playerSeconds[player] ?? 0
        if activeLineup.contains(player), isClockRunning, let start = stintStartedAt[player] {
            total += max(0, Int(date.timeIntervalSince(start)))
        }
        return total
    }

    func timeRemaining(at date: Date) -> String {
        let remaining = max(0, Self.quarterLengthSeconds - displayedQuarterSeconds(at: date))
        return Self.clockString(seconds: remaining)
    }

    private func runningDelta(at date: Date) -> Int {
        guard isClockRunning, let start = clockStartedAt else { return 0 }
        return max(0, Int(date.timeIntervalSince(start)))
    }

    static func clockString(seconds: Int) -> String {
        "\(seconds / 60):\(String(format: "%02d", seconds % 60))"
    }

    // MARK: - Lineup

    mutating func advanceQuarter() {
        guard quarter < 5 else { return }
        commitClockTime()
        commitAndRestartStints()
        closeCurrentLineupSegmentIfNeeded()
        quarter += 1
        isClockRunning = false
        quarterSeconds = 0
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

        commitClockTime()
        commitAndRestartStints()
        closeCurrentLineupSegmentIfNeeded()
        activeLineup[outgoingIndex] = incoming
        recordEvent(
            .substitution,
            playerName: incoming,
            detail: "IN:\(incoming) OUT:\(outgoing)",
            playID: selectedPlayID,
            createsPossession: false
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

        commitClockTime()
        commitAndRestartStints()
        closeCurrentLineupSegmentIfNeeded()
        activeLineup = normalized
        recordEvent(
            .substitution,
            playerName: nil,
            detail: "LINEUP:\(normalized.joined(separator: ", "))",
            playID: selectedPlayID,
            createsPossession: false
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

    // MARK: - Events

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
        case .freeThrowTrip:
            homeScore -= freeThrowMadeCount(from: removed.detail)
        case .awayTwoMade:
            awayScore -= 2
        case .awayThreeMade:
            awayScore -= 3
        case .awayFreeThrowMade:
            awayScore -= 1
        default:
            break
        }

        shotEvents.removeAll { $0.eventID == removed.id }
        oppRecentActions.removeAll { $0.eventID == removed.id }

        rebuildDerivedSegments()
    }

    @discardableResult
    mutating func recordEvent(
        _ kind: LiveGameEventKind,
        playerName: String?,
        detail: String = "",
        playID: UUID?,
        createsPossession: Bool = true,
        xLocation: Double? = nil,
        yLocation: Double? = nil
    ) -> UUID {
        commitClockTime()
        applyScore(for: kind)

        let event = RecordedGameEvent(
            id: UUID(),
            quarter: quarter,
            eventIndex: events.count + 1,
            playerName: playerName,
            kind: kind,
            timestamp: .now,
            timeRemaining: timeRemaining(at: .now),
            scoreMargin: homeScore - awayScore,
            detail: detail,
            playID: playID,
            lineupSegmentID: lineupSegments.last?.id,
            taggedLineup: activeLineup
        )

        events.append(event)

        if kind.isShotEvent, !kind.isOpponentEvent {
            shotEvents.append(makeShotEvent(for: kind, playerName: playerName, eventID: event.id, playID: playID, xLocation: xLocation, yLocation: yLocation))
        }

        if kind.isOpponentEvent {
            trackOpponentAction(for: event)
        }

        if createsPossession {
            appendPossessionIfNeeded(for: kind)
        }

        rebuildDerivedSegments()
        return event.id
    }

    mutating func recordFreeThrowTrip(player: String, totalFt: Int, made: Int, playID: UUID?) -> UUID {
        commitClockTime()
        let clampedMade = min(max(made, 0), totalFt)
        homeScore += clampedMade

        let event = RecordedGameEvent(
            id: UUID(),
            quarter: quarter,
            eventIndex: events.count + 1,
            playerName: player,
            kind: .freeThrowTrip,
            timestamp: .now,
            timeRemaining: timeRemaining(at: .now),
            scoreMargin: homeScore - awayScore,
            detail: "\(clampedMade)/\(totalFt) FT",
            playID: playID,
            lineupSegmentID: lineupSegments.last?.id,
            taggedLineup: activeLineup
        )

        events.append(event)

        for attempt in 0..<totalFt {
            let madeAttempt = attempt < clampedMade
            shotEvents.append(
                ShotEvent(
                    id: UUID(),
                    gameID: nil,
                    playerName: player,
                    shotType: .freeThrow,
                    result: madeAttempt ? .made : .missed,
                    points: madeAttempt ? 1 : 0,
                    xLocation: nil,
                    yLocation: nil,
                    zone: .freeThrow,
                    quarter: quarter,
                    playID: playID,
                    eventID: event.id
                )
            )
        }

        possessions.append(
            Possession(
                id: UUID(),
                gameID: nil,
                number: possessions.count + 1,
                quarter: quarter,
                startingLineup: activeLineup,
                result: .score
            )
        )

        rebuildDerivedSegments()
        return event.id
    }

    mutating func attachPlay(_ playID: UUID?, toEventID eventID: UUID) {
        guard let index = events.firstIndex(where: { $0.id == eventID }) else { return }
        events[index].playID = playID
        for i in shotEvents.indices where shotEvents[i].eventID == eventID {
            shotEvents[i].playID = playID
        }
        selectedPlayID = playID
    }

    mutating func attachOpponentShotLocation(x: Double, y: Double, toEventID eventID: UUID) {
        guard let index = events.firstIndex(where: { $0.id == eventID }) else { return }
        events[index].detail = "x_loc:\(Int(x)) y_loc:\(Int(y))"
    }

    mutating func removeOpponentAction(eventID: UUID) {
        guard let index = events.firstIndex(where: { $0.id == eventID }) else { return }
        let event = events.remove(at: index)

        if event.kind.pointsValue > 0 {
            awayScore = max(0, awayScore - event.kind.pointsValue)
        }

        shotEvents.removeAll { $0.eventID == event.id }
        oppRecentActions.removeAll { $0.eventID == eventID }

        rebuildDerivedSegments()
    }

    mutating func makeCompletedGame() -> Game {
        commitClockTime()
        commitPlayerMinutes()

        var byPlayer = events.reduce(into: [String: PlayerStat]()) { partial, event in
            var stat = partial[event.playerName ?? ""] ?? PlayerStat(id: UUID(), playerName: event.playerName ?? "", points: 0, minutes: 0, rebounds: 0, assists: 0, steals: 0, blocks: 0, turnovers: 0, fouls: 0, fieldGoalsMade: 0, fieldGoalAttempts: 0, threePointsMade: 0, threePointAttempts: 0, freeThrowsMade: 0, freeThrowAttempts: 0, offensiveRebounds: 0, defensiveRebounds: 0, plusMinus: 0, reboundsConceded: 0)

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
            case .freeThrowTrip:
                let made = freeThrowMadeCount(from: event.detail)
                let total = freeThrowTotalCount(from: event.detail)
                stat.points += made
                stat.freeThrowsMade += made
                stat.freeThrowAttempts += total
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

            partial[event.playerName ?? ""] = stat
        }

        for event in events where event.kind == .opponentOffensiveRebound {
            for name in event.taggedLineup {
                guard var stat = byPlayer[name] else { continue }
                stat.reboundsConceded += 1
                byPlayer[name] = stat
            }
        }

        let playerStats = byPlayer.values
            .filter { !$0.playerName.isEmpty }
            .map { stat -> PlayerStat in
                var stat = stat
                stat.minutes = Int(Double(playerSeconds[stat.playerName] ?? 0) / 60)
                return stat
            }
            .sorted { lhs, rhs in
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

    // MARK: - Private helpers

    private mutating func commitAndRestartStints() {
        commitPlayerMinutes()
        if isClockRunning {
            let now = Date.now
            for player in activeLineup { stintStartedAt[player] = now }
        }
    }

    private func makeShotEvent(for kind: LiveGameEventKind, playerName: String?, eventID: UUID, playID: UUID?, xLocation: Double?, yLocation: Double?) -> ShotEvent {
        let shotType: ShotType
        let result: ShotResult

        switch kind {
        case .homeTwoMade, .homeTwoMissed:
            shotType = .twoPoint
            result = kind == .homeTwoMade ? .made : .missed
        case .homeThreeMade, .homeThreeMissed:
            shotType = .threePoint
            result = kind == .homeThreeMade ? .made : .missed
        default:
            shotType = .freeThrow
            result = kind == .homeFreeThrowMade ? .made : .missed
        }

        let zone: ShotZone
        if let xLocation, let yLocation {
            zone = inferShotZone(x: xLocation, y: yLocation, shotType: shotType)
        } else {
            zone = shotType == .threePoint ? .aboveBreakThree : (shotType == .twoPoint ? .paint : .freeThrow)
        }

        return ShotEvent(
            id: UUID(),
            gameID: nil,
            playerName: playerName,
            shotType: shotType,
            result: result,
            points: kind.pointsValue,
            xLocation: xLocation,
            yLocation: yLocation,
            zone: zone,
            quarter: quarter,
            playID: playID,
            eventID: eventID
        )
    }

    private mutating func trackOpponentAction(for event: RecordedGameEvent) {
        let action = OpponentAction(
            id: UUID(),
            eventID: event.id,
            kind: event.kind,
            points: event.kind.pointsValue,
            result: event.kind.isScoringEvent ? .made : .missed,
            detail: event.detail
        )
        oppRecentActions.append(action)
        if oppRecentActions.count > 10 {
            oppRecentActions.removeFirst()
        }
    }

    private func freeThrowMadeCount(from detail: String) -> Int {
        Int(detail.split(separator: "/").first ?? "") ?? 0
    }

    private func freeThrowTotalCount(from detail: String) -> Int {
        let totalPart = detail.split(separator: "/").last ?? ""
        return Int(totalPart.trimmingCharacters(in: CharacterSet(charactersIn: " FT"))) ?? 0
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
            case .freeThrowTrip:
                rebuilt[index].pointsScored += freeThrowMadeCount(from: event.detail)
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
    case freeThrowTrip
    case opponentOffensiveRebound

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
        case .freeThrowTrip: "Free Throws"
        case .opponentOffensiveRebound: "Opp O-Rebound"
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
        case .freeThrowTrip: "target"
        case .opponentOffensiveRebound: "arrow.up.forward.circle"
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
        case .assist, .rebound, .offensiveRebound, .block, .steal, .turnover, .foul, .homeTwoMade, .homeThreeMade, .homeFreeThrowMade, .homeTwoMissed, .homeThreeMissed, .homeFreeThrowMissed, .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed, .freeThrowTrip, .opponentOffensiveRebound:
            true
        case .substitution:
            false
        }
    }

    var possessionResult: PossessionResult {
        switch self {
        case .homeTwoMade, .homeThreeMade, .homeFreeThrowMade, .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .freeThrowTrip:
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

    var isOpponentEvent: Bool {
        switch self {
        case .awayTwoMade, .awayThreeMade, .awayFreeThrowMade, .awayTwoMissed, .awayThreeMissed, .awayFreeThrowMissed, .opponentOffensiveRebound:
            true
        default:
            false
        }
    }

    var isScoringEvent: Bool {
        pointsValue > 0
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
