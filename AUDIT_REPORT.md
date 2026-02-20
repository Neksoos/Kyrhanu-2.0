# Kyrhanu — Production Audit Report (Frontend + Backend)

Date: 2026-02-20

## 0) Repo reality check (RISK)
The uploaded **backend** is **Python FastAPI + asyncpg + raw SQL migrations**, not Node.js/Nest/Fastify. I did **not** rewrite the stack (that would be a rewrite project). All fixes below are applied to what реально є в архівах.

## 1) Executive summary
### P0 (blocks auth / security)
1. **Insecure auth by `tg_id`** (query/header) without verifying Telegram signatures → anyone could impersonate users.
2. **Mini App “не бачить користувача”**: initData was not consistently validated + no stable session → intermittent 401/409 loop.
3. **No browser Telegram Login Widget flow** (signature verify + unified session) → browser users couldn’t login safely.
4. **Migrations re-applied on every start** (non-idempotent SQL) → breakage risk / data corruption.

### P1 (high impact)
1. No clear **linking** flow (email/password → later link Telegram id) for unified account.
2. Cookie/session handling was not robust / was mixing approaches.

### P2 (cleanup/maintainability)
1. Dead / legacy auth artifacts and code paths.
2. Potentially obsolete DB tables from older iterations.

## 2) What I changed (implemented)
### 2.1 Unified auth: Mini App + Browser → ONE account
**Backend** now supports:
- **Telegram Mini App**: validates `X-Init-Data` (HMAC, auth_date), extracts `user.id`.
- **Browser Login Widget**: validates `hash` payload.
- **One account rule**: `telegram_id` is the canonical Telegram user id. We map it to an internal `players.tg_id`.
- **Linking**: user can create an email/password account first, then link Telegram (unique constraint prevents linking same telegram to multiple accounts).

Implemented in:
- `core/tg_auth.py` — robust verification for both flows.
- `core/session.py` — Redis-backed httpOnly cookie sessions.
- `routers/auth.py` — `/api/auth/verify`, `/api/auth/login-widget`, `/api/auth/register-password`, `/api/auth/login-password`, `/api/auth/link-telegram`.
- `main.py` — middleware sets `request.state.tg_id` from session cookie OR verified initData.

### 2.2 Fix: “Mini App не бачить користувача”
Root cause: frontend/backend used different assumptions about identity; Mini App calls were sometimes made without signature validation and session.

Fix:
- Backend middleware validates initData and resolves player → sets cookie session automatically.
- Frontend checks `/api/auth/verify` first; on `409 NEED_REGISTER` redirects to `/register`.

### 2.3 Migration safety
- Added a `schema_migrations` table and changed `run_migrations()` to **apply each migration only once**.

Implemented in:
- `db.py` — `run_migrations()` tracks applied files.

### 2.4 Minimal DB schema extension (safe, additive)
`ensure_min_schema()` now ensures these columns exist:
- `players.id BIGSERIAL UNIQUE` (internal surrogate id)
- `players.telegram_id BIGINT UNIQUE` (canonical Telegram user id)
- `players.login TEXT UNIQUE (case-insensitive)`
- `players.password_hash TEXT` (PBKDF2)

This is **additive** and should not break existing rows.

## 3) Frontend audit notes (Next.js)
### Current auth flow
- All API calls go through `app/api/proxy/[...path]/route.ts` so that **cookies stay same-origin**.
- `src/lib/api.ts` automatically attaches `X-Init-Data` in Mini App and always uses `credentials: 'include'`.
- `app/_components/RootClientShell.tsx` enforces:
  - `POST /api/auth/verify` → ok
  - `409 NEED_REGISTER` → `/register`
  - `401` → `/login`

### Browser login widget
- `app/login/page.tsx` renders Telegram Login Widget dynamically and calls `/api/auth/login-widget`.
- If backend returns `409 NEED_REGISTER`, payload is stored in `sessionStorage` and `/register` completes the registration.

## 4) Backend audit notes (FastAPI)
### Auth model
- Middleware sets `request.state.tg_id`.
- Legacy `tg_id` query params are tolerated, but **must match** authenticated user (guard in middleware).

### Security checklist
- ✅ Telegram Mini App initData signature verification.
- ✅ Telegram Login Widget hash verification.
- ✅ httpOnly session cookies stored in Redis.
- ⚠️ Rate-limiting is not present (recommend add a simple per-IP limiter for auth endpoints).
- ⚠️ Cookie settings depend on deployment:
  - Telegram webview often works with `SameSite=Lax`, but if you embed cross-site flows you may need `SameSite=None; Secure`.

## 5) DB findings and cleanup candidates
### Confirmed obsolete candidate
- **`item_equipment_stats`** — referenced in migration comments as "старий експеримент" and not used in code.

### Likely obsolete but needs verification (RISK)
- **`zastavy`** — current code seems to use `forts/*` tables, and no SQL queries target `zastavy`. Might be leftover from earlier "застави" iteration.

### UNKNOWN (don’t drop blindly)
- **`forum_category_requests`** — exists in migrations and an unused helper (`services/forum/migrations.py`), but not used by forum router yet.

A cleanup SQL script is provided (see `DB_CLEANUP_CANDIDATES.sql`).

## 6) Key files changed
Backend:
- `main.py`
- `db.py`
- `core/tg_auth.py`
- `core/session.py`
- `routers/auth.py`

Frontend:
- `app/api/proxy/[...path]/route.ts`
- `src/lib/api.ts`
- `app/_components/RootClientShell.tsx`
- `app/login/page.tsx`
- `app/register/page.tsx`
- `.env.example`

## 7) Run commands
### Backend
```bash
cd Kyrhanu-backend-main
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# env (example)
export DATABASE_URL='postgresql://user:pass@host:5432/db'
export REDIS_URL='redis://default:pass@host:6379'
export TELEGRAM_BOT_TOKEN='123:ABC...'   # token for the bot used by Mini App + Login Widget
export BOT_USERNAME='Kyrganubot'         # without @ (prod). For dev: kyrganuosnova_bot
export FRONTEND_ORIGIN='http://localhost:3000'

uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### Frontend
```bash
cd Kyrhanu-frontend-main
npm i

cp .env.example .env.local
# set API_BASE to your backend base URL

npm run dev
```

## 8) Recommended next steps
- Gradually remove `tg_id` from query/body and move routers to `Depends(get_tg_id)`.
- Add rate-limit for `/api/auth/*` endpoints.
- Add a proper DB migration for the new auth columns (so you can eventually remove parts of `ensure_min_schema()`).
