from __future__ import annotations

import os
import time
import uuid
from typing import Dict, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from db import get_pool
from models.player import PlayerDTO
from routers.auth import get_player  # ✅ перевіряє initData і що гравець існує

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

router = APIRouter(prefix="/api/stars", tags=["stars"])

# ✅ Твої паки (SKU → ціна XTR → скільки клейнодів нарахувати)
PRODUCTS: Dict[str, Dict[str, Any]] = {
    "kleynody_starter": {
        "title": "Стартовий вогник",
        "description": "50 клейнодів на баланс.",
        "amount_xtr": 120,
        "grant_kleynody": 50,
    },
    "kleynody_hunter": {
        "title": "Набіг мандрівника",
        "description": "140 клейнодів (+10% включено).",
        "amount_xtr": 300,
        "grant_kleynody": 140,
    },
    "kleynody_warlord": {
        "title": "Скарб ватажка",
        "description": "320 клейнодів (+18% включено).",
        "amount_xtr": 640,
        "grant_kleynody": 320,
    },
    "kleynody_legend": {
        "title": "Легендарний сховок",
        "description": "700 клейнодів (+25% включено).",
        "amount_xtr": 1300,
        "grant_kleynody": 700,
    },
}


class CreateInvoiceIn(BaseModel):
    sku: str


class CreateInvoiceOut(BaseModel):
    ok: bool = True
    invoice_link: str


@router.get("/catalog")
async def catalog():
    return {"ok": True, "products": PRODUCTS}


@router.post("/create-invoice", response_model=CreateInvoiceOut)
async def create_invoice(
    body: CreateInvoiceIn,
    player: PlayerDTO = Depends(get_player),
) -> CreateInvoiceOut:
    if not BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN not configured")

    sku = (body.sku or "").strip()
    p = PRODUCTS.get(sku)
    if not p:
        raise HTTPException(404, "unknown_sku")

    payload = f"{player.tg_id}:{sku}:{int(time.time())}:{uuid.uuid4().hex}"

    # 1) записуємо замовлення в БД (для ідемпотентності)
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tg_stars_orders (payload, tg_id, sku, amount_xtr, grant_kleynody, status)
            VALUES ($1, $2, $3, $4, $5, 'created')
            """,
            payload,
            int(player.tg_id),
            sku,
            int(p["amount_xtr"]),
            int(p["grant_kleynody"]),
        )

    # 2) створюємо інвойс-лінк у Telegram
    # Для Stars валюта XTR, provider_token для цифрового можна не передавати. 1
    req = {
        "title": str(p["title"]),
        "description": str(p["description"]),
        "payload": payload,
        "currency": "XTR",
        "prices": [{"label": str(p["title"]), "amount": int(p["amount_xtr"])}],
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{TG_API}/createInvoiceLink", json=req)
            data = r.json()
    except Exception as e:
        raise HTTPException(502, f"telegram_createInvoiceLink_failed: {e}")

    if not data.get("ok"):
        raise HTTPException(502, f"telegram_error: {data}")

    return CreateInvoiceOut(invoice_link=str(data["result"]))