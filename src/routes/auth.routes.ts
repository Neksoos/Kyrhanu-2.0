import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import crypto from "crypto";
import { userService } from "../services/user.service";
import { setRefreshCookie, sanitizeUser } from "../utils/http";
import { verifyTelegramInitData } from "../utils/telegram";

function hashPassword(password: string) {
  const salt = crypto.randomBytes(16);
  const key = crypto.scryptSync(password, salt, 32);
  return `scrypt$1$${salt.toString("hex")}$${key.toString("hex")}`;
}

function verifyPassword(password: string, stored: string) {
  // expected format: scrypt$1$<saltHex>$<keyHex>
  const parts = stored.split("$");
  if (parts.length !== 4) return false;

  const [, , saltHex, keyHex] = parts;
  const salt = Buffer.from(saltHex, "hex");
  const expected = Buffer.from(keyHex, "hex");
  const actual = crypto.scryptSync(password, salt, expected.length);

  return crypto.timingSafeEqual(expected, actual);
}

export async function authRoutes(app: FastifyInstance) {
  // Email/password registration
  app.post("/auth/register", async (request, reply) => {
    const body = request.body as any;
    const email = String(body?.email ?? "").trim().toLowerCase();
    const password = String(body?.password ?? "");

    if (!email || !password) return reply.code(400).send({ error: "email and password required" });
    if (password.length < 6) return reply.code(400).send({ error: "password too short" });

    const existing = await userService.findByEmail(email);
    if (existing) return reply.code(409).send({ error: "Email already registered" });

    const passwordHash = hashPassword(password);
    const user = await userService.createWithEmail(email, passwordHash);

    const tokens = await app.issueTokens(user.id, {
      ip: request.ip,
      userAgent: request.headers["user-agent"] || ""
    });

    // refresh token in cookie for /auth/refresh
    setRefreshCookie(reply, tokens.refreshToken);

    return reply.send({
      ok: true,
      user: sanitizeUser(user),
      accessToken: tokens.accessToken
    });
  });

  // Email/password login
  app.post("/auth/login", async (request, reply) => {
    const body = request.body as any;
    const email = String(body?.email ?? "").trim().toLowerCase();
    const password = String(body?.password ?? "");

    if (!email || !password) return reply.code(400).send({ error: "email and password required" });

    const user = await userService.findByEmail(email);
    if (!user || !user.password_hash) return reply.code(401).send({ error: "Invalid credentials" });
    if (!verifyPassword(password, user.password_hash)) return reply.code(401).send({ error: "Invalid credentials" });

    await userService.updateLastLogin(user.id);

    const tokens = await app.issueTokens(user.id, {
      ip: request.ip,
      userAgent: request.headers["user-agent"] || ""
    });

    setRefreshCookie(reply, tokens.refreshToken);

    return reply.send({
      ok: true,
      user: sanitizeUser(user),
      accessToken: tokens.accessToken
    });
  });

  app.post(
    "/auth/telegram/initdata",
    async (request: FastifyRequest, reply: FastifyReply) => {
      const body = request.body as any;
      const initData: string = body?.initData;

      if (!initData) {
        return reply.code(400).send({ error: "initData required" });
      }

      let verified: ReturnType<typeof verifyTelegramInitData>;
      try {
        verified = verifyTelegramInitData(initData, process.env.TG_BOT_TOKEN || "");
      } catch (e: any) {
        return reply.code(401).send({
          error: "initData invalid",
          message: e?.message || String(e)
        });
      }

      const telegramIdStr = verified.telegram_id;
      if (!telegramIdStr) {
        return reply.code(400).send({ error: "initData missing telegram_id" });
      }

      const displayName =
        [verified.first_name, verified.last_name].filter(Boolean).join(" ") || "Player";

      let user = await userService.findByTelegramId(telegramIdStr);

      if (!user) {
        user = await userService.createWithTelegram(
          telegramIdStr,
          verified.telegram_username ?? null,
          displayName
        );
      } else {
        await userService.updateLastLogin(user.id);
      }

      const tokens = await app.issueTokens(user.id, {
        ip: request.ip,
        userAgent: request.headers["user-agent"] || ""
      });

      setRefreshCookie(reply, tokens.refreshToken);

      return reply.send({
        ok: true,
        user: {
          id: user.id,
          display_name: user.display_name,
          telegram_id: user.telegram_id,
          telegram_username: user.telegram_username
        },
        accessToken: tokens.accessToken
      });
    }
  );

  app.post("/auth/refresh", async (request, reply) => {
    const refreshToken = request.cookies?.refresh_token ?? (request.cookies as any)?.refreshToken;
    if (!refreshToken) {
      return reply.code(401).send({ error: "Missing refresh token" });
    }

    const user = await userService.findByRefreshToken(refreshToken);
    if (!user) {
      return reply.code(401).send({ error: "Invalid refresh token" });
    }

    const tokens = await app.issueTokens(user.id, {
      ip: request.ip,
      userAgent: request.headers["user-agent"] || ""
    });

    setRefreshCookie(reply, tokens.refreshToken);
    return reply.send({ ok: true, accessToken: tokens.accessToken });
  });

  app.post("/auth/logout", async (request, reply) => {
    const refreshToken = request.cookies?.refresh_token ?? (request.cookies as any)?.refreshToken;
    if (refreshToken) {
      await userService.invalidateRefreshToken(refreshToken);
    }

    reply.clearCookie("refresh_token", { path: "/" });
    return reply.send({ ok: true });
  });

  const meHandler = async (request: any, reply: any) => {
    const u = await app.authUser(request);
    if (!u) return reply.code(401).send({ error: "Unauthorized" });
    return reply.send({ ok: true, user: u });
  };

  // Keep both paths to match older frontend calls.
  app.get("/auth/me", meHandler);
  app.get("/me", meHandler);
}