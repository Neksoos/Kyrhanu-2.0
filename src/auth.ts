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
  const accessTtlSeconds = Number(process.env.ACCESS_TTL_SECONDS || 900);

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
      // Генеруємо access token
      const accessToken = app.jwt.sign({ sub: userId }, { expiresIn: accessTtlSeconds });

      // Генеруємо випадковий refresh‑token і його хеш
      const refreshToken = crypto.randomBytes(32).toString("hex");
      const refreshHash = sha256(refreshToken);

      // IP та userAgent
      const ip = meta?.ip ?? "0.0.0.0";
      const userAgent = meta?.userAgent ?? "";

      // Генеруємо UUID для auth‑сесії. Без явного id insert провалюється,
      // оскільки поле id таблиці auth_sessions не має дефолту у старих схемах.
      const sessionId = crypto.randomUUID?.() ?? crypto.randomBytes(16).toString("hex");

      // Зберігаємо refresh‑сесію, явно передаючи id
      await pool.query(
        `
        INSERT INTO auth_sessions (id, user_id, refresh_token_hash, ip, user_agent, expires_at)
        VALUES ($1, $2, $3, $4, $5, NOW() + interval '30 days')
        `,
        [sessionId, userId, refreshHash, ip, userAgent]
      );

      return { accessToken, refreshToken };
    }
  );
});