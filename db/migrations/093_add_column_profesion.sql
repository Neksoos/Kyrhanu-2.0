BEGIN;

-- 1) Гнучка ознака: для яких професій/станків цей предмет
ALTER TABLE items
ADD COLUMN IF NOT EXISTS use_professions TEXT[] NOT NULL DEFAULT '{}';

-- 2) Індекс для запитів типу: use_professions @> ARRAY['blacksmith']
CREATE INDEX IF NOT EXISTS items_use_professions_gin
ON items USING gin (use_professions);

COMMIT;
