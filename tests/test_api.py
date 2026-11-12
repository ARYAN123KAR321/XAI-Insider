"""API-level tests: auth, role enforcement, error contract."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _client(isolated_env):
    from app.api.main import create_app
    return TestClient(create_app())


def test_health(isolated_env):
    c = _client(isolated_env)
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "X-Request-ID" in r.headers


def test_auth_required(isolated_env):
    c = _client(isolated_env)
    assert c.get("/api/v1/datasets").status_code == 401


def test_login_and_error_contract(isolated_env):
    c = _client(isolated_env)
    bad = c.post("/api/v1/auth/login", json={"username": "tester", "password": "nope"})
    assert bad.status_code == 401
    body = bad.json()
    assert body["code"] == 401 and "request_id" in body

    ok = c.post("/api/v1/auth/login", json={"username": "tester", "password": "pw"})
    assert ok.status_code == 200
    assert ok.json()["access_token"]


def test_reviewer_cannot_create_case(isolated_env):
    """T-09: role enforcement is server-side, not just UI hiding."""
    c = _client(isolated_env)
    token = c.post("/api/v1/auth/login",
                   json={"username": "rev", "password": "pw"}).json()["access_token"]
    r = c.post("/api/v1/cases", json={"title": "x"},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "request_id" in r.json()


def test_analyst_can_create_case(isolated_env):
    c = _client(isolated_env)
    token = c.post("/api/v1/auth/login",
                   json={"username": "tester", "password": "pw"}).json()["access_token"]
    r = c.post("/api/v1/cases", json={"title": "investigation"},
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert r.json()["case_id"].startswith("case_")