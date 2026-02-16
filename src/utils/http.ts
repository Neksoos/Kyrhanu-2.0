import type { FastifyInstance, FastifyReply } from "fastify";

/**
 * Refresh cookie helper.
 * IMPORTANT: For cross-domain фронт/бек в production потрібні:
 *   SameSite=None + Secure=true
 * А в dev "none" без HTTPS ламається в браузерах, тому ставимо "lax".
 */
export function setRefreshCookie(
  app: FastifyInstance,
  reply: FastifyReply,
  token: string,
) {
  // We don't rely on a custom `app.config` decorator.
  // Railway/Node environments expose NODE_ENV via process.env.
  const isProd = (process.env.NODE_ENV ?? "production") === "production";

  reply.setCookie("refresh_token", token, {
    path: "/",
    httpOnly: true,
    secure: isProd,
    // In production we need cross-site cookies (frontend and backend are on different domains)
    // so SameSite must be "none" and `secure` must be true.
    // In local/dev environments, "none" without HTTPS breaks in most browsers.
    sameSite: isProd ? "none" : "lax",
    // ~30 days (should match backend refresh expiry)
    maxAge: 60 * 60 * 24 * 30,
  });
}

export function clearRefreshCookie(reply: FastifyReply) {
  reply.clearCookie("refresh_token", { path: "/" });
}