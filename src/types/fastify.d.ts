import "fastify";

declare module "fastify" {
  interface FastifyInstance {
    issueTokens: (
      userId: string,
      meta?: { ip?: string; userAgent?: string }
    ) => Promise<{ accessToken: string; refreshToken: string }>;

    verifyAccessToken: (token: string) => Promise<any | null>;

    authUser: (request: any) => Promise<{ id: string } | null>;
  }
}