"""Regression tests for the cold-start / idle-stall fixes.

Covers the changes made together because they address one failure mode —
a heavy game save that stalls or errors when the server was idle:

1. ``create_app`` no longer leaves a pooled connection behind when it
   returns (and, under ``AUTO_MIGRATE=False``, performs no database work at
   all). With gunicorn's ``preload_app=True`` the factory runs in the master
   process, so anything pooled there is inherited by every fork and the first
   request each worker serves drives a Postgres backend shared with its
   siblings: crossed libpq protocol, a hang, or psycopg2.DatabaseError
   "error with status PGRES_TUPLES_OK and no message from the libpq".
2. ``core.BoundedSMTPConnection`` bounds SMTP socket I/O with MAIL_TIMEOUT.
3. ``config._engine_options`` adds a bounded libpq connect timeout for
   Postgres only.
"""

import types

import pytest
from sqlalchemy import text

from config import TestingConfig, config_map


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


class _FakeSMTP:
    def __init__(self, host, port, timeout=None, **kwargs):
        self.host, self.port, self.timeout = host, port, timeout
        self.calls = []

    def set_debuglevel(self, level):
        self.calls.append(("debuglevel", level))

    def starttls(self):
        self.calls.append(("starttls",))

    def login(self, username, password):
        self.calls.append(("login", username, password))


def _mail_state(**overrides):
    state = dict(
        server="smtp.example.com",
        port=587,
        use_ssl=False,
        use_tls=False,
        debug=0,
        username=None,
        password=None,
    )
    state.update(overrides)
    return types.SimpleNamespace(**state)


def _recording_factory(sink):
    """Build a fake smtplib.SMTP class that records every constructed instance."""

    class _Fake(_FakeSMTP):
        def __init__(self, host, port, timeout=None, **kwargs):
            super().__init__(host, port, timeout=timeout, **kwargs)
            sink.append(self)

    return _Fake


@pytest.fixture
def file_backed_app(monkeypatch, tmp_path):
    """A testing app backed by a file-based SQLite DB.

    The in-memory database used by TestingConfig gets a SingletonThreadPool
    that holds its one connection open by design, so it cannot show whether
    startup left a *pool* connection behind. A file database uses a normal
    QueuePool, which is the pool shape Postgres gets in production.
    """

    class _FileBackedTestingConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path}/startup_test.db"

    monkeypatch.setitem(config_map, "file_backed_testing", _FileBackedTestingConfig)
    from web import create_app

    app = create_app("file_backed_testing")
    yield app
    with app.app_context():
        from web import db

        db.session.remove()
        db.engine.dispose()


# ---------------------------------------------------------------------------
# 1. create_app must not leave a pooled connection behind
# ---------------------------------------------------------------------------


def test_create_app_leaves_no_pooled_connection(file_backed_app):
    """No connection may survive create_app: gunicorn's preload master runs
    this factory and then forks, so anything pooled here is inherited by
    every worker."""
    from web import db

    with file_backed_app.app_context():
        assert db.engine.pool.checkedin() == 0
        assert db.engine.pool.checkedout() == 0


def test_database_still_usable_after_startup_disposal(file_backed_app):
    """Dropping the startup connection must not break the pool: the next
    checkout opens a fresh one."""
    from web import db

    with file_backed_app.app_context():
        assert db.session.execute(text("SELECT 1")).scalar() == 1
        assert db.engine.pool.checkedout() == 1

        db.session.remove()
        assert db.engine.pool.checkedin() == 1
        assert db.engine.pool.checkedout() == 0


# ---------------------------------------------------------------------------
# 2. Bounded SMTP connection
# ---------------------------------------------------------------------------


def test_mail_timeout_default_is_applied(monkeypatch, app):
    import core
    from core import BoundedSMTPConnection

    created = []
    monkeypatch.setattr(core.smtplib, "SMTP", _recording_factory(created))
    with app.app_context():
        BoundedSMTPConnection(_mail_state()).configure_host()

    assert len(created) == 1
    assert created[0].timeout == 30


def test_mail_timeout_honours_config(monkeypatch, app):
    import core
    from core import BoundedSMTPConnection

    created = []
    monkeypatch.setattr(core.smtplib, "SMTP", _recording_factory(created))
    app.config["MAIL_TIMEOUT"] = 7
    try:
        with app.app_context():
            BoundedSMTPConnection(_mail_state()).configure_host()
    finally:
        app.config["MAIL_TIMEOUT"] = 30

    assert created[-1].timeout == 7


def test_mail_timeout_is_applied_on_tls_and_ssl_paths(monkeypatch, app):
    import core
    from core import BoundedSMTPConnection

    created = []
    monkeypatch.setattr(core.smtplib, "SMTP", _recording_factory(created))
    monkeypatch.setattr(core.smtplib, "SMTP_SSL", _recording_factory(created))

    with app.app_context():
        BoundedSMTPConnection(
            _mail_state(use_tls=True, username="u", password="p")
        ).configure_host()
        BoundedSMTPConnection(_mail_state(use_ssl=True)).configure_host()

    tls_conn, ssl_conn = created[-2], created[-1]
    assert tls_conn.timeout == 30
    assert ("starttls",) in tls_conn.calls  # TLS still negotiated, just bounded
    assert ("login", "u", "p") in tls_conn.calls
    assert ssl_conn.timeout == 30


def test_mail_extension_hands_out_bounded_connection(app):
    from core import BoundedSMTPConnection, mail

    with app.app_context():
        conn = mail.connect()

    assert isinstance(conn, BoundedSMTPConnection)


# ---------------------------------------------------------------------------
# 3. Engine options
# ---------------------------------------------------------------------------


def test_engine_options_bound_postgres_connect(monkeypatch):
    from config import _engine_options

    monkeypatch.delenv("DB_CONNECT_TIMEOUT", raising=False)
    opts = _engine_options("postgresql://user:pass@db/basketball_stats")

    assert opts["connect_args"] == {"connect_timeout": 10}
    assert opts["pool_pre_ping"] is True
    assert opts["pool_recycle"] == 300


def test_engine_options_postgres_connect_timeout_configurable(monkeypatch):
    from config import _engine_options

    monkeypatch.setenv("DB_CONNECT_TIMEOUT", "7")
    opts = _engine_options("postgresql://user:pass@db/basketball_stats")
    assert opts["connect_args"] == {"connect_timeout": 7}


def test_engine_options_sqlite_has_no_connect_args():
    """connect_timeout is libpq-only; the sqlite3 driver would reject it."""
    from config import _engine_options

    assert "connect_args" not in _engine_options(None)
    assert "connect_args" not in _engine_options("sqlite:///some/path.db")


# ---------------------------------------------------------------------------
# 4. AUTO_MIGRATE posture (keeps startup DB work out of the preload master)
# ---------------------------------------------------------------------------


def test_auto_migrate_off_in_base_and_production_config():
    """Production must never migrate inside create_app: gunicorn preloads the
    factory into the master, so any startup DB work leaves a connection behind
    for the forks. Prod runs migrations in the compose `migrator` service."""
    from config import Config, ProductionConfig

    assert Config.AUTO_MIGRATE is False
    assert ProductionConfig.AUTO_MIGRATE is False


def test_auto_migrate_on_in_dev_and_testing_config():
    """Dev and tests keep the convenience behaviour the suite was written
    against (the session-scoped app fixture builds its schema itself)."""
    from config import DevelopmentConfig, TestingConfig

    assert DevelopmentConfig.AUTO_MIGRATE is True
    assert TestingConfig.AUTO_MIGRATE is True


def test_auto_migrate_false_skips_startup_database_work(monkeypatch, tmp_path):
    """With AUTO_MIGRATE off, create_app must not build the schema: no tables
    are created by the factory."""
    from sqlalchemy import inspect

    class _NoMigrateTestingConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path}/no_migrate.db"
        AUTO_MIGRATE = False

    monkeypatch.setitem(config_map, "no_migrate_testing", _NoMigrateTestingConfig)
    from web import create_app

    app = create_app("no_migrate_testing")
    with app.app_context():
        from web import db

        assert app.config["AUTO_MIGRATE"] is False
        # The auto-migrate would have created every model table.
        assert not inspect(db.engine).has_table("players")
