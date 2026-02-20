CREATE TABLE IF NOT EXISTS player_premium_owned (
  tg_id bigint NOT NULL,
  sku text NOT NULL,
  kind text NOT NULL CHECK (kind IN ('frame','name','avatar')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tg_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_player_premium_owned_tg
  ON player_premium_owned (tg_id);

-- Якщо таблиця вже існувала раніше:
ALTER TABLE player_premium_owned
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE player_premium_owned
  DROP CONSTRAINT IF EXISTS player_premium_owned_kind_check;

ALTER TABLE player_premium_owned
  ADD CONSTRAINT player_premium_owned_kind_check
  CHECK (kind IN ('frame','name','avatar'));

ALTER TABLE players
  ADD COLUMN IF NOT EXISTS equipped_avatar_sku text;