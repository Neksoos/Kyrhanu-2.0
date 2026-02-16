"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.guildsRoutes = guildsRoutes;
const zod_1 = require("zod");
const db_1 = require("../db");
const crypto_1 = require("../utils/crypto");
async function guildsRoutes(app) {
    app.get("/guilds", async (req, reply) => {
        const au = await app.requireAuth(req);
        const g = await db_1.pool.query(`select g.*
       from guild_members gm join guilds g on g.id=gm.guild_id
       where gm.user_id=$1
       limit 1`, [au.id]).then((r) => r.rows[0] ?? null);
        return reply.send({ guild: g });
    });
    app.post("/guilds/create", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = zod_1.z.object({ name: zod_1.z.string().min(3).max(32), tag: zod_1.z.string().min(2).max(6) }).parse(req.body);
        const joinCode = (0, crypto_1.randomId)("G-").slice(0, 10);
        const guild = await db_1.pool.query(`insert into guilds (id, name, tag, owner_user_id, join_code, created_at)
       values (gen_random_uuid(), $1, $2, $3, $4, now())
       returning *`, [body.name, body.tag.toUpperCase(), au.id, joinCode]).then((r) => r.rows[0]);
        await db_1.pool.query(`insert into guild_members (guild_id, user_id, role, joined_at)
       values ($1, $2, 'owner', now())`, [guild.id, au.id]);
        return reply.send({ guild });
    });
    app.post("/guilds/join", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = zod_1.z.object({ join_code: zod_1.z.string().min(4) }).parse(req.body);
        const guild = await db_1.pool.query(`select * from guilds where join_code=$1`, [body.join_code]).then((r) => r.rows[0]);
        if (!guild)
            return reply.code(404).send({ error: "GUILD_NOT_FOUND" });
        await db_1.pool.query(`insert into guild_members (guild_id, user_id, role, joined_at)
       values ($1, $2, 'member', now())
       on conflict (guild_id, user_id) do nothing`, [guild.id, au.id]);
        return reply.send({ ok: true, guild });
    });
    app.post("/guilds/leave", async (req, reply) => {
        const au = await app.requireAuth(req);
        await db_1.pool.query(`delete from guild_members where user_id=$1`, [au.id]);
        return reply.send({ ok: true });
    });
    app.post("/guilds/boss/attack", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = zod_1.z.object({ live_boss_id: zod_1.z.string().uuid() }).parse(req.body);
        const gm = await db_1.pool.query(`select guild_id from guild_members where user_id=$1 limit 1`, [au.id]).then((r) => r.rows[0]);
        if (!gm)
            return reply.code(400).send({ error: "NO_GUILD" });
        // reuse world boss damage but attribute to guild
        await db_1.pool.query(`insert into guild_boss_damage (id, guild_id, live_boss_id, user_id, damage, created_at)
       values (gen_random_uuid(), $1, $2, $3, 10, now())`, [gm.guild_id, body.live_boss_id, au.id]);
        return reply.send({ ok: true, damage: 10 });
    });
}
