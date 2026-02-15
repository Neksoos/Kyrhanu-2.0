import { FastifyInstance } from "fastify";
import { z } from "zod";
import { pool } from "../db";
import { generateDailyCharacter } from "../utils/stats";

function dayKeyUTC(d = new Date()) {
  const yyyy = d.getUTCFullYear();
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const dd = String(d.getUTCDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`; // date
}

async function ensureInventory(userId: string) {
  const inv = await pool.query(`select * from inventories where user_id = $1`, [userId]).then((r) => r.rows[0]);
  if (inv) return inv;

  const created = await pool
    .query(`insert into inventories (id, user_id, capacity, created_at) values (gen_random_uuid(), $1, 60, now()) returning *`, [userId])
    .then((r) => r.rows[0]);

  // starter wallets
  await pool.query(
    `insert into wallets (user_id, currency_code, balance)
     values ($1,'gold',250), ($1,'shards',10)
     on conflict (user_id, currency_code) do nothing`,
    [userId]
  );

  // starter items: give 1-2 instances
  const starterCodes = ["starter_hat", "starter_blade", "starter_charm"];
  for (const code of starterCodes) {
    const item = await pool.query(`select * from items where code=$1`, [code]).then((r) => r.rows[0]);
    if (!item) continue;
    const inst = await pool.query(
      `insert into item_instances (id, item_id, user_id, roll_seed, rolled_stats, created_at)
       values (gen_random_uuid(), $1, $2, (random()*1000000)::int, $3::jsonb, now())
       returning *`,
      [item.id, userId, JSON.stringify({})]
    ).then((r) => r.rows[0]);

    await pool.query(
      `insert into inventory_items (inventory_id, item_instance_id, quantity)
       values ($1, $2, 1)
       on conflict do nothing`,
      [created.id, inst.id]
    );
  }

  return created;
}

async function getTodayCharacter(userId: string) {
  const key = dayKeyUTC();
  const row = await pool.query(
    `select * from characters where user_id=$1 and day_key=$2 limit 1`,
    [userId, key]
  );
  return row.rows[0] ?? null;
}

async function createTodayCharacter(userId: string) {
  const key = dayKeyUTC();
  const seed = Math.floor(Math.random() * 2_000_000_000);
  const gen = generateDailyCharacter(seed);

  const row = await pool.query(
    `insert into characters (id, user_id, day_key, archetype, stats_seed, generated_stats, level, xp, created_at)
     values (gen_random_uuid(), $1, $2, $3, $4, $5::jsonb, 1, 0, now())
     on conflict (user_id, day_key) do update set user_id=excluded.user_id
     returning *`,
    [userId, key, gen.archetype_id, seed, JSON.stringify(gen)]
  );
  // ensure equipment slots exist
  const ch = row.rows[0];
  const slots = ["head", "weapon", "charm", "armor"];
  for (const s of slots) {
    await pool.query(
      `insert into equipment_slots (id, character_id, slot, item_instance_id)
       values (gen_random_uuid(), $1, $2, null)
       on conflict (character_id, slot) do nothing`,
      [ch.id, s]
    );
  }
  return ch;
}

export async function gameRoutes(app: FastifyInstance) {
  app.get("/health", async () => ({ ok: true }));

  app.get("/me", async (req, reply) => {
    const au = await app.requireAuth(req);
    const user = await pool.query(`select * from users where id=$1`, [au.id]).then((r) => r.rows[0]);
    if (!user) return reply.code(404).send({ error: "NOT_FOUND" });

    await ensureInventory(au.id);

    let character = await getTodayCharacter(au.id);
    if (!character) character = await createTodayCharacter(au.id);

    return reply.send({
      user: {
        id: user.id,
        telegram_id: user.telegram_id,
        telegram_username: user.telegram_username,
        email: user.email,
        flags: user.flags ?? {}
      },
      today: { day_key: dayKeyUTC(), character }
    });
  });

  app.post("/characters/generate", async (req, reply) => {
    const au = await app.requireAuth(req);
    const body = z.object({ force: z.boolean().optional() }).parse(req.body ?? {});

    const existing = await getTodayCharacter(au.id);
    if (existing && !body.force) {
      return reply.send({ day_key: dayKeyUTC(), character: existing, already: true });
    }

    // reroll policy: allow force only if user spends shards (example)
    if (existing && body.force) {
      const w = await pool.query(`select balance from wallets where user_id=$1 and currency_code='shards'`, [au.id]).then((r) => r.rows[0]);
      const bal = Number(w?.balance ?? 0);
      if (bal < 2) return reply.code(402).send({ error: "NOT_ENOUGH_SHARDS" });
      await pool.query(`update wallets set balance = balance - 2 where user_id=$1 and currency_code='shards'`, [au.id]);
      await pool.query(
        `delete from characters where id=$1`,
        [existing.id]
      );
    }

    const ch = await createTodayCharacter(au.id);
    return reply.send({ day_key: dayKeyUTC(), character: ch, already: false });
  });

  app.get("/inventory", async (req, reply) => {
    const au = await app.requireAuth(req);
    const inv = await ensureInventory(au.id);

    const items = await pool.query(
      `select ii.id as instance_id, ii.rolled_stats, i.code, i.name, i.rarity, i.slot
       from inventory_items invi
       join item_instances ii on ii.id = invi.item_instance_id
       join items i on i.id = ii.item_id
       where invi.inventory_id = $1
       order by i.rarity desc, i.name asc`,
      [inv.id]
    );

    return reply.send({ inventory: { id: inv.id, capacity: inv.capacity }, items: items.rows });
  });

  app.get("/equipment", async (req, reply) => {
    const au = await app.requireAuth(req);
    let ch = await getTodayCharacter(au.id);
    if (!ch) ch = await createTodayCharacter(au.id);

    const slots = await pool.query(
      `select es.slot, es.item_instance_id,
              i.code as item_code, i.name as item_name, i.rarity
       from equipment_slots es
       left join item_instances ii on ii.id = es.item_instance_id
       left join items i on i.id = ii.item_id
       where es.character_id = $1
       order by es.slot asc`,
      [ch.id]
    );
    return reply.send({ character_id: ch.id, slots: slots.rows });
  });

  app.post("/equipment", async (req, reply) => {
    const au = await app.requireAuth(req);
    const body = z
      .object({
        slot: z.string().min(2),
        item_instance_id: z.string().uuid().nullable()
      })
      .parse(req.body);

    let ch = await getTodayCharacter(au.id);
    if (!ch) ch = await createTodayCharacter(au.id);

    if (body.item_instance_id) {
      // verify ownership
      const own = await pool.query(`select 1 from item_instances where id=$1 and user_id=$2`, [body.item_instance_id, au.id]);
      if (own.rowCount === 0) return reply.code(403).send({ error: "NOT_OWNER" });
    }

    await pool.query(
      `update equipment_slots set item_instance_id=$1 where character_id=$2 and slot=$3`,
      [body.item_instance_id, ch.id, body.slot]
    );

    return reply.send({ ok: true });
  });
}