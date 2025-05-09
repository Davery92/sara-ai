# services/gateway/app/chat.py
import os, httpx, jwt, json, logging, traceback
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, status, HTTPException, Depends
from fastapi.responses import StreamingResponse
from .auth import verify

router = APIRouter(prefix="/v1")

# Set up logging
log = logging.getLogger("gateway.chat")
logging.basicConfig(level=logging.INFO)

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://100.104.68.115:11434")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

@router.post("/chat/completions")
async def completions(req: Request, auth_payload: dict = Depends(verify)):
    # User is authenticated since verify dependency passed
    user = auth_payload["sub"]
    print(f"✅ Chat completion request from user: {user}")
    
    # read body & headers up front
    body = await req.body()
    body_str = body.decode('utf-8')
    log.info(f"Request body: {body_str[:200]}...")
    
    # Check if we have a valid model specified
    try:
        body_json = json.loads(body_str)
        model = body_json.get('model', 'unknown')
        log.info(f"Using model: {model}")
    except Exception as e:
        log.error(f"Failed to parse body JSON: {e}")
        model = 'unknown'
    
    headers = {k: v for k, v in req.headers.items() if k.lower() != "host"}
    log.info(f"Headers: {headers}")
    log.info(f"Forwarding to Ollama URL: {OLLAMA_URL}/v1/chat/completions")

    async def iterator():
        # client now lives for the lifetime of this iterator
        log.info("Creating HTTP client for streaming response")
        async with httpx.AsyncClient(timeout=60.0) as client:  # Set a reasonable timeout
            try:
                log.info("Starting streaming request to Ollama")
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/v1/chat/completions",
                    content=body,
                    headers=headers,
                    timeout=60.0  # Set a timeout for the request too
                ) as upstream:
                    log.info(f"Ollama response status: {upstream.status_code}")
                    if upstream.status_code != 200:
                        error_text = await upstream.aread()
                        log.error(f"Ollama error {upstream.status_code}: {error_text}")
                        # Create a properly formatted error response
                        error_json = {
                            "error": {
                                "message": f"Error from Ollama: {error_text}",
                                "type": "ollama_error",
                                "code": upstream.status_code
                            }
                        }
                        yield json.dumps(error_json).encode('utf-8')
                        return
                        
                    chunk_count = 0
                    async for chunk in upstream.aiter_raw():
                        chunk_count += 1
                        if chunk_count <= 3 or chunk_count % 10 == 0:
                            log.info(f"Received chunk #{chunk_count}: {chunk[:50]}")
                        yield chunk
                    
                    log.info(f"Streaming complete, sent {chunk_count} chunks")
            except httpx.TimeoutException:
                log.error(f"Request to Ollama timed out")
                error_json = {
                    "error": {
                        "message": "Request to Ollama timed out",
                        "type": "timeout_error"
                    }
                }
                yield json.dumps(error_json).encode('utf-8')
            except httpx.HTTPError as e:
                log.error(f"HTTP error connecting to Ollama: {e}")
                error_json = {
                    "error": {
                        "message": f"HTTP error: {str(e)}",
                        "type": "http_error"
                    }
                }
                yield json.dumps(error_json).encode('utf-8')
            except Exception as e:
                log.error(f"Error streaming from Ollama: {e}")
                traceback.print_exc()
                error_json = {
                    "error": {
                        "message": f"Error: {str(e)}",
                        "type": "server_error"
                    }
                }
                yield json.dumps(error_json).encode('utf-8')

    log.info("Returning StreamingResponse")
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