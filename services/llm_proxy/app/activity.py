from temporalio import activity
import aiohttp, os, json, logging, asyncio
from typing import List, Dict, Any, Optional
# import uuid # Not strictly needed here if doc_id generated in workflow

log = logging.getLogger("llm_proxy.activity")

OPENAI_PATH = "/v1/chat/completions"

DOCUMENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "createDocument",
            "description": "Creates a new document with a title and specified kind. The content will be generated subsequently based on the ongoing conversation context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the new document.",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["text", "code", "image", "sheet"],
                        "description": "The kind of document to create.",
                    },
                },
                "required": ["title", "kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "updateDocument",
            "description": "Requests an update to an existing document based on a description of changes. The existing content will be fetched and updated based on this description and conversation context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "string",
                        "description": "The UUID of the document to be updated.",
                    },
                    "description": {
                        "type": "string",
                        "description": "A description of the changes to make to the document.",
                    },
                },
                "required": ["document_id", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extractTextFromFile",
            "description": "Extracts text content from an uploaded file (TXT, PDF, DOC, DOCX). Use this before answering questions about a user-uploaded file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_name": { # This should be the unique path/key of the file in MinIO
                        "type": "string",
                        "description": "The unique identifier (pathname or key) of the file in storage."
                    },
                    "original_filename": { # Useful for determining file type by extension
                        "type": "string",
                        "description": "The original filename as uploaded by the user."
                    }
                },
                "required": ["object_name", "original_filename"]
            }
        }
    }
]

@activity.defn
async def call_ollama(model: str, prompt: str, stream: bool = False) -> List[str]:
    """
    Basic Ollama call for backward compatibility.
    Calls Ollama's OpenAI-compatible endpoint with a simple prompt.
    """
    base = os.getenv("OLLAMA_URL")
    if not base:
        log.error("OLLAMA_URL environment variable is not set for call_ollama activity!")
        raise ValueError("OLLAMA_URL environment variable is not set")
    
    url = f"{base}{OPENAI_PATH}"
    
    # Convert simple prompt to messages format
    messages = [{"role": "user", "content": prompt}]
    
    payload = {
        "model": model,
        "messages": messages,
        "stream": stream
    }
    
    activity.heartbeat()
    log.info(f"Calling Ollama with simple prompt. Model: {model}, Streaming: {stream}")
    
    results = []
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            activity.heartbeat()
            if resp.status != 200:
                text = await resp.text()
                log.error(f"Ollama error {resp.status} -> {text[:500]}")
                return [f"Ollama API Error {resp.status}: {text[:200]}"]
                
            if not stream:
                data = await resp.json()
                return [data.get("choices", [{}])[0].get("message", {}).get("content", "")]
                
            # Streaming response
            async for line in resp.content:
                activity.heartbeat()
                line = line.strip()
                if not line or not line.startswith(b"data: "):
                    continue
                    
                sse_payload = line.removeprefix(b"data: ").strip()
                if sse_payload == b"[DONE]":
                    break
                    
                try:
                    chunk = json.loads(sse_payload.decode('utf-8'))
                    content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                    if content is not None:
                        results.append(content)
                except Exception as e:
                    log.warning(f"Error processing stream chunk: {e}")
                    
            return results

@activity.defn
async def call_ollama_with_tool_support(
    model: str, 
    messages: list[dict], 
    stream: bool = True,
    use_document_tools: bool = False
) -> dict:
    """
    Calls Ollama's OpenAI-compatible endpoint, with support for tool calling.
    Assumes Ollama model supports OpenAI-style tool calling.

    Returns a dictionary:
    {
        "type": "chat_content" | "tool_calls" | "error",
        "content": list[str] (for chat_content: streamed delta chunks) 
                   | list[dict] (for tool_calls: parsed tool_call objects from Ollama response)
                   | str (for error: error message),
        "finish_reason": str | None (e.g., "stop", "tool_calls")
    }
    """
    base = os.getenv("OLLAMA_URL")
    if not base:
        log.error("OLLAMA_URL environment variable is not set for call_ollama_with_tool_support activity!")
        raise ValueError("OLLAMA_URL environment variable is not set")

    url = f"{base}{OPENAI_PATH}"

    payload = {
        "model": model, 
        "messages": messages, 
        "stream": stream
    }
    if use_document_tools:
        payload["tools"] = DOCUMENT_TOOLS
        payload["tool_choice"] = "auto" # Explicitly setting auto, can be specific if needed

    activity.heartbeat()
    log.info(f"Calling Ollama. Model: {model}, Streaming: {stream}, Using Tools: {use_document_tools}")
    log.debug(f"Ollama Payload: {json.dumps(payload, indent=2)}")

    results_content = []
    final_finish_reason = None
    
    # This will store fully formed tool_calls objects if they are sent in one go.
    # If tool_calls are streamed incrementally (e.g. token by token for name/args),
    # a more complex aggregation logic would be needed here.
    # Based on Ollama blog, it seems tool_calls might come as a complete block
    # in the 'message' object of a chunk, especially if finish_reason is 'tool_calls'.
    aggregated_tool_calls = []


    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            activity.heartbeat()
            if resp.status != 200:
                text = await resp.text()
                log.error(f"Ollama error {resp.status} -> {text[:500]}")
                return {"type": "error", "content": f"Ollama API Error {resp.status}: {text[:200]}", "finish_reason": "error"}

            if not stream:
                # Handle non-streaming response (should contain full message or tool_calls)
                data = await resp.json()
                log.debug(f"Ollama Non-Streaming Response: {json.dumps(data, indent=2)}")
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                final_finish_reason = choice.get("finish_reason")

                if message.get("tool_calls"):
                    return {
                        "type": "tool_calls", 
                        "content": message["tool_calls"], # This is a list of tool_call objects
                        "finish_reason": final_finish_reason
                    }
                elif message.get("content") is not None: # Not 'is not None'
                    return {
                        "type": "chat_content", 
                        "content": [message["content"]],
                        "finish_reason": final_finish_reason
                    }
                else: # No content and no tool_calls
                    log.warning("Ollama non-streaming response had no content or tool_calls.")
                    return {"type": "error", "content": "No content or tool_calls in Ollama non-streaming response", "finish_reason": "error"}

            # -------- Streaming Branch --------
            async for raw_sse_line in resp.content:
                activity.heartbeat()
                line = raw_sse_line.strip()
                if not line or not line.startswith(b"data: "):
                    continue

                sse_payload_bytes = line.removeprefix(b"data: ").strip()
                if sse_payload_bytes == b"[DONE]":
                    log.debug("Received [DONE] marker from Ollama stream.")
                    break
                
                try:
                    # Parse JSON payload after stripping data: prefix
                    chunk = json.loads(sse_payload_bytes.decode("utf-8"))
                    
                    # Check for tool calls in the Ollama response
                    choice = chunk.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    tool_calls = delta.get("tool_calls", [])
                    finish_reason = choice.get("finish_reason")
                    
                    # Process tool calls if present
                    if tool_calls:
                        log.info(f"Found tool calls in streaming response: {tool_calls}")
                        aggregated_tool_calls.extend(tool_calls)
                        # This ensures we report tool calls in the final result
                        final_finish_reason = "tool_calls"
                    
                    # Process regular content in streaming mode
                    content = delta.get("content")
                    if content is not None:
                        results_content.append(content)
                        
                    # Check if this chunk indicates the end with tool_calls finish reason
                    if finish_reason == "tool_calls":
                        log.info("Streaming response finished with tool_calls reason")
                        final_finish_reason = "tool_calls"
                        
                        # Fetch any tool_calls from the message object if present
                        message = chunk.get("choices", [{}])[0].get("message", {})
                        if message and message.get("tool_calls"):
                            aggregated_tool_calls.extend(message["tool_calls"])
                            
                except json.JSONDecodeError:
                    log.warning(f"Failed to parse JSON from SSE payload: {sse_payload_bytes[:200]}")
                except Exception as e:
                    log.warning(f"Error processing stream chunk: {e}")
                    
            # End of streaming - determine final response type
            if aggregated_tool_calls:
                log.info(f"Returning aggregated tool calls: {aggregated_tool_calls}")
                return {
                    "type": "tool_calls", 
                    "content": aggregated_tool_calls,
                    "finish_reason": final_finish_reason or "tool_calls"
                }
            else:
                return {
                    "type": "chat_content", 
                    "content": results_content,
                    "finish_reason": final_finish_reason or "stop"
                }

# New function to extract artifact details from tool calls
@activity.defn
async def extract_artifact_details(tool_calls: list) -> dict:
    """
    Extracts details about the artifact from tool_calls returned by the LLM.
    Returns a dictionary with artifact details that can be used for WebSocket messaging.
    """
    for tool_call in tool_calls:
        function = tool_call.get("function", {})
        name = function.get("name", "")
        
        if name == "createDocument":
            try:
                arguments = json.loads(function.get("arguments", "{}"))
                return {
                    "action": "create",
                    "title": arguments.get("title", "Untitled Document"),
                    "kind": arguments.get("kind", "text"),
                }
            except json.JSONDecodeError:
                logging.error(f"Failed to parse createDocument arguments: {function.get('arguments')}")
                
        elif name == "updateDocument":
            try:
                arguments = json.loads(function.get("arguments", "{}"))
                return {
                    "action": "update",
                    "document_id": arguments.get("document_id", ""),
                    "description": arguments.get("description", ""),
                }
            except json.JSONDecodeError:
                logging.error(f"Failed to parse updateDocument arguments: {function.get('arguments')}")
                
    return {"action": "none"}
