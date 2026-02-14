"""Pydantic request/response schemas for the API.

This module defines all of the data transfer objects used by the backend.
Originally, the `RegisterRequest` model used the `EmailStr` type from
``pydantic``. That type depends on the optional ``email-validator``
package, which wasn't available in the provided environment and caused
runtime ``ImportError`` exceptions (see logs). To avoid this hard
dependency while still providing basic validation, the model below
stores the email as a plain string and validates it with a simple
regular expression. If stricter validation is desired, the optional
dependency can still be installed and the original behaviour restored.
"""

from typing import Optional
import re

from pydantic import BaseModel, Field, validator


class TelegramAuthRequest(BaseModel):
    """Payload from the Telegram Mini App used for initial authentication."""
    init_data: str = Field(..., description="Telegram WebApp initData")


class TelegramWidgetAuthRequest(BaseModel):
    """Payload from the Telegram Login Widget (browser auth)."""
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class RegisterRequest(BaseModel):
    """Request payload for email/password registration.

    The ``email`` field is a simple string validated against a minimal
    regular expression. This avoids the optional dependency on
    ``email-validator`` while still rejecting obviously invalid values.
    """

    username: str
    email: str
    password: str
    age_confirm: bool = False

    @validator("email")
    def validate_email(cls, value: str) -> str:
        # A minimal regex for an email address. It allows most common
        # patterns but does not enforce full RFC compliance. Replace
        # this with your own validation if needed.
        pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        if not pattern.match(value):
            raise ValueError("Invalid email address")
        return value


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