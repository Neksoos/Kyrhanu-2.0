import crypto from "crypto";

export function sha256Hex(input: string | Buffer): string {
  return crypto.createHash("sha256").update(input).digest("hex");
}

/**
 * HMAC-SHA256 returning raw bytes (Buffer).
 * `key` can be a Buffer or string; `data` can be Buffer or string.
 */
export function hmacSha256(key: Buffer | string, data: Buffer | string): Buffer {
  return crypto.createHmac("sha256", key).update(data).digest();
}

export function hmacSha256Hex(key: Buffer | string, data: Buffer | string): string {
  return hmacSha256(key, data).toString("hex");
}

export function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return crypto.timingSafeEqual(ab, bb);
}

export function randomId(prefix = ""): string {
  return prefix + crypto.randomBytes(16).toString("hex");
}