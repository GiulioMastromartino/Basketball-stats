import SwiftUI

struct GlossaryScreen: View {
    private struct Section: Identifiable {
        let id = UUID()
        let title: String
        let icon: String
        let terms: [Term]
    }

    private struct Term: Identifiable {
        let id = UUID()
        let name: String
        let definition: String
        let formula: String?
    }

    private let sections: [Section] = [
        Section(title: "Traditional Stats", icon: "list.number", terms: [
            Term(name: "MIN — Minutes", definition: "Total minutes played. Averages are per game.", formula: nil),
            Term(name: "PTS — Points", definition: "Total points scored, including field goals and free throws.", formula: nil),
            Term(name: "REB — Rebounds", definition: "Total rebounds pulled in, offensive and defensive combined.", formula: nil),
            Term(name: "OREB — Offensive Rebounds", definition: "Rebounds secured after a missed shot by your own team.", formula: nil),
            Term(name: "DREB — Defensive Rebounds", definition: "Rebounds secured after a missed shot by the opponent.", formula: nil),
            Term(name: "AST — Assists", definition: "Passes that directly lead to a made basket.", formula: nil),
            Term(name: "STL — Steals", definition: "Gaining possession from an opponent via an active play.", formula: nil),
            Term(name: "BLK — Blocks", definition: "Rejecting an opponent shot attempt.", formula: nil),
            Term(name: "TOV — Turnovers", definition: "Losing possession to the opponent.", formula: nil),
            Term(name: "PF — Personal Fouls", definition: "Illegal personal contact that results in a foul.", formula: nil),
        ]),
        Section(title: "Shooting Stats", icon: "scope", terms: [
            Term(name: "FG% — Field Goal Percentage", definition: "Shooting efficiency on all field goal attempts.", formula: "FG% = FGM / FGA × 100"),
            Term(name: "2P% — Two-Point Percentage", definition: "Shooting efficiency on two-point attempts.", formula: nil),
            Term(name: "3P% — Three-Point Percentage", definition: "Shooting efficiency on three-point attempts.", formula: nil),
            Term(name: "FT% — Free Throw Percentage", definition: "Shooting efficiency from the free throw line.", formula: nil),
            Term(name: "M/A — Made / Attempted", definition: "Raw makes and attempts for a given shot type.", formula: nil),
            Term(name: "FTA/FGA — Free Throw Rate", definition: "How often a player draws fouls relative to shots.", formula: "FTA / FGA × 100"),
        ]),
        Section(title: "Advanced Efficiency", icon: "gauge.with.dots.needle.67percent", terms: [
            Term(name: "EFF — Efficiency", definition: "Classic all-in-one box score rating.", formula: "EFF = (PTS + REB + AST + STL + BLK) − ((FGA−FGM) + (FTA−FTM) + TOV)"),
            Term(name: "TS% — True Shooting Percentage", definition: "Shooting efficiency accounting for 2PT, 3PT and free throws.", formula: "TS% = PTS / (2 × (FGA + 0.44 × FTA)) × 100"),
            Term(name: "eFG% — Effective Field Goal Percentage", definition: "FG% adjusted to credit 3-pointers.", formula: "eFG% = (FGM + 0.5 × 3PM) / FGA × 100"),
            Term(name: "GmSc — Game Score", definition: "Hollinger's single-game performance rating.", formula: "GmSc = PTS + 0.4·FGM − 0.7·FGA − 0.4·(FTA−FTM) + 0.7·OREB + 0.3·DREB + STL + 0.7·AST + 0.7·BLK − 0.4·PF − TOV"),
        ]),
        Section(title: "Advanced Ratings", icon: "chart.bar.xaxis", terms: [
            Term(name: "ORtg — Offensive Rating", definition: "Points produced per 100 possessions.", formula: "ORtg = Points / Possessions × 100"),
            Term(name: "DRtg — Defensive Rating", definition: "Points allowed per 100 possessions.", formula: "DRtg = OppPoints / Possessions × 100"),
            Term(name: "Net Rating", definition: "Team differential per 100 possessions.", formula: "Net = ORtg − DRtg"),
            Term(name: "PPP — Points Per Possession", definition: "Points produced on a single possession.", formula: "PPP = Points / Possessions"),
        ]),
        Section(title: "Player Impact Metrics", icon: "person.crop.circle.badge.plus", terms: [
            Term(name: "USG% — Usage Rate", definition: "Share of team plays a player is involved in while on court.", formula: "USG% = (FGA + 0.44·FTA + TOV) / TeamPossessions × 100"),
            Term(name: "A/TO — Assist to Turnover Ratio", definition: "Playmaking efficiency.", formula: "A/TO = Assists / Turnovers (if TOV > 0, else Assists)"),
        ]),
        Section(title: "Team Dynamics", icon: "bolt.fill", terms: [
            Term(name: "PACE", definition: "Possessions per 40 minutes of play.", formula: "PACE = Possessions / (Minutes / 5) × 40"),
            Term(name: "OREB% — Offensive Rebound Percentage", definition: "Share of available rebounds grabbed on offense.", formula: "OREB / REB × 100"),
            Term(name: "TOV% — Turnover Percentage", definition: "Turnovers per 100 offensive plays.", formula: "TOV% = TOV / (FGA + 0.44·FTA + TOV) × 100"),
        ]),
        Section(title: "Lineup & Synergy Analysis", icon: "person.3.fill", terms: [
            Term(name: "Lineup Rating", definition: "Net rating of a five-man unit per 100 possessions.", formula: nil),
            Term(name: "Synergy — Net Differential", definition: "Group performance when ON vs OFF the court together.", formula: "Net Diff = ON Net − OFF Net"),
            Term(name: "ON Net Rating", definition: "Net rating in the minutes the group is on the floor.", formula: nil),
            Term(name: "OFF Net Rating", definition: "Net rating in the minutes the group sits.", formula: nil),
            Term(name: "Resistance", definition: "Lineup stability measure combining possessions, continuity and net impact.", formula: nil),
        ]),
        Section(title: "Multi-Game Averages", icon: "calendar", terms: [
            Term(name: "GP — Games Played", definition: "Number of games a player appeared in.", formula: nil),
            Term(name: "MPG — Minutes Per Game", definition: "Average minutes played per game.", formula: nil),
            Term(name: "PPG — Points Per Game", definition: "Average points scored per game.", formula: nil),
            Term(name: "RPG — Rebounds Per Game", definition: "Average rebounds per game.", formula: nil),
            Term(name: "APG — Assists Per Game", definition: "Average assists per game.", formula: nil),
            Term(name: "SPG — Steals Per Game", definition: "Average steals per game.", formula: nil),
            Term(name: "BPG — Blocks Per Game", definition: "Average blocks per game.", formula: nil),
            Term(name: "TOPG — Turnovers Per Game", definition: "Average turnovers per game.", formula: nil),
            Term(name: "CV — Consistency", definition: "Coefficient of variation of points scored; lower is steadier.", formula: "CV = StdDev(PPG) / Mean(PPG) × 100"),
        ]),
        Section(title: "Possession Calculation", icon: "function", terms: [
            Term(name: "Possessions (Dean Oliver)", definition: "The standard estimate of a team or player's possessions.", formula: "Poss = FGA − OREB + TOV + 0.44 × FTA"),
        ]),
        Section(title: "Performance Benchmarks", icon: "flag.checkered", terms: [
            Term(name: "TS% Tiers", definition: "Excellent ≥ 60% · Good ≥ 55% · Average ≥ 50% · Poor < 50%", formula: nil),
            Term(name: "eFG% Tiers", definition: "Excellent ≥ 55% · Good ≥ 50% · Average ≥ 45% · Poor < 45%", formula: nil),
            Term(name: "3P% Tiers", definition: "Excellent ≥ 40% · Good ≥ 36% · Average ≥ 33% · Poor < 30%", formula: nil),
            Term(name: "PPP Tiers", definition: "Excellent ≥ 1.10 · Good ≥ 1.00 · Average ≥ 0.90 · Poor < 0.80", formula: nil),
            Term(name: "ORtg Tiers", definition: "Excellent ≥ 115 · Good ≥ 105 · Average ≥ 95 · Poor < 90", formula: nil),
            Term(name: "A/TO Tiers", definition: "Excellent ≥ 3.0 · Good ≥ 2.0 · Average ≥ 1.5 · Poor < 1.0", formula: nil),
            Term(name: "USG% Tiers", definition: "Usage measured as share of team possessions; 20–30% typical for stars.", formula: nil),
            Term(name: "GmSc Tiers", definition: "40+ historic game · 30+ All-Star level · 20+ starter level · 10+ solid", formula: nil),
        ]),
    ]

    var body: some View {
        HSPage {
            ScrollView {
                VStack(spacing: 16) {
                    ForEach(sections) { section in
                        VStack(alignment: .leading, spacing: 12) {
                            HStack(spacing: 8) {
                                Image(systemName: section.icon)
                                    .foregroundStyle(HSToken.accent)
                                HSSectionHeader(title: section.title)
                            }
                            LazyVGrid(columns: [GridItem(.flexible(), spacing: 16), GridItem(.flexible(), spacing: 16)], spacing: 14) {
                                ForEach(section.terms) { term in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(term.name)
                                            .font(.outfit(size: 13, weight: .bold))
                                            .foregroundStyle(HSToken.accent)
                                        Text(term.definition)
                                            .font(.outfit(size: 12))
                                            .foregroundStyle(HSToken.inkMuted)
                                        if let formula = term.formula {
                                            Text(formula)
                                                .font(.system(size: 11, design: .monospaced))
                                                .foregroundStyle(HSToken.cool)
                                        }
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                }
                            }
                        }
                        .padding(16)
                        .background(HSToken.surface, in: RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: HSToken.radius, style: .continuous)
                                .stroke(HSToken.line, lineWidth: 1)
                        )
                    }
                }
                .padding()
            }
            .scrollContentBackground(.hidden)
            .navigationTitle("Glossary")
        }
    }
}
