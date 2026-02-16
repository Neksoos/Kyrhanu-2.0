import type { FastifyInstance, FastifyRequest } from "fastify";
import fp from "fastify-plugin";
import jwt from "@fastify/jwt";
import crypto from "node:crypto";
import { pool } from "./db";

export type AuthUser = { id: string };

function sha256(input: string) {
  return crypto.createHash("sha256").update(input).digest("hex");
}

function reqIpSafe() {
  return "0.0.0.0";
}

/**
 * Auth plugin:
 * - provides `app.issueTokens(userId)`
 * - provides `app.authUser(req)` which reads cookie refreshToken
 * - provides `app.requireAuth(req)` which throws 401 if unauthenticated
 */
export const authPlugin = fp(async (app: FastifyInstance) => {
  app.register(jwt, {
    secret: process.env.JWT_SECRET || process.env.TG_BOT_TOKEN || "dev-secret",
  });

  app.decorate("authUser", async function authUser(req: FastifyRequest): Promise<AuthUser | null> {
    try {
      const token = (req.cookies as any)?.refreshToken;
      if (!token) return null;
      const decoded = app.jwt.verify<{ sub: string }>(token);
      return { id: decoded.sub };
    } catch {
      return null;
    }
  });

  app.decorate("requireAuth", async function requireAuth(req: FastifyRequest): Promise<AuthUser> {
    const user = await (app as any).authUser(req);
    if (!user) {
      const err: any = new Error("Unauthorized");
      err.statusCode = 401;
      throw err;
    }
    return user;
  });

  app.decorate("issueTokens", async function issueTokens(userId: string) {
    const accessToken = app.jwt.sign({ sub: userId }, { expiresIn: "15m" });

    const refreshPlain = `${userId}.${Date.now()}.${Math.random()}`;
    const refreshToken = app.jwt.sign({ sub: userId, jti: refreshPlain }, { expiresIn: "30d" });

    const refreshHash = sha256(refreshToken);
    const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 24 * 30).toISOString();

    await pool.query(
      `INSERT INTO sessions (user_id, refresh_hash, user_agent, ip, expires_at)
       VALUES ($1, $2, $3, $4, $5)
       ON CONFLICT (refresh_hash) DO NOTHING`,
      [userId, refreshHash, "", reqIpSafe(), expiresAt]
    );

    return { accessToken, refreshToken, refreshExpiresAt: expiresAt };
  });
});

declare module "fastify" {
  interface FastifyInstance {
    authUser: (req: FastifyRequest) => Promise<AuthUser | null>;
    requireAuth: (req: FastifyRequest) => Promise<AuthUser>;
    issueTokens: (userId: string) => Promise<{ accessToken: string; refreshToken: string; refreshExpiresAt: string }>;
  }
}