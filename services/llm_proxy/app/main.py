from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import logging
import json
import aiohttp
import os
import asyncio

app = FastAPI(title="LLM Streaming Proxy")
log = logging.getLogger("llm_proxy")
logging.basicConfig(level=logging.INFO)

@app.get("/healthz")
async def healthz():
    """Health check endpoint for the LLM proxy service"""
    return {"status": "ok", "message": "LLM proxy service is running"}

@app.websocket("/v1/stream")
async def stream_ws(ws: WebSocket):
    await ws.accept()
    try:
        # 1. Read initial payload
        payload = await ws.receive_json()
        payload.setdefault("stream", True)
        model = payload.get("model")
        if not model or "messages" not in payload:
            log.error("Missing model or messages in payload")
            await ws.send_text(json.dumps({"error": "Missing required fields: model + messages"}))
            return

        # Explicitly log what os.getenv returns BEFORE any default is applied
        raw_ollama_url_env = os.getenv("OLLAMA_URL")
        log.info(f"RAW OLLAMA_URL from env: '{raw_ollama_url_env}'")

        ollama_url = raw_ollama_url_env # Use the raw value
        if not ollama_url:
            log.error("CRITICAL: OLLAMA_URL is not set for llm_proxy FastAPI app!")
            # Forcing it here if not set - this indicates a problem with env var propagation
            ollama_url = "http://100.104.68.115:11434" 
            log.warning(f"OLLAMA_URL was not set, forcing to: {ollama_url}")
        
        log.info(f"🧠 Forwarding to Ollama (model={payload.get('model')}) at {ollama_url}...")
        log.debug(f"Payload → {json.dumps(payload)}")

        # 2. Call Ollama
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{ollama_url}/v1/chat/completions", json=payload, timeout=30) as resp:
                log.info(f"✅ Ollama responded with status: {resp.status}")
                if resp.status != 200:
                    err = await resp.text()
                    log.error(f"❌ Ollama error: {err}")
                    await ws.send_text(json.dumps({"error": err}))
                    return

                # 3. Stream chunks, but suppress the literal "DONE"
                chunk_count = 0
                async for raw in resp.content:
                    for line in raw.split(b"\n"):
                        if not line.startswith(b"data: "):
                            continue

                        chunk = line[len(b"data: "):].strip()
                        if chunk == b"[DONE]":
                            # emit a proper stop event and close
                            stop_event = {"choices":[{"delta":{},"finish_reason":"stop"}]}
                            await ws.send_text(json.dumps(stop_event))
                            log.info("✅ Emitted stop event")
                            await ws.close()
                            log.info("✅ WebSocket closed")
                            return

                        # otherwise pass through the JSON chunk
                        try:
                            # sanity‐check parse
                            data = json.loads(chunk)
                            log.debug(f"Chunk {chunk_count}: {data}")
                            await ws.send_text(chunk.decode())
                            chunk_count += 1
                        except json.JSONDecodeError:
                            log.warning(f"Skipping invalid JSON chunk: {chunk}")
                            continue

    except WebSocketDisconnect:
        log.info("Client disconnected")
    except Exception as e:
        log.exception("💥 Stream error")
        # try to inform client, then close
        try:
            await ws.send_text(json.dumps({"error": str(e)}))
            await ws.close()
        except:
            pass
