FROM python:3.12-slim

# Оптимальні змінні середовища
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Копіюємо requirements і встановлюємо залежності
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь код
COPY . .

# Щоб Python бачив локальні імпорти (routers, services і т.д.)
ENV PYTHONPATH=/app

# Which ASGI app to run.
# - app.main:app (2.0 API with JWT + runs/shop/inventory)  ✅ default
# - main:app (legacy game API with Telegram cookie sessions)
#
# Railway / Docker can override this env var when needed.
ENV APP_MODULE=app.main:app

# Запуск: слухаємо PORT від Railway (fallback 8080 локально)
CMD ["sh", "-c", "uvicorn ${APP_MODULE} --host 0.0.0.0 --port ${PORT:-8080}"]