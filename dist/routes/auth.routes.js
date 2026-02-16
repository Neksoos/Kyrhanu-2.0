"use strict";
// (файл довгий — тут саме цілий файл як у тебе, але з виправленими двома роутами)
Object.defineProperty(exports, "__esModule", { value: true });
exports.authRoutes = authRoutes;
const zod_1 = require("zod");
const env_1 = require("../env");
const db_1 = require("../db");
const crypto_1 = require("../utils/crypto");
const telegram_1 = require("../utils/telegram");
const http_1 = require("../utils/http");
const user_service_1 = require("../services/user.service");
async function authRoutes(app) {
    app.post("/auth/register", async (req, reply) => {
        const body = zod_1.z
            .object({
            email: zod_1.z.string().email(),
            password: zod_1.z.string().min(6),
            username: zod_1.z.string().min(2).max(32).optional()
        })
            .parse(req.body);
        const password_hash = (0, crypto_1.sha256Hex)(body.password);
        const exists = await db_1.pool.query(`select id from users where email = $1`, [body.email]).then((r) => r.rows[0]);
        if (exists)
            return reply.code(409).send({ error: "EMAIL_EXISTS" });
        const user = await db_1.pool
            .query(`insert into users (email, password_hash, username) values ($1, $2, $3) returning *`, [body.email, password_hash, body.username ?? null])
            .then((r) => r.rows[0]);
        await (0, user_service_1.createInitialPlayerData)(user.id);
        await (0, user_service_1.updateLastLogin)(user.id);
        const tokens = await app.issueTokens(user.id);
        (0, http_1.setRefreshCookie)(app, reply, tokens.refreshToken);
        return reply.send({ accessToken: tokens.accessToken, user: (0, http_1.sanitizeUser)(user) });
    });
    app.post("/auth/login", async (req, reply) => {
        const body = zod_1.z
            .object({
            email: zod_1.z.string().email(),
            password: zod_1.z.string().min(1)
        })
            .parse(req.body);
        const password_hash = (0, crypto_1.sha256Hex)(body.password);
        const user = await db_1.pool
            .query(`select * from users where email = $1 and password_hash = $2`, [body.email, password_hash])
            .then((r) => r.rows[0]);
        if (!user)
            return reply.code(401).send({ error: "INVALID_CREDENTIALS" });
        await (0, user_service_1.updateLastLogin)(user.id);
        const tokens = await app.issueTokens(user.id);
        (0, http_1.setRefreshCookie)(app, reply, tokens.refreshToken);
        return reply.send({ accessToken: tokens.accessToken, user: (0, http_1.sanitizeUser)(user) });
    });
    app.post("/auth/logout", async (_req, reply) => {
        (0, http_1.setRefreshCookie)(app, reply, "");
        return reply.send({ ok: true });
    });
    // ✅ FIXED: return 401 instead of 500 + correct verification used in utils/telegram.ts
    app.post("/auth/telegram/initdata", async (req, reply) => {
        const body = zod_1.z
            .object({
            initData: zod_1.z.string().min(1)
        })
            .parse(req.body);
        let tg;
        try {
            tg = (0, telegram_1.verifyTelegramInitData)(body.initData, env_1.env.TG_BOT_TOKEN);
        }
        catch (err) {
            req.log.warn({ err }, "telegram initData verification failed");
            return reply.code(401).send({ error: "INVALID_TELEGRAM_INITDATA" });
        }
        const existingByTg = await (0, user_service_1.findUserByTelegramId)(tg.telegram_id);
        // If already logged in with email/pass: link telegram_id to existing account
        const authUser = await app.authUser(req);
        if (authUser) {
            const current = await db_1.pool.query(`select * from users where id = $1`, [authUser.id]).then((r) => r.rows[0]);
            if (!current)
                return reply.code(401).send({ error: "UNAUTHORIZED" });
            if (existingByTg && existingByTg.id !== current.id) {
                return reply.code(409).send({ error: "TELEGRAM_ALREADY_LINKED" });
            }
            if (!current.telegram_id) {
                await db_1.pool.query(`update users set telegram_id = $1, telegram_username = $2, linked_at = now() where id = $3`, [tg.telegram_id, tg.telegram_username, current.id]);
            }
            await (0, user_service_1.updateLastLogin)(current.id);
            const tokens = await app.issueTokens(current.id);
            (0, http_1.setRefreshCookie)(app, reply, tokens.refreshToken);
            return reply.send({
                accessToken: tokens.accessToken,
                user: (0, http_1.sanitizeUser)({ ...current, telegram_id: tg.telegram_id, telegram_username: tg.telegram_username })
            });
        }
        // Not logged in: login/register by telegram_id
        const user = existingByTg ? existingByTg : await (0, user_service_1.createUserFromTelegram)(tg);
        await (0, user_service_1.updateLastLogin)(user.id);
        const tokens = await app.issueTokens(user.id);
        (0, http_1.setRefreshCookie)(app, reply, tokens.refreshToken);
        return reply.send({ accessToken: tokens.accessToken, user: (0, http_1.sanitizeUser)(user) });
    });
    // ✅ FIXED: return 401 instead of 500 if widget hash invalid
    app.post("/auth/telegram/widget", async (req, reply) => {
        const body = zod_1.z.record(zod_1.z.any()).parse(req.body);
        let tg;
        try {
            tg = (0, telegram_1.verifyTelegramWidgetData)(body, env_1.env.TG_WIDGET_BOT_TOKEN);
        }
        catch (err) {
            req.log.warn({ err }, "telegram widget verification failed");
            return reply.code(401).send({ error: "INVALID_TELEGRAM_WIDGET" });
        }
        const authUser = await app.authUser(req);
        const existingByTg = await (0, user_service_1.findUserByTelegramId)(tg.telegram_id);
        if (authUser) {
            const current = await db_1.pool.query(`select * from users where id = $1`, [authUser.id]).then((r) => r.rows[0]);
            if (!current)
                return reply.code(401).send({ error: "UNAUTHORIZED" });
            if (existingByTg && existingByTg.id !== current.id) {
                return reply.code(409).send({ error: "TELEGRAM_ALREADY_LINKED" });
            }
            if (!current.telegram_id) {
                await db_1.pool.query(`update users set telegram_id = $1, telegram_username = $2, linked_at = now() where id = $3`, [tg.telegram_id, tg.telegram_username, current.id]);
            }
            await (0, user_service_1.updateLastLogin)(current.id);
            const tokens = await app.issueTokens(current.id);
            (0, http_1.setRefreshCookie)(app, reply, tokens.refreshToken);
            return reply.send({
                accessToken: tokens.accessToken,
                user: (0, http_1.sanitizeUser)({ ...current, telegram_id: tg.telegram_id, telegram_username: tg.telegram_username })
            });
        }
        const user = existingByTg ? existingByTg : await (0, user_service_1.createUserFromTelegram)(tg);
        await (0, user_service_1.updateLastLogin)(user.id);
        const tokens = await app.issueTokens(user.id);
        (0, http_1.setRefreshCookie)(app, reply, tokens.refreshToken);
        return reply.send({ accessToken: tokens.accessToken, user: (0, http_1.sanitizeUser)(user) });
    });
}
