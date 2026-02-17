FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# deps for building wheels (bcrypt/asyncpg) on slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential gcc curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy code (your package name is "app")
COPY app /app/app

EXPOSE 8000

# NOTE: use --proxy-headers if behind reverse proxy
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]