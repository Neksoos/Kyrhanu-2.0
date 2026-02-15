import Fastify from "fastify";
import cors from "@fastify/cors";
import cookie from "@fastify/cookie";
import { env } from "./env";
import { healthcheckDb } from "./db";
import { authPlugin } from "./auth";
import { authRoutes } from "./routes/auth.routes";
import { gameRoutes } from "./routes/game.routes";
import { runsRoutes } from "./routes/runs.routes";
import { bossesRoutes } from "./routes/bosses.routes";
import { guildsRoutes } from "./routes/guilds.routes";
import { seasonsRoutes } from "./routes/seasons.routes";
import { shopRoutes } from "./routes/shop.routes";

async function main() {
  const app = Fastify({ logger: true });

  app.register(cookie);

  app.register(cors, {
    origin: (origin, cb) => {
      // allow no-origin (curl, server-to-server)
      if (!origin) return cb(null, true);
      const ok = env.CORS_ORIGINS.includes(origin);
      cb(null, ok);
    },
    credentials: true
  });

  app.register(authPlugin);

  app.get("/healthz", async () => {
    const dbOk = await healthcheckDb();
    return { ok: true, dbOk };
  });

  await authRoutes(app);
  await gameRoutes(app);
  await runsRoutes(app);
  await bossesRoutes(app);
  await guildsRoutes(app);
  await seasonsRoutes(app);
  await shopRoutes(app);

  app.setErrorHandler((err, req, reply) => {
    req.log.error(err);
    const status = (err as any).statusCode ?? 500;
    reply.code(status).send({ error: err.message ?? "Server error" });
  });

  await app.listen({ port: env.PORT, host: "0.0.0.0" });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});