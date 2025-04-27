# app/main.py
import os
import logging
import json
import asyncio
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from temporalio.client import Client as TemporalClient
from uuid import uuid4

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Declare a place to stash the connected client
temporal_client: Optional[TemporalClient] = None

@app.on_event("startup")
async def connect_to_temporal():
    global temporal_client
    try:
        # connect to Temporal server
        temporal_client = await TemporalClient.connect("temporal:7233")
        logger.info("Successfully connected to Temporal")
    except Exception as e:
        logger.error(f"Failed to connect to Temporal: {e}")
        raise

@app.websocket("/v1/stream")
async def stream(ws: WebSocket):
    await ws.accept()
    
    try:
        payload = await ws.receive_json()
        logger.info(f"Received payload: {payload}")
        
        # Extract model and prompt from payload
        model = payload.get("model", "llama2")
        prompt = payload.get("prompt", "")
        stream_mode = payload.get("stream", False)
        
        # kick off LLMWorkflow on Temporal
        workflow_id = f"llm-{uuid4()}"
        logger.info(f"Starting workflow with ID: {workflow_id}")
        
        handle = await temporal_client.start_workflow(
            "LLMWorkflow",
            args=[model, prompt, stream_mode],
            id=workflow_id,
            task_queue="llm-queue",
        )
        
        logger.info(f"Workflow started, waiting for result...")
        
        # Wait for workflow to complete
        result = await handle.result()
        logger.info(f"Workflow completed with result: {result}")
        
        # Send the result back to the client
        try:
            # Send the complete Ollama response
            await ws.send_json(result)
            logger.info(f"Successfully sent response to client")
            
        except WebSocketDisconnect:
            logger.info("Client disconnected before response could be sent")
        except Exception as e:
            logger.error(f"Failed to send response: {e}", exc_info=True)
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"Error in websocket handler: {e}", exc_info=True)
        try:
            await ws.send_json({"error": str(e)})
        except Exception:
            logger.debug("Failed to send error - client may have disconnected")
    finally:
        try:
            # Attempt to close the WebSocket if it's still open
            await ws.close()
        except Exception:
            # Connection already closed, ignore
            pass

# Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy"}