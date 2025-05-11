from temporalio import workflow
from datetime import timedelta
from typing import List
from .activity import call_ollama

@workflow.defn(name="LLMWorkflow")
class ChatWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> List[str]:
        model = payload.get("model", "default")
        prompt = payload.get("msg") or payload.get("prompt", "")
        stream = payload.get("stream", False)

        return await workflow.execute_activity(
            call_ollama,
            args=[model, prompt, stream],
            start_to_close_timeout=timedelta(minutes=2),
        )



