"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.ARCHETYPES = void 0;
exports.generateDailyCharacter = generateDailyCharacter;
exports.damageFormula = damageFormula;
const rng_1 = require("./rng");
exports.ARCHETYPES = [
    { id: "KOZAK", name: "Козак-Характерник", base: { hp: 120, atk: 14, def: 10, spd: 10, crit: 5, luck: 6 } },
    { id: "MOLFAR", name: "Мольфар", base: { hp: 95, atk: 18, def: 7, spd: 11, crit: 7, luck: 10 } },
    { id: "BEREHYNIA", name: "Берегиня", base: { hp: 110, atk: 12, def: 12, spd: 10, crit: 5, luck: 9 } },
    { id: "PLASTUN", name: "Пластун", base: { hp: 100, atk: 15, def: 9, spd: 14, crit: 9, luck: 7 } }
];
function generateDailyCharacter(seed) {
    const r = (0, rng_1.mulberry32)(seed);
    const archetype = (0, rng_1.pick)(r, exports.ARCHETYPES);
    const roll = (base) => base + (0, rng_1.randInt)(r, -3, 5);
    const stats = {
        hp: roll(archetype.base.hp),
        atk: roll(archetype.base.atk),
        def: roll(archetype.base.def),
        spd: roll(archetype.base.spd),
        crit: Math.max(0, roll(archetype.base.crit)),
        luck: Math.max(0, roll(archetype.base.luck))
    };
    // tiny “пасивка дня” як flavor
    const passives = [
        "Курганний інстинкт: +1 удача в першому енкаунтері",
        "Січовий крок: +1 швидкість у забігах",
        "Шепіт мавок: +2 крит проти боса",
        "Оберіг: 1 раз на забіг зменшує шкоду на 20%"
    ];
    return {
        archetype_id: archetype.id,
        archetype_name: archetype.name,
        stats,
        passive: (0, rng_1.pick)(r, passives)
    };
}
function damageFormula(stats) {
    // проста формула: base atk + crit chance
    const base = Math.max(1, stats.atk);
    const critChance = Math.min(30, Math.max(0, stats.crit));
    const roll = Math.random() * 100;
    const crit = roll < critChance;
    const luckBonus = Math.floor(stats.luck / 3);
    return {
        damage: base + luckBonus + (crit ? Math.ceil(base * 0.75) : 0),
        crit
    };
}
