"""Server-only PostgreSQL adapter; no silent fallback or uncertain write retries."""

from urllib.parse import quote, urlsplit

from transport import request_json, setting


class StorageError(Exception):
    status_code = 503
    detail = "Database request failed. Your changes are not confirmed. Refresh before retrying."


class SupabaseStore:
    def __init__(self, env, transport=request_json):
        url = urlsplit(setting(env, "SUPABASE_URL"))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.path not in ("", "/")
            or url.query
            or url.fragment
        ):
            raise StorageError()

        key = setting(env, "SUPABASE_SECRET_KEY") or setting(
            env, "SUPABASE_SERVICE_ROLE_KEY"
        )
        if not key:
            raise StorageError()

        self.base = f"https://{url.netloc}/rest/v1/"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if not key.startswith("sb_secret_"):
            self.headers["Authorization"] = "Bearer " + key
        self.transport = transport

    async def request(self, path, method="GET", data=None, prefer=None):
        try:
            headers = {**self.headers, **({"Prefer": prefer} if prefer else {})}
            result = await self.transport(
                self.base + path, method=method, headers=headers, data=data
            )
            if not 200 <= result.status < 300:
                raise StorageError()

            return result.json()

        except Exception as exc:
            raise StorageError() from exc

    async def health(self):
        await self.request("ittrs_settings?select=key&limit=1")

    async def rate_limit(self, key, expires, now):
        return await self.request(
            "rpc/ittrs_rate_limit",
            "POST",
            {"p_key": key, "p_expires": expires, "p_now": now},
        )

    async def session(self, token_hash, now):
        rows = await self.request(
            f"ittrs_sessions?token_hash=eq.{quote(token_hash)}&expires_at=gt.{now}&select=expires_at&limit=1"
        )
        return rows[0] if rows else None

    async def create_session(self, token_hash, expires, now):
        await self.request(
            "rpc/ittrs_create_session",
            "POST",
            {"p_hash": token_hash, "p_expires": expires, "p_now": now},
        )

    async def delete_session(self, token_hash):
        await self.request(
            "ittrs_sessions?token_hash=eq." + quote(token_hash), "DELETE"
        )

    async def config(self):
        rows = await self.request("ittrs_settings?key=eq.sla&select=value&limit=1")
        return rows[0]["value"] if rows else None

    async def set_config(self, value):
        await self.request(
            "ittrs_settings?on_conflict=key",
            "POST",
            {"key": "sla", "value": value},
            "resolution=merge-duplicates,return=minimal",
        )

    async def reset_config(self):
        await self.request("ittrs_settings?key=eq.sla", "DELETE")

    async def workload(self):
        return await self.request("rpc/ittrs_workload", "POST", {})

    async def ticket(self, ticket_id):
        rows = await self.request(
            "tickets?id=eq." + quote(ticket_id) + "&select=*&limit=1"
        )
        return rows[0] if rows else None

    async def insert_ticket(self, data):
        rows = await self.request("tickets", "POST", data, "return=representation")
        if not rows or not rows[0].get("id"):
            raise StorageError()

        return rows[0]

    async def update_ticket(self, ticket_id, data):
        rows = await self.request(
            "tickets?id=eq." + quote(ticket_id), "PATCH", data, "return=representation"
        )
        if not rows or not rows[0].get("id"):
            raise StorageError()

        return rows[0]

    async def dashboard(self):
        return await self.request("rpc/ittrs_dashboard", "POST", {})


def storage(env):
    provider = setting(env, "DATABASE_PROVIDER", "supabase")
    if provider == "local-sqlite":
        if setting(env, "APP_ENV") != "local":
            raise StorageError()

        from local_store import LocalStore

        return LocalStore(setting(env, "SQLITE_PATH", ".local/ittrs.sqlite3"))

    if provider != "supabase":
        raise StorageError()

    return SupabaseStore(env)
