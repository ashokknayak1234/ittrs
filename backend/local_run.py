"""Run the same FastAPI application locally with offline SQLite and demo/Ollama."""

import argparse
import os
from pathlib import Path

import uvicorn
from fastapi.staticfiles import StaticFiles

from main import create_app


def local_app(provider="demo"):

    env = dict(os.environ)

    env.update(
        APP_ENV="local",
        DATABASE_PROVIDER="local-sqlite",
        AI_PROVIDER=provider,
        ADMIN_USER="admin",
        ADMIN_PASSWORD="local-demo-only",
    )

    env.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    app = create_app(env=env)

    app.mount(
        "/",
        StaticFiles(
            directory=Path(__file__).resolve().parent.parent / "cloudflare/public",
            html=True,
        ),
        name="frontend",
    )

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--provider", choices=["demo", "ollama"], default="demo")

    parser.add_argument("--port", type=int, default=8787)

    args = parser.parse_args()

    uvicorn.run(local_app(args.provider), host="127.0.0.1", port=args.port)
