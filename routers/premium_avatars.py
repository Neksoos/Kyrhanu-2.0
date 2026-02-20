from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Tuple


def _ua_title_from_stem(stem: str) -> str:
    # stem типу "avatar_cossack_veteran" або "avatar_premium_upyr"
    key = stem.replace("avatar_", "").replace("premium_", "")
    overrides = {
        "chugaister": "Чугайстер",
        "mavchyn": "Мавчин",
        "naviy": "Навій",
        "upyr": "Упир",
        "vovkulak": "Вовкулак",
        "domovyk": "Домовик",
        "runic_warden": "Руничний вартовий",
        "rusalka_watcher": "Спостерігач русалок",
        "salt_miner": "Соляний шахтар",
        "steppe_scout": "Степовий розвідник",
        "tattooed_stonemason": "Татуйований каменяр",
        "tavern_storyteller": "Оповідач таверни",
        "woodland_leshy": "Лісовий лісовик",
        "obsidian_masked": "Обсидіанова маска",
        "kyiv_scribe": "Київський писар",
        "cossack_veteran": "Козак-ветеран",
        "carpathian_molfar": "Карпатський мольфар",
        "forest_herbalist": "Лісовий травник",
        "marsh_hunter": "Болотяний мисливець",
        "border_guard": "Прикордонний вартовий",
        "knight_of_kurgans": "Лицар курганів",
        "amber_relic_keeper": "Хранитель бурштинових реліквій",
        "beekeeper_guardian": "Пасічник-охоронець",
        "blacksmith_apprentice": "Учень коваля",
        "messenger_with_crow_pin": "Вісник з воронячою шпилькою",
    }
    if key in overrides:
        return overrides[key]

    # фолбек: Title Case з підкреслень
    return " ".join(w.capitalize() for w in key.split("_"))


def _default_avatars_dir() -> Path:
    env = os.getenv("AVATARS_DIR")
    if env:
        return Path(env)
    # найчастіше бек і фронт в одному репо і є /public/avatars
    return Path.cwd() / "public" / "avatars"


def build_avatars_catalog() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
    """
    Повертає:
      - AVATARS_CATALOG: sku -> item
      - AVATAR_VARIANT_TO_BASE: variant_sku -> base_sku (для *_f/_m)
    """
    avatars_dir = _default_avatars_dir()

    # fallback (як на твоїх скрінах), якщо папки нема на бекенді
    fallback_stems = [
        "avatar_amber_relic_keeper",
        "avatar_beekeeper_guardian",
        "avatar_blacksmith_apprentice",
        "avatar_border_guard",
        "avatar_carpathian_molfar",
        "avatar_cossack_veteran",
        "avatar_domovyk",
        "avatar_forest_herbalist",
        "avatar_knight_of_kurgans",
        "avatar_kyiv_scribe",
        "avatar_marsh_hunter",
        "avatar_messenger_with_crow_pin",
        "avatar_obsidian_masked",
        "avatar_runic_warden",
        "avatar_rusalka_watcher",
        "avatar_salt_miner",
        "avatar_steppe_scout",
        "avatar_tattooed_stonemason",
        "avatar_tavern_storyteller",
        "avatar_woodland_leshy",
        # premium gendered:
        "avatar_premium_chugaister",
        "avatar_premium_mavchyn",
        "avatar_premium_naviy",
        "avatar_premium_upyr",
        "avatar_premium_vovkulak",
    ]

    files: list[Path] = []
    if avatars_dir.exists() and avatars_dir.is_dir():
        files = sorted([p for p in avatars_dir.glob("*.png") if p.is_file()])

    # групування premium *_f/_m
    premium_variants: dict[str, dict[str, str]] = {}  # base -> {"m": path, "f": path}
    singles: dict[str, str] = {}  # stem -> path

    if files:
        for p in files:
            stem = p.stem  # без .png
            if not stem.startswith("avatar_"):
                continue

            if stem.startswith("avatar_premium_") and stem.endswith(("_f", "_m")):
                base = stem[:-2]  # прибираємо _f/_m
                g = stem[-1]      # f або m
                premium_variants.setdefault(base, {})[g] = f"/avatars/{p.name}"
            else:
                singles[stem] = f"/avatars/{p.name}"
    else:
        # fallback: формуємо шляхи як у фронта (/avatars/...)
        for stem in fallback_stems:
            if stem.startswith("avatar_premium_"):
                premium_variants.setdefault(stem, {})["m"] = f"/avatars/{stem}_m.png"
                premium_variants.setdefault(stem, {})["f"] = f"/avatars/{stem}_f.png"
            else:
                singles[stem] = f"/avatars/{stem}.png"

    catalog: Dict[str, Dict[str, Any]] = {}
    variant_to_base: Dict[str, str] = {}

    # ціни під себе підкрутиш
    PRICE_REGULAR = 90
    PRICE_PREMIUM = 140

    for stem, path in singles.items():
        catalog[stem] = {
            "kind": "avatar",
            "title": f"Аватар: {_ua_title_from_stem(stem)}",
            "price_kleynody": PRICE_REGULAR,
            "icon": path,
            "asset": {"type": "single", "path": path},
        }

    for base, variants in premium_variants.items():
        # гарантовано мати хоч один варіант
        icon = variants.get("m") or variants.get("f") or f"/avatars/{base}_m.png"
        catalog[base] = {
            "kind": "avatar",
            "title": f"Аватар (преміум): {_ua_title_from_stem(base)}",
            "price_kleynody": PRICE_PREMIUM,
            "icon": icon,
            "asset": {"type": "gendered", "variants": {"m": variants.get("m"), "f": variants.get("f")}},
        }
        if variants.get("m"):
            variant_to_base[f"{base}_m"] = base
        if variants.get("f"):
            variant_to_base[f"{base}_f"] = base

    return catalog, variant_to_base


AVATARS_CATALOG, AVATAR_VARIANT_TO_BASE = build_avatars_catalog()