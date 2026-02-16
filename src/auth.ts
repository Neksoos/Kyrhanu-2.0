import { FastifyPluginAsync } from "fastify";
import fp from "fastify-plugin";
import crypto from "crypto";
import { pool } from "./db";

declare module "fastify" {
  interface FastifyInstance {
    requireAuth: (req: any) => Promise<{ id: string }>;
    authUser: (req: any) => Promise<{ id: string } | null>;

    issueTokens: (
      userId: string,
      meta?: { ip?: string; userAgent?: string }
    ) => Promise<{ accessToken: string; refreshToken: string }>;
  }
}

function sha256(s: string) {
  return crypto.createHash("sha256").update(s).digest("hex");
}

export const authPlugin: FastifyPluginAsync = fp(async (app) => {
  const accessTtlSeconds = Number(process.env.ACCESS_TTL_SECONDS || 900); // 15 хв

  app.decorate("authUser", async (req: any) => {
    try {
      const header = req.headers?.authorization;
      if (!header) return null;

      const [type, token] = header.split(" ");
      if (type !== "Bearer" || !token) return null;

      const payload: any = app.jwt.verify(token);
      if (!payload?.sub) return null;

      return { id: String(payload.sub) };
    } catch {
      return null;
    }
  });

  app.decorate("requireAuth", async (req: any) => {
    const u = await app.authUser(req);
    if (!u) throw app.httpErrors.unauthorized();
    return u;
  });

  app.decorate(
    "issueTokens",
    async (userId: string, meta?: { ip?: string; userAgent?: string }) => {
      const accessToken = app.jwt.sign(
        { sub: userId },
        { expiresIn: accessTtlSeconds }
      );

      const refreshToken = crypto.randomBytes(32).toString("hex");
      const refreshHash = sha256(refreshToken);

      const ip = meta?.ip ?? "0.0.0.0";
      const userAgent = meta?.userAgent ?? "";

      // Зберігаємо refresh у auth_sessions (як в SQL міграції)
      await pool.query(
        `
        INSERT INTO auth_sessions (user_id, refresh_token_hash, ip, user_agent, expires_at)
        VALUES ($1, $2, $3, $4, NOW() + interval '30 days')
        `,
        [userId, refreshHash, ip, userAgent]
      );

      return { accessToken, refreshToken };
    }
  );
});