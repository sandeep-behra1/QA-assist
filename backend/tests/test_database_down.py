"""A database outage is reported plainly (503), not as a 500 with a stack trace."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


def test_unreachable_database_returns_503_with_a_hint():
    def broken_db():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))
        yield  # pragma: no cover - makes this a generator dependency

    app.dependency_overrides[get_db] = broken_db
    try:
        response = TestClient(app, raise_server_exceptions=False).get("/verticals")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    assert "not reachable" in response.json()["detail"]
