FROM python:3.12-slim
WORKDIR /app

# ── worker’s own code ─────────────────────────────
COPY workflows/memory_worker/pyproject.toml .
COPY workflows/memory_worker/activities.py .
COPY workflows/memory_worker/workflow.py .
COPY workflows/memory_worker/worker.py .

# ── copy ALL gateway helpers (redis_client, db/, models/, etc.) ──
COPY services/gateway ./services/gateway
# if you still need common helpers:
COPY services/common   ./services/common

RUN pip install --no-cache-dir .

CMD ["python", "-m", "worker"]
