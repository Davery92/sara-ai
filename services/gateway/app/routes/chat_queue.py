from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..deps.auth import get_jwt_token          # already exists
from ..nats_utils import publish_chat          # we added this helper
from ..deps.nats import get_js  
from uuid import uuid4               # whatever you use now
import json, time
from ..redis_client import get_redis 
from ..utils.save_chat_chunk import save_chat_chunk
import jwt
from ..auth import _SECRET, _ALG

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

    # Parse JWT token to get user_id
    try:
        jwt_payload = jwt.decode(jwt_token, _SECRET, algorithms=[_ALG])
        user_id = jwt_payload.get("sub", "")
    except Exception as e:
        # If token decoding fails, use empty user_id
        user_id = ""
        
    # Create payload with user_id
    payload = req.dict()
    payload["user_id"] = user_id

    # Publish it to NATS for processing
    subj = f"chat.request.{req.room_id}"
    ack_subj = f"ack.{uuid4()}"
    reply_subj = f"resp.{uuid4()}"  

    headers = {
        "Auth":  jwt_token,
        "Ack":   ack_subj,
        "Reply": reply_subj,              # 🆕
    }
    await js.publish(subj, json.dumps(payload).encode(), headers=headers)
    return {
        "queued": True,
        "ack_subject":   ack_subj,
        "reply_subject": reply_subj       # let the caller know where to listen
    }