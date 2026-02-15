import { FastifyInstance } from "fastify";
import { z } from "zod";
import { pool } from "../db";
import { damageFormula } from "../utils/stats";

export async function bossesRoutes(app: FastifyInstance) {
  app.get("/bosses/active", async (req, reply) => {
    const boss = await pool.query(
      `select lb.*, bt.code as template_code, bt.name as template_name, bt.description
       from live_bosses lb
       join boss_templates bt on bt.id = lb.boss_template_id
       where lb.status='active' and lb.starts_at <= now() and lb.ends_at > now()
       order by lb.starts_at desc
       limit 1`
    ).then((r) => r.rows[0]);

    if (!boss) return reply.send({ boss: null });
    return reply.send({ boss });
  });

  app.post("/bosses/attack", async (req, reply) => {
    const au = await app.requireAuth(req);
    const body = z.object({ live_boss_id: z.string().uuid() }).parse(req.body);

    const boss = await pool.query(`select * from live_bosses where id=$1 and status='active'`, [body.live_boss_id]).then((r) => r.rows[0]);
    if (!boss) return reply.code(404).send({ error: "BOSS_NOT_FOUND" });

    const ch = await pool.query(
      `select generated_stats from characters where user_id=$1 and day_key = (now() at time zone 'utc')::date limit 1`,
      [au.id]
    ).then((r) => r.rows[0]);

    if (!ch) return reply.code(400).send({ error: "NO_TODAY_CHARACTER" });

    const stats = (ch.generated_stats?.stats ?? ch.generated_stats?.stats ?? ch.generated_stats?.stats) || ch.generated_stats?.stats;
    const s = stats ?? ch.generated_stats?.stats ?? ch.generated_stats?.stats ?? ch.generated_stats?.stats ?? { atk: 10, crit: 5, luck: 5 };
    const { damage, crit } = damageFormula({ atk: Number(s.atk ?? 10), crit: Number(s.crit ?? 5), luck: Number(s.luck ?? 5) });

    // apply damage atomically
    const updated = await pool.query(
      `update live_bosses set hp = greatest(0, hp - $1)
       where id=$2
       returning hp, max_hp`,
      [damage, boss.id]
    ).then((r) => r.rows[0]);

    await pool.query(
      `insert into boss_damage (id, live_boss_id, user_id, damage, created_at)
       values (gen_random_uuid(), $1, $2, $3, now())`,
      [boss.id, au.id, damage]
    );

    // if dead -> mark defeated
    if (Number(updated.hp) <= 0) {
      await pool.query(`update live_bosses set status='defeated' where id=$1`, [boss.id]);
    }

    return reply.send({ damage, crit, boss: { hp: updated.hp, max_hp: updated.max_hp, defeated: Number(updated.hp) <= 0 } });
  });
}