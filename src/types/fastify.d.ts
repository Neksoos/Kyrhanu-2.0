import "fastify";

export type AuthUser = {
  id: string;
};

declare module "fastify" {
  interface FastifyInstance {
    requireAuth: (req: any) => Promise<AuthUser>;
    authUser: (req: any) => Promise<AuthUser | null>;

    issueTokens: (
      userId: string,
      meta?: { ip?: string; userAgent?: string }
    ) => Promise<{
      accessToken: string;
      refreshToken: string;
    }>;
  }
}