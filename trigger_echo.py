# trigger_echo.py
import asyncio
from temporalio.client import Client
from services.dialogue_worker.main import EchoWorkflow

async def main():
    # 1) connect to your local Temporal server
    client = await Client.connect("localhost:7233")

    # 2) start and await the EchoWorkflow
    result = await client.execute_workflow(
        EchoWorkflow.run,           # workflow entrypoint
        "hello temporal",           # arg
        id="echo-workflow-1",       # unique run ID
        task_queue="echo-queue",    # where your worker is listening
    )
    print("Got workflow result:", result)

if __name__ == "__main__":
    asyncio.run(main())
