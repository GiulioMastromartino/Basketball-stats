import Foundation

struct DashboardSummary {
    let totalGames: Int
    let wins: Int
    let losses: Int
    let pointsPerGame: Double
    let lastGame: Game?

    init(games: [Game]) {
        totalGames = games.count
        wins = games.filter { $0.result == .win }.count
        losses = games.filter { $0.result == .loss }.count
        lastGame = games.sorted(by: { $0.date > $1.date }).first
        if games.isEmpty {
            pointsPerGame = 0
        } else {
            pointsPerGame = Double(games.reduce(0) { $0 + $1.teamScore }) / Double(games.count)
        }
    }

    var winRateText: String {
        guard totalGames > 0 else { return "0%" }
        let value = (Double(wins) / Double(totalGames)) * 100
        return value.formatted(.number.precision(.fractionLength(0))) + "%"
    }

    var averagePointsText: String {
        pointsPerGame.formatted(.number.precision(.fractionLength(1)))
    }
}
