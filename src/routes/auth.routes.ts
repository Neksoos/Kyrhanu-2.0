import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import { userService } from "../services/user.service";
import { verifyTelegramInitData } from "../utils/telegram";

export async function authRoutes(app: FastifyInstance) {
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
        [verified.first_name, verified.last_name].filter(Boolean).join(" ") ||
        "Player";

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

      return reply.send({
        ok: true,
        user: {
          id: user.id,
          display_name: user.display_name,
          telegram_id: user.telegram_id,
          telegram_username: user.telegram_username
        },
        ...tokens
      });
    }
  );

  app.post("/auth/refresh", async (request, reply) => {
    const refreshToken = request.cookies?.refresh_token;
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

    return reply.send({ ok: true, ...tokens });
  });

  app.post("/auth/logout", async (request, reply) => {
    const refreshToken = request.cookies?.refresh_token;
    if (refreshToken) {
      await userService.invalidateRefreshToken(refreshToken);
    }

    reply.clearCookie("refresh_token", { path: "/" });
    return reply.send({ ok: true });
  });

  app.get("/auth/me", async (request, reply) => {
    const user = await app.authUser(request);
    if (!user) return reply.code(401).send({ error: "Unauthorized" });

    return reply.send({ ok: true, user });
  });
}