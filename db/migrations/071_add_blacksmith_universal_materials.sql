BEGIN;

-- ─────────────────────────────────────────────
-- 0) Ensure recipes table exists
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blacksmith_recipes (
  code                   text PRIMARY KEY,
  name                   text NOT NULL,
  slot                   text NOT NULL,
  level_req              int  NOT NULL DEFAULT 1,

  forge_hits             int  NOT NULL DEFAULT 60,
  base_progress_per_hit  double precision NOT NULL DEFAULT 0.0166667,
  heat_sensitivity       double precision NOT NULL DEFAULT 0.65,
  rhythm_min_ms          int  NOT NULL DEFAULT 120,
  rhythm_max_ms          int  NOT NULL DEFAULT 220,

  output_item_code       text NOT NULL,
  output_amount          int  NOT NULL DEFAULT 1,

  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);

-- ✅ backward-compat: якщо таблиця вже існувала без output_type
ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS output_type text NOT NULL DEFAULT 'item';

-- ─────────────────────────────────────────────
-- 0.1) Ensure ingredients table matches current schema
--      (recipe_code, input_kind, input_code, qty, role)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blacksmith_recipe_ingredients (
  id          bigserial PRIMARY KEY,
  recipe_code text NOT NULL REFERENCES blacksmith_recipes(code) ON DELETE CASCADE,
  input_kind  text NOT NULL DEFAULT 'material',
  input_code  text NOT NULL,
  qty         int  NOT NULL DEFAULT 1,
  role        text NOT NULL DEFAULT 'metal'
);

-- ─────────────────────────────────────────────
-- 0.2) backward-compat: старі схеми ingredients
--      (material_code -> input_code) + відсутні колонки
-- ─────────────────────────────────────────────
DO $$
BEGIN
  -- якщо таблиця існувала раніше і мала material_code замість input_code
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'material_code'
  )
  AND NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'input_code'
  )
  THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      RENAME COLUMN material_code TO input_code;
  END IF;

  -- на всякий випадок: якщо чогось не вистачає у старій таблиці
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'input_kind'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN input_kind text NOT NULL DEFAULT 'material';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'qty'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN qty int NOT NULL DEFAULT 1;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'role'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN role text NOT NULL DEFAULT 'metal';
  END IF;

  -- страховка: якщо немає input_code ні в якому вигляді (дуже стара/крива схема)
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'input_code'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN input_code text;
  END IF;

  -- якщо ми додали input_code як nullable — зробимо NOT NULL, коли це безпечно
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'blacksmith_recipe_ingredients'
      AND column_name = 'input_code'
      AND is_nullable = 'YES'
  )
  AND NOT EXISTS (
    SELECT 1 FROM public.blacksmith_recipe_ingredients
    WHERE input_code IS NULL
  )
  THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ALTER COLUMN input_code SET NOT NULL;
  END IF;
END $$;

-- індекси
CREATE INDEX IF NOT EXISTS idx_bsmith_recipes_slot ON blacksmith_recipes(slot);

-- важливо: гарантовано мати саме цей unique-індекс під ON CONFLICT
DROP INDEX IF EXISTS uq_bsmith_ing;
CREATE UNIQUE INDEX uq_bsmith_ing
ON blacksmith_recipe_ingredients (recipe_code, input_code, role);

-- ─────────────────────────────────────────────
-- 1) craft_materials: add universal smith items
-- ─────────────────────────────────────────────
INSERT INTO craft_materials (code, name, descr, profession, source_type, rarity)
SELECT *
FROM (VALUES
(
  'smith_reagent',
  'Ковальський реагент',
  'Універсальна суміш мінералів і солей, що стабілізує метал під час кування. Використовується на всіх етапах ковальського процесу.',
  'коваль',
  'змішане',
  'Добротний'
),
(
  'smith_quench_mix',
  'Гартівний склад',
  'Суміш масел, солей і мінералів для фінальної гартовки виробів. Потрібна для завершення будь-якого ковальського кування.',
  'коваль',
  'змішане',
  'Добротний'
)
) v(code, name, descr, profession, source_type, rarity)
WHERE NOT EXISTS (
  SELECT 1 FROM craft_materials cm WHERE cm.code = v.code
);

-- ─────────────────────────────────────────────
-- 2) Add these materials into EVERY recipe (через input_code)
--    reagent qty  = GREATEST(1, CEIL(level_req/2))
--    quench qty   = GREATEST(1, level_req - 1)
-- ─────────────────────────────────────────────

-- reagent
INSERT INTO blacksmith_recipe_ingredients (recipe_code, input_kind, input_code, qty, role)
SELECT
  r.code AS recipe_code,
  'material' AS input_kind,
  'smith_reagent' AS input_code,
  GREATEST(1, CEIL(r.level_req / 2.0))::int AS qty,
  'process' AS role
FROM blacksmith_recipes r
ON CONFLICT (recipe_code, input_code, role) DO NOTHING;

-- quench mix
INSERT INTO blacksmith_recipe_ingredients (recipe_code, input_kind, input_code, qty, role)
SELECT
  r.code AS recipe_code,
  'material' AS input_kind,
  'smith_quench_mix' AS input_code,
  GREATEST(1, (r.level_req - 1))::int AS qty,
  'quench' AS role
FROM blacksmith_recipes r
ON CONFLICT (recipe_code, input_code, role) DO NOTHING;

COMMIT;