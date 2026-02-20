BEGIN;

-- на всякий випадок (якщо хтось застосовував 077 без 071)
ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS output_type text NOT NULL DEFAULT 'item';

-- 1) ФІКС ШОЛОМІВ КОВАЛЯ
-- Привʼязуємо існуючі рецепти до items

UPDATE blacksmith_recipes
SET
  slot = 'helmet',
  output_type = 'forge',
  output_item_code = 'helm_t01'
WHERE code IN ('smith_helm_iron_1','smith_helm_iron_01');

UPDATE blacksmith_recipes
SET
  slot = 'helmet',
  output_type = 'forge',
  output_item_code = 'helm_t02'
WHERE code IN ('smith_helm_iron_2','smith_helm_iron_02');

UPDATE blacksmith_recipes
SET
  slot = 'helmet',
  output_type = 'forge',
  output_item_code = 'helm_t03'
WHERE code IN ('smith_helm_iron_3','smith_helm_iron_03');

UPDATE blacksmith_recipes
SET
  slot = 'helmet',
  output_type = 'forge',
  output_item_code = 'helm_t11'
WHERE code LIKE '%helm%master%';

UPDATE blacksmith_recipes
SET
  slot = 'helmet',
  output_type = 'forge',
  output_item_code = 'helm_t29'
WHERE code LIKE '%malahit%';

UPDATE blacksmith_recipes
SET
  slot = 'helmet',
  output_type = 'forge',
  output_item_code = 'helm_t37'
WHERE code LIKE '%quartz%';

COMMIT;