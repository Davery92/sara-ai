# services/gateway/app/metrics.py
from prometheus_client import Counter, Histogram

WS_LATENCY  = Histogram("gw_ws_send_seconds", "WS send latency", ["path"])
TOKENS_OUT  = Counter("gw_tokens_out_total", "Tokens streamed", ["model"])
CLIENT_DROPS = Counter("gw_client_disconnect_total", "Disconnected mid-stream")

# mount the /metrics endpoint once
from prometheus_client import make_asgi_app
app.mount("/metrics", make_asgi_app())
