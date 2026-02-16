import type { FastifyInstance } from "fastify";
import { verifyTelegramInitData } from "../telegram/verify";
import { userService } from "../services/user.service";
import { sanitizeUser, setRefreshCookie } from "../utils/http";

export async function authRoutes(app: FastifyInstance) {
  // Telegram WebApp initData -> login/register
  app.post("/auth/telegram/initdata", async (request, reply) => {
    const { initData } = request.body as any;
    if (!initData) return reply.code(400).send({ error: "initData required" });

    const verified = verifyTelegramInitData(initData, process.env.TG_BOT_TOKEN || "");
    const tg = verified.user;

    let user = await userService.findByTelegramId(tg.id);
    if (!user) {
      user = await userService.createFromTelegram(tg);
    } else {
      await userService.updateLastLogin(user.id);
    }

    const tokens = await app.issueTokens(String(user.id));
    setRefreshCookie(reply, tokens.refreshToken);

    return reply.send({
      user: sanitizeUser(user),
      accessToken: tokens.accessToken,
    });
  });

  // Refresh access token
  app.post("/auth/refresh", async (request, reply) => {
    const refreshToken = (request.cookies as any)?.refreshToken;
    if (!refreshToken) return reply.code(401).send({ error: "No refresh token" });

    const current = await userService.findByRefreshToken(refreshToken);
    if (!current) return reply.code(401).send({ error: "Invalid refresh token" });

    const tokens = await app.issueTokens(String(current.id));
    setRefreshCookie(reply, tokens.refreshToken);

    return reply.send({ accessToken: tokens.accessToken });
  });

  // Logout
  app.post("/auth/logout", async (request, reply) => {
    const refreshToken = (request.cookies as any)?.refreshToken;
    if (refreshToken) await userService.invalidateRefreshToken(refreshToken);

    setRefreshCookie(reply, "");
    return reply.send({ ok: true });
  });

  // Get current user (by refresh cookie)
  app.get("/auth/me", async (request, reply) => {
    const refreshToken = (request.cookies as any)?.refreshToken;
    if (!refreshToken) return reply.code(401).send({ error: "Unauthorized" });

    const user = await userService.findByRefreshToken(refreshToken);
    if (!user) return reply.code(401).send({ error: "Unauthorized" });

    return reply.send({ user: sanitizeUser(user) });
  });

  // DEV endpoint
  app.get("/auth/ping", async (_req, reply) => reply.send({ ok: true }));
}