import Foundation

struct PlayerSummary: Identifiable, Hashable {
    var id: String { playerName }
    var playerName: String
    var gamesPlayed: Int
    var mpg: Double
    var ppg: Double
    var plusMinusAvg: Double
    var plusMinusTotal: Int
    var rpg: Double
    var orebpg: Double
    var drebpg: Double
    var apg: Double
    var spg: Double
    var bpg: Double
    var topg: Double
    var pfpg: Double
    var eff: Double
    var ortg: Double
    var ppp: Double
    var possPer40: Double
    var usgPct: Double
    var fgPct: Double
    var twoPtPct: Double
    var tpPct: Double
    var ftPct: Double
    var tsPct: Double
    var efgPct: Double
    var astTov: Double
    var ftaPct: Double
    var orebPct: Double
    var consistency: Double
    var fgm: Int
    var fga: Int
    var twoPtMade: Int
    var twoPtAtt: Int
    var tpm: Int
    var tpa: Int
    var ftm: Int
    var fta: Int
    var isTeamTotal: Bool = false

    static let zero = PlayerSummary(
        playerName: "",
        gamesPlayed: 0, mpg: 0, ppg: 0, plusMinusAvg: 0, plusMinusTotal: 0,
        rpg: 0, orebpg: 0, drebpg: 0, apg: 0, spg: 0, bpg: 0, topg: 0, pfpg: 0,
        eff: 0, ortg: 0, ppp: 0, possPer40: 0, usgPct: 0,
        fgPct: 0, twoPtPct: 0, tpPct: 0, ftPct: 0, tsPct: 0, efgPct: 0,
        astTov: 0, ftaPct: 0, orebPct: 0, consistency: 0,
        fgm: 0, fga: 0, twoPtMade: 0, twoPtAtt: 0, tpm: 0, tpa: 0, ftm: 0, fta: 0
    )
}

struct PlayerGameLogEntry: Identifiable, Hashable {
    var id: String { "\(game.id)-\(playerName)" }
    var game: Game
    var stat: PlayerStat
    var playerName: String
    var ortg: Double
    var ppp: Double
    var possPer40: Double
    var eff: Double
    var gmScore: Double
}

struct PlayerDetail: Hashable {
    var summary: PlayerSummary
    var totals: PlayerDetailTotals
    var averages: PlayerDetailAverages
    var careerHighs: PlayerDetailHighs
    var gameLog: [PlayerGameLogEntry]
}

struct PlayerDetailTotals: Hashable {
    var points: Int
    var rebounds: Int
    var offensiveRebounds: Int
    var defensiveRebounds: Int
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
    var plusMinus: Int
}

struct PlayerDetailAverages: Hashable {
    var mpg: Double
    var ppg: Double
    var rpg: Double
    var orebpg: Double
    var drebpg: Double
    var apg: Double
    var spg: Double
    var bpg: Double
    var topg: Double
    var pfpg: Double
    var plusMinus: Double
    var eff: Double
    var ortg: Double
    var ppp: Double
    var possPer40: Double
    var usgPct: Double
    var fgPct: Double
    var twoPtPct: Double
    var tpPct: Double
    var ftPct: Double
    var tsPct: Double
    var efgPct: Double
    var astTov: Double
    var ftaPct: Double
    var orebPct: Double
    var consistency: Double
}

struct PlayerDetailHighs: Hashable {
    var points: Int
    var rebounds: Int
    var assists: Int
    var steals: Int
    var blocks: Int
}

enum PlayerStatsComputer {
    static func possessions(for stat: PlayerStat) -> Double {
        Double(stat.fieldGoalAttempts - stat.offensiveRebounds) + Double(stat.turnovers) + 0.44 * Double(stat.freeThrowAttempts)
    }

    static func ortg(for stat: PlayerStat) -> Double {
        let poss = possessions(for: stat)
        guard poss > 0 else { return 0 }
        return Double(stat.points) / poss * 100
    }

    static func ppp(for stat: PlayerStat) -> Double {
        let poss = possessions(for: stat)
        guard poss > 0 else { return 0 }
        return Double(stat.points) / poss
    }

    static func tsPct(for stat: PlayerStat) -> Double {
        let denom = 2 * (Double(stat.fieldGoalAttempts) + 0.44 * Double(stat.freeThrowAttempts))
        guard denom > 0 else { return 0 }
        return Double(stat.points) / denom * 100
    }

    static func efgPct(for stat: PlayerStat) -> Double {
        guard stat.fieldGoalAttempts > 0 else { return 0 }
        return (Double(stat.fieldGoalsMade) + 0.5 * Double(stat.threePointsMade)) / Double(stat.fieldGoalAttempts) * 100
    }

    static func eff(for stat: PlayerStat) -> Double {
        Double(stat.points + stat.rebounds + stat.assists + stat.steals + stat.blocks)
            - Double((stat.fieldGoalAttempts - stat.fieldGoalsMade) + (stat.freeThrowAttempts - stat.freeThrowsMade) + stat.turnovers)
    }

    static func gmScore(for stat: PlayerStat) -> Double {
        Double(stat.points)
            + 0.4 * Double(stat.fieldGoalsMade) - 0.7 * Double(stat.fieldGoalAttempts)
            - 0.4 * Double(stat.freeThrowAttempts - stat.freeThrowsMade)
            + 0.7 * Double(stat.offensiveRebounds) + 0.3 * Double(stat.defensiveRebounds)
            + Double(stat.steals) + 0.7 * Double(stat.assists) + 0.7 * Double(stat.blocks)
            - 0.4 * Double(stat.fouls) - Double(stat.turnovers)
    }

    static func minutesToDouble(_ minutes: Int) -> Double {
        Double(minutes) / 60
    }

    static func summary(for stats: [PlayerStat], gamesPlayed: Int) -> PlayerSummary {
        guard !stats.isEmpty, gamesPlayed > 0 else { return .zero }
        let gamesD = Double(gamesPlayed)
        let minutesTotal = stats.reduce(0) { $0 + $1.minutes }
        let minutesD = Double(minutesTotal) / 60
        let mpg = minutesD / gamesD
        let ppg = Double(stats.reduce(0) { $0 + $1.points }) / gamesD
        let rpg = Double(stats.reduce(0) { $0 + $1.rebounds }) / gamesD
        let orebpg = Double(stats.reduce(0) { $0 + $1.offensiveRebounds }) / gamesD
        let drebpg = Double(stats.reduce(0) { $0 + $1.defensiveRebounds }) / gamesD
        let apg = Double(stats.reduce(0) { $0 + $1.assists }) / gamesD
        let spg = Double(stats.reduce(0) { $0 + $1.steals }) / gamesD
        let bpg = Double(stats.reduce(0) { $0 + $1.blocks }) / gamesD
        let topg = Double(stats.reduce(0) { $0 + $1.turnovers }) / gamesD
        let pfpg = Double(stats.reduce(0) { $0 + $1.fouls }) / gamesD
        let plusMinusTotal = stats.reduce(0) { $0 + $1.plusMinus }
        let fgm = stats.reduce(0) { $0 + $1.fieldGoalsMade }
        let fga = stats.reduce(0) { $0 + $1.fieldGoalAttempts }
        let tpm = stats.reduce(0) { $0 + $1.threePointsMade }
        let tpa = stats.reduce(0) { $0 + $1.threePointAttempts }
        let ftm = stats.reduce(0) { $0 + $1.freeThrowsMade }
        let fta = stats.reduce(0) { $0 + $1.freeThrowAttempts }
        let twoPtMade = fgm - tpm
        let twoPtAtt = fga - tpa
        let teamPoss = stats.reduce(0.0) { $0 + possessions(for: $1) }
        let usage = stats.reduce(0.0) { $0 + Double($1.fieldGoalAttempts) + 0.44 * Double($1.freeThrowAttempts) + Double($1.turnovers) }
        let points = stats.reduce(0) { $0 + $1.points }
        let perGameRatingAvg = { (metric: (PlayerStat) -> Double) -> Double in
            let total = stats.map(metric).reduce(0, +)
            return total / Double(stats.count)
        }
        let avgTs = perGameRatingAvg(tsPct)
        let avgEfg = perGameRatingAvg(efgPct)
        let avgOrtg = perGameRatingAvg(ortg)
        let avgPpp = perGameRatingAvg(ppp)
        let fgPct = fga > 0 ? Double(fgm) / Double(fga) * 100 : 0
        let twoPtPct = twoPtAtt > 0 ? Double(twoPtMade) / Double(twoPtAtt) * 100 : 0
        let tpPct = tpa > 0 ? Double(tpm) / Double(tpa) * 100 : 0
        let ftPct = fta > 0 ? Double(ftm) / Double(fta) * 100 : 0
        let astTov = {
            let tov = stats.reduce(0) { $0 + $1.turnovers }
            let ast = stats.reduce(0) { $0 + $1.assists }
            return tov > 0 ? Double(ast) / Double(tov) : Double(ast)
        }()
        let mean = Double(points) / gamesD
        let variance = stats.map { pow(Double($0.points) - mean, 2) }.reduce(0, +) / Double(max(stats.count - 1, 1))
        let cv = mean > 0 ? sqrt(variance) / mean * 100 : 0

        return PlayerSummary(
            playerName: stats.first?.playerName ?? "",
            gamesPlayed: gamesPlayed,
            mpg: mpg,
            ppg: ppg,
            plusMinusAvg: gamesD > 0 ? Double(plusMinusTotal) / gamesD : 0,
            plusMinusTotal: plusMinusTotal,
            rpg: rpg,
            orebpg: orebpg,
            drebpg: drebpg,
            apg: apg,
            spg: spg,
            bpg: bpg,
            topg: topg,
            pfpg: pfpg,
            eff: Double(points + stats.reduce(0) { $0 + $1.rebounds + $1.assists + $1.steals + $1.blocks }
                - (fga - fgm + fta - ftm + stats.reduce(0) { $0 + $1.turnovers })) / gamesD,
            ortg: avgOrtg,
            ppp: avgPpp,
            possPer40: minutesD > 0 ? Double(points) / minutesD * 40 : 0,
            usgPct: teamPoss > 0 ? usage / teamPoss * 100 : 0,
            fgPct: fgPct,
            twoPtPct: twoPtPct,
            tpPct: tpPct,
            ftPct: ftPct,
            tsPct: avgTs,
            efgPct: avgEfg,
            astTov: astTov,
            ftaPct: fga > 0 ? Double(fta) / Double(fga) * 100 : 0,
            orebPct: 0,
            consistency: cv,
            fgm: fgm,
            fga: fga,
            twoPtMade: twoPtMade,
            twoPtAtt: twoPtAtt,
            tpm: tpm,
            tpa: tpa,
            ftm: ftm,
            fta: fta
        )
    }

    static func teamSummary(from games: [Game]) -> PlayerSummary {
        let stats = games.flatMap(\.playerStats)
        var summary = summary(for: stats, gamesPlayed: games.count)
        summary.playerName = "TEAM TOTAL"
        summary.isTeamTotal = true
        summary.plusMinusTotal = games.reduce(0) { $0 + $1.teamScore - $1.opponentScore }
        return summary
    }

    static func summaries(for games: [Game]) -> [PlayerSummary] {
        let grouped = Dictionary(grouping: games.flatMap(\.playerStats), by: \.playerName)
        return grouped.map { name, stats in
            var s = summary(for: stats, gamesPlayed: games.count)
            s.playerName = name
            return s
        }
        .sorted { $0.ppg > $1.ppg }
    }

    static func detail(for playerName: String, in games: [Game]) -> PlayerDetail {
        if playerName == "__team_total__" {
            return teamDetail(from: games)
        }
        let stats = games
            .sorted { $0.date < $1.date }
            .compactMap { game -> (game: Game, stat: PlayerStat)? in
                guard let stat = game.playerStats.first(where: { $0.playerName == playerName }) else { return nil }
                return (game, stat)
            }
        return buildDetail(playerName: playerName, stats: stats)
    }

    static func teamDetail(from games: [Game]) -> PlayerDetail {
        let stats = games
            .sorted { $0.date < $1.date }
            .compactMap { game -> (game: Game, stat: PlayerStat)? in
                let players = game.playerStats
                guard !players.isEmpty else { return nil }
                return (game, aggregate(players, game: game))
            }
        var detail = buildDetail(playerName: "Team Total", stats: stats)
        var summary = detail.summary
        summary.isTeamTotal = true
        summary.plusMinusTotal = games.reduce(0) { $0 + $1.teamScore - $1.opponentScore }
        detail.summary = summary
        return detail
    }

    private static func aggregate(_ stats: [PlayerStat], game: Game) -> PlayerStat {
        PlayerStat(
            id: UUID(),
            playerName: "Team Total",
            points: stats.reduce(0) { $0 + $1.points },
            minutes: stats.reduce(0) { $0 + $1.minutes },
            rebounds: stats.reduce(0) { $0 + $1.rebounds },
            assists: stats.reduce(0) { $0 + $1.assists },
            steals: stats.reduce(0) { $0 + $1.steals },
            blocks: stats.reduce(0) { $0 + $1.blocks },
            turnovers: stats.reduce(0) { $0 + $1.turnovers },
            fouls: stats.reduce(0) { $0 + $1.fouls },
            fieldGoalsMade: stats.reduce(0) { $0 + $1.fieldGoalsMade },
            fieldGoalAttempts: stats.reduce(0) { $0 + $1.fieldGoalAttempts },
            threePointsMade: stats.reduce(0) { $0 + $1.threePointsMade },
            threePointAttempts: stats.reduce(0) { $0 + $1.threePointAttempts },
            freeThrowsMade: stats.reduce(0) { $0 + $1.freeThrowsMade },
            freeThrowAttempts: stats.reduce(0) { $0 + $1.freeThrowAttempts },
            offensiveRebounds: stats.reduce(0) { $0 + $1.offensiveRebounds },
            defensiveRebounds: stats.reduce(0) { $0 + $1.defensiveRebounds },
            plusMinus: game.teamScore - game.opponentScore,
            reboundsConceded: 0
        )
    }

    private static func buildDetail(playerName: String, stats: [(game: Game, stat: PlayerStat)]) -> PlayerDetail {
        let gamesPlayed = stats.count
        let summary = self.summary(for: stats.map(\.stat), gamesPlayed: gamesPlayed)

        let totals = PlayerDetailTotals(
            points: stats.reduce(0) { $0 + $1.stat.points },
            rebounds: stats.reduce(0) { $0 + $1.stat.rebounds },
            offensiveRebounds: stats.reduce(0) { $0 + $1.stat.offensiveRebounds },
            defensiveRebounds: stats.reduce(0) { $0 + $1.stat.defensiveRebounds },
            assists: stats.reduce(0) { $0 + $1.stat.assists },
            steals: stats.reduce(0) { $0 + $1.stat.steals },
            blocks: stats.reduce(0) { $0 + $1.stat.blocks },
            turnovers: stats.reduce(0) { $0 + $1.stat.turnovers },
            fouls: stats.reduce(0) { $0 + $1.stat.fouls },
            fieldGoalsMade: stats.reduce(0) { $0 + $1.stat.fieldGoalsMade },
            fieldGoalAttempts: stats.reduce(0) { $0 + $1.stat.fieldGoalAttempts },
            threePointsMade: stats.reduce(0) { $0 + $1.stat.threePointsMade },
            threePointAttempts: stats.reduce(0) { $0 + $1.stat.threePointAttempts },
            freeThrowsMade: stats.reduce(0) { $0 + $1.stat.freeThrowsMade },
            freeThrowAttempts: stats.reduce(0) { $0 + $1.stat.freeThrowAttempts },
            plusMinus: stats.reduce(0) { $0 + $1.stat.plusMinus }
        )

        let averages = PlayerDetailAverages(
            mpg: summary.mpg,
            ppg: summary.ppg,
            rpg: summary.rpg,
            orebpg: summary.orebpg,
            drebpg: summary.drebpg,
            apg: summary.apg,
            spg: summary.spg,
            bpg: summary.bpg,
            topg: summary.topg,
            pfpg: summary.pfpg,
            plusMinus: summary.plusMinusAvg,
            eff: summary.eff,
            ortg: summary.ortg,
            ppp: summary.ppp,
            possPer40: summary.possPer40,
            usgPct: summary.usgPct,
            fgPct: summary.fgPct,
            twoPtPct: summary.twoPtPct,
            tpPct: summary.tpPct,
            ftPct: summary.ftPct,
            tsPct: summary.tsPct,
            efgPct: summary.efgPct,
            astTov: summary.astTov,
            ftaPct: summary.ftaPct,
            orebPct: summary.orebPct,
            consistency: summary.consistency
        )

        let gameLog = stats.reversed().map { entry -> PlayerGameLogEntry in
            let s = entry.stat
            return PlayerGameLogEntry(
                game: entry.game,
                stat: s,
                playerName: playerName,
                ortg: ortg(for: s),
                ppp: ppp(for: s),
                possPer40: minutesToDouble(s.minutes) > 0 ? Double(s.points) / minutesToDouble(s.minutes) * 40 : 0,
                eff: eff(for: s),
                gmScore: gmScore(for: s)
            )
        }

        return PlayerDetail(
            summary: summary,
            totals: totals,
            averages: averages,
            careerHighs: PlayerDetailHighs(
                points: stats.map(\.stat.points).max() ?? 0,
                rebounds: stats.map(\.stat.rebounds).max() ?? 0,
                assists: stats.map(\.stat.assists).max() ?? 0,
                steals: stats.map(\.stat.steals).max() ?? 0,
                blocks: stats.map(\.stat.blocks).max() ?? 0
            ),
            gameLog: gameLog
        )
    }
}
