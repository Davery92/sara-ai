import asyncio
import json
import websockets

async def test_websocket():
    uri = "ws://localhost:8000/v1/stream?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkYXZpZCIsInR5cGUiOiJhY2Nlc3MiLCJqdGkiOiI2YjA2YjI3ZC00YzlhLTRiNDEtODUzNy02NjFkYTkyYjEyNWMiLCJpYXQiOjE3NDY4Nzk2MTIuNzAyOTM5NywiZXhwIjoxNzQ3NDg0NDEyLjcwMjkzOTd9.O60mqalaNOrELTV9lq52KO6O2bc2TaCZS1SkWK-z7R0"
    
    payload = {
        "model": "llama2",
        "messages": [
            {"role": "user", "content": "Hello, how are you today?"}
        ]
    }
    
    print(f"Connecting to {uri}")
    async with websockets.connect(uri) as websocket:
        print("Connected, sending payload...")
        await websocket.send(json.dumps(payload))
        
        print("Waiting for response...")
        while True:
            try:
                response = await websocket.recv()
                print(f"Received: {response}")
            except websockets.exceptions.ConnectionClosed:
                print("Connection closed")
                break

if __name__ == "__main__":
    asyncio.run(test_websocket()) 