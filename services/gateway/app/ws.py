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
    
        await nc.subscribe(resp_subj, cb=_on_reply)
        
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
                
                # ── 5 · publish to JetStream ──────────────────────────
                try:
                    await nc.publish(
                        req_subj,
                        json.dumps(payload).encode(),
                        reply=resp_subj,          # ← add back
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
    except Exception as e:
        log.exception("💥 Stream error")
        await ws.send_text(json.dumps({"error": str(e)}))
    finally:
        try:
            await nc.close()
        except:
            pass