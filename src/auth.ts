import { FastifyInstance, FastifyRequest } from "fastify";
import fp from "fastify-plugin";
import fastifyJwt from "@fastify/jwt";
import bcrypt from "bcryptjs";
import { env } from "./env";
import { sha256Hex } from "./utils/crypto";
import { pool } from "./db";

declare module "@fastify/jwt" {
  interface FastifyJWT {
    payload: { sub: string };
    user: { sub: string };
  }
}

export type AuthUser = { id: string };

export const authPlugin = fp(async (app: FastifyInstance) => {
  app.register(fastifyJwt, { secret: env.JWT_SECRET });

  app.decorate("authUser", async function authUser(req: FastifyRequest): Promise<AuthUser | null> {
    const hdr = req.headers.authorization;
    if (!hdr?.startsWith("Bearer ")) return null;
    const token = hdr.slice("Bearer ".length);
    try {
      const decoded = app.jwt.verify<{ sub: string }>(token);
      return { id: decoded.sub };
    } catch {
      return null;
    }
  });

  app.decorate("requireAuth", async function requireAuth(req: FastifyRequest): Promise<AuthUser> {
    const u = await (app as any).authUser(req);
    if (!u) {
      // `@fastify/sensible` adds httpErrors at runtime, but its typing can be finicky.
      // Use a safe runtime fallback so strict TS builds don't fail.
      const httpErrors = (app as any).httpErrors;
      if (httpErrors?.unauthorized) throw httpErrors.unauthorized("Unauthorized");
      const err: any = new Error("Unauthorized");
      err.statusCode = 401;
      throw err;
    }
    return u;
  });

  app.decorate("hashPassword", async (password: string) => bcrypt.hash(password, 10));
  app.decorate("verifyPassword", async (password: string, hash: string) => bcrypt.compare(password, hash));

  app.decorate("issueTokens", async function issueTokens(userId: string) {
    const access = app.jwt.sign({ sub: userId }, { expiresIn: "15m" });

    const refreshPlain = `${userId}.${Date.now()}.${Math.random()}`;
    const refreshHash = sha256Hex(refreshPlain);

    const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 24 * 30); // 30d
    await pool.query(
      `insert into auth_sessions (id, user_id, refresh_token_hash, user_agent, ip, created_at, expires_at)
       values (gen_random_uuid(), $1, $2, $3, $4, now(), $5)`,
      [userId, refreshHash, "", reqIpSafe(), expiresAt]
    );

    return { accessToken: access, refreshToken: refreshPlain, refreshExpiresAt: expiresAt.toISOString() };
  });

  function reqIpSafe() {
    return "0.0.0.0";
  }
});

declare module "fastify" {
  interface FastifyInstance {
    authUser: (req: FastifyRequest) => Promise<AuthUser | null>;
    requireAuth: (req: FastifyRequest) => Promise<AuthUser>;
    hashPassword: (password: string) => Promise<string>;
    verifyPassword: (password: string, hash: string) => Promise<boolean>;
    issueTokens: (userId: string) => Promise<{ accessToken: string; refreshToken: string; refreshExpiresAt: string }>;
  }
}