import pg from "pg";
import { env } from "./env";

export const pool = new pg.Pool({
  connectionString: env.DATABASE_URL,
  max: 10
});

export async function healthcheckDb(): Promise<boolean> {
  const res = await pool.query("select 1 as ok");
  return res.rows?.[0]?.ok === 1;
}