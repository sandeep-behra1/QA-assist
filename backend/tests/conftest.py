"""Test configuration.

Tests run against SQLite by default so the suite needs no database server.
Set TEST_DATABASE_URL to a PostgreSQL URL to run the same tests against the
real target engine (both are verified).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="cimet-qa-tests-"))
_DEFAULT_SQLITE = f"sqlite:///{(_TMP_ROOT / 'test.db').as_posix()}"

# Must be set before any app module imports, because the engine is built at
# import time from these settings.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", _DEFAULT_SQLITE)
os.environ["MEDIA_ROOT"] = str(_TMP_ROOT / "media")
# Real environment variables beat backend/.env, so a developer's Groq key can
# never make the suite hit the network, spend quota, or turn nondeterministic.
os.environ["LLM_PROVIDER"] = "mock"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed.seed_data import reset_database, seed_all  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    reset_database(session)
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def seeded_db(db: Session) -> Session:
    # Rendering demo audio is skipped for speed; one test covers it explicitly.
    seed_all(db, demo_audio=False)
    return db


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_client(seeded_db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: seeded_db
    yield TestClient(app)
    app.dependency_overrides.clear()
