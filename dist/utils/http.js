"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.internal = exports.notFound = exports.forbidden = exports.unauthorized = exports.badRequest = void 0;
exports.ok = ok;
exports.fail = fail;
exports.sanitizeUser = sanitizeUser;
exports.setRefreshCookie = setRefreshCookie;
function ok(reply, data, statusCode = 200) {
    return reply.code(statusCode).send({ ok: true, data });
}
function fail(reply, statusCode, code, message, details) {
    const body = {
        ok: false,
        code,
        message,
        ...(details !== undefined ? { details } : {}),
    };
    return reply.code(statusCode).send(body);
}
const badRequest = (reply, code, message, details) => fail(reply, 400, code, message, details);
exports.badRequest = badRequest;
const unauthorized = (reply, code, message, details) => fail(reply, 401, code, message, details);
exports.unauthorized = unauthorized;
const forbidden = (reply, code, message, details) => fail(reply, 403, code, message, details);
exports.forbidden = forbidden;
const notFound = (reply, code, message, details) => fail(reply, 404, code, message, details);
exports.notFound = notFound;
const internal = (reply, code, message, details) => fail(reply, 500, code, message, details);
exports.internal = internal;
/**
 * Remove sensitive fields from a DB user object before sending it to the client.
 * (password_hash must never be exposed.)
 */
function sanitizeUser(user) {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { password_hash, ...safe } = user;
    return safe;
}
/**
 * Set refresh token cookie.
 *
 * We use SameSite=None because frontend and backend are usually on different
 * Railway domains.
 */
function setRefreshCookie(app, reply, token) {
    const isProd = (app.config?.NODE_ENV ?? process.env.NODE_ENV) === "production";
    reply.setCookie("refresh_token", token, {
        path: "/",
        httpOnly: true,
        secure: isProd,
        sameSite: "none",
        // ~30 days (should match backend refresh expiry)
        maxAge: 60 * 60 * 24 * 30,
    });
}
// Backwards-friendly default export
exports.default = {
    ok,
    fail,
    badRequest: exports.badRequest,
    unauthorized: exports.unauthorized,
    forbidden: exports.forbidden,
    notFound: exports.notFound,
    internal: exports.internal,
    sanitizeUser,
    setRefreshCookie,
};
