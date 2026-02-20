
-- Premium subscriptions for "Жива вода" та "Благословення мольфара"

ALTER TABLE players
  ADD COLUMN IF NOT EXISTS premium_water_until  timestamptz,
  ADD COLUMN IF NOT EXISTS premium_molfar_until timestamptz;

-- Індекс для швидких перевірок (опціонально, але корисно)
CREATE INDEX IF NOT EXISTS idx_players_premium_water_until
  ON players (premium_water_until);

CREATE INDEX IF NOT EXISTS idx_players_premium_molfar_until
  ON players (premium_molfar_until);
