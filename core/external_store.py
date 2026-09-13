#!/usr/bin/env python3
"""Isolated SQLite cache for external championship data (FIP/Playbasket).

This store is deliberately separate from the application's Postgres database:
it holds scraped reference data only, can be wiped and rebuilt at any time,
and nothing in the app ever promotes its rows into internal games without an
explicit GM action. Location defaults to ``data/external_cache.db`` and can
be overridden with the ``EXT_CACHE_PATH`` environment variable (used by the
``external_data`` Docker volume in production).
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ext_championships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    comitato_codice TEXT NOT NULL DEFAULT '',
    codice_campionato TEXT NOT NULL DEFAULT '',
    codice_fase TEXT NOT NULL DEFAULT '',
    codice_girone TEXT NOT NULL DEFAULT '',
    season_label TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    last_checked TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (provider, comitato_codice, codice_campionato, codice_fase,
            codice_girone, season_label)
);
CREATE TABLE IF NOT EXISTS ext_games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    championship_id INTEGER NOT NULL REFERENCES ext_championships(id),
    stable_hash TEXT NOT NULL,
    game_number TEXT NOT NULL DEFAULT '',
    round_label TEXT NOT NULL DEFAULT '',
    game_date TEXT NOT NULL DEFAULT '',
    game_time TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    home TEXT NOT NULL DEFAULT '',
    away TEXT NOT NULL DEFAULT '',
    home_score INTEGER,
    away_score INTEGER,
    venue TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_updated TEXT NOT NULL,
    UNIQUE (championship_id, stable_hash)
);
CREATE INDEX IF NOT EXISTS idx_ext_games_champ ON ext_games(championship_id);
CREATE TABLE IF NOT EXISTS ext_standings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    championship_id INTEGER NOT NULL REFERENCES ext_championships(id),
    position INTEGER NOT NULL DEFAULT 0,
    team TEXT NOT NULL DEFAULT '',
    points INTEGER NOT NULL DEFAULT 0,
    played INTEGER NOT NULL DEFAULT 0,
    won INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    scored INTEGER NOT NULL DEFAULT 0,
    conceded INTEGER NOT NULL DEFAULT 0,
    scraped_at TEXT NOT NULL,
    UNIQUE (championship_id, team)
);
CREATE TABLE IF NOT EXISTS ext_sync_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    championship_id INTEGER REFERENCES ext_championships(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    fetched INTEGER NOT NULL DEFAULT 0,
    added INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_path() -> Path:
    override = os.getenv("EXT_CACHE_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "external_cache.db"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the cache DB (creating parent dirs, schema and WAL mode)."""
    db_path = Path(path) if path else default_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    return conn


def stable_hash(provider: str, comitato: str, campionato: str, fase: str,
                girone: str, season: str, game_number: str, date: str,
                home: str, away: str) -> str:
    """Identity of a fixture that survives score updates (scores excluded)."""
    raw = "|".join([provider, comitato, campionato, fase, girone, season,
                    (game_number or "").strip(),
                    (date or "").strip(),
                    (home or "").strip().lower(),
                    (away or "").strip().lower()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def upsert_championship(conn: sqlite3.Connection, provider: str,
                        comitato: str = "", campionato: str = "",
                        fase: str = "", girone: str = "", season: str = "",
                        display_name: str = "", source_url: str = "",
                        active: bool = True) -> int:
    now = _utcnow()
    conn.execute(
        """INSERT INTO ext_championships
           (provider, comitato_codice, codice_campionato, codice_fase,
            codice_girone, season_label, display_name, source_url, active,
            created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (provider, comitato_codice, codice_campionato,
                        codice_fase, codice_girone, season_label)
           DO UPDATE SET display_name=excluded.display_name,
                         source_url=excluded.source_url,
                         active=excluded.active""",
        (provider, comitato, campionato, fase, girone, season,
         display_name, source_url, int(active), now),
    )
    conn.commit()
    row = conn.execute(
        """SELECT id FROM ext_championships
           WHERE provider=? AND comitato_codice=? AND codice_campionato=?
             AND codice_fase=? AND codice_girone=? AND season_label=?""",
        (provider, comitato, campionato, fase, girone, season),
    ).fetchone()
    return int(row["id"])


def _score(value) -> int | None:
    """Playbasket/FIP use -1 or '' for unplayed games."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def upsert_game(conn: sqlite3.Connection, championship_id: int,
                game: dict) -> str:
    """Insert or update one game. Returns 'added', 'updated' or 'unchanged'."""
    champ = conn.execute(
        "SELECT * FROM ext_championships WHERE id=?",
        (championship_id,),
    ).fetchone()
    if champ is None:
        raise ValueError(f"Unknown championship {championship_id}")
    game_hash = stable_hash(
        champ["provider"], champ["comitato_codice"],
        champ["codice_campionato"], champ["codice_fase"],
        champ["codice_girone"], champ["season_label"],
        str(game.get("game_number") or game.get("n_gara") or ""),
        str(game.get("date") or game.get("data") or ""),
        str(game.get("home") or game.get("casa") or ""),
        str(game.get("away") or game.get("ospite") or ""),
    )
    home_score = _score(game.get("home_score", game.get("pc")))
    away_score = _score(game.get("away_score", game.get("po")))
    now = _utcnow()
    existing = conn.execute(
        "SELECT * FROM ext_games WHERE championship_id=? AND stable_hash=?",
        (championship_id, game_hash),
    ).fetchone()
    venue = str(game.get("venue") or game.get("campo") or "")
    city = str(game.get("city") or game.get("citta") or "")
    if existing is None:
        conn.execute(
            """INSERT INTO ext_games
               (championship_id, stable_hash, game_number, round_label,
                game_date, game_time, status, home, away, home_score,
                away_score, venue, city, first_seen, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (championship_id, game_hash,
             str(game.get("game_number") or game.get("n_gara") or ""),
             str(game.get("round") or game.get("turno") or ""),
             str(game.get("date") or game.get("data") or ""),
             str(game.get("time") or game.get("ora") or ""),
             str(game.get("status") or game.get("stato") or ""),
             str(game.get("home") or game.get("casa") or ""),
             str(game.get("away") or game.get("ospite") or ""),
             home_score, away_score, venue, city, now, now),
        )
        conn.commit()
        return "added"
    changed = (
        existing["home_score"] != home_score
        or existing["away_score"] != away_score
        or existing["status"] != str(game.get("status") or game.get("stato") or "")
        or existing["round_label"] != str(game.get("round") or game.get("turno") or "")
    )
    if changed:
        conn.execute(
            """UPDATE ext_games SET home_score=?, away_score=?, status=?,
                                  round_label=?, venue=?, city=?,
                                  last_updated=? WHERE id=?""",
            (home_score, away_score,
             str(game.get("status") or game.get("stato") or ""),
             str(game.get("round") or game.get("turno") or ""),
             venue, city, now, existing["id"]),
        )
        conn.commit()
        return "updated"
    return "unchanged"


def replace_standings(conn: sqlite3.Connection, championship_id: int,
                      rows: list[dict]) -> int:
    """Replace the standings snapshot for a championship."""
    conn.execute("DELETE FROM ext_standings WHERE championship_id=?",
                 (championship_id,))
    now = _utcnow()
    for position, row in enumerate(rows, start=1):
        conn.execute(
            """INSERT INTO ext_standings
               (championship_id, position, team, points, played, won, lost,
                scored, conceded, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (championship_id, int(row.get("pos", position)),
             str(row.get("team", "")), int(row.get("pts", 0)),
             int(row.get("g", 0)), int(row.get("w", 0)),
             int(row.get("l", 0)), int(row.get("pf", 0)),
             int(row.get("ps", 0)), now),
        )
    conn.commit()
    return len(rows)


def log_sync(conn: sqlite3.Connection, championship_id: int | None,
             fetched: int = 0, added: int = 0, updated: int = 0,
             error: str | None = None) -> int:
    now = _utcnow()
    cur = conn.execute(
        """INSERT INTO ext_sync_log
           (championship_id, started_at, finished_at, fetched, added,
            updated, error)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (championship_id, now, now, fetched, added, updated, error),
    )
    conn.commit()
    return int(cur.lastrowid)


def touch_checked(conn: sqlite3.Connection, championship_id: int) -> None:
    conn.execute("UPDATE ext_championships SET last_checked=? WHERE id=?",
                 (_utcnow(), championship_id))
    conn.commit()


def get_championship(conn: sqlite3.Connection,
                     championship_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM ext_championships WHERE id=?",
                       (championship_id,)).fetchone()
    return dict(row) if row else None


def list_championships(conn: sqlite3.Connection,
                       active_only: bool = False) -> list[dict]:
    query = "SELECT * FROM ext_championships"
    if active_only:
        query += " WHERE active=1"
    query += " ORDER BY id"
    return [dict(r) for r in conn.execute(query).fetchall()]


def list_games(conn: sqlite3.Connection, championship_id: int,
               team_filter: str = "") -> list[dict]:
    rows = conn.execute(
        """SELECT * FROM ext_games WHERE championship_id=?
           ORDER BY game_date, game_number""",
        (championship_id,),
    ).fetchall()
    games = [dict(r) for r in rows]
    if team_filter:
        needle = team_filter.strip().lower()
        games = [g for g in games
                 if needle in (g["home"] or "").lower()
                 or needle in (g["away"] or "").lower()]
    return games


def get_standings(conn: sqlite3.Connection,
                  championship_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT * FROM ext_standings WHERE championship_id=?
           ORDER BY position""",
        (championship_id,)).fetchall()]


def new_since(conn: sqlite3.Connection, championship_id: int,
              since: str) -> list[dict]:
    """Games first seen or updated after an ISO timestamp (for badges)."""
    return [dict(r) for r in conn.execute(
        """SELECT * FROM ext_games WHERE championship_id=?
           AND (first_seen > ? OR last_updated > ?)
           ORDER BY game_date""",
        (championship_id, since, since)).fetchall()]


def seed_from_snapshot(conn: sqlite3.Connection, snapshot: dict,
                       provider: str = "playbasket_html") -> dict:
    """Seed the store from a scrape snapshot (games + standings)."""
    meta = snapshot.get("meta", {})
    champ_id = upsert_championship(
        conn,
        provider=provider,
        comitato=meta.get("comitato", "RLO"),
        campionato=meta.get("campionato", "DR4"),
        fase=meta.get("fase", "1"),
        girone=str(meta.get("girone", "M")),
        season=str(meta.get("season", "")),
        display_name=f"{meta.get('competition', '')} Girone {meta.get('girone', '')}",
        source_url=meta.get("source_url", ""),
    )
    added = updated = 0
    for game in snapshot.get("games", []):
        outcome = upsert_game(conn, champ_id, game)
        if outcome == "added":
            added += 1
        elif outcome == "updated":
            updated += 1
    standings = replace_standings(conn, champ_id,
                                  snapshot.get("standings", []))
    touch_checked(conn, champ_id)
    return {"championship_id": champ_id, "added": added,
            "updated": updated, "standings": standings}


def seed_from_snapshot_file(conn: sqlite3.Connection, path: Path | str,
                            provider: str = "playbasket_html") -> dict:
    with open(path, encoding="utf-8") as handle:
        return seed_from_snapshot(conn, json.load(handle),
                                  provider=provider)
