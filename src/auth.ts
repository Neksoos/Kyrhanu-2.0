import fp from "fastify-plugin";
import type { FastifyPluginAsync, FastifyRequest } from "fastify";

export const authPlugin: FastifyPluginAsync = fp(async (app) => {
  // Default: 24h. (Some WebViews block third-party cookies; longer-lived access
  // tokens reduce reliance on refresh cookies in production.)
  const accessTtlSeconds = Number(process.env.ACCESS_TTL_SECONDS || 86400);

  function getTokenFromHeader(request: FastifyRequest) {
    const h = request.headers["authorization"];
    if (!h) return null;
    const [type, token] = h.split(" ");
    if (type?.toLowerCase() !== "bearer" || !token) return null;
    return token;
  }

  app.decorate("requireAuth", async (request: FastifyRequest) => {
    const token = getTokenFromHeader(request);
    if (!token) throw app.httpErrors.unauthorized();

    try {
      const payload = app.jwt.verify<{ sub: string }>(token);
      (request as any).user = { id: payload.sub };
    } catch {
      throw app.httpErrors.unauthorized();
    }
  });

  app.decorate("issueAccessToken", (userId: string) => {
    return app.jwt.sign({ sub: userId }, { expiresIn: accessTtlSeconds });
  });
});

declare module "fastify" {
  interface FastifyInstance {
    requireAuth: (request: FastifyRequest) => Promise<void>;
    issueAccessToken: (userId: string) => string;
  }
}