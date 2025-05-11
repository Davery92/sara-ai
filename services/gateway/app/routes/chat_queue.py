from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..deps.auth import get_jwt_token          # already exists
from ..nats_utils import publish_chat          # we added this helper
from ..deps.nats import get_js  
from uuid import uuid4               # whatever you use now
import json, time
from ..redis_client import get_redis 
from ..utils.save_chat_chunk import save_chat_chunk

router = APIRouter(tags=["chat"])

class ChatRequest(BaseModel):
    room_id: str
    msg: str

@router.post("/chat/queue")
async def enqueue_chat(req: ChatRequest,
                       jwt_token: str = Depends(get_jwt_token),
                       js = Depends(get_js)):

    # Save the user's message to Redis and Postgres
    await save_chat_chunk(req.room_id, "user", req.msg)

    # Publish it to NATS for processing
    subj = f"chat.request.{req.room_id}"
    ack_subj = f"ack.{uuid4()}"
    headers = {
        "Auth": jwt_token,
        "Ack":  ack_subj,
    }
    await js.publish(subj, req.json().encode(), headers=headers)
    return {"queued": True, "ack_subject": ack_subj}