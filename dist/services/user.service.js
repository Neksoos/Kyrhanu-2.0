"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.userService = void 0;
exports.findByEmail = findByEmail;
exports.findByTelegramId = findByTelegramId;
exports.findById = findById;
exports.createWithEmail = createWithEmail;
exports.createWithTelegram = createWithTelegram;
exports.linkTelegramIdToUser = linkTelegramIdToUser;
exports.updateUserLastLogin = updateUserLastLogin;
exports.ensureInitialPlayerData = ensureInitialPlayerData;
exports.createUserFromEmail = createUserFromEmail;
exports.createUserFromTelegram = createUserFromTelegram;
exports.findUserByTelegramId = findUserByTelegramId;
exports.linkTelegramToUser = linkTelegramToUser;
exports.updateLastLogin = updateLastLogin;
exports.createInitialPlayerData = createInitialPlayerData;
const db_1 = require("../db");
const USER_SELECT = `
  id,
  email,
  password_hash,
  telegram_id,
  telegram_username,
  last_login,
  created_at,
  updated_at
`;
async function findByEmail(email) {
    const q = await db_1.pool.query(`select ${USER_SELECT}
     from users
     where email is not null and lower(email) = lower($1)
     limit 1`, [email]);
    return q.rows[0] ?? null;
}
async function findByTelegramId(telegramId) {
    const q = await db_1.pool.query(`select ${USER_SELECT}
     from users
     where telegram_id = $1
     limit 1`, [telegramId]);
    return q.rows[0] ?? null;
}
async function findById(userId) {
    const q = await db_1.pool.query(`select ${USER_SELECT}
     from users
     where id = $1
     limit 1`, [userId]);
    return q.rows[0] ?? null;
}
async function createWithEmail(email, passwordHash) {
    const q = await db_1.pool.query(`insert into users (email, password_hash, last_login)
     values ($1, $2, now())
     returning ${USER_SELECT}`, [email, passwordHash]);
    return q.rows[0];
}
async function createWithTelegram(telegramId, telegramUsername = null) {
    const q = await db_1.pool.query(`insert into users (telegram_id, telegram_username, last_login)
     values ($1, $2, now())
     returning ${USER_SELECT}`, [telegramId, telegramUsername]);
    return q.rows[0];
}
async function linkTelegramIdToUser(userId, telegramId, telegramUsername = null) {
    await db_1.pool.query(`update users
     set telegram_id = $1,
         telegram_username = coalesce($2, telegram_username),
         updated_at = now()
     where id = $3`, [telegramId, telegramUsername, userId]);
}
async function updateUserLastLogin(userId) {
    await db_1.pool.query(`update users set last_login = now(), updated_at = now() where id = $1`, [userId]);
}
/**
 * Create/ensure baseline rows for a new player.
 *
 * Current gameplay routes already "ensure" these on /me, so this is defensive.
 */
async function ensureInitialPlayerData(userId) {
    await db_1.pool.query(`insert into inventories (user_id)
     values ($1)
     on conflict (user_id) do nothing`, [userId]);
}
// ---------------------------------------------------------------------------
// Compatibility exports used by auth.routes.ts
// ---------------------------------------------------------------------------
async function createUserFromEmail(email, passwordHash) {
    return createWithEmail(email, passwordHash);
}
async function createUserFromTelegram(tg) {
    const telegramId = String(tg.telegram_id ?? tg.id ?? "");
    const telegramUsername = (tg.telegram_username ?? tg.username ?? null) === "" ? null : (tg.telegram_username ?? tg.username ?? null);
    if (!telegramId) {
        throw new Error("telegram_id is required");
    }
    return createWithTelegram(telegramId, telegramUsername);
}
async function findUserByTelegramId(telegramId) {
    return findByTelegramId(telegramId);
}
async function linkTelegramToUser(userId, telegramId, telegramUsername = null) {
    return linkTelegramIdToUser(userId, telegramId, telegramUsername);
}
async function updateLastLogin(userId) {
    return updateUserLastLogin(userId);
}
async function createInitialPlayerData(userId) {
    return ensureInitialPlayerData(userId);
}
// Backwards-friendly service object (some legacy code imports default)
exports.userService = {
    findByEmail,
    findByTelegramId,
    findById,
    createWithEmail,
    createWithTelegram,
    linkTelegramIdToUser,
    updateUserLastLogin,
    ensureInitialPlayerData,
    // compat
    createUserFromEmail,
    createUserFromTelegram,
    findUserByTelegramId,
    linkTelegramToUser,
    updateLastLogin,
    createInitialPlayerData,
};
exports.default = exports.userService;
