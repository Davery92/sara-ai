from fastapi import WebSocket, WebSocketDisconnect
from . import app              # FastAPI instance
from .ollama_client import stream_completion

@app.websocket("/v1/stream")
async def stream(ws: WebSocket):
    """Bidirectional WS proxy → streams chunks from the local LLM."""
    await ws.accept()

    try:
        # first client message = generation params (model, prompt, etc.)
        payload = await ws.receive_json()

        async for chunk in stream_completion(payload):
            await ws.send_json(chunk)

    except WebSocketDisconnect:
        # client quit early — just swallow
        pass
    finally:
        await ws.close()