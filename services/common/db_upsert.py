from sqlalchemy.dialects.postgresql import insert
import importlib

# Try different import paths based on environment
try:
    # First try the direct app import (for Docker)
    from app.db.models import Memory
except ImportError:
    try:
        # Then try local project structure (for development)
        from services.gateway.app.db.models import Memory
    except ImportError:
        # If both fail, postpone import until runtime
        Memory = None
        
        def _get_memory_model():
            global Memory
            if Memory is None:
                try:
                    # Try to dynamically import at runtime
                    gateway_models = importlib.import_module("app.db.models")
                    Memory = gateway_models.Memory
                except ImportError:
                    gateway_models = importlib.import_module("services.gateway.app.db.models")
                    Memory = gateway_models.Memory
            return Memory

async def upsert_memory(
    session,
    *,
    mem_id,
    room_id,
    text,
    embedding,
    msg_type="raw",
):
    # Get Memory model dynamically if not imported directly
    mem_model = Memory if Memory is not None else _get_memory_model()
    
    stmt = (
        insert(mem_model)
        .values(
            id=mem_id,
            room_id=room_id,
            text=text,
            embedding=embedding,
            type=msg_type,
        )
        .on_conflict_do_update(
            index_elements=[mem_model.id],
            set_={
                "text": text,
                "embedding": embedding,
                "type": msg_type,
            },
        )
    )
    await session.execute(stmt)
