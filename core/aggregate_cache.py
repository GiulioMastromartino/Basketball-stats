"""Per-game aggregate cache (platform health / perf).

Short-TTL in-process cache for expensive analytics aggregates. Keys embed
the exact game-id set, so new games self-invalidate; the TTL only guards
against repeated identical reads (dashboard refresh storms, NL queries).
Test-safe: call :func:`invalidate` in tests that need a cold cache.
"""

import time

TTL_SECONDS = 120

_cache: dict = {}


def _key(game_ids) -> tuple:
    return tuple(sorted(int(g) for g in (game_ids or [])))


def cached_four_factors(game_ids: list) -> dict:
    """Four Factors for an exact game set, cached 120s."""
    from core.advanced_analytics import AnalyticsEngine

    key = ("four_factors", _key(game_ids))
    if not key[1]:
        return {}
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None:
        value, stored_at = hit
        if now - stored_at < TTL_SECONDS:
            return value
    value = AnalyticsEngine.get_four_factors(game_ids=list(key[1])) or {}
    _cache[key] = (value, now)
    return value


def invalidate() -> None:
    """Drop all cached aggregates (tests, admin debugging)."""
    _cache.clear()
