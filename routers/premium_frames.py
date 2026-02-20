from __future__ import annotations
from typing import Dict, Any

FRAMES_CATALOG: Dict[str, Dict[str, Any]] = {
    "frame_wood_carved": {"kind": "frame", "title": "Рамка: різьблене дерево", "price_kleynody": 90, "icon": "/premium/frame_wood_carved_icon.png", "overlay": "/premium/frame_wood_carved_overlay.png"},
    "frame_iron_rivets": {"kind": "frame", "title": "Рамка: залізні заклепки", "price_kleynody": 120, "icon": "/premium/frame_iron_rivets_icon.png", "overlay": "/premium/frame_iron_rivets_overlay.png"},
    "frame_runic": {"kind": "frame", "title": "Рамка: рунична", "price_kleynody": 160, "icon": "/premium/frame_runic_icon.png", "overlay": "/premium/frame_runic_overlay.png"},
    "frame_moonlit": {"kind": "frame", "title": "Рамка: місячна", "price_kleynody": 170, "icon": "/premium/frame_moonlit_icon.png", "overlay": "/premium/frame_moonlit_overlay.png"},
    "frame_obsidian": {"kind": "frame", "title": "Рамка: обсидіан", "price_kleynody": 150, "icon": "/premium/frame_obsidian_icon.png", "overlay": "/premium/frame_obsidian_overlay.png"},
    "frame_bone": {"kind": "frame", "title": "Рамка: кістяна", "price_kleynody": 140, "icon": "/premium/frame_bone_icon.png", "overlay": "/premium/frame_bone_overlay.png"},
    "frame_amber": {"kind": "frame", "title": "Рамка: бурштин", "price_kleynody": 160, "icon": "/premium/frame_amber_icon.png", "overlay": "/premium/frame_amber_overlay.png"},
    "frame_silver": {"kind": "frame", "title": "Рамка: срібло", "price_kleynody": 180, "icon": "/premium/frame_silver_icon.png", "overlay": "/premium/frame_silver_overlay.png"},
    "frame_gold": {"kind": "frame", "title": "Рамка: золото", "price_kleynody": 220, "icon": "/premium/frame_gold_icon.png", "overlay": "/premium/frame_gold_overlay.png"},
    "frame_ember_glow": {"kind": "frame", "title": "Рамка: жар-полиск", "price_kleynody": 260, "icon": "/premium/frame_ember_glow_icon.png", "overlay": "/premium/frame_ember_glow_overlay.png"},
    "frame_rainbow_glow": {"kind": "frame", "title": "Рамка: райдужний полиск", "price_kleynody": 280, "icon": "/premium/frame_rainbow_glow_icon.png", "overlay": "/premium/frame_rainbow_glow_overlay.png"},
}

# Backward-compatible alias (щоб не ламались старі імпорти)
CATALOG_FRAMES = FRAMES_CATALOG