"""Shared fixtures. Every test runs against a throwaway DB and the mock composer."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Set before any app import: settings are read at import time, and the archive path in
# particular must not be the repo's real one or tests would write into it.
_TMP = Path(tempfile.mkdtemp(prefix="reportsmith-tests-"))
os.environ.setdefault("REPORTSMITH_ARCHIVE_DIR", str(_TMP / "archive"))
os.environ.setdefault("REPORTSMITH_LLM", "mock")

from app.assemble.engine import default_adapters  # noqa: E402
from app.periods import default_period, next_period  # noqa: E402
from app.template.store import default_template  # noqa: E402


@pytest.fixture
def template():
    return default_template()


@pytest.fixture
def adapters():
    return default_adapters()


@pytest.fixture
def period() -> str:
    return default_period().id


@pytest.fixture
def second_period(period: str) -> str:
    return next_period(period).id


@pytest.fixture
def db_session() -> Iterator:
    """A fresh SQLite file **and a fresh archive directory** per test.

    Both matter. Each test starts pack ids at 1, so a shared archive directory would make
    the second test to issue a pack collide with the first — and the collision would look
    like the immutability guard working, which is exactly the false pass worth avoiding.
    """
    import app.db as db_module
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.settings import settings

    root = Path(tempfile.mkdtemp(prefix="rs-db-"))
    original_archive = settings.archive_dir
    settings.archive_dir = root / "archive"

    path = root / "test.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    original_engine, original_session = db_module.engine, db_module.SessionLocal
    db_module.engine, db_module.SessionLocal = engine, Session
    db_module.init_db()

    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        db_module.engine, db_module.SessionLocal = original_engine, original_session
        settings.archive_dir = original_archive
        # The in-process snapshot cache is keyed on pack id, which restarts at 1 every
        # test. Left populated, the next test's pack 1 would archive the previous test's
        # data — and the hashes would still verify, so nothing would look wrong.
        from app.service import _SNAPSHOTS

        _SNAPSHOTS.clear()
