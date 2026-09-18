#!/usr/bin/env python3
"""Cron-friendly sync-health check (platform health / observability).

Exits 0 when every tracked championship is fresh, 1 when any is stale or
erroring, 2 when the sidecar itself is unreadable. Intended for the daily
cron *after* ``jobs.championship_sync --once`` and for Jenkins failure
alerting::

    python -m jobs.championship_sync --once
    python -m jobs.check_sync_health --championship 3
"""

import argparse
import json
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--championship", type=int, default=None,
                        help="Only check one sidecar championship id")
    args = parser.parse_args(argv)

    from web import create_app
    from core.sync_diff import sync_health_snapshot

    app = create_app()
    with app.app_context():
        snapshot = sync_health_snapshot(args.championship)
    print(json.dumps(snapshot, indent=2, default=str))
    champs = snapshot.get("championships", [])
    if snapshot.get("error") and not champs:
        return 2
    if args.championship is not None and not champs:
        print(f"No championship with id {args.championship}",
              file=sys.stderr)
        return 2
    if any(c.get("stale") for c in champs):
        return 1
    if any(c.get("recent_errors") for c in champs):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
