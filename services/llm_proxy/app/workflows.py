from temporalio import workflow
from datetime import timedelta
from typing import List
from .activity import call_ollama

@workflow.defn(name="LLMWorkflow")
class ChatWorkflow:
    @workflow.run
    async def run(self, model: str, prompt: str, stream: bool) -> List[str]:
        return await workflow.execute_activity(
            call_ollama,
            args=[model, prompt, stream],    # <<< IMPORTANT
            start_to_close_timeout=timedelta(minutes=2),
        )
