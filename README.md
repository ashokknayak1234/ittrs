# ITTRS — Intelligent Ticket Triage and Routing System

Live app: https://ittrs.omkarrsb.workers.dev

The backend is **Python/FastAPI**, based on the original backend in this repository. Cloudflare Python Workers hosts the API and serves the static frontend. Supabase PostgreSQL stores tickets, login sessions, rate limits, and SLA overrides. Workers AI is the current optional LLM provider; local Ollama through a protected tunnel is also supported.

## Where to edit

| What | Source |
| --- | --- |
| Page structure/content | `cloudflare/public/index.html` |
| Colours, layout, mobile styles | `cloudflare/public/style.css` |
| Browser interactions and API calls | `cloudflare/public/app.js` |
| Search/filter presentation | `cloudflare/public/view-model.js` |
| Python API, login, triage, overrides, escalation | `backend/main.py` |
| Python LLM prompts and provider connections | `backend/llm_classifier.py` |
| Python Supabase queries | `backend/supabase_client.py` |
| Python HTTP transport | `backend/transport.py` |
| Pydantic validation and taxonomy | `backend/models.py` |
| PII redaction | `backend/pii_redactor.py` |
| SLA rules and calculation | `backend/config/sla_rules.yaml`, `backend/sla_config.py` |
| Cloudflare deployment | `backend/wrangler.jsonc` |
| Database schema history | `supabase/migrations/` |

`backend/worker.py` is a small Python ASGI entrypoint. `backend/build_worker.py` packages the canonical Python source into an ignored build directory so virtual environments, tests, credentials, and development files are not uploaded. Do not edit the generated `.worker-source/` directory.

There is no application backend written in JavaScript/Node. JavaScript is used by the browser; Node is also required by Cloudflare's deployment tooling. The old JavaScript API, D1 development setup, duplicate HTML dashboards, and obsolete all-in-one Docker configuration have been removed.

## Local development

Install Python 3.13+ and [uv](https://docs.astral.sh/uv/getting-started/installation/). From the repository:

```powershell
cd backend
uv sync
uv run python local_run.py
```

Open http://127.0.0.1:8787. Login: `admin` / `local-demo-only`.

This is explicitly labelled offline demo mode: Python/FastAPI, local SQLite, and deterministic demo rules. It does not call the live database or an AI service. Data lives in `backend/.local/ittrs.sqlite3` and is ignored by Git.

To test with a real local Ollama model:

```powershell
ollama pull qwen2.5:1.5b
uv run python local_run.py --provider ollama
```

Ollama must be running on the same PC at `http://127.0.0.1:11434`. Stop the existing local server before starting the other provider. Both local modes use the same offline SQLite database; SQLite is rejected in production.

## Test and deploy

GitHub pushes do not automatically deploy; run Wrangler locally as described below.

From `backend/`:

```powershell
uv run pytest -q
uv run pywrangler deploy --dry-run
uv run pywrangler deploy
```

Use `uv run pywrangler dev --port 8790` for a Cloudflare-runtime integration check. It uses production provider settings and real remote services when credentials are configured; it is not the offline demo. Restart it after editing backend source to rebuild the packaged files. For a local header-free check of the backend, the health route is `/health` and reports `runtime: python` and `framework: fastapi`.

The Worker name/account is pinned in `backend/wrangler.jsonc`. Use `uv run pywrangler login --device` and `uv run pywrangler whoami` to authenticate the correct account. Existing deployed secrets are retained during code deployments. The `pyproject.toml`, `uv.lock`, and `pylock.toml` files describe/pin native development and Cloudflare-compatible Python packages.

Frontend-only checks, from `cloudflare/`:

```powershell
npm test
```

Changing the frontend also requires deployment from `backend/`, because its Wrangler configuration uploads the static assets with the Python API.

## Secrets and database

Copy `backend/.env.example` to `backend/.env` and supply secrets locally. Do not commit or share the populated file. Upload with:

```powershell
uv run pywrangler secret bulk .env
```

Use a Supabase server secret (`sb_secret_...`) or the legacy service-role key, never a public/anon key. No secrets are embedded in the frontend. Browser login uses an HttpOnly, Secure, SameSite cookie; only a hash of its token is stored in PostgreSQL. Production passwords must have at least 16 characters.

The existing Supabase project already has all three migrations applied. **Do not rerun them.** Switching from the JavaScript Worker to Python uses the same tables and functions; no data migration is needed. For a genuinely new database, apply the files in `supabase/migrations/` in timestamp order using the Supabase SQL editor or your migration workflow.

SLA settings are persisted in PostgreSQL and survive deployments. Workload is calculated from stored tickets, not per-process counters. No automatic D1 fallback or write-back queue exists. Failed writes are not retried automatically because a timeout may occur after a commit; refresh before resubmitting.

## Behaviour preserved and improved

The original categories, severity levels, routing teams, configurable YAML SLA calculations, PII redaction, ticket submission, override, and customer-not-satisfied escalation remain. The frontend uses the same API URLs. Authentication, rate limits, workload, and SLA overrides now use persistent storage instead of process-local state. Model output is validated before saving; raw complaints are redacted before inference and storage.

Legacy clients may explicitly configure `ITTRS_API_KEY` server-side and use it when logging in to receive an `access_token`; subsequent requests use that key plus `X-Admin-Token`. The old hardcoded development key is not accepted by default, and triage now requires an authenticated session. The website uses cookies and needs no API key.

The inference path uses the allowed optional LLM API approach. No Pandas/scikit-learn training pipeline is implemented, and the project should not claim to train a classical ML model.

## Optional Ollama provider

The optional Ollama provider connects through a protected Cloudflare Tunnel with Access service authentication. The real tunnel still needs setup on the model host; it is not required when using Workers AI.

## Limits

No multi-user roles, password recovery, ticket closure, or retention workflow is implemented. Workload counts stored tickets; the queue displays the newest 100. Regex PII redaction is imperfect. Concurrent triage requests can see the same workload snapshot. Provider health is verified by a test classification, not just `/health`. The local Ollama computer must stay awake and connected.

Cloudflare Python Workers is currently a beta platform; the application source is Python/FastAPI, using Cloudflare's official Python ASGI adapter. See [Cloudflare FastAPI support](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/).
