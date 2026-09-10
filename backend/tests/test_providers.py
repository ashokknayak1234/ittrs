import asyncio
import json

import pytest

from llm_classifier import AIError, classify_ticket, ollama_options, provider_info
from supabase_client import StorageError, SupabaseStore, storage
from transport import HttpResult


def run(value):
    return asyncio.run(value)


def result(data, status=200):
    return HttpResult(status, json.dumps(data).encode())


DECISION = {
    "category": "Network",
    "severity": "High",
    "team": "Team Beta",
    "decision_rationale": "VPN unavailable; Team Beta handles networking.",
}
REMOTE = {
    "APP_ENV": "production",
    "AI_PROVIDER": "ollama",
    "OLLAMA_BASE_URL": "https://ollama.example.com",
    "OLLAMA_ACCESS_CLIENT_ID": "test-id",
    "OLLAMA_ACCESS_CLIENT_SECRET": "test-secret",
}


def test_workers_ai_redacts_and_validates():
    class AI:
        async def run(self, model, options):
            assert model.startswith("@cf/meta/")
            assert "person@example.com" not in json.dumps(options)
            assert "[REDACTED_EMAIL]" in json.dumps(options)
            assert options["response_format"]["type"] == "json_schema"
            return {"response": json.dumps(DECISION)}

    decision = run(
        classify_ticket("VPN unavailable for person@example.com", {}, {"AI": AI()})
    )
    assert decision.team == "Team Beta"


def test_ollama_contract_local_and_tunnel():
    async def remote(url, **options):
        assert url == "https://ollama.example.com/api/chat"
        assert options["headers"]["CF-Access-Client-Secret"] == "test-secret"
        assert options["data"]["stream"] is False
        assert options["data"]["model"] == "qwen2.5:1.5b"
        assert options["max_bytes"] == 65536 and options["timeout"] == 90
        return result({"message": {"content": json.dumps(DECISION)}})

    assert run(classify_ticket("VPN down", {}, REMOTE, remote)).severity == "High"

    async def local(url, **options):
        assert url == "http://127.0.0.1:11434/api/chat"
        assert "CF-Access-Client-Secret" not in options["headers"]
        return result({"message": {"content": json.dumps(DECISION)}})

    run(
        classify_ticket(
            "VPN down",
            {},
            {**REMOTE, "APP_ENV": "local", "OLLAMA_BASE_URL": "http://127.0.0.1:11434"},
            local,
        )
    )


@pytest.mark.parametrize(
    "change",
    [
        {"OLLAMA_ACCESS_CLIENT_ID": ""},
        {"OLLAMA_ACCESS_CLIENT_SECRET": ""},
        {"OLLAMA_BASE_URL": "http://ollama.example.com"},
        {"OLLAMA_BASE_URL": "https://user:password@ollama.example.com"},
        {"OLLAMA_BASE_URL": "https://ollama.example.com/api/chat"},
        {"OLLAMA_BASE_URL": "https://localhost"},
        {"OLLAMA_TIMEOUT_MS": "0"},
    ],
)
def test_ollama_invalid_configuration(change):
    with pytest.raises(AIError) as error:
        ollama_options({**REMOTE, **change})
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    "failure", ["redirect", "invalid-json", "invalid-schema", "offline", "timeout"]
)
def test_ollama_failures_have_no_fallback(failure):
    class NoFallback:
        async def run(self, *args):
            raise AssertionError("Must not fall back to Workers AI")

    async def http(url, **kwargs):
        if failure == "redirect":
            return result({}, 302)
        if failure == "invalid-json":
            return HttpResult(200, b"not json")
        if failure == "invalid-schema":
            return result({"message": {"content": "{}"}})
        if failure == "timeout":
            raise TimeoutError()
        raise OSError("private diagnostic")

    with pytest.raises(AIError) as error:
        run(classify_ticket("VPN down", {}, {**REMOTE, "AI": NoFallback()}, http))
    assert error.value.status_code == (504 if failure == "timeout" else 502)
    assert "private" not in str(error.value)


def test_production_rejects_demo_and_sqlite():
    with pytest.raises(AIError):
        provider_info({"APP_ENV": "production", "AI_PROVIDER": "demo"})
    with pytest.raises(StorageError):
        storage({"APP_ENV": "production", "DATABASE_PROVIDER": "local-sqlite"})


def test_supabase_secret_and_confirmed_rows():
    calls = []

    async def http(url, **options):
        calls.append((url, options))
        assert options["headers"]["apikey"] == "sb_secret_test"
        assert "Authorization" not in options["headers"]
        return result([{**(options["data"] or {}), "id": "test-id"}])

    db = SupabaseStore(
        {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
        },
        http,
    )
    assert run(db.insert_ticket({"complaint_text": "safe"}))["id"] == "test-id"
    assert (
        calls[0][1]["prefer"]
        if "prefer" in calls[0][1]
        else calls[0][1]["headers"]["Prefer"] == "return=representation"
    )
    run(db.create_session("hash", 200, 100))
    assert calls[-1][0].endswith("rpc/ittrs_create_session")
    assert calls[-1][1]["data"]["p_hash"] == "hash"


@pytest.mark.parametrize("status", [302, 401, 402, 500])
def test_database_failure_is_not_retried_or_exposed(status):
    calls = []

    async def http(url, **options):
        calls.append(url)
        return result({"private": "server diagnostics"}, status)

    db = SupabaseStore(
        {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
        },
        http,
    )
    with pytest.raises(StorageError):
        run(db.insert_ticket({"id": "test"}))
    assert len(calls) == 1
