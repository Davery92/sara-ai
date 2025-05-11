FROM python:3.12-slim
WORKDIR /app

# Set Python path to include the project root
ENV PYTHONPATH=/app:$PYTHONPATH

# ── worker's own code ─────────────────────────────
COPY workflows/memory_worker/pyproject.toml .
COPY workflows/memory_worker/activities.py .
COPY workflows/memory_worker/workflow.py .
COPY workflows/memory_worker/worker.py .
COPY workflows/memory_worker/redis_client.py .

# ── copy ALL gateway helpers (redis_client, db/, models/, etc.) ──
COPY services/gateway ./services/gateway
# if you still need common helpers:
COPY services/common   ./services/common

# Install additional dependencies
RUN pip install --no-cache-dir . PyYAML bcrypt>=4.0.1 redis

CMD ["python", "-m", "worker"]
