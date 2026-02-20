# Kyhranu Backend (FastAPI)

## Запуск локально
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Альтернативний entrypoint (2.0 API)
Якщо ти деплоїш гілку з `/runs`, `/shop`, `/inventory` (JWT + refresh cookie), запускай:
```bash
uvicorn app.main:app --reload --port 8000
```

У Docker/Railway можна просто виставити змінну:
`APP_MODULE=app.main:app`

Потрібно налаштувати `DATABASE_URL` у `.env` (див. `.env.example`).
