from temporalio import workflow
from datetime import timedelta

@workflow.defn
class MemoryRollupWorkflow:
    @workflow.run
    async def run(self) -> None:
        user_ids_to_process = await workflow.execute_activity(
            "list_rooms_with_hot_buffer",
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        if user_ids_to_process:
            await workflow.execute_activity(
                "process_rooms", args=[user_ids_to_process],
                schedule_to_close_timeout=timedelta(minutes=5),
            )
