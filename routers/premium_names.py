from __future__ import annotations
from typing import Dict, Any

NAMES_CATALOG: Dict[str, Dict[str, Any]] = {
    "name_amber":    {"kind": "name", "title": "Колір імені: Бурштин",  "price_kleynody": 60, "icon": "/premium/name_amber_icon.png",    "css": {"type": "solid", "value": "#fbbf24"}},
    "name_amethyst": {"kind": "name", "title": "Колір імені: Аметист",  "price_kleynody": 70, "icon": "/premium/name_amethyst_icon.png", "css": {"type": "solid", "value": "#a855f7"}},
    "name_bronze":   {"kind": "name", "title": "Колір імені: Бронза",   "price_kleynody": 60, "icon": "/premium/name_bronze_icon.png",   "css": {"type": "solid", "value": "#b45309"}},
    "name_copper":   {"kind": "name", "title": "Колір імені: Мідь",     "price_kleynody": 60, "icon": "/premium/name_copper_icon.png",   "css": {"type": "solid", "value": "#f97316"}},
    "name_crimson":  {"kind": "name", "title": "Колір імені: Кров",     "price_kleynody": 70, "icon": "/premium/name_crimson_icon.png",  "css": {"type": "solid", "value": "#ef4444"}},
    "name_emerald":  {"kind": "name", "title": "Колір імені: Смарагд",  "price_kleynody": 70, "icon": "/premium/name_emerald_icon.png",  "css": {"type": "solid", "value": "#22c55e"}},
    "name_frost":    {"kind": "name", "title": "Колір імені: Крига",    "price_kleynody": 70, "icon": "/premium/name_frost_icon.png",    "css": {"type": "solid", "value": "#38bdf8"}},
    "name_gold":     {"kind": "name", "title": "Колір імені: Золото",   "price_kleynody": 80, "icon": "/premium/name_gold_icon.png",     "css": {"type": "solid", "value": "#f59e0b"}},
    "name_obsidian": {"kind": "name", "title": "Колір імені: Обсидіан", "price_kleynody": 70, "icon": "/premium/name_obsidian_icon.png", "css": {"type": "solid", "value": "#111827"}},
    "name_pearl":    {"kind": "name", "title": "Колір імені: Перлина",  "price_kleynody": 70, "icon": "/premium/name_pearl_icon.png",    "css": {"type": "solid", "value": "#e5e7eb"}},
    "name_ruby":     {"kind": "name", "title": "Колір імені: Рубін",    "price_kleynody": 70, "icon": "/premium/name_ruby_icon.png",     "css": {"type": "solid", "value": "#fb7185"}},
    "name_sapphire": {"kind": "name", "title": "Колір імені: Сапфір",   "price_kleynody": 70, "icon": "/premium/name_sapphire_icon.png", "css": {"type": "solid", "value": "#3b82f6"}},
}

# Backward-compatible alias
CATALOG_NAMES = NAMES_CATALOG