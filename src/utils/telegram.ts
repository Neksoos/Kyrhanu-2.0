import { hmacSha256Hex, safeEqual } from "./crypto";

function parseQueryString(qs: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of qs.split("&")) {
    const [k, v] = part.split("=");
    if (!k) continue;
    out[decodeURIComponent(k)] = decodeURIComponent(v ?? "");
  }
  return out;
}

/**
 * Telegram Mini App initData verification:
 * - secret_key = sha256(bot_token) as raw bytes
 * - data_check_string = sorted key=value joined by \n (excluding hash)
 * - hash = HMAC_SHA256(secret_key, data_check_string) hex
 */
export function verifyTelegramInitData(initData: string, botToken: string, maxAgeSec = 86400) {
  const data = parseQueryString(initData);
  const hash = data.hash;
  if (!hash) throw new Error("initData missing hash");

  const authDate = Number(data.auth_date ?? "0");
  const nowSec = Math.floor(Date.now() / 1000);
  if (!authDate || nowSec - authDate > maxAgeSec) throw new Error("initData expired");

  const pairs = Object.entries(data)
    .filter(([k]) => k !== "hash")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");

  const secretKey = Buffer.from(require("crypto").createHash("sha256").update(botToken).digest());
  const computed = hmacSha256Hex(secretKey, pairs);

  if (!safeEqual(computed, hash)) throw new Error("initData hash mismatch");

  // user is JSON string
  let user: any = null;
  if (data.user) user = JSON.parse(data.user);
  if (!user?.id) throw new Error("initData missing user");

  return {
    telegram_id: String(user.id),
    telegram_username: user.username ? String(user.username) : null,
    first_name: user.first_name ? String(user.first_name) : null,
    last_name: user.last_name ? String(user.last_name) : null,
    language_code: user.language_code ? String(user.language_code) : null,
    auth_date: authDate
  };
}

/**
 * Telegram Login Widget verification:
 * same idea: sort key=value excluding hash, HMAC with sha256(bot_token)
 */
export function verifyTelegramWidgetData(payload: Record<string, any>, botToken: string, maxAgeSec = 86400) {
  const data: Record<string, string> = {};
  for (const [k, v] of Object.entries(payload)) {
    if (v === undefined || v === null) continue;
    data[k] = String(v);
  }
  const hash = data.hash;
  if (!hash) throw new Error("widget missing hash");

  const authDate = Number(data.auth_date ?? "0");
  const nowSec = Math.floor(Date.now() / 1000);
  if (!authDate || nowSec - authDate > maxAgeSec) throw new Error("widget auth_date expired");

  const pairs = Object.entries(data)
    .filter(([k]) => k !== "hash")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");

  const secretKey = Buffer.from(require("crypto").createHash("sha256").update(botToken).digest());
  const computed = hmacSha256Hex(secretKey, pairs);

  if (!safeEqual(computed, hash)) throw new Error("widget hash mismatch");

  if (!data.id) throw new Error("widget missing id");

  return {
    telegram_id: String(data.id),
    telegram_username: data.username ? String(data.username) : null,
    first_name: data.first_name ? String(data.first_name) : null,
    last_name: data.last_name ? String(data.last_name) : null,
    photo_url: data.photo_url ? String(data.photo_url) : null,
    auth_date: authDate
  };
}