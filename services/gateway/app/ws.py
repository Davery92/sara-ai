import json
import logging
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.common.nats_helpers import nats_connect, session_subjects
from .auth import _SECRET, _ALG  
import os 
from .redis_client import get_redis
from websockets.exceptions import ConnectionClosedOK


router = APIRouter()
log = logging.getLogger("gateway.ws")


@router.websocket("/v1/stream")
async def stream_endpoint(ws: WebSocket):
    await ws.accept()
    nc = None
    r = None
    sub = None
    
    # Track streaming state across callbacks
    is_streaming = False
    current_room_id = None
    buffered_response = None
    
    try:
        # Auth validation with error responses
        token = ws.query_params.get("token")
        if not token:
            await ws.send_text(json.dumps({"error": "Missing auth token"}))
            return
            
        try:
            jwt.decode(token, _SECRET, algorithms=[_ALG])
        except jwt.InvalidTokenError:
            await ws.send_text(json.dumps({"error": "Invalid authentication token"}))
            return
    
        # ── 1 · per-session NATS subjects ─────────────────────────────
        session_id, req_subj, resp_subj = session_subjects()
        ack_subj = f"ack.{session_id}"
        log.info("Using NATS ack subject: %s", ack_subj)
        
        # ── 2 · NATS connection ───────────────────────────────────────
        try:
            nc = await nats_connect()
        except Exception as e:
            log.error(f"Failed to connect to NATS: {str(e)}")
            await ws.send_text(json.dumps({"error": "Failed to connect to message bus"}))
            return
        
        # ── 3 · forward assistant chunks to the browser ───────────────
        r = await get_redis()
        MAX_HISTORY = int(os.getenv("REDIS_MAX_HISTORY", "50"))
        REDIS_TTL   = int(os.getenv("REDIS_CONV_TTL_SECONDS", "3600"))

        async def push_to_redis(role: str, text: str, room_id: str):
            key = f"room:{room_id}:messages"
            entry = json.dumps({"role": role, "content": text})
            await r.lpush(key, entry)
            await r.ltrim(key, 0, MAX_HISTORY - 1)
            await r.expire(key, REDIS_TTL)
            log.debug(f"Pushed to Redis: {role} message for room {room_id}")

        async def load_history(room_id: str):
            key = f"room:{room_id}:messages"
            # 1) grab the raw bytes/strings
            raw = await r.lrange(key, 0, MAX_HISTORY - 1)
            log.debug(f"[Redis raw for {key}]: {raw!r}")

            # 2) parse them into JSON
            history = [json.loads(item) for item in reversed(raw)]
            log.debug(f"[Parsed history for {key}]: {history!r}")

            return history
            
        # Track if we're currently receiving a streamed response
        is_streaming = False
        current_room_id = None
        buffered_response = None

        async def _on_reply(msg):
            nonlocal is_streaming, current_room_id, buffered_response
            
            try:
                # Extract room_id from headers if available
                headers = msg.headers or {}
                room_id = headers.get("Room-Id", "default-room")
                if isinstance(room_id, bytes):
                    room_id = room_id.decode()
                
                # Store the current room_id for this streaming session
                if not is_streaming:
                    current_room_id = room_id
                    is_streaming = True
                    buffered_response = None
                
                raw = msg.data.decode() if isinstance(msg.data, (bytes, bytearray)) else msg.data
                log.info("⇢ to browser [%s] %.120s", ws.client, raw)

                # extract finish_reason…
                finish_reason = None
                try:
                    payload = json.loads(raw)
                    choices = payload.get("choices", [])
                    if choices:
                        finish_reason = choices[0].get("finish_reason")
                        
                        # For streamed responses, we need to buffer the content
                        if buffered_response is None:
                            buffered_response = payload.copy()
                        else:
                            # Merge the deltas into our buffered response
                            for i, choice in enumerate(choices):
                                if "delta" in choice and "content" in choice["delta"]:
                                    if i < len(buffered_response["choices"]):
                                        if "content" not in buffered_response["choices"][i]:
                                            buffered_response["choices"][i]["content"] = ""
                                        buffered_response["choices"][i]["content"] += choice["delta"]["content"]
                except json.JSONDecodeError:
                    pass

                # send to client, guarding closed socket
                try:
                    await ws.send_text(raw)
                except ConnectionClosedOK:
                    log.info("Client socket closed, unsubscribing from NATS")
                    await sub.unsubscribe()
                    return

                # Always send acknowledgment
                await nc.publish(ack_subj, b"+ACK")
                
                # On final chunk, persist the full buffered response and reset streaming state
                if finish_reason == "stop":
                    log.info("Received final chunk (stop), saving complete response to Redis")
                    if buffered_response:
                        # Store the complete message in Redis
                        buffered_json = json.dumps(buffered_response)
                        await push_to_redis("assistant", buffered_json, current_room_id)
                        log.info(f"Stored complete response for room {current_room_id}")
                    
                    # Reset streaming state
                    is_streaming = False
                    current_room_id = None
                    buffered_response = None
                    
                    # Unsubscribe from NATS
                    log.info("Unsubscribing from NATS after final chunk")
                    await sub.unsubscribe()

            except Exception as e:
                log.exception(f"Failed to relay chunk to WS: {str(e)}")

            except Exception:
                log.exception("failed to relay chunk to WS")

        # attach the callback
        sub = await nc.subscribe(resp_subj, cb=_on_reply)
        
        try:
            while True:
                raw = await ws.receive_text()
                
                # ignore empty keep-alive frames some clients send
                if not raw.strip():
                    continue
                
                # must be JSON
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_json({"error": "invalid JSON"})
                    continue
                
                # ── 4 · build headers: Auth, Ack, Reply ───────────────
                # Extract token from Authorization header or query param
                auth_header = ws.headers.get("Authorization", "")
                jwt_raw = ""
                
                if auth_header:
                    # Remove 'Bearer ' prefix if present
                    jwt_raw = auth_header.replace("Bearer ", "").strip()
                else:
                    # Check query parameters for token
                    query_params = dict(ws.query_params)
                    jwt_raw = query_params.get("token", "")
                
                # 1) extract room_id from payload
                room_id = payload.get("room_id", "default-room")
                
                headers = {
                    "Ack": ack_subj,
                    "Reply": resp_subj,
                    "Room-Id": room_id,  # Add room_id to headers for _on_reply
                }
                
                # Only add Auth header if we have a token
                if jwt_raw:
                    headers["Auth"] = jwt_raw
                    log.info("Auth header set for request")
                else:
                    log.warning("No JWT token found in request")
                    await ws.send_json({"error": "Authentication required"})
                    continue
                
                # extract user_id for persona / memory look-ups
                user_id = ""
                if jwt_raw:
                    try:
                        data = jwt.decode(jwt_raw, _SECRET, algorithms=[_ALG])
                        user_id = data.get("sub", "")
                        log.info(f"Decoded user_id: {user_id}")
                    except Exception as e:
                        log.warning(f"JWT decode failed: {e}")
                        await ws.send_json({"error": f"Authentication error: {str(e)}"})
                        continue
                
                payload["user_id"] = user_id
                
                # 2) extract the user turn from the incoming array
                incoming = payload.get("messages", [])
                last = incoming[-1] if incoming else {}
                user_text = last.get("content", "") or last.get("text", "")
                
                # 3) push into Redis under the persistent room key
                await push_to_redis("user", user_text, room_id)
                
                # 4) reload history from Redis
                history = await load_history(room_id)
                log.debug(f"[Redis history for room {room_id}]: {history}")
                
                # 5) overwrite payload.messages with history from Redis
                payload["messages"] = history
                
                # 6) publish to JetStream
                try:
                    await nc.publish(
                        req_subj,
                        json.dumps(payload).encode(),
                        headers=headers,
                    )
                except Exception as e:
                    log.exception(f"Failed to publish message: {e}")
                    await ws.send_json({"error": f"Failed to process request: {str(e)}"})
                
        except WebSocketDisconnect:
            log.info("WS disconnected by client")
        except Exception as e:
            log.exception(f"WS handler error: {e}")
            await ws.send_json({"error": f"Server error: {str(e)}"})
    
    except WebSocketDisconnect:
        log.info("Client disconnected")
        if sub:
            await nc.unsubscribe(sub)
    except Exception as e:
        log.exception("💥 Stream error")
        await ws.send_text(json.dumps({"error": str(e)}))
    finally:
        try:
            if nc:
                await nc.close()
            if r:
                await r.close()
        except:
            pass