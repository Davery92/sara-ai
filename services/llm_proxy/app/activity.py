from temporalio import activity
import aiohttp
import os
import json
import logging

log = logging.getLogger("llm_proxy.activity")

@activity.defn
async def call_ollama(model: str, prompt, stream: bool) -> list[str]:
    """
    Activity that streams from Ollama's chat API and collects chunks.
    
    Args:
        model: Model name to use with Ollama
        prompt: Either a string prompt or a messages array format
        stream: Whether to stream the response
    """
    url = os.getenv("OLLAMA_URL", "http://100.104.68.115:11434")
    results: list[str] = []
    
    # Construct the request payload for chat API
    if isinstance(prompt, list):
        # We received a messages array format
        log.info(f"Using messages format with Ollama API: {len(prompt)} messages")
        payload = {
            "model": model,
            "messages": prompt,  # Use the messages as provided
            "stream": stream
        }
    else:
        # We received a single string prompt
        log.info(f"Using single prompt format with Ollama API: {prompt[:50]}...")
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream
        }
    
    log.info(f"Calling Ollama API at {url}/api/chat")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{url}/api/chat", json=payload) as response:
            if response.status != 200:
                error_text = await response.text()
                log.error(f"Ollama API error: {response.status} - {error_text[:200]}")
                return [f"Error: {response.status} from Ollama API"]
                
            if stream:
                async for line in response.content:
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            # Extract content from message if it exists
                            if 'message' in data and 'content' in data['message']:
                                results.append(data['message']['content'])
                        except json.JSONDecodeError:
                            # If it's not JSON, append the raw line
                            results.append(line.decode('utf-8'))
            else:
                data = await response.json()
                if 'message' in data and 'content' in data['message']:
                    results.append(data['message']['content'])
    
    return results