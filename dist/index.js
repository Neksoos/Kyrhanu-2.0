"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const fastify_1 = __importDefault(require("fastify"));
const cors_1 = __importDefault(require("@fastify/cors"));
const cookie_1 = __importDefault(require("@fastify/cookie"));
const sensible_1 = __importDefault(require("@fastify/sensible"));
const env_1 = require("./env");
const db_1 = require("./db");
const auth_1 = require("./auth");
const auth_routes_1 = require("./routes/auth.routes");
const game_routes_1 = require("./routes/game.routes");
const runs_routes_1 = require("./routes/runs.routes");
const bosses_routes_1 = require("./routes/bosses.routes");
const guilds_routes_1 = require("./routes/guilds.routes");
const seasons_routes_1 = require("./routes/seasons.routes");
const shop_routes_1 = require("./routes/shop.routes");
const migrations_1 = require("./migrations");
function normalizeOriginEntry(v) {
    const s = v.trim().replace(/\/+$/, "");
    if (!s)
        return {};
    if (s === "*")
        return { any: true };
    try {
        // якщо дали повний URL
        const u = new URL(s.startsWith("http") ? s : `https://${s}`);
        // якщо запис був із схемою — збережемо origin, і хост теж
        if (s.startsWith("http"))
            return { origin: u.origin, host: u.host };
        // якщо запис без схеми — трактуємо як host allowlist
        return { host: u.host };
    }
    catch {
        // fallback
        return { host: s };
    }
}
function originKey(origin) {
    const s = origin.trim().replace(/\/+$/, "");
    const u = new URL(s);
    return { origin: u.origin, host: u.host };
}
async function main() {
    // Авто-міграції при старті (SQL файли в /sql). Безпечно повторювати (IF NOT EXISTS / ON CONFLICT).
    // Якщо треба вимкнути — встанови AUTO_MIGRATE=false.
    if ((process.env.AUTO_MIGRATE ?? "true").toLowerCase() !== "false") {
        const { applied } = await (0, migrations_1.runMigrations)();
        // eslint-disable-next-line no-console
        console.log("DB migrations applied:", applied);
    }
    const app = (0, fastify_1.default)({ logger: true });
    app.register(cookie_1.default);
    app.register(sensible_1.default);
    const entries = env_1.env.CORS_ORIGINS.map(normalizeOriginEntry);
    // Якщо список пустий (наприклад, env заданий як порожній рядок) — не ламаємо запити,
    // дозволяємо все і даємо змогу сервісу працювати.
    const allowAny = entries.length === 0 || entries.some((e) => e.any);
    const allowedOrigins = new Set(entries.map((e) => e.origin).filter(Boolean));
    const allowedHosts = new Set(entries.map((e) => e.host).filter(Boolean));
    const isAllowed = (origin) => {
        if (!origin || origin === "null")
            return true; // curl/server-to-server або WebView з Origin:null
        if (allowAny)
            return true;
        try {
            const k = originKey(origin);
            return allowedOrigins.has(k.origin) || allowedHosts.has(k.host);
        }
        catch {
            const o = origin.replace(/\/+$/, "");
            return allowedOrigins.has(o) || allowedHosts.has(o);
        }
    };
    // CORS plugin
    app.register(cors_1.default, {
        origin: (origin, cb) => {
            // fastify-cors при `true` віддзеркалює origin (і це сумісно з credentials)
            if (isAllowed(origin ?? undefined))
                return cb(null, true);
            return cb(null, false);
        },
        credentials: true,
        methods: ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allowedHeaders: ["Content-Type", "Authorization"],
        optionsSuccessStatus: 204
    });
    // IMPORTANT:
    // Не додаємо manual `app.options('*')`.
    // @fastify/cors сам реєструє wildcard preflight handler.
    // Якщо додати свій — Railway/production падає з помилкою:
    // "Method 'OPTIONS' already declared for route '*'".
    app.register(auth_1.authPlugin);
    app.get("/healthz", async () => {
        const dbOk = await (0, db_1.healthcheckDb)();
        return { ok: true, dbOk };
    });
    await (0, auth_routes_1.authRoutes)(app);
    await (0, game_routes_1.gameRoutes)(app);
    await (0, runs_routes_1.runsRoutes)(app);
    await (0, bosses_routes_1.bossesRoutes)(app);
    await (0, guilds_routes_1.guildsRoutes)(app);
    await (0, seasons_routes_1.seasonsRoutes)(app);
    await (0, shop_routes_1.shopRoutes)(app);
    app.setErrorHandler((err, req, reply) => {
        req.log.error(err);
        const status = err.statusCode ?? 500;
        reply.code(status).send({ error: err.message ?? "Server error" });
    });
    await app.listen({ port: env_1.env.PORT, host: "0.0.0.0" });
}
main().catch((e) => {
    console.error(e);
    process.exit(1);
});
