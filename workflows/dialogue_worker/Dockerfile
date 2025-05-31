FROM python:3.12-slim

WORKDIR /app

# Copy the entire project
COPY . .

# Install Python dependencies from root pyproject.toml
# This includes temporalio, aiohttp, minio, pypdf2, python-docx, nats-py
RUN pip install .

# Set Python path to include the project root
ENV PYTHONPATH=/app

CMD ["python", "workflows/dialogue_worker/worker.py"] 