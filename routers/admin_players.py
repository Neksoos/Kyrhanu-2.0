# routers/admin_players.py
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel

from config import settings
from db import get_pool

router = APIRouter(prefix="/admin", tags=["admin_players"])


# ──────────────────────────────────────────────
# SAFE SCHEMA GUARD (fixes 500 if columns missing)
# ──────────────────────────────────────────────
async def ensure_players_admin_schema(conn) -> None:
    """
    Адмінка читає ці колонки з players. Якщо хоч однієї нема — SQL падає і дає 500.
    Тому гарантуємо їх існування (безпечно: ADD COLUMN IF NOT EXISTS).
    """
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS is_banned BOOLEAN NOT NULL DEFAULT FALSE"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS last_login DATE"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS login_streak INTEGER NOT NULL DEFAULT 0"
    )

    # базові стати / прогрес
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS xp BIGINT NOT NULL DEFAULT 0"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS hp INTEGER"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS mp INTEGER"
    )

    # бойові стати (якщо їх нема — адмінка все одно очікує)
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS phys_attack INTEGER"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS magic_attack INTEGER"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS phys_defense INTEGER"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS magic_defense INTEGER"
    )

    # валюту теж інколи нема на старих схемах
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS chervontsi BIGINT NOT NULL DEFAULT 0"
    )
    await conn.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS kleynody BIGINT NOT NULL DEFAULT 0"
    )


# Коротка модель для списку
class PlayerItem(BaseModel):
    tg_id: int
    name: Optional[str] = None
    level: int
    chervontsi: int
    kleynody: int
    is_banned: bool = False


# Розширена модель для картки гравця
class PlayerDetails(BaseModel):
    tg_id: int
    name: Optional[str] = None
    level: int
    chervontsi: int
    kleynody: int
    is_banned: bool = False

    race_key: Optional[str] = None
    class_key: Optional[str] = None
    gender: Optional[str] = None

    xp: Optional[int] = None
    hp: Optional[int] = None
    mp: Optional[int] = None
    phys_attack: Optional[int] = None
    magic_attack: Optional[int] = None
    phys_defense: Optional[int] = None
    magic_defense: Optional[int] = None

    created_at: Optional[str] = None
    last_login: Optional[str] = None
    login_streak: Optional[int] = None


class PlayersResponse(BaseModel):
    ok: bool = True
    items: List[PlayerItem]
    total: int


class PlayerToggleBanResponse(BaseModel):
    ok: bool = True
    player: PlayerDetails


class PlayerBalanceUpdateRequest(BaseModel):
    add_chervontsi: int = 0
    add_kleynody: int = 0


class SinglePlayerResponse(BaseModel):
    ok: bool = True
    player: PlayerDetails


async def verify_admin_token(x_admin_token: Optional[str] = Header(None)) -> None:
    if not x_admin_token:
        raise HTTPException(status_code=401, detail={"error": "NO_ADMIN_TOKEN"})
    if x_admin_token != settings.ADMIN_SECRET:
        raise HTTPException(status_code=401, detail={"error": "INVALID_ADMIN_TOKEN"})


@router.get("/players", response_model=PlayersResponse)
async def list_players(
    q: Optional[str] = Query(None, description="Пошук по TG ID або імені"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(verify_admin_token),
):
    pool = await get_pool()

    where_clauses = []
    params: list = []

    if q:
        q_clean = q.strip()
        if q_clean.isdigit():
            where_clauses.append("tg_id = $1")
            params.append(int(q_clean))
        else:
            where_clauses.append("name ILIKE $1")
            params.append(f"%{q_clean}%")

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    async with pool.acquire() as conn:
        await ensure_players_admin_schema(conn)

        count_sql = f"SELECT COUNT(*) FROM players {where_sql}"
        total = await conn.fetchval(count_sql, *params)

        select_params = list(params)
        idx_limit = len(select_params) + 1
        idx_offset = len(select_params) + 2
        select_params.extend([limit, offset])

        select_sql = f"""
            SELECT
                tg_id,
                COALESCE(name, '') AS name,
                COALESCE(level, 1) AS level,
                COALESCE(chervontsi, 0) AS chervontsi,
                COALESCE(kleynody, 0) AS kleynody,
                COALESCE(is_banned, FALSE) AS is_banned
            FROM players
            {where_sql}
            ORDER BY tg_id DESC
            LIMIT ${idx_limit}
            OFFSET ${idx_offset}
        """

        rows = await conn.fetch(select_sql, *select_params)

    items = [
        PlayerItem(
            tg_id=r["tg_id"],
            name=r["name"] or None,
            level=int(r["level"]),
            chervontsi=int(r["chervontsi"]),
            kleynody=int(r["kleynody"]),
            is_banned=bool(r["is_banned"]),
        )
        for r in rows
    ]

    return PlayersResponse(ok=True, items=items, total=total or 0)


async def _row_to_player_details(row) -> PlayerDetails:
    if not row:
        raise HTTPException(status_code=404, detail={"error": "PLAYER_NOT_FOUND"})
    return PlayerDetails(
        tg_id=row["tg_id"],
        name=row["name"] or None,
        level=int(row["level"]),
        chervontsi=int(row["chervontsi"]),
        kleynody=int(row["kleynody"]),
        is_banned=bool(row["is_banned"]),
        race_key=row.get("race_key"),
        class_key=row.get("class_key"),
        gender=row.get("gender"),
        xp=row.get("xp"),
        hp=row.get("hp"),
        mp=row.get("mp"),
        phys_attack=row.get("phys_attack"),
        magic_attack=row.get("magic_attack"),
        phys_defense=row.get("phys_defense"),
        magic_defense=row.get("magic_defense"),
        created_at=str(row.get("created_at")) if row.get("created_at") else None,
        last_login=str(row.get("last_login")) if row.get("last_login") else None,
        login_streak=row.get("login_streak"),
    )


@router.get("/players/{tg_id}", response_model=SinglePlayerResponse)
async def get_player(
    tg_id: int,
    _: None = Depends(verify_admin_token),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_players_admin_schema(conn)

        row = await conn.fetchrow(
            """
            SELECT
                tg_id,
                COALESCE(name, '') AS name,
                COALESCE(level, 1) AS level,
                COALESCE(chervontsi, 0) AS chervontsi,
                COALESCE(kleynody, 0) AS kleynody,
                COALESCE(is_banned, FALSE) AS is_banned,

                race_key,
                class_key,
                gender,

                COALESCE(xp, 0) AS xp,
                COALESCE(hp, 0) AS hp,
                COALESCE(mp, 0) AS mp,
                COALESCE(phys_attack, 0) AS phys_attack,
                COALESCE(magic_attack, 0) AS magic_attack,
                COALESCE(phys_defense, 0) AS phys_defense,
                COALESCE(magic_defense, 0) AS magic_defense,

                created_at,
                last_login,
                COALESCE(login_streak, 0) AS login_streak
            FROM players
            WHERE tg_id = $1
            """,
            tg_id,
        )

    player = await _row_to_player_details(row)
    return SinglePlayerResponse(ok=True, player=player)


async def _set_ban_flag(tg_id: int, banned: bool) -> PlayerDetails:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_players_admin_schema(conn)

        row = await conn.fetchrow(
            """
            UPDATE players
            SET is_banned = $2
            WHERE tg_id = $1
            RETURNING
                tg_id,
                COALESCE(name, '') AS name,
                COALESCE(level, 1) AS level,
                COALESCE(chervontsi, 0) AS chervontsi,
                COALESCE(kleynody, 0) AS kleynody,
                COALESCE(is_banned, FALSE) AS is_banned,

                race_key,
                class_key,
                gender,

                COALESCE(xp, 0) AS xp,
                COALESCE(hp, 0) AS hp,
                COALESCE(mp, 0) AS mp,
                COALESCE(phys_attack, 0) AS phys_attack,
                COALESCE(magic_attack, 0) AS magic_attack,
                COALESCE(phys_defense, 0) AS phys_defense,
                COALESCE(magic_defense, 0) AS magic_defense,

                created_at,
                last_login,
                COALESCE(login_streak, 0) AS login_streak
            """,
            tg_id,
            banned,
        )

    return await _row_to_player_details(row)


@router.post("/players/{tg_id}/ban", response_model=PlayerToggleBanResponse)
async def ban_player(
    tg_id: int,
    _: None = Depends(verify_admin_token),
):
    player = await _set_ban_flag(tg_id, True)
    return PlayerToggleBanResponse(ok=True, player=player)


@router.post("/players/{tg_id}/unban", response_model=PlayerToggleBanResponse)
async def unban_player(
    tg_id: int,
    _: None = Depends(verify_admin_token),
):
    player = await _set_ban_flag(tg_id, False)
    return PlayerToggleBanResponse(ok=True, player=player)


@router.post("/players/{tg_id}/balance", response_model=PlayerToggleBanResponse)
async def update_player_balance(
    tg_id: int,
    body: PlayerBalanceUpdateRequest,
    _: None = Depends(verify_admin_token),
):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_players_admin_schema(conn)

        row = await conn.fetchrow(
            """
            UPDATE players
            SET
                chervontsi = GREATEST(0, COALESCE(chervontsi, 0) + $2),
                kleynody   = GREATEST(0, COALESCE(kleynody, 0)   + $3)
            WHERE tg_id = $1
            RETURNING
                tg_id,
                COALESCE(name, '') AS name,
                COALESCE(level, 1) AS level,
                COALESCE(chervontsi, 0) AS chervontsi,
                COALESCE(kleynody, 0) AS kleynody,
                COALESCE(is_banned, FALSE) AS is_banned,

                race_key,
                class_key,
                gender,

                COALESCE(xp, 0) AS xp,
                COALESCE(hp, 0) AS hp,
                COALESCE(mp, 0) AS mp,
                COALESCE(phys_attack, 0) AS phys_attack,
                COALESCE(magic_attack, 0) AS magic_attack,
                COALESCE(phys_defense, 0) AS phys_defense,
                COALESCE(magic_defense, 0) AS magic_defense,

                created_at,
                last_login,
                COALESCE(login_streak, 0) AS login_streak
            """,
            tg_id,
            body.add_chervontsi,
            body.add_kleynody,
        )

    player = await _row_to_player_details(row)
    return PlayerToggleBanResponse(ok=True, player=player)
