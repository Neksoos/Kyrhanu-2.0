BEGIN;

-- =========================================================
-- 1) Захист: усе крафтове НЕ повинно лутатись
-- =========================================================
UPDATE items
SET is_lootable = false
WHERE COALESCE(is_craftable, false) = true;

-- =========================================================
-- 2) Фікс твого сід-екіпу шоломів:
--    вони помилково записані як category='trash'
--    робимо їх equip + craftable + НЕ lootable
-- =========================================================
UPDATE items
SET
  category    = 'equip',
  is_lootable = false,
  is_craftable = true
WHERE
  code = 'smith_helmet_zaliznyi'
  OR code LIKE 'helm_t%';

-- =========================================================
-- 3) Сміття та джанк мають падати
-- =========================================================
UPDATE items
SET is_lootable = true
WHERE
  COALESCE(is_archived, false) = false
  AND category IN ('trash', 'junk');

-- =========================================================
-- 4) Екіп, який може падати:
--    - тільки некрафтовий
--    - тільки звичайний/добротний (під твій лутер)
-- =========================================================
UPDATE items
SET is_lootable = true
WHERE
  COALESCE(is_archived, false) = false
  AND category = 'equip'
  AND COALESCE(is_craftable, false) = false
  AND rarity IN ('Звичайний', 'Добротний');

-- =========================================================
-- 5) Контрольна перевірка (можеш лишити, можеш прибрати):
--    крафтове не повинно бути lootable=true
-- =========================================================
-- SELECT count(*) FROM items WHERE COALESCE(is_craftable,false)=true AND COALESCE(is_lootable,false)=true;

COMMIT;