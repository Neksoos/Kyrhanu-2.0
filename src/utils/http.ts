import type { FastifyInstance, FastifyReply } from "fastify";

/**
 * Small helper utilities for HTTP responses.
 *
 * NOTE: Some earlier versions of this project referenced this module from routes.
 * It is intentionally kept lightweight so older imports keep compiling.
 */

export type ApiErrorBody = {
  ok: false;
  code: string;
  message: string;
  details?: unknown;
};

export type ApiOkBody<T = unknown> = {
  ok: true;
  data: T;
};

export function ok<T>(reply: FastifyReply, data: T, statusCode = 200) {
  return reply.code(statusCode).send({ ok: true, data } satisfies ApiOkBody<T>);
}

export function fail(
  reply: FastifyReply,
  statusCode: number,
  code: string,
  message: string,
  details?: unknown,
) {
  const body: ApiErrorBody = {
    ok: false,
    code,
    message,
    ...(details !== undefined ? { details } : {}),
  };
  return reply.code(statusCode).send(body);
}

export const badRequest = (
  reply: FastifyReply,
  code: string,
  message: string,
  details?: unknown,
) => fail(reply, 400, code, message, details);

export const unauthorized = (
  reply: FastifyReply,
  code: string,
  message: string,
  details?: unknown,
) => fail(reply, 401, code, message, details);

export const forbidden = (
  reply: FastifyReply,
  code: string,
  message: string,
  details?: unknown,
) => fail(reply, 403, code, message, details);

export const notFound = (
  reply: FastifyReply,
  code: string,
  message: string,
  details?: unknown,
) => fail(reply, 404, code, message, details);

export const internal = (
  reply: FastifyReply,
  code: string,
  message: string,
  details?: unknown,
) => fail(reply, 500, code, message, details);

/**
 * Remove sensitive fields from a DB user object before sending it to the client.
 * (password_hash must never be exposed.)
 */
export function sanitizeUser<T extends Record<string, any>>(user: T) {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { password_hash, ...safe } = user as any;
  return safe as Omit<T, "password_hash">;
}

/**
 * Set refresh token cookie.
 *
 * We use SameSite=None because frontend and backend are usually on different
 * Railway domains.
 */
export function setRefreshCookie(
  app: FastifyInstance,
  reply: FastifyReply,
  token: string,
) {
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
export default {
  ok,
  fail,
  badRequest,
  unauthorized,
  forbidden,
  notFound,
  internal,
  sanitizeUser,
  setRefreshCookie,
};
