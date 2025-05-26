import json
import logging
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, status
from services.common.nats_helpers import nats_connect, session_subjects
from .auth import _SECRET, _ALG
import os
from .redis_client import get_redis
from .redis_utils import push_unified_user_memory
from websockets.exceptions import ConnectionClosedOK
import httpx
from datetime import datetime
from starlette.websockets import WebSocketState
from sqlalchemy.ext.asyncio import AsyncSession
from .db.session import get_session
from .db import crud
from uuid import UUID
# from asyncio import anext # Removed this line as anext is a built-in function

router = APIRouter()
log = logging.getLogger("gateway.ws")

# Get Ollama base URL from environment
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")


@router.get("/v1/models/available")
@router.get("/api/models/available")
async def list_models():
    """Fetch available models from Ollama"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{LLM_BASE_URL}/api/tags") # Corrected typo in previous step
            if response.status_code != 200:
                ollama_error = await response.text()
                log.error(f"Ollama /api/tags error {response.status_code}: {ollama_error[:200]}")
                raise HTTPException(status_code=503, detail=f"Failed to fetch models from Ollama: {response.reason_phrase}")

            models_data = response.json()
            models = []

            for model_info in models_data.get("models", []):
                models.append({
                    "id": model_info["name"],
                    "name": model_info["name"].replace("-", " ").title(),
                    "description": f"Ollama {model_info['name']} model"
                })

            return models
    except httpx.RequestError as e:
        log.error(f"HTTPX RequestError fetching models: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Service unavailable: Could not connect to LLM service at {LLM_BASE_URL}")
    except Exception as e:
        log.error(f"Unexpected error fetching models: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.websocket("/v1/stream")
@router.websocket("/api/stream")
async def stream_endpoint(ws: WebSocket):
    await ws.accept()
    nc = None
    r = None
    sub = None
    jwt_raw = None
    
    # Initialize db_session here for use throughout the WebSocket lifetime
    db_session_gen = get_session()
    db: AsyncSession = await anext(db_session_gen) # `anext` is a built-in, no explicit import needed
    
    # Track streaming state across callbacks
    is_streaming = False
    current_room_id_for_stream = None
    buffered_response = None
    
    try:
        token_from_query = ws.query_params.get("token")
        auth_header = ws.headers.get("authorization", "")
        
        if token_from_query:
            jwt_raw = token_from_query
        elif auth_header.lower().startswith("bearer "):
            jwt_raw = auth_header.split(" ", 1)[1]
        
        if not jwt_raw:
            log.warning("Missing auth token for WebSocket connection.")
            await ws.send_text(json.dumps({"error": "Missing auth token"}))
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        try:
            # Decode JWT to get user_id for DB operations and Redis key
            decoded_jwt_payload = jwt.decode(jwt_raw, _SECRET, algorithms=[_ALG])
            user_id_from_jwt = UUID(decoded_jwt_payload.get("sub")) # Convert to UUID
            log.info(f"Token validated for WebSocket connection. User: {user_id_from_jwt}")
        except jwt.PyJWTError as e:
            log.error(f"Invalid JWT for WebSocket: {e}")
            await ws.send_text(json.dumps({"error": "Invalid authentication token"}))
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        except ValueError: # If sub is not a valid UUID string
            log.error(f"JWT 'sub' claim is not a valid UUID: {decoded_jwt_payload.get('sub')}")
            await ws.send_text(json.dumps({"error": "Invalid authentication token format"}))
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    
        # ── 1 · per-session NATS subjects ─────────────────────────────
        session_id, req_subj, resp_subj = session_subjects()
        ack_subj = f"ack.{session_id}"
        log.info("Using NATS ack subject: %s, reply subject: %s", ack_subj, resp_subj)
        
        # ── 2 · NATS connection ───────────────────────────────────────
        try:
            nc = await nats_connect()
        except Exception as e:
            log.error(f"Failed to connect to NATS: {str(e)}")
            await ws.send_text(json.dumps({"error": "Failed to connect to message bus"}))
            await ws.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        
        # ── 3 · Redis history & unified memory functions ──────────────
        r = await get_redis()
        MAX_HISTORY = int(os.getenv("HOT_MSG_LIMIT", "200")) # Use HOT_MSG_LIMIT for history cap
        REDIS_TTL   = int(os.getenv("REDIS_CONV_TTL_MIN", "60")) * 60 # seconds

        # This function now correctly loads unified history and transforms messages for LLM
        async def load_history(user_id_for_redis: UUID):
            key = f"user:{str(user_id_for_redis)}:messages" # Ensure user_id is string for key
            if r:
                raw_history_items = [] # Default to empty list
                try:
                    raw_history_items = await r.lrange(key, 0, MAX_HISTORY - 1)
                except Exception as e:
                    log.error(f"Error fetching history from Redis for key {key}: {e}")
                    return [] # Return empty on error

                history = []
                # raw_history_items are byte strings from Redis
                for item_bytes in reversed(raw_history_items): 
                    try:
                        item = json.loads(item_bytes)
                        
                        # Convert 'text' field to 'content' for LLM compatibility
                        if 'text' in item and 'role' in item:
                            llm_message = {"role": item['role'], "content": item['text']}
                            history.append(llm_message)
                        # If already in desired format (e.g. if something else wrote it or future-proofing)
                        elif 'content' in item and 'role' in item:
                            log.debug(f"History item for user {user_id_for_redis} already in 'role'/'content' format: {item_str[:100]}...")
                            history.append({"role": item['role'], "content": item['content']})
                        else:
                            log.warning(f"Skipping malformed history item for user {user_id_for_redis} (missing role/text/content): {item_str[:200]}")
                    except json.JSONDecodeError:
                        log.warning(f"Failed to decode JSON from Redis for user {user_id_for_redis}: {item_bytes!r}")
                    except UnicodeDecodeError:
                        log.warning(f"Failed to decode UTF-8 from Redis for user {user_id_for_redis}: {item_bytes!r}")
                
                log.debug(f"[Unified history RAW from Redis for user {user_id_for_redis} count: {len(raw_history_items)}]: {str(raw_history_items)[:300]}...")
                log.debug(f"[Unified history PARSED for LLM for user {user_id_for_redis} count: {len(history)}]: {str(history)[:300]}...")
                return history
            else:
                log.warning(f"Redis client not available in load_history for user {user_id_for_redis}")
                return []
            
        # Track if we're currently receiving a streamed response
        is_streaming = False
        current_room_id_for_stream = None
        buffered_response = None

        async def _on_reply(msg):
            nonlocal is_streaming, current_room_id_for_stream, buffered_response, sub, db # Add db to nonlocal
            
            # Check if the subscription is already closed. If so, ignore this message.
            if sub and hasattr(sub, '_closed') and sub._closed:
                log.debug(f"[BACKEND_WS] Received message on closed subscription {msg.subject}. Ignoring.")
                return

            # 1. Decode raw message and extract room_id from headers (always available)
            # raw_nats_message is bytes from NATS, so decode it
            raw_nats_message = msg.data.decode('utf-8') if isinstance(msg.data, (bytes, bytearray)) else str(msg.data)
            headers = msg.headers or {}
            room_id_from_header = headers.get("Room-Id", "default-room")
            if isinstance(room_id_from_header, bytes):
                room_id_from_header = room_id_from_header.decode('utf-8') # Ensure header is decoded

            room_id_uuid_from_header = UUID(room_id_from_header) # Convert to UUID
            
            payload_json = None
            delta_content = None # Initialize content and finish_reason to None
            finish_reason = None
            is_done = False # Initialize is_done flag
            
            # 2. Attempt to parse JSON and extract structured data
            try:
                payload_json = json.loads(raw_nats_message)
                choices = payload_json.get("choices", [])
                if choices and isinstance(choices, list) and len(choices) > 0:
                     choice = choices[0]
                     delta = choice.get("delta", {})
                     if isinstance(delta, dict):
                        delta_content = delta.get("content", None)
                     finish_reason = choice.get("finish_reason", None)
                is_done = payload_json.get("done", False) # Check for top-level done flag

            except json.JSONDecodeError:
                log.debug("[BACKEND_WS] Received non-JSON chunk. Could be [DONE] or artifact.")
                pass # Continue processing based on raw_nats_message
                
            # 3. State Management and Processing Logic

            # Condition for a new stream starting:
            # We are not currently streaming, AND (it's a JSON message with content OR it's a non-JSON message that's not empty/DONE)
            is_potential_stream_start_message = (
                (payload_json and delta_content is not None) or
                (not payload_json and raw_nats_message.strip() and raw_nats_message.strip() != "[DONE]")
            )

            if not is_streaming and is_potential_stream_start_message:
                 current_room_id_for_stream = room_id_uuid_from_header
                 is_streaming = True
                 buffered_response = {"choices": [{"delta": {"content": ""}}]} # Initialize buffer
                 log.info(f"[BACKEND_WS] Streaming started for room_id: {current_room_id_for_stream}")

            # Only process and forward the message if it belongs to the currently active stream
            if is_streaming and current_room_id_for_stream == room_id_uuid_from_header:
                # --- Buffering ---
                # This logic ensures `buffered_response` correctly aggregates content.
                if payload_json and payload_json.get("choices") and payload_json["choices"][0].get("delta"):
                    # For structured JSON chunks (like from Ollama)
                    content_to_add = payload_json["choices"][0]["delta"].get("content", "")
                    if content_to_add is not None:
                        # Append content to the buffered response
                        if "choices" in buffered_response and buffered_response["choices"] and "delta" in buffered_response["choices"][0]:
                            if "content" not in buffered_response["choices"][0]["delta"]:
                                buffered_response["choices"][0]["delta"]["content"] = ""
                            buffered_response["choices"][0]["delta"]["content"] += content_to_add
                        else: # Re-initialize if structure lost
                            buffered_response = {"choices": [{"delta": {"content": content_to_add}}]}
                elif not payload_json and raw_nats_message.strip() and raw_nats_message.strip() != "[DONE]":
                    # For non-JSON chunks (like raw text from a custom stream or artifact content)
                    raw_content = raw_nats_message
                    if buffered_response is None:
                        # Initialize with raw content if the first chunk in stream is non-JSON
                        buffered_response = {"choices": [{"delta": {"content": raw_content}}]}
                    else:
                        # Append raw content to existing buffer
                        if "choices" in buffered_response and buffered_response["choices"] and "delta" in buffered_response["choices"][0]:
                            if "content" not in buffered_response["choices"][0]["delta"]:
                                buffered_response["choices"][0]["delta"]["content"] = ""
                            buffered_response["choices"][0]["delta"]["content"] += raw_content
                        else:
                            # Re-initialize if structure lost
                            buffered_response = {"choices": [{"delta": {"content": raw_content}}]}


                # --- Sending to WebSocket ---
                # Always send the raw message received from NATS to the WebSocket if it's part of the active stream.
                log.debug(f"[BACKEND_WS] Sending to WebSocket (room: {current_room_id_for_stream}): {raw_nats_message[:200]}...")
                try:
                    await ws.send_text(raw_nats_message)
                except ConnectionClosedOK:
                    log.info("[BACKEND_WS] Client socket closed during _on_reply send, unsubscribing.")
                    if sub and hasattr(sub, '_closed') and not sub._closed:
                         try: await sub.unsubscribe()
                         except Exception as unsub_error: log.error(f"[BACKEND_WS] Error during unsubscribe on WS close: {unsub_error}")
                    sub = None
                    is_streaming = False # Also reset streaming state
                    current_room_id_for_stream = None
                    buffered_response = None
                    return # Stop processing this stream
                except Exception as send_exc:
                    log.error(f"[BACKEND_WS] Error sending to WebSocket client: {send_exc}. Unsubscribing.")
                    if sub and hasattr(sub, '_closed') and not sub._closed:
                        try: await sub.unsubscribe()
                        except Exception as unsub_error: log.error(f"[BACKEND_WS] Error during unsubscribe on send error: {unsub_error}")
                    sub = None
                    is_streaming = False # Also reset streaming state
                    current_room_id_for_stream = None
                    buffered_response = None
                    try: await ws.send_json({"error": f"Gateway send error: {str(send_exc)[:100]}..."})
                    except: pass
                    return

                # --- Stream Completion Check ---
                is_stream_end_signal = (finish_reason == "stop" or is_done or raw_nats_message.strip() == "[DONE]")

                if is_stream_end_signal:
                    log.info(f"[BACKEND_WS] Stream finished signal received (finish_reason: {finish_reason}, done: {is_done}, raw: {'[DONE]' if raw_nats_message.strip() == '[DONE]' else 'other'}) for room {current_room_id_for_stream}.")
                    
                    # Process and store the final buffered response
                    if buffered_response and current_room_id_for_stream and user_id_from_jwt:
                        full_assistant_content = buffered_response.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        
                        if full_assistant_content:
                            try:
                                log.info(f"[BACKEND_WS] Attempting to save full assistant response for room {current_room_id_for_stream}, user {user_id_from_jwt}. Length: {len(full_assistant_content)}")
                                
                                # Prepare data for save_chat_message
                                assistant_parts = json.dumps([{"type": "text", "text": full_assistant_content}])
                                assistant_attachments_dict = {"model": buffered_response.get("model", "unknown_model")}
                                # Add sources to attachments if it becomes available
                                # assistant_attachments_dict["sources"] = ... 
                                assistant_attachments = json.dumps(assistant_attachments_dict)

                                # Save to PostgreSQL using save_chat_message
                                await crud.save_chat_message(
                                    db=db,
                                    chat_id=current_room_id_for_stream, # This is a UUID
                                    role="assistant",
                                    parts=assistant_parts,
                                    attachments=assistant_attachments,
                                    created_at=datetime.utcnow() # Add created_at timestamp
                                )
                                await db.commit() # Commit after successful save
                                log.info(f"[BACKEND_WS] Saved assistant message to DB for room {current_room_id_for_stream}, user {user_id_from_jwt}")

                                # Now, push to unified user memory in Redis
                                await push_unified_user_memory(
                                    user_id=str(user_id_from_jwt), # Ensure string UUID
                                    room_id=str(current_room_id_for_stream), # Ensure string UUID
                                    role="assistant",
                                    text=full_assistant_content
                                )
                                log.info(f"[BACKEND_WS] Stored complete assistant response to UNIFIED Redis for user {user_id_from_jwt}.")

                            except Exception as db_save_error:
                                log.error(f"[BACKEND_WS] Error saving assistant message to DB/Redis: {db_save_error}", exc_info=True)
                                await db.rollback() # Rollback on error
                        else:
                            log.warning("[BACKEND_WS] Assistant response content was empty, not saving to DB or unified Redis.")

                    # Clean up stream-specific state and unsubscribe
                    is_streaming = False
                    current_room_id_for_stream = None
                    buffered_response = None # Clear buffer
                    
                    return

            # If not streaming and the message wasn't a stream start signal, or for a different room
            elif not is_streaming and not is_potential_stream_start_message:
                 log.debug(f"[BACKEND_WS] Received message when not streaming and not a start signal. Ignoring: {raw_nats_message[:100]}...")
                 return # Ignore messages not part of an active stream for this room or not a valid start
            elif is_streaming and current_room_id_for_stream != room_id_uuid_from_header:
                 log.warning(f"[BACKEND_WS] Received message for different room ({room_id_uuid_from_header}) while streaming for {current_room_id_for_stream}. Ignoring.")
                 return

        sub = await nc.subscribe(resp_subj, cb=_on_reply)
        log.info(f"Subscribed to NATS reply subject: {resp_subj}")
        
        try:
            while True:
                raw_client_message = await ws.receive_text()
                
                if not raw_client_message.strip():
                    log.debug("Received empty keep-alive frame from client, ignoring.")
                    continue
                
                try:
                    client_payload = json.loads(raw_client_message)
                except json.JSONDecodeError:
                    log.error(f"Received invalid JSON from client: {raw_client_message[:100]}")
                    await ws.send_json({"error": "invalid JSON"})
                    continue
                
                # Extract and validate room_id and user_id from client_payload and JWT
                room_id_str = client_payload.get("room_id")
                if not room_id_str:
                    log.error("Missing room_id in client payload.")
                    await ws.send_json({"error": "Missing room_id in request"})
                    continue
                
                try:
                    room_id_uuid = UUID(room_id_str) # Convert room_id to UUID
                except ValueError:
                    log.error(f"Invalid room_id format from client: {room_id_str}")
                    await ws.send_json({"error": "Invalid room_id format"})
                    continue

                current_user_message_text = client_payload.get("msg", "").strip()
                log.info(f"Current user message: '{current_user_message_text}' for room_id: {room_id_uuid}, user_id: {user_id_from_jwt}")

                if current_user_message_text:
                    # Save user message to PostgreSQL
                    log.info(f"[BACKEND_WS] User message received for room {room_id_uuid}, user {user_id_from_jwt}. Length: {len(current_user_message_text)}")
                    
                    # Prepare data for save_chat_message
                    user_parts = json.dumps([{"type": "text", "text": current_user_message_text}])
                    user_attachments = json.dumps({}) # No specific attachments for user message here

                    await crud.save_chat_message(
                        db=db,
                        chat_id=room_id_uuid,
                        role="user",
                        parts=user_parts,
                        attachments=user_attachments,
                        created_at=datetime.utcnow() # Add created_at timestamp
                    )
                    await db.commit() # Commit after successful save
                    log.info(f"[BACKEND_WS] Saved user message to DB for room {room_id_uuid}, user {user_id_from_jwt}")
                    
                    # Now, push to unified user memory in Redis
                    await push_unified_user_memory(
                        user_id=str(user_id_from_jwt),
                        room_id=str(room_id_uuid),
                        role="user",
                        text=current_user_message_text
                    )
                    log.info(f"Stored user message to UNIFIED Redis for room {room_id_uuid}, user {user_id_from_jwt}.") # Adjusted log

                    # Relay message to NATS for LLM processing
                    history_for_llm = await load_history(user_id_for_redis=user_id_from_jwt) 
                    log.debug(f"Full history for user '{user_id_from_jwt}': {history_for_llm}")
                    nats_payload = {
                        "room_id": str(room_id_uuid), # Ensure it's a string for NATS payload
                        "user_id": str(user_id_from_jwt), # Ensure it's a string for NATS payload
                        "msg": current_user_message_text,
                        "messages": history_for_llm,      # Correctly formatted for LLM
                        "model": client_payload.get("model"),
                        "use_document_tools": client_payload.get("use_document_tools", True),
                        "session_auth_token": jwt_raw,
                    }
                    
                    log.debug(f"DEBUG: nats_payload['messages'] sent to NATS for user {user_id_from_jwt}, room {room_id_uuid}: {json.dumps(nats_payload['messages'], indent=2, default=str)}") # Add this line

                    headers = { "Ack": ack_subj, "Reply": resp_subj, "Room-Id": str(room_id_uuid), "Auth": jwt_raw } # Ensure Auth header is present
                    
                    log.info(f"Publishing to NATS: {req_subj}. Payload: {json.dumps(nats_payload, default=str)[:200]}...")
                    try:
                        await nc.publish(
                            req_subj,
                            json.dumps(nats_payload).encode(),
                            headers=headers,
                        )
                        log.debug(f"Published to NATS: {req_subj}")
                    except Exception as e:
                        log.exception(f"Failed to publish to NATS: {e}")
                        await ws.send_json({"error": f"Failed to process request: {str(e)}"})
                
        except WebSocketDisconnect:
            log.info(f"WS disconnected by client (user: {user_id_from_jwt})")
        except Exception as e:
            log.exception(f"WS handler error: {e}")
            try:
                await ws.send_json({"error": f"Server error: {str(e)}"})
            except: pass
    
    except Exception as e: 
        log.exception("💥 Stream endpoint initial setup error")
        try:
            if ws.client_state != WebSocketState.DISCONNECTED:
                await ws.send_text(json.dumps({"error": f"Initialization error: {str(e)}"}))
        except: pass
    finally:
        log.info("Cleaning up WebSocket stream endpoint resources.")
        if sub and hasattr(sub, '_closed') and not sub._closed:
            try:
                await sub.unsubscribe()
                log.info(f"Unsubscribed from NATS subject: {resp_subj if 'resp_subj' in locals() else 'unknown'}")
            except Exception as e:
                log.error(f"Error unsubscribing from NATS: {e}")
        if nc:
            try:
                if not nc.is_closed:
                    await nc.close()
                    log.info("NATS connection closed.")
                else:
                    log.info("NATS connection was already closed or never fully opened.")
            except Exception as e:
                log.error(f"Error closing NATS connection: {e}")
        if r:
            try:
                await r.close()
                log.info("Redis connection closed.")
            except Exception as e:
                log.error(f"Error closing Redis connection: {e}")
        try:
            # Ensure the database session is closed
            await db_session_gen.aclose() # Correctly close the async generator session
            log.info("Database session closed.")
        except Exception as e:
            log.error(f"Error closing database session: {e}")
        # FIXED: Removed the inner try-except block, relying on the outer one.
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
            log.info("LLM Proxy WebSocket connection closed in finally.")