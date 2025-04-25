# services/gateway/main.py
# Thin compatibility shim — points old import path at the new one
from services.gateway.app.main import app   # noqa: F401
