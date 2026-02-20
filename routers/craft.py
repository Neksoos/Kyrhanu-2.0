from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db import get_pool
from routers.auth import get_tg_id

router = APIRouter(prefix="/api/craft", tags=["craft"])

MAX_LEVEL = 20


class CraftRequest(BaseModel):
    recipe_code: str
    qty: int = 1


# ─────────────────────────────────────
# XP логіка
# ─────────────────────────────────────
def xp_to_next(level: int) -> int:
    return 100 + (level - 1) * 75


async def add_xp(conn, player_id: int, profession_code: str, xp_gain: int):
    prof = await conn.fetchrow(
        """
        SELECT pp.level, pp.xp, pp.profession_id
        FROM player_professions pp
        JOIN professions p ON p.id = pp.profession_id
        WHERE pp.player_id=$1 AND p.code=$2
        """,
        player_id,
        profession_code
    )

    if not prof:
        raise HTTPException(400, "Profession not learned")

    level = prof["level"]
    xp = prof["xp"] + xp_gain

    while level < MAX_LEVEL and xp >= xp_to_next(level):
        xp -= xp_to_next(level)
        level += 1

    await conn.execute(
        """
        UPDATE player_professions
        SET level=$1, xp=$2
        WHERE player_id=$3 AND profession_id=$4
        """,
        level,
        xp,
        player_id,
        prof["profession_id"]
    )


# ─────────────────────────────────────
# LIST PROFESSIONS
# ─────────────────────────────────────
@router.get("/professions")
async def list_my_professions(tg_id: int = Depends(get_tg_id)):
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

    return {"ok": True, "professions": [dict(r) for r in rows]}


# ─────────────────────────────────────
# LIST RECIPES
# ─────────────────────────────────────
@router.get("/recipes")
async def list_recipes(profession: str):
    if profession == "alchemist":
        return {
            "ok": True,
            "redirect": "/api/alchemy/recipes"
        }

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT *
            FROM craft_recipes
            WHERE profession_code=$1
            ORDER BY level_required
            """,
            profession
        )

    return {"ok": True, "recipes": [dict(r) for r in rows]}


# ─────────────────────────────────────
# CRAFT
# ─────────────────────────────────────
@router.post("/craft")
async def craft(payload: CraftRequest, tg_id: int = Depends(get_tg_id)):
    pool = await get_pool()

    async with pool.acquire() as conn:
        player = await conn.fetchrow(
            "SELECT id, energy FROM players WHERE tg_id=$1",
            tg_id
        )
        if not player:
            raise HTTPException(404, "Player not found")

        recipe = await conn.fetchrow(
            "SELECT * FROM craft_recipes WHERE code=$1",
            payload.recipe_code
        )
        if not recipe:
            raise HTTPException(404, "Recipe not found")

        profession_code = recipe["profession_code"]

        prof = await conn.fetchrow(
            """
            SELECT pp.level
            FROM player_professions pp
            JOIN professions p ON p.id = pp.profession_id
            WHERE pp.player_id=$1 AND p.code=$2
            """,
            player["id"],
            profession_code
        )

        if not prof:
            raise HTTPException(400, "Profession not learned")

        if prof["level"] < recipe["level_required"]:
            raise HTTPException(400, "Profession level too low")

        energy_cost = recipe["energy_cost"] + recipe["level_required"] * 2
        total_energy = energy_cost * payload.qty

        if player["energy"] < total_energy:
            raise HTTPException(400, "Not enough energy")

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

            # списання матеріалів
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

            # списання енергії
            await conn.execute(
                """
                UPDATE players
                SET energy = energy - $1
                WHERE id=$2
                """,
                total_energy,
                player["id"]
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

            xp_gain = recipe["level_required"] * 20 * payload.qty
            await add_xp(conn, player["id"], profession_code, xp_gain)

    return {
        "ok": True,
        "crafted": recipe["result_item_code"],
        "xp_gained": xp_gain
    }