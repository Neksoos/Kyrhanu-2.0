# Kyrhanu — Cleanup & Migration Plan

Date: 2026-02-20

This plan is conservative ("обережно"). Anything destructive is staged behind verification steps.

## 1) Preconditions (before any cleanup)
1. Take a DB backup:
   - `pg_dump --format=custom --no-owner --no-acl -f backup.dump $DATABASE_URL`
2. Confirm current app version is deployed and stable.
3. Make sure you can rollback (keep previous Railway deploy, and keep the DB backup).

## 2) Auth rollout plan (safe)
### 2.1 Environment variables
Backend:
- `TELEGRAM_BOT_TOKEN` — token for the bot used by:
  - Mini App initData verification
  - Browser Login Widget verification
- `REDIS_URL` — required for cookie sessions
- `BOT_USERNAME` — used for referral links (without @):
  - dev: `kyrganuosnova_bot`
  - prod: `Kyrganubot`
Frontend:
- `API_BASE` — backend base URL (used by Next.js proxy route)
- `NEXT_PUBLIC_TG_LOGIN_BOT_USERNAME` — bot username for Telegram Login Widget

### 2.2 Deploy sequence
1. Deploy backend first (new `/api/auth/*` endpoints + sessions).
2. Deploy frontend (proxy + login/register pages).
3. Verify flows:
   - Mini App: open via Telegram → `/api/auth/verify` returns `ok` or `NEED_REGISTER`
   - Browser: Login Widget → `/api/auth/login-widget` sets session cookie
   - Link: create password account → link Telegram → login via Telegram uses same character

## 3) DB migrations (auth columns)
Currently, the backend ensures auth columns in `ensure_min_schema()` (idempotent, additive).
Recommended next: create a dedicated SQL migration file and stop doing schema changes in code later.

Suggested migration (conceptually):
- `ALTER TABLE players ADD COLUMN IF NOT EXISTS telegram_id BIGINT;`
- `CREATE UNIQUE INDEX IF NOT EXISTS players_telegram_id_uq ON players(telegram_id) WHERE telegram_id IS NOT NULL;`
- `ALTER TABLE players ADD COLUMN IF NOT EXISTS login TEXT;`
- `CREATE UNIQUE INDEX IF NOT EXISTS players_login_ci_uq ON players ((lower(login))) WHERE login IS NOT NULL;`
- `ALTER TABLE players ADD COLUMN IF NOT EXISTS password_hash TEXT;`

Rollback:
- keep columns, but you can stop using them (dropping columns is risky; do it only later).

## 4) DB cleanup candidates
See `DB_CLEANUP_CANDIDATES.sql`.

Process:
1. Run the verification queries first (counts + dependencies).
2. Rename tables to `__deprecated__...` first (safe).
3. Wait 1–2 deploy cycles.
4. Only then consider DROP.

Rollback:
- If you only renamed, you can rename back.

## 5) Repo cleanup (safe)
Already applied:
- Removed generated `__pycache__` / `*.pyc` from backend package.
- Removed unused `services/referrals_api.py` (no imports found).

Recommended next (manual review):
- Remove unused frontend component `app/_components/AuthGate.tsx` (no imports).
- Add lint/format scripts and enforce in CI.
- Add rate limiter to backend for auth endpoints.

## 6) Verification checklist
- [ ] Mini App login works and keeps same character across restarts.
- [ ] Browser login works (session cookie).
- [ ] Linking works (password account + Telegram).
- [ ] CORS allows your deployed frontend origin.
- [ ] Migrations apply only once, app restarts do not re-run all SQL files.
