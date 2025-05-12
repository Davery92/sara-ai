from temporalio import activity
import aiohttp, os, json, logging, asyncio

log = logging.getLogger("llm_proxy.activity")

OPENAI_PATH = "/v1/chat/completions"          # ← new endpoint

@activity.defn
async def call_ollama(model: str, prompt, stream: bool = True) -> list[str]:
    """
    Streams from Ollama’s OpenAI-compatible endpoint and returns the raw text
    that an end-user would see (no JSON re-encoding).
    """
    base = os.getenv("OLLAMA_URL", "http://100.104.68.115:11434")
    url  = f"{base}{OPENAI_PATH}"

    # ----- build the OpenAI-style request body ----------------------------
    if isinstance(prompt, list):               # already a messages array
        payload = {"model": model, "messages": prompt, "stream": stream}
        log.info("messages-format prompt (%d messages)", len(prompt))
    else:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": stream,
        }
        log.info("single prompt: %.50s …", prompt)

    # ----- call Ollama ----------------------------------------------------
    results: list[str] = []
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                log.error("Ollama error %s → %.200s", resp.status, text)
                return [f"Error {resp.status}: {text[:120]}"]

            if not stream:                     # non-streaming = one JSON blob
                data    = await resp.json()
                content = (
                    data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content")
                )
                if content:
                    results.append(content)
                return results

            # -------- streaming branch ------------------------------------
            async for raw in resp.aiter_raw():     # raw SSE bytes
                for line in raw.split(b"\n"):
                    if not line or not line.startswith(b"data: "):
                        continue

                    payload = line.removeprefix(b"data: ").strip()
                    if payload == b"[DONE]":       # end-of-stream marker
                        return results

                    try:
                        chunk = json.loads(payload.decode())
                        delta = (
                            chunk.get("choices", [{}])[0]
                                 .get("delta", {})
                                 .get("content")
                        )
                        if delta is not None:
                            results.append(delta)
                    except json.JSONDecodeError:
                        # fall back to literal text
                        results.append(payload.decode(errors="ignore"))

    return results
