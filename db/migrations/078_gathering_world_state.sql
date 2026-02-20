-- 068_gathering_world_state.sql
-- Асинхронна конкуренція gathering без PvP:
-- - локальний стан "спота" (місця збору)
-- - глобальний пул ресурсу на день
-- - анонімні "сліди" останніх дій

-- 1) Споти (унікальні по area + source)
CREATE TABLE IF NOT EXISTS gathering_spots (
  id          SERIAL PRIMARY KEY,
  area_key    TEXT NOT NULL,
  source_type TEXT NOT NULL, -- herb|ore|ks
  UNIQUE(area_key, source_type)
);

-- (опційно, але корисно для явного прискорення пошуку)
-- Postgres зазвичай вже створює індекс під UNIQUE, але хай буде ок.
CREATE INDEX IF NOT EXISTS idx_gathering_spots_area_source
  ON gathering_spots(area_key, source_type);

-- 2) Стан спота
CREATE TABLE IF NOT EXISTS gathering_spot_state (
  spot_id      INTEGER PRIMARY KEY REFERENCES gathering_spots(id) ON DELETE CASCADE,
  local_stock  INTEGER NOT NULL DEFAULT 100, -- 0..100
  quality_bias INTEGER NOT NULL DEFAULT 0,   -- -2..+2
  danger_level INTEGER NOT NULL DEFAULT 0,   -- 0..5
  spirit_state TEXT    NOT NULL DEFAULT 'calm', -- calm|restless|hostile
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Захист від некоректних значень (щоб не ловити "тихі" баги)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_gathering_spot_state_local_stock'
  ) THEN
    ALTER TABLE gathering_spot_state
      ADD CONSTRAINT chk_gathering_spot_state_local_stock
      CHECK (local_stock BETWEEN 0 AND 100);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_gathering_spot_state_quality_bias'
  ) THEN
    ALTER TABLE gathering_spot_state
      ADD CONSTRAINT chk_gathering_spot_state_quality_bias
      CHECK (quality_bias BETWEEN -2 AND 2);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_gathering_spot_state_danger_level'
  ) THEN
    ALTER TABLE gathering_spot_state
      ADD CONSTRAINT chk_gathering_spot_state_danger_level
      CHECK (danger_level BETWEEN 0 AND 5);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_gathering_spot_state_spirit_state'
  ) THEN
    ALTER TABLE gathering_spot_state
      ADD CONSTRAINT chk_gathering_spot_state_spirit_state
      CHECK (spirit_state IN ('calm', 'restless', 'hostile'));
  END IF;
END
$$;

-- 3) Анонімні сліди (короткий лог)
CREATE TABLE IF NOT EXISTS gathering_spot_log (
  id         BIGSERIAL PRIMARY KEY,
  spot_id    INTEGER NOT NULL REFERENCES gathering_spots(id) ON DELETE CASCADE,
  action     TEXT NOT NULL,  -- start|complete|escape|...
  impact     TEXT NOT NULL,  -- deplete|stabilize|corrupt|...
  intensity  INTEGER NOT NULL DEFAULT 1, -- 1..3
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Захист для intensity
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_gathering_spot_log_intensity'
  ) THEN
    ALTER TABLE gathering_spot_log
      ADD CONSTRAINT chk_gathering_spot_log_intensity
      CHECK (intensity BETWEEN 1 AND 3);
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_gather_log_spot_time
  ON gathering_spot_log(spot_id, created_at DESC);

-- 4) Глобальний пул на день (по source_type)
CREATE TABLE IF NOT EXISTS gathering_global_pool (
  day          DATE NOT NULL,
  source_type  TEXT NOT NULL, -- herb|ore|ks
  global_stock INTEGER NOT NULL DEFAULT 100, -- 0..100
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY(day, source_type)
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_gathering_global_pool_global_stock'
  ) THEN
    ALTER TABLE gathering_global_pool
      ADD CONSTRAINT chk_gathering_global_pool_global_stock
      CHECK (global_stock BETWEEN 0 AND 100);
  END IF;
END
$$;