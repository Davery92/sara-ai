#!/usr/bin/env python3
"""
Manual test script for the memory worker workflow.
This script manually triggers the memory processing workflow to test it immediately.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

from temporalio.client import Client
from workflows.memory_worker.workflow import MemoryRollupWorkflow

async def test_memory_worker():
    """Manually trigger the memory worker workflow for testing."""
    print("🧪 Testing Memory Worker Workflow...")
    print("=" * 50)
    
    try:
        # Connect to Temporal
        print("📡 Connecting to Temporal...")
        client = await Client.connect("temporal:7233")
        print("✅ Connected to Temporal")
        
        # Execute the workflow directly
        print("🚀 Starting memory rollup workflow...")
        result = await client.execute_workflow(
            MemoryRollupWorkflow.run,
            id=f"memory-rollup-test-{int(asyncio.get_event_loop().time())}",
            task_queue="memory-rollup",
        )
        
        print(f"✅ Workflow completed successfully!")
        print(f"📊 Result: {result}")
        
    except Exception as e:
        print(f"❌ Error running workflow: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_memory_worker())
    if success:
        print("\n🎉 Memory worker test completed successfully!")
    else:
        print("\n💥 Memory worker test failed!")
        sys.exit(1) 