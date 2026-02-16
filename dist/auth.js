"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.authPlugin = void 0;
const fastify_plugin_1 = __importDefault(require("fastify-plugin"));
const jwt_1 = __importDefault(require("@fastify/jwt"));
const bcryptjs_1 = __importDefault(require("bcryptjs"));
const env_1 = require("./env");
const crypto_1 = require("./utils/crypto");
const db_1 = require("./db");
exports.authPlugin = (0, fastify_plugin_1.default)(async (app) => {
    app.register(jwt_1.default, { secret: env_1.env.JWT_SECRET });
    app.decorate("authUser", async function authUser(req) {
        const hdr = req.headers.authorization;
        if (!hdr?.startsWith("Bearer "))
            return null;
        const token = hdr.slice("Bearer ".length);
        try {
            const decoded = app.jwt.verify(token);
            return { id: decoded.sub };
        }
        catch {
            return null;
        }
    });
    app.decorate("requireAuth", async function requireAuth(req) {
        const u = await app.authUser(req);
        if (!u) {
            // `@fastify/sensible` adds httpErrors at runtime, but its typing can be finicky.
            // Use a safe runtime fallback so strict TS builds don't fail.
            const httpErrors = app.httpErrors;
            if (httpErrors?.unauthorized)
                throw httpErrors.unauthorized("Unauthorized");
            const err = new Error("Unauthorized");
            err.statusCode = 401;
            throw err;
        }
        return u;
    });
    app.decorate("hashPassword", async (password) => bcryptjs_1.default.hash(password, 10));
    app.decorate("verifyPassword", async (password, hash) => bcryptjs_1.default.compare(password, hash));
    app.decorate("issueTokens", async function issueTokens(userId) {
        const access = app.jwt.sign({ sub: userId }, { expiresIn: "15m" });
        const refreshPlain = `${userId}.${Date.now()}.${Math.random()}`;
        const refreshHash = (0, crypto_1.sha256Hex)(refreshPlain);
        const expiresAt = new Date(Date.now() + 1000 * 60 * 60 * 24 * 30); // 30d
        await db_1.pool.query(`insert into auth_sessions (id, user_id, refresh_token_hash, user_agent, ip, created_at, expires_at)
       values (gen_random_uuid(), $1, $2, $3, $4, now(), $5)`, [userId, refreshHash, "", reqIpSafe(), expiresAt]);
        return { accessToken: access, refreshToken: refreshPlain, refreshExpiresAt: expiresAt.toISOString() };
    });
    function reqIpSafe() {
        return "0.0.0.0";
    }
});
