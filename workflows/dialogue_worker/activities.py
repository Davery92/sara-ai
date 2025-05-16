import json
import logging
import aiohttp
import uuid # For document IDs if not passed

from temporalio import activity
from services.common.nats_helpers import NatsClient # Assuming you have a NatsClient class

# Placeholder for actual NatsClient initialization if needed globally for activities,
# or it can be instantiated per call / passed if worker context provides it.
# For simplicity, activities might take NATS config/subjects as params.

log = logging.getLogger(__name__)

# Configuration (ideally from workflow inputs or env)
# GATEWAY_API_URL_BASE = "http://gateway:8000" # Example

@activity.defn
async def enhance_prompt_activity(
    current_messages: list[dict], 
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
    log.info(f"Enhancing prompt for user_id: {user_id}, room_id: {room_id}")

    user_input_msg = ""
    if current_messages and current_messages[-1]["role"] == "user":
        user_input_msg = current_messages[-1]["content"]

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
    if user_input_msg and room_id:
        try:
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{gateway_api_url}/v1/memory/query",
                    json={"query": user_input_msg, "room_id": room_id, "top_n": memory_top_n},
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
    
    # Check if a system prompt already exists and update it, or insert one.
    # Ensure it's the first message.
    updated_messages = [msg for msg in current_messages if msg["role"] != "system"]
    updated_messages.insert(0, {"role": "system", "content": system_prompt_content})
    
    log.debug(f"Enhanced messages: {json.dumps(updated_messages, indent=2)}")
    return updated_messages


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
    nc = None
    try:
        # This assumes NatsClient handles connection and is async context managed
        # or provides simple connect/publish/close methods.
        # For a single publish, a new connection might be acceptable for simplicity in an activity.
        async with NatsClient() as nats_client_instance: # NatsClient from services.common.nats_helpers
             await nats_client_instance.connect([nats_url] if isinstance(nats_url, str) else nats_url)
             await nats_client_instance.conn.publish(subject, json.dumps(payload).encode(), headers=headers)
             log.info(f"Successfully published to {subject}")
    except Exception as e:
        log.error(f"Failed to publish to NATS subject '{subject}': {e}")
        # Decide if this should raise an error to fail the activity
        raise


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