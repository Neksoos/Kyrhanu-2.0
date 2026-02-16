import type { FastifyReply } from "fastify";

/**
 * Make sure we never leak sensitive things in API responses.
 * (Used for user objects and other payloads.)
 */
export function sanitizeUser<T extends Record<string, any>>(user: T): Omit<T, "password" | "password_hash" | "refresh_hash"> {
  const copy: any = { ...user };
  delete copy.password;
  delete copy.password_hash;
  delete copy.refresh_hash;
  return copy;
}

/**
 * Sets refresh token cookie.
 * NOTE: uses env vars only (Railway-friendly).
 */
export function setRefreshCookie(reply: FastifyReply, token: string) {
  const isProd = (process.env.NODE_ENV ?? "production") === "production";

  reply.setCookie("refreshToken", token, {
    httpOnly: true,
    secure: isProd,
    sameSite: isProd ? "none" : "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30, // 30 days
  });
}