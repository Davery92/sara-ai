"""
FastAPI dependency that returns a JetStream context.

During unit-tests we just create one connection the first time and
reuse it; real prod code can swap this for a pooled or DI-managed
version without changing the import path.
"""
import asyncio
from functools import lru_cache
from nats.aio.client import Client as NATS
from fastapi import Depends

NATS_URL = "nats://nats:4222"

@lru_cache(maxsize=1)
def _loop():
    return asyncio.get_event_loop()

_js_singleton = None

async def _init_js():
    global _js_singleton
    if _js_singleton is None:
        nc = NATS()
        await nc.connect(servers=[NATS_URL])
        _js_singleton = nc.jetstream()
    return _js_singleton

async def get_js() -> "nats.js.JetStreamContext":   # noqa: F821 (forward ref)
    return await _init_js()
