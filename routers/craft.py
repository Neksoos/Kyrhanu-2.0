# routers/craft.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict
from db import get_pool
from routers.auth import get_tg_id

router = APIRouter(prefix="/api/craft", tags=["craft"])


# ─────────────────────────────────────
# DTO
# ─────────────────────────────────────
class CraftRequest(BaseModel):
    recipe_code: str
    qty: int = 1


# ─────────────────────────────────────
# HELPERS
# ─────────────────────────────────────
async def _get_player(tg_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT id FROM players WHERE tg_id=$1",
            tg_id
        )


# ─────────────────────────────────────
# GET professions overview
# ─────────────────────────────────────
@router.get("/professions")
async def craft_professions(tg_id: int = Depends(get_tg_id)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.code, p.name, pp.level, pp.xp
            FROM player_professions pp
            JOIN professions p ON p.id = pp.profession_id
            WHERE pp.player_id = (
                SELECT id FROM players WHERE tg_id=$1
            )
            """,
            tg_id
        )

    return {
        "ok": True,
        "professions": [
            dict(r) for r in rows
        ]
    }


# ─────────────────────────────────────
# GET recipes
# ─────────────────────────────────────
@router.get("/recipes")
async def get_recipes(profession: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT code, name, descr, energy_cost
            FROM craft_recipes
            WHERE profession_code=$1
            ORDER BY level_required
            """,
            profession
        )

    return {"ok": True, "recipes": [dict(r) for r in rows]}


# ─────────────────────────────────────
# POST craft
# ─────────────────────────────────────
@router.post("/craft")
async def craft(payload: CraftRequest, tg_id: int = Depends(get_tg_id)):
    player = await _get_player(tg_id)
    if not player:
        raise HTTPException(404, "Player not found")

    pool = await get_pool()

    async with pool.acquire() as conn:
        recipe = await conn.fetchrow(
            """
            SELECT *
            FROM craft_recipes
            WHERE code=$1
            """,
            payload.recipe_code
        )
        if not recipe:
            raise HTTPException(404, "Recipe not found")

        ingredients = await conn.fetch(
            """
            SELECT item_code, qty
            FROM craft_recipe_ingredients
            WHERE recipe_code=$1
            """,
            payload.recipe_code
        )

        async with conn.transaction():
            # перевірка матеріалів
            for ing in ingredients:
                have = await conn.fetchval(
                    """
                    SELECT quantity
                    FROM player_materials
                    WHERE player_id=$1 AND material_code=$2
                    """,
                    player["id"],
                    ing["item_code"]
                )
                if not have or have < ing["qty"] * payload.qty:
                    raise HTTPException(400, "Not enough materials")

            # списання
            for ing in ingredients:
                await conn.execute(
                    """
                    UPDATE player_materials
                    SET quantity = quantity - $1
                    WHERE player_id=$2 AND material_code=$3
                    """,
                    ing["qty"] * payload.qty,
                    player["id"],
                    ing["item_code"]
                )

            # видача предмета
            await conn.execute(
                """
                INSERT INTO player_inventory (player_id, item_code, quantity)
                VALUES ($1,$2,$3)
                ON CONFLICT (player_id, item_code)
                DO UPDATE SET quantity = player_inventory.quantity + EXCLUDED.quantity
                """,
                player["id"],
                recipe["result_item_code"],
                recipe["result_qty"] * payload.qty
            )

    return {"ok": True, "crafted": recipe["result_item_code"]}