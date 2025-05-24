from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(prefix="/messages", tags=["messages"])

class MessageIn(BaseModel):
    text: str

class MessageOut(BaseModel):
    status: str
    text: str

@router.post("/", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def create_message(payload: MessageIn):
    # This route is currently a stub for the original /messages endpoint.
    # The actual message persistence is now handled by the WebSocket stream.
    # If you need to implement direct HTTP message creation for other purposes,
    # you'd use the `crud.save_chat_message` function here similar to `chats.py`.
    return MessageOut(status="queued", text=payload.text)