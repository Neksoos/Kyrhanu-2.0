"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.seasonsRoutes = seasonsRoutes;
const db_1 = require("../db");
async function seasonsRoutes(app) {
    app.get("/seasons/active", async () => {
        const s = await db_1.pool.query(`select * from seasons where is_active=true and starts_at <= now() and ends_at > now()
       order by starts_at desc limit 1`).then((r) => r.rows[0] ?? null);
        return { season: s };
    });
    app.get("/quests/today", async (req, reply) => {
        const au = await app.requireAuth(req);
        // ensure daily quests exist: assign first 3 active daily templates
        const templates = await db_1.pool.query(`select * from quest_templates where active=true and cadence='daily' order by created_at asc limit 3`).then((r) => r.rows);
        const dayKey = await db_1.pool.query(`select (now() at time zone 'utc')::date as d`).then((r) => r.rows[0].d);
        for (const t of templates) {
            await db_1.pool.query(`insert into user_quests (id, user_id, quest_template_id, day_key, progress, created_at)
         values (gen_random_uuid(), $1, $2, $3, 0, now())
         on conflict (user_id, quest_template_id, day_key) do nothing`, [au.id, t.id, dayKey]);
        }
        const qs = await db_1.pool.query(`select uq.*, qt.code, qt.name, qt.description, qt.goal, qt.reward
       from user_quests uq
       join quest_templates qt on qt.id=uq.quest_template_id
       where uq.user_id=$1 and uq.day_key=$2
       order by qt.created_at asc`, [au.id, dayKey]).then((r) => r.rows);
        return reply.send({ day_key: dayKey, quests: qs });
    });
    app.post("/rewards/claim", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = (req.body ?? {});
        // minimal: claim quest reward by user_quest id
        if (!body.user_quest_id)
            return reply.code(400).send({ error: "MISSING_USER_QUEST_ID" });
        const uq = await db_1.pool.query(`select uq.*, qt.reward
       from user_quests uq join quest_templates qt on qt.id=uq.quest_template_id
       where uq.id=$1 and uq.user_id=$2`, [body.user_quest_id, au.id]).then((r) => r.rows[0]);
        if (!uq)
            return reply.code(404).send({ error: "NOT_FOUND" });
        if (uq.claimed_at)
            return reply.send({ ok: true, already: true });
        // mark claimed
        await db_1.pool.query(`update user_quests set claimed_at=now() where id=$1`, [uq.id]);
        const reward = uq.reward ?? {};
        const gold = Number(reward.gold ?? 0);
        const dust = Number(reward.dust ?? 0);
        const shards = Number(reward.shards ?? 0);
        const bpXp = Number(reward.bp_xp ?? 0);
        // ensure wallets for any currencies
        if (gold > 0 || dust > 0 || shards > 0) {
            await db_1.pool.query(`insert into wallets (user_id, currency_code, balance) values
           ($1, 'gold', 0),
           ($1, 'dust', 0),
           ($1, 'shards', 0)
         on conflict (user_id, currency_code) do nothing`, [au.id]);
        }
        // credit gold
        if (gold > 0) {
            await db_1.pool.query(`update wallets set balance = balance + $2 where user_id=$1 and currency_code='gold'`, [au.id, gold]);
        }
        // credit dust
        if (dust > 0) {
            await db_1.pool.query(`update wallets set balance = balance + $2 where user_id=$1 and currency_code='dust'`, [au.id, dust]);
        }
        // credit shards
        if (shards > 0) {
            await db_1.pool.query(`update wallets set balance = balance + $2 where user_id=$1 and currency_code='shards'`, [au.id, shards]);
        }
        // credit Battle Pass XP
        if (bpXp > 0) {
            // find current active season
            const season = await db_1.pool.query(`select * from seasons where is_active=true and starts_at <= now() and ends_at > now() order by starts_at desc limit 1`).then((r) => r.rows[0]);
            if (season) {
                // ensure user battle pass row exists
                const ubp = await db_1.pool.query(`insert into user_battle_pass (user_id, season_id, xp, premium)
           values ($1, $2, 0, false)
           on conflict (user_id, season_id) do update set xp = user_battle_pass.xp
           returning *`, [au.id, season.id]).then((r) => r.rows[0]);
                await db_1.pool.query(`update user_battle_pass set xp = xp + $2 where user_id=$1 and season_id=$3`, [au.id, bpXp, season.id]);
            }
        }
        return reply.send({ ok: true, reward });
    });
}
