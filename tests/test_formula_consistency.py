"""
Regression tests for core basketball formulas.
Ensures canonical implementations are used everywhere.
"""

import pytest
from core.utils import (
    calculate_ts_percent,
    calculate_efg_percent,
    calculate_possessions,
    calculate_ortg,
    calculate_game_score,
    safe_percentage,
)

# Test data: (points, fga, fta, expected_ts_pct)
TS_TEST_CASES = [
    (100, 50, 20, None),  # expected computed
    (0, 0, 0, 0.0),
    (30, 10, 5, None),
]

# Test data for eFG%: (fgm, tpm, fga, expected)
EFG_TEST_CASES = [
    (10, 5, 20, ((10 + 0.5 * 5) / 20 * 100)),
    (0, 0, 10, 0.0),
    (8, 2, 15, ((8 + 1) / 15 * 100)),
]

# Test data for possessions: (fga, fta, oreb, tov, expected)
POSS_TEST_CASES = [
    (10, 5, 2, 3, 10 + 0.44 * 5 - 2 + 3),
    (0, 0, 0, 0, 0),
    (8, 2, 1, 1, 8 + 0.44 * 2 - 1 + 1),
]

# Test data for ORTG: (points, possessions, expected)
ORTG_TEST_CASES = [
    (100, 50, (100 / 50 * 100)),
    (0, 1, 0.0),
    (90, 40, (90 / 40 * 100)),
]

# Test data for Game Score: parameters and expected
GMS_TEST_CASES = [
    # (pts, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov, expected roughly)
    # Use known value from basketball-reference or manual calc.
    (30, 10, 20, 5, 6, 2, 5, 1, 3, 0, 2, 3, None),  # approximate
]


def test_ts_percent_known_values():
    for points, fga, fta, expected in TS_TEST_CASES:
        if expected is None:
            # compute expected using same formula as in utils
            denominator = 2 * (fga + 0.44 * fta)
            expected = (points / denominator * 100) if denominator != 0 else 0.0
        result = calculate_ts_percent(points, fga, fta)
        assert round(result, 2) == round(expected, 2), (
            f"Failed for ({points},{fga},{fta})"
        )


def test_efg_percent_matches_formula():
    for fgm, tpm, fga, expected in EFG_TEST_CASES:
        result = calculate_efg_percent(fgm, tpm, fga)
        assert round(result, 2) == round(expected, 2), f"Failed for ({fgm},{tpm},{fga})"


def test_possessions_matches_formula():
    for fga, fta, oreb, tov, expected in POSS_TEST_CASES:
        result = calculate_possessions(fga, fta, oreb, tov)
        assert round(result, 2) == round(expected, 2), (
            f"Failed for ({fga},{fta},{oreb},{tov})"
        )


def test_ortg_matches_formula():
    for points, possessions, expected in ORTG_TEST_CASES:
        result = calculate_ortg(points, possessions)
        # calculate_ortg may return 0 if possessions=0
        assert round(result, 2) == round(expected, 2), (
            f"Failed for ({points},{possessions})"
        )


def test_game_score_matches_inline():
    # Compare against a local inline implementation to ensure it matches
    for (
        pts,
        fgm,
        fga,
        ftm,
        fta,
        oreb,
        dreb,
        stl,
        ast,
        blk,
        pf,
        tov,
        expected,
    ) in GMS_TEST_CASES:
        expected = (
            pts
            + 0.4 * fgm
            - 0.7 * fga
            - 0.4 * (fta - ftm)
            + 0.7 * oreb
            + 0.3 * dreb
            + stl
            + 0.7 * ast
            + 0.7 * blk
            - 0.4 * pf
            - tov
        )
        result = calculate_game_score(
            pts, fgm, fga, ftm, fta, oreb, dreb, stl, ast, blk, pf, tov
        )
        assert result == expected, f"Game score mismatch for {pts} pts etc."


def test_safe_percentage_rounding():
    assert safe_percentage(5, 10) == 50.0
    assert safe_percentage(1, 3) == round((1 / 3 * 100), 1)
    assert safe_percentage(0, 10) == 0.0
    assert safe_percentage(10, 0) == 0.0


# Additional regression: ensure no duplicate TS% function exists in advanced_analytics
def test_no_duplicate_ts_percent_definition():
    import core.advanced_analytics as adv

    # The module should not have a function named calculate_ts_percent at top level
    # It should import from utils instead.
    # Check if 'calculate_ts_percent' is in adv module's dict
    assert not hasattr(adv, "calculate_ts_percent"), (
        "Duplicate TS% function still exists in advanced_analytics.py; remove it and import from utils instead."
    )
