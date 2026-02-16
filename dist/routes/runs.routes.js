"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.runsRoutes = runsRoutes;
const zod_1 = require("zod");
const db_1 = require("../db");
function newSeed() {
    return BigInt(Math.floor(Math.random() * 2_000_000_000));
}
async function runsRoutes(app) {
    app.post("/runs/start", async (req, reply) => {
        const au = await app.requireAuth(req);
        const ch = await db_1.pool.query(`select * from characters where user_id=$1 and day_key = (now() at time zone 'utc')::date limit 1`, [au.id]).then((r) => r.rows[0]);
        if (!ch)
            return reply.code(400).send({ error: "NO_TODAY_CHARACTER" });
        const seed = newSeed();
        const run = await db_1.pool.query(`insert into runs (id, user_id, character_id, seed, status, state, started_at)
       values (gen_random_uuid(), $1, $2, $3, 'active', $4::jsonb, now())
       returning *`, [au.id, ch.id, seed.toString(), JSON.stringify({ room: 0, hp_loss: 0 })]).then((r) => r.rows[0]);
        // first encounter
        await db_1.pool.query(`insert into encounters (id, run_id, idx, kind, seed, data, created_at)
       values (gen_random_uuid(), $1, 0, 'fight', $2, $3::jsonb, now())`, [run.id, seed.toString(), JSON.stringify({ enemy: "Мавка-розвідниця", level: 1 })]);
        return reply.send({ run });
    });
    app.post("/runs/act", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = zod_1.z.object({ run_id: zod_1.z.string().uuid(), action: zod_1.z.enum(["ATTACK", "DEFEND", "FLEE"]) }).parse(req.body);
        const run = await db_1.pool.query(`select * from runs where id=$1 and user_id=$2`, [body.run_id, au.id]).then((r) => r.rows[0]);
        if (!run)
            return reply.code(404).send({ error: "RUN_NOT_FOUND" });
        if (run.status !== "active")
            return reply.code(400).send({ error: "RUN_NOT_ACTIVE" });
        // lightweight simulation
        const nextRoom = Number(run.state?.room ?? 0) + 1;
        const finished = nextRoom >= 5;
        const newState = { ...(run.state ?? {}), room: nextRoom };
        await db_1.pool.query(`update runs set state=$1::jsonb where id=$2`, [JSON.stringify(newState), run.id]);
        if (finished) {
            // reward both gold and dust when a run finishes
            const rewardGold = 40;
            const rewardDust = 12;
            const outcome = {
                result: "victory",
                rooms: nextRoom,
                rewards: [
                    { currency: "gold", amount: rewardGold },
                    { currency: "dust", amount: rewardDust }
                ]
            };
            await db_1.pool.query(`update runs set status='finished', finished_at=now(), outcome=$1::jsonb where id=$2`, [JSON.stringify(outcome), run.id]);
            // record transactions for each currency
            await db_1.pool.query(`insert into transactions (id, user_id, currency_code, amount, reason, meta, created_at)
         values 
           (gen_random_uuid(), $1, 'gold', $2, 'run_finish', $3::jsonb, now()),
           (gen_random_uuid(), $1, 'dust', $4, 'run_finish', $3::jsonb, now())`, [au.id, rewardGold, JSON.stringify({ run_id: run.id }), rewardDust]);
            // ensure wallets exist for both currencies
            await db_1.pool.query(`insert into wallets (user_id, currency_code, balance) values
           ($1, 'gold', 0),
           ($1, 'dust', 0)
         on conflict (user_id, currency_code) do nothing`, [au.id]);
            // update balances
            await db_1.pool.query(`update wallets set balance = balance + $2 where user_id=$1 and currency_code='gold'`, [au.id, rewardGold]);
            await db_1.pool.query(`update wallets set balance = balance + $2 where user_id=$1 and currency_code='dust'`, [au.id, rewardDust]);
            return reply.send({ run_id: run.id, status: "finished", outcome });
        }
        // add another encounter
        await db_1.pool.query(`insert into encounters (id, run_id, idx, kind, seed, data, created_at)
       values (gen_random_uuid(), $1, $2, 'event', (random()*1000000)::int, $3::jsonb, now())`, [run.id, nextRoom, JSON.stringify({ text: "Туман кургану шепоче… ти знаходиш дрібний оберіг." })]);
        return reply.send({ run_id: run.id, status: "active", state: newState });
    });
    app.post("/runs/finish", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = zod_1.z.object({ run_id: zod_1.z.string().uuid() }).parse(req.body);
        const run = await db_1.pool.query(`select * from runs where id=$1 and user_id=$2`, [body.run_id, au.id]).then((r) => r.rows[0]);
        if (!run)
            return reply.code(404).send({ error: "RUN_NOT_FOUND" });
        return reply.send({ run });
    });
}
