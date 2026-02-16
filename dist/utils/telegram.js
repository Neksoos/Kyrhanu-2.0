"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.verifyTelegramWidgetAuth = void 0;
exports.verifyTelegramWidgetData = verifyTelegramWidgetData;
exports.verifyTelegramInitData = verifyTelegramInitData;
const crypto_1 = __importDefault(require("crypto"));
const crypto_2 = require("./crypto");
function normalizeInitData(raw) {
    let s = (raw ?? "").trim();
    if (!s)
        return s;
    // Some libs pass full query/hash like "?tgWebAppData=...&tgWebAppVersion=..."
    if (s.startsWith("?") || s.startsWith("#"))
        s = s.slice(1);
    // If it looks like launch params, extract tgWebAppData.
    if (s.includes("tgWebAppData=")) {
        const outer = new URLSearchParams(s);
        const tgWebAppData = outer.get("tgWebAppData");
        if (tgWebAppData) {
            // URLSearchParams.get decodes once, resulting in a standard initData string.
            s = tgWebAppData;
        }
    }
    return s.trim();
}
/**
 * Verify Telegram Login Widget payload.
 *
 * Returns normalized telegram user info on success.
 */
function verifyTelegramWidgetData(authData, botToken) {
    const token = (botToken ?? "").trim();
    if (!token)
        throw new Error("TG_WIDGET_BOT_TOKEN missing");
    const { hash, ...data } = authData;
    if (!hash || typeof hash !== "string")
        throw new Error("widget hash missing");
    const sortedKeys = Object.keys(data).sort();
    const dataCheckString = sortedKeys
        .map((key) => `${key}=${data[key]}`)
        .join("\n");
    const secretKey = crypto_1.default.createHash("sha256").update(token).digest();
    const computedHash = crypto_1.default
        .createHmac("sha256", secretKey)
        .update(dataCheckString)
        .digest("hex");
    if (!(0, crypto_2.safeEqual)(computedHash, hash)) {
        throw new Error("widget hash mismatch");
    }
    const telegram_id = String(authData.id ?? authData.user_id ?? "");
    if (!telegram_id)
        throw new Error("widget id missing");
    const auth_date = Number(authData.auth_date ?? 0);
    return {
        telegram_id,
        telegram_username: authData.username ?? null,
        first_name: authData.first_name ?? null,
        last_name: authData.last_name ?? null,
        photo_url: authData.photo_url ?? null,
        auth_date,
        hash,
        raw: authData,
    };
}
/**
 * Verify Telegram WebApp initData.
 *
 * Algorithm per Telegram docs:
 *  1) Build data_check_string from all pairs except "hash" (sorted by key)
 *  2) secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
 *  3) hash = HMAC_SHA256(key=secret_key, msg=data_check_string)
 */
function verifyTelegramInitData(initDataRaw, botToken) {
    const token = (botToken ?? "").trim();
    if (!token)
        throw new Error("TG_BOT_TOKEN missing");
    const initData = normalizeInitData(initDataRaw);
    if (!initData)
        throw new Error("initData missing");
    const params = new URLSearchParams(initData);
    const hash = params.get("hash");
    if (!hash)
        throw new Error("initData hash missing");
    const pairs = [];
    params.forEach((value, key) => {
        if (key === "hash")
            return;
        pairs.push([key, value]);
    });
    pairs.sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    const dataCheckString = pairs.map(([k, v]) => `${k}=${v}`).join("\n");
    const secretKey = crypto_1.default
        .createHmac("sha256", "WebAppData")
        .update(token)
        .digest();
    const computedHash = crypto_1.default
        .createHmac("sha256", secretKey)
        .update(dataCheckString)
        .digest("hex");
    if (!(0, crypto_2.safeEqual)(computedHash, hash)) {
        throw new Error("initData hash mismatch");
    }
    const userRaw = params.get("user");
    if (!userRaw)
        throw new Error("initData user missing");
    let user;
    try {
        user = JSON.parse(userRaw);
    }
    catch {
        throw new Error("initData user JSON invalid");
    }
    const auth_date = Number(params.get("auth_date") ?? 0);
    return {
        telegram_id: String(user.id),
        telegram_username: user.username ?? null,
        first_name: user.first_name ?? null,
        last_name: user.last_name ?? null,
        photo_url: user.photo_url ?? null,
        auth_date,
        query_id: params.get("query_id") ?? null,
        hash,
        raw: initData,
    };
}
// Compatibility alias
exports.verifyTelegramWidgetAuth = verifyTelegramWidgetData;
