import asyncio
from datetime import timedelta
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from nats.aio.client import Client as NATS

# — Activity
@activity.defn
async def echo_activity(msg: str) -> str:
    return f"pong 🏓: {msg}"

# — Workflow
@workflow.defn
class EchoWorkflow:
    @workflow.run
    async def run(self, message: str) -> str:
        return await workflow.execute_activity(
            echo_activity,
            message,
            # correct timeout parameter name:
            start_to_close_timeout=timedelta(seconds=5)
        )

async def main():
    # connect to NATS (optional: to subscribe to requests)
    nc = NATS()
    await nc.connect(servers=["nats://nats:4222"])
    # connect to Temporal
    client = await Client.connect("temporal:7233")
    # run the worker
    async with Worker(
        client,
        task_queue="echo-queue",
        workflows=[EchoWorkflow],
        activities=[echo_activity]
    ):
        print("Worker listening on 'echo-queue'…")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())
