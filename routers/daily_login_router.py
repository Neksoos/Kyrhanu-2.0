from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from routers.auth import get_tg_id
from services.daily_login import process_daily_login  # type: ignore

router = APIRouter(prefix="/api/daily-login", tags=["daily-login"])


class DailyLoginResponse(BaseModel):
    xp_gain: int
    coins_gain: int
    got_kleynod: bool


@router.post("/claim", response_model=DailyLoginResponse)
async def claim_daily_login(tg_id: int = Depends(get_tg_id)) -> DailyLoginResponse:
    xp_gain, coins_gain, got_kleynod = await process_daily_login(tg_id)
    return DailyLoginResponse(
        xp_gain=int(xp_gain or 0),
        coins_gain=int(coins_gain or 0),
        got_kleynod=bool(got_kleynod),
    )
