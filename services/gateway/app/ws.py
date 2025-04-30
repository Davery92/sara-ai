# services/gateway/app/ws.py

import json, logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.common.nats_helpers import nats_connect, session_subjects

router = APIRouter()
log = logging.getLogger("ws")

@router.websocket("/v1/stream")
async def stream_endpoint(ws: WebSocket):
    await ws.accept()

    # 1) New session → two subjects
    session_id, req_subj, resp_subj = session_subjects()

    # 2) NATS connect
    nc = await nats_connect()

    # 3) Subscribe for replies and forward them to the client
    async def on_reply(msg):
        try:
            # msg.data is bytes of a JSON text chunk
            await ws.send_text(msg.data.decode())
        except Exception:
            log.exception("failed to send chunk to WS")

    await nc.subscribe(resp_subj, cb=on_reply)

    try:
        while True:
            text = await ws.receive_text()
            if not text.strip():
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await ws.send_json({"error": "invalid JSON"})
                continue

            # 4) Publish the client’s chat request
            await nc.publish(
                 req_subj,
                 json.dumps(payload).encode(),
                 reply=resp_subj
             )


    except WebSocketDisconnect:
        log.info("WebSocket disconnected by client")
    except Exception as e:
        log.exception("WebSocket error: %s", e)
    finally:
        await nc.close()
