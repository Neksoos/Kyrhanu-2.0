from __future__ import annotations

import os
import httpx
from fastapi import APIRouter, Request, HTTPException

from db import get_pool

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TG_WEBHOOK_SECRET = os.getenv("TG_WEBHOOK_SECRET", "").strip()
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

router = APIRouter(prefix="/tg", tags=["telegram"])


async def _tg_call(method: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{TG_API}/{method}", json=payload)
        r.raise_for_status()
        data = r.json()

    if not data.get("ok"):
        # важливо бачити причину в логах/помилках
        raise RuntimeError(f"telegram_error: {data}")

    return data


@router.post("/webhook")
async def webhook(request: Request):
    if TG_WEBHOOK_SECRET:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if got != TG_WEBHOOK_SECRET:
            raise HTTPException(403, "bad_webhook_secret")

    if not BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN not configured")

    update = await request.json()

    # 1) pre_checkout_query
    pcq = update.get("pre_checkout_query")
    if pcq:
        query_id = pcq["id"]
        payload = pcq.get("invoice_payload", "")
        from_id = int(pcq.get("from", {}).get("id", 0))
        currency = pcq.get("currency")
        total_amount = int(pcq.get("total_amount", 0))

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT tg_id, status, amount_xtr
                FROM tg_stars_orders
                WHERE payload=$1
                """,
                payload,
            )

        ok = True
        err = None

        if not row or int(row["tg_id"]) != from_id:
            ok = False
            err = "Замовлення не знайдено або недійсне."
        elif row["status"] == "paid":
            ok = False
            err = "Замовлення вже оплачено."
        elif currency != "XTR" or total_amount != int(row["amount_xtr"]):
            ok = False
            err = "Невірна сума або валюта."

        # відповідаємо Telegram максимально швидко
        try:
            await _tg_call(
                "answerPreCheckoutQuery",
                {
                    "pre_checkout_query_id": query_id,
                    "ok": ok,
                    **({"error_message": err} if (not ok and err) else {}),
                },
            )
        except Exception:
            # якщо тут впаде — Telegram може повторити апдейт, а нам це навіть корисно
            raise HTTPException(502, "answerPreCheckoutQuery_failed")

        # статус оновлюємо вже після відповіді (і обережно)
        if ok:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE tg_stars_orders
                    SET status='pre_checkout_ok', updated_at=now()
                    WHERE payload=$1
                      AND status IN ('created','pre_checkout_ok')
                    """,
                    payload,
                )

        return {"ok": True}

    # 2) successful_payment
    msg = update.get("message") or {}
    sp = msg.get("successful_payment")
    if sp:
        payload = sp.get("invoice_payload", "")
        currency = sp.get("currency")
        total_amount = int(sp.get("total_amount", 0))
        charge_id = sp.get("telegram_payment_charge_id")

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                order = await conn.fetchrow(
                    """
                    SELECT tg_id, amount_xtr, grant_kleynody, status
                    FROM tg_stars_orders
                    WHERE payload=$1
                    FOR UPDATE
                    """,
                    payload,
                )
                if not order:
                    return {"ok": True}

                if order["status"] == "paid":
                    return {"ok": True}

                if currency != "XTR" or total_amount != int(order["amount_xtr"]):
                    await conn.execute(
                        """
                        UPDATE tg_stars_orders
                        SET status='error_amount', currency=$2, total_amount=$3, updated_at=now()
                        WHERE payload=$1
                        """,
                        payload, currency, total_amount,
                    )
                    return {"ok": True}

                await conn.execute(
                    """
                    UPDATE tg_stars_orders
                    SET status='paid',
                        currency=$2,
                        total_amount=$3,
                        telegram_payment_charge_id=$4,
                        paid_at=now(),
                        updated_at=now()
                    WHERE payload=$1
                    """,
                    payload, currency, total_amount, charge_id,
                )

                tg_id = int(order["tg_id"])
                grant = int(order["grant_kleynody"])

                await conn.execute(
                    """
                    UPDATE players
                    SET kleynody = COALESCE(kleynody,0) + $1
                    WHERE tg_id=$2
                    """,
                    grant, tg_id,
                )

        return {"ok": True}

    return {"ok": True}