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
