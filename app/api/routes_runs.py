import json
import random
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_id

router = APIRouter(prefix="/runs", tags=["runs"])


def _now():
    return datetime.now(timezone.utc)


async def _get_equipped_stats(db: AsyncSession, user_id: str) -> dict:
    # equipment.slots: {"weapon": "<uuid>", "armor": "<uuid>"}
    row = (
        await db.execute(text("SELECT slots FROM equipment WHERE user_id = :uid"), {"uid": user_id})
    ).first()
    slots = (row[0] if row else {}) or {}
    if isinstance(slots, str):
        slots = json.loads(slots)

    weapon_iid = (slots or {}).get("weapon")
    armor_iid = (slots or {}).get("armor")

    atk = 1
    max_hp_bonus = 0

    if weapon_iid:
        w = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE((i.data->'stats'->>'atk')::int, 0) AS atk
                    FROM item_instances ii
                    JOIN items i ON i.id = ii.item_id
                    WHERE ii.id = :iid AND ii.user_id = :uid
                    """
                ),
                {"iid": weapon_iid, "uid": user_id},
            )
        ).mappings().first()
        atk += int((w or {}).get("atk") or 0)

    if armor_iid:
        a = (
            await db.execute(
                text(
                    """
                    SELECT COALESCE((i.data->'stats'->>'hp')::int, 0) AS hp
                    FROM item_instances ii
                    JOIN items i ON i.id = ii.item_id
                    WHERE ii.id = :iid AND ii.user_id = :uid
                    """
                ),
                {"iid": armor_iid, "uid": user_id},
            )
        ).mappings().first()
        max_hp_bonus += int((a or {}).get("hp") or 0)

    return {"atk": atk, "max_hp_bonus": max_hp_bonus}


def _make_nodes(seed: int) -> list[dict]:
    rng = random.Random(seed)

    def node(t: str, title: str, body: str, choices: list[dict], enemy: dict | None = None):
        n = {"type": t, "title": title, "body": body, "choices": choices}
        if enemy:
            n["enemy"] = enemy
        return n

    # 6 nodes: event -> combat -> rest -> treasure -> combat -> final
    return [
        node(
            "event",
            "Crossroads",
            "A cold wind howls between the kurgans.",
            [
                {"id": "scout", "label": "Scout ahead", "effects": {"gold": 5}, "next": 1},
                {"id": "rush", "label": "Rush forward", "effects": {"hp": -2}, "next": 1},
                {"id": "listen", "label": "Listen to the whispers", "effects": {"energy": 1}, "next": 1},
            ],
        ),
        node(
            "combat",
            "Ambush",
            "A bandit leaps from behind a stone.",
            [
                {"id": "fight", "label": "Stand and fight", "effects": {}, "next": 2},
                {"id": "bribe", "label": "Bribe with coins", "effects": {"gold": -8}, "next": 2},
            ],
            enemy={"name": "Bandit", "hp": 10 + rng.randint(0, 3), "atk": 3},
        ),
        node(
            "rest",
            "Campfire",
            "You find a brief shelter.",
            [
                {"id": "rest", "label": "Rest", "effects": {"hp": +4, "energy": +1}, "next": 3},
                {"id": "sharpen", "label": "Sharpen blade", "effects": {"energy": +1}, "next": 3},
            ],
        ),
        node(
            "treasure",
            "Hidden Cache",
            "Under a slab, you find old goods.",
            [
                {"id": "take_gold", "label": "Take coins", "effects": {"gold": 15}, "next": 4},
                {"id": "take_relic", "label": "Take a relic", "effects": {"loot": "herbal_kit"}, "next": 4},
            ],
        ),
        node(
            "combat",
            "Guardian",
            "A restless spirit blocks the path.",
            [
                {"id": "banish", "label": "Banish it", "effects": {}, "next": 5},
                {"id": "endure", "label": "Endure", "effects": {"hp": -1}, "next": 5},
            ],
            enemy={"name": "Wisp", "hp": 12 + rng.randint(0, 4), "atk": 4},
        ),
        node(
            "final",
            "Return",
            "The kurgans let you go — for now.",
            [
                {"id": "finish", "label": "Finish run", "effects": {}, "next": None},
            ],
        ),
    ]


async def _get_active_run(db: AsyncSession, user_id: str):
    row = (
        await db.execute(
            text(
                """
                SELECT id, mode, state, created_at, finished_at
                FROM runs
                WHERE user_id = :uid AND finished_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"uid": user_id},
        )
    ).mappings().first()

    if not row:
        return None

    state = row["state"] or {}
    if isinstance(state, str):
        state = json.loads(state)

    return {"id": str(row["id"]), "mode": row["mode"], "state": state, "created_at": row["created_at"]}


def _present_run(run: dict) -> dict:
    state = run["state"] or {}
    step = int(state.get("step", 0))
    nodes = state.get("nodes", [])
    node = nodes[step] if 0 <= step < len(nodes) else None

    return {
        "ok": True,
        "run": {
            "id": run["id"],
            "mode": run.get("mode"),
            "state": {
                **state,
                "current": node,
                "step": step,
                "total": len(nodes),
            },
        },
    }


@router.get("/current")
async def runs_current(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    run = await _get_active_run(db, user_id)
    if not run:
        return {"ok": True, "run": None}
    return _present_run(run)


@router.post("/start")
async def runs_start(
    body: dict | None = None,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    # Resume if exists
    run = await _get_active_run(db, user_id)
    if run:
        return _present_run(run)

    mode = (body or {}).get("mode") or "daily"
    seed = random.randint(1, 1_000_000_000)
    stats = await _get_equipped_stats(db, user_id)

    max_hp = 20 + int(stats.get("max_hp_bonus") or 0)
    state = {
        "seed": seed,
        "step": 0,
        "nodes": _make_nodes(seed),
        "player": {"hp": max_hp, "max_hp": max_hp, "energy": 2},
        "gold": 0,
        "loot": [],
        "combat": None,
        "log": ["Run started"],
    }

    rid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO runs (id, user_id, mode, state, created_at)
            VALUES (:id, :uid, :mode, :state::jsonb, :now)
            """
        ),
        {"id": str(rid), "uid": user_id, "mode": mode, "state": json.dumps(state), "now": _now()},
    )
    await db.commit()

    return _present_run({"id": str(rid), "mode": mode, "state": state})


@router.post("/{run_id}/choice")
async def runs_choice(
    run_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    choice_id = (body or {}).get("choice_id")
    if not choice_id:
        raise HTTPException(status_code=400, detail="Missing choice_id")

    row = (
        await db.execute(
            text(
                """
                SELECT state
                FROM runs
                WHERE id = :rid AND user_id = :uid AND finished_at IS NULL
                FOR UPDATE
                """
            ),
            {"rid": run_id, "uid": user_id},
        )
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    state = row[0] or {}
    if isinstance(state, str):
        state = json.loads(state)

    # Cannot choose while combat is active
    if state.get("combat"):
        raise HTTPException(status_code=400, detail="Combat in progress")

    step = int(state.get("step", 0))
    nodes = state.get("nodes", [])
    if step < 0 or step >= len(nodes):
        raise HTTPException(status_code=400, detail="Invalid step")

    node = nodes[step]
    choice = next((c for c in node.get("choices", []) if c.get("id") == choice_id), None)
    if not choice:
        raise HTTPException(status_code=400, detail="Invalid choice")

    eff = choice.get("effects", {}) or {}

    player = state.get("player", {})
    player["hp"] = max(0, min(int(player.get("max_hp", 20)), int(player.get("hp", 0)) + int(eff.get("hp", 0) or 0)))
    player["energy"] = max(0, int(player.get("energy", 0)) + int(eff.get("energy", 0) or 0))
    state["player"] = player

    state["gold"] = int(state.get("gold", 0)) + int(eff.get("gold", 0) or 0)

    loot = state.get("loot", [])
    if eff.get("loot"):
        loot.append({"item_id": eff["loot"], "source": f"node:{step}"})
    state["loot"] = loot

    nxt = choice.get("next")

    # Apply next step
    if nxt is None:
        # finish
        return await _finish_run(db, user_id, run_id, state)

    state["step"] = int(nxt)
    state.setdefault("log", []).append(f"Choice: {choice_id}")

    # If next node is combat, initialize combat state
    if 0 <= state["step"] < len(nodes):
        nn = nodes[state["step"]]
        if nn.get("type") == "combat":
            enemy = nn.get("enemy") or {"name": "Enemy", "hp": 10, "atk": 3}
            state["combat"] = {
                "enemy_name": enemy.get("name", "Enemy"),
                "enemy_hp": int(enemy.get("hp", 10)),
                "enemy_max_hp": int(enemy.get("hp", 10)),
                "enemy_atk": int(enemy.get("atk", 3)),
                "player_defending": False,
                "log": [f"Encounter: {enemy.get('name', 'Enemy')}"]
            }

    await db.execute(
        text("UPDATE runs SET state = :state::jsonb WHERE id = :rid"),
        {"state": json.dumps(state), "rid": run_id},
    )
    await db.commit()

    return {"ok": True, "run": {"id": run_id, "state": {**state, "current": nodes[state['step']], "total": len(nodes)}}}


@router.post("/{run_id}/combat/act")
async def runs_combat_act(
    run_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    action = (body or {}).get("action")
    if action not in {"attack", "defend", "skill"}:
        raise HTTPException(status_code=400, detail="Invalid action")

    row = (
        await db.execute(
            text(
                """
                SELECT state
                FROM runs
                WHERE id = :rid AND user_id = :uid AND finished_at IS NULL
                FOR UPDATE
                """
            ),
            {"rid": run_id, "uid": user_id},
        )
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    state = row[0] or {}
    if isinstance(state, str):
        state = json.loads(state)

    combat = state.get("combat")
    if not combat:
        raise HTTPException(status_code=400, detail="No combat")

    nodes = state.get("nodes", [])
    step = int(state.get("step", 0))

    # Player action
    stats = await _get_equipped_stats(db, user_id)
    atk = int(stats.get("atk") or 1)

    player = state.get("player", {})
    energy = int(player.get("energy", 0))

    combat["player_defending"] = False

    if action == "attack":
        dmg = atk
        combat["enemy_hp"] = max(0, int(combat.get("enemy_hp", 0)) - dmg)
        combat.setdefault("log", []).append(f"You strike for {dmg}")
    elif action == "defend":
        combat["player_defending"] = True
        combat.setdefault("log", []).append("You brace for impact")
    elif action == "skill":
        if energy <= 0:
            raise HTTPException(status_code=400, detail="Not enough energy")
        player["energy"] = energy - 1
        dmg = atk + 2
        combat["enemy_hp"] = max(0, int(combat.get("enemy_hp", 0)) - dmg)
        combat.setdefault("log", []).append(f"Skill hits for {dmg}")

    # Enemy response if alive
    if int(combat.get("enemy_hp", 0)) > 0:
        base = int(combat.get("enemy_atk", 3))
        if combat.get("player_defending"):
            base = max(1, base - 2)
        player["hp"] = max(0, int(player.get("hp", 0)) - base)
        combat.setdefault("log", []).append(f"Enemy hits for {base}")

    state["player"] = player

    # Resolve combat
    if int(player.get("hp", 0)) <= 0:
        # death -> finish (no rewards)
        state.setdefault("log", []).append("Defeated")
        state["combat"] = None
        state["result"] = "defeat"
        return await _finish_run(db, user_id, run_id, state)

    if int(combat.get("enemy_hp", 0)) <= 0:
        state.setdefault("log", []).append("Victory")
        state["combat"] = None
        # advance to next node automatically
        state["step"] = min(step + 1, len(nodes) - 1)

        # if we landed on final with only finish choice, we keep it

    await db.execute(
        text("UPDATE runs SET state = :state::jsonb WHERE id = :rid"),
        {"state": json.dumps(state), "rid": run_id},
    )
    await db.commit()

    step2 = int(state.get("step", 0))
    node = nodes[step2] if 0 <= step2 < len(nodes) else None

    return {"ok": True, "run": {"id": run_id, "state": {**state, "current": node, "total": len(nodes)}}}


async def _finish_run(db: AsyncSession, user_id: str, run_id: str, state: dict):
    # Apply rewards: gold -> wallet chervontsi, loot -> inventory instances
    gold = max(0, int(state.get("gold", 0) or 0))
    loot = state.get("loot", []) or []

    # Wallet
    if gold:
        await db.execute(
            text("UPDATE wallet SET chervontsi = chervontsi + :g WHERE user_id = :uid"),
            {"g": gold, "uid": user_id},
        )

    # Ensure equipment row exists so _get_equipped_stats doesn't break later
    await db.execute(
        text(
            """
            INSERT INTO equipment (user_id, slots)
            VALUES (:uid, '{}'::jsonb)
            ON CONFLICT (user_id) DO NOTHING
            """
        ),
        {"uid": user_id},
    )

    # Loot items -> create instances
    created_instances: list[str] = []
    for entry in loot:
        item_id = (entry or {}).get("item_id")
        if not item_id:
            continue
        iid = uuid.uuid4()
        await db.execute(
            text(
                """
                INSERT INTO item_instances (id, user_id, item_id, rarity, affixes, created_at)
                VALUES (:iid, :uid, :item_id, 'common', '{}'::jsonb, :now)
                """
            ),
            {"iid": str(iid), "uid": user_id, "item_id": item_id, "now": _now()},
        )
        await db.execute(
            text(
                """
                INSERT INTO inventory (user_id, item_instance_id, qty)
                VALUES (:uid, :iid, 1)
                ON CONFLICT (user_id, item_instance_id)
                DO UPDATE SET qty = inventory.qty + 1
                """
            ),
            {"uid": user_id, "iid": str(iid)},
        )
        created_instances.append(str(iid))

    state["rewards"] = {"gold": gold, "items": created_instances}

    await db.execute(
        text(
            """
            UPDATE runs
            SET state = :state::jsonb,
                finished_at = :now
            WHERE id = :rid AND user_id = :uid
            """
        ),
        {"state": json.dumps(state), "now": _now(), "rid": run_id, "uid": user_id},
    )
    await db.commit()

    return {"ok": True, "run": {"id": run_id, "state": {**state, "current": None}}}


@router.post("/{run_id}/finish")
async def runs_finish(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    row = (
        await db.execute(
            text(
                """
                SELECT state
                FROM runs
                WHERE id = :rid AND user_id = :uid AND finished_at IS NULL
                FOR UPDATE
                """
            ),
            {"rid": run_id, "uid": user_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    state = row[0] or {}
    if isinstance(state, str):
        state = json.loads(state)

    return await _finish_run(db, user_id, run_id, state)
