// (файл довгий — тут саме цілий файл як у тебе, але з виправленими двома роутами)

import { FastifyInstance } from "fastify";
import { z } from "zod";
import { env } from "../env";
import { pool } from "../db";
import { sha256Hex } from "../utils/crypto";
import { verifyTelegramInitData, verifyTelegramWidgetData } from "../utils/telegram";
import { sanitizeUser, setRefreshCookie } from "../utils/http";
import {
  createInitialPlayerData,
  createUserFromTelegram,
  findUserByTelegramId,
  updateLastLogin
} from "../services/user.service";

export async function authRoutes(app: FastifyInstance) {
  app.post("/auth/register", async (req, reply) => {
    const body = z
      .object({
        email: z.string().email(),
        password: z.string().min(6),
        username: z.string().min(2).max(32).optional()
      })
      .parse(req.body);

    const password_hash = sha256Hex(body.password);

    const exists = await pool.query(`select id from users where email = $1`, [body.email]).then((r) => r.rows[0]);
    if (exists) return reply.code(409).send({ error: "EMAIL_EXISTS" });

    const user = await pool
      .query(
        `insert into users (email, password_hash, username) values ($1, $2, $3) returning *`,
        [body.email, password_hash, body.username ?? null]
      )
      .then((r) => r.rows[0]);

    await createInitialPlayerData(user.id);
    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);

    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });

  app.post("/auth/login", async (req, reply) => {
    const body = z
      .object({
        email: z.string().email(),
        password: z.string().min(1)
      })
      .parse(req.body);

    const password_hash = sha256Hex(body.password);

    const user = await pool
      .query(`select * from users where email = $1 and password_hash = $2`, [body.email, password_hash])
      .then((r) => r.rows[0]);

    if (!user) return reply.code(401).send({ error: "INVALID_CREDENTIALS" });

    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);

    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });

  app.post("/auth/logout", async (_req, reply) => {
    setRefreshCookie(app, reply, "");
    return reply.send({ ok: true });
  });

  // ✅ FIXED: return 401 instead of 500 + correct verification used in utils/telegram.ts
  app.post("/auth/telegram/initdata", async (req, reply) => {
    const body = z
      .object({
        initData: z.string().min(1)
      })
      .parse(req.body);

    let tg: ReturnType<typeof verifyTelegramInitData>;
    try {
      tg = verifyTelegramInitData(body.initData, env.TG_BOT_TOKEN);
    } catch (err) {
      req.log.warn({ err }, "telegram initData verification failed");
      return reply.code(401).send({ error: "INVALID_TELEGRAM_INITDATA" });
    }

    const existingByTg = await findUserByTelegramId(tg.telegram_id);

    // If already logged in with email/pass: link telegram_id to existing account
    const authUser = await app.authUser(req);
    if (authUser) {
      const current = await pool.query(`select * from users where id = $1`, [authUser.id]).then((r) => r.rows[0]);
      if (!current) return reply.code(401).send({ error: "UNAUTHORIZED" });

      if (existingByTg && existingByTg.id !== current.id) {
        return reply.code(409).send({ error: "TELEGRAM_ALREADY_LINKED" });
      }

      if (!current.telegram_id) {
        await pool.query(
          `update users set telegram_id = $1, telegram_username = $2, linked_at = now() where id = $3`,
          [tg.telegram_id, tg.telegram_username, current.id]
        );
      }

      await updateLastLogin(current.id);
      const tokens = await app.issueTokens(current.id);
      setRefreshCookie(app, reply, tokens.refreshToken);
      return reply.send({
        accessToken: tokens.accessToken,
        user: sanitizeUser({ ...current, telegram_id: tg.telegram_id, telegram_username: tg.telegram_username })
      });
    }

    // Not logged in: login/register by telegram_id
    const user = existingByTg ? existingByTg : await createUserFromTelegram(tg);
    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);
    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });

  // ✅ FIXED: return 401 instead of 500 if widget hash invalid
  app.post("/auth/telegram/widget", async (req, reply) => {
    const body = z.record(z.any()).parse(req.body);

    let tg: ReturnType<typeof verifyTelegramWidgetData>;
    try {
      tg = verifyTelegramWidgetData(body, env.TG_WIDGET_BOT_TOKEN);
    } catch (err) {
      req.log.warn({ err }, "telegram widget verification failed");
      return reply.code(401).send({ error: "INVALID_TELEGRAM_WIDGET" });
    }

    const authUser = await app.authUser(req);
    const existingByTg = await findUserByTelegramId(tg.telegram_id);

    if (authUser) {
      const current = await pool.query(`select * from users where id = $1`, [authUser.id]).then((r) => r.rows[0]);
      if (!current) return reply.code(401).send({ error: "UNAUTHORIZED" });

      if (existingByTg && existingByTg.id !== current.id) {
        return reply.code(409).send({ error: "TELEGRAM_ALREADY_LINKED" });
      }
      if (!current.telegram_id) {
        await pool.query(
          `update users set telegram_id = $1, telegram_username = $2, linked_at = now() where id = $3`,
          [tg.telegram_id, tg.telegram_username, current.id]
        );
      }
      await updateLastLogin(current.id);
      const tokens = await app.issueTokens(current.id);
      setRefreshCookie(app, reply, tokens.refreshToken);
      return reply.send({
        accessToken: tokens.accessToken,
        user: sanitizeUser({ ...current, telegram_id: tg.telegram_id, telegram_username: tg.telegram_username })
      });
    }

    const user = existingByTg ? existingByTg : await createUserFromTelegram(tg);
    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);
    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });
}