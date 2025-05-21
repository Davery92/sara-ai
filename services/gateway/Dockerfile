FROM python:3.12-slim
WORKDIR /app

# Set Python path to include the project root
ENV PYTHONPATH=/app:$PYTHONPATH

COPY services/gateway/requirements.txt .
# Install dependencies including PyYAML
RUN pip install --no-cache-dir -r requirements.txt PyYAML httpx websockets

COPY services/gateway/alembic.ini /app/alembic.ini
COPY services/gateway/alembic /app/alembic

# Copy the gateway app code
COPY services/gateway/app ./app
COPY services/gateway/__init__.py ./services/gateway/
COPY services/gateway/main.py ./services/gateway/

# Copy our shared NATS helpers so `services.common` exists
COPY services/common ./services/common

# Create personalities directory and copy persona files
RUN mkdir -p /app/configs/personalities
COPY configs/personalities/*.md /app/configs/personalities/

# Use the correct module path to run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
