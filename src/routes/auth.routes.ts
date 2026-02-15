import { FastifyInstance } from "fastify";
import { z } from "zod";
import { pool } from "../db";
import { sha256Hex } from "../utils/crypto";
import { verifyTelegramInitData, verifyTelegramWidgetData } from "../utils/telegram";
import { env } from "../env";

function setRefreshCookie(app: FastifyInstance, reply: any, refreshToken: string) {
  reply.setCookie("pk_refresh", refreshToken, {
    httpOnly: true,
    sameSite: "lax",
    secure: env.NODE_ENV !== "development",
    path: "/",
    domain: env.COOKIE_DOMAIN
  });
}

async function findUserByTelegramId(telegramId: string) {
  const res = await pool.query(`select * from users where telegram_id = $1`, [telegramId]);
  return res.rows[0] ?? null;
}

async function findUserByEmail(email: string) {
  const res = await pool.query(`select * from users where email = $1`, [email]);
  return res.rows[0] ?? null;
}

async function createUserFromTelegram(tg: { telegram_id: string; telegram_username: string | null }) {
  const res = await pool.query(
    `insert into users (telegram_id, telegram_username, created_at, last_login, flags)
     values ($1, $2, now(), now(), '{}'::jsonb)
     returning *`,
    [tg.telegram_id, tg.telegram_username]
  );
  return res.rows[0];
}

async function updateLastLogin(userId: string) {
  await pool.query(`update users set last_login = now() where id = $1`, [userId]);
}

export async function authRoutes(app: FastifyInstance) {
  // email register
  app.post("/auth/register", async (req, reply) => {
    const body = z.object({ email: z.string().email(), password: z.string().min(8).max(128) }).parse(req.body);

    const exists = await findUserByEmail(body.email);
    if (exists) return reply.code(409).send({ error: "EMAIL_TAKEN" });

    const hash = await app.hashPassword(body.password);
    const res = await pool.query(
      `insert into users (email, password_hash, created_at, last_login, flags)
       values ($1, $2, now(), now(), '{}'::jsonb)
       returning *`,
      [body.email, hash]
    );
    const user = res.rows[0];

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);
    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });

  // email login
  app.post("/auth/login", async (req, reply) => {
    const body = z.object({ email: z.string().email(), password: z.string().min(1) }).parse(req.body);

    const user = await findUserByEmail(body.email);
    if (!user?.password_hash) return reply.code(401).send({ error: "INVALID_CREDENTIALS" });

    const ok = await app.verifyPassword(body.password, user.password_hash);
    if (!ok) return reply.code(401).send({ error: "INVALID_CREDENTIALS" });

    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);
    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });

  // refresh
  app.post("/auth/refresh", async (req, reply) => {
    const refresh = (req.cookies as any)?.pk_refresh;
    if (!refresh) return reply.code(401).send({ error: "NO_REFRESH" });

    const refreshHash = sha256Hex(String(refresh));
    const row = await pool.query(
      `select * from auth_sessions where refresh_token_hash = $1 and revoked_at is null and expires_at > now()
       limit 1`,
      [refreshHash]
    );
    const sess = row.rows[0];
    if (!sess) return reply.code(401).send({ error: "INVALID_REFRESH" });

    const accessToken = app.jwt.sign({ sub: sess.user_id }, { expiresIn: "15m" });
    await updateLastLogin(sess.user_id);
    return reply.send({ accessToken });
  });

  // logout
  app.post("/auth/logout", async (req, reply) => {
    const refresh = (req.cookies as any)?.pk_refresh;
    if (refresh) {
      const refreshHash = sha256Hex(String(refresh));
      await pool.query(`update auth_sessions set revoked_at = now() where refresh_token_hash = $1`, [refreshHash]);
    }
    reply.clearCookie("pk_refresh", { path: "/", domain: env.COOKIE_DOMAIN });
    return reply.send({ ok: true });
  });

  // Mini App initData login
  app.post("/auth/telegram/initdata", async (req, reply) => {
    const body = z.object({ initData: z.string().min(10) }).parse(req.body);

    const tg = verifyTelegramInitData(body.initData, env.TG_BOT_TOKEN);

    // linking support: if Authorization bearer exists and that user has no telegram_id, link it
    const authUser = await app.authUser(req);

    const existingByTg = await findUserByTelegramId(tg.telegram_id);

    if (authUser) {
      // link telegram to current user if possible
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
      return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser({ ...current, telegram_id: tg.telegram_id, telegram_username: tg.telegram_username }) });
    }

    // no auth session: login/create by telegram
    const user = existingByTg ? existingByTg : await createUserFromTelegram(tg);
    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);
    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });

  // Browser widget login
  app.post("/auth/telegram/widget", async (req, reply) => {
    const body = z.record(z.any()).parse(req.body);
    const tg = verifyTelegramWidgetData(body, env.TG_WIDGET_BOT_TOKEN);

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
      return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser({ ...current, telegram_id: tg.telegram_id, telegram_username: tg.telegram_username }) });
    }

    const user = existingByTg ? existingByTg : await createUserFromTelegram(tg);
    await updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id);
    setRefreshCookie(app, reply, tokens.refreshToken);
    return reply.send({ accessToken: tokens.accessToken, user: sanitizeUser(user) });
  });
}

function sanitizeUser(u: any) {
  return {
    id: u.id,
    telegram_id: u.telegram_id,
    telegram_username: u.telegram_username,
    email: u.email,
    created_at: u.created_at,
    last_login: u.last_login,
    flags: u.flags ?? {}
  };
}