"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.pool = void 0;
exports.healthcheckDb = healthcheckDb;
const pg_1 = require("pg");
const env_1 = require("./env");
/**
 * Postgres connection pool.
 *
 * IMPORTANT: use named exports from `pg` so TypeScript keeps proper types.
 * This prevents `any` leakage which was breaking strict builds.
 */
exports.pool = new pg_1.Pool({
    connectionString: env_1.env.DATABASE_URL,
    max: 10
});
async function healthcheckDb() {
    const res = await exports.pool.query("select 1 as ok");
    return res.rows?.[0]?.ok === 1;
}
