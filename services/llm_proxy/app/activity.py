from temporalio import activity
import aiohttp
import os
import json

@activity.defn
async def call_ollama(model: str, prompt: str, stream: bool) -> list[str]:
    """
    Activity that streams from Ollama's chat API and collects chunks.
    """
    url = os.getenv("OLLAMA_URL", "http://100.104.68.115:11434")
    results: list[str] = []
    
    # Construct the request payload for chat API
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{url}/api/chat", json=payload) as response:
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