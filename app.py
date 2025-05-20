# app.py  – makes  “from app import app”  work for tests
from services.gateway.app.main import app  # noqa: F401
