from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from temporalio.client import Client as TemporalClient
from uuid import uuid4
import logging
import json
from .workflows import ChatWorkflow

app = FastAPI(title="LLM Streaming Proxy")
log = logging.getLogger("llm_proxy")

@app.websocket("/v1/stream")
async def stream_ws(ws: WebSocket):
    await ws.accept()
    try:
        data = await ws.receive_json()
        model = data.get("model")
        prompt = data.get("prompt")
        stream = data.get("stream", True)

        # Connect to Temporal and start the workflow
        client = await TemporalClient.connect("temporal:7233")
        
        # Fixed: Pass arguments correctly
        run_handle = await client.start_workflow(
            ChatWorkflow.run,
            id=f"chat-{uuid4()}",
            task_queue="llm-queue",
            args=[model, prompt, stream],  # ← pack them here
        )

        
        # Await workflow result and stream back
        chunks = await run_handle.result()
        for chunk in chunks:
            await ws.send_text(chunk)
    
    except WebSocketDisconnect:
        log.info("Client disconnected")
    except Exception as e:
        log.exception("Error in llm_proxy stream: %s", e)
        await ws.close()