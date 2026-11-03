from __future__ import annotations

from typing import Optional, Iterable

from sqlalchemy import inspect, text
from sqlalchemy.sql import sqltypes


def _sql_literal(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def _default_sql(column):
    if column.server_default is not None:
        try:
            return str(column.server_default.arg)
        except Exception:
            return None
    if column.default is not None:
        try:
            arg = column.default.arg
        except Exception:
            return None
        if callable(arg):
            return None
        return _sql_literal(arg)
    return None


def _compile_type(column, engine):
    try:
        compiled = column.type.compile(dialect=engine.dialect)
    except Exception:
        compiled = None

    if not compiled or isinstance(column.type, sqltypes.NullType):
        return "TEXT"
    return compiled


def add_missing_columns(db, logger: Optional[object] = None) -> int:
    """Create missing tables and add missing columns based on SQLAlchemy models.

    Tables first (``CREATE TABLE IF NOT EXISTS`` semantics via
    ``checkfirst=True``): a database created before a model existed -- e.g. an
    established deployment picking up a new feature table such as
    ``account_tokens`` -- would otherwise keep failing at runtime, because the
    old code skipped tables it did not recognise. Then, for tables that
    already existed, add any missing columns.

    SQLite-safe: only uses CREATE TABLE / ALTER TABLE ADD COLUMN, omits
    NOT NULL/UNIQUE/INDEX enforcement on added columns.
    Returns the number of tables + columns created/added.
    """
    engine = db.engine
    inspector = inspect(engine)
    columns_added = 0

    for table in db.Model.metadata.sorted_tables:
        table_name = table.name

        if not inspector.has_table(table_name):
            try:
                table.create(engine, checkfirst=True)
                columns_added += 1
                if logger:
                    logger.info(
                        f"Schema auto-migrate: created missing table {table_name}"
                    )
            except Exception as exc:
                db.session.rollback()
                if logger:
                    logger.warning(
                        f"Schema auto-migrate: failed to create {table_name}: {exc}"
                    )
            continue

        existing_cols = {c["name"] for c in inspector.get_columns(table_name)}

        for column in table.columns:
            if column.name in existing_cols:
                continue

            col_type = _compile_type(column, engine)
            default_sql = _default_sql(column)

            sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{column.name}" {col_type}'
            if default_sql is not None:
                sql += f" DEFAULT {default_sql}"

            try:
                db.session.execute(text(sql))
                db.session.commit()
                columns_added += 1
                if logger:
                    logger.info(
                        f"Schema auto-migrate: added {table_name}.{column.name}"
                    )
            except Exception as exc:
                db.session.rollback()
                if logger:
                    logger.warning(
                        f"Schema auto-migrate: failed {table_name}.{column.name}: {exc}"
                    )

    return columns_added


# ── Multi-server: import idempotency at the DB layer ─────────────────────


def _fk_child_tables(db, parent_table: str, parent_pk: str = "id"):
    """Return list of (child_table, child_fk_column) that reference parent_table.pk.

    Used by dedupe_games() to cascade-delete child rows of duplicate games
    generically, without hard-coding every child table name.
    """
    children = []
    for table in db.Model.metadata.sorted_tables:
        child_name = table.name
        if child_name == parent_table:
            continue
        for fk in table.foreign_keys:
            # fk.target_fullname is like "games.id" — check it references
            # our parent table's primary key.
            if (
                fk.target_fullname
                == f"{parent_table}.{parent_pk}"
            ):
                # fk.parent is the child Column that carries the FK constraint.
                children.append((child_name, fk.parent.name))
                break
    return children


def dedupe_games(db, logger: Optional[object] = None) -> int:
    """Remove duplicate games, keeping the lowest-id row per (team_id,
    sort_date, opponent).

    Child rows (player_stats, shot_events, game_events, lineup_segments, …)
    are deleted via FK introspection so the dedupe is complete and safe to
    re-run. Returns the number of duplicate game rows removed.
    """
    engine = db.engine
    inspector = inspect(engine)

    if not inspector.has_table("games"):
        return 0

    # Find duplicates: same team_id + sort_date + opponent, more than one row.
    dupes = db.session.execute(
        text(
            "SELECT MIN(id) AS keep_id, team_id, sort_date, opponent, "
            "COUNT(*) AS n FROM games "
            "GROUP BY team_id, sort_date, opponent HAVING COUNT(*) > 1"
        )
    ).all()

    removed = 0
    for keep_id, team_id, sort_date, opponent, n in dupes:
        # Child rows of all duplicate games (including the keeper's children
        # would be wrong — we only delete children of the *loser* rows).
        loser_ids = db.session.execute(
            text(
                "SELECT id FROM games WHERE team_id = :t AND sort_date = :s "
                "AND opponent = :o AND id != :k ORDER BY id"
            ),
            {"t": team_id, "s": sort_date, "o": opponent, "k": keep_id},
        ).scalars().all()

        for loser_id in loser_ids:
            # Delete child rows referencing this game.
            for child_table, fk_col in _fk_child_tables(db, "games"):
                try:
                    db.session.execute(
                        text(
                            f'DELETE FROM "{child_table}" WHERE "{fk_col}" = :lid'
                        ),
                        {"lid": loser_id},
                    )
                except Exception:
                    # Child table may not exist or lack this FK on this
                    # dialect; skip it without aborting the dedupe transaction.
                    pass

            db.session.execute(
                text("DELETE FROM games WHERE id = :lid"), {"lid": loser_id}
            )
            removed += 1

    if removed:
        db.session.commit()
        if logger:
            logger.info(f"Dedupe games: removed {removed} duplicate row(s)")

    return removed


def add_games_unique_index(db, logger: Optional[object] = None) -> bool:
    """Create ``uq_games_team_date_opponent`` on games(team_id, sort_date,
    opponent) after deduping. Idempotent and safe to re-run on every deploy.

    Returns True when the index is in place.
    """
    engine = db.engine
    inspector = inspect(engine)

    if not inspector.has_table("games"):
        if logger:
            logger.warning("add_games_unique_index: games table missing")
        return False

    # Always dedupe first so the unique index can be created.
    dedupe_games(db, logger=logger)

    dialect = engine.dialect.name
    index_name = "uq_games_team_date_opponent"
    existing = {
        idx["name"] for idx in inspector.get_indexes("games")
    } | {
        c["name"] for c in inspector.get_unique_constraints("games")
    }

    if index_name in existing:
        return True

    try:
        if dialect == "postgresql":
            db.session.execute(
                text(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
                    f'ON games (team_id, sort_date, opponent)'
                )
            )
        else:
            # SQLite: CREATE UNIQUE INDEX on existing dupes fails; dedupe
            # above already removed them, so this is safe.
            db.session.execute(
                text(
                    f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" '
                    f'ON games (team_id, sort_date, opponent)'
                )
            )
        db.session.commit()
        if logger:
            logger.info(f"Created {index_name} on games(team_id, sort_date, opponent)")
        return True
    except Exception as exc:
        db.session.rollback()
        if logger:
            logger.warning(f"add_games_unique_index failed: {exc}")
        return False
