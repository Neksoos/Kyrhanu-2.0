from __future__ import annotations

from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from db import get_pool

router = APIRouter(prefix="/api/craft_materials", tags=["craft_materials"])
router_public = APIRouter(prefix="/craft_materials", tags=["craft_materials"])


def _category(code: str) -> str:
    if code.startswith("alch_flask_"):
        return "flask"
    if code.startswith("alch_base_"):
        return "base"
    return "other"


@router.get("/brief")
@router_public.get("/brief")
async def craft_materials_brief(q: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Короткий довідник матеріалів для UI (code -> name).
    Повертає ВСІ craft_materials.

    Формат: [{ "code": "...", "name": "..." }, ...]
    """
    pool = await get_pool()

    if q and q.strip():
        qq = q.strip()
        rows = await pool.fetch(
            """
            SELECT code, name
            FROM craft_materials
            WHERE code ILIKE '%' || $1 || '%'
               OR name ILIKE '%' || $1 || '%'
            ORDER BY id ASC
            """,
            qq,
        )
    else:
        rows = await pool.fetch(
            """
            SELECT code, name
            FROM craft_materials
            ORDER BY id ASC
            """
        )

    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "code": str(r["code"]),
                "name": r["name"],
            }
        )
    return out


@router.get("/shop")
@router_public.get("/shop")
async def craft_materials_shop(q: Optional[str] = None) -> Dict[str, Any]:
    """
    Реміснича лавка (тільки shop-матеріали алхімії):
    - alch_flask_*
    - alch_base_*
    """
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT
            id,
            code,
            name,
            descr,
            appearance_text
        FROM craft_materials
        WHERE code LIKE 'alch_flask_%'
           OR code LIKE 'alch_base_%'
        ORDER BY
          CASE
            WHEN code LIKE 'alch_flask_%' THEN 1
            WHEN code LIKE 'alch_base_%' THEN 2
            ELSE 9
          END,
          id ASC
        """
    )

    items: List[Dict[str, Any]] = []

    for r in rows:
        code = str(r["code"])
        items.append(
            {
                "id": int(r["id"]),
                "code": code,
                "name": r["name"],
                "descr": r["descr"],
                "appearance_text": r["appearance_text"],
                "category": _category(code),
                "price": None,
            }
        )

    if q and q.strip():
        qq = q.lower().strip()
        items = [
            i
            for i in items
            if qq in (i["name"] or "").lower()
            or qq in (i["code"] or "").lower()
            or qq in (i["descr"] or "").lower()
            or qq in (i["appearance_text"] or "").lower()
        ]

    return {"ok": True, "items": items}


@router.get("/list")
@router_public.get("/list")
async def craft_materials_list(q: Optional[str] = None) -> Dict[str, Any]:
    """
    BACKWARD-COMPAT:
    Раніше /list був alias на /shop і віддавав ТІЛЬКИ алхімію.
    Це ламало куванння (smith_*), бо назви інгредієнтів не приходили.

    Тепер /list повертає ВСІ craft_materials.
    """
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT
            id,
            code,
            name,
            descr,
            profession,
            source_type,
            rarity,
            appearance_text
        FROM craft_materials
        ORDER BY
            profession NULLS LAST,
            source_type NULLS LAST,
            rarity NULLS LAST,
            name ASC,
            id ASC
        """
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        code = str(r["code"])
        items.append(
            {
                "id": int(r["id"]),
                "code": code,
                "name": r["name"],
                "descr": r["descr"],
                "appearance_text": r["appearance_text"],
                "profession": r["profession"],
                "source_type": r["source_type"],
                "rarity": r["rarity"],
                "category": _category(code),
                "price": None,
            }
        )

    if q and q.strip():
        qq = q.lower().strip()
        items = [
            i
            for i in items
            if qq in (i.get("name") or "").lower()
            or qq in (i.get("code") or "").lower()
            or qq in (i.get("descr") or "").lower()
            or qq in (i.get("appearance_text") or "").lower()
        ]

    return {"ok": True, "items": items}