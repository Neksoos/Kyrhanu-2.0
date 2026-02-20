# services/npc_quests.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Set


# ──────────────────────────────────────────────────────────────────────
# МОДЕЛІ ДАНИХ
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ItemRef:
    """Посилання на предмет за CODE та кількістю."""
    code: str
    qty: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {"code": str(self.code), "qty": int(self.qty)}


@dataclass(frozen=True)
class QuestReward:
    xp: int = 0
    chervontsi: int = 0
    items: Tuple[ItemRef, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xp": int(self.xp),
            "chervontsi": int(self.chervontsi),
            "items": [i.to_dict() for i in self.items],
        }


@dataclass(frozen=True)
class QuestStage:
    id: str
    text_lines: Tuple[str, ...]
    choices: Dict[str, str] = field(default_factory=dict)
    require_items: Tuple[ItemRef, ...] = ()
    complete_reward: Optional[QuestReward] = None
    is_final: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text_lines": list(self.text_lines),
            "choices": dict(self.choices),
            "require_items": [i.to_dict() for i in self.require_items],
            "complete_reward": self.complete_reward.to_dict() if self.complete_reward else None,
            "is_final": bool(self.is_final),
        }


@dataclass(frozen=True)
class QuestDef:
    npc_key: str
    quest_key: str
    title: str
    description: str
    stages: Dict[str, QuestStage]
    start_id: str
    once: bool = True
    level_req: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "npc_key": self.npc_key,
            "quest_key": self.quest_key,
            "title": self.title,
            "description": self.description,
            "stages": {k: v.to_dict() for k, v in self.stages.items()},
            "start_id": self.start_id,
            "once": bool(self.once),
            "level_req": int(self.level_req),
        }


# ──────────────────────────────────────────────────────────────────────
# ЛОКАЛЬНИЙ КАТАЛОГ ПРЕДМЕТІВ ДЛЯ КВЕСТІВ (ПО CODE)
# ──────────────────────────────────────────────────────────────────────
# type: quest / consumable / trinket
ITEM_CATALOG: Dict[str, Dict[str, str]] = {
    # Oksana
    "q_wax_charm":          {"name": "Віск-оберіг", "type": "quest", "desc": "Чистий віск, благий до свічок."},
    "t_oksana_holy_candle": {"name": "Свята свічка Оксани", "type": "trinket", "desc": "Тепле полум’я дає відчуття захисту."},
    "q_red_thread":         {"name": "Червона нитка", "type": "quest", "desc": "Нитка для оберегів і вузлів пам’яті."},
    "q_st_johns_wort":      {"name": "Сухоцвіт звіробою", "type": "quest", "desc": "Теплий трав’яний оберіг від холоду й страху."},
    "t_oksana_knot_charm":  {"name": "Оберіг-вузлик", "type": "trinket", "desc": "Малий вузлик, що тримає думку в купі."},

    # Semen
    "q_werewolf_claws":   {"name": "Кігті яружного вовкулаки", "type": "quest", "desc": "Гострі й темні від давньої скверни."},
    "t_semen_silver_coin":{"name": "Срібний медяк Семена", "type": "trinket", "desc": "Дзвенить, мов струна. На щастя."},
    "q_creaky_wedge":     {"name": "Скрипучий ладок", "type": "quest", "desc": "Старий дерев’яний клин для лагодження ліри."},
    "q_leather_gut":      {"name": "Жила зі шкіри", "type": "quest", "desc": "Міцна жила для струн."},
    "t_semen_buckle":     {"name": "Лірницька пряжка", "type": "trinket", "desc": "Пряжка, що дзвенить у такт. На щастя."},

    # Panas
    "q_duckweed":           {"name": "Ряска болотяна", "type": "quest", "desc": "Зелень із тихих плес."},
    "q_oak_moss":           {"name": "Мох дубовий", "type": "quest", "desc": "Сухий, але міцний."},
    "q_glass_vial":         {"name": "Скляна банька", "type": "quest", "desc": "Щоб не бахкало — потрібен посуд."},
    "c_stabilization_potion":{"name": "Зілля стабілізації", "type": "consumable", "desc": "Трохи гальмує вибухові сюрпризи."},
    "q_hearth_chalk":       {"name": "Крейда з печі", "type": "quest", "desc": "Біла крейда, щоб креслити кола й не влізти в біду."},
    "q_boiler_soot":        {"name": "Сажа котлова", "type": "quest", "desc": "Сажа для “заземлення” вибриків зілля."},
    "c_muffle_powder":      {"name": "Порошок приглушення", "type": "consumable", "desc": "Зменшує шанс небажаних ефектів (тимчасово)."},

    # Nastia
    "q_spice_box":        {"name": "Скринька спецій", "type": "quest", "desc": "Суміш гостра, як язик Насті."},
    "q_carrier_seal":     {"name": "Печатка перевізника", "type": "quest", "desc": "Знак, що вантаж пройшов огляд."},
    "t_saltbelly_voucher":{"name": "Талон «Солоний Киш»", "type": "trinket", "desc": "Знижка від Насті."},
    "q_debtors_list":     {"name": "Список боржників", "type": "quest", "desc": "Папірці, що пахнуть проблемами й прибутком."},
    "q_customs_plomb":    {"name": "Пломба митника", "type": "quest", "desc": "Офіційний знак. Не питай, як дістався."},
    "t_discount_coupon":  {"name": "Купон на знижку", "type": "trinket", "desc": "Можна виторгувати дрібну вигоду."},

    # Yurko
    "q_gnus_fang":      {"name": "Ікло степового гнуса", "type": "quest", "desc": "Маленьке, та капосне."},
    "t_courage_patch":  {"name": "Нашивка відваги", "type": "trinket", "desc": "Носиш — і не пасуєш."},
    "q_scabbard_strap": {"name": "Ремінець для піхов", "type": "quest", "desc": "Щоб меч не бовтався, як язик у шинку."},
    "q_button_knope":   {"name": "Кнопа-ґудзик", "type": "quest", "desc": "Дрібниця, але без неї все тримається на чесному слові."},
    "t_recruit_memo":   {"name": "Пам’ятка рекрута", "type": "trinket", "desc": "Папірець із правилами виживання. Смішно, але працює."},
}

ITEM_CODES: Set[str] = set(ITEM_CATALOG.keys())


def validate_items_exist(refs: Sequence[ItemRef]) -> None:
    missing = [r.code for r in refs if r.code not in ITEM_CODES]
    if missing:
        raise ValueError(f"Unknown quest item codes: {missing}")


# ──────────────────────────────────────────────────────────────────────
# ❶ Берегиня Оксана — квести
# ──────────────────────────────────────────────────────────────────────

def _quest_oksana() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Ой, дєтко, засвіти свічку в серці — і ніч не така страшна.",
                "Шо стоїш, як пеньок? Йди-но ближче — добром поділюся.",
                "Свічі та віск самі не ростуть. Принесеш — освятимо шлях твій.",
            ),
            choices={"✅ «Поможу, пані Берегине»": "collect", "❌ «Не зараз»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Не силуй себе. Та тільки знай: темрява не чекає.",),
            choices={},
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=(
                "Добре робиш, дєтко. Принеси мені трохи воску — чистого, як ранкова роса.",
                "Мені треба: 3× «Віск-оберіг». Тоді свічку складемо — і шлях яснітиме.",
            ),
            choices={"🕯 «Приніс(ла) віск»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=(
                "Оце добре, світло любить хоробрих.",
                "Бачиш? Світло стало теплішим — дорога вже ясніша.",
            ),
            require_items=(ItemRef("q_wax_charm", 3),),
            complete_reward=QuestReward(xp=35, chervontsi=50, items=(ItemRef("t_oksana_holy_candle", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="berehynia_oksana",
        quest_key="oksana_light",
        title="Свічка Берегині",
        description="Принести віск для святої свічки, що оберігає мандрівника.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=1,
    )


def _quest_oksana_knot() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Дєтко, оберіг не тільки від лиха — він і думку рівняє.",
                "Принеси мені нитку червону та сухоцвіт — сплету тобі вузлик, як треба.",
            ),
            choices={"✅ «Зберу»": "collect", "❌ «Не зараз»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Як серце не тягне — не муч. Але бережися вітру.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=(
                "Мені треба: 2× «Червона нитка» і 3× «Сухоцвіт звіробою».",
                "Не барися — вузлик не любить пустих днів.",
            ),
            choices={"🧵 «Приніс(ла)»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=(
                "От і добре. Тримай — невелика річ, а на дорозі помагає.",
                "Коли думки розлазяться — стисни вузлик в долоні.",
            ),
            require_items=(ItemRef("q_red_thread", 2), ItemRef("q_st_johns_wort", 3)),
            complete_reward=QuestReward(xp=40, chervontsi=55, items=(ItemRef("t_oksana_knot_charm", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="berehynia_oksana",
        quest_key="oksana_knot",
        title="Оберіг-вузлик",
        description="Зібрати нитку й сухоцвіт для простого оберега Оксани.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=2,
    )


def _quest_oksana_calm() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Є люди, що вночі не сплять — страх їх гризе.",
                "Принеси мені ще воску — зробимо маленьку свічку для тих, хто лишився сам.",
            ),
            choices={"✅ «Добре»": "collect", "❌ «Не візьмусь»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Та й так буває. Тільки не гнівайся на себе.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Принеси 2× «Віск-оберіг». Більше не треба — свічка мала.",),
            choices={"🕯 «Є віск»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Бачиш, як рівно горить? Так і в голові має бути рівно.",),
            require_items=(ItemRef("q_wax_charm", 2),),
            complete_reward=QuestReward(xp=30, chervontsi=35, items=(ItemRef("t_oksana_holy_candle", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="berehynia_oksana",
        quest_key="oksana_calm_candle",
        title="Тиха свічка",
        description="Принести віск для малої свічки підтримки.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=1,
    )


# ──────────────────────────────────────────────────────────────────────
# ❷ Семен
# ──────────────────────────────────────────────────────────────────────

def _quest_semen() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Ґей, вуйку, не лякайся — то струни мої тремтять, не душа твоя.",
                "Є звір лютий, шо голос мій крав. Виведи його на чисте — верну пісню людям.",
            ),
            choices={"✅ «Добре, пошукаю»": "collect", "❌ «Не маю часу»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Еге ж, дорога вільна. Тільки пісня без тебе буде тихіша.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=(
                "Шукай у ярах темних — там де вітер свище, як струна порвана.",
                "Принеси 3× «Кігті яружного вовкулаки». Тоді й заграю тобі щось файне.",
            ),
            choices={"🎻 «Маю трофеї»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Оце пісня! Чуєш, як поле відгукується? Спасибі тобі, вуйку.",),
            require_items=(ItemRef("q_werewolf_claws", 3),),
            complete_reward=QuestReward(xp=60, chervontsi=70, items=(ItemRef("t_semen_silver_coin", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="lirnyk_semen",
        quest_key="semen_song",
        title="Пісня з яруги",
        description="Добути кігті яружного вовкулаки, щоби повернути лірнику голос пісні.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=3,
    )


def _quest_semen_strings() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Вуйку, моя ліра як старий кінь: ще тягне, але скрипить.",
                "Принеси мені жилу та ладок — підтягну струни, щоб голос не сідав.",
            ),
            choices={"✅ «Зроблю»": "collect", "❌ «Не до того»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Еге ж. То й лишимося зі скрипом замість пісні.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба: 2× «Жила зі шкіри» і 1× «Скрипучий ладок».",),
            choices={"🎻 «Приніс(ла)»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("О, тепер воно звучить. Не як у молодості, але чесно.",),
            require_items=(ItemRef("q_leather_gut", 2), ItemRef("q_creaky_wedge", 1)),
            complete_reward=QuestReward(xp=65, chervontsi=75, items=(ItemRef("t_semen_buckle", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="lirnyk_semen",
        quest_key="semen_strings",
        title="Струни не терплять брехні",
        description="Дістати матеріали для лагодження ліри Семена.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=3,
    )


def _quest_semen_coin() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Медяк мій срібний я людям даю — але не всім підряд.",
                "Доведи, що не тікаєш від роботи: принеси ще кігтів, щоб я мав чим історію скріпити.",
            ),
            choices={"✅ «Принесу»": "collect", "❌ «Пас»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Ну то й не буде тобі ні медяка, ні балади.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Принеси 2× «Кігті яружного вовкулаки».",),
            choices={"🦴 «Є»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Гаразд. Тримай дрібну річ, але в кишені тепліше з нею.",),
            require_items=(ItemRef("q_werewolf_claws", 2),),
            complete_reward=QuestReward(xp=40, chervontsi=45, items=(ItemRef("t_semen_silver_coin", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="lirnyk_semen",
        quest_key="semen_coin_again",
        title="Ще одна дума",
        description="Принести трофеї, щоб Семен склав нову баладу.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=4,
    )


# ──────────────────────────────────────────────────────────────────────
# ❸ Панас
# ──────────────────────────────────────────────────────────────────────

def _quest_panas() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Йой, та я ж тільки трохи зачаклував — а воно бухнуло!",
                "Шо ж ти, поможи зілля назбирати — бо без нього знов бахне.",
            ),
            choices={"✅ «Зберу, аби не бахкало»": "collect", "❌ «Я пас»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Та й так піде… певно… якось… ой, ліпше не треба.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=(
                "Треба: 5× «Ряска болотяна», 2× «Мох дубовий», 1× «Скляна банька».",
                "А я тут… трохи постою подалі. Для стабілізації, так сказати.",
            ),
            choices={"🧪 «Приніс(ла) інгредієнти»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("О! Не бахкає! Ти маг майже як я… тобто краще.",),
            require_items=(ItemRef("q_duckweed", 5), ItemRef("q_oak_moss", 2), ItemRef("q_glass_vial", 1)),
            complete_reward=QuestReward(xp=45, chervontsi=40, items=(ItemRef("c_stabilization_potion", 2),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="nedochaklun_panas",
        quest_key="panas_stabilizer",
        title="Щоб не бахкало",
        description="Зібрати інгредієнти для Панаса, аби зілля перестало вибухати.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=1,
    )


def _quest_panas_chalk() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Йой, я круги креслив — а воно само себе перекреслило!",
                "Принеси мені крейди і сажі — зробим нормальне коло, шоб не лізло куди не треба.",
            ),
            choices={"✅ «Ок»": "collect", "❌ «Я пас»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Та й так піде… але як бахне — я попереджав.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба: 2× «Крейда з печі» і 2× «Сажа котлова».",),
            choices={"🧯 «Приніс(ла)»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("О! Тепер хоч не страшно дихати біля котла.",),
            require_items=(ItemRef("q_hearth_chalk", 2), ItemRef("q_boiler_soot", 2)),
            complete_reward=QuestReward(xp=45, chervontsi=50, items=(ItemRef("c_muffle_powder", 2),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="nedochaklun_panas",
        quest_key="panas_chalk_circle",
        title="Коло без сюрпризів",
        description="Зібрати крейду й сажу, щоб Панас не наробив біди.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=2,
    )


def _quest_panas_bottle_more() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "У мене баньки закінчились. А без баньки — все по штанях, йой.",
                "Принеси ще одну «Скляну баньку», шоб я хоч щось дожив до вечора.",
            ),
            choices={"✅ «Принесу»": "collect", "❌ «Не хочу»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Ну то я піду шукати баньку… десь… в диму.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба 1× «Скляну баньку».",),
            choices={"🧪 «Ось банька»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Спасибі! Я тепер хоча б вибухну культурно, у тарі.",),
            require_items=(ItemRef("q_glass_vial", 1),),
            complete_reward=QuestReward(xp=25, chervontsi=30, items=(ItemRef("c_stabilization_potion", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="nedochaklun_panas",
        quest_key="panas_one_more_bottle",
        title="Банька — це безпека",
        description="Дістати ще одну баньку для експериментів Панаса.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=1,
    )


# ──────────────────────────────────────────────────────────────────────
# ❹ Настя
# ──────────────────────────────────────────────────────────────────────

def _quest_nastia() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Сонечко, маю ділову пропозицію — без лоха і життя не те.",
                "Є клієнт, любить гостре. Принесеш спецій — зроблю тобі ціну як родичу.",
            ),
            choices={"✅ «Йду в ділі»": "collect", "❌ «Пас»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Не шото — твоя воля. Тільки потім не шкодуй.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=(
                "Мені треба 1× «Скринька спецій» і 1× «Печатка перевізника».",
                "Печатка — то шоб не чіпали по дорозі, ясно? Працюємо культурно.",
            ),
            choices={"🧂 «Маю спеції й печатку»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Красота! Ти шо, профі? Я в захваті, чесне слово.",),
            require_items=(ItemRef("q_spice_box", 1), ItemRef("q_carrier_seal", 1)),
            complete_reward=QuestReward(xp=55, chervontsi=120, items=(ItemRef("t_saltbelly_voucher", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="nastia_salt_belly",
        quest_key="nastia_spice_run",
        title="Гострий на язик вантаж",
        description="Дістати скриньку спецій і печатку перевізника для Насті.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=5,
    )


def _quest_nastia_debts() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Слухай, сонечко, бізнес — то пам’ять. Хто винен — того не забуваємо.",
                "Принеси мені «Список боржників». Він десь гуляє, а мені треба працювати.",
            ),
            choices={"✅ «Знайду»": "collect", "❌ «Пас»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Добре. Будемо без списку, на чесному слові. Ха-ха.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба 1× «Список боржників».",),
            choices={"📜 «Є список»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("О, красота. Тепер у людей буде стимул згадати про совість.",),
            require_items=(ItemRef("q_debtors_list", 1),),
            complete_reward=QuestReward(xp=55, chervontsi=110, items=(ItemRef("t_discount_coupon", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="nastia_salt_belly",
        quest_key="nastia_debts_list",
        title="Пам’ять бізнесу",
        description="Повернути Насті список боржників.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=5,
    )


def _quest_nastia_seal() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Тут така справа: пломба — то як броня. Без неї вантажі нервують.",
                "Принеси 1× «Пломба митника». Як дістанеш — твої методи мене не цікавлять.",
            ),
            choices={"✅ «Добре»": "collect", "❌ «Ні»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Ну то ходи без пломби. Я подивлюся здалеку.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба 1× «Пломба митника».",),
            choices={"🧷 «Ось пломба»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("От тепер інша розмова. Ти в темі, я бачу.",),
            require_items=(ItemRef("q_customs_plomb", 1),),
            complete_reward=QuestReward(xp=60, chervontsi=140, items=(ItemRef("t_saltbelly_voucher", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="nastia_salt_belly",
        quest_key="nastia_customs_seal",
        title="Пломба вирішує",
        description="Дістати митну пломбу для Насті.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=6,
    )


# ──────────────────────────────────────────────────────────────────────
# ❺ Юрко
# ──────────────────────────────────────────────────────────────────────

def _quest_yurko() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Та йой! Ти якраз мені треба! Шо, підемо в бійку чи як?",
                "Збери пару трофеїв — покажемо, шо ми з нашої застави не лякаємось!",
            ),
            choices={"✅ «Беру тренування»": "collect", "❌ «Маю інші справи»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Ей, не крут носом. Як надумаєш — гукай.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба 5× «Ікло степового гнуса». Наб’ємо руку — і дух піде!",),
            choices={"🦴 «Приніс(ла) ікла»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Оце робота! Видиш? Дух є! Далі буде ще ліпше.",),
            require_items=(ItemRef("q_gnus_fang", 5),),
            complete_reward=QuestReward(xp=70, chervontsi=80, items=(ItemRef("t_courage_patch", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="yurko_rekrut",
        quest_key="yurko_trophies",
        title="Набити руку",
        description="Зібрати ікла степового гнуса, аби показати відвагу на тренуванні.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=2,
    )


def _quest_yurko_scabbard() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Та йой, мені піхви розлізлись. Я як бігаю — меч брязкає, як каструля.",
                "Принеси ремінець і ґудзик — зробим нормально!",
            ),
            choices={"✅ «Зроблю»": "collect", "❌ «Маю справи»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Ей, ну то я далі буду брязкати. Може, ворог злякається.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба: 1× «Ремінець для піхов» і 2× «Кнопа-ґудзик».",),
            choices={"🪡 «Приніс(ла)»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("Файно! Тепер можна бігти так, щоб не смішити людей.",),
            require_items=(ItemRef("q_scabbard_strap", 1), ItemRef("q_button_knope", 2)),
            complete_reward=QuestReward(xp=65, chervontsi=85, items=(ItemRef("t_recruit_memo", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="yurko_rekrut",
        quest_key="yurko_scabbard_fix",
        title="Щоб не брязкало",
        description="Принести дрібні речі для лагодження спорядження Юрка.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=2,
    )


def _quest_yurko_more_teeth() -> QuestDef:
    stages: Dict[str, QuestStage] = {
        "start": QuestStage(
            id="start",
            text_lines=(
                "Командир каже: “принеси доказів, шо тренувався”.",
                "Принеси ще 3 ікла — і буде доказ, ясно?",
            ),
            choices={"✅ «Беру»": "collect", "❌ «Не хочу»": "reject"},
        ),
        "reject": QuestStage(
            id="reject",
            text_lines=("Та йой… ну добре. Але не кажи, шо я не просив.",),
            is_final=True,
        ),
        "collect": QuestStage(
            id="collect",
            text_lines=("Мені треба 3× «Ікло степового гнуса».",),
            choices={"🦷 «Ось ікла»": "turn_in"},
        ),
        "turn_in": QuestStage(
            id="turn_in",
            text_lines=("О, файно! Тепер командир не буде бурчати так голосно.",),
            require_items=(ItemRef("q_gnus_fang", 3),),
            complete_reward=QuestReward(xp=55, chervontsi=70, items=(ItemRef("t_courage_patch", 1),)),
            is_final=True,
        ),
    }
    validate_items_exist(stages["turn_in"].require_items)
    validate_items_exist(stages["turn_in"].complete_reward.items)  # type: ignore
    return QuestDef(
        npc_key="yurko_rekrut",
        quest_key="yurko_more_teeth",
        title="Доказ тренування",
        description="Зібрати додаткові трофеї для звіту Юрка.",
        stages=stages,
        start_id="start",
        once=True,
        level_req=3,
    )


# ──────────────────────────────────────────────────────────────────────
# РЕЄСТР КВЕСТІВ
# ──────────────────────────────────────────────────────────────────────

ALL_QUESTS: List[QuestDef] = [
    _quest_oksana(),
    _quest_semen(),
    _quest_panas(),
    _quest_nastia(),
    _quest_yurko(),
    _quest_oksana_knot(),
    _quest_oksana_calm(),
    _quest_semen_strings(),
    _quest_semen_coin(),
    _quest_panas_chalk(),
    _quest_panas_bottle_more(),
    _quest_nastia_debts(),
    _quest_nastia_seal(),
    _quest_yurko_scabbard(),
    _quest_yurko_more_teeth(),
]

QUESTS_BY_KEY: Dict[str, QuestDef] = {q.quest_key: q for q in ALL_QUESTS}

QUESTS_BY_NPC: Dict[str, List[QuestDef]] = {}
for q in ALL_QUESTS:
    QUESTS_BY_NPC.setdefault(q.npc_key, []).append(q)


# ──────────────────────────────────────────────────────────────────────
# ПУБЛІЧНІ ХЕЛПЕРИ
# ──────────────────────────────────────────────────────────────────────

def get_quests_for_npc(npc_key: str) -> Sequence[QuestDef]:
    return tuple(QUESTS_BY_NPC.get(npc_key, []))


def get_quest(quest_key: str) -> Optional[QuestDef]:
    return QUESTS_BY_KEY.get(quest_key)


def all_quest_item_codes() -> Sequence[str]:
    codes: Set[str] = set()
    for q in ALL_QUESTS:
        for s in q.stages.values():
            for r in s.require_items:
                codes.add(r.code)
            if s.complete_reward:
                for g in s.complete_reward.items:
                    codes.add(g.code)
    return tuple(sorted(codes))


def get_item_meta(code: str) -> Optional[Dict[str, str]]:
    return ITEM_CATALOG.get(code)


def quests_json_for_npc(npc_key: str) -> List[Dict[str, Any]]:
    return [q.to_dict() for q in get_quests_for_npc(npc_key)]


def quest_json(quest_key: str) -> Optional[Dict[str, Any]]:
    q = get_quest(quest_key)
    return q.to_dict() if q else None


__all__ = [
    "ItemRef",
    "QuestReward",
    "QuestStage",
    "QuestDef",
    "ITEM_CATALOG",
    "ITEM_CODES",
    "validate_items_exist",
    "ALL_QUESTS",
    "QUESTS_BY_KEY",
    "QUESTS_BY_NPC",
    "get_quests_for_npc",
    "get_quest",
    "all_quest_item_codes",
    "get_item_meta",
    "quests_json_for_npc",
    "quest_json",
]