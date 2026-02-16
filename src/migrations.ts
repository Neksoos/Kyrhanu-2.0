import fs from 'fs';
import path from 'path';

import { pool } from './db';

/**
 * Runs SQL files from /sql in lexicographic order (e.g. 001_*.sql, 002_*.sql ...).
 *
 * Notes:
 * - Migrations in this project are written to be idempotent (IF NOT EXISTS / ON CONFLICT).
 * - We take a Postgres advisory lock to avoid concurrent migration runs.
 */
export async function runMigrations(): Promise<{ applied: string[] }> {
  const sqlDir = path.join(process.cwd(), 'sql');
  if (!fs.existsSync(sqlDir)) {
    // In some runtimes process.cwd() can differ; fail loudly so it is obvious.
    throw new Error(`SQL migrations folder not found: ${sqlDir}`);
  }

  const files = fs
    .readdirSync(sqlDir)
    .filter((f) => /\.sql$/i.test(f))
    .sort((a, b) => a.localeCompare(b, 'en'));

  const client = await pool.connect();
  const applied: string[] = [];

  try {
    // 64-bit advisory lock key (arbitrary constant but stable)
    await client.query('SELECT pg_advisory_lock($1)', [913_002_001]);

    for (const file of files) {
      const fullPath = path.join(sqlDir, file);
      const sql = fs.readFileSync(fullPath, 'utf8');
      if (!sql.trim()) continue;

      await client.query(sql);
      applied.push(file);
    }
  } finally {
    try {
      await client.query('SELECT pg_advisory_unlock($1)', [913_002_001]);
    } catch {
      // ignore
    }
    client.release();
  }

  return { applied };
}
