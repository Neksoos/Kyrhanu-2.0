import Fastify from "fastify";
import cors from "@fastify/cors";
import cookie from "@fastify/cookie";
import sensible from "@fastify/sensible";
import jwt from "@fastify/jwt";
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
import { runMigrations } from "./migrations";

function normalizeOriginEntry(v: string): { origin?: string; host?: string; any?: boolean } {
  const s = v.trim().replace(/\/+$/, "");
  if (!s) return {};
  if (s === "*") return { any: true };
  try {
    const u = new URL(s.startsWith("http") ? s : `https://${s}`);
    if (s.startsWith("http")) return { origin: u.origin, host: u.host };
    return { host: u.host };
  } catch {
    return { host: s };
  }
}

function originKey(origin: string): { origin: string; host: string } {
  const s = origin.trim().replace(/\/+$/, "");
  const u = new URL(s);
  return { origin: u.origin, host: u.host };
}

async function main() {
  if ((process.env.AUTO_MIGRATE ?? "true").toLowerCase() !== "false") {
    const { applied } = await runMigrations();
    console.log("DB migrations applied:", applied);
  }

  const app = Fastify({ logger: true });

  app.register(cookie);
  app.register(sensible);

  // JWT plugin must be registered to add `app.jwt` (sign/verify/etc.)
  // and to get correct TypeScript types.
  app.register(jwt, { secret: env.JWT_SECRET });

  const entries = env.CORS_ORIGINS.map(normalizeOriginEntry);
  const allowAny = entries.length === 0 || entries.some((e) => e.any);
  const allowedOrigins = new Set(entries.map((e) => e.origin).filter(Boolean) as string[]);
  const allowedHosts = new Set(entries.map((e) => e.host).filter(Boolean) as string[]);

  const isAllowed = (origin?: string) => {
    if (!origin || origin === "null") return true;
    if (allowAny) return true;
    try {
      const k = originKey(origin);
      return allowedOrigins.has(k.origin) || allowedHosts.has(k.host);
    } catch {
      const o = origin.replace(/\/+$/, "");
      return allowedOrigins.has(o) || allowedHosts.has(o);
    }
  };

  app.register(cors, {
    origin: (origin, cb) => {
      if (isAllowed(origin ?? undefined)) return cb(null, true);
      return cb(null, false);
    },
    credentials: true,
    methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allowedHeaders: ["Content-Type", "Authorization"],
    optionsSuccessStatus: 204
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