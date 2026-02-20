# src/services/npc_roamer.py

import time
from typing import Optional, Tuple, Dict, Any, Callable

from .npc_engine import PlayerContext, maybe_pick_npc  # ✅ беремо єдину логіку
# прибери імпорт all_npcs, NpcDef, SpawnRules — вони більше не потрібні

# замість _COOLDOWNS/_LAST_OFFER можеш лишити тільки _LAST_OFFER
_LAST_OFFER: Dict[int, str] = {}
_LEVEL_PROVIDER: Optional[Callable[[int], int]] = None

def _player_level(uid: int) -> int:
    if callable(_LEVEL_PROVIDER):
        try:
            return int(_LEVEL_PROVIDER(uid))
        except Exception:
            return 1
    return 1

async def _render_screen_patched(*args, **kwargs):
    uid, screen_key = _get_uid_and_screen(args, kwargs)

    if uid is not None and screen_key:
        deny = any(screen_key.startswith(p) for p in _DENY_SCREENS_PREFIX)
        if not deny:
            hour = int(time.localtime().tm_hour)
            lvl = _player_level(uid)

            ctx = PlayerContext(
                uid=uid,
                level=lvl,
                screen_key=_area_of(screen_key),  # або screen_key, залежно як ти хочеш правила
                hour=hour,
            )

            data = maybe_pick_npc(ctx, force=False)  # ✅ одна логіка з API
            if data:
                btn_text = f"✨ Зустріти {data.get('name','NPC')}"
                cb_data = f"npc:meet:{data.get('key')}"
                kwargs["reply_markup"] = _append_button(
                    kwargs.get("reply_markup") or kwargs.get("keyboard"),
                    btn_text,
                    cb_data,
                )

    return await _original_render_screen(*args, **kwargs)