import json
import logging
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.common.nats_helpers import nats_connect, session_subjects
from .auth import _SECRET, _ALG  # Fix import syntax

router = APIRouter()
log = logging.getLogger("gateway.ws")

@router.websocket("/v1/stream")
async def stream_endpoint(ws: WebSocket):
    await ws.accept()
    
    # ── 1 · per-session NATS subjects ─────────────────────────────
    session_id, req_subj, resp_subj = session_subjects()
    ack_subj = f"ack.{session_id}"
    log.info("Using NATS ack subject: %s", ack_subj)
    
    # ── 2 · NATS connection ───────────────────────────────────────
    nc = await nats_connect()
    
    # ── 3 · forward assistant chunks to the browser ───────────────
    # services/gateway/app/ws.py  (only the _on_reply callback)

    async def _on_reply(msg):
        try:
            # msg.data can be str OR bytes depending on sender
            data = msg.data.decode() if isinstance(msg.data, (bytes, bytearray)) else msg.data
            await ws.send_text(data)

            # heartbeat so the worker stays alive
            await nc.publish(ack_subj, b"+ACK")
        except Exception:
            log.exception("failed to relay chunk to WS")

    
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
            
            headers = {
                "Ack": ack_subj,
                "Reply": resp_subj,
            }
            
            # Only add Auth header if we have a token
            if jwt_raw:
                headers["Auth"] = jwt_raw
                log.info("Auth header set for request")
            else:
                log.warning("No JWT token found in request")
            
            # extract user_id for persona / memory look-ups
            user_id = ""
            if jwt_raw:
                try:
                    data = jwt.decode(jwt_raw, _SECRET, algorithms=[_ALG])
                    user_id = data.get("sub", "")
                    log.info(f"Decoded user_id: {user_id}")
                except Exception as e:
                    log.warning(f"JWT decode failed: {e}")
            
            payload["user_id"] = user_id
            
            # ── 5 · publish to JetStream ──────────────────────────
            await nc.publish(
                req_subj,
                json.dumps(payload).encode(),
                headers=headers  # Ack + Auth
            )
            
    except WebSocketDisconnect:
        log.info("WS disconnected by client")
    except Exception as e:
        log.exception(f"WS handler error: {e}")
    finally:
        await nc.close()