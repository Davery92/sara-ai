from fastapi import WebSocket, WebSocketDisconnect
from . import app              # FastAPI instance
from .ollama_client import stream_completion
from temporalio.client import Client as TemporalClient
from services.dialogue_worker.main import EchoWorkflow 
import os
from uuid import uuid4

TEMPORAL_URL = os.getenv("TEMPORAL_URL", "temporal:7233")

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

@app.websocket("/v1/dialogue")
async def dialogue_ws(ws: WebSocket):
    await ws.accept()
    temporal_url = os.getenv("TEMPORAL_URL", "127.0.0.1:7233")
    client = await TemporalClient.connect(temporal_url)
    try:
        while True:
            msg = await ws.receive_text()
            # start the workflow and await result
            result = await client.execute_workflow(
                EchoWorkflow.run,
                msg,
                id=f"echo-{uuid4()}",
                task_queue="echo-queue",
            )
            await ws.send_text(result)
    except WebSocketDisconnect:
        pass