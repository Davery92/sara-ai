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
    ollama_session = None
    ollama_response = None
    try:
        payload = await ws.receive_json()
        payload.setdefault("stream", True)
        model = payload.get("model")
        if not model or "messages" not in payload:
            log.error("Missing model or messages in payload")
            await ws.send_text(json.dumps({"error": "Missing required fields: model + messages"}))
            await ws.close()
            return

        raw_ollama_url_env = os.getenv("OLLAMA_URL")
        ollama_url = raw_ollama_url_env
        if not ollama_url:
            ollama_url = "http://100.104.68.115:11434"
            log.warning(f"OLLAMA_URL was not set, defaulting to: {ollama_url}")
        
        log.info(f"🧠 Forwarding to Ollama (model={model}) at {ollama_url}...")
        log.debug(f"Payload → {json.dumps(payload)}")
        log.info(f"LLM Proxy sending messages array: {json.dumps(payload.get('messages'), indent=2, default=str)}")

        ollama_session = aiohttp.ClientSession()
        ollama_response = await ollama_session.post(
            f"{ollama_url}/v1/chat/completions", 
            json=payload, 
            timeout=aiohttp.ClientTimeout(total=180, connect=10)
        )
        
        log.info(f"✅ Ollama responded with status: {ollama_response.status}")
        if ollama_response.status != 200:
            err_text = await ollama_response.text()
            log.error(f"❌ Ollama error {ollama_response.status}: {err_text[:500]}")
            await ws.send_text(json.dumps({"error": f"Ollama API Error: {err_text[:200]}"}))
            return

        chunk_count = 0
        outer_loop_break = False
        async for raw_chunk_bytes in ollama_response.content.iter_any():
            if not raw_chunk_bytes:
                continue

            if ws.client_state == WebSocketDisconnect:
                log.info("Client WebSocket disconnected during Ollama stream.")
                break 
            
            try:
                full_chunk_str = raw_chunk_bytes.decode('utf-8').strip()
                if full_chunk_str.startswith("data: "):
                    sse_payload_str = full_chunk_str.removeprefix("data: ").strip()
                    if sse_payload_str == "[DONE]":
                        stop_event = {"choices":[{"delta":{},"finish_reason":"stop", "index": 0}],"model": model, "id": ""}
                        await ws.send_text(json.dumps(stop_event))
                        log.info(f"✅ Emitted stop event due to '[DONE]' after {chunk_count} chunks.")
                        outer_loop_break = True
                        break
                    
                    data = json.loads(sse_payload_str)
                    await ws.send_text(sse_payload_str)
                    chunk_count += 1
                    if data.get("choices", [{}])[0].get("finish_reason") == "stop" or data.get("done") == True:
                        log.info(f"✅ Detected finish_reason or done in single SSE chunk {chunk_count}.")
                        outer_loop_break = True
                        break
                elif full_chunk_str:
                    data = json.loads(full_chunk_str)
                    await ws.send_text(full_chunk_str)
                    chunk_count += 1
                    if data.get("choices", [{}])[0].get("finish_reason") == "stop" or data.get("done") == True:
                        log.info(f"✅ Detected finish_reason or done in single JSON chunk {chunk_count}.")
                        outer_loop_break = True
                        break
            except json.JSONDecodeError:
                try:
                    chunk_lines = raw_chunk_bytes.decode('utf-8').splitlines()
                    for line_str in chunk_lines:
                        line_str = line_str.strip()
                        if not line_str.startswith("data: "):
                            continue
                        
                        sse_payload_str = line_str.removeprefix("data: ").strip()
                        if sse_payload_str == "[DONE]":
                            stop_event = {"choices":[{"delta":{},"finish_reason":"stop", "index": 0}],"model": model, "id": ""}
                            await ws.send_text(json.dumps(stop_event))
                            log.info(f"✅ Emitted stop event due to '[DONE]' from multi-line chunk after {chunk_count} total chunks.")
                            outer_loop_break = True
                            break 

                        data = json.loads(sse_payload_str)
                        await ws.send_text(sse_payload_str)
                        chunk_count += 1
                        if data.get("choices", [{}])[0].get("finish_reason") == "stop" or data.get("done") == True:
                            log.info(f"✅ Detected finish_reason or done in multi-line SSE chunk {chunk_count}.")
                            outer_loop_break = True
                            break
                    if outer_loop_break:
                        break
                except json.JSONDecodeError:
                    log.warning(f"Skipping invalid JSON in multi-line chunk processing: {raw_chunk_bytes.decode('utf-8', errors='ignore')[:100]}")
                    continue
                except Exception as e_inner:
                    log.error(f"Error sending multi-line chunk to client WebSocket: {e_inner}")
                    outer_loop_break = True
                    break
            except WebSocketDisconnect:
                log.info("Client WebSocket disconnected while processing/sending Ollama chunks.")
                outer_loop_break = True
                break
            except Exception as e:
                log.error(f"Error processing/sending chunk to client WebSocket: {e}")
                outer_loop_break = True
                break
        
        if outer_loop_break:
            log.info(f"Outer loop break called after {chunk_count} chunks.")

        log.info(f"Finished streaming {chunk_count} chunks from Ollama.")

    except WebSocketDisconnect:
        log.info("Client disconnected before or during initial payload processing.")
    except aiohttp.ClientError as e:
        log.error(f"aiohttp.ClientError communicating with Ollama: {e}")
        if ws.client_state != WebSocketDisconnect:
            try:
                await ws.send_text(json.dumps({"error": f"Ollama connection error: {str(e)}"}))
            except: pass
    except asyncio.TimeoutError:
        log.error("Asyncio TimeoutError, likely during Ollama request.")
        if ws.client_state != WebSocketDisconnect:
            try:
                await ws.send_text(json.dumps({"error": "Request to Ollama timed out."}))
            except: pass
    except Exception as e:
        log.exception("💥 LLM Proxy Stream error")
        if ws.client_state != WebSocketDisconnect:
            try:
                await ws.send_text(json.dumps({"error": f"LLM Proxy internal error: {str(e)}"}))
            except: pass
    finally:
        log.info("Cleaning up LLM Proxy WebSocket resources.")
        if ollama_response and hasattr(ollama_response, 'closed') and not ollama_response.closed:
            ollama_response.close()
            log.info("Closed Ollama response stream.")
        if ollama_session and hasattr(ollama_session, 'closed') and not ollama_session.closed:
            await ollama_session.close()
        
        if hasattr(ws, 'client_state') and ws.client_state != WebSocketDisconnect:
            try:
                await ws.close()
                log.info("LLM Proxy WebSocket connection closed in finally.")
            except Exception as e_ws_close:
                log.error(f"Error closing LLM Proxy WebSocket in finally: {e_ws_close}")
