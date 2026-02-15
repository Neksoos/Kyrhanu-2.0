import dotenv from "dotenv";
import crypto from "crypto";

dotenv.config();

function req(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing env: ${name}`);
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
function resolveJwtSecret(): string {
  const explicit = process.env.JWT_SECRET;
  if (explicit && explicit.trim().length >= 16) return explicit;

  const bot = process.env.TG_BOT_TOKEN;
  if (bot && bot.trim().length > 0) {
    const derived = crypto.createHash("sha256").update(bot).digest("hex");
    // eslint-disable-next-line no-console
    console.warn(
      "[env] JWT_SECRET is missing/weak; using derived secret from TG_BOT_TOKEN. Set JWT_SECRET on Railway Variables."
    );
    return derived;
  }

  // If BOT token is also missing, keep the original strict behavior.
  return req("JWT_SECRET");
}

export const env = {
  NODE_ENV: process.env.NODE_ENV ?? "development",
  PORT: Number(process.env.PORT ?? 8080),

  DATABASE_URL: req("DATABASE_URL"),

  JWT_SECRET: resolveJwtSecret(),

  TG_BOT_TOKEN: req("TG_BOT_TOKEN"),
  TG_WIDGET_BOT_TOKEN: process.env.TG_WIDGET_BOT_TOKEN ?? req("TG_BOT_TOKEN"),

  CORS_ORIGINS: (process.env.CORS_ORIGINS ?? "http://localhost:3000")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),

  COOKIE_DOMAIN: process.env.COOKIE_DOMAIN // optional
};