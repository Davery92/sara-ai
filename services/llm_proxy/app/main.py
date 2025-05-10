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
        stream = data.get("stream", True)
        
        # Convert OpenAI messages to a single prompt string if present
        prompt = data.get("prompt")
        if not prompt and "messages" in data:
            # Join all messages into a single prompt string
            prompt = ""
            for msg in data["messages"]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "system":
                    prompt += f"{content}\n"
                elif role == "user":
                    prompt += f"User: {content}\n"
                elif role == "assistant":
                    prompt += f"Assistant: {content}\n"
            prompt = prompt.strip()
        
        if not model or not prompt:
            log.error("Missing required fields model or prompt/messages")
            await ws.send_text(json.dumps({"error": "Missing required fields"}))
            return

        # Log what we're sending to Temporal
        log.info(f"Starting workflow with model: {model}")
        if isinstance(prompt, list):
            log.info(f"Using messages format with {len(prompt)} messages")
        else:
            log.info(f"Using single prompt string: {prompt[:50]}...")

        # Connect to Temporal and start the workflow
        client = await TemporalClient.connect("temporal:7233")
        
        # Safety: ensure prompt is a string
        if isinstance(prompt, list):
            prompt = '\n'.join(str(x) for x in prompt)
        log.info(f"Type of model: {type(model)}, prompt: {type(prompt)}, stream: {type(stream)}")
        log.info(f"Prompt value: {prompt!r}")

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