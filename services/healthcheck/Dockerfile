FROM python:3.12-slim
RUN pip install --no-cache-dir redis psycopg2-binary nats-py
COPY scripts/health_check.py /opt/health_check.py
CMD ["python", "/opt/health_check.py"]

