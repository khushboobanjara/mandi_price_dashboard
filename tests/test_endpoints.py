import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import get_db
from app.services import ingest
from tests.test_ingest import FakeClient, good_data


@pytest.fixture()
def client(session_factory, monkeypatch):
    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override
    monkeypatch.setattr(main, "check_connection", lambda: None)
    # No `with TestClient(...)`, so lifespan/scheduler are not started in tests.
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["database"] is True


def test_health_degraded_when_db_down(client, monkeypatch):
    def boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(main, "check_connection", boom)
    assert client.get("/health").json()["status"] == "degraded"


def test_manual_refresh_flow(client, session_factory, monkeypatch):
    monkeypatch.setattr(
        main, "run_refresh",
        lambda trigger: ingest.run_refresh(trigger, FakeClient(good_data()), session_factory),
    )
    r = client.post("/api/refresh")
    assert r.status_code == 202  # TestClient runs the background task before returning
    status = client.get("/api/refresh/status").json()
    assert status["last_refresh"]["status"] == "success"
    assert status["last_refresh"]["trigger"] == "manual"
    assert status["last_successful_refresh_at"].endswith("Z")
    assert client.get("/api/stats").json()["total_records"] == 3
    assert len(client.get("/api/prices/latest?commodity=Mustard").json()) == 1
    assert client.get("/api/fetch-logs").json()[0]["records_inserted"] == 3


def test_manual_refresh_conflict_when_running(client, monkeypatch):
    monkeypatch.setattr(main, "is_refresh_running", lambda: True)
    assert client.post("/api/refresh").status_code == 409


def test_empty_database_endpoints(client):
    assert client.get("/api/stats").json()["total_records"] == 0
    assert client.get("/api/refresh/status").json()["last_refresh"] is None
    assert client.get("/api/fetch-logs").json() == []
