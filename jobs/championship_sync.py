#!/usr/bin/env python3
"""Daily sync of tracked external championships into the SQLite sidecar.

Usage:
    python -m jobs.championship_sync --once        # single run (cron/manual)
    python -m jobs.championship_sync --daemon      # loop every --interval seconds

Reads active ``TrackedChampionship`` rows from Postgres, fetches each via
its provider adapter, upserts into ``core.external_store`` by stable hash,
and logs the outcome. Never touches internal games or player data.
"""

import argparse
import logging
import sys
import time
import traceback

logger = logging.getLogger("championship_sync")


def _adapters():
    from jobs.adapters import fip_api, playbasket_html
    return {"fip_api": fip_api, "playbasket_html": playbasket_html}


def sync_once() -> dict:
    """Run one sync pass over all active tracked championships."""
    from core import external_store as store
    from core.models import TrackedChampionship, db
    from web import create_app

    app = create_app()
    summary = {"championships": 0, "added": 0, "updated": 0, "errors": []}
    with app.app_context():
        tracked = TrackedChampionship.query.filter_by(active=True).all()
        if not tracked:
            # Bootstrap: seed the bundled DR4 snapshot so the page works
            # out of the box.
            from pathlib import Path
            seed = (Path(__file__).resolve().parents[1] / "data"
                    / "playbasket_dr4_2025_26.json")
            if seed.exists():
                conn = store.connect()
                try:
                    result = store.seed_from_snapshot_file(conn, seed)
                    summary["added"] += result["added"]
                    summary["championships"] += 1
                    logger.info("Bootstrapped bundled DR4 snapshot: %s",
                                result)
                finally:
                    conn.close()
            return summary
        adapters = _adapters()
        for item in tracked:
            conn = store.connect()
            try:
                adapter = adapters.get(item.provider)
                if adapter is None:
                    raise ValueError(f"Unknown provider {item.provider}")
                if item.provider == "fip_api":
                    games = adapter.fetch_games(
                        item.comitato_codice, item.codice_campionato,
                        item.codice_fase, item.codice_girone)
                    standings = []
                else:
                    season_year = (item.season_label.split("/")[-1].strip()
                                   if "/" in (item.season_label or "")
                                   else (item.season_label or "").strip())
                    games, standings, _ = adapter.fetch_championship(
                        province=item.province_codice or "MI",
                        championship=item.codice_campionato or "DR4",
                        season=season_year or "2026",
                        girone=item.codice_girone or "M")
                champ_id = store.upsert_championship(
                    conn, provider=item.provider,
                    comitato=item.comitato_codice,
                    campionato=item.codice_campionato, fase=item.codice_fase,
                    girone=item.codice_girone, season=item.season_label,
                    display_name=item.display_name)
                added = updated = 0
                for game in games:
                    outcome = store.upsert_game(conn, champ_id, game)
                    if outcome == "added":
                        added += 1
                    elif outcome == "updated":
                        updated += 1
                if standings:
                    store.replace_standings(conn, champ_id, standings)
                store.touch_checked(conn, champ_id)
                store.log_sync(conn, champ_id, fetched=len(games),
                               added=added, updated=updated)
                summary["championships"] += 1
                summary["added"] += added
                summary["updated"] += updated
                logger.info("Synced %s: %d fetched, %d added, %d updated",
                            item.display_name, len(games), added, updated)
            except Exception as exc:  # never break the whole pass
                logger.error("Sync failed for %s: %s", item.display_name,
                             exc)
                try:
                    store.log_sync(conn, None, error=f"{type(exc).__name__}: {exc}")
                except Exception:
                    pass
                summary["errors"].append(f"{item.display_name}: {exc}")
                logger.debug(traceback.format_exc())
            finally:
                conn.close()
    # Touching the ORM above may leave the Flask session dirty; roll back.
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true",
                        help="Run a single sync pass and exit")
    parser.add_argument("--daemon", action="store_true",
                        help="Loop forever, sleeping --interval between passes")
    parser.add_argument("--interval", type=int, default=86400,
                        help="Seconds between daemon passes (default 86400)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if not args.once and not args.daemon:
        args.once = True
    if args.daemon:
        logger.info("Championship sync daemon started (interval %ds)",
                    args.interval)
        while True:
            summary = sync_once()
            logger.info("Pass complete: %s", summary)
            time.sleep(args.interval)
        return 0
    summary = sync_once()
    logger.info("Sync complete: %s", summary)
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
