import { pool } from "../db";
import crypto from "node:crypto";

export type DbUserRow = {
  id: string;
  email: string | null;
  password_hash: string | null;
  telegram_id: string | null;
  telegram_username: string | null;
  display_name: string;
  last_login: string | null;
  created_at: string;
};

function sha256Hex(input: string): string {
  return crypto.createHash("sha256").update(input).digest("hex");
}

const USER_SELECT =
  "id, email, password_hash, telegram_id, telegram_username, display_name, last_login, created_at";

export async function findById(userId: string): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select ${USER_SELECT} from users where id=$1 limit 1`,
    [userId]
  );
  return q.rows[0] ?? null;
}

export async function findByEmail(email: string): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select ${USER_SELECT} from users where email=$1 limit 1`,
    [email]
  );
  return q.rows[0] ?? null;
}

export async function findByTelegramId(
  telegramId: string
): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select ${USER_SELECT} from users where telegram_id=$1 limit 1`,
    [telegramId]
  );
  return q.rows[0] ?? null;
}

export async function createWithEmail(
  email: string,
  passwordHash: string
): Promise<DbUserRow> {
  const q = await pool.query<DbUserRow>(
    `insert into users (email, password_hash, last_login)
     values ($1, $2, now())
     returning ${USER_SELECT}`,
    [email, passwordHash]
  );
  return q.rows[0];
}

export async function createWithTelegram(
  telegramId: string,
  telegramUsername: string | null = null,
  displayName: string | null = null
): Promise<DbUserRow> {
  const q = await pool.query<DbUserRow>(
    `insert into users (telegram_id, telegram_username, display_name, last_login)
     values ($1, $2, coalesce($3, 'Player'), now())
     returning ${USER_SELECT}`,
    [telegramId, telegramUsername, displayName]
  );
  return q.rows[0];
}

export async function updateLastLogin(userId: string): Promise<void> {
  await pool.query(`update users set last_login = now() where id=$1`, [userId]);
}

export async function createUserFromEmail(email: string, passwordHash: string) {
  return createWithEmail(email, passwordHash);
}

export async function createUserFromTelegram(tg: {
  id: number;
  username?: string | null;
  first_name?: string | null;
  last_name?: string | null;
}): Promise<DbUserRow> {
  const displayName =
    [tg.first_name, tg.last_name].filter(Boolean).join(" ") || "Player";
  return createWithTelegram(String(tg.id), tg.username ?? null, displayName);
}

// ✅ alias
export const createFromTelegram = createUserFromTelegram;

export async function createInitialPlayerData(userId: string) {
  // тут якщо у вас є seed/ініт таблиць - залишаємо як є
  return;
}

export async function findByRefreshToken(
  refreshToken: string
): Promise<DbUserRow | null> {
  const refreshHash = sha256Hex(refreshToken);
  const q = await pool.query<DbUserRow>(
    `
    select u.${USER_SELECT}
    from auth_sessions s
    join users u on u.id = s.user_id
    where s.refresh_token_hash = $1
      and s.revoked_at is null
      and s.expires_at > now()
    order by s.created_at desc
    limit 1
    `,
    [refreshHash]
  );
  return q.rows[0] ?? null;
}

export async function invalidateRefreshToken(refreshToken: string): Promise<void> {
  const refreshHash = sha256Hex(refreshToken);
  await pool.query(
    `
    update auth_sessions
    set revoked_at = coalesce(revoked_at, now())
    where refresh_token_hash = $1
    `,
    [refreshHash]
  );
}

export const userService = {
  findById,
  findByEmail,
  findByTelegramId,

  createWithEmail,
  createWithTelegram,

  createUserFromEmail,
  createUserFromTelegram,
  createFromTelegram,

  updateLastLogin,
  createInitialPlayerData,

  findByRefreshToken,
  invalidateRefreshToken
};