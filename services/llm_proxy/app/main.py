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
    return {
        "status": "ok",
        "message": "LLM proxy service is running"
    }

@app.websocket("/v1/stream")
async def stream_ws(ws: WebSocket):
    await ws.accept()
    try:
        # Expect full OpenAI-style payload
        payload = await ws.receive_json()
        payload.setdefault("stream", True)
        model = payload.get("model")

        if not model or "messages" not in payload:
            log.error("Missing model or messages in payload")
            await ws.send_text(json.dumps({"error": "Missing required fields: model + messages"}))
            return

        ollama_url = os.getenv('OLLAMA_URL', 'http://localhost:11434')
        log.info(f"🧠 Forwarding to Ollama (model={model}) via /v1/chat/completions")
        log.info(f"Full payload: {json.dumps(payload)}")

        async with aiohttp.ClientSession() as session:
            url = f"{ollama_url}/v1/chat/completions"
            try:
                async with session.post(url, json=payload, timeout=30.0) as resp:
                    log.info(f"✅ Ollama responded with status: {resp.status}")
                    
                    if resp.status != 200:
                        text = await resp.text()
                        log.error(f"❌ Ollama error response: {text}")
                        await ws.send_text(json.dumps({"error": text}))
                        return

                    # Process streaming response
                    chunk_count = 0
                    async for raw in resp.content:
                        log.info(f"Raw chunk received: {raw}")
                        for line in raw.split(b"\n"):
                            if not line.startswith(b"data: "):
                                continue
                            
                            chunk = line.removeprefix(b"data: ").strip()
                            
                            if chunk == b"[DONE]":
                                await ws.send_text("[DONE]")
                                log.info("✅ Ollama stream completed")
                                return
                            
                            try:
                                # Parse the JSON chunk to access data
                                chunk_data = json.loads(chunk)
                                log.info(f"Chunk {chunk_count}: {json.dumps(chunk_data)}")
                                
                                # Filter out <think> and </think> tags from Qwen
                                if (chunk_data.get("choices") and 
                                    len(chunk_data["choices"]) > 0 and 
                                    chunk_data["choices"][0].get("delta") and 
                                    "content" in chunk_data["choices"][0]["delta"]):
                                    
                                    content = chunk_data["choices"][0]["delta"]["content"]
                                    if content == "<think>" or content == "</think>":
                                        continue
                                
                                # Pass through the raw OpenAI-compatible format
                                # Frontend expects: data.choices[0]
                                await ws.send_text(chunk.decode("utf-8"))
                                chunk_count += 1
                                
                            except json.JSONDecodeError:
                                log.warning(f"Non-JSON chunk: {chunk}")
                                continue
                            except Exception as e:
                                log.warning(f"⚠️ Error processing chunk: {str(e)}")
                                continue
            except aiohttp.ClientError as e:
                log.error(f"❌ Ollama request failed: {str(e)}")
                await ws.send_text(json.dumps({"error": f"LLM service request failed: {str(e)}"}))
            except asyncio.TimeoutError:
                log.error("❌ Ollama request timed out")
                await ws.send_text(json.dumps({"error": "LLM service request timed out"}))

    except WebSocketDisconnect:
        log.info("Client disconnected")
    except Exception as e:
        log.exception("💥 Stream error")
        await ws.send_text(json.dumps({"error": str(e)}))
        await ws.close()
