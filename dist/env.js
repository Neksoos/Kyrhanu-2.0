"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.env = void 0;
const dotenv_1 = __importDefault(require("dotenv"));
const crypto_1 = __importDefault(require("crypto"));
dotenv_1.default.config();
function req(name) {
    const v = process.env[name];
    if (!v)
        throw new Error(`Missing env: ${name}`);
    return v;
}
/**
 * Railway UX note:
 * - DATABASE_URL is always required.
 * - TG_BOT_TOKEN is required for Telegram auth.
 * - JWT_SECRET is *recommended*.
 *   If it's missing, we fall back to a deterministic secret derived from TG_BOT_TOKEN,
 *   so the service can boot and tokens remain stable across restarts.
 *   Set JWT_SECRET in production for better security hygiene.
 */
function resolveJwtSecret() {
    const explicit = process.env.JWT_SECRET;
    if (explicit && explicit.trim().length >= 16)
        return explicit;
    const bot = process.env.TG_BOT_TOKEN;
    if (bot && bot.trim().length > 0) {
        const derived = crypto_1.default.createHash("sha256").update(bot).digest("hex");
        // eslint-disable-next-line no-console
        console.warn("[env] JWT_SECRET is missing/weak; using derived secret from TG_BOT_TOKEN. Set JWT_SECRET on Railway Variables.");
        return derived;
    }
    // If BOT token is also missing, keep the original strict behavior.
    return req("JWT_SECRET");
}
exports.env = {
    NODE_ENV: process.env.NODE_ENV ?? "development",
    PORT: Number(process.env.PORT ?? 8080),
    DATABASE_URL: req("DATABASE_URL"),
    JWT_SECRET: resolveJwtSecret(),
    TG_BOT_TOKEN: req("TG_BOT_TOKEN"),
    TG_WIDGET_BOT_TOKEN: process.env.TG_WIDGET_BOT_TOKEN ?? req("TG_BOT_TOKEN"),
    // IMPORTANT:
    // Якщо CORS_ORIGINS не заданий у Railway, preflight (OPTIONS) з фронту буде падати 404,
    // і браузер/Telegram WebView покаже "Failed to fetch".
    // Тому дефолт — "*" (дозволити всі), а в продакшені краще явно задати allowlist:
    //   CORS_ORIGINS=https://<front-domain>
    CORS_ORIGINS: (process.env.CORS_ORIGINS ?? "*")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    COOKIE_DOMAIN: process.env.COOKIE_DOMAIN // optional
};
