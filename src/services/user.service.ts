import { pool } from "../db";

/**
 * User service.
 *
 * This module is used by auth routes (email/password, telegram initData, and
 * linking). Keep exported names stable to avoid TS build breaks.
 */

export type DbUserRow = {
  id: number;
  email: string | null;
  password_hash: string | null;
  telegram_id: string | null;
  telegram_username: string | null;
  last_login: Date | null;
  created_at: Date;
  updated_at: Date;
};

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

export async function findByEmail(email: string): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select ${USER_SELECT}
     from users
     where email is not null and lower(email) = lower($1)
     limit 1`,
    [email],
  );
  return q.rows[0] ?? null;
}

export async function findByTelegramId(
  telegramId: string,
): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select ${USER_SELECT}
     from users
     where telegram_id = $1
     limit 1`,
    [telegramId],
  );
  return q.rows[0] ?? null;
}

export async function findById(userId: number): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select ${USER_SELECT}
     from users
     where id = $1
     limit 1`,
    [userId],
  );
  return q.rows[0] ?? null;
}

export async function createWithEmail(
  email: string,
  passwordHash: string,
): Promise<DbUserRow> {
  const q = await pool.query<DbUserRow>(
    `insert into users (email, password_hash, last_login)
     values ($1, $2, now())
     returning ${USER_SELECT}`,
    [email, passwordHash],
  );
  return q.rows[0];
}

export async function createWithTelegram(
  telegramId: string,
  telegramUsername: string | null = null,
): Promise<DbUserRow> {
  const q = await pool.query<DbUserRow>(
    `insert into users (telegram_id, telegram_username, last_login)
     values ($1, $2, now())
     returning ${USER_SELECT}`,
    [telegramId, telegramUsername],
  );
  return q.rows[0];
}

export async function linkTelegramIdToUser(
  userId: number,
  telegramId: string,
  telegramUsername: string | null = null,
): Promise<void> {
  await pool.query(
    `update users
     set telegram_id = $1,
         telegram_username = coalesce($2, telegram_username),
         updated_at = now()
     where id = $3`,
    [telegramId, telegramUsername, userId],
  );
}

export async function updateUserLastLogin(userId: number): Promise<void> {
  await pool.query(
    `update users set last_login = now(), updated_at = now() where id = $1`,
    [userId],
  );
}

/**
 * Create/ensure baseline rows for a new player.
 *
 * Current gameplay routes already "ensure" these on /me, so this is defensive.
 */
export async function ensureInitialPlayerData(userId: number): Promise<void> {
  await pool.query(
    `insert into inventories (user_id)
     values ($1)
     on conflict (user_id) do nothing`,
    [userId],
  );
}

// ---------------------------------------------------------------------------
// Compatibility exports used by auth.routes.ts
// ---------------------------------------------------------------------------

export async function createUserFromEmail(email: string, passwordHash: string) {
  return createWithEmail(email, passwordHash);
}

export async function createUserFromTelegram(tg: {
  telegram_id?: string;
  telegram_username?: string | null;
  id?: string | number;
  username?: string | null;
}) {
  const telegramId = String(tg.telegram_id ?? tg.id ?? "");
  const telegramUsername =
    (tg.telegram_username ?? tg.username ?? null) === "" ? null : (tg.telegram_username ?? tg.username ?? null);

  if (!telegramId) {
    throw new Error("telegram_id is required");
  }
  return createWithTelegram(telegramId, telegramUsername);
}

export async function findUserByTelegramId(telegramId: string) {
  return findByTelegramId(telegramId);
}

export async function linkTelegramToUser(
  userId: number,
  telegramId: string,
  telegramUsername: string | null = null,
) {
  return linkTelegramIdToUser(userId, telegramId, telegramUsername);
}

export async function updateLastLogin(userId: number) {
  return updateUserLastLogin(userId);
}

export async function createInitialPlayerData(userId: number) {
  return ensureInitialPlayerData(userId);
}

// Backwards-friendly service object (some legacy code imports default)
export const userService = {
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

export default userService;
