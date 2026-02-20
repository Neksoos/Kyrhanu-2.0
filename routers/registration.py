# routers/registration.py
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends, Response, Request
from pydantic import BaseModel, Field
from loguru import logger

from db import get_pool

try:
    from db import ensure_min_schema
except Exception:
    async def ensure_min_schema() -> None:
        return None

# optional: щоб перехоплювати CHECK constraint і не віддавати 500
try:
    import asyncpg
    from asyncpg.exceptions import CheckViolationError
except Exception:
    asyncpg = None  # type: ignore
    CheckViolationError = None  # type: ignore

from models.player import PlayerDTO
from core.session import create_session
from core.tg_auth import get_verified_initdata, get_tg_user, verify_login_widget

router = APIRouter(prefix="/api", tags=["registration"])

BANNED_WORDS = {"хуй", "хує", "хуи", "пиз", "єб", "еб", "бля", "сука", "шлюх"}
ANTI_UA_PATTERNS = [
    re.compile(r"\bхохл\w*\b", re.IGNORECASE),
    re.compile(r"\bукр[ыiі]\w*\b", re.IGNORECASE),
    re.compile(r"\bукроп\w*\b", re.IGNORECASE),
]
_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\ufeff"}

# ✅ ВАЖЛИВО:
#  - це прибирає крапки, дужки, спецсимволи (типу S.O.V.A)
#  - пропускає букви (в т.ч. укр/кирилиця), цифри, _, пробіл, дефіс, апостроф
#  - якщо у тебе DB constraint ще суворіший — його додатково перехопимо нижче
NAME_ALLOWED_RE = re.compile(r"^[\w' -]+$", re.UNICODE)


def _clean(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", (s or "")).strip()
    s = "".join(ch for ch in s if ch not in _ZERO_WIDTH)
    return s.replace("’", "'").replace("`", "'")


def _name_is_clean(name: str) -> bool:
    name = _clean(name)
    if not (3 <= len(name) <= 16):
        return False

    # ✅ синхронізація з DB-підходом: пунктуацію/крапки не пускаємо
    if not NAME_ALLOWED_RE.match(name):
        return False

    low = name.casefold()
    if any(bad in low for bad in BANNED_WORDS):
        return False
    for pat in ANTI_UA_PATTERNS:
        if pat.search(low):
            return False
    return True


async def _name_is_free(conn, name: str, exclude_tg_id: Optional[int] = None) -> bool:
    """
    Перевіряємо унікальність імені.
    exclude_tg_id — щоб гравець міг оновити своє ж ім’я без "Ім'я зайняте".
    """
    if exclude_tg_id is not None:
        row = await conn.fetchrow(
            "SELECT 1 FROM players WHERE lower(name)=lower($1) AND tg_id <> $2 LIMIT 1",
            name,
            int(exclude_tg_id),
        )
    else:
        row = await conn.fetchrow(
            "SELECT 1 FROM players WHERE lower(name)=lower($1) LIMIT 1",
            name,
        )
    return row is None


class RegReq(BaseModel):
    name: str = Field(..., description="Ім'я героя (3–16)")
    gender: Optional[str] = Field(None, description="m/f/x")
    race_key: Optional[str] = None
    class_key: Optional[str] = None
    referrer_tg: Optional[int] = Field(None, description="tg_id реферера")
    locale: Optional[str] = "uk"


class RegWidgetReq(RegReq):
    payload: dict


@router.get("/name-available")
async def name_available(name: str = Query(..., min_length=1)):
    nm = _clean(name)
    if not _name_is_clean(nm):
        return {"ok": False, "available": False, "reason": "invalid"}

    pool = await get_pool()
    async with pool.acquire() as conn:
        free = await _name_is_free(conn, nm)

    return {"ok": True, "available": free}


@router.get("/me", response_model=PlayerDTO)
async def me(tg_id: int = Query(...)):
    """
    Лишається як було (по tg_id), щоб не ламати старий фронт/адмінку.
    Якщо хочеш — можу переробити на initData-only.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM players WHERE tg_id=$1", tg_id)

    if not row:
        raise HTTPException(404, "Not found")

    d = dict(row)
    return PlayerDTO(
        tg_id=int(d["tg_id"]),
        name=d.get("name") or "",
        gender=d.get("gender"),
        race_key=d.get("race_key"),
        class_key=d.get("class_key"),
        chervontsi=int(d.get("chervontsi") or 0),
        kleynody=int(d.get("kleynody") or 0),
        locale=d.get("locale") or "uk",
    )


@router.post("/registration")
async def registration(
    req: RegReq,
    response: Response,
    request: Request,
    _data: dict[str, str] = Depends(get_verified_initdata),
    u: dict = Depends(get_tg_user),
):
    """
    Створення/оновлення гравця через X-Init-Data (Telegram MiniApp).
    tg_id береться тільки з перевіреного initData.
    """
    tg_id = int(u["id"])

    name = _clean(req.name)
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if not _name_is_clean(name):
        raise HTTPException(status_code=400, detail="Некоректне ім’я")

    await ensure_min_schema()

    pool = await get_pool()
    async with pool.acquire() as conn:
        # ім’я має бути вільне (окрім цього tg_id)
        if not await _name_is_free(conn, name, exclude_tg_id=tg_id):
            raise HTTPException(status_code=409, detail="Ім’я зайняте")

        try:
            await conn.execute(
                """
                INSERT INTO players (tg_id, telegram_id, name, gender, race_key, class_key, locale, chervontsi, kleynody)
                VALUES ($1,$1,$2,$3,$4,$5,COALESCE($6,'uk'),50,0)
                ON CONFLICT (tg_id) DO UPDATE SET
                  telegram_id=COALESCE(players.telegram_id, EXCLUDED.telegram_id),
                  name=EXCLUDED.name,
                  gender=EXCLUDED.gender,
                  race_key=EXCLUDED.race_key,
                  class_key=EXCLUDED.class_key,
                  locale=EXCLUDED.locale
                """,
                tg_id,
                name,
                req.gender,
                req.race_key,
                req.class_key,
                req.locale,
            )
        except Exception as e:
            # ✅ якщо БД має CHECK constraint на name — повертаємо 400 (а не 500)
            msg = str(e)
            if CheckViolationError is not None and isinstance(e, CheckViolationError):
                raise HTTPException(status_code=400, detail="Некоректне ім’я")
            # запасний варіант — по тексту (бо asyncpg інколи загортає ексепшн)
            if "players_name_valid_ck" in msg or "violates check constraint" in msg:
                raise HTTPException(status_code=400, detail="Некоректне ім’я")
            raise

        # рефералка (як у тебе було)
        if req.referrer_tg and int(req.referrer_tg) != tg_id:
            try:
                await conn.execute(
                    """
                    INSERT INTO referrals (referrer_tg, invitee_tg)
                    VALUES ($1,$2) ON CONFLICT DO NOTHING
                    """,
                    int(req.referrer_tg),
                    tg_id,
                )
            except Exception as e:
                logger.warning(f"referral insert failed: {e}")

        row = await conn.fetchrow(
            "SELECT * FROM players WHERE tg_id=$1",
            tg_id,
        )

    if not row:
        raise HTTPException(500, "failed_to_load_player")

    # Set session cookie for both MiniApp and browser (via proxy)
    try:
        await create_session(response, int(row['tg_id']))
    except Exception:
        pass

    return {
        "ok": True,
        "player": {
            "tg_id": int(row["tg_id"]),
            "name": row["name"],
            "gender": row.get("gender"),
            "race_key": row.get("race_key"),
            "class_key": row.get("class_key"),
            "locale": row.get("locale") or "uk",
            "chervontsi": int(row.get("chervontsi") or 0),
            "kleynody": int(row.get("kleynody") or 0),
        },
    }

@router.post("/registration-widget")
async def registration_widget(req: RegWidgetReq, response: Response, request: Request):
    """Register/update player from Telegram Login Widget payload (browser).

    Expects body to include {payload: {...}}
    """
    if not isinstance(req.payload, dict) or not req.payload:
        raise HTTPException(status_code=400, detail='payload required')

    verified = verify_login_widget(req.payload)
    if verified.get('id') is None:
        raise HTTPException(status_code=401, detail='id missing')

    telegram_id = int(verified['id'])

    name = _clean(req.name)
    if not name:
        raise HTTPException(status_code=400, detail='name required')
    if not _name_is_clean(name):
        raise HTTPException(status_code=400, detail="Некоректне ім'я")

    await ensure_min_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        if not await _name_is_free(conn, name, exclude_tg_id=telegram_id):
            raise HTTPException(status_code=409, detail="Ім'я зайняте")

        await conn.execute(
            """
            INSERT INTO players (tg_id, telegram_id, name, gender, race_key, class_key, locale, chervontsi, kleynody)
            VALUES ($1,$1,$2,$3,$4,$5,COALESCE($6,'uk'),50,0)
            ON CONFLICT (tg_id) DO UPDATE SET
              telegram_id=COALESCE(players.telegram_id, EXCLUDED.telegram_id),
              name=EXCLUDED.name,
              gender=EXCLUDED.gender,
              race_key=EXCLUDED.race_key,
              class_key=EXCLUDED.class_key,
              locale=EXCLUDED.locale
            """,
            telegram_id,
            name,
            req.gender,
            req.race_key,
            req.class_key,
            req.locale,
        )

        row = await conn.fetchrow('SELECT * FROM players WHERE tg_id=$1', telegram_id)

    if not row:
        raise HTTPException(status_code=500, detail='failed_to_load_player')

    try:
        await create_session(response, int(row['tg_id']))
    except Exception:
        pass

    return {
        'ok': True,
        'player': {
            'tg_id': int(row['tg_id']),
            'name': row['name'],
            'gender': row.get('gender'),
            'race_key': row.get('race_key'),
            'class_key': row.get('class_key'),
            'locale': row.get('locale') or 'uk',
            'chervontsi': int(row.get('chervontsi') or 0),
            'kleynody': int(row.get('kleynody') or 0),
        },
    }
