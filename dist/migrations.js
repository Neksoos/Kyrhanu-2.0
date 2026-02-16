"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.runMigrations = runMigrations;
const fs_1 = __importDefault(require("fs"));
const path_1 = __importDefault(require("path"));
const db_1 = require("./db");
/**
 * Runs SQL files from /sql in lexicographic order (e.g. 001_*.sql, 002_*.sql ...).
 *
 * Notes:
 * - Migrations in this project are written to be idempotent (IF NOT EXISTS / ON CONFLICT).
 * - We take a Postgres advisory lock to avoid concurrent migration runs.
 */
async function runMigrations() {
    const sqlDir = path_1.default.join(process.cwd(), 'sql');
    if (!fs_1.default.existsSync(sqlDir)) {
        // In some runtimes process.cwd() can differ; fail loudly so it is obvious.
        throw new Error(`SQL migrations folder not found: ${sqlDir}`);
    }
    const files = fs_1.default
        .readdirSync(sqlDir)
        .filter((f) => /\.sql$/i.test(f))
        .sort((a, b) => a.localeCompare(b, 'en'));
    const client = await db_1.pool.connect();
    const applied = [];
    try {
        // 64-bit advisory lock key (arbitrary constant but stable)
        await client.query('SELECT pg_advisory_lock($1)', [913_002_001]);
        for (const file of files) {
            const fullPath = path_1.default.join(sqlDir, file);
            const sql = fs_1.default.readFileSync(fullPath, 'utf8');
            if (!sql.trim())
                continue;
            await client.query(sql);
            applied.push(file);
        }
    }
    finally {
        try {
            await client.query('SELECT pg_advisory_unlock($1)', [913_002_001]);
        }
        catch {
            // ignore
        }
        client.release();
    }
    return { applied };
}
