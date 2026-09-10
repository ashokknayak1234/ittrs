"""SQLite storage for offline CPython development only; never a production fallback."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from supabase_client import StorageError


class LocalStore:
    def __init__(self, path):

        self.path = str(path)

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with self.connection() as db:
            db.executescript("""

                CREATE TABLE IF NOT EXISTS tickets (

                    id TEXT PRIMARY KEY, complaint_text TEXT NOT NULL, category TEXT NOT NULL,

                    severity TEXT NOT NULL, team TEXT NOT NULL, sla_risk_level TEXT NOT NULL,

                    decision_rationale TEXT NOT NULL, escalation_status TEXT NOT NULL,

                    is_overridden INTEGER NOT NULL DEFAULT 0, override_reason TEXT,

                    satisfaction_status TEXT NOT NULL DEFAULT 'Normal', sla_alerted INTEGER NOT NULL DEFAULT 0,

                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));

                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);

                CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);

                CREATE TABLE IF NOT EXISTS rate_limits (key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL);

            """)

    @contextmanager
    def connection(self):

        db = sqlite3.connect(self.path, timeout=10)

        db.row_factory = sqlite3.Row

        try:
            with db:
                yield db

        except sqlite3.Error as exc:
            raise StorageError() from exc

        finally:
            db.close()

    async def health(self):

        with self.connection() as db:
            db.execute("SELECT 1").fetchone()

    async def rate_limit(self, key, expires, now):

        with self.connection() as db:
            db.execute("DELETE FROM rate_limits WHERE expires_at < ?", (now,))

            return db.execute(
                "INSERT INTO rate_limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1 RETURNING count",
                (key, expires),
            ).fetchone()[0]

    async def session(self, token_hash, now):

        with self.connection() as db:
            row = db.execute(
                "SELECT expires_at FROM sessions WHERE token_hash=? AND expires_at>?",
                (token_hash, now),
            ).fetchone()

            return dict(row) if row else None

    async def create_session(self, token_hash, expires, now):

        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))

            db.execute("INSERT INTO sessions VALUES (?,?)", (token_hash, expires))

    async def delete_session(self, token_hash):

        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))

    async def config(self):

        with self.connection() as db:
            row = db.execute("SELECT value FROM settings WHERE key='sla'").fetchone()

            return json.loads(row[0]) if row else None

    async def set_config(self, value):

        with self.connection() as db:
            db.execute(
                "INSERT INTO settings VALUES ('sla',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (json.dumps(value),),
            )

    async def reset_config(self):

        with self.connection() as db:
            db.execute("DELETE FROM settings WHERE key='sla'")

    async def workload(self):

        with self.connection() as db:
            return {
                row[0]: row[1]
                for row in db.execute("SELECT team,COUNT(*) FROM tickets GROUP BY team")
            }

    async def ticket(self, ticket_id):

        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM tickets WHERE id=?", (ticket_id,)
            ).fetchone()

            return dict(row) if row else None

    async def insert_ticket(self, data):

        keys = (
            "id",
            "complaint_text",
            "category",
            "severity",
            "team",
            "sla_risk_level",
            "decision_rationale",
            "escalation_status",
        )

        with self.connection() as db:
            db.execute(
                "INSERT INTO tickets ("
                + ",".join(keys)
                + ") VALUES ("
                + ",".join("?" for _ in keys)
                + ")",
                [data[k] for k in keys],
            )

        return await self.ticket(data["id"])

    async def update_ticket(self, ticket_id, data):

        allowed = {
            "team",
            "severity",
            "override_reason",
            "is_overridden",
            "sla_risk_level",
            "escalation_status",
            "decision_rationale",
            "satisfaction_status",
            "sla_alerted",
        }

        if not data or not set(data) <= allowed:
            raise StorageError()

        with self.connection() as db:
            db.execute(
                "UPDATE tickets SET "
                + ",".join(k + "=?" for k in data)
                + " WHERE id=?",
                [*data.values(), ticket_id],
            )

        return await self.ticket(ticket_id)

    async def dashboard(self):

        with self.connection() as db:
            counts = dict(
                db.execute("""SELECT COUNT(*) total_tickets,

                COALESCE(SUM(severity='Critical'),0) critical_tickets,

                COALESCE(SUM(sla_alerted),0) sla_alerts,

                COALESCE(SUM(satisfaction_status='Not_Satisfied'),0) not_satisfied FROM tickets""").fetchone()
            )

            tickets = [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM tickets ORDER BY created_at DESC LIMIT 100"
                )
            ]

        return {**counts, "workload": await self.workload(), "tickets": tickets}
