"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.sha256Hex = sha256Hex;
exports.hmacSha256 = hmacSha256;
exports.hmacSha256Hex = hmacSha256Hex;
exports.safeEqual = safeEqual;
exports.randomId = randomId;
const crypto_1 = __importDefault(require("crypto"));
function sha256Hex(input) {
    return crypto_1.default.createHash("sha256").update(input).digest("hex");
}
/**
 * HMAC-SHA256 returning raw bytes (Buffer).
 * `key` can be a Buffer or string; `data` can be Buffer or string.
 */
function hmacSha256(key, data) {
    return crypto_1.default.createHmac("sha256", key).update(data).digest();
}
function hmacSha256Hex(key, data) {
    return hmacSha256(key, data).toString("hex");
}
function safeEqual(a, b) {
    const ab = Buffer.from(a);
    const bb = Buffer.from(b);
    if (ab.length !== bb.length)
        return false;
    return crypto_1.default.timingSafeEqual(ab, bb);
}
function randomId(prefix = "") {
    return prefix + crypto_1.default.randomBytes(16).toString("hex");
}
