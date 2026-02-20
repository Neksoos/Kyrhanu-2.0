BEGIN;

ALTER TABLE items
  ADD COLUMN IF NOT EXISTS is_lootable  boolean,
  ADD COLUMN IF NOT EXISTS is_craftable boolean;

-- якщо колонки вже були створені раніше без NOT NULL — доб’ємо консистентність
UPDATE items SET is_lootable  = false WHERE is_lootable  IS NULL;
UPDATE items SET is_craftable = false WHERE is_craftable IS NULL;

ALTER TABLE items
  ALTER COLUMN is_lootable  SET DEFAULT false,
  ALTER COLUMN is_craftable SET DEFAULT false;

ALTER TABLE items
  ALTER COLUMN is_lootable  SET NOT NULL,
  ALTER COLUMN is_craftable SET NOT NULL;

COMMIT;