FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# ✅ ВАЖЛИВО: копіюємо і app, і routers, і root main.py (якщо треба)
COPY app /app/app
COPY routers /app/routers
COPY main.py /app/main.py

EXPOSE 8000

# ✅ Railway дає PORT змінною, тому беремо його
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]