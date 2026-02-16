import fp from 'fastify-plugin';
import jwt from '@fastify/jwt';
import crypto from 'node:crypto';
import type { FastifyInstance, FastifyRequest } from 'fastify';

import { env } from './env';
import { getUserById } from './services/user.service';

type JwtPayload = {
  sub: string;
  role?: string;
  type?: 'access' | 'refresh';
};

function deriveJwtSecret(): string {
  const base = env.TG_BOT_TOKEN || env.TG_WIDGET_BOT_TOKEN || 'dev-secret';
  return crypto.createHash('sha256').update(base).digest('hex');
}

function unauthorized(message = 'Unauthorized'): Error {
  const err = new Error(message) as Error & { statusCode?: number };
  err.statusCode = 401;
  return err;
}

function getBearerToken(req: FastifyRequest): string | null {
  const h = req.headers.authorization;
  if (!h) return null;
  const m = /^Bearer\s+(.+)$/i.exec(h);
  return m?.[1] ?? null;
}

export const authPlugin = fp(async function authPlugin(app: FastifyInstance) {
  const secret = env.JWT_SECRET && env.JWT_SECRET.length >= 16 ? env.JWT_SECRET : deriveJwtSecret();

  await app.register(jwt, { secret });

  app.decorate('issueTokens', (userId: string) => {
    const sub = String(userId);
    const accessToken = app.jwt.sign({ type: 'access' }, { sub, expiresIn: '15m' });
    const refreshToken = app.jwt.sign({ type: 'refresh' }, { sub, expiresIn: '30d' });
    return { accessToken, refreshToken };
  });

  app.decorate('requireAuth', async (req: FastifyRequest) => {
    const token = getBearerToken(req);
    if (!token) throw unauthorized('Missing access token');

    let payload: JwtPayload;
    try {
      payload = app.jwt.verify<JwtPayload>(token);
    } catch {
      throw unauthorized('Invalid access token');
    }

    if (!payload?.sub) throw unauthorized('Invalid access token');
    if (payload.type && payload.type !== 'access') throw unauthorized('Invalid access token');

    const user = await getUserById(payload.sub);
    if (!user) throw unauthorized('User not found');

    const au = { id: payload.sub, role: payload.role };
    req.authUser = au;
    return au;
  });

  app.decorate('authUser', async (req: FastifyRequest) => {
    try {
      return await app.requireAuth(req);
    } catch {
      return null;
    }
  });
});

export default authPlugin;