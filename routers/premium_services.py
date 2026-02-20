from __future__ import annotations

from typing import Dict, Any

# ✅ Послуги (витратні "токени")
# Важливо: rename_collateral дорожче за rename_character
SERVICES_CATALOG: Dict[str, Dict[str, Any]] = {
    "rename_character": {
        "kind": "service",
        "title": "Перейменування персонажа",
        "price_kleynody": 300,
        "icon": "/premium/services/rename_character.png",
    },
    "rename_collateral": {
        "kind": "service",
        "title": "Перейменування застави",
        "price_kleynody": 500,
        "icon": "/premium/services/rename_collateral.png",
    },
}