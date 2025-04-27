from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ..db.session import get_session
from ..db.models import Message

router = APIRouter(prefix="/messages")

@router.post("/", status_code=201)
async def create_message(
    payload: dict,
    session: AsyncSession = Depends(get_session)
):
    text = payload.get("text")
    if not text:
        raise HTTPException(400, "Missing `text` field")
    msg = Message(text=text)
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    return {"id": msg.id, "text": msg.text, "created_at": msg.created_at}
