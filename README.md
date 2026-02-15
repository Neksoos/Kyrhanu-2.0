# Прокляті Кургани 2.0 (Telegram Mini App + Web)

## Local dev (monorepo)
### 1) Backend
cd apps/api
cp .env.example .env
npm i
npm run db:migrate
npm run dev

### 2) Frontend
cd apps/web
cp .env.example .env.local
npm i
npm run dev

## Railway deploy
- API service root: apps/api
- WEB service root: apps/web
- Set ENV vars from .env.example files.
