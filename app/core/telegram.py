import hmac
import hashlib
import time
from urllib.parse import parse_qsl
from app.core.config import settings

def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()

def verify_telegram_webapp_initdata(init_data: str, max_age_sec: int | None = None) -> dict:
    """
    Telegram WebApp initData verification:
    - parse key=value pairs
    - build data_check_string with sorted keys excluding 'hash'
    - secret_key = HMAC_SHA256("WebAppData", bot_token)
    - hash = HMAC_SHA256(secret_key, data_check_string)
    """
    if max_age_sec is None:
        max_age_sec = settings.TELEGRAM_WEBAPP_MAX_AGE_SEC

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing hash")

    # Optional time check if auth_date present
    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date:
        now = int(time.time())
        if now - auth_date > max_age_sec:
            raise ValueError("initData expired")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))
    secret_key = _hmac_sha256(b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode("utf-8"))
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Bad initData hash")

    # user field is JSON string in initData; front can send parsed too, but we keep as-is here
    return pairs

def verify_telegram_login_widget(payload: dict) -> dict:
    """
    Telegram Login Widget verification:
    - payload contains: id, first_name, username, auth_date, hash, etc.
    - data_check_string: sorted key=value excluding hash
    - secret_key = sha256(bot_token)
    - hash = HMAC_SHA256(secret_key, data_check_string)
    """
    received_hash = payload.get("hash")
    if not received_hash:
        raise ValueError("Missing hash")

    auth_date = int(payload.get("auth_date", 0))
    if auth_date:
        now = int(time.time())
        if now - auth_date > settings.TELEGRAM_WEBAPP_MAX_AGE_SEC:
            raise ValueError("widget payload expired")

    data = {k: str(v) for k, v in payload.items() if k != "hash" and v is not None}
    data_check_string = "\n".join(f"{k}={data[k]}" for k in sorted(data.keys()))
    token = (settings.TELEGRAM_WIDGET_BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN).encode("utf-8")
    secret_key = hashlib.sha256(token).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Bad widget hash")
    return payload