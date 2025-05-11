from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
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
    n = req.top_n or MEMORY_TOP_N
    
    # Try semantic search with embeddings first
    try:
        embed = await compute_embedding(req.query)
        
        stmt = (
            select(Memory.text)
            .where(Memory.room_id == req.room_id, Memory.type == "summary")
            .order_by(Memory.embedding.op("<->")(embed))
            .limit(n)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [MemorySummary(text=row) for row in rows]
    
    except Exception as e:
        # If embedding fails, fall back to latest entries
        import logging
        logging.warning(f"Embedding error in memory_query: {e}. Falling back to latest entries.")
        
        # Fallback: just return the most recent summaries
        stmt = (
            select(Memory.text)
            .where(Memory.room_id == req.room_id, Memory.type == "summary")
            .order_by(desc(Memory.created_at))
            .limit(n)
        )
        
        try:
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [MemorySummary(text=row) for row in rows]
        except Exception as fallback_error:
            logging.error(f"Fallback query also failed: {fallback_error}")
            return [] 