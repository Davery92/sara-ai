from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..deps.auth import get_jwt_token          # already exists
from ..nats_utils import publish_chat          # we added this helper
from ..deps.nats import get_js                 # whatever you use now

router = APIRouter(prefix="/v1", tags=["chat"])

class ChatRequest(BaseModel):
    room_id: str
    msg: str

@router.post("/chat/queue")
async def enqueue_chat(req: ChatRequest,
                       jwt_token: str = Depends(get_jwt_token),
                       js = Depends(get_js)):
    subj = f"chat.request.{req.room_id}"
    await publish_chat(js, subj, req.json().encode(), jwt_token)
    return {"queued": True}
