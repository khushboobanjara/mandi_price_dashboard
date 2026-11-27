"""Stage 5: frontend serving, health probes, security headers, gzip, refresh cooldown."""
import pytest
from fastapi.testclient import TestClient

from app import main
from app.database import get_db


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
    monkeypatch.setattr(main, "_last_manual_started", 0.0)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_index_served_with_versioned_assets(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "__ASSET_V__" not in r.text            # placeholder replaced
    assert "/static/js/app.js?v=" in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_static_assets_have_correct_types(client):
    js = client.get("/static/js/app.js")
    assert js.status_code == 200 and "javascript" in js.headers["content-type"]
    assert "text/css" in client.get("/static/css/style.css").headers["content-type"]
    assert client.get("/static/vendor/chart.umd.js").status_code == 200
    assert client.get("/favicon.svg").status_code == 200


def test_only_public_subfolders_are_exposed(client):
    assert client.get("/static/index.html").status_code == 404
    assert client.get("/static/../app/config.py").status_code == 404


def test_security_headers_and_request_id(client):
    r = client.get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]
    api = client.get("/api/stats")
    assert api.headers["cache-control"] == "no-cache"
    assert "content-security-policy" not in client.get("/health").headers


def test_gzip_for_large_responses(client):
    r = client.get("/static/vendor/chart.umd.js", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_health_has_extra_fields(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["database"] is True
    assert body["version"] and body["uptime_seconds"] >= 0
    assert body["data_freshness"] == "never"      # empty database


def test_health_live_and_ready(client, monkeypatch):
    assert client.get("/health/live").json() == {"status": "alive"}
    # Scheduler is not started by TestClient (no lifespan), so not ready:
    assert client.get("/health/ready").status_code == 503
    from types import SimpleNamespace
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=True))
    assert client.get("/health/ready").status_code == 200
    monkeypatch.setattr(main, "check_connection", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.get("/health/ready").status_code == 503


def test_manual_refresh_cooldown(client, monkeypatch):
    monkeypatch.setattr(main, "run_refresh", lambda trigger: None)
    assert client.post("/api/refresh").status_code == 202
    r = client.post("/api/refresh")
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_unhandled_error_returns_json_with_request_id(session_factory, monkeypatch):
    def boom():
        raise RuntimeError("kaboom")
    monkeypatch.setattr(main, "_last_success", lambda db: boom())
    monkeypatch.setattr(main, "check_connection", lambda: None)

    def override():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()
    main.app.dependency_overrides[get_db] = override
    try:
        c = TestClient(main.app, raise_server_exceptions=False)
        r = c.get("/health")
        assert r.status_code == 500
        assert r.json()["detail"] == "Internal server error" and r.json()["request_id"]
    finally:
        main.app.dependency_overrides.clear()
