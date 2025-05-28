FROM python:3.12-slim

WORKDIR /app

# Copy the entire project
COPY . .

# Install Python dependencies
# First install any pyproject.toml if it exists at the root
RUN if [ -f pyproject.toml ]; then pip install .; fi

# Install dialogue worker specific requirements
RUN if [ -f services/dialogue_worker/requirements.txt ]; then pip install -r services/dialogue_worker/requirements.txt; fi

# Install any additional requirements for temporal/workflow dependencies
RUN pip install temporalio

# Set Python path to include the project root
ENV PYTHONPATH=/app

CMD ["python", "workflows/dialogue_worker/worker.py"] 