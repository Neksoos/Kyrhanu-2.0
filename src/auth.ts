import type { FastifyInstance, FastifyReply, FastifyRequest } from "fastify";
import fp from "fastify-plugin";
import crypto from "crypto";
import { pool } from "./db/pool";

function sha256Hex(input: string) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

function reqIpSafe() {
  return "";
}

export const authPlugin = fp(async function authPlugin(app: FastifyInstance) {
  // issue access+refresh; stores refresh hash in DB
  app.decorate("issueTokens", async function issueTokens(userId: string | number) {
    const uid = String(userId);
    const access = app.jwt.sign({ sub: uid }, { expiresIn: "15m" });

    const refreshPlain = `${uid}.${Date.now()}.${Math.random()}`;
    const refreshHash = sha256Hex(refreshPlain);

    const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString();

    // store refresh hash
    await pool.query(
      `insert into auth_sessions (id, user_id, refresh_token_hash, user_agent, ip, created_at, expires_at)
       values (gen_random_uuid(), $1, $2, $3, $4, now(), $5)`,
      [uid, refreshHash, "", reqIpSafe(), expiresAt]
    );

    return { accessToken: access, refreshToken: refreshPlain, refreshExpiresAt: expiresAt };
  });
});

declare module "fastify" {
  interface FastifyInstance {
    issueTokens: (
      userId: string | number
    ) => Promise<{ accessToken: string; refreshToken: string; refreshExpiresAt: string }>;
  }
}