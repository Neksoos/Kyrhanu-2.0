-- 087_fix_premium_owned_kind_avatar.sql

-- 1) на випадок, якщо колонок ще нема (або база стара)
ALTER TABLE player_premium_owned
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();

ALTER TABLE player_premium_owned
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();

-- 2) прибираємо старий CHECK (який дозволяє тільки frame/name)
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT c.conname
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    WHERE t.relname = 'player_premium_owned'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) ILIKE '%kind%'
  LOOP
    EXECUTE format('ALTER TABLE player_premium_owned DROP CONSTRAINT IF EXISTS %I', r.conname);
  END LOOP;
END $$;

-- 3) ставимо правильний CHECK
ALTER TABLE player_premium_owned
  ADD CONSTRAINT player_premium_owned_kind_check
  CHECK (kind IN ('frame','name','avatar'));