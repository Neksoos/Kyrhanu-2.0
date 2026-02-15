import { Pool } from "pg";
import { env } from "./env";

/**
 * Postgres connection pool.
 *
 * IMPORTANT: use named exports from `pg` so TypeScript keeps proper types.
 * This prevents `any` leakage which was breaking strict builds.
 */
export const pool = new Pool({
  connectionString: env.DATABASE_URL,
  max: 10
});

export async function healthcheckDb(): Promise<boolean> {
  const res = await pool.query<{ ok: number }>("select 1 as ok");
  return res.rows?.[0]?.ok === 1;
}