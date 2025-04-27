# services/llm_proxy/Dockerfile

# 1. Pick a lightweight Python base
FROM python:3.12-slim

# 2. Ensure logs are output promptly
ENV PYTHONUNBUFFERED=1

# 3. Set our working directory
WORKDIR /app

# 4. Install build tools and your dependencies
#    First copy just the files that list your deps so this step is cached
COPY pyproject.toml .
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .  

# 5. Now copy in the rest of your code
COPY . .

# 6. Tell Docker which port your app listens on
EXPOSE 8000

# 7. Finally, launch Uvicorn pointing at your app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]