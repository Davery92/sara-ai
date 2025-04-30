FROM python:3.12-slim
WORKDIR /app

COPY services/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the gateway app code
COPY services/gateway/app ./app

# Copy our shared NATS helpers so `services.common` exists
COPY services/common ./services/common

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
