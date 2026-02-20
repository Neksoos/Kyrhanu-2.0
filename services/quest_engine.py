"""Quest engine service for Kyrhanu.

This module implements a simple in‑memory quest progression engine and
adds the ability to automatically apply quest rewards when a stage is
completed.  It mirrors the data structures from the original
`services/npc_quests.py` (QuestDef, QuestStage, QuestReward) and
provides functions to start a quest, get a player's current stage
and advance to the next stage.

In contrast to the upstream implementation, the `advance` function
here is asynchronous: it awaits helper services to add experience,
coins and items to the player's state whenever a stage defines a
`complete_reward`.  This eliminates the TODOs present in the
upstream code and centralises reward handling.

Note: the progress store `_progress` is currently an in‑memory
dictionary keyed by `(uid, quest_key)`.  For a production system
you may wish to persist this state in Redis or a database.
"""

from __future__ import annotations

import time
from typing import Dict, Any, Tuple, Optional, List, Sequence

from loguru import logger

# ✅ FIX: use relative imports inside the "services" package
from .npc_quests import (
    get_quest,
    get_quests_for_npc,
    QuestStage,
    QuestDef,
)

# Reward helpers (also relative)
from .progress import add_player_xp
from .economy import add_coins
from .rewards import distribute_drops


# In‑memory quest progress store.
# _progress[(uid, quest_key)] = {
#     "stage": current stage id,
#     "done": bool,
#     "ts": last update timestamp
# }
_progress: Dict[Tuple[int, str], Dict[str, Any]] = {}


def start_quest(uid: int, quest_key: str) -> Dict[str, Any]:
    """
    Start a quest for a player if it hasn't been started yet.

    :param uid: Telegram ID of the player
    :param quest_key: key of the quest
    :returns: the internal progress record
    :raises ValueError: if the quest is unknown
    """
    q = get_quest(quest_key)
    if not q:
        raise ValueError("QUEST_NOT_FOUND")

    key = (uid, quest_key)
    if key not in _progress:
        _progress[key] = {
            "stage": q.start_id,
            "done": False,
            "ts": time.time(),
        }
    return _progress[key]


def get_player_stage(uid: int, quest_key: str) -> QuestStage:
    """
    Return the current stage of a quest for a player.

    If the quest has not been started yet this returns the starting stage.
    :param uid: Telegram ID of the player
    :param quest_key: quest identifier
    :returns: the current QuestStage object
    :raises ValueError: if the quest is unknown
    """
    q = get_quest(quest_key)
    if not q:
        raise ValueError("QUEST_NOT_FOUND")
    key = (uid, quest_key)
    if key not in _progress:
        return q.stages[q.start_id]
    stage_id = _progress[key]["stage"]
    return q.stages[stage_id]


async def _apply_reward(uid: int, reward) -> None:
    """
    Apply quest reward to a player.

    This helper takes a `QuestReward` object and awards XP, coins
    and items to the player.  It is separated from `advance` for
    clarity and error handling.
    """
    if reward is None:
        return
    try:
        # XP
        if getattr(reward, "xp", 0):
            xp = int(reward.xp)
            if xp > 0:
                await add_player_xp(uid, xp)

        # Coins (chervontsi)
        coins = getattr(reward, "chervontsi", 0)
        if coins and coins > 0:
            await add_coins(uid, coins)

        # Items
        items: Sequence = getattr(reward, "items", ()) or ()
        if items:
            # Convert ItemRef objects into drop dicts understood by distribute_drops
            drops: List[Dict[str, Any]] = []
            for item in items:
                # item has fields `name` and `qty`
                name = getattr(item, "name", None)
                qty = getattr(item, "qty", 1)
                if name:
                    drops.append({"name": name, "qty": qty})
            if drops:
                await distribute_drops(uid, drops)

    except Exception as e:
        # Log errors but don't interrupt quest progression
        logger.exception(f"quest_engine: failed to apply reward for uid={uid}: {e}")


async def advance(uid: int, quest_key: str, choice_label: str) -> Dict[str, Any]:
    """
    Advance a player's quest by following a choice.

    This asynchronous function checks the player's current stage, finds
    the next stage based on the choice label, applies any required
    items and rewards, updates progress and returns a response
    describing the new stage.

    :param uid: Telegram ID of the player
    :param quest_key: quest identifier
    :param choice_label: the label of the choice clicked by the player
    :returns: dict with keys `stage`, `text_lines`, `choices`, `is_final`, and
              optionally `reward` containing the applied reward
    :raises ValueError: if the quest or choice does not exist
    """
    q = get_quest(quest_key)
    if not q:
        raise ValueError("QUEST_NOT_FOUND")

    key = (uid, quest_key)
    if key not in _progress:
        start_quest(uid, quest_key)

    current_stage = get_player_stage(uid, quest_key)

    # Determine next stage id from the selected choice
    next_id = current_stage.choices.get(choice_label)
    if not next_id:
        raise ValueError("BAD_CHOICE")
    next_stage = q.stages[next_id]

    # TODO: handle require_items by checking/removing items from inventory
    if next_stage.require_items:
        # Here one could call a service to ensure items exist and remove them
        # from the player's inventory.  For now we simply assume the client
        # has done this validation; enforcement should be implemented later.
        pass

    reward_dict: Optional[Dict[str, Any]] = None

    # Apply reward if present
    if next_stage.complete_reward:
        reward = next_stage.complete_reward
        reward_dict = reward.to_dict()
        await _apply_reward(uid, reward)

    # Mark quest as done if this stage is final
    if next_stage.is_final:
        _progress[key]["done"] = True

    # Update progress state
    _progress[key]["stage"] = next_stage.id
    _progress[key]["ts"] = time.time()

    return {
        "stage": next_stage.id,
        "text_lines": next_stage.text_lines,
        "choices": next_stage.choices,
        "is_final": next_stage.is_final,
        "reward": reward_dict,
    }


def list_player_quests(uid: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    List all quests for a player, grouped into active and completed.

    Each quest record contains basic metadata (quest_key, npc_key, title), the
    current stage number, the text lines and choices for that stage, and flags
    indicating whether the stage is final or the quest is done.

    :param uid: Telegram ID of the player
    :returns: a dict with keys ``active`` and ``completed``, each mapping to a
              list of quest progress records
    """
    active: List[Dict[str, Any]] = []
    completed: List[Dict[str, Any]] = []

    # Iterate over all progress entries for the specified player
    for (player, quest_key), state in list(_progress.items()):
        if player != uid:
            continue
        try:
            q = get_quest(quest_key)
        except Exception:
            q = None
        if not q:
            continue
        # Obtain the current stage object; this will default to the starting
        # stage if the quest has not been started yet.
        stage_obj = get_player_stage(uid, quest_key)
        record: Dict[str, Any] = {
            "quest_key": quest_key,
            "npc_key": q.npc_key,
            "title": q.title,
            "stage": state.get("stage"),
            "stage_lines": list(stage_obj.text_lines),
            "choices": dict(stage_obj.choices),
            "is_final": bool(stage_obj.is_final),
            "done": bool(state.get("done")),
        }
        if state.get("done"):
            completed.append(record)
        else:
            active.append(record)

    return {"active": active, "completed": completed}


# Exportable symbols
__all__ = [
    "start_quest",
    "get_player_stage",
    "advance",
    "list_player_quests",
]
