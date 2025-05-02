# services/gateway/app/chat.py
import os, httpx, jwt, json
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/v1")

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.104.68.115:11434")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

@router.post("/chat/completions")
async def completions(req: Request):
    # read body & headers up front
    body = await req.body()
    headers = {k: v for k, v in req.headers.items() if k.lower() != "host"}

    async def iterator():
        # client now lives for the lifetime of this iterator
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/v1/chat/completions",
                content=body,
                headers=headers,
            ) as upstream:
                async for chunk in upstream.aiter_raw():
                    yield chunk

    return StreamingResponse(iterator(), media_type="application/json")

@router.websocket("/chat/completions/ws")
async def ws_completions(ws: WebSocket):
    await ws.accept()

    # Extract token from query or header
    token = ws.query_params.get("token")
    if not token:
        auth_header = ws.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")

    # Validate JWT
    if not token:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing authentication token")
        return

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Not an access token")
        user = payload["sub"]
        print(f"✅ WebSocket connected for user: {user}")
    except jwt.PyJWTError as e:
        print(f"❌ JWT error: {e}")
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    # Process messages in a loop
    try:
        while True:
            try:
                data = await ws.receive_text()
                print(f"[📥] Message received: {data[:100]}...")

                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "POST",
                        f"{OLLAMA_URL}/v1/chat/completions",
                        content=data.encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                    ) as r:
                        if r.status_code != 200:
                            error_text = await r.text()
                            print(f"❌ Ollama error {r.status_code}: {error_text}")
                            await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason="Ollama error")
                            return

                        print("[🔁] Streaming response from Ollama...")
                        async for chunk in r.aiter_raw():
                            chunk_text = chunk.decode("utf-8", errors="replace")
                            print(f"[⬅️] Chunk: {chunk_text[:50]}...")
                            await ws.send_text(chunk_text)

                        # ✅ Send final finish_reason and DONE
                        await ws.send_text(
                            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                        )
                        await ws.send_text("data: [DONE]\n\n")
                        print("[✅] Response complete, ready for next user message")

            except WebSocketDisconnect:
                print(f"[⚠️] Disconnected: {user}")
                break

    except Exception as e:
        print(f"[❌] Server error: {e}")
        import traceback
        traceback.print_exc()
        try:
            await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason=str(e)[:123])
        except:
            pass