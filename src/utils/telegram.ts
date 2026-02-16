import { hmacSha256, hmacSha256Hex, sha256Hex, safeEqual } from "./crypto";

/**
 * Telegram WebApp initData (Mini App) verification
 * Docs: https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
 *
 * Steps:
 * 1) Parse initData querystring into key/value map (URL-decoded)
 * 2) Build data_check_string: sorted "key=value" pairs (excluding hash) joined by "\n"
 * 3) secret_key = HMAC_SHA256(key="WebAppData", data=<bot_token>)
 * 4) computed_hash = HMAC_SHA256_HEX(key=secret_key, data=data_check_string)
 * 5) Compare computed_hash with provided hash (timing-safe)
 */
function parseInitData(qs: string): Record<string, string> {
  const params = new URLSearchParams(qs);
  const out: Record<string, string> = {};
  for (const [k, v] of params.entries()) out[k] = v;
  return out;
}

export type TelegramWebAppUser = {
  id: number;
  is_bot?: boolean;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  is_premium?: boolean;
  photo_url?: string;
};

export function verifyTelegramInitData(initData: string, botToken: string, maxAgeSec = 86400) {
  if (!initData) throw new Error("initData missing");

  const data = parseInitData(initData);
  const hash = data.hash;
  if (!hash) throw new Error("initData missing hash");

  const authDate = Number(data.auth_date ?? "0");
  const nowSec = Math.floor(Date.now() / 1000);
  if (!authDate || nowSec - authDate > maxAgeSec) throw new Error("initData auth_date expired");

  const dataCheckString = Object.entries(data)
    .filter(([k]) => k !== "hash")
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");

  // secret_key = HMAC_SHA256(key="WebAppData", data=<bot_token>)
  const secretKey = hmacSha256("WebAppData", botToken);
  const computed = hmacSha256Hex(secretKey, dataCheckString);

  if (!safeEqual(computed, hash)) throw new Error("initData hash mismatch");

  if (!data.user) throw new Error("initData missing user");

  let user: TelegramWebAppUser | null = null;
  try {
    user = JSON.parse(data.user) as TelegramWebAppUser;
  } catch {
    throw new Error("initData user JSON invalid");
  }

  if (!user?.id) throw new Error("initData user.id missing");

  return {
    telegram_id: String(user.id),
    telegram_username: user.username ?? null,
    first_name: user.first_name ?? null,
    last_name: user.last_name ?? null,
    photo_url: user.photo_url ?? null,
    auth_date: authDate,
    query_id: data.query_id ?? null,
    chat_instance: data.chat_instance ?? null,
    chat_type: data.chat_type ?? null,
    start_param: data.start_param ?? null
  };
}

/**
 * Telegram Login Widget verification (browser widget)
 * Docs: https://core.telegram.org/widgets/login#checking-authorization
 *
 * secret_key = SHA256(bot_token)
 * computed_hash = HMAC_SHA256_HEX(key=secret_key, data=data_check_string)
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

  const secretKey = Buffer.from(sha256Hex(botToken), "hex");
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