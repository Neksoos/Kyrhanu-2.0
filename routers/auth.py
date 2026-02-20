# routers/auth.py
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from typing import Optional, Any, Dict

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.session import create_session, destroy_session
from core.tg_auth import optional_tg_user, optional_verified_initdata, verify_login_widget
from db import ensure_min_schema, fetch_player_by_telegram_id, get_pool
from models.player import PlayerDTO

router = APIRouter(prefix="/api/auth", tags=["auth"])

PWD_SALT = os.getenv("PWD_SALT", "CHANGE_ME_PASSWORD_SALT")
INTERNAL_ID_BASE = int(os.getenv("INTERNAL_ID_BASE", "1000000000000000"))  # 1e15


class VerifyResp(BaseModel):
    ok: bool
    player: PlayerDTO


class PasswordRegisterReq(BaseModel):
    login: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)
    name: str = Field(..., min_length=3, max_length=16)
    gender: Optional[str] = None
    race_key: Optional[str] = None
    class_key: Optional[str] = None
    locale: Optional[str] = "uk"


class PasswordLoginReq(BaseModel):
    login: str
    password: str


class WidgetAuthReq(BaseModel):
    payload: Dict[str, Any]


class LinkTelegramReq(BaseModel):
    payload: Dict[str, Any]


class PasswordAuthResp(BaseModel):
    ok: bool = True
    player: PlayerDTO


def _sanitize_player_name(name: str, fallback_id: int) -> str:
    """Sanitize names for DB constraints."""
    s = (name or "").strip()
    s = s.replace("’", "'")
    s = re.sub(r"[^0-9A-Za-zА-Яа-яІіЇїЄєҐґ' -]+", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()

    if len(s) < 3:
        s = f"Гість{fallback_id % 10000}"

    return s[:16]


def _hash_password_legacy(raw: str) -> str:
    return hashlib.sha256((PWD_SALT + raw).encode("utf-8")).hexdigest()


def _hash_password_pbkdf2(raw: str) -> str:
    # Format: pbkdf2_sha256$<iters>$<salt>$<hex>
    iters = 260_000
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), iters)
    return f"pbkdf2_sha256${iters}${salt}${dk.hex()}"


def _verify_password(raw: str, stored: str) -> bool:
    if not stored:
        return False

    if stored.startswith("pbkdf2_sha256$"):
        try:
            _alg, iters_s, salt, hexhash = stored.split("$", 3)
            iters = int(iters_s)
            dk = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt.encode("utf-8"), iters)
            return hmac.compare_digest(dk.hex(), hexhash)
        except Exception:
            return False

    # legacy sha256(salt+password)
    return hmac.compare_digest(_hash_password_legacy(raw), stored)


async def _row_to_player_dto(row) -> PlayerDTO:
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


async def _get_player_row_by_tg(conn: Any, tg_id: int):
    return await conn.fetchrow("SELECT * FROM players WHERE tg_id=$1", int(tg_id))


async def _alloc_internal_tg_id(conn: Any) -> int:
    row = await conn.fetchrow(
        "SELECT COALESCE(MAX(tg_id), $1) AS mx FROM players",
        int(INTERNAL_ID_BASE),
    )
    mx = int(row["mx"] or INTERNAL_ID_BASE)
    return max(mx + 1, INTERNAL_ID_BASE)


# ─────────────────────────────────────────────
# ✅ DEPENDENCIES (used across routers)
# ─────────────────────────────────────────────

async def get_tg_id(
    request: Request,
    u: dict[str, Any] | None = Depends(optional_tg_user),
) -> int:
    """Return authenticated internal tg_id.

    Priority:
    1) request.state.tg_id (session cookie or mapped initData)
    2) verified initData user.id (legacy / early boot)
    """
    st = getattr(request.state, "tg_id", None)
    if st:
        return int(st)

    if getattr(request.state, "need_register", False):
        locale = getattr(request.state, "locale", "uk")
        raise HTTPException(
            status_code=409,
            detail={"code": "NEED_REGISTER", "reason": "PLAYER_NOT_FOUND", "locale": locale},
        )

    if u and u.get("id") is not None:
        # This is telegram_id; on legacy DB it might also be tg_id.
        # We do NOT auto-create here.
        telegram_id = int(u["id"])
        player = await fetch_player_by_telegram_id(telegram_id)
        if player:
            return int(player["tg_id"])

        locale = u.get("language_code") or getattr(request.state, "locale", "uk")
        raise HTTPException(
            status_code=409,
            detail={"code": "NEED_REGISTER", "reason": "PLAYER_NOT_FOUND", "locale": locale},
        )

    raise HTTPException(status_code=401, detail="Missing auth")


async def get_player(
    request: Request,
    _init: dict[str, str] | None = Depends(optional_verified_initdata),
    tg_id: int = Depends(get_tg_id),
) -> PlayerDTO:
    """Return player DTO for authenticated user, or 409 NEED_REGISTER."""
    await ensure_min_schema()

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await _get_player_row_by_tg(conn, tg_id)

    if not row:
        locale = getattr(request.state, "locale", "uk")
        raise HTTPException(
            status_code=409,
            detail={"code": "NEED_REGISTER", "reason": "PLAYER_NOT_FOUND", "locale": locale},
        )

    return await _row_to_player_dto(row)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@router.post("/verify", response_model=VerifyResp)
async def verify(player: PlayerDTO = Depends(get_player)):
    return VerifyResp(ok=True, player=player)


@router.post("/logout")
async def logout(request: Request, response: Response):
    await destroy_session(request, response)
    return {"ok": True}


@router.post("/login-widget", response_model=VerifyResp)
async def login_widget(req: WidgetAuthReq, response: Response):
    verified = verify_login_widget(req.payload)
    if verified.get("id") is None:
        raise HTTPException(status_code=401, detail="id missing")

    telegram_id = int(verified["id"])
    player = await fetch_player_by_telegram_id(telegram_id)
    if not player:
        locale = verified.get("language_code") or "uk"
        raise HTTPException(
            status_code=409,
            detail={"code": "NEED_REGISTER", "reason": "PLAYER_NOT_FOUND", "locale": locale},
        )

    await create_session(response, int(player["tg_id"]))
    return VerifyResp(ok=True, player=await _row_to_player_dto(player))


@router.post("/link-telegram")
async def link_telegram(request: Request, req: LinkTelegramReq):
    """Link Telegram to an already authenticated (usually password) account."""
    tg_id = getattr(request.state, "tg_id", None)
    if not tg_id:
        raise HTTPException(status_code=401, detail="Missing session")

    verified = verify_login_widget(req.payload)
    if verified.get("id") is None:
        raise HTTPException(status_code=401, detail="id missing")

    telegram_id = int(verified["id"])

    await ensure_min_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        # check uniqueness
        row = await conn.fetchrow(
            "SELECT tg_id FROM players WHERE telegram_id=$1 AND tg_id <> $2 LIMIT 1",
            telegram_id,
            int(tg_id),
        )
        if row:
            raise HTTPException(status_code=409, detail={"code": "TG_ALREADY_LINKED"})

        await conn.execute(
            "UPDATE players SET telegram_id=$1 WHERE tg_id=$2",
            telegram_id,
            int(tg_id),
        )

    return {"ok": True}


@router.post("/register-password", response_model=PasswordAuthResp)
async def register_password(req: PasswordRegisterReq, response: Response):
    await ensure_min_schema()

    login = req.login.strip().lower()
    if not login:
        raise HTTPException(status_code=400, detail="login required")

    safe_name = _sanitize_player_name(req.name, 0)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # login unique
        exists = await conn.fetchrow(
            "SELECT 1 FROM players WHERE lower(login)=lower($1) LIMIT 1",
            login,
        )
        if exists:
            raise HTTPException(status_code=409, detail="login already used")

        # allocate internal tg_id
        new_tg_id = await _alloc_internal_tg_id(conn)

        try:
            await conn.execute(
                """
                INSERT INTO players (tg_id, name, login, password_hash, locale, gender, race_key, class_key, chervontsi, kleynody)
                VALUES ($1,$2,$3,$4,COALESCE($5,'uk'),$6,$7,$8,50,0)
                """,
                int(new_tg_id),
                safe_name,
                login,
                _hash_password_pbkdf2(req.password),
                req.locale,
                req.gender,
                req.race_key,
                req.class_key,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="name already used")

        row = await _get_player_row_by_tg(conn, int(new_tg_id))

    if not row:
        raise HTTPException(status_code=500, detail="failed_to_create_player")

    await create_session(response, int(new_tg_id))
    return PasswordAuthResp(ok=True, player=await _row_to_player_dto(row))


@router.post("/login-password", response_model=PasswordAuthResp)
async def login_password(req: PasswordLoginReq, response: Response):
    await ensure_min_schema()
    login = (req.login or "").strip().lower()
    if not login:
        raise HTTPException(status_code=400, detail="login required")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM players WHERE lower(login)=lower($1) LIMIT 1",
            login,
        )

    if not row:
        raise HTTPException(status_code=401, detail="invalid credentials")

    d = dict(row)
    stored = d.get('password_hash') or ''
    if not _verify_password(req.password or '', stored):
        raise HTTPException(status_code=401, detail="invalid credentials")

    await create_session(response, int(d['tg_id']))
    return PasswordAuthResp(ok=True, player=await _row_to_player_dto(row))
