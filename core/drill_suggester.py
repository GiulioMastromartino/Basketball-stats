"""Drill suggester (Slice N2).

Recommends 3 drills from the weakest Four Factor, each linked to playbook
play types so a coach can jump from "what's wrong" to "what to run".
Benchmarks are youth/semi-pro reasonable defaults, not NBA targets.
"""

# factor key -> (benchmark, higher_is_better, label)
BENCHMARKS = {
    "efg_pct": (50.0, True, "Shooting (eFG%)"),
    "tov_pct": (14.0, False, "Ball security (TOV%)"),
    "orb_pct": (28.0, True, "Offensive rebounding (OREB%)"),
    "ft_rate": (0.28, True, "Getting to the line (FT rate)"),
}

DRILL_LIBRARY = [
    {"name": "3-spot catch-and-shoot ladder", "factor": "efg_pct",
     "category": "Shooting", "duration_min": 15,
     "play_types": ["Offense", "Zone Offense"],
     "description": "5 makes per spot (corner/wing/top) before rotating; "
                    "track makes loud."},
    {"name": "Small-sided 3v3 no-dribble", "factor": "efg_pct",
     "category": "Spacing", "duration_min": 15,
     "play_types": ["Offense", "Transition"],
     "description": "Pass-and-cut only; punishes standing around, rewards "
                    "paint touches before a shot."},
    {"name": "Two-ball pressure handling", "factor": "tov_pct",
     "category": "Ball handling", "duration_min": 10,
     "play_types": ["Press Break", "Transition"],
     "description": "Pairs, two balls, full-court zig-zag vs a live defender; "
                    "weak-hand finish."},
    {"name": "4v3 disadvantage passing", "factor": "tov_pct",
     "category": "Decision making", "duration_min": 15,
     "play_types": ["Offense", "Press Break"],
     "description": "Offense down a player must complete 5 passes before "
                    "scoring; reads over dribbling."},
    {"name": "Circle crash + outlet", "factor": "orb_pct",
     "category": "Rebounding", "duration_min": 12,
     "play_types": ["Offense", "Transition"],
     "description": "Coach shoots, two crashers vs two box-outs; outlet must "
                    "hit the far hash in 2 dribbles."},
    {"name": "Free-throw + sprint-back", "factor": "orb_pct",
     "category": "Rebounding", "duration_min": 10,
     "play_types": ["Defense", "Transition"],
     "description": "Missed FT is live; defense must secure and push. Losers "
                    "run, winners shoot."},
    {"name": "Rip-and-go 1v1 from the wing", "factor": "ft_rate",
     "category": "Attacking", "duration_min": 12,
     "play_types": ["Offense", "Transition"],
     "description": "Live 1v1, 6-second clock; only paint touches score. "
                    "Rewards drawing contact."},
    {"name": "Bonus-situation shell", "factor": "ft_rate",
     "category": "Team offense", "duration_min": 15,
     "play_types": ["Offense", "Zone Offense"],
     "description": "4v4 shell starting at 5 team fouls; offense hunts the "
                    "bonus, defense must guard without fouling."},
]


def _gap(factor: str, value: float) -> float:
    """Signed shortfall vs benchmark (>= 0 means needs work)."""
    benchmark, higher_is_better, _label = BENCHMARKS[factor]
    if higher_is_better:
        return benchmark - value
    return value - benchmark


def weakest_factor(four_factors: dict):
    """Return the factor key furthest below its benchmark (None if empty)."""
    if not four_factors:
        return None
    scored = [(key, _gap(key, float(four_factors.get(key, 0) or 0)))
              for key in BENCHMARKS if key in four_factors]
    if not scored:
        return None
    return max(scored, key=lambda kv: kv[1])[0]


def suggest_drills(four_factors: dict, limit: int = 3, zone: str = None) -> dict:
    """Suggest up to ``limit`` drills for the weakest factor.

    ``zone`` (e.g. "corner-3") optionally re-prioritizes shooting drills.
    Returns ``{"weakest": key, "label": ..., "drills": [...]}``.
    """
    weakest = weakest_factor(four_factors or {})
    if weakest is None:
        return {"weakest": None, "label": None, "drills": []}
    _benchmark, _hib, label = BENCHMARKS[weakest]
    pool = [d for d in DRILL_LIBRARY if d["factor"] == weakest]
    if zone and weakest == "efg_pct":
        pool = sorted(pool, key=lambda d: 0 if "3" in d["name"] or
                      "shoot" in d["category"].lower() else 1)
    return {
        "weakest": weakest,
        "label": label,
        "team_value": four_factors.get(weakest),
        "benchmark": _benchmark,
        "drills": [dict(d) for d in pool[:limit]],
    }
