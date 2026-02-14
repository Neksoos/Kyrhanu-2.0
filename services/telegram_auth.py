"""
Telegram WebApp authentication.
Verifies initData using HMAC SHA-256 as per Telegram docs.
"""
import hmac
import hashlib
import urllib.parse
import json
from typing import Optional, Dict, Any

from config import settings


class TelegramAuthError(Exception):
    pass


def verify_telegram_init_data(init_data: str) -> Optional[Dict[str, Any]]:
    """
    Verify Telegram WebApp initData.
    Returns parsed data if valid, None otherwise.
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise TelegramAuthError("TELEGRAM_BOT_TOKEN not configured")
    
    # Parse init data
    parsed = _parse_init_data(init_data)
    if not parsed:
        return None
    
    received_hash = parsed.pop('hash', None)
    if not received_hash:
        return None
    
    # Create data check string (sorted by key)
    data_check_string = _create_data_check_string(parsed)
    
    # Calculate secret key
    secret_key = hmac.new(
        b"WebAppData",
        settings.TELEGRAM_BOT_TOKEN.encode(),
        hashlib.sha256
    ).digest()
    
    # Calculate expected hash
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    # Verify
    if not hmac.compare_digest(expected_hash, received_hash):
        return None
    
    # Check auth date (prevent replay attacks)
    auth_date = parsed.get('auth_date')
    if auth_date:
        import time
        # Allow 24 hour window
        if time.time() - int(auth_date) > 86400:
            return None
    
    return parsed


def verify_telegram_login_widget(data: Dict[str, Any]) -> bool:
    """Verify Telegram Login Widget payload (browser auth).

    Telegram docs: https://core.telegram.org/widgets/login
    """
    if not settings.TELEGRAM_BOT_TOKEN:
        raise TelegramAuthError("TELEGRAM_BOT_TOKEN not configured")

    if not isinstance(data, dict):
        return False

    received_hash = data.get("hash")
    if not received_hash:
        return False

    # Data check string: key=value sorted by key, excluding hash
    pairs = []
    for k in sorted(data.keys()):
        if k == "hash":
            continue
        v = data[k]
        if v is None:
            continue
        pairs.append(f"{k}={v}")
    data_check_string = "\n".join(pairs)

    # secret key is sha256(bot_token)
    secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return False

    # Check auth_date (anti-replay)
    auth_date = data.get("auth_date")
    if auth_date:
        import time
        if time.time() - int(auth_date) > 86400:
            return False

    return True


def _parse_init_data(init_data: str) -> Dict[str, Any]:
    """Parse URL-encoded init data string."""
    try:
        result = {}
        for pair in init_data.split('&'):
            if '=' in pair:
                key, value = pair.split('=', 1)
                result[key] = urllib.parse.unquote(value)
        
        # Parse user JSON
        if 'user' in result:
            result['user'] = json.loads(result['user'])
        
        return result
    except Exception:
        return {}


def _create_data_check_string(data: Dict[str, Any]) -> str:
    """Create data check string for HMAC verification."""
    items = []
    for key in sorted(data.keys()):
        if key == 'hash':
            continue
        value = data[key]
        if isinstance(value, dict):
            value = json.dumps(value, separators=(',', ':'))
        items.append(f"{key}={value}")
    
    return '\n'.join(items)


def extract_user_info(parsed_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract user info from parsed init data."""
    user_data = parsed_data.get('user')
    if not user_data:
        return None
    
    return {
        'tg_id': user_data.get('id'),
        'username': user_data.get('username'),
        'first_name': user_data.get('first_name'),
        'last_name': user_data.get('last_name'),
        'language_code': user_data.get('language_code'),
        'is_premium': user_data.get('is_premium', False),
        'photo_url': user_data.get('photo_url')
    }