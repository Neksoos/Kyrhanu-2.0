"""Pydantic request/response schemas for the API."""
from typing import Optional

from pydantic import BaseModel, Field
from pydantic import EmailStr


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., description="Telegram WebApp initData")


class TelegramWidgetAuthRequest(BaseModel):
    """Payload from Telegram Login Widget (browser auth)."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    age_confirm: bool = False


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class TapRequest(BaseModel):
    client_timestamp: int = Field(..., description="Client unix timestamp in ms")
    sequence_number: int = Field(..., ge=1, description="Monotonic counter from client")
    nonce: str = Field(..., min_length=8, max_length=128)


class DailyChoiceRequest(BaseModel):
    choice: str


class BuyItemRequest(BaseModel):
    item_key: str


class PurchasePackRequest(BaseModel):
    pack_key: str
    payment_method: str = "stripe"


class CreateGuildRequest(BaseModel):
    name: str
    tag: Optional[str] = None


class JoinGuildRequest(BaseModel):
    guild_id: int


class BossAttackRequest(BaseModel):
    boss_id: int
    use_kleynodu: int = 0


class ReferralClaimRequest(BaseModel):
    referral_code: str


class ShareRequest(BaseModel):
    share_type: str