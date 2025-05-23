from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
# FIX: Changed 'Message' to 'EmbeddingMessage'
from ..db.models import EmbeddingMessage
from ..db.session import get_session
from ..utils.embeddings import compute_embedding

router = APIRouter()

@router.get("/v1/search", tags=["search"])
async def semantic_search(
    q: str = Query(..., min_length=1),
    k: int = Query(5, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    # 1) Turn the query into a vector
    try:
        q_vec = await compute_embedding(q)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")

    # 2) Nearest-neighbor lookup using pgvector <-> operator
    # FIX: Changed 'Message' to 'EmbeddingMessage'
    stmt = (
        select(EmbeddingMessage.id, EmbeddingMessage.text)
        .order_by(EmbeddingMessage.embedding.op("<->")(q_vec))
        .limit(k)
    )
    result = await session.execute(stmt)
    rows = result.all()

    return [{"id": r.id, "text": r.text} for r in rows]