"""Benchmarks for the Perf_Improvements work.

Measures the Rust batch APIs vs their pure-Python equivalents and the
single-pass / bulk DB helpers vs the legacy N-query call patterns.

Run on (or closest to) the hardware described in docs/PROD_MACHINE.md
before claiming speedups — JSON round-trip overhead and rayon scaling
behave differently per CPU/arch and optimization level.

Usage:
    python bench_perf_improvements.py [--quick] [--reps N] [--json out.json]

The DB-backed section uses the `testing` app config on a scratch database.
Matplotlib chart benches are opt-in via --charts (they are slow).
"""

import argparse
import json
import random
import statistics
import sys
import time

sys.path.insert(0, ".")

from core import rust_analytics
from core.rust_analytics import RUST_AVAILABLE


def bench(name, new_fn, old_fn, reps=5):
    new_times, old_times = [], []
    for _ in range(reps):
        t0 = time.perf_counter()
        new_fn()
        new_times.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        old_fn()
        old_times.append((time.perf_counter() - t0) * 1000)
    new_med = statistics.median(new_times)
    old_med = statistics.median(old_times)
    speedup = old_med / new_med if new_med > 0 else float("inf")
    print(f"{name:55s} new={new_med:9.2f}ms  old={old_med:9.2f}ms  x{speedup:.2f}")
    return {"name": name, "new_ms": new_med, "old_ms": old_med, "speedup": speedup}


def bench_pure(scale):
    from core.rust_analytics import (
        _python_aggregate_combinatorial_stats,
        _python_parse_time_to_seconds,
    )

    rng = random.Random(42)
    results = []

    shots = [
        {
            "points": rng.choice([0, 2, 2, 3]),
            "x_loc": rng.uniform(0, 500),
            "y_loc": rng.uniform(0, 470),
            "shot_type": rng.choice(["2pt", "2pt", "3pt", "ft"]),
        }
        for _ in range(scale)
    ]
    # Production uses scalar PyO3 calls here: measured ~10x faster than the
    # JSON batch API (serde round-trip dominates the trivial predicate).
    results.append(
        bench(
            f"shot zones scalar-vs-batch x{scale}",
            lambda: [
                rust_analytics.classify_shot_zone(s["x_loc"], s["y_loc"], s["shot_type"])
                for s in shots
            ],
            lambda: rust_analytics.classify_shot_zones_batch(shots),
        )
    )

    hex_shots = [
        {"x_loc": s["x_loc"], "y_loc": s["y_loc"], "points": s["points"],
         "result": rng.choice(["made", "missed"])}
        for s in shots
    ]
    # Production uses plain-Python aggregation: measured ~2.7x faster than
    # the Rust JSON-batch API at every realistic scale.
    results.append(
        bench(
            f"hexbins python-vs-rust x{scale}",
            lambda: _py_hexbins(hex_shots, 50),
            lambda: rust_analytics.aggregate_hexbins(hex_shots, 50),
        )
    )

    entries = [
        [rng.randint(0, 20), rng.randint(0, 10), rng.randint(0, 5), rng.randint(0, 5)]
        for _ in range(scale)
    ]
    results.append(
        bench(
            f"calculate_possessions_batch x{scale}",
            lambda: rust_analytics.calculate_possessions_batch(entries),
            lambda: [float(e[0]) + 0.44 * float(e[1]) - float(e[2]) + float(e[3])
                     for e in entries],
        )
    )

    margins = [[rng.randint(-15, 15), rng.randint(0, 2400)] for _ in range(scale)]
    results.append(
        bench(
            f"batch_is_clutch x{scale}",
            lambda: rust_analytics.batch_is_clutch(margins),
            lambda: [abs(m) <= 5 and s <= 300 for m, s in margins],
        )
    )

    times = [
        f"{rng.randint(0, 11)}:{rng.randint(0, 59):02d}" if rng.random() > 0.1 else None
        for _ in range(scale)
    ]
    results.append(
        bench(
            f"parse_times_batch x{scale}",
            lambda: rust_analytics.parse_times_batch(times),
            lambda: [_python_parse_time_to_seconds(t) for t in times],
        )
    )

    details = [
        json.dumps({"p": i}) if i % 3 else ("nope" if i % 3 == 1 else None)
        for i in range(scale)
    ]
    results.append(
        bench(
            f"parse_details_batch x{scale}",
            lambda: rust_analytics.parse_details_batch(details),
            lambda: [_py_parse_detail(d) for d in details],
        )
    )

    players = [f"P{i}" for i in range(12)]
    segments = [
        {
            "players": rng.sample(players, 5),
            "points_scored": rng.randint(0, 15),
            "points_allowed": rng.randint(0, 15),
            "possessions": float(rng.randint(1, 12)),
            "reb_conceded": rng.randint(0, 3),
            "duration_seconds": rng.randint(30, 400),
        }
        for _ in range(max(scale // 10, 50))
    ]
    results.append(
        bench(
            f"aggregate_combinatorial_stats x{len(segments)}",
            lambda: rust_analytics.aggregate_combinatorial_stats(segments),
            lambda: _python_aggregate_combinatorial_stats(segments),
        )
    )
    return results


def _py_hexbins(shots, hs):
    from collections import defaultdict

    bins = defaultdict(lambda: {"makes": 0, "attempts": 0, "points": 0})
    for s in shots:
        if s["x_loc"] is None or s["y_loc"] is None:
            continue
        hx = int(s["x_loc"] // hs) * hs + hs // 2
        hy = int(s["y_loc"] // hs) * hs + hs // 2
        b = bins[(hx, hy)]
        b["attempts"] += 1
        b["points"] += s["points"] or 0
        if s["result"] == "made":
            b["makes"] += 1
    return [
        {"x": x, "y": y, "attempts": v["attempts"], "makes": v["makes"],
         "fg_pct": round(v["makes"] / v["attempts"] * 100, 1) if v["attempts"] else 0.0,
         "points": v["points"]}
        for (x, y), v in bins.items()
    ]


def _py_parse_detail(detail):
    import ast as _ast

    if detail is None:
        return {}
    if isinstance(detail, dict):
        return detail
    try:
        parsed = json.loads(detail)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        try:
            parsed = _ast.literal_eval(detail)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError, SyntaxError):
            return {}


def seed_db(db, models, n_players=8, shots_per_player=150, n_events=1500):
    Game, PlayerStat, Play, ShotEvent, GameEvent = (
        models.Game, models.PlayerStat, models.Play,
        models.ShotEvent, models.GameEvent,
    )
    rng = random.Random(7)
    org = models.Organization(name="Bench Org", slug="bench-org")
    db.session.add(org)
    db.session.flush()
    team = models.Team(name="Bench Team", organization_id=org.id, slug="bench-team")
    db.session.add(team)
    db.session.flush()
    game = Game(
        team_id=team.id,
        date="20-03-2026", opponent="Bench Opponent", team_score=80,
        opponent_score=70, result="W", game_type="Season",
        sort_date="2026-03-20", source="BENCH",
    )
    db.session.add(game)
    db.session.flush()

    names = [f"Bench{i}" for i in range(n_players)]
    for i, name in enumerate(names):
        db.session.add(PlayerStat(
            game_id=game.id, player_name=name, minutes="20:00",
            points=10 + i, fgm=4, fga=8, tpm=1, tpa=3, ftm=1, fta=2,
            oreb=1, dreb=2, reb=3, ast=2, stl=1, blk=0, tov=2, pf=1,
            plus_minus=5, fg_percent=50.0, tp_percent=33.3, ft_percent=50.0,
        ))
    plays = [Play(team_id=team.id, name=f"BenchPlay{i}", play_type="Offense", description="b") for i in range(4)]
    db.session.add_all(plays)
    db.session.flush()

    for name in names:
        for _ in range(shots_per_player):
            made = rng.random() > 0.5
            pts = rng.choice([2, 3]) if made else 0
            db.session.add(ShotEvent(
                game_id=game.id, player_name=name,
                shot_type="3pt" if pts == 3 else "2pt",
                result="made" if made else "missed", points=pts,
                x_loc=rng.uniform(0, 500), y_loc=rng.uniform(0, 470),
                quarter=rng.randint(1, 4), play_id=rng.choice(plays).id,
            ))
    for i in range(n_events):
        etype = rng.choice(["SHOT_2PT", "SHOT_3PT", "FOUL", "TURNOVER"])
        db.session.add(GameEvent(
            game_id=game.id, event_type=etype, player_name=rng.choice(names),
            shot_attempt=rng.choice(["made", "missed"]) if "SHOT" in etype else None,
            play_id=rng.choice(plays).id, quarter=rng.randint(1, 4),
            time_remaining=f"{rng.randint(0, 11)}:{rng.randint(0, 59):02d}",
            score_margin=rng.randint(-15, 15),
        ))
    db.session.commit()
    return game.id, names


def bench_db(game_id, names, reps):
    from core import play_analytics
    from core.services.analytics_service import AnalyticsService
    from web import db

    results = []
    results.append(
        bench(
            "summary_play_analysis (1 pass vs 3 getters)",
            lambda: play_analytics.get_summary_play_analysis(game_id),
            lambda: (
                play_analytics.get_summary_play_stats(game_id),
                play_analytics.get_summary_play_player_stats(game_id),
                play_analytics.get_summary_player_play_stats(game_id),
            ),
            reps=reps,
        )
    )

    game_ids = [game_id]
    results.append(
        bench(
            "team_rankings_all (1 scan vs N scans)",
            lambda: AnalyticsService.calculate_team_rankings_all(game_ids, db.session),
            lambda: [
                AnalyticsService.calculate_team_rankings(n, game_ids, {}, db.session)
                for n in names
            ],
            reps=reps,
        )
    )
    return results


def bench_charts(game_id, names, reps):
    from core.charts import generate_shot_chart, generate_shot_charts_for_game
    from web import db

    return [
        bench(
            "shot_charts_for_game (1 query vs N queries)",
            lambda: generate_shot_charts_for_game(game_id, names, db.session),
            lambda: [generate_shot_chart(n, [game_id], db.session) for n in names],
            reps=reps,
        )
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smaller scale, fewer reps")
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--json", default=None, help="write results JSON here")
    ap.add_argument("--charts", action="store_true", help="include matplotlib benches")
    ap.add_argument("--skip-db", action="store_true")
    args = ap.parse_args()

    scale = 500 if args.quick else 5000
    reps = args.reps or (2 if args.quick else 5)
    print(f"Rust engine: {'LOADED' if RUST_AVAILABLE else 'MISSING (Python fallback)'}")
    print(f"scale={scale} reps={reps}\n")

    results = bench_pure(scale)

    if not args.skip_db:
        from web import create_app, db
        from core import models

        app = create_app("testing")
        with app.app_context():
            db.create_all()
            try:
                n_players = 4 if args.quick else 8
                spp = 40 if args.quick else 150
                nev = 300 if args.quick else 1500
                game_id, names = seed_db(db, models, n_players, spp, nev)
                results += bench_db(game_id, names, reps)
                if args.charts:
                    results += bench_charts(game_id, names, max(reps, 2))
            finally:
                db.session.remove()
                db.drop_all()

    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nwrote {args.json}")
    slow = [r for r in results if r["speedup"] < 1.0]
    if slow:
        print(f"\nNOTE: {len(slow)} bench(es) show the new path slower:")
        for r in slow:
            print(f"  - {r['name']}: x{r['speedup']:.2f}")


if __name__ == "__main__":
    main()
