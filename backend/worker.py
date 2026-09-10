"""Cloudflare Python entrypoint; application logic lives in main.py."""
from workers import WorkerEntrypoint, Response, asgi

try:
    from main import app
    startup_error = None
except Exception as error:
    app = None
    startup_error = error

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if startup_error is not None:
            print("Python backend initialization:", type(startup_error).__name__, str(startup_error))
            return Response.from_json({"detail": "Backend initialization failed."}, status=503)
        return await asgi.fetch(app, request, self.env, self.ctx)
