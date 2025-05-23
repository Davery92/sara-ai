# services/gateway/app/ws_metrics.py
import time, uuid
from prometheus_client import Histogram, Counter, Gauge

WS_SEND_SECONDS = Histogram(
    "gw_ws_send_seconds",
    "Time to ws.send_text",
    ["status", "path"],
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1, 2)
)
WS_OPEN = Gauge("gw_ws_open", "Open WS conns")

async def safe_send(ws, data, path):
    start = time.perf_counter()
    try:
        await ws.send_text(data)
        WS_SEND_SECONDS.labels("ok", path).observe(time.perf_counter() - start)
    except Exception:
        WS_SEND_SECONDS.labels("err", path).observe(time.perf_counter() - start)
        raise
