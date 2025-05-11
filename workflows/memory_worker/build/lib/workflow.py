from temporalio import workflow
from datetime import timedelta

@workflow.defn
class MemoryRollupWorkflow:
    @workflow.run
    async def run(self) -> None:
        rooms = await workflow.execute_activity(
            "list_rooms_with_hot_buffer",
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        await workflow.await_all([self.process_room(r) for r in rooms])

    async def process_room(self, room_id: str):
        chunks = await workflow.execute_activity(
            "fetch_buffer", room_id,
            schedule_to_close_timeout=timedelta(seconds=30),
        )
        if not chunks:
            return

        summary, embedding = await workflow.gather(
            workflow.execute_activity(
                "summarise_texts", chunks,
                schedule_to_close_timeout=timedelta(minutes=2),
            ),
            workflow.execute_activity(
                "embed_text",
                "\n".join(c["text"] for c in chunks),
                schedule_to_close_timeout=timedelta(seconds=30),
            ),
        )

        await workflow.execute_activity(
            "upsert_summary", room_id, summary, embedding,
            schedule_to_close_timeout=timedelta(seconds=30),
        )
