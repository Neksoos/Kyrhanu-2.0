# routers/blacksmith.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Literal, Iterable, Set

from fastapi import APIRouter, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from db import get_pool

# ✅ після рефакторингу інвентаря:
from services.inventory.service import give_item_to_player  # type: ignore
from services.inventory.migrations import (
    ensure_items_columns as _ensure_items_columns,
    ensure_player_inventory_columns as _ensure_player_inventory_columns,
)

# ✅ achievements (метрики)
from services.achievements.metrics import inc_metric  # type: ignore
from services.profession_progress import add_prof_xp

router = APIRouter(prefix="/api/blacksmith", tags=["blacksmith"])


# ─────────────────────────────────────────────
# DTO
# ─────────────────────────────────────────────

class IngredientDTO(BaseModel):
    # ⚠️ назва material_code лишається як у фронті,
    # але в БД це буде input_code
    material_code: str
    qty: int
    role: str = "metal"

    # ✅ UI-friendly: бек може одразу віддати назву, щоб фронт не робив окремий довідник
    name: Optional[str] = None

    # ✅ звідки брати кількість: player_materials (material) або player_inventory (item)
    kind: Optional[Literal["material", "item"]] = None


class RecipeDTO(BaseModel):
    code: str
    name: str
    slot: str
    level_req: int

    forge_hits: int = 60
    base_progress_per_hit: float = 0.0166667
    heat_sensitivity: float = 0.65
    rhythm_window_ms: Tuple[int, int] = (120, 220)

    output_item_code: str
    output_item_name: Optional[str] = None
    output_item_kind: Optional[Literal["material", "item"]] = None
    output_amount: int = 1
    ingredients: List[IngredientDTO]


class MissingDTO(BaseModel):
    material_code: str
    need: int
    have: int
    missing: int
    role: str

    # optional UI labels
    name: Optional[str] = None
    kind: Optional[Literal["material", "item"]] = None


class RecipeStatusDTO(BaseModel):
    recipe: RecipeDTO
    can_forge: bool
    missing: List[MissingDTO]


class ForgeStartBody(BaseModel):
    recipe_code: str = Field(..., min_length=1)


class ForgeStartResponse(BaseModel):
    forge_id: int
    recipe_code: str

    required_hits: int
    base_progress_per_hit: float
    heat_sensitivity: float
    rhythm_window_ms: Tuple[int, int]


class ForgeClaimBody(BaseModel):
    forge_id: int
    recipe_code: str
    client_report: Optional[dict] = None


class ForgeClaimResponse(BaseModel):
    ok: bool = True
    item_code: str
    amount: int
    xp_gained: int = 0
    profession_level: int | None = None
    profession_xp: int | None = None


class ForgeCancelBody(BaseModel):
    forge_id: int
    recipe_code: str
    client_report: Optional[dict] = None


class ForgeCancelResponse(BaseModel):
    ok: bool = True
    refunded: bool = True


# ✅ Smelting DTOs (руда → злитки)

class SmeltRecipeDTO(BaseModel):
    code: str
    name: str
    output_item_code: str
    output_item_name: Optional[str] = None
    output_item_kind: Optional[Literal["material", "item"]] = None
    output_amount: int = 1
    ingredients: List[IngredientDTO]


class SmeltStatusDTO(BaseModel):
    recipe: SmeltRecipeDTO
    can_smelt: bool
    missing: List[MissingDTO]


class SmeltStartBody(BaseModel):
    recipe_code: str = Field(..., min_length=1)


class SmeltStartResponse(BaseModel):
    ok: bool = True
    recipe_code: str
    item_code: str
    item_name: Optional[str] = None
    item_kind: Optional[Literal["material", "item"]] = None
    amount: int


# ─────────────────────────────────────────────
# DB ensure
# ─────────────────────────────────────────────

async def _ensure_blacksmith_tables() -> None:
    # ✅ важливо: items/player_inventory мають мати потрібні колонки ДО будь-яких запитів
    await _ensure_items_columns()
    await _ensure_player_inventory_columns()

    pool = await get_pool()
    async with pool.acquire() as conn:
        # --- базові таблиці (recipes) ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacksmith_recipes (
                code                  text PRIMARY KEY,
                name                  text NOT NULL,
                slot                  text NOT NULL,
                level_req             int  NOT NULL DEFAULT 1,

                forge_hits            int  NOT NULL DEFAULT 60,
                base_progress_per_hit double precision NOT NULL DEFAULT 0.0166667,
                heat_sensitivity      double precision NOT NULL DEFAULT 0.65,
                rhythm_min_ms         int  NOT NULL DEFAULT 120,
                rhythm_max_ms         int  NOT NULL DEFAULT 220,

                output_item_code      text NOT NULL,
                output_amount         int  NOT NULL DEFAULT 1,

                created_at            timestamptz NOT NULL DEFAULT now(),
                updated_at            timestamptz NOT NULL DEFAULT now()
            );
            """
        )

        # ✅ ingredients table під ТВОЮ схему (input_kind/input_code)
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacksmith_recipe_ingredients (
                id          bigserial PRIMARY KEY,
                recipe_code text NOT NULL REFERENCES blacksmith_recipes(code) ON DELETE CASCADE,
                input_kind  text NOT NULL DEFAULT 'material',
                input_code  text NOT NULL,
                qty         int  NOT NULL DEFAULT 1,
                role        text NOT NULL DEFAULT 'metal'
            );
            """
        )

        # уникальний індекс, щоб ON CONFLICT працював
        await conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bsmith_ing
            ON blacksmith_recipe_ingredients (recipe_code, input_code, role);
            """
        )

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bsmith_recipes_slot ON blacksmith_recipes(slot);")

        # --- forge table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_blacksmith_forge (
                id                    bigserial PRIMARY KEY,
                tg_id                 bigint NOT NULL,
                recipe_code           text NOT NULL REFERENCES blacksmith_recipes(code),
                status                text NOT NULL DEFAULT 'started', -- started|claimed|cancelled
                started_at            timestamptz NOT NULL DEFAULT now(),
                claimed_at            timestamptz NULL,

                required_hits         int NOT NULL,
                base_progress_per_hit double precision NOT NULL,
                heat_sensitivity      double precision NOT NULL,
                rhythm_min_ms         int NOT NULL,
                rhythm_max_ms         int NOT NULL
            );
            """
        )

        # --- еволюційні колонки (щоб не падало на старій базі) ---
        await conn.execute("""ALTER TABLE player_blacksmith_forge ADD COLUMN IF NOT EXISTS cancelled_at timestamptz NULL;""")
        await conn.execute("""ALTER TABLE player_blacksmith_forge ADD COLUMN IF NOT EXISTS client_hits int NULL;""")
        await conn.execute("""ALTER TABLE player_blacksmith_forge ADD COLUMN IF NOT EXISTS client_report jsonb NULL;""")

        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bsmith_forge_tg ON player_blacksmith_forge(tg_id, status);")

        # --- smelting ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacksmith_smelt_recipes (
                code             text PRIMARY KEY,
                name             text NOT NULL,
                output_item_code text NOT NULL,
                output_amount    int  NOT NULL DEFAULT 1,
                created_at       timestamptz NOT NULL DEFAULT now(),
                updated_at       timestamptz NOT NULL DEFAULT now()
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacksmith_smelt_ingredients (
                recipe_code   text NOT NULL REFERENCES blacksmith_smelt_recipes(code) ON DELETE CASCADE,
                material_code text NOT NULL, -- item_code
                qty           int  NOT NULL DEFAULT 1,
                role          text NOT NULL DEFAULT 'ore',
                PRIMARY KEY (recipe_code, material_code, role)
            );
            """
        )
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_bsmith_smelt ON blacksmith_smelt_recipes(code);")


# ─────────────────────────────────────────────
# helpers (INVENTORY)
# ─────────────────────────────────────────────

CodeKind = Literal["material", "item"]


async def _player_materials_qty_by_code(conn: Any, tg_id: int) -> Dict[str, int]:
    """Скільки craft_materials має гравець (мапа code -> qty)."""
    rows = await conn.fetch(
        """
        SELECT cm.code AS code, COALESCE(SUM(pm.qty), 0)::int AS qty
        FROM player_materials pm
        JOIN craft_materials cm ON cm.id = pm.material_id
        WHERE pm.tg_id = $1
        GROUP BY cm.code
        """,
        tg_id,
    )
    return {str(r["code"]): int(r["qty"] or 0) for r in (rows or [])}


async def _load_code_index(conn: Any, codes: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Індекс кодів інгредієнтів/виходів: code -> meta(kind,id,name,...).

    Пріоритет: craft_materials (material) > items (item).
    """
    uniq: List[str] = sorted({str(c) for c in codes if c})
    if not uniq:
        return {}

    mats = await conn.fetch(
        """
        SELECT id, code, name, profession, source_type, rarity, descr
        FROM craft_materials
        WHERE code = ANY($1::text[])
        """,
        uniq,
    )
    items = await conn.fetch(
        """
        SELECT id, code, name, category, emoji, rarity, description, slot
        FROM items
        WHERE code = ANY($1::text[])
        """,
        uniq,
    )

    out: Dict[str, Dict[str, Any]] = {}
    for r in items:
        code = str(r["code"])
        out[code] = {
            "kind": "item",
            "item_id": int(r["id"]),
            "name": r["name"],
            "category": r["category"],
            "emoji": r["emoji"],
            "rarity": r["rarity"],
            "description": r["description"],
            "slot": r["slot"],
        }

    # craft_materials мають пріоритет (перекривають items з тим самим code)
    for r in mats:
        code = str(r["code"])
        out[code] = {
            "kind": "material",
            "material_id": int(r["id"]),
            "name": r["name"],
            "category": r["profession"],
            "rarity": r["rarity"],
            "source_type": r["source_type"],
            "descr": r["descr"],
        }

    return out

async def _player_inventory_qty_by_code(conn: Any, tg_id: int) -> Dict[str, int]:
    rows = await conn.fetch(
        """
        SELECT i.code AS code, COALESCE(SUM(pi.qty), 0)::int AS qty
        FROM player_inventory pi
        JOIN items i ON i.id = pi.item_id
        WHERE pi.tg_id = $1
          AND pi.is_equipped = FALSE
        GROUP BY i.code
        """,
        tg_id,
    )
    return {str(r["code"]): int(r["qty"] or 0) for r in (rows or [])}


def _calc_missing_inventory(
    ingredients: List[IngredientDTO],
    have_by_code: Dict[str, int],
) -> Tuple[bool, List[MissingDTO]]:
    missing: List[MissingDTO] = []
    for ing in ingredients:
        code = str(ing.material_code)
        need = int(ing.qty)
        have = int(have_by_code.get(code, 0))
        miss = max(0, need - have)
        if miss > 0:
            missing.append(
                MissingDTO(
                    material_code=code,
                    need=need,
                    have=have,
                    missing=miss,
                    role=str(ing.role),
                )
            )
    return (len(missing) == 0), missing


def _decorate_ingredients(ingredients: List[IngredientDTO], idx: Dict[str, Dict[str, Any]]) -> List[IngredientDTO]:
    """Додає name/kind до IngredientDTO (без зміни code/qty)."""
    out: List[IngredientDTO] = []
    for ing in ingredients:
        code = str(ing.material_code)
        meta = idx.get(code) or {}
        kind = meta.get("kind")
        out.append(
            IngredientDTO(
                material_code=code,
                qty=int(ing.qty),
                role=str(ing.role),
                name=(meta.get("name") or None),
                kind=(kind if kind in ("material", "item") else None),
            )
        )
    return out


def _calc_missing_mixed(
    ingredients: List[IngredientDTO],
    have_items: Dict[str, int],
    have_materials: Dict[str, int],
    idx: Dict[str, Dict[str, Any]],
) -> Tuple[bool, List[MissingDTO]]:
    """Перевірка інгредієнтів для рецептів, де можуть бути і items, і craft_materials."""
    missing: List[MissingDTO] = []

    for ing in ingredients:
        code = str(ing.material_code)
        need = int(ing.qty)
        if need <= 0:
            continue

        meta = idx.get(code)
        kind = (meta or {}).get("kind")
        if kind == "material":
            have = int(have_materials.get(code, 0))
        elif kind == "item":
            have = int(have_items.get(code, 0))
        else:
            have = 0

        miss = max(0, need - have)
        if miss > 0:
            missing.append(
                MissingDTO(
                    material_code=code,
                    need=need,
                    have=have,
                    missing=miss,
                    role=str(ing.role),
                    name=(meta.get("name") if meta else None),
                    kind=(kind if kind in ("material", "item") else None),
                )
            )

    return (len(missing) == 0), missing


async def _add_material_to_player(conn: Any, tg_id: int, material_id: int, qty: int) -> None:
    if qty <= 0:
        return
    await conn.execute(
        """
        INSERT INTO player_materials(tg_id, material_id, qty, created_at, updated_at)
        VALUES ($1, $2, $3, now(), now())
        ON CONFLICT (tg_id, material_id)
        DO UPDATE SET qty = player_materials.qty + EXCLUDED.qty,
                      updated_at = now()
        """,
        tg_id,
        material_id,
        qty,
    )


async def _deduct_materials(conn: Any, tg_id: int, ingredients: List[IngredientDTO], idx: Dict[str, Dict[str, Any]]) -> None:
    """Списує craft_materials з player_materials (в межах транзакції)."""
    for ing in ingredients:
        code = str(ing.material_code)
        need = int(ing.qty)
        if need <= 0:
            continue

        meta = idx.get(code) or {}
        material_id = meta.get("material_id")
        if not material_id:
            raise HTTPException(400, detail={"code": "MATERIAL_CODE_NOT_FOUND", "material_code": code})

        row = await conn.fetchrow(
            """
            SELECT qty
            FROM player_materials
            WHERE tg_id=$1 AND material_id=$2
            FOR UPDATE
            """,
            tg_id,
            int(material_id),
        )

        have = int((row or {}).get("qty") or 0)
        if have < need:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "NOT_ENOUGH_MATERIALS",
                    "material_code": code,
                    "need": need,
                    "have": have,
                },
            )

        new_qty = have - need
        if new_qty <= 0:
            await conn.execute(
                "DELETE FROM player_materials WHERE tg_id=$1 AND material_id=$2",
                tg_id,
                int(material_id),
            )
        else:
            await conn.execute(
                "UPDATE player_materials SET qty=$3, updated_at=now() WHERE tg_id=$1 AND material_id=$2",
                tg_id,
                int(material_id),
                int(new_qty),
            )


async def _deduct_mixed_inputs(conn: Any, tg_id: int, ingredients: List[IngredientDTO]) -> Dict[str, Dict[str, Any]]:
    """Списує інгредієнти з відповідного сховища.

    Повертає idx (code -> meta), щоб його можна було перевикористати для refund/output.
    """
    codes = [str(i.material_code) for i in ingredients]
    idx = await _load_code_index(conn, codes)

    # якщо код не знайдений ніде — це помилка сідінгу/рецепта
    unknown: List[str] = [c for c in codes if c not in idx]
    if unknown:
        raise HTTPException(400, detail={"code": "INGREDIENT_CODE_UNKNOWN", "unknown": unknown})

    have_items = await _player_inventory_qty_by_code(conn, tg_id)
    have_mats = await _player_materials_qty_by_code(conn, tg_id)
    ok, miss = _calc_missing_mixed(ingredients, have_items, have_mats, idx)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={"code": "NOT_ENOUGH_INGREDIENTS", "missing": [m.dict() for m in miss]},
        )

    mats: List[IngredientDTO] = []
    items: List[IngredientDTO] = []
    for ing in ingredients:
        code = str(ing.material_code)
        kind = (idx.get(code) or {}).get("kind")
        if kind == "material":
            mats.append(ing)
        else:
            items.append(ing)

    if mats:
        await _deduct_materials(conn, tg_id, mats, idx)
    if items:
        await _deduct_inventory_items(conn, tg_id, items)

    return idx


async def _deduct_inventory_items(conn: Any, tg_id: int, ingredients: List[IngredientDTO]) -> None:
    have_by_code = await _player_inventory_qty_by_code(conn, tg_id)
    ok, miss = _calc_missing_inventory(ingredients, have_by_code)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail={"code": "NOT_ENOUGH_ITEMS", "missing": [m.dict() for m in miss]},
        )

    for ing in ingredients:
        code = str(ing.material_code)
        need = int(ing.qty)
        if need <= 0:
            continue

        item_id = await conn.fetchval("SELECT id FROM items WHERE code=$1", code)
        if not item_id:
            raise HTTPException(400, detail={"code": "ITEM_CODE_NOT_FOUND", "item_code": code})

        rows = await conn.fetch(
            """
            SELECT id, qty
            FROM player_inventory
            WHERE tg_id=$1 AND item_id=$2 AND is_equipped=FALSE
            ORDER BY created_at ASC, id ASC
            FOR UPDATE
            """,
            tg_id,
            int(item_id),
        )

        remaining = need
        for r in rows:
            if remaining <= 0:
                break
            inv_id = int(r["id"])
            q = int(r["qty"] or 0)
            if q <= 0:
                continue

            take = min(q, remaining)
            new_q = q - take

            if new_q <= 0:
                await conn.execute("DELETE FROM player_inventory WHERE id=$1", inv_id)
            else:
                await conn.execute(
                    "UPDATE player_inventory SET qty=$2, updated_at=NOW() WHERE id=$1",
                    inv_id,
                    new_q,
                )

            remaining -= take

        if remaining > 0:
            raise HTTPException(500, "INVENTORY_DEDUCT_FAILED")


async def _get_item_meta(conn: Any, item_code: str) -> Dict[str, Optional[str]]:
    row = await conn.fetchrow(
        "SELECT code, name, category, emoji, rarity, description, slot FROM items WHERE code=$1",
        item_code,
    )
    if not row:
        return {
            "name": item_code,
            "category": "mat",
            "emoji": None,
            "rarity": None,
            "description": None,
            "slot": None,
        }
    return {
        "name": str(row["name"]),
        "category": row["category"],
        "emoji": row["emoji"],
        "rarity": row["rarity"],
        "description": row["description"],
        "slot": row["slot"],
    }


# ✅ ТУТ ГОЛОВНИЙ ФІКС: беремо input_code з БД, а віддаємо як material_code
async def _load_recipe_ingredients(conn: Any, recipe_code: str) -> List[IngredientDTO]:
    irows = await conn.fetch(
        """
        SELECT input_code, qty, role
        FROM blacksmith_recipe_ingredients
        WHERE recipe_code=$1
          AND input_kind='material'
        ORDER BY role, input_code
        """,
        recipe_code,
    )
    return [
        IngredientDTO(
            material_code=str(x["input_code"]),
            qty=int(x["qty"]),
            role=str(x["role"]),
        )
        for x in (irows or [])
    ]


# ─────────────────────────────────────────────
# endpoints: SMELT
# ─────────────────────────────────────────────

async def _load_smelt_recipes(conn: Any) -> List[SmeltRecipeDTO]:
    rrows = await conn.fetch(
        """
        SELECT code, name, output_item_code, output_amount
        FROM blacksmith_smelt_recipes
        ORDER BY name
        """
    )
    irows = await conn.fetch(
        """
        SELECT recipe_code, material_code, qty, role
        FROM blacksmith_smelt_ingredients
        ORDER BY recipe_code, role, material_code
        """
    )
    ings_by: Dict[str, List[IngredientDTO]] = {}
    for r in irows:
        code = str(r["recipe_code"])
        ings_by.setdefault(code, []).append(
            IngredientDTO(
                material_code=str(r["material_code"]),
                qty=int(r["qty"]),
                role=str(r["role"]),
            )
        )

    out: List[SmeltRecipeDTO] = []
    for r in rrows:
        code = str(r["code"])
        out.append(
            SmeltRecipeDTO(
                code=code,
                name=str(r["name"]),
                output_item_code=str(r["output_item_code"]),
                output_amount=int(r["output_amount"] or 1),
                ingredients=ings_by.get(code, []),
            )
        )
    return out


@router.get("/smelt/recipes/status", response_model=List[SmeltStatusDTO])
async def smelt_recipes_status(tg_id: int) -> List[SmeltStatusDTO]:
    if tg_id <= 0:
        raise HTTPException(400, "INVALID_TG_ID")

    await _ensure_blacksmith_tables()

    pool = await get_pool()
    async with pool.acquire() as conn:
        recipes = await _load_smelt_recipes(conn)
        if not recipes:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "SMELT_RECIPES_NOT_SEEDED",
                    "hint": "Заповни blacksmith_smelt_recipes та blacksmith_smelt_ingredients (migrations/seed).",
                },
            )
        all_codes: Set[str] = set()
        for rr in recipes:
            all_codes.add(str(rr.output_item_code))
            for ing in rr.ingredients:
                all_codes.add(str(ing.material_code))

        idx = await _load_code_index(conn, all_codes)
        have_items = await _player_inventory_qty_by_code(conn, tg_id)
        have_mats = await _player_materials_qty_by_code(conn, tg_id)

    out: List[SmeltStatusDTO] = []
    for r in recipes:
        meta_out = idx.get(str(r.output_item_code)) or {}
        r2 = SmeltRecipeDTO(
            code=r.code,
            name=r.name,
            output_item_code=r.output_item_code,
            output_item_name=(meta_out.get("name") or None),
            output_item_kind=(meta_out.get("kind") if meta_out.get("kind") in ("material", "item") else None),
            output_amount=int(r.output_amount or 1),
            ingredients=_decorate_ingredients(r.ingredients, idx),
        )
        ok, miss = _calc_missing_mixed(r2.ingredients, have_items, have_mats, idx)
        out.append(SmeltStatusDTO(recipe=r2, can_smelt=ok, missing=miss))
    return out


@router.post("/smelt/start", response_model=SmeltStartResponse)
async def smelt_start(tg_id: int, body: SmeltStartBody) -> SmeltStartResponse:
    if tg_id <= 0:
        raise HTTPException(400, "INVALID_TG_ID")

    await _ensure_blacksmith_tables()

    item_code: str = ""
    amount: int = 0
    item_name: Optional[str] = None
    item_kind: Optional[CodeKind] = None
    item_meta: Dict[str, Optional[str]] = {}

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                rr = await conn.fetchrow(
                    """
                    SELECT output_item_code, output_amount
                    FROM blacksmith_smelt_recipes
                    WHERE code=$1
                    """,
                    body.recipe_code,
                )
                if not rr:
                    raise HTTPException(404, "SMELT_RECIPE_NOT_FOUND")

                irows = await conn.fetch(
                    """
                    SELECT material_code, qty, role
                    FROM blacksmith_smelt_ingredients
                    WHERE recipe_code=$1
                    """,
                    body.recipe_code,
                )
                ingredients = [
                    IngredientDTO(
                        material_code=str(x["material_code"]),
                        qty=int(x["qty"]),
                        role=str(x["role"]),
                    )
                    for x in (irows or [])
                ]

                # ✅ головний фікс: інгредієнти можуть жити і в player_inventory (items), і в player_materials (craft_materials)
                await _deduct_mixed_inputs(conn, tg_id, ingredients)

                item_code = str(rr["output_item_code"])
                amount = int(rr["output_amount"] or 1)

                out_idx = await _load_code_index(conn, [item_code])
                out_meta = out_idx.get(item_code) or {}
                kind = out_meta.get("kind")

                if kind == "material" and out_meta.get("material_id"):
                    item_kind = "material"
                    item_name = out_meta.get("name")
                    await _add_material_to_player(conn, tg_id, int(out_meta["material_id"]), amount)
                else:
                    # fallback: вважаємо це items-ом
                    item_kind = "item"
                    item_meta = await _get_item_meta(conn, item_code)
                    item_name = item_meta.get("name") or item_code
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"smelt_start failed: tg_id={tg_id} recipe={body.recipe_code}")
        raise HTTPException(500, detail={"code": "SMELT_INTERNAL", "error": str(e)})

    # items додаємо через сервіс інвентарю (він уміє створити item при відсутності)
    if item_kind == "item":
        await give_item_to_player(
            tg_id=tg_id,
            item_code=item_code,
            name=item_meta.get("name") or item_code,
            category=item_meta.get("category"),
            emoji=item_meta.get("emoji"),
            rarity=item_meta.get("rarity"),
            description=item_meta.get("description"),
            qty=amount,
            slot=item_meta.get("slot"),
        )

    xp_gain = 10
    async with pool.acquire() as conn_xp:
        async with conn_xp.transaction():
            xp_gain = 8 + max(1, amount) * 5
            await add_prof_xp(conn_xp, tg_id, "blacksmith", xp_gain)

    try:
        await inc_metric(tg_id, "smelt_blacksmith_count", 1)
    except Exception:
        logger.exception("blacksmith: inc_metric smelt_blacksmith_count FAILED tg_id={}", tg_id)

    return SmeltStartResponse(
        ok=True,
        recipe_code=body.recipe_code,
        item_code=item_code,
        item_name=item_name,
        item_kind=item_kind,
        amount=amount,
    )


# ─────────────────────────────────────────────
# endpoints: FORGE
# ─────────────────────────────────────────────

async def _load_forge_recipes(conn: Any) -> List[RecipeDTO]:
    rrows = await conn.fetch(
        """
        SELECT code, name, slot, level_req,
               forge_hits, base_progress_per_hit, heat_sensitivity, rhythm_min_ms, rhythm_max_ms,
               output_item_code, output_amount
        FROM blacksmith_recipes
        ORDER BY slot, level_req, name
        """
    )

    # ✅ ТУТ ГОЛОВНИЙ ФІКС: беремо input_code
    irows = await conn.fetch(
        """
        SELECT recipe_code, input_code, qty, role
        FROM blacksmith_recipe_ingredients
        WHERE input_kind='material'
        ORDER BY recipe_code, role, input_code
        """
    )

    ings_by: Dict[str, List[IngredientDTO]] = {}
    for r in irows:
        code = str(r["recipe_code"])
        ings_by.setdefault(code, []).append(
            IngredientDTO(
                material_code=str(r["input_code"]),
                qty=int(r["qty"]),
                role=str(r["role"]),
            )
        )

    out: List[RecipeDTO] = []
    for r in rrows:
        code = str(r["code"])
        hits = int(r["forge_hits"] or 60)
        base = float(r["base_progress_per_hit"] or (1.0 / max(1, hits)))
        out.append(
            RecipeDTO(
                code=code,
                name=str(r["name"]),
                slot=str(r["slot"]),
                level_req=int(r["level_req"] or 1),
                forge_hits=hits,
                base_progress_per_hit=base,
                heat_sensitivity=float(r["heat_sensitivity"] or 0.65),
                rhythm_window_ms=(int(r["rhythm_min_ms"] or 120), int(r["rhythm_max_ms"] or 220)),
                output_item_code=str(r["output_item_code"]),
                output_amount=int(r["output_amount"] or 1),
                ingredients=ings_by.get(code, []),
            )
        )
    return out


@router.get("/recipes/status", response_model=List[RecipeStatusDTO])
async def recipes_status(tg_id: int) -> List[RecipeStatusDTO]:
    if tg_id <= 0:
        raise HTTPException(400, "INVALID_TG_ID")

    await _ensure_blacksmith_tables()

    pool = await get_pool()
    async with pool.acquire() as conn:
        recipes = await _load_forge_recipes(conn)
        if not recipes:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "RECIPES_NOT_SEEDED",
                    "hint": "Заповни blacksmith_recipes та blacksmith_recipe_ingredients (migrations/seed).",
                },
            )
        all_codes: Set[str] = set()
        for rr in recipes:
            all_codes.add(str(rr.output_item_code))
            for ing in rr.ingredients:
                all_codes.add(str(ing.material_code))

        idx = await _load_code_index(conn, all_codes)
        have_items = await _player_inventory_qty_by_code(conn, tg_id)
        have_mats = await _player_materials_qty_by_code(conn, tg_id)

    out: List[RecipeStatusDTO] = []
    for r in recipes:
        meta_out = idx.get(str(r.output_item_code)) or {}
        r2 = RecipeDTO(
            code=r.code,
            name=r.name,
            output_item_code=r.output_item_code,
            output_item_name=(meta_out.get("name") or None),
            output_item_kind=(meta_out.get("kind") if meta_out.get("kind") in ("material", "item") else None),
            output_amount=int(r.output_amount or 1),
            ingredients=_decorate_ingredients(r.ingredients, idx),
        )
        ok, miss = _calc_missing_mixed(r2.ingredients, have_items, have_mats, idx)
        out.append(RecipeStatusDTO(recipe=r2, can_forge=ok, missing=miss))
    return out


@router.post("/forge/start", response_model=ForgeStartResponse)
async def forge_start(tg_id: int, body: ForgeStartBody) -> ForgeStartResponse:
    if tg_id <= 0:
        raise HTTPException(400, "INVALID_TG_ID")

    await _ensure_blacksmith_tables()

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow(
                """
                SELECT code, forge_hits, base_progress_per_hit, heat_sensitivity,
                       rhythm_min_ms, rhythm_max_ms
                FROM blacksmith_recipes
                WHERE code=$1
                """,
                body.recipe_code,
            )
            if not r:
                raise HTTPException(404, "RECIPE_NOT_FOUND")

            ingredients = await _load_recipe_ingredients(conn, body.recipe_code)
            await _deduct_mixed_inputs(conn, tg_id, ingredients)

            started_at = datetime.now(timezone.utc)
            hits = int(r["forge_hits"] or 60)
            base = float(r["base_progress_per_hit"] or (1.0 / max(1, hits)))

            row = await conn.fetchrow(
                """
                INSERT INTO player_blacksmith_forge(
                  tg_id, recipe_code, status, started_at,
                  required_hits, base_progress_per_hit, heat_sensitivity, rhythm_min_ms, rhythm_max_ms
                )
                VALUES($1,$2,'started',$3,$4,$5,$6,$7,$8)
                RETURNING id
                """,
                tg_id,
                body.recipe_code,
                started_at,
                hits,
                base,
                float(r["heat_sensitivity"] or 0.65),
                int(r["rhythm_min_ms"] or 120),
                int(r["rhythm_max_ms"] or 220),
            )
            forge_id = int(row["id"])

    return ForgeStartResponse(
        forge_id=forge_id,
        recipe_code=body.recipe_code,
        required_hits=int(r["forge_hits"] or 60),
        base_progress_per_hit=float(r["base_progress_per_hit"] or (1.0 / max(1, int(r["forge_hits"] or 60)))),
        heat_sensitivity=float(r["heat_sensitivity"] or 0.65),
        rhythm_window_ms=(int(r["rhythm_min_ms"] or 120), int(r["rhythm_max_ms"] or 220)),
    )


@router.post("/forge/cancel", response_model=ForgeCancelResponse)
async def forge_cancel(tg_id: int, body: ForgeCancelBody) -> ForgeCancelResponse:
    if tg_id <= 0:
        raise HTTPException(400, "INVALID_TG_ID")

    await _ensure_blacksmith_tables()

    pool = await get_pool()
    ingredients: List[IngredientDTO] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            f = await conn.fetchrow(
                """
                SELECT id, tg_id, recipe_code, status
                FROM player_blacksmith_forge
                WHERE id=$1
                FOR UPDATE
                """,
                body.forge_id,
            )
            if not f:
                raise HTTPException(404, "FORGE_NOT_FOUND")
            if int(f["tg_id"]) != tg_id:
                raise HTTPException(403, "FORGE_NOT_YOURS")
            if str(f["status"]) != "started":
                raise HTTPException(400, "FORGE_NOT_ACTIVE")
            if str(f["recipe_code"]) != body.recipe_code:
                raise HTTPException(400, "RECIPE_MISMATCH")

            ingredients = await _load_recipe_ingredients(conn, body.recipe_code)

            await conn.execute(
                """
                UPDATE player_blacksmith_forge
                   SET status='cancelled',
                       cancelled_at=now(),
                       client_hits=$2,
                       client_report=$3
                 WHERE id=$1
                """,
                body.forge_id,
                int((body.client_report or {}).get("hits") or 0),
                body.client_report,
            )

    pool2 = await get_pool()
    async with pool2.acquire() as conn2:
        idx = await _load_code_index(conn2, [str(i.material_code) for i in ingredients])
        for ing in ingredients:
            code = str(ing.material_code)
            qty = int(ing.qty)
            if qty <= 0:
                continue
            meta = idx.get(code) or {}
            if meta.get("kind") == "material" and meta.get("material_id"):
                await _add_material_to_player(conn2, tg_id, int(meta["material_id"]), qty)
                continue

            item_meta = await _get_item_meta(conn2, code)
            await give_item_to_player(
                tg_id=tg_id,
                item_code=code,
                name=item_meta["name"] or code,
                category=item_meta["category"],
                emoji=item_meta["emoji"],
                rarity=item_meta["rarity"],
                description=item_meta["description"],
                qty=qty,
                slot=item_meta["slot"],
            )

    return ForgeCancelResponse(ok=True, refunded=True)


@router.post("/forge/claim", response_model=ForgeClaimResponse)
async def forge_claim(tg_id: int, body: ForgeClaimBody) -> ForgeClaimResponse:
    if tg_id <= 0:
        raise HTTPException(400, "INVALID_TG_ID")

    await _ensure_blacksmith_tables()

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            f = await conn.fetchrow(
                """
                SELECT id, tg_id, recipe_code, status, required_hits, started_at
                FROM player_blacksmith_forge
                WHERE id=$1
                FOR UPDATE
                """,
                body.forge_id,
            )
            if not f:
                raise HTTPException(404, "FORGE_NOT_FOUND")
            if int(f["tg_id"]) != tg_id:
                raise HTTPException(403, "FORGE_NOT_YOURS")
            if str(f["status"]) != "started":
                raise HTTPException(400, "FORGE_NOT_ACTIVE")
            if str(f["recipe_code"]) != body.recipe_code:
                raise HTTPException(400, "RECIPE_MISMATCH")

            rr = await conn.fetchrow(
                """
                SELECT output_item_code, output_amount
                FROM blacksmith_recipes
                WHERE code=$1
                """,
                body.recipe_code,
            )
            if not rr:
                raise HTTPException(404, "RECIPE_NOT_FOUND")

            started_at = f["started_at"]
            if started_at and (datetime.now(timezone.utc) - started_at).total_seconds() < 2:
                raise HTTPException(400, "FORGE_TOO_FAST")

            client_hits = int((body.client_report or {}).get("hits") or 0)
            min_hits = max(1, int(int(f["required_hits"] or 1) * 0.40))
            if client_hits and client_hits < min_hits:
                raise HTTPException(400, detail={"code": "NOT_ENOUGH_HITS", "min_hits": min_hits})

            item_code = str(rr["output_item_code"])
            amount = int(rr["output_amount"] or 1)
            meta = await _get_item_meta(conn, item_code)

            await conn.execute(
                """
                UPDATE player_blacksmith_forge
                   SET status='claimed',
                       claimed_at=now(),
                       client_hits=$2,
                       client_report=$3
                 WHERE id=$1
                """,
                body.forge_id,
                client_hits,
                body.client_report,
            )

    await give_item_to_player(
        tg_id=tg_id,
        item_code=item_code,
        name=meta["name"] or item_code,
        category=meta["category"],
        emoji=meta["emoji"],
        rarity=meta["rarity"],
        description=meta["description"],
        qty=amount,
        slot=meta["slot"],
    )

    xp_gain = 0
    prof_state = None
    async with pool.acquire() as conn_xp:
        async with conn_xp.transaction():
            lvl_req = int((await conn_xp.fetchval("SELECT level_req FROM blacksmith_recipes WHERE code=$1", body.recipe_code)) or 1)
            xp_gain = (16 + lvl_req * 8) * max(1, amount)
            prof_state = await add_prof_xp(conn_xp, tg_id, "blacksmith", xp_gain)

    try:
        await inc_metric(tg_id, "craft_blacksmith_count", 1)
    except Exception:
        logger.exception("blacksmith: inc_metric craft_blacksmith_count FAILED tg_id={}", tg_id)

    return ForgeClaimResponse(
        ok=True,
        item_code=item_code,
        amount=amount,
        xp_gained=xp_gain,
        profession_level=(prof_state.level if prof_state else None),
        profession_xp=(prof_state.xp if prof_state else None),
    )
