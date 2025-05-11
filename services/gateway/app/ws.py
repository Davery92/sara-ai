# services/gateway/app/ws.py

import json, logging
import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.common.nats_helpers import nats_connect, session_subjects
from .auth import _SECRET, _ALG

router = APIRouter()
log = logging.getLogger("ws")

@router.websocket("/v1/stream")
async def stream_endpoint(ws: WebSocket):
    await ws.accept()

    # 1) New session → two subjects for request & response
    session_id, req_subj, resp_subj = session_subjects()
    # 1b) And one subject for heartbeats (ACKs)
    ack_subj = f"ack.{session_id}"
    log.info(f"Using NATS Ack subject: {ack_subj}")

    # 2) Connect to NATS
    nc = await nats_connect()

    # 3) Subscribe for replies and forward them (plus send back +ACK)
    async def on_reply(msg):
        try:
            chunk = msg.data.decode()
            await ws.send_text(chunk)
            # Heartbeat back to the worker so it stays alive
            await nc.publish(ack_subj, b"+ACK")
        except Exception:
            log.exception("failed to send chunk to WS")

    await nc.subscribe(resp_subj, cb=on_reply)

    try:
        while True:
            text = await ws.receive_text()
            if not text.strip():
                continue

            # Parse the incoming JSON
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await ws.send_json({"error": "invalid JSON"})
                continue

            # 4) Extract JWT and build headers (Auth + Ack)
            jwt_raw = ws.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            headers: dict[str, bytes] = {}
            if jwt_raw:
                headers["Auth"] = jwt_raw.encode()
            headers["Ack"] = ack_subj.encode()

            # Optionally extract user_id from your JWT
            user_id = ""
            if jwt_raw:
                try:
                    data = jwt.decode(jwt_raw, _SECRET, algorithms=[_ALG])
                    user_id = data.get("sub", "")
                except Exception as e:
                    log.warning(f"Failed to decode JWT: {e}")

            # Attach it for persona/memory lookup
            payload["user_id"] = user_id

            # Publish the request with both reply & ack subjects
            await nc.publish(
                req_subj,
                json.dumps(payload).encode(),
                reply=resp_subj,
                headers=headers
            )

    except WebSocketDisconnect:
        log.info("WebSocket disconnected by client")
    except Exception as e:
        log.exception("WebSocket error: %s", e)
    finally:
        await nc.close()
