import asyncio
import json
import logging
import os
import time
import traceback
import aiohttp
import uuid

from nats.aio.client import Client as NATS
from prometheus_client import Counter, Histogram, start_http_server
from jetstream import verify, consume
from jwt.exceptions import InvalidTokenError
import websockets

# ── Config ───────────────────────────────────────────────────────────────
NATS_URL      = os.getenv("NATS_URL",  "nats://nats:4222")
LLM_WS_URL    = os.getenv("LLM_WS_URL","ws://llm_proxy:8000/v1/stream")
GATEWAY_URL   = os.getenv("GATEWAY_URL","http://gateway:8000")
LLM_MODEL     = os.getenv("LLM_MODEL", "qwen3:32b")
METRICS_PORT  = int(os.getenv("METRICS_PORT", 8000))
MEMORY_TOP_N  = int(os.getenv("MEMORY_TOP_N", 3))
DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "sara_default")

SYS_CORE        = os.getenv("SYSTEM_PROMPT","You are a helpful AI assistant.")
MEMORY_TEMPLATE = os.getenv("MEMORY_TEMPLATE","Previous conversation summaries:\n{memories}")

ACK_TIMEOUT = 15
ACK_EVERY   = 10

# ── Prometheus metrics ───────────────────────────────────────────────────
CHUNKS_RELAYED = Counter("dw_chunk_out_total", "Chunks relayed to NATS", ["model"])
CANCELLED      = Counter("dw_stream_cancel_total","Streams cancelled — idle")
WS_LATENCY     = Histogram("dw_ws_send_seconds","Latency per chunk", buckets=(0.001,0.005,0.01,0.05,0.1,0.5,1,2))
MEMORY_SUCCESS = Counter("dw_memory_success_total","Successful memory retrievals")
MEMORY_FAILURE = Counter("dw_memory_failure_total","Failed memory retrievals")
PERSONA_SUCCESS= Counter("dw_persona_success_total","Successful persona retrievals")
PERSONA_FAILURE= Counter("dw_persona_failure_total","Failed persona retrievals")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dialogue_worker")

def build_llm_payload(user_payload: dict) -> dict:
    log.info(f"[DW build_llm_payload] INPUT user_payload 'msg': '{user_payload.get('msg')}'")
    log.info(f"[DW build_llm_payload] INPUT user_payload 'messages' (count: {len(user_payload.get('messages', []))}): {json.dumps(user_payload.get('messages', []), indent=2)}")
    log.info(f"[DW build_llm_payload] INPUT user_payload 'attachments': {json.dumps(user_payload.get('attachments'), indent=2)}")
    
    result = {
        "model": user_payload.get("model") or LLM_MODEL,
        "messages": user_payload.get("messages", [{"role": "user", "content": user_payload.get("msg", "")}]),
        "stream": True,
    }
    
    log.info(f"[DW build_llm_payload] OUTPUT result 'messages' (count: {len(result.get('messages', []))}): {json.dumps(result.get('messages', []), indent=2)}")
    
    return result

async def get_memories(user_msg: str, room_id: str, auth_token: str = None) -> list[str]:
    try:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GATEWAY_URL}/v1/memory/query",
                json={"query": user_msg, "room_id": room_id, "top_n": MEMORY_TOP_N},
                timeout=5.0,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    MEMORY_FAILURE.inc()
                    return []
                memories = await resp.json()
                MEMORY_SUCCESS.inc()
                return [memory["text"] for memory in memories]
    except Exception:
        MEMORY_FAILURE.inc()
        return []

async def get_persona_config(user_id: str = None, auth_token: str = None) -> str:
    try:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        params = {"user_id": user_id} if user_id else {}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{GATEWAY_URL}/v1/persona/config", params=params, timeout=5.0, headers=headers) as resp:
                if resp.status != 200:
                    PERSONA_FAILURE.inc()
                    return SYS_CORE
                data = await resp.json()
                PERSONA_SUCCESS.inc()
                return data.get("content", SYS_CORE)
    except Exception:
        PERSONA_FAILURE.inc()
        return SYS_CORE

async def enhance_prompt(payload: dict, auth_token: str = None) -> dict:
    user_msg_text_for_memory = payload.get("msg", "") 
    room_id = payload.get("room_id", "")
    user_id = payload.get("user_id", "")
    latest_user_attachments = payload.get("attachments") # Extract attachments

    log.info(f"[DW_ENHANCE_PROMPT] Initial payload 'msg': '{user_msg_text_for_memory}'")
    log.info(f"[DW_ENHANCE_PROMPT] Initial payload 'attachments': {json.dumps(latest_user_attachments, indent=2)}")
    log.info(f"[DW_ENHANCE_PROMPT] Received payload 'messages' (count: {len(payload.get('messages', []))}). Last message: {payload.get('messages', [])[-1] if payload.get('messages') else 'None'}")

    persona_content = await get_persona_config(user_id, auth_token)
    memories = await get_memories(user_msg_text_for_memory, room_id, auth_token) if user_msg_text_for_memory and room_id else []

    system_prompt_content = persona_content
    if memories:
        memory_text = "\n\n".join([f"- {m}" for m in memories])
        system_prompt_content += f"\n\n{MEMORY_TEMPLATE.format(memories=memory_text)}"
    
    # current_conversation_messages are historical messages from payload.get("messages", [])
    # They should already be in the correct format from the gateway.
    historical_llm_messages = [msg for msg in payload.get("messages", []) if msg.get("role") != "system" and msg.get("content") is not None]

    # Construct the LATEST user message with its text and attachment hints
    latest_user_content_parts = []
    if payload.get("msg"): # This is the typed text "what's this document"
        latest_user_content_parts.append({"type": "text", "text": payload.get("msg")})

    if latest_user_attachments and isinstance(latest_user_attachments, list):
        for att in latest_user_attachments:
            log.info(f"[DW_ENHANCE_PROMPT] Processing attachment: {att.get('original_filename')}")
            latest_user_content_parts.append({
                "type": "text", # Still sending as text, but the content instructs the LLM
                "text": (
                    f"[User uploaded file: '{att.get('original_filename', 'unknown_file')}' "
                    f"of type '{att.get('content_type', 'unknown_type')}'. "
                    f"You can use the 'extractTextFromFile' tool to process its content. "
                    f"Use object_name: '{att.get('object_name')}' and "
                    f"original_filename: '{att.get('original_filename')}']"
                )
            })
    
    log.info(f"[DW_ENHANCE_PROMPT] Constructed latest_user_content_parts: {json.dumps(latest_user_content_parts, indent=2)}")

    final_messages_for_llm = [{"role": "system", "content": system_prompt_content}]
    final_messages_for_llm.extend(historical_llm_messages) # Add historical messages

    if latest_user_content_parts: # Only add the latest user turn if there's content for it
        final_messages_for_llm.append({"role": "user", "content": latest_user_content_parts})
    elif payload.get("msg"): # Fallback if only text and no attachments made it to parts
        log.warning("[DW_ENHANCE_PROMPT] latest_user_content_parts was empty but msg existed. Adding msg as simple text content.")
        final_messages_for_llm.append({"role": "user", "content": payload.get("msg")})

    # THIS IS THE KEY: update the 'messages' in the original payload object
    # The llm_proxy activity call uses this payload.
    payload["messages"] = final_messages_for_llm
    
    log.info(f"[DW_ENHANCE_PROMPT] Final 'payload[messages]' being sent to LLM (count: {len(payload['messages'])}):")
    for i, msg in enumerate(payload['messages']):
        log.info(f"[DW_ENHANCE_PROMPT] LLM Message [{i}] Role: {msg.get('role')}, Content Preview: {str(msg.get('content'))[:200]}...")
        if isinstance(msg.get('content'), list):
            for j, part in enumerate(msg.get('content')):
                 log.info(f"[DW_ENHANCE_PROMPT]   Part [{j}] Type: {part.get('type')}, Text Preview: {str(part.get('text'))[:150]}...")

    return payload

async def forward_to_llm_proxy(payload: dict, reply_subject: str, ack_subject: str, nc: NATS, room_id_header: str):
    last_ack   = time.monotonic()
    INIT_ACK   = b"+INIT_ACK"
    CHUNK_ACK  = b"+ACK"

    async def _ack_listener(_msg):
        nonlocal last_ack
        last_ack = time.monotonic()

    ack_sid = await nc.subscribe(ack_subject, cb=_ack_listener)
    llm_payload_built = build_llm_payload(payload)
    model_name  = llm_payload_built["model"]

    # ---- ADD COMPREHENSIVE LOGGING BLOCK ----
    log.info(f"[DW forward_to_llm_proxy] Payload being sent to llm_proxy WebSocket (model: {model_name}):")
    log.info(f"[DW forward_to_llm_proxy] Original payload 'msg' field: '{payload.get('msg')}'")
    log.info(f"[DW forward_to_llm_proxy] Original payload 'attachments' field: {json.dumps(payload.get('attachments'), indent=2)}")
    log.info(f"[DW forward_to_llm_proxy] Messages IN 'llm_payload_built' (from build_llm_payload, count: {len(llm_payload_built.get('messages', []))}):")
    for i, msg_item in enumerate(llm_payload_built.get("messages", [])):
        log.info(f"[DW forward_to_llm_proxy]   LLM_PAYLOAD_BUILT Message [{i}] Role: {msg_item.get('role')}, Content Preview: {str(msg_item.get('content'))[:200]}...")
        if isinstance(msg_item.get('content'), list):
            for j, part_item in enumerate(msg_item.get('content')):
                 log.info(f"[DW forward_to_llm_proxy]     Part [{j}] Type: {part_item.get('type')}, Text Preview: {str(part_item.get('text'))[:150]}...")
    # ---- END LOGGING BLOCK ----

    try:
        # Increased connection timeout for better reliability
        async with websockets.connect(LLM_WS_URL, close_timeout=5.0) as ws:
            log.info("✅ Connected to llm_proxy (%s) – sending prompt", model_name)
            
            # ---- LOG WHAT'S ACTUALLY BEING SENT ----
            log.info(f"[DW forward_to_llm_proxy] Full llm_payload_built being sent to LLM Proxy WS: {json.dumps(llm_payload_built, indent=2)}")
            # ---- END LOGGING ----
            
            await ws.send(json.dumps(llm_payload_built))
            await nc.publish(ack_subject, INIT_ACK)

            chunk_no = 0
            tool_call_detected = False
            artifact_chunks = []
            
            # Define common headers for NATS replies
            nats_reply_headers = {"Room-Id": room_id_header}

            try:
                async for message in ws:
                    # Check for artifact tool call response from LLM proxy
                    try:
                        parsed = json.loads(message)
                        
                        # Check if this is a tool call response for artifact creation
                        if parsed.get("type") == "tool_calls":
                            tool_call_detected = True
                            log.info("Found tool calls in streaming response: %s", parsed.get("content", []))
                            
                            # Send appropriate WebSocket message for artifact creation/update
                            for tool_call in parsed.get("content", []):
                                function = tool_call.get("function", {})
                                name = function.get("name", "")
                                
                                if name in ["createDocument", "updateDocument"]:
                                    try:
                                        arguments = json.loads(function.get("arguments", "{}"))
                                        
                                        if name == "createDocument":
                                            document_id = str(uuid.uuid4())
                                            artifact_init = {
                                                "type": "artifact_create_init",
                                                "payload": {
                                                    "documentId": document_id,
                                                    "title": arguments.get("title", "Untitled Document"),
                                                    "kind": arguments.get("kind", "text")
                                                }
                                            }
                                            await nc.publish(reply_subject, json.dumps(artifact_init).encode(), headers=nats_reply_headers)
                                            
                                            # Send a regular assistant message about the artifact creation
                                            assistant_message = {
                                                "choices": [
                                                    {
                                                        "delta": {
                                                            "content": f"I'm creating a {arguments.get('kind', 'text')} document titled \"{arguments.get('title', 'Untitled Document')}\" for you."
                                                        }
                                                    }
                                                ]
                                            }
                                            await nc.publish(reply_subject, json.dumps(assistant_message).encode(), headers=nats_reply_headers)
                                            
                                            # Now generate content based on conversation context
                                            await generate_artifact_content(
                                                model_name,
                                                document_id, 
                                                arguments.get("kind", "text"),
                                                arguments.get("title", "Untitled"),
                                                user_id,
                                                room_id,
                                                reply_subject,
                                                nc,
                                                payload.get("messages", []),
                                                auth_token, # Pass auth_token for API call
                                                nats_reply_headers
                                            )
                                            
                                        elif name == "updateDocument":
                                            document_id = arguments.get("document_id", "")
                                            if document_id:
                                                artifact_update = {
                                                    "type": "artifact_update_init",
                                                    "payload": {
                                                        "documentId": document_id,
                                                        "description": arguments.get("description", "")
                                                    }
                                                }
                                                await nc.publish(reply_subject, json.dumps(artifact_update).encode(), headers=nats_reply_headers)
                                                
                                                # Send a regular assistant message about the artifact update
                                                assistant_message = {
                                                    "choices": [
                                                        {
                                                            "delta": {
                                                                "content": f"I'm updating the document based on: {arguments.get('description', '')}."
                                                            }
                                                        }
                                                    ]
                                                }
                                                await nc.publish(reply_subject, json.dumps(assistant_message).encode(), headers=nats_reply_headers)
                                                
                                                # Fetch current content and generate updated content
                                                await update_artifact_content(
                                                    model_name,
                                                    document_id,
                                                    arguments.get("description", ""),
                                                    user_id,
                                                    room_id,
                                                    reply_subject,
                                                    nc,
                                                    payload.get("messages", []),
                                                    auth_token,
                                                    nats_reply_headers
                                                )
                                            else:
                                                log.error("Update document tool call missing document_id")
                                                await nc.publish(reply_subject, json.dumps({
                                                    "error": "Missing document_id in updateDocument tool call"
                                                }).encode(), headers=nats_reply_headers)
                                        
                                        # Don't continue processing the WebSocket stream - we're handling via artifact flow
                                        break
                                    except json.JSONDecodeError:
                                        log.error(f"Failed to parse tool call arguments: {function.get('arguments')}")
                                        continue
                            
                            # Send acknowledgment for this chunk
                            await nc.publish(ack_subject, CHUNK_ACK)
                            continue
                        
                        # For error messages
                        if "error" in parsed:
                            error_msg = parsed["error"]
                            log.error(f"LLM proxy returned error: {error_msg}")
                            await nc.publish(reply_subject, json.dumps({"error": f"LLM service error: {error_msg}"}).encode(), headers=nats_reply_headers)
                            return
                            
                    except json.JSONDecodeError:
                        pass  # Not JSON, continue normal processing
                    
                    # If no tool call detected, process as normal chat message
                    if not tool_call_detected:
                        data = message.encode()
                        log.info("⇢ to NATS %s : %.120s", reply_subject, data)
                        await nc.publish(reply_subject, data, headers=nats_reply_headers)
                        CHUNKS_RELAYED.labels(model=model_name).inc()

                        chunk_no += 1
                        if chunk_no % ACK_EVERY == 0:
                            await nc.publish(ack_subject, CHUNK_ACK)

                        if time.monotonic() - last_ack > ACK_TIMEOUT:
                            CANCELLED.inc()
                            log.warning("⚠️  client idle >%s s – cancelling", ACK_TIMEOUT)
                            await ws.close()
                            break
            finally:
                # Only send DONE if it was a regular chat (not artifact creation)
                if not tool_call_detected:
                    await nc.publish(reply_subject, b"[DONE]", headers=nats_reply_headers)
                await ack_sid.unsubscribe()
    except websockets.exceptions.WebSocketException as e:
        log.error(f"WebSocket error: {e}")
        await nc.publish(reply_subject, json.dumps({"error": f"Failed to connect to LLM service: {str(e)}"}).encode(), headers={"Room-Id": room_id_header})
    except Exception as e:
        log.exception(f"Error in LLM proxy communication: {e}")
        await nc.publish(reply_subject, json.dumps({"error": f"Internal error: {str(e)}"}).encode(), headers={"Room-Id": room_id_header})

async def generate_artifact_content(model, document_id, kind, title, user_id, room_id, reply_subject, nc, messages, auth_token: str, nats_reply_headers: dict): # ADDED auth_token
    """
    Generates content for a newly created artifact and streams it via WebSocket
    """
    try:
        # Create a system prompt for content generation
        system_prompt = f"You are creating a {kind} document titled '{title}'. Generate appropriate content based on the conversation context."
        
        # Build prompt with recent conversation context
        content_gen_prompt = [
            {"role": "system", "content": system_prompt},
            # Include recent conversation messages for context (up to 5)
        ]
        
        # Add recent conversation messages if available
        if messages:
            content_gen_prompt.extend(messages[-5:])
        
        # Add the final instruction
        content_gen_prompt.append(
            {"role": "user", "content": f"Please generate the content for the {kind} document titled '{title}'."}
        )
        
        # Connect to llm_proxy for content generation
        async with websockets.connect(LLM_WS_URL, close_timeout=5.0) as ws:
            # Request content generation without document tools
            llm_payload = {
                "model": model,
                "messages": content_gen_prompt,
                "stream": True,
                "use_document_tools": False
            }
            
            await ws.send(json.dumps(llm_payload))
            
            # Track total generated content for final save
            full_content = ""
            
            # Stream responses back to client
            async for message in ws:
                try:
                    # Try to parse as JSON, but handle plain text too
                    try:
                        parsed = json.loads(message)
                        if "error" in parsed:
                            log.error(f"Error generating content: {parsed['error']}")
                            continue
                            
                        # Extract content from Ollama format
                        content = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content is None:
                            continue
                    except json.JSONDecodeError:
                        # Treat unparseable message as raw content
                        content = message
                    
                    # Append to full content
                    full_content += content
                    
                    # Send delta to client
                    ws_delta = {
                        "type": "artifact_delta",
                        "payload": {
                            "documentId": document_id,
                            "kind": kind,
                            "delta": content
                        }
                    }
                    await nc.publish(reply_subject, json.dumps(ws_delta).encode(), headers=nats_reply_headers)
                    
                except Exception as e:
                    log.exception(f"Error processing content generation chunk: {e}")
            
            # Save artifact to database
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {"Content-Type": "application/json"}
                    # Re-add Authorization header for backend API call
                    if auth_token:
                        headers["Authorization"] = f"Bearer {auth_token}"

                    body = {
                        "title": title,
                        "kind": kind,
                        "content": full_content
                    }
                    async with session.post(
                        f"{GATEWAY_URL}/v1/artifacts/{document_id}",
                        json=body,
                        headers=headers
                    ) as resp:
                        if resp.status != 201: # Check for 201 Created status
                            error_text = await resp.text()
                            log.error(f"Failed to save artifact: {error_text}")
            except Exception as e:
                log.exception(f"Error saving artifact: {e}")
            
            # Send finish message
            ws_finish = {
                "type": "artifact_finish",
                "payload": {
                    "documentId": document_id
                }
            }
            await nc.publish(reply_subject, json.dumps(ws_finish).encode(), headers=nats_reply_headers)
            
    except Exception as e:
        log.exception(f"Error in artifact content generation: {e}")
        error_msg = {
            "type": "error",
            "payload": {
                "message": f"Error generating artifact content: {str(e)}"
            }
        }
        await nc.publish(reply_subject, json.dumps(error_msg).encode(), headers=nats_reply_headers)

async def update_artifact_content(model, document_id, description, user_id, room_id, reply_subject, nc, messages, auth_token: str, nats_reply_headers: dict):
    """
    Updates content for an existing artifact and streams it via WebSocket
    """
    try:
        # Fetch current document content
        current_content = ""
        kind = "text" # Default kind
        title = "Untitled" # Default title
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
                async with session.get(
                    f"{GATEWAY_URL}/v1/artifacts/{document_id}",
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        doc_data = await resp.json()
                        # Get the latest version's content
                        if isinstance(doc_data, list) and len(doc_data) > 0:
                            latest_doc = doc_data[0] # Assuming latest is first due to desc ordering in getter
                            current_content = latest_doc.get("content", "")
                            kind = latest_doc.get("kind", "text")
                            title = latest_doc.get("title", "Untitled")
                        else:
                            log.warning(f"No document content found for {document_id}, possibly empty list.")
                    else:
                        log.error(f"Failed to fetch artifact: Status {resp.status}")
                        error_text = await resp.text()
                        log.error(f"Error: {error_text}")
                        # Send error to client
                        await nc.publish(reply_subject, json.dumps({
                            "error": f"Failed to fetch document: {error_text}"
                        }).encode(), headers=nats_reply_headers)
                        return
        except Exception as e:
            log.exception(f"Error fetching artifact: {e}")
            await nc.publish(reply_subject, json.dumps({
                "error": f"Error fetching document: {str(e)}"
            }).encode(), headers=nats_reply_headers)
            return
        
        # Create system prompt for content update
        system_prompt = f"You are updating a {kind} document titled '{title}' based on this description: '{description}'. Here is the current content:\n\n{current_content}\n\nGenerate the updated content."
        
        # Build prompt with recent conversation context
        content_gen_prompt = [
            {"role": "system", "content": system_prompt},
            # Include recent conversation context
        ]
        
        # Add recent conversation messages if available
        if messages:
            content_gen_prompt.extend(messages[-5:])
            
        # Add the final instruction
        content_gen_prompt.append(
            {"role": "user", "content": f"Please update the document based on: {description}"}
        )
        
        # Connect to llm_proxy for content generation
        async with websockets.connect(LLM_WS_URL, close_timeout=5.0) as ws:
            # Request content generation without document tools
            llm_payload = {
                "model": model,
                "messages": content_gen_prompt,
                "stream": True,
                "use_document_tools": False
            }
            
            await ws.send(json.dumps(llm_payload))
            
            # Track total generated content for final save
            full_content = ""
            
            # Stream responses back to client
            async for message in ws:
                try:
                    # Try to parse as JSON, but handle plain text too
                    try:
                        parsed = json.loads(message)
                        if "error" in parsed:
                            log.error(f"Error generating content: {parsed['error']}")
                            continue
                            
                        # Extract content from Ollama format
                        content = parsed.get("choices", [{}])[0].get("delta", {}).get("content")
                        if content is None:
                            continue
                    except json.JSONDecodeError:
                        # Treat unparseable message as raw content
                        content = message
                    
                    # Append to full content
                    full_content += content
                    
                    # Send delta to client
                    ws_delta = {
                        "type": "artifact_delta",
                        "payload": {
                            "documentId": document_id,
                            "kind": kind,
                            "delta": content
                        }
                    }
                    await nc.publish(reply_subject, json.dumps(ws_delta).encode(), headers=nats_reply_headers)
                    
                except Exception as e:
                    log.exception(f"Error processing content update chunk: {e}")
            
            # Save updated artifact to database
            try:
                async with aiohttp.ClientSession() as session:
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {auth_token}" if auth_token else ""
                    }
                    body = {
                        "title": title,
                        "kind": kind,
                        "content": full_content
                    }
                    async with session.post(
                        f"{GATEWAY_URL}/v1/artifacts/{document_id}",
                        json=body,
                        headers=headers
                    ) as resp:
                        if resp.status != 201: # Check for 201 Created status
                            error_text = await resp.text()
                            log.error(f"Failed to save updated artifact: {error_text}")
            except Exception as e:
                log.exception(f"Error saving updated artifact: {e}")
            
            # Send finish message
            ws_finish = {
                "type": "artifact_finish",
                "payload": {
                    "documentId": document_id
                }
            }
            await nc.publish(reply_subject, json.dumps(ws_finish).encode(), headers=nats_reply_headers)
            
    except Exception as e:
        log.exception(f"Error in artifact content update: {e}")
        error_msg = {
            "type": "error",
            "payload": {
                "message": f"Error updating artifact content: {str(e)}"
            }
        }
        await nc.publish(reply_subject, json.dumps(error_msg).encode(), headers=nats_reply_headers)

async def on_request(msg, nc):
    hdrs = msg.headers or {}
    reply_subject = hdrs.get("Reply")
    ack_subject   = hdrs.get("Ack")
    auth_token    = hdrs.get("Auth")

    if not (reply_subject and ack_subject and auth_token):
        log.error("Missing required headers – dropping message")
        # Send error message to client if reply subject is available
        if reply_subject:
            await nc.publish(reply_subject, json.dumps({
                "error": "Missing required headers"
            }).encode())
        await msg.term()
        return

    for field in ("Reply", "Ack", "Auth"):
        if isinstance(hdrs.get(field), bytes):
            hdrs[field] = hdrs[field].decode()

    try:
        payload = json.loads(msg.data)
        log.info(f"[DIALOGUE_WORKER on_request] Received payload from NATS: {json.dumps(payload, indent=2)}")
        room_id = payload.get("room_id") # This is already a string UUID
        user_id = payload.get("user_id")
        
        if not room_id:
            log.error("Missing room_id in payload")
            if reply_subject:
                await nc.publish(reply_subject, json.dumps({
                    "error": "Missing room_id in request"
                }).encode())
            await msg.term()
            return
            
        # Enhance the prompt with memory and persona
        enhanced_payload = await enhance_prompt(payload, auth_token)
        
        # Check if we should use the document tools
        use_document_tools = payload.get("use_document_tools", True)
        
        if use_document_tools:
            # Forward directly to WebSocket and handle possible artifact creation/update
            await forward_with_artifact_support(enhanced_payload, reply_subject, ack_subject, nc, auth_token, room_id)
        else:
            # Use the regular forwarding for normal chat
            await forward_to_llm_proxy(enhanced_payload, reply_subject, ack_subject, nc, room_id)
            
        await msg.ack()
    except Exception as e:
        log.exception(f"Error processing message: {e}")
        traceback.print_exc()
        if reply_subject:
            await nc.publish(reply_subject, json.dumps({
                "error": f"Error processing message: {str(e)}"
            }).encode())
        await msg.term()

async def forward_with_artifact_support(payload, reply_subject, ack_subject, nc, auth_token, room_id_header: str):
    """
    Handles forwarding to LLM proxy with support for artifact creation/update.
    Detects when LLM outputs a tool call and initiates the artifact workflow.
    """
    last_ack   = time.monotonic()
    INIT_ACK   = b"+INIT_ACK"
    CHUNK_ACK  = b"+ACK"

    async def _ack_listener(_msg):
        nonlocal last_ack
        last_ack = time.monotonic()

    ack_sid = await nc.subscribe(ack_subject, cb=_ack_listener)
    llm_payload_built = build_llm_payload(payload)
    model_name  = llm_payload_built["model"]
    room_id = payload.get("room_id")
    user_id = payload.get("user_id", "")
    
    # WebSocket connection ID (for sending artifact messages)
    # In production, you'd track this properly, but for this implementation 
    # we'll use the reply_subject as a unique identifier
    websocket_id = reply_subject 

    # ---- ADD COMPREHENSIVE LOGGING BLOCK ----
    log.info(f"[DW forward_with_artifact_support] Payload being sent to llm_proxy WebSocket (model: {model_name}):")
    log.info(f"[DW forward_with_artifact_support] Original payload 'msg' field: '{payload.get('msg')}'")
    log.info(f"[DW forward_with_artifact_support] Original payload 'attachments' field: {json.dumps(payload.get('attachments'), indent=2)}")
    log.info(f"[DW forward_with_artifact_support] Messages IN 'llm_payload_built' (from build_llm_payload, count: {len(llm_payload_built.get('messages', []))}):")
    for i, msg_item in enumerate(llm_payload_built.get("messages", [])):
        log.info(f"[DW forward_with_artifact_support]   LLM_PAYLOAD_BUILT Message [{i}] Role: {msg_item.get('role')}, Content Preview: {str(msg_item.get('content'))[:200]}...")
        if isinstance(msg_item.get('content'), list):
            for j, part_item in enumerate(msg_item.get('content')):
                 log.info(f"[DW forward_with_artifact_support]     Part [{j}] Type: {part_item.get('type')}, Text Preview: {str(part_item.get('text'))[:150]}...")
    # ---- END LOGGING BLOCK ----

    try:
        # Connect to llm_proxy WebSocket
        async with websockets.connect(LLM_WS_URL, close_timeout=5.0) as ws:
            log.info("✅ Connected to llm_proxy (%s) – sending prompt with document tools", model_name)
            
            # Add flag to indicate document tool support should be used
            enhanced_payload_for_ws = {**llm_payload_built, "use_document_tools": True}
            
            # ---- LOG WHAT'S ACTUALLY BEING SENT ----
            log.info(f"[DW forward_with_artifact_support] Full enhanced_payload_for_ws being sent to LLM Proxy WS: {json.dumps(enhanced_payload_for_ws, indent=2)}")
            # ---- END LOGGING ----
            
            await ws.send(json.dumps(enhanced_payload_for_ws))
            await nc.publish(ack_subject, INIT_ACK)

            chunk_no = 0
            tool_call_detected = False
            artifact_chunks = []
            
            # Define common headers for NATS replies
            nats_reply_headers = {"Room-Id": room_id_header}

            try:
                async for message in ws:
                    # Check for artifact tool call response from LLM proxy
                    try:
                        parsed = json.loads(message)
                        
                        # Check if this is a tool call response for artifact creation
                        if parsed.get("type") == "tool_calls":
                            tool_call_detected = True
                            log.info("Found tool calls in streaming response: %s", parsed.get("content", []))
                            
                            # Send appropriate WebSocket message for artifact creation/update
                            for tool_call in parsed.get("content", []):
                                function = tool_call.get("function", {})
                                name = function.get("name", "")
                                
                                if name in ["createDocument", "updateDocument"]:
                                    try:
                                        arguments = json.loads(function.get("arguments", "{}"))
                                        
                                        if name == "createDocument":
                                            document_id = str(uuid.uuid4())
                                            artifact_init = {
                                                "type": "artifact_create_init",
                                                "payload": {
                                                    "documentId": document_id,
                                                    "title": arguments.get("title", "Untitled Document"),
                                                    "kind": arguments.get("kind", "text")
                                                }
                                            }
                                            await nc.publish(reply_subject, json.dumps(artifact_init).encode(), headers=nats_reply_headers)
                                            
                                            # Send a regular assistant message about the artifact creation
                                            assistant_message = {
                                                "choices": [
                                                    {
                                                        "delta": {
                                                            "content": f"I'm creating a {arguments.get('kind', 'text')} document titled \"{arguments.get('title', 'Untitled Document')}\" for you."
                                                        }
                                                    }
                                                ]
                                            }
                                            await nc.publish(reply_subject, json.dumps(assistant_message).encode(), headers=nats_reply_headers)
                                            
                                            # Now generate content based on conversation context
                                            await generate_artifact_content(
                                                model_name,
                                                document_id, 
                                                arguments.get("kind", "text"),
                                                arguments.get("title", "Untitled"),
                                                user_id,
                                                room_id,
                                                reply_subject,
                                                nc,
                                                payload.get("messages", []),
                                                auth_token, # Pass auth_token for API call
                                                nats_reply_headers
                                            )
                                            
                                        elif name == "updateDocument":
                                            document_id = arguments.get("document_id", "")
                                            if document_id:
                                                artifact_update = {
                                                    "type": "artifact_update_init",
                                                    "payload": {
                                                        "documentId": document_id,
                                                        "description": arguments.get("description", "")
                                                    }
                                                }
                                                await nc.publish(reply_subject, json.dumps(artifact_update).encode(), headers=nats_reply_headers)
                                                
                                                # Send a regular assistant message about the artifact update
                                                assistant_message = {
                                                    "choices": [
                                                        {
                                                            "delta": {
                                                                "content": f"I'm updating the document based on: {arguments.get('description', '')}."
                                                            }
                                                        }
                                                    ]
                                                }
                                                await nc.publish(reply_subject, json.dumps(assistant_message).encode(), headers=nats_reply_headers)
                                                
                                                # Fetch current content and generate updated content
                                                await update_artifact_content(
                                                    model_name,
                                                    document_id,
                                                    arguments.get("description", ""),
                                                    user_id,
                                                    room_id,
                                                    reply_subject,
                                                    nc,
                                                    payload.get("messages", []),
                                                    auth_token,
                                                    nats_reply_headers
                                                )
                                            else:
                                                log.error("Update document tool call missing document_id")
                                                await nc.publish(reply_subject, json.dumps({
                                                    "error": "Missing document_id in updateDocument tool call"
                                                }).encode(), headers=nats_reply_headers)
                                        
                                        # Don't continue processing the WebSocket stream - we're handling via artifact flow
                                        break
                                    except json.JSONDecodeError:
                                        log.error(f"Failed to parse tool call arguments: {function.get('arguments')}")
                                        continue
                            
                            # Send acknowledgment for this chunk
                            await nc.publish(ack_subject, CHUNK_ACK)
                            continue
                        
                        # For error messages
                        if "error" in parsed:
                            error_msg = parsed["error"]
                            log.error(f"LLM proxy returned error: {error_msg}")
                            await nc.publish(reply_subject, json.dumps({"error": f"LLM service error: {error_msg}"}).encode(), headers=nats_reply_headers)
                            return
                            
                    except json.JSONDecodeError:
                        pass  # Not JSON, continue normal processing
                    
                    # If no tool call detected, process as normal chat message
                    if not tool_call_detected:
                        data = message.encode()
                        log.info("⇢ to NATS %s : %.120s", reply_subject, data)
                        await nc.publish(reply_subject, data, headers=nats_reply_headers)
                        CHUNKS_RELAYED.labels(model=model_name).inc()

                        chunk_no += 1
                        if chunk_no % ACK_EVERY == 0:
                            await nc.publish(ack_subject, CHUNK_ACK)

                        if time.monotonic() - last_ack > ACK_TIMEOUT:
                            CANCELLED.inc()
                            log.warning("⚠️  client idle >%s s – cancelling", ACK_TIMEOUT)
                            await ws.close()
                            break
            finally:
                # Only send DONE if it was a regular chat (not artifact creation)
                if not tool_call_detected:
                    await nc.publish(reply_subject, b"[DONE]", headers=nats_reply_headers)
                await ack_sid.unsubscribe()
    except websockets.exceptions.WebSocketException as e:
        log.error(f"WebSocket error: {e}")
        await nc.publish(reply_subject, json.dumps({"error": f"Failed to connect to LLM service: {str(e)}"}).encode(), headers={"Room-Id": room_id_header})
    except Exception as e:
        log.exception(f"Error in LLM proxy communication: {e}")
        await nc.publish(reply_subject, json.dumps({"error": f"Internal error: {str(e)}"}).encode(), headers={"Room-Id": room_id_header})

async def main():
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics on :%s/metrics", METRICS_PORT)
    await consume(on_request)

if __name__ == "__main__":
    asyncio.run(main())
