-- ✅ 1) Поле в players для екіпнутого аватара
ALTER TABLE players
  ADD COLUMN IF NOT EXISTS equipped_avatar_sku TEXT;

-- ✅ 2) Таблиця володіння преміумом (тепер kind: frame | name | avatar)
CREATE TABLE IF NOT EXISTS player_premium_owned (
  tg_id bigint NOT NULL,
  sku text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('frame','name','avatar')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tg_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_player_premium_owned_tg
  ON player_premium_owned (tg_id);

-- ✅ 3) Якщо таблиця вже існує зі старим CHECK (тільки frame/name) — онови constraint:
ALTER TABLE player_premium_owned
  DROP CONSTRAINT IF EXISTS player_premium_owned_kind_check;

ALTER TABLE player_premium_owned
  ADD CONSTRAINT player_premium_owned_kind_check
  CHECK (kind IN ('frame','name','avatar'));