CREATE TABLE IF NOT EXISTS tg_stars_orders (
  id BIGSERIAL PRIMARY KEY,
  payload TEXT UNIQUE NOT NULL,
  tg_id BIGINT NOT NULL,
  sku TEXT NOT NULL,
  amount_xtr INTEGER NOT NULL,
  grant_kleynody INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'created',
  currency TEXT,
  total_amount INTEGER,
  telegram_payment_charge_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tg_stars_orders_tg_id
  ON tg_stars_orders(tg_id);