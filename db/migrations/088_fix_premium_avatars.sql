-- Додаємо поле для екіпованого аватара у таблицю players
ALTER TABLE players
  ADD COLUMN IF NOT EXISTS equipped_avatar_sku TEXT;

-- Таблиця володіння преміум-предметами.
-- kind тепер приймає 'frame','name','avatar'
CREATE TABLE IF NOT EXISTS player_premium_owned (
  tg_id       BIGINT NOT NULL,
  sku         TEXT   NOT NULL,
  kind        TEXT   NOT NULL CHECK (kind IN ('frame','name','avatar')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tg_id, sku)
);

CREATE INDEX IF NOT EXISTS idx_player_premium_owned_tg
  ON player_premium_owned (tg_id);

-- Якщо таблиця вже існує зі старим constraint,
-- слід видалити старий CHECK та додати новий:
ALTER TABLE player_premium_owned
  DROP CONSTRAINT IF EXISTS player_premium_owned_kind_check;
ALTER TABLE player_premium_owned
  ADD  CONSTRAINT player_premium_owned_kind_check
  CHECK (kind IN ('frame','name','avatar'));