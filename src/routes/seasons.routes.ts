import { FastifyInstance } from "fastify";
import { pool } from "../db";

export async function seasonsRoutes(app: FastifyInstance) {
  app.get("/seasons/active", async () => {
    const s = await pool.query(
      `select * from seasons where is_active=true and starts_at <= now() and ends_at > now()
       order by starts_at desc limit 1`
    ).then((r) => r.rows[0] ?? null);

    return { season: s };
  });

  app.get("/quests/today", async (req, reply) => {
    const au = await app.requireAuth(req);

    // ensure daily quests exist: assign first 3 active daily templates
    const templates = await pool.query(
      `select * from quest_templates where active=true and cadence='daily' order by created_at asc limit 3`
    ).then((r) => r.rows);

    const dayKey = await pool.query(`select (now() at time zone 'utc')::date as d`).then((r) => r.rows[0].d);

    for (const t of templates) {
      await pool.query(
        `insert into user_quests (id, user_id, quest_template_id, day_key, progress, created_at)
         values (gen_random_uuid(), $1, $2, $3, 0, now())
         on conflict (user_id, quest_template_id, day_key) do nothing`,
        [au.id, t.id, dayKey]
      );
    }

    const qs = await pool.query(
      `select uq.*, qt.code, qt.name, qt.description, qt.goal, qt.reward
       from user_quests uq
       join quest_templates qt on qt.id=uq.quest_template_id
       where uq.user_id=$1 and uq.day_key=$2
       order by qt.created_at asc`,
      [au.id, dayKey]
    ).then((r) => r.rows);

    return reply.send({ day_key: dayKey, quests: qs });
  });

  app.post("/rewards/claim", async (req, reply) => {
    const au = await app.requireAuth(req);
    const body = (req.body ?? {}) as any;

    // minimal: claim quest reward by user_quest id
    if (!body.user_quest_id) return reply.code(400).send({ error: "MISSING_USER_QUEST_ID" });

    const uq = await pool.query(
      `select uq.*, qt.reward
       from user_quests uq join quest_templates qt on qt.id=uq.quest_template_id
       where uq.id=$1 and uq.user_id=$2`,
      [body.user_quest_id, au.id]
    ).then((r) => r.rows[0]);

    if (!uq) return reply.code(404).send({ error: "NOT_FOUND" });
    if (uq.claimed_at) return reply.send({ ok: true, already: true });

    // simplistic: mark claimed and grant gold if in reward json
    await pool.query(`update user_quests set claimed_at=now() where id=$1`, [uq.id]);

    const reward = uq.reward ?? {};
    const gold = Number(reward.gold ?? 0);
    if (gold > 0) {
      await pool.query(
        `insert into wallets (user_id, currency_code, balance) values ($1,'gold',0)
         on conflict (user_id, currency_code) do nothing`,
        [au.id]
      );
      await pool.query(`update wallets set balance = balance + $2 where user_id=$1 and currency_code='gold'`, [au.id, gold]);
    }

    return reply.send({ ok: true, reward });
  });
}