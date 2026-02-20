-- Додаємо поле для екіпованого аватара в players
ALTER TABLE players
  ADD COLUMN IF NOT EXISTS equipped_avatar_sku TEXT;

-- Створюємо таблицю, якщо її ще немає
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

-- Оновлюємо constraint, якщо в таблиці вже є старий варіант
ALTER TABLE player_premium_owned
  DROP CONSTRAINT IF EXISTS player_premium_owned_kind_check;
ALTER TABLE player_premium_owned
  ADD  CONSTRAINT player_premium_owned_kind_check
  CHECK (kind IN ('frame','name','avatar'));