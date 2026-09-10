import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from llm_classifier import AIError
from local_store import LocalStore
from main import create_app
from models import TicketDecision
from supabase_client import StorageError

ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture
def app_state(tmp_path):
    env = {
        "APP_ENV": "local",
        "ADMIN_USER": "admin",
        "ADMIN_PASSWORD": "local-demo-only",
        "AI_PROVIDER": "demo",
        "DATABASE_PROVIDER": "local-sqlite",
    }
    store = LocalStore(tmp_path / "db.sqlite3")
    seen = []

    async def classifier(text, workload, env):
        seen.append(text)
        return TicketDecision(
            category="Network",
            severity="High",
            team="Team Beta",
            decision_rationale="Category=Network; Severity=High; Team=Team Beta because VPN is unavailable.",
        )

    app = create_app(env, lambda _: store, classifier)
    return env, store, classifier, seen, TestClient(app)


def login(client, **overrides):
    return client.post(
        "/api/auth/login",
        headers=ORIGIN,
        json={"username": "admin", "password": "local-demo-only", **overrides},
    )


def test_full_persisted_flow_and_restart(app_state):
    env, db, classifier, seen, client = app_state
    assert client.get("/health").json()["runtime"] == "python"
    assert login(client).status_code == 200
    cookie = client.cookies.get("ittrs_session")
    # A fresh app process uses the same database-backed session.
    client = TestClient(create_app(env, lambda _: db, classifier))
    client.cookies.set("ittrs_session", cookie)
    assert client.get("/api/auth/me").status_code == 200
    r = client.post(
        "/api/triage",
        headers=ORIGIN,
        json={"complaint_text": "VPN unavailable; contact alice@example.com."},
    )
    assert r.status_code == 200, r.text
    ticket = r.json()["ticket"]
    assert r.json()["security_flags"]["pii_redacted"]
    assert (
        "alice@example.com" not in ticket["complaint_text"]
        and "alice@example.com" not in seen[0]
    )
    assert "[SLA rule]" in ticket["decision_rationale"]
    assert ticket["escalation_status"] == "Escalated"
    r = client.put(
        f"/api/tickets/{ticket['id']}/override",
        headers=ORIGIN,
        json={
            "team": "Team Gamma",
            "severity": "Medium",
            "override_reason": "Reviewed by alice@example.com",
        },
    )
    assert r.status_code == 200 and r.json()["ticket"]["team"] == "Team Gamma"
    assert "alice@example.com" not in r.json()["ticket"]["override_reason"]
    r = client.post(
        f"/api/tickets/{ticket['id']}/not-satisfied",
        headers=ORIGIN,
        json={"comment": "Still broken"},
    )
    assert r.status_code == 200 and r.json()["ticket"]["severity"] == "Critical"
    d = client.get("/api/admin/dashboard").json()
    assert (
        d["total_tickets"]
        == d["critical_tickets"]
        == d["sla_alerts"]
        == d["not_satisfied"]
        == 1
    )
    assert d["workload"] == {"Team Gamma": 1}
    assert client.post("/api/auth/logout", headers=ORIGIN).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_persisted_sla_settings_validation_and_reset(app_state):
    env, db, classifier, _, client = app_state
    login(client)
    rules = client.get("/api/admin/sla-config").json()["config"]
    rules["severity_sla_hours"]["Critical"] = 0.5
    assert (
        client.put("/api/admin/sla-config", headers=ORIGIN, json=rules).status_code
        == 200
    )
    another = TestClient(create_app(env, lambda _: db, classifier))
    another.cookies.update(client.cookies)
    assert (
        another.get("/api/admin/sla-config").json()["config"]["severity_sla_hours"][
            "Critical"
        ]
        == 0.5
    )
    rules["risk_thresholds_hours"]["high"] = 99
    assert (
        client.put("/api/admin/sla-config", headers=ORIGIN, json=rules).status_code
        == 422
    )
    assert (
        client.post("/api/admin/sla-config/reset", headers=ORIGIN).json()["config"][
            "severity_sla_hours"
        ]["Critical"]
        == 2
    )


def test_auth_origin_expiry_invalid_requests(app_state):
    env, db, _, _, client = app_state
    assert client.get("/api/admin/dashboard").status_code == 401
    assert login(client, password="bad").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "local-demo-only"}
        ).status_code
        == 403
    )
    assert login(client).status_code == 200
    assert (
        client.post(
            "/api/triage", headers=ORIGIN, json={"complaint_text": " "}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/triage",
            headers={**ORIGIN, "Content-Type": "application/json"},
            content="{",
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/triage",
            headers={**ORIGIN, "Content-Type": "application/json"},
            content="x" * 32769,
        ).status_code
        == 413
    )
    assert (
        client.post("/api/triage", headers=ORIGIN, content="wrong type").status_code
        == 415
    )
    assert (
        client.put(
            "/api/tickets/nope/override",
            headers=ORIGIN,
            json={"team": "Team Beta", "severity": "Low", "override_reason": "test"},
        ).status_code
        == 404
    )
    with db.connection() as connection:
        connection.execute("UPDATE sessions SET expires_at=?", (int(time.time()) - 1,))
    assert client.get("/api/auth/me").status_code == 401


def test_rate_limit_and_secure_cookie(app_state):
    env, db, classifier, _, client = app_state
    for _ in range(10):
        assert login(client, password="bad").status_code == 401
    assert login(client).status_code == 429
    env.update(
        APP_ENV="production",
        AI_PROVIDER="workers-ai",
        ADMIN_PASSWORD="a-strong-password-for-testing",
    )
    with db.connection() as connection:
        connection.execute("DELETE FROM rate_limits")
    secure = TestClient(
        create_app(env, lambda _: db, classifier), base_url="https://testserver"
    )
    response = secure.post(
        "/api/auth/login",
        headers={"Origin": "https://testserver"},
        json={"username": "admin", "password": env["ADMIN_PASSWORD"]},
    )
    assert response.status_code == 200
    assert (
        "Secure" in response.headers["set-cookie"]
        and "HttpOnly" in response.headers["set-cookie"]
    )
    assert "access_token" not in response.json()


def test_failure_never_creates_a_ticket(app_state):
    env, db, _, _, _ = app_state

    async def failed(*args):
        raise AIError(502, "AI unavailable. No ticket was saved.")

    client = TestClient(create_app(env, lambda _: db, failed))
    login(client)
    assert (
        client.post(
            "/api/triage", headers=ORIGIN, json={"complaint_text": "VPN down"}
        ).status_code
        == 502
    )
    assert asyncio.run(db.dashboard())["total_tickets"] == 0

    class FailingStore:
        async def health(self):
            raise StorageError()

    broken = TestClient(create_app(env, lambda _: FailingStore()))
    assert broken.get("/health").status_code == 503
