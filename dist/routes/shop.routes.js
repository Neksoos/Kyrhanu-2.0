"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.shopRoutes = shopRoutes;
const zod_1 = require("zod");
const db_1 = require("../db");
async function shopRoutes(app) {
    app.get("/shop/offers", async () => {
        const offers = await db_1.pool.query(`select * from shop_offers
       where active=true and starts_at <= now() and ends_at > now()
       order by created_at desc`).then((r) => r.rows);
        return { offers };
    });
    // 준비: Telegram Stars / Payments
    app.post("/shop/purchase", async (req, reply) => {
        const au = await app.requireAuth(req);
        const body = zod_1.z.object({ offer_id: zod_1.z.string().uuid(), provider: zod_1.z.enum(["telegram_stars", "test"]) }).parse(req.body);
        const offer = await db_1.pool.query(`select * from shop_offers where id=$1 and active=true`, [body.offer_id]).then((r) => r.rows[0]);
        if (!offer)
            return reply.code(404).send({ error: "OFFER_NOT_FOUND" });
        const purchase = await db_1.pool.query(`insert into purchases (id, user_id, offer_id, provider, provider_payload, status, created_at)
       values (gen_random_uuid(), $1, $2, $3, $4::jsonb, 'pending', now())
       returning *`, [au.id, offer.id, body.provider, JSON.stringify({ note: "integrate telegram stars invoice here" })]).then((r) => r.rows[0]);
        return reply.send({
            purchase,
            payment: {
                provider: body.provider,
                // тут буде payload для invoice / Stars
                hint: "TODO: create invoice + handle webhook/confirmation"
            }
        });
    });
}
