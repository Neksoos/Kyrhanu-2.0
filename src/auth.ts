import fp from "fastify-plugin";
import jwt from "@fastify/jwt";
import crypto from "crypto";
import { pool } from "./db";

function base64url(buf: Buffer) {
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function sha256Hex(input: string) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

function makeRandomToken(bytes = 32) {
  return base64url(crypto.randomBytes(bytes));
}

function makeAccessToken(app: any, userId: string) {
  const payload = { sub: userId };
  return app.jwt.sign(payload, { expiresIn: "15m" });
}

export type IssueTokensMeta = {
  ip?: string;
  userAgent?: string;
};

export default fp(async function authPlugin(app) {
  const jwtSecret =
    process.env.JWT_SECRET && process.env.JWT_SECRET.length >= 16
      ? process.env.JWT_SECRET
      : process.env.TG_BOT_TOKEN
      ? sha256Hex(process.env.TG_BOT_TOKEN)
      : sha256Hex("dev-secret");

  app.register(jwt, { secret: jwtSecret });

  app.decorate("issueTokens", async (userId: string) => {
    const accessToken = makeAccessToken(app, userId);

    const refreshToken = makeRandomToken(48);
    const refreshTokenHash = sha256Hex(refreshToken);

    const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 24 * 30); // 30d

    // IMPORTANT: explicitly generate UUID id to avoid relying on DB default
    // (some deployments may miss the default on auth_sessions.id)
    const sessionId = "gen_random_uuid()";

    await pool.query(
      `
      insert into auth_sessions (id, user_id, refresh_token_hash, expires_at)
      values (${sessionId}, $1, $2, $3)
      `,
      [userId, refreshTokenHash, expiresAt]
    );

    return { accessToken, refreshToken };
  });

  app.decorate("verifyAccessToken", async (token: string) => {
    try {
      return await app.jwt.verify(token);
    } catch {
      return null;
    }
  });

  app.decorate("authUser", async (request: any) => {
    const hdr = request.headers?.authorization;
    if (!hdr || typeof hdr !== "string") return null;
    const m = hdr.match(/^Bearer\s+(.+)$/i);
    if (!m) return null;

    const token = m[1];
    const payload = await app.verifyAccessToken(token);
    if (!payload || !payload.sub) return null;

    return { id: String(payload.sub) };
  });
});