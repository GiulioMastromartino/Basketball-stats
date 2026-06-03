import Foundation

enum SampleData {
    static let playTypes: [PlayType] = [
        PlayType(id: UUID(), name: "Offense"),
        PlayType(id: UUID(), name: "Defense"),
        PlayType(id: UUID(), name: "Special"),
    ]

    static let users: [User] = LocalAuthService().defaultUsers()

    static let settings: [SystemSetting] = [
        SystemSetting(id: UUID(), key: "notify_game_added", value: "false", description: "Send a notification when a game is saved", updatedAt: .now),
        SystemSetting(id: UUID(), key: "attach_game_pdf", value: "false", description: "Attach a PDF when sharing reports", updatedAt: .now),
    ]

    static let plays: [Play] = [
        Play(
            id: UUID(uuidString: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa") ?? UUID(),
            name: "Horns Twist",
            description: "High-post entry into weak-side flare and ball-screen.",
            playType: "Offense",
            difficulty: "Medium",
            personnelRequired: "2 bigs, 3 guards",
            tags: ["horns", "flare", "secondary"],
            source: "native-seed",
            canvasScene: PlayCanvasScene(
                width: 500,
                height: 470,
                tokens: [
                    PlayToken(id: UUID(), number: "1", role: "PG", x: 250, y: 390),
                    PlayToken(id: UUID(), number: "5", role: "C", x: 180, y: 180),
                    PlayToken(id: UUID(), number: "4", role: "PF", x: 320, y: 180),
                ],
                connectors: [
                    PlayConnector(id: UUID(), kind: .pass, fromX: 250, fromY: 390, toX: 180, toY: 180),
                    PlayConnector(id: UUID(), kind: .screen, fromX: 320, fromY: 180, toX: 240, toY: 180),
                ],
                labels: [PlayLabel(id: UUID(), text: "Twist", x: 250, y: 120)]
            ),
            frames: [
                PlayFrame(id: UUID(), sequenceNumber: 1, caption: "Entry", focusPlayers: ["1", "5"], annotations: ["PG enters to left elbow"]),
                PlayFrame(id: UUID(), sequenceNumber: 2, caption: "Twist screen", focusPlayers: ["4", "1"], annotations: ["4 flips the angle and 1 attacks middle"]),
            ],
            createdAt: .now,
            updatedAt: .now
        )
    ]

    static let games: [Game] = [
        Game(
            id: UUID(uuidString: "11111111-1111-1111-1111-111111111111") ?? UUID(),
            externalReference: "sample-abbiategrasso",
            date: Calendar.current.date(byAdding: .day, value: -2, to: .now) ?? .now,
            sortDate: (Calendar.current.date(byAdding: .day, value: -2, to: .now) ?? .now).isoSortDate,
            opponent: "Abbiategrasso",
            teamScore: 74,
            opponentScore: 37,
            gameType: .season,
            source: .imported,
            playerStats: [
                PlayerStat(id: UUID(), playerName: "Mastromartino", points: 18, minutes: 31, rebounds: 6, assists: 7, steals: 2, blocks: 0, turnovers: 1, fouls: 2, fieldGoalsMade: 7, fieldGoalAttempts: 13, threePointsMade: 2, threePointAttempts: 5, freeThrowsMade: 2, freeThrowAttempts: 2, offensiveRebounds: 1, defensiveRebounds: 5, plusMinus: 18, reboundsConceded: 0),
                PlayerStat(id: UUID(), playerName: "Rossi", points: 14, minutes: 28, rebounds: 9, assists: 1, steals: 1, blocks: 1, turnovers: 2, fouls: 3, fieldGoalsMade: 5, fieldGoalAttempts: 11, threePointsMade: 1, threePointAttempts: 3, freeThrowsMade: 3, freeThrowAttempts: 4, offensiveRebounds: 3, defensiveRebounds: 6, plusMinus: 14, reboundsConceded: 1),
                PlayerStat(id: UUID(), playerName: "Bianchi", points: 11, minutes: 24, rebounds: 4, assists: 5, steals: 0, blocks: 0, turnovers: 1, fouls: 2, fieldGoalsMade: 4, fieldGoalAttempts: 9, threePointsMade: 1, threePointAttempts: 4, freeThrowsMade: 2, freeThrowAttempts: 3, offensiveRebounds: 0, defensiveRebounds: 4, plusMinus: 11, reboundsConceded: 0),
            ],
            shotEvents: [
                ShotEvent(id: UUID(), gameID: nil, playerName: "Mastromartino", shotType: .threePoint, result: .made, points: 3, xLocation: 360, yLocation: 120, zone: .aboveBreakThree, quarter: 1, playID: nil),
                ShotEvent(id: UUID(), gameID: nil, playerName: "Rossi", shotType: .twoPoint, result: .made, points: 2, xLocation: 250, yLocation: 110, zone: .paint, quarter: 2, playID: nil),
            ],
            events: [],
            lineupSegments: [
                LineupSegment(id: UUID(), quarter: 1, players: ["Mastromartino", "Rossi", "Bianchi", "Neri", "Verdi"], startEventIndex: 1, endEventIndex: 15, pointsScored: 20, pointsAllowed: 8, possessions: 12, displayName: "Starting Five"),
                LineupSegment(id: UUID(), quarter: 4, players: ["Mastromartino", "Rossi", "Bianchi", "Neri", "Verdi"], startEventIndex: 38, endEventIndex: 54, pointsScored: 18, pointsAllowed: 9, possessions: 11, displayName: "Closing Five"),
            ],
            notes: "Strong half-court defense and good spacing.",
            syncState: .synced,
            schemaVersion: 4,
            createdAt: .now,
            updatedAt: .now
        ),
        Game(
            id: UUID(uuidString: "22222222-2222-2222-2222-222222222222") ?? UUID(),
            externalReference: "sample-nebula",
            date: Calendar.current.date(byAdding: .day, value: -7, to: .now) ?? .now,
            sortDate: (Calendar.current.date(byAdding: .day, value: -7, to: .now) ?? .now).isoSortDate,
            opponent: "Nebula",
            teamScore: 72,
            opponentScore: 71,
            gameType: .season,
            source: .live,
            playerStats: [
                PlayerStat(id: UUID(), playerName: "Mastromartino", points: 22, minutes: 34, rebounds: 5, assists: 4, steals: 3, blocks: 0, turnovers: 2, fouls: 1, fieldGoalsMade: 8, fieldGoalAttempts: 16, threePointsMade: 3, threePointAttempts: 7, freeThrowsMade: 3, freeThrowAttempts: 4, offensiveRebounds: 1, defensiveRebounds: 4, plusMinus: 7, reboundsConceded: 0),
                PlayerStat(id: UUID(), playerName: "Verdi", points: 13, minutes: 26, rebounds: 8, assists: 3, steals: 1, blocks: 2, turnovers: 3, fouls: 4, fieldGoalsMade: 5, fieldGoalAttempts: 12, threePointsMade: 1, threePointAttempts: 4, freeThrowsMade: 2, freeThrowAttempts: 2, offensiveRebounds: 3, defensiveRebounds: 5, plusMinus: 4, reboundsConceded: 0),
            ],
            shotEvents: [],
            events: [],
            lineupSegments: [
                LineupSegment(id: UUID(), quarter: 4, players: ["Mastromartino", "Rossi", "Verdi", "Bianchi", "Neri"], startEventIndex: 30, endEventIndex: 44, pointsScored: 16, pointsAllowed: 14, possessions: 11, displayName: "Clutch Lineup"),
            ],
            notes: "Late-game lineup held up in clutch possessions.",
            syncState: .pendingUpload,
            schemaVersion: 4,
            createdAt: .now,
            updatedAt: .now
        ),
        Game(
            id: UUID(uuidString: "33333333-3333-3333-3333-333333333333") ?? UUID(),
            externalReference: "sample-aurora",
            date: Calendar.current.date(byAdding: .day, value: -13, to: .now) ?? .now,
            sortDate: (Calendar.current.date(byAdding: .day, value: -13, to: .now) ?? .now).isoSortDate,
            opponent: "Aurora",
            teamScore: 68,
            opponentScore: 60,
            gameType: .friendly,
            source: .manual,
            playerStats: [
                PlayerStat(id: UUID(), playerName: "Rossi", points: 17, minutes: 30, rebounds: 7, assists: 2, steals: 2, blocks: 0, turnovers: 2, fouls: 2, fieldGoalsMade: 6, fieldGoalAttempts: 13, threePointsMade: 2, threePointAttempts: 6, freeThrowsMade: 3, freeThrowAttempts: 4, offensiveRebounds: 2, defensiveRebounds: 5, plusMinus: 10, reboundsConceded: 0),
                PlayerStat(id: UUID(), playerName: "Bianchi", points: 10, minutes: 21, rebounds: 3, assists: 6, steals: 1, blocks: 0, turnovers: 1, fouls: 1, fieldGoalsMade: 4, fieldGoalAttempts: 8, threePointsMade: 1, threePointAttempts: 3, freeThrowsMade: 1, freeThrowAttempts: 2, offensiveRebounds: 0, defensiveRebounds: 3, plusMinus: 8, reboundsConceded: 0),
            ],
            shotEvents: [],
            events: [],
            lineupSegments: [],
            notes: "Friendly used for rotation testing.",
            syncState: .localOnly,
            schemaVersion: 4,
            createdAt: .now,
            updatedAt: .now
        ),
    ]

    static let bundle = AppDataBundle(
        games: games,
        liveSession: .empty,
        plays: plays,
        playTypes: playTypes,
        users: users,
        currentUserID: users.first?.id,
        systemSettings: settings,
        syncIssues: []
    )
}

private extension Date {
    var isoSortDate: String {
        ISO8601DateFormatter().string(from: self).prefix(10).description
    }
}
