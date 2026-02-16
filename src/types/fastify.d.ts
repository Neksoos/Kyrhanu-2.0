import 'fastify';
import type { FastifyRequest } from 'fastify';
import type { FastifyJwt } from '@fastify/jwt';

type AuthUser = {
  id: string;
  role?: string;
};

declare module 'fastify' {
  interface FastifyInstance {
    jwt: FastifyJwt;

    issueTokens: (userId: string) => { accessToken: string; refreshToken: string };
    requireAuth: (req: FastifyRequest) => Promise<AuthUser>;
    authUser: (req: FastifyRequest) => Promise<AuthUser | null>;
  }

  interface FastifyRequest {
    authUser?: AuthUser;
  }
}