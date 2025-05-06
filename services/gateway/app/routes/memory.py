from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os
from ..db.models import Memory
from ..db.session import get_session
from ..utils.embeddings import compute_embedding

router = APIRouter()

MEMORY_TOP_N = int(os.getenv("MEMORY_TOP_N", 5))

class QueryReq(BaseModel):
    query: str = Field(..., description="Query text to search for relevant memories.")
    room_id: str = Field(..., description="Room ID to scope the memory search.")
    top_n: int = Field(None, description="Number of top results to return (optional, overrides env var)")

class MemorySummary(BaseModel):
    text: str

@router.post("/v1/memory/query", response_model=list[MemorySummary], tags=["memory"], summary="Query top-N memory summaries by semantic similarity.")
async def memory_query(req: QueryReq, session: AsyncSession = Depends(get_session)):
    """Returns the top-N most relevant memory summaries for a given query and room."""
    try:
        embed = await compute_embedding(req.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")

    n = req.top_n or MEMORY_TOP_N
    stmt = (
        select(Memory.text)
        .where(Memory.room_id == req.room_id, Memory.type == "summary")
        .order_by(Memory.embedding.op("<->")(embed))
        .limit(n)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [MemorySummary(text=row) for row in rows] 