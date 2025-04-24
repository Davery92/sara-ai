import uvicorn
from fastapi import FastAPI
from .api import router
from .dependencies import get_settings

settings = get_settings()
app = FastAPI(title="Sara Gateway", version="0.1.0")

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
