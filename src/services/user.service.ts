import { pool } from "../db";

/**
 * User service extracted for reuse.
 *
 * NOTE: Some earlier versions of the project imported this module.
 * The current routes may query the DB directly, but keeping this file
 * helps TypeScript builds when older imports exist.
 */

export type DbUserRow = {
  id: number;
  email: string | null;
  password_hash: string | null;
  telegram_id: string | null;
  created_at: Date;
  updated_at: Date;
};

export async function findByEmail(email: string): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select id, email, password_hash, telegram_id, created_at, updated_at
     from users
     where lower(email) = lower($1)
     limit 1`,
    [email],
  );
  return q.rows[0] ?? null;
}

export async function findByTelegramId(telegramId: string): Promise<DbUserRow | null> {
  const q = await pool.query<DbUserRow>(
    `select id, email, password_hash, telegram_id, created_at, updated_at
     from users
     where telegram_id = $1
     limit 1`,
    [telegramId],
  );
  return q.rows[0] ?? null;
}

export async function createWithEmail(email: string, passwordHash: string): Promise<DbUserRow> {
  const q = await pool.query<DbUserRow>(
    `insert into users (email, password_hash)
     values ($1, $2)
     returning id, email, password_hash, telegram_id, created_at, updated_at`,
    [email, passwordHash],
  );
  return q.rows[0];
}

export async function createWithTelegram(telegramId: string): Promise<DbUserRow> {
  const q = await pool.query<DbUserRow>(
    `insert into users (telegram_id)
     values ($1)
     returning id, email, password_hash, telegram_id, created_at, updated_at`,
    [telegramId],
  );
  return q.rows[0];
}

export async function linkTelegramId(userId: number, telegramId: string): Promise<void> {
  await pool.query(`update users set telegram_id = $1, updated_at = now() where id = $2`, [telegramId, userId]);
}

// Backwards-friendly service object
export const userService = {
  findByEmail,
  findByTelegramId,
  createWithEmail,
  createWithTelegram,
  linkTelegramId,
};

export default userService;