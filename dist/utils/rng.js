"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mulberry32 = mulberry32;
exports.randInt = randInt;
exports.pick = pick;
// Deterministic RNG (Mulberry32)
function mulberry32(seed) {
    let t = seed >>> 0;
    return function () {
        t += 0x6D2B79F5;
        let x = Math.imul(t ^ (t >>> 15), 1 | t);
        x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
        return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
}
function randInt(r, min, max) {
    return Math.floor(r() * (max - min + 1)) + min;
}
function pick(r, arr) {
    return arr[Math.floor(r() * arr.length)];
}
