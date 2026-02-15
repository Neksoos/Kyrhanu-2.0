import dotenv from "dotenv";
dotenv.config();

function req(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing env: ${name}`);
  return v;
}

export const env = {
  NODE_ENV: process.env.NODE_ENV ?? "development",
  PORT: Number(process.env.PORT ?? 8080),

  DATABASE_URL: req("DATABASE_URL"),

  JWT_SECRET: req("JWT_SECRET"),

  TG_BOT_TOKEN: req("TG_BOT_TOKEN"),
  TG_WIDGET_BOT_TOKEN: process.env.TG_WIDGET_BOT_TOKEN ?? req("TG_BOT_TOKEN"),

  CORS_ORIGINS: (process.env.CORS_ORIGINS ?? "http://localhost:3000")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean),

  COOKIE_DOMAIN: process.env.COOKIE_DOMAIN // optional
};