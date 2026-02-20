from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from db import get_pool
from routers.auth import get_tg_id
from services.inventory.service import give_item_to_player
from services.profession_progress import add_prof_xp, get_prof_level

router = APIRouter(prefix="/api/craft", tags=["craft"])


class CraftRequest(BaseModel):
    recipe_code: str = Field(..., min_length=2)
    qty: int = Field(1, ge=1, le=20)


def _xp_reward(level_required: int, qty: int) -> int:
    base = 14 + (max(1, int(level_required)) * 6)
    return base * max(1, int(qty))


@router.get("/professions")
async def list_my_professions(tg_id: int = Depends(get_tg_id)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.code, p.name, pp.level, pp.xp
            FROM player_professions pp
            JOIN professions p ON p.id = pp.profession_id
            JOIN players pl ON pl.id = pp.player_id
            WHERE pl.tg_id = $1
            ORDER BY p.kind, p.code
            """,
            tg_id,
        )
    return {"ok": True, "professions": [dict(r) for r in rows]}


@router.get("/recipes")
async def list_recipes(profession: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if profession == "alchemist":
            rows = await conn.fetch(
                """
                SELECT code, name, descr, level_req AS level_required,
                       brew_time_sec AS energy_cost, output_item_code AS result_item_code,
                       output_amount AS result_qty
                FROM alchemy_recipes
                ORDER BY level_req, code
                """
            )
            return {"ok": True, "recipes": [dict(r) for r in rows]}

        rows = await conn.fetch(
            """
            SELECT code, profession_code, name, descr, result_item_code,
                   COALESCE(result_qty, 1) AS result_qty,
                   COALESCE(level_required, 1) AS level_required,
                   COALESCE(energy_cost, 0) AS energy_cost
            FROM craft_recipes
            WHERE profession_code=$1
            ORDER BY level_required, code
            """,
            profession,
        )

    return {"ok": True, "recipes": [dict(r) for r in rows]}


async def _load_materials_by_code(conn: Any, tg_id: int) -> dict[str, int]:
    rows = await conn.fetch(
        """
        SELECT cm.code, pm.qty
        FROM player_materials pm
        JOIN craft_materials cm ON cm.id = pm.material_id
        WHERE pm.tg_id = $1
        """,
        tg_id,
    )
    return {str(r["code"]): int(r["qty"] or 0) for r in rows}


@router.post("/craft")
async def craft(payload: CraftRequest, tg_id: int = Depends(get_tg_id)):
    pool = await get_pool()

    async with pool.acquire() as conn:
        player = await conn.fetchrow("SELECT tg_id, energy FROM players WHERE tg_id=$1", tg_id)
        if not player:
            raise HTTPException(404, "PLAYER_NOT_FOUND")

        recipe = await conn.fetchrow(
            """
            SELECT code, profession_code, result_item_code,
                   COALESCE(result_qty,1) AS result_qty,
                   COALESCE(level_required,1) AS level_required,
                   COALESCE(energy_cost,0) AS energy_cost,
                   name
            FROM craft_recipes
            WHERE code=$1
            """,
            payload.recipe_code,
        )
        if not recipe:
            raise HTTPException(404, "RECIPE_NOT_FOUND")

        progress = await get_prof_level(conn, tg_id, str(recipe["profession_code"]))
        if progress.level < int(recipe["level_required"]):
            raise HTTPException(
                400,
                detail={
                    "code": "PROF_LEVEL_TOO_LOW",
                    "required": int(recipe["level_required"]),
                    "current": progress.level,
                },
            )

        ingredients = await conn.fetch(
            """
            SELECT item_code, qty
            FROM craft_recipe_ingredients
            WHERE recipe_code=$1
            """,
            payload.recipe_code,
        )

        required_energy = int(recipe["energy_cost"]) * int(payload.qty)
        if int(player["energy"] or 0) < required_energy:
            raise HTTPException(400, detail={"code": "NOT_ENOUGH_ENERGY", "need": required_energy})

        materials = await _load_materials_by_code(conn, tg_id)
        missing: list[dict[str, int | str]] = []
        for ing in ingredients:
            code = str(ing["item_code"])
            need = int(ing["qty"]) * int(payload.qty)
            have = int(materials.get(code, 0))
            if have < need:
                missing.append({"item_code": code, "need": need, "have": have})

        if missing:
            raise HTTPException(400, detail={"code": "NOT_ENOUGH_MATERIALS", "missing": missing})

        async with conn.transaction():
            for ing in ingredients:
                code = str(ing["item_code"])
                need = int(ing["qty"]) * int(payload.qty)
                material_id = await conn.fetchval(
                    "SELECT id FROM craft_materials WHERE code=$1",
                    code,
                )
                if not material_id:
                    raise HTTPException(400, detail=f"MATERIAL_NOT_FOUND:{code}")

                await conn.execute(
                    """
                    UPDATE player_materials
                    SET qty = qty - $1, updated_at = NOW()
                    WHERE tg_id=$2 AND material_id=$3
                    """,
                    need,
                    tg_id,
                    int(material_id),
                )
                await conn.execute(
                    "DELETE FROM player_materials WHERE tg_id=$1 AND material_id=$2 AND qty <= 0",
                    tg_id,
                    int(material_id),
                )

            await conn.execute(
                "UPDATE players SET energy = energy - $1 WHERE tg_id=$2",
                required_energy,
                tg_id,
            )

            xp_gain = _xp_reward(int(recipe["level_required"]), int(payload.qty))
            new_progress = await add_prof_xp(conn, tg_id, str(recipe["profession_code"]), xp_gain)

    crafted_amount = int(recipe["result_qty"] or 1) * int(payload.qty)
    await give_item_to_player(tg_id=tg_id, item_code=str(recipe["result_item_code"]), qty=crafted_amount)

    return {
        "ok": True,
        "recipe_code": str(recipe["code"]),
        "created_item_code": str(recipe["result_item_code"]),
        "created_qty": crafted_amount,
        "energy_spent": required_energy,
        "xp_gained": xp_gain,
        "profession": {
            "code": str(recipe["profession_code"]),
            "level": new_progress.level,
            "xp": new_progress.xp,
            "xp_to_next": new_progress.xp_to_next,
        },
    }
