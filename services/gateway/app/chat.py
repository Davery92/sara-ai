# services/gateway/app/chat.py
import os, httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/v1")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.104.68.115:11434")

@router.post("/chat/completions")
async def completions(req: Request):
    async with httpx.AsyncClient(timeout=None) as client:
        upstream = client.stream(
            "POST",
            f"{OLLAMA_URL}/v1/chat/completions",
            content=await req.body(),
            headers={k: v for k, v in req.headers.items() if k.lower() != "host"},
        )

        async def iterator():
            async with upstream as r:
                async for chunk in r.aiter_raw():
                    yield chunk

        return StreamingResponse(iterator(), media_type="application/json")
