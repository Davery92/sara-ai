# services/gateway/app/routes/messages.py

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
    return MessageOut(status="queued", text=payload.text)
