"""Canonical Python/FastAPI backend for both Cloudflare and local Uvicorn."""

import hashlib
import os
import secrets
import time
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from llm_classifier import AIError, classify_ticket, provider_info
from models import (
    SEVERITIES,
    TEAMS,
    AdminDashboardResponse,
    AdminLoginRequest,
    NotSatisfiedRequest,
    NotSatisfiedResponse,
    OverrideRequest,
    OverrideResponse,
    SlaConfigResponse,
    TriageRequest,
    TriageResponse,
)
from pii_redactor import redact_pii
from sla_config import SlaConfigError, _validate, compute_sla, load_sla_config
from supabase_client import StorageError, storage
from transport import setting

COOKIE = "ittrs_session"


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise HTTPException(422, f"Text must contain 1–{maximum} characters.")

    return value.strip()


async def rate_limit(request, scope, maximum, seconds):
    now = int(time.time())
    address = request.headers.get("CF-Connecting-IP") or (
        request.client.host if request.client else "local"
    )
    key = hashed(f"{scope}:{address}:{now // seconds}")
    count = await request.state.db.rate_limit(key, (now // seconds + 1) * seconds, now)
    if count > maximum:
        raise HTTPException(429, "Too many requests. Try again later.")


def session_hash(request):
    token = request.cookies.get(COOKIE, "")

    # Optional compatibility for explicitly configured legacy API clients.
    legacy_key = setting(request.state.env, "ITTRS_API_KEY")
    if (
        not token
        and legacy_key
        and secrets.compare_digest(
            hashed(request.headers.get("X-API-Key", "")), hashed(legacy_key)
        )
    ):
        token = request.headers.get("X-Admin-Token", "")
    return hashed(token) if token else ""


async def active_config(db):
    configured = await db.config()
    rules = configured if configured is not None else load_sla_config()
    _validate(rules)
    return {
        "source": "admin_override" if configured is not None else "yaml_defaults",
        "config": rules,
    }


async def get_ticket(db, ticket_id):
    try:
        UUID(ticket_id)
    except ValueError:
        raise HTTPException(404, "Ticket not found.")

    record = await db.ticket(ticket_id)
    if not record:
        raise HTTPException(404, "Ticket not found.")

    return record


class ApiGuard:
    """ASGI middleware without background streaming tasks or mutable globals."""

    def __init__(self, app, env=None, store_factory=storage):
        self.app, self.env, self.store_factory = app, env, store_factory

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        api = request.url.path == "/health" or request.url.path.startswith("/api/")
        started = False

        async def send_headers(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = list(message.get("headers", []))
                if api:
                    headers.append((b"cache-control", b"no-store"))
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-ittrs-backend", b"python-fastapi"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        downstream_receive = receive
        try:
            request.state.env = scope.get(
                "env", self.env if self.env is not None else os.environ
            )
            if api:
                request.state.db = self.store_factory(request.state.env)
                if request.method not in ("GET", "HEAD"):
                    origin = f"{request.url.scheme}://{request.url.netloc}"
                    legacy_key = setting(request.state.env, "ITTRS_API_KEY")
                    legacy = bool(legacy_key) and secrets.compare_digest(
                        hashed(request.headers.get("X-API-Key", "")), hashed(legacy_key)
                    )
                    if request.headers.get("Origin") != origin and not (
                        legacy and not request.cookies.get(COOKIE)
                    ):
                        raise HTTPException(403, "Request origin is not allowed.")
                    if request.url.path not in (
                        "/api/auth/logout",
                        "/api/admin/sla-config/reset",
                    ) and "application/json" not in request.headers.get(
                        "Content-Type", ""
                    ):
                        raise HTTPException(415, "Use application/json.")
                    chunks, size = [], 0
                    async for chunk in request.stream():
                        size += len(chunk)
                        if size > 32768:
                            raise HTTPException(413, "Request too large.")
                        chunks.append(chunk)
                    body, delivered = b"".join(chunks), False

                    async def replay_body():
                        nonlocal delivered
                        if not delivered:
                            delivered = True
                            return {
                                "type": "http.request",
                                "body": body,
                                "more_body": False,
                            }
                        return await receive()

                    downstream_receive = replay_body
                if request.url.path not in ("/health", "/api/auth/login"):
                    if not await request.state.db.session(
                        session_hash(request), int(time.time())
                    ):
                        raise HTTPException(401, "Please sign in.")
            await self.app(scope, downstream_receive, send_headers)
        except (StorageError, AIError, HTTPException) as exc:
            if started:
                raise
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(
                scope, receive, send_headers
            )
        except Exception as exc:
            if started:
                raise
            print("ITTRS request failed:", type(exc).__name__)
            await JSONResponse(
                {"detail": "Service unavailable. Please retry."}, status_code=503
            )(scope, receive, send_headers)


def create_app(env=None, store_factory=storage, classifier=classify_ticket):
    app = FastAPI(
        title="ITTRS Python Ticket Triage API",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(ApiGuard, env=env, store_factory=store_factory)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"detail": "Invalid request. Check the required fields and their lengths."},
            status_code=422,
        )

    @app.get("/health")
    async def health(request: Request):
        await request.state.db.health()
        info = provider_info(request.state.env)
        return {
            "status": "ok",
            "service": "ittrs",
            "runtime": "python",
            "framework": "fastapi",
            "mode": "local-demo" if info["provider"] == "demo" else info["provider"],
            "model": info["model"],
            "database": setting(request.state.env, "DATABASE_PROVIDER", "supabase"),
        }

    @app.post("/api/auth/login")
    async def login(data: AdminLoginRequest, request: Request):
        await rate_limit(request, "login", 10, 900)
        configured = setting(
            request.state.env,
            "ADMIN_PASSWORD",
            setting(request.state.env, "ITTRS_ADMIN_PASSWORD"),
        )
        if not configured or (
            setting(request.state.env, "APP_ENV") != "local" and len(configured) < 16
        ):
            raise HTTPException(
                503, "Set a strong ADMIN_PASSWORD secret before signing in."
            )
        user = setting(
            request.state.env,
            "ADMIN_USER",
            setting(request.state.env, "ITTRS_ADMIN_USER", "admin"),
        )
        good_user = secrets.compare_digest(
            hashed(text(data.username, 100)), hashed(user)
        )
        good_password = secrets.compare_digest(
            hashed(text(data.password, 512)), hashed(configured)
        )
        if not good_user or not good_password:
            raise HTTPException(401, "Invalid username or password.")

        token, now = secrets.token_hex(32), int(time.time())
        await request.state.db.create_session(hashed(token), now + 28800, now)
        result = {"status": "success"}
        legacy_key = setting(request.state.env, "ITTRS_API_KEY")
        if legacy_key and secrets.compare_digest(
            hashed(request.headers.get("X-API-Key", "")), hashed(legacy_key)
        ):
            result.update(access_token=token, token_type="bearer")
        response = JSONResponse(result)
        response.set_cookie(
            COOKIE,
            token,
            max_age=28800,
            httponly=True,
            samesite="strict",
            secure=not (
                setting(request.state.env, "APP_ENV") == "local"
                and request.url.scheme == "http"
            ),
        )
        return response

    @app.get("/api/auth/me")
    async def me(request: Request):
        return {"username": setting(request.state.env, "ADMIN_USER", "admin")}

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        await request.state.db.delete_session(session_hash(request))
        response = JSONResponse({"status": "success"})
        response.delete_cookie(
            COOKIE,
            httponly=True,
            samesite="strict",
            secure=not (
                setting(request.state.env, "APP_ENV") == "local"
                and request.url.scheme == "http"
            ),
        )
        return response

    @app.post("/api/triage", response_model=TriageResponse)
    async def triage(data: TriageRequest, request: Request):
        await rate_limit(request, "triage", 30, 3600)
        safe, contains_pii = redact_pii(text(data.complaint_text, 10000))
        db = request.state.db
        load = await db.workload()
        decision = await classifier(safe, load, request.state.env)
        rules = (await active_config(db))["config"]
        _, risk, line = compute_sla(
            decision.severity, decision.category, load.get(decision.team, 0) + 1, rules
        )
        escalation = (
            "Escalated" if decision.severity in ("High", "Critical") else "Normal"
        )
        info = provider_info(request.state.env)
        rationale = f"[AI] {info['provider']} / {info['model']}\n{decision.decision_rationale}{line}\n[Escalation] {escalation}"
        saved = await db.insert_ticket(
            {
                "id": str(uuid4()),
                "complaint_text": safe,
                "category": decision.category,
                "severity": decision.severity,
                "team": decision.team,
                "sla_risk_level": risk,
                "decision_rationale": rationale,
                "escalation_status": escalation,
            }
        )
        return {
            "status": "success",
            "security_flags": {"pii_redacted": contains_pii},
            "ticket": saved,
        }

    @app.get("/api/dashboard", response_model=AdminDashboardResponse)
    @app.get("/api/admin/dashboard", response_model=AdminDashboardResponse)
    async def dashboard(request: Request):
        return await request.state.db.dashboard()

    @app.get("/api/admin/sla-config", response_model=SlaConfigResponse)
    async def get_config(request: Request):
        return await active_config(request.state.db)

    @app.put("/api/admin/sla-config", response_model=SlaConfigResponse)
    async def put_config(request: Request):
        try:
            rules = await request.json()
            _validate(rules)
        except (ValueError, TypeError, KeyError, SlaConfigError) as exc:
            raise HTTPException(
                422,
                "Invalid SLA rules. Use positive hours/multipliers and ordered risk thresholds.",
            ) from exc
        await request.state.db.set_config(rules)
        return await active_config(request.state.db)

    @app.post("/api/admin/sla-config/reset", response_model=SlaConfigResponse)
    async def reset_config(request: Request):
        await request.state.db.reset_config()
        return await active_config(request.state.db)

    @app.put("/api/tickets/{ticket_id}/override", response_model=OverrideResponse)
    async def override(ticket_id: str, data: OverrideRequest, request: Request):
        if data.team not in TEAMS or data.severity not in SEVERITIES:
            raise HTTPException(422, "Select a valid team and severity.")

        db = request.state.db
        ticket = await get_ticket(db, ticket_id)
        load, rules = await db.workload(), (await active_config(db))["config"]
        count = load.get(data.team, 0) + (0 if data.team == ticket["team"] else 1)
        _, risk, line = compute_sla(data.severity, ticket["category"], count, rules)
        reason, _ = redact_pii(text(data.override_reason, 2000))
        updated = await db.update_ticket(
            ticket_id,
            {
                "team": data.team,
                "severity": data.severity,
                "override_reason": reason,
                "is_overridden": True,
                "sla_risk_level": risk,
                "escalation_status": "Escalated"
                if data.severity in ("High", "Critical")
                else "Normal",
                "decision_rationale": ticket["decision_rationale"]
                + f"\n[Override] {data.team}; {data.severity}."
                + line,
            },
        )
        return {"status": "success", "ticket": updated}

    @app.post(
        "/api/tickets/{ticket_id}/not-satisfied", response_model=NotSatisfiedResponse
    )
    async def not_satisfied(
        ticket_id: str, data: NotSatisfiedRequest, request: Request
    ):
        db = request.state.db
        ticket = await get_ticket(db, ticket_id)
        load, rules = await db.workload(), (await active_config(db))["config"]
        _, risk, line = compute_sla(
            "Critical", ticket["category"], load.get(ticket["team"], 1), rules
        )
        comment, _ = redact_pii(data.comment.strip())
        updated = await db.update_ticket(
            ticket_id,
            {
                "severity": "Critical",
                "escalation_status": "Escalated",
                "satisfaction_status": "Not_Satisfied",
                "sla_alerted": True,
                "sla_risk_level": risk,
                "override_reason": comment or ticket.get("override_reason"),
                "decision_rationale": ticket["decision_rationale"]
                + "\n[Customer not satisfied] Escalated to Critical."
                + line,
            },
        )
        return {"status": "success", "ticket": updated, "sla_alerted": True}

    return app


app = create_app()
