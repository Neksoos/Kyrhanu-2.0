import crypto from "crypto";

export function sha256Hex(input: string | Buffer): string {
  return crypto.createHash("sha256").update(input).digest("hex");
}

export function hmacSha256Hex(key: Buffer | string, data: string): string {
  return crypto.createHmac("sha256", key).update(data).digest("hex");
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