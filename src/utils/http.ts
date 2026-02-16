import type { FastifyReply } from "fastify";

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
  const body: ApiErrorBody = { ok: false, code, message, ...(details !== undefined ? { details } : {}) };
  return reply.code(statusCode).send(body);
}

export const badRequest = (reply: FastifyReply, code: string, message: string, details?: unknown) =>
  fail(reply, 400, code, message, details);

export const unauthorized = (reply: FastifyReply, code: string, message: string, details?: unknown) =>
  fail(reply, 401, code, message, details);

export const forbidden = (reply: FastifyReply, code: string, message: string, details?: unknown) =>
  fail(reply, 403, code, message, details);

export const notFound = (reply: FastifyReply, code: string, message: string, details?: unknown) =>
  fail(reply, 404, code, message, details);

export const internal = (reply: FastifyReply, code: string, message: string, details?: unknown) =>
  fail(reply, 500, code, message, details);

// Backwards-friendly default export
export default {
  ok,
  fail,
  badRequest,
  unauthorized,
  forbidden,
  notFound,
  internal,
};