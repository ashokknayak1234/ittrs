"""Async HTTP shared by CPython and Cloudflare's Python runtime."""

import asyncio
import json
import sys
from dataclasses import dataclass


def setting(env, name, default=""):
    return (
        env.get(name, default) if isinstance(env, dict) else getattr(env, name, default)
    )


@dataclass
class HttpResult:
    status: int
    content: bytes

    def json(self):
        return json.loads(self.content) if self.content else None


async def request_json(
    url, method="GET", headers=None, data=None, timeout=15, max_bytes=4_000_000
):
    """Never follow redirects or retry writes; cap and time-limit responses."""
    payload = None if data is None else json.dumps(data)
    async with asyncio.timeout(timeout):
        if sys.platform == "emscripten":
            from workers import fetch

            response = await fetch(
                url,
                method=method,
                headers=headers or {},
                body=payload,
                redirect="manual",
            )
            reader = response.body.getReader() if response.body is not None else None
            chunks, size = [], 0
            if reader:
                try:
                    while True:
                        chunk = await reader.read()
                        if chunk.done:
                            break
                        value = bytes(chunk.value.to_py())
                        size += len(value)
                        if size > max_bytes:
                            raise ValueError("Response exceeds size limit")

                        chunks.append(value)
                finally:
                    await reader.cancel()
            return HttpResult(response.status, b"".join(chunks))

        import httpx

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
            async with client.stream(
                method, url, headers=headers, content=payload
            ) as response:
                chunks, size = [], 0
                async for value in response.aiter_bytes():
                    size += len(value)
                    if size > max_bytes:
                        raise ValueError("Response exceeds size limit")

                    chunks.append(value)
                return HttpResult(response.status_code, b"".join(chunks))
