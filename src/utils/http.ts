import type { FastifyReply } from "fastify";

export function setRefreshCookie(reply: FastifyReply, token: string) {
  reply.setCookie("refresh_token", token, {
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
}

export function clearRefreshCookie(reply: FastifyReply) {
  reply.clearCookie("refresh_token", { path: "/" });
}

/**
 * Strip sensitive fields before returning a user object to the client.
 */
export function sanitizeUser<T extends Record<string, any>>(user: T): Omit<T, "password_hash"> {
  const { password_hash, ...safe } = user as any;
  return safe;
}