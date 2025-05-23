from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, cast
from sqlalchemy.dialects import postgresql
import os
from ..db.models import Memory 
from ..db.session import get_session
from ..utils.embeddings import compute_embedding
from pgvector.sqlalchemy import Vector
import logging
log = logging.getLogger("gateway.memory")
router = APIRouter()

MEMORY_TOP_N = int(os.getenv("MEMORY_TOP_N", 10))

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
    
    try:
        embed = await compute_embedding(req.query)
        
        log.debug(f"Type of embed: {type(embed)}, first element: {type(embed[0]) if embed and len(embed) > 0 else 'N/A'}")

        stmt = (
            select(Memory.text)
            .where(Memory.room_id == req.room_id, Memory.type == "summary")
            .order_by(Memory.embedding.op("<->")(
                cast(embed, Vector(len(embed)))
            ))
            .limit(n)
        )
        
        log.info(f"Attempting semantic search query for room_id: {req.room_id}")
        result = await session.execute(stmt)
        rows = result.scalars().all()
        log.info(f"Semantic search successful. Found {len(rows)} memories.")
        return [MemorySummary(text=row) for row in rows]
    
    except Exception as e:
        log.warning(f"Embedding error in memory_query: {e}. Falling back to latest entries.")
        
        stmt = (
            select(Memory.text)
            .where(Memory.room_id == req.room_id, Memory.type == "summary")
            .order_by(desc(Memory.created_at))
            .limit(n)
        )
        
        try:
            result = await session.execute(stmt)
            rows = result.scalars().all()
            log.info(f"Fallback query successful. Found {len(rows)} memories.")
            return [MemorySummary(text=row) for row in rows]
        except Exception as fallback_error:
            log.error(f"Fallback query also failed: {fallback_error}")
            raise HTTPException(status_code=500, detail=f"Failed to query memories: {e}") 