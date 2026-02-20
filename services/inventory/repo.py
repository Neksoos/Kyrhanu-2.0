# services/inventory/repo.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException

from db import get_pool
from services.inventory.migrations import (
    ensure_items_columns,
    ensure_player_inventory_columns,
    ensure_players_columns,
)
from services.inventory.utils import normalize_slot, stackable


async def give_item_to_player_repo(
    tg_id: int,
    *,
    item_code: str,
    name: str,
    category: Optional[str] = None,
    emoji: Optional[str] = None,
    rarity: Optional[str] = None,
    description: Optional[str] = None,
    stats: Optional[Dict[str, Any]] = None,
    qty: Optional[int] = None,
    amount: Optional[int] = None,
    slot: Optional[str] = None,
) -> None:
    """
    Правило:
      - Стекові (stackable=True та items.slot IS NULL) → один рядок, slot=NULL, qty=N.
      - Не-стек або екіп → кожен екземпляр окремим рядком, slot=items.slot (НЕ NULL), qty=1.
    Автодоповнює незаповнені поля вже наявних items, щоб уникнути порожніх описів чи NULL-полів.
    """
    final_qty = qty if qty is not None else (amount if amount is not None else 1)
    try:
        final_qty = int(final_qty)
    except Exception:
        final_qty = 1

    if final_qty <= 0:
        return

    await ensure_items_columns()
    await ensure_player_inventory_columns()

    pool = await get_pool()

    code = (item_code or "").strip()
    if not code:
        raise HTTPException(400, "INVALID_ITEM_CODE")

    stats_json: Dict[str, Any] = stats or {}
    slot_norm = normalize_slot(slot)
    desc_norm: str = (description or "").strip()

    async with pool.acquire() as conn:
        item_row = await conn.fetchrow(
            """
            SELECT id, stackable, slot, category, emoji, rarity, description, stats, name
            FROM items
            WHERE code = $1
            """,
            code,
        )

        # Якщо предмета немає, створимо запис в items
        if not item_row:
            stack_flag = stackable(category)
            await conn.execute(
                """
                INSERT INTO items(
                    code, name, category, emoji, rarity,
                    slot, stats, stackable, description
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NULLIF($9,''))
                ON CONFLICT (code) DO NOTHING
                """,
                code,
                (name or code),
                category,
                emoji,
                rarity,
                slot_norm,
                stats_json,
                stack_flag,
                desc_norm,
            )
            item_row = await conn.fetchrow(
                """
                SELECT id, stackable, slot, category, emoji, rarity, description, stats, name
                FROM items
                WHERE code = $1
                """,
                code,
            )

        if not item_row:
            raise HTTPException(500, "ITEM_CREATE_FAILED")

        item_id = int(item_row["id"])
        item_slot = normalize_slot(item_row["slot"])

        # Заповнюємо порожні поля існуючого предмета даними з аргументів
        updates: Dict[str, Any] = {}
        db_name = (item_row.get("name") or "").strip()
        if not db_name and (name or "").strip():
            updates["name"] = (name or code).strip()
        db_desc = (item_row.get("description") or "").strip()
        if not db_desc and desc_norm:
            updates["description"] = desc_norm
        db_rarity = (item_row.get("rarity") or "").strip()
        if not db_rarity and (rarity or "").strip():
            updates["rarity"] = (rarity or "").strip()
        db_emoji = (item_row.get("emoji") or "").strip()
        if not db_emoji and (emoji or "").strip():
            updates["emoji"] = (emoji or "").strip()
        db_cat = (item_row.get("category") or "").strip()
        if not db_cat and (category or "").strip():
            updates["category"] = (category or "").strip()
        db_stats = item_row.get("stats")
        if (db_stats is None or db_stats == {}) and stats is not None:
            updates["stats"] = stats_json
        if item_slot is None and slot_norm:
            updates["slot"] = slot_norm
            item_slot = slot_norm

        if updates:
            cols = list(updates.keys())
            set_sql = ", ".join([f"{c} = ${i+2}" for i, c in enumerate(cols)])
            values = [updates[c] for c in cols]
            await conn.execute(
                f"UPDATE items SET {set_sql} WHERE id = $1",
                item_id,
                *values,
            )

        # Логіка стекування: якщо предмет stackable і slot == NULL, об’єднуємо в один запис
        item_cat = (item_row["category"] if "category" in item_row else None) or category
        stack_flag = (bool(item_row["stackable"]) if "stackable" in item_row else False) or stackable(item_cat)
        if stack_flag and item_slot is None:
            try:
                await conn.execute(
                    """
                    INSERT INTO player_inventory (tg_id, item_id, qty, is_equipped, slot, created_at, updated_at)
                    VALUES ($1, $2, $3, FALSE, NULL, NOW(), NOW())
                    ON CONFLICT (tg_id, item_id)
                    WHERE slot IS NULL AND is_equipped = FALSE
                    DO UPDATE
                    SET qty = player_inventory.qty + EXCLUDED.qty,
                        updated_at = NOW()
                    """,
                    tg_id,
                    item_id,
                    final_qty,
                )
                return
            except Exception:
                updated = await conn.execute(
                    """
                    UPDATE player_inventory
                    SET qty = qty + $3, updated_at = NOW()
                    WHERE tg_id = $1
                      AND item_id = $2
                      AND slot IS NULL
                      AND is_equipped = FALSE
                    """,
                    tg_id,
                    item_id,
                    final_qty,
                )
                if isinstance(updated, str) and updated.endswith(" 0"):
                    await conn.execute(
                        """
                        INSERT INTO player_inventory(tg_id, item_id, qty, is_equipped, slot, created_at, updated_at)
                        VALUES ($1, $2, $3, FALSE, NULL, NOW(), NOW())
                        """,
                        tg_id,
                        item_id,
                        final_qty,
                    )
                return

        # Якщо предмет не стековий або має слот – додаємо кожен екземпляр окремо
        final_slot = item_slot or slot_norm
        if not final_slot:
            raise HTTPException(400, "ITEM_HAS_NO_SLOT")
        for _ in range(final_qty):
            await conn.execute(
                """
                INSERT INTO player_inventory(tg_id, item_id, qty, is_equipped, slot, created_at, updated_at)
                VALUES ($1,$2,1,FALSE,$3,NOW(),NOW())
                """,
                tg_id,
                item_id,
                final_slot,
            )


async def equip_repo(inv_id: int, tg_id: int) -> None:
    """
    Екіпування: не скидаємо slot у NULL, swap виконується без проміжного стану, щоб уникнути конфліктів індексів.
    """
    await ensure_items_columns()
    await ensure_player_inventory_columns()

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT pi.id AS inv_id, pi.tg_id,
                       COALESCE(pi.qty,1) AS qty,
                       COALESCE(pi.is_equipped,FALSE) AS is_equipped,
                       pi.slot AS inv_slot,
                       pi.item_id AS item_id,
                       i.slot AS item_slot
                FROM player_inventory pi
                JOIN items i ON i.id = pi.item_id
                WHERE pi.id = $1 AND pi.tg_id = $2
                FOR UPDATE
                """,
                inv_id,
                tg_id,
            )
            if not row:
                raise HTTPException(404, "ITEM_NOT_FOUND")
            if int(row["qty"] or 1) != 1:
                raise HTTPException(400, "CANNOT_EQUIP_STACK")
            slot = normalize_slot(row["item_slot"] or row["inv_slot"])
            if not slot:
                raise HTTPException(400, "ITEM_HAS_NO_SLOT")

            # Знімаємо поточний екіп у слоті, якщо це інший предмет
            cur = await conn.fetchrow(
                """
                SELECT id FROM player_inventory
                WHERE tg_id = $1
                  AND slot = $2
                  AND is_equipped = TRUE
                FOR UPDATE
                """,
                tg_id,
                slot,
            )
            if cur and int(cur["id"]) != int(inv_id):
                await conn.execute(
                    """
                    UPDATE player_inventory
                    SET is_equipped = FALSE, updated_at = NOW()
                    WHERE id = $1 AND tg_id = $2
                    """,
                    int(cur["id"]),
                    tg_id,
                )
            # Екіпуємо обраний
            await conn.execute(
                """
                UPDATE player_inventory
                SET is_equipped = TRUE,
                    slot = $3,
                    updated_at = NOW()
                WHERE id = $1 AND tg_id = $2
                """,
                inv_id,
                tg_id,
                slot,
            )


async def unequip_repo(inv_id: int, tg_id: int) -> None:
    """
    Знімає екіпування. Не скидає slot у NULL, просто is_equipped = FALSE.
    """
    await ensure_items_columns()
    await ensure_player_inventory_columns()

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE player_inventory
            SET is_equipped = FALSE,
                updated_at = NOW()
            WHERE id = $1 AND tg_id = $2
            """,
            inv_id,
            tg_id,
        )


async def unequip_slot_repo(slot: str, tg_id: int) -> None:
    """
    Знімає всі предмети з певного слоту. Не скидає slot у NULL, тільки is_equipped.
    """
    await ensure_items_columns()
    await ensure_player_inventory_columns()

    slot = normalize_slot(slot)
    if not slot:
        raise HTTPException(400, "INVALID_SLOT")

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE player_inventory
            SET is_equipped = FALSE,
                updated_at = NOW()
            WHERE tg_id = $1
              AND slot = $2
              AND is_equipped = TRUE
            """,
            tg_id,
            slot,
        )


async def list_inventory_rows(tg_id: int):
    await ensure_items_columns()
    await ensure_player_inventory_columns()

    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT
                pi.id      AS inv_id,
                pi.item_id AS item_id,
                pi.qty     AS qty,
                pi.is_equipped AS is_equipped,
                pi.slot    AS inv_slot,
                i.code     AS item_code,
                i.emoji    AS emoji,
                i.name     AS name,
                i.description AS description,
                i.rarity   AS rarity,
                i.slot     AS item_slot,
                i.category AS category,
                i.stats    AS stats,
                i.atk      AS atk,
                i.defense  AS defense,
                i.hp       AS hp,
                i.mp       AS mp,
                i.weight   AS weight
            FROM player_inventory pi
            JOIN items i ON i.id = pi.item_id
            WHERE pi.tg_id = $1
            ORDER BY pi.is_equipped DESC, i.rarity NULLS LAST, i.name
            """,
            tg_id,
        )


async def get_item_row(inv_id: int, tg_id: int):
    await ensure_items_columns()
    await ensure_player_inventory_columns()

    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT
                pi.id           AS inv_id,
                pi.item_id      AS item_id,
                pi.qty          AS qty,
                pi.is_equipped  AS is_equipped,
                pi.slot         AS inv_slot,
                i.code          AS item_code,
                i.emoji         AS emoji,
                i.name          AS name,
                i.description   AS description,
                i.rarity        AS rarity,
                i.slot          AS item_slot,
                i.category      AS category,
                i.stats         AS stats,
                i.atk           AS atk,
                i.defense       AS defense,
                i.hp            AS hp,
                i.mp            AS mp,
                i.weight        AS weight
            FROM player_inventory pi
            JOIN items i ON i.id = pi.item_id
            WHERE pi.id = $1 AND pi.tg_id = $2
            """,
            inv_id,
            tg_id,
        )


async def consume_repo(inv_id: int, tg_id: int, want_qty: int) -> Dict[str, int]:
    await ensure_items_columns()
    await ensure_player_inventory_columns()
    await ensure_players_columns()

    try:
        want = int(want_qty or 1)
    except Exception:
        want = 1
    if want <= 0:
        want = 1
    if want > 50:
        want = 50

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
              pi.id AS inv_id,
              pi.tg_id,
              pi.qty,
              pi.is_equipped,
              pi.slot AS inv_slot,
              i.category,
              i.stats,
              i.hp AS item_hp,
              i.mp AS item_mp
            FROM player_inventory pi
            JOIN items i ON i.id = pi.item_id
            WHERE pi.id = $1 AND pi.tg_id = $2
            """,
            inv_id,
            tg_id,
        )
        if not row:
            raise HTTPException(404, "ITEM_NOT_FOUND")

        if bool(row["is_equipped"]):
            raise HTTPException(400, "ITEM_NOT_USABLE")

        if row["inv_slot"] is not None:
            raise HTTPException(400, "ITEM_NOT_USABLE")

        have = int(row["qty"] or 0)
        if have <= 0:
            raise HTTPException(400, "NOT_ENOUGH_QTY")

        use_qty = min(have, want)

        category = (row["category"] or "").strip().lower()
        base_stats: Dict[str, Any] = dict(row["stats"] or {})

        hp_restore = int(base_stats.get("hp", 0) or 0) + int(row["item_hp"] or 0)
        mp_restore = int(base_stats.get("mp", 0) or 0) + int(row["item_mp"] or 0)
        energy_restore = int(base_stats.get("energy", 0) or 0)

        allowed_cat = category.startswith(("food", "potion", "consum"))
        if not allowed_cat and (hp_restore <= 0 and mp_restore <= 0 and energy_restore <= 0):
            raise HTTPException(400, "ITEM_NOT_USABLE")

        hp_restore *= use_qty
        mp_restore *= use_qty
        energy_restore *= use_qty

        # списання предмета зі стека
        if have - use_qty <= 0:
            await conn.execute(
                "DELETE FROM player_inventory WHERE id=$1 AND tg_id=$2",
                inv_id,
                tg_id,
            )
            remaining_qty = 0
        else:
            await conn.execute(
                """
                UPDATE player_inventory
                SET qty = qty - $3,
                    updated_at = NOW()
                WHERE id=$1 AND tg_id=$2
                """,
                inv_id,
                tg_id,
                use_qty,
            )
            remaining_qty = have - use_qty

        # застосування ефектів із капами
        p = await conn.fetchrow(
            """
            SELECT hp, mp, energy, hp_max, mp_max, energy_max
            FROM players
            WHERE tg_id=$1
            """,
            tg_id,
        )
        if not p:
            raise HTTPException(404, "PLAYER_NOT_FOUND")

        hp_max = int(p["hp_max"] or 100)
        mp_max = int(p["mp_max"] or 50)
        energy_max = int(p["energy_max"] or 240)

        cur_hp = int(p["hp"]) if p["hp"] is not None else hp_max
        cur_mp = int(p["mp"]) if p["mp"] is not None else mp_max
        cur_en = int(p["energy"]) if p["energy"] is not None else energy_max

        new_hp = min(hp_max, cur_hp + hp_restore) if hp_restore > 0 else cur_hp
        new_mp = min(mp_max, cur_mp + mp_restore) if mp_restore > 0 else cur_mp
        new_en = min(energy_max, cur_en + energy_restore) if energy_restore > 0 else cur_en

        await conn.execute(
            """
            UPDATE players
            SET hp=$2, mp=$3, energy=$4
            WHERE tg_id=$1
            """,
            tg_id,
            new_hp,
            new_mp,
            new_en,
        )

    return {
        "used_qty": use_qty,
        "remaining_qty": remaining_qty,
        "hp": new_hp,
        "hp_max": hp_max,
        "mp": new_mp,
        "mp_max": mp_max,
        "energy": new_en,
        "energy_max": energy_max,
    }