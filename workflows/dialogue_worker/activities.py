import json
import logging
import aiohttp
import uuid # For document IDs if not passed

from temporalio import activity
# Assuming you have a NatsClient class, if not, adjust or import nats.aio.client directly
# from services.common.nats_helpers import NatsClient 

log = logging.getLogger(__name__)

# Configuration (ideally from workflow inputs or env)
# GATEWAY_API_URL_BASE = "http://gateway:8000" # Example

@activity.defn
async def enhance_prompt_activity(
    current_messages: list[dict], # Historical messages, already in {"role": ..., "content": ...} format
    latest_user_message_text: str | None, # The latest user message text
    user_id: str, 
    room_id: str, # room_id might be part of user_id or a separate concept
    auth_token: str,
    gateway_api_url: str, # e.g. http://gateway:8000
    default_persona_content: str,
    memory_template: str,
    memory_top_n: int
) -> list[dict]:
    """
    Adapts prompt enhancement logic.
    Takes current messages, adds system prompt with persona and memories.
    """
    activity.heartbeat()
    log.info(f"Enhancing prompt for user_id: {user_id}, room_id: {room_id}. Received {len(current_messages)} historical messages. Latest user msg: '{latest_user_message_text[:100] if latest_user_message_text else "None"}...'")

    user_input_for_memory = ""
    # Determine input for memory query: use latest_user_message_text if available, else last from history.
    if latest_user_message_text:
        user_input_for_memory = latest_user_message_text
    elif current_messages: 
        last_message = current_messages[-1]
        # History items (current_messages) should now have 'content' field from gateway
        if last_message.get("role") == "user" and last_message.get("content"):
            user_input_for_memory = last_message.get("content", "")
        else:
            log.warning(f"Last user message in history was not role 'user' or had no 'content': {str(last_message)[:200]}")
    log.info(f"Input for memory query: '{user_input_for_memory[:100]}...'")

    # Simplified get_persona_config
    persona_content = default_persona_content # Start with default
    try:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        params = {"user_id": user_id} if user_id else {}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{gateway_api_url}/v1/persona/config", params=params, timeout=5.0, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    persona_content = data.get("content", default_persona_content)
                    log.info(f"Successfully fetched persona for user {user_id}")
                else:
                    log.warning(f"Failed to fetch persona (status {resp.status}), using default.")
    except Exception as e:
        log.error(f"Error fetching persona: {e}, using default.")
    
    # Simplified get_memories
    memories = []
    if user_input_for_memory and room_id: # Changed from user_input_msg
        try:
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{gateway_api_url}/v1/memory/query",
                    json={"query": user_input_for_memory, "room_id": room_id, "top_n": memory_top_n}, # Changed from user_input_msg
                    timeout=5.0,
                    headers=headers
                ) as resp:
                    if resp.status == 200:
                        mem_data = await resp.json()
                        memories = [m["text"] for m in mem_data]
                        log.info(f"Successfully fetched {len(memories)} memories.")
                    else:
                        log.warning(f"Failed to fetch memories (status {resp.status}).")
        except Exception as e:
            log.error(f"Error fetching memories: {e}")

    system_prompt_content = persona_content
    if memories:
        memory_text = "\n\n".join([f"- {m}" for m in memories])
        system_prompt_content += f"\n\n{memory_template.format(memories=memory_text)}"
    
    # current_messages (history) are already in {"role": ..., "content": ...} format from gateway.
    # We just need to ensure they are not system messages.
    final_llm_messages = [msg for msg in current_messages if msg.get("role") != "system" and msg.get("content") is not None]

    # Add the latest user message to the list if it exists
    if latest_user_message_text:
        final_llm_messages.append({"role": "user", "content": latest_user_message_text})
        log.debug(f"Appended latest user message: {latest_user_message_text[:100]}...")
    else:
        log.warning("No latest_user_message_text provided to enhance_prompt_activity.")

    # Insert the new system prompt at the beginning
    final_llm_messages.insert(0, {"role": "system", "content": system_prompt_content})
    
    # Log the messages being sent to LLM
    log.debug(f"Final messages prepared for LLM ({len(final_llm_messages)} messages): {json.dumps(final_llm_messages, indent=2)}")
    return final_llm_messages


@activity.defn
async def publish_to_nats_activity(
    nats_url: str, # e.g., "nats://nats:4222"
    subject: str, 
    payload: dict, 
    headers: dict | None = None
):
    """Publishes a message to a NATS subject."""
    activity.heartbeat()
    log.info(f"Publishing to NATS subject '{subject}': {json.dumps(payload)}")
    # Local import of NATS client to avoid circular imports or global state issues
    import nats.aio.client
    nc = nats.aio.client.Client()
    try:
        await nc.connect(servers=[nats_url] if isinstance(nats_url, str) else nats_url)
        await nc.publish(subject, json.dumps(payload).encode(), headers=headers)
        log.info(f"Successfully published to {subject}")
    except Exception as e:
        log.error(f"Failed to publish to NATS subject '{subject}': {e}")
        raise
    finally:
        if nc.is_connected:
            await nc.close()


@activity.defn
async def save_artifact_activity(
    gateway_api_url: str, # e.g. "http://gateway:8000"
    document_id: str,
    title: str,
    kind: str,
    content: str,
    auth_token: str # The user's JWT
):
    """Saves the artifact via the gateway API."""
    activity.heartbeat()
    log.info(f"Saving artifact ID: {document_id}, Title: {title}")
    api_url = f"{gateway_api_url}/v1/artifacts/{document_id}"
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    payload = {"title": title, "kind": kind, "content": content}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(api_url, json=payload, headers=headers, timeout=10.0) as resp:
                if resp.status == 201: # Created
                    log.info(f"Artifact {document_id} saved successfully.")
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    log.error(f"Failed to save artifact {document_id}. Status: {resp.status}, Body: {error_text}")
                    # Raise an application error that the workflow can catch if needed
                    raise Exception(f"API Error {resp.status}: {error_text}")
        except aiohttp.ClientError as e:
            log.error(f"HTTP Client error saving artifact {document_id}: {e}")
            raise 

# NEW ACTIVITY: Generate Chat Title
@activity.defn
async def generate_chat_title_activity(
    llm_proxy_url: str,
    llm_model: str,
    first_user_message: str,
    first_assistant_response: str
) -> str:
    """
    Generates a concise title for a chat based on the first user message
    and the assistant's initial response.
    """
    activity.heartbeat()
    log.info("Generating chat title...")

    prompt = f"Given the start of a conversation, generate a very short, concise title (max 5-7 words, no quotes). Example: 'User: What is AI? Assistant: AI is... Title: Introduction to AI'\n\n"
    prompt += f"User: {first_user_message}\n"
    prompt += f"Assistant: {first_assistant_response}\n"
    prompt += "Title:"

    messages = [
        {"role": "system", "content": "You are a helpful assistant that generates concise chat titles."},
        {"role": "user", "content": prompt}
    ]

    payload = {
        "model": llm_model,
        "messages": messages,
        "stream": False # We want a single, complete response for the title
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{llm_proxy_url}/v1/chat/completions", json=payload, timeout=10.0) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    log.error(f"LLM Proxy error generating title {resp.status} -> {text[:500]}")
                    return "Untitled Chat" # Fallback title on error
                
                response_data = await resp.json()
                title = response_data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                
                if not title:
                    log.warning("LLM returned empty title, using fallback.")
                    return "Untitled Chat"
                
                # Trim to a reasonable length and remove any quotes
                title = title.replace('"', '').replace("'", "").replace("Title:", "").strip()
                if len(title) > 50: # Cap length
                    title = title[:47] + "..."
                
                log.info(f"Generated chat title: '{title}'")
                return title

    except Exception as e:
        log.error(f"Error calling LLM for title generation: {e}")
        return "Untitled Chat" # Fallback title on error

# NEW ACTIVITY: Update Chat Title in Gateway
@activity.defn
async def update_chat_title_activity(
    gateway_api_url: str,
    chat_id: str,
    new_title: str,
    auth_token: str
):
    """Updates the chat title in the Gateway service."""
    activity.heartbeat()
    log.info(f"Updating chat {chat_id} title to '{new_title}' via Gateway.")

    api_url = f"{gateway_api_url}/api/chats/{chat_id}"
    headers = {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    payload = {"title": new_title}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(api_url, json=payload, headers=headers, timeout=10.0) as resp:
                if resp.status == 200:
                    log.info(f"Chat {chat_id} title updated to '{new_title}' successfully.")
                    return True
                else:
                    error_text = await resp.text()
                    log.error(f"Failed to update chat {chat_id} title. Status: {resp.status}, Body: {error_text}")
                    raise Exception(f"API Error {resp.status}: {error_text}")
        except aiohttp.ClientError as e:
            log.error(f"HTTP Client error updating chat title: {e}")
            raise 

# NEW ACTIVITY: Extract Text from File
@activity.defn
async def extract_text_from_file_activity(object_name: str, original_filename: str) -> str:
    """
    Extracts text from files stored in MinIO.
    Supports TXT, PDF, DOCX, and basic DOC files.
    """
    import os
    import io
    from minio import Minio
    from minio.error import S3Error
    from pypdf2 import PdfReader
    from docx import Document as DocxDocument
    
    activity.heartbeat()
    log.info(f"Attempting to extract text from MinIO object: {object_name} (original: {original_filename})")

    # MinIO client setup
    MINIO_ENDPOINT_ACT = os.getenv("MINIO_ENDPOINT", "minio:9000")
    MINIO_ACCESS_KEY_ACT = os.getenv("MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY_ACT = os.getenv("MINIO_SECRET_KEY")
    MINIO_BUCKET_NAME_ACT = os.getenv("MINIO_BUCKET_NAME", "sara-uploads")
    MINIO_SECURE_ACT_STR = os.getenv("MINIO_SECURE", "false").lower()
    MINIO_SECURE_ACT = MINIO_SECURE_ACT_STR == 'true'

    if not MINIO_ACCESS_KEY_ACT or not MINIO_SECRET_KEY_ACT:
        log.error("MinIO client not configured properly. Missing access or secret key.")
        raise Exception("File storage service not configured for text extraction.")

    try:
        minio_client_act = Minio(
            MINIO_ENDPOINT_ACT,
            access_key=MINIO_ACCESS_KEY_ACT,
            secret_key=MINIO_SECRET_KEY_ACT,
            secure=MINIO_SECURE_ACT
        )
        log.info(f"MinIO client for activities initialized: {MINIO_ENDPOINT_ACT}, secure={MINIO_SECURE_ACT}")
    except Exception as e:
        log.error(f"Failed to initialize MinIO client for activities: {e}")
        raise Exception(f"File storage service initialization failed: {e}")

    response = None
    try:
        response = minio_client_act.get_object(MINIO_BUCKET_NAME_ACT, object_name)
        file_content = response.read()
    except S3Error as e:
        log.error(f"MinIO S3Error getting object {object_name}: {e}")
        raise Exception(f"Could not retrieve file from storage: {e.code}")
    finally:
        if response:
            response.close()
            response.release_conn()

    ext = original_filename.split('.')[-1].lower() if '.' in original_filename else ""
    extracted_text = ""

    if ext == "txt":
        try:
            extracted_text = file_content.decode('utf-8', errors='ignore')
        except Exception as e:
            log.error(f"Error decoding TXT file {original_filename}: {e}")
            extracted_text = f"[Error decoding TXT content: {e}]"
    elif ext == "pdf":
        try:
            reader = PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                extracted_text += page.extract_text() + "\n"
        except Exception as e:
            log.error(f"Error extracting text from PDF {original_filename}: {e}")
            extracted_text = f"[Error extracting PDF content: {e}]"
    elif ext == "docx":
        try:
            doc = DocxDocument(io.BytesIO(file_content))
            for para in doc.paragraphs:
                extracted_text += para.text + "\n"
        except Exception as e:
            log.error(f"Error extracting text from DOCX {original_filename}: {e}")
            extracted_text = f"[Error extracting DOCX content: {e}]"
    elif ext == "doc": 
        log.warning(f".doc file ({original_filename}) processing is not fully supported. Attempting plain text decode.")
        try:
            # This is a very basic attempt; proper .doc parsing is complex
            extracted_text = file_content.decode('latin-1', errors='replace')
            extracted_text = f"[Content from .doc file (may be garbled or incomplete):\n{extracted_text}\n]"
        except Exception as e:
            log.error(f"Error decoding .doc file {original_filename} as plain text: {e}")
            extracted_text = "[Could not extract text from .doc file]"
    else:
        log.warning(f"Unsupported file type for text extraction: {ext} (from filename: {original_filename})")
        return f"[File type '{ext}' not supported for text extraction]"

    if not extracted_text.strip():
        log.warning(f"No text could be extracted from {original_filename} (type: {ext}). It might be empty or an image-based file.")
        extracted_text = "[No text content found in file]"

    log.info(f"Extracted text from {original_filename} (first 100 chars): {extracted_text[:100].replace('\n', ' ')}...")
    return extracted_text

