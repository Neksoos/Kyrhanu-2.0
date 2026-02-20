-- =========================================================
-- SEED: Blacksmith HELMETS Lv 1-50 (ONLY recipes + ingredients)
-- ✅ items НЕ чіпаємо (бо вони вже є у тебе)
-- ✅ blacksmith_recipes: prof_key / craft_time_sec / output_kind / output_code / type / json_data
-- ✅ blacksmith_recipe_ingredients: recipe_code / input_kind / input_code / qty / role
-- =========================================================

BEGIN;

-- ─────────────────────────────────────────────
-- 0) Ensure blacksmith_recipes matches expected schema (backward-compat)
-- ─────────────────────────────────────────────
ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS prof_key text NOT NULL DEFAULT 'blacksmith';

ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS craft_time_sec int NOT NULL DEFAULT 180;

ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS output_kind text NOT NULL DEFAULT 'item';

ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS output_code text;

ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS type text NOT NULL DEFAULT 'forge';

ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS notes text;

ALTER TABLE blacksmith_recipes
  ADD COLUMN IF NOT EXISTS json_data jsonb NOT NULL DEFAULT '{}'::jsonb;

-- Якщо у старій схемі було output_item_code — заповнюємо output_code
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipes'
      AND column_name='output_item_code'
  ) THEN
    UPDATE blacksmith_recipes
    SET output_code = COALESCE(output_code, output_item_code),
        output_kind = COALESCE(output_kind, 'item')
    WHERE output_code IS NULL;
  END IF;

  -- Якщо була output_type — мапимо в type
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipes'
      AND column_name='output_type'
  ) THEN
    UPDATE blacksmith_recipes
    SET type = COALESCE(type, output_type)
    WHERE type IS NULL;
  END IF;
END $$;

-- ─────────────────────────────────────────────
-- 0.05) CRITICAL backward-compat:
--       якщо output_item_code існує і має NOT NULL — знімаємо, інакше UPSERT впаде
-- ─────────────────────────────────────────────
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipes'
      AND column_name='output_item_code'
  ) THEN
    BEGIN
      ALTER TABLE public.blacksmith_recipes
        ALTER COLUMN output_item_code DROP NOT NULL;
    EXCEPTION WHEN others THEN
      NULL;
    END;
  END IF;
END $$;

-- ─────────────────────────────────────────────
-- 0.1) Ensure ingredients table matches current schema
--      (material_code -> input_code) + missing cols
-- ─────────────────────────────────────────────
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipe_ingredients'
      AND column_name='material_code'
  )
  AND NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipe_ingredients'
      AND column_name='input_code'
  )
  THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      RENAME COLUMN material_code TO input_code;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipe_ingredients'
      AND column_name='input_kind'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN input_kind text NOT NULL DEFAULT 'material';
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipe_ingredients'
      AND column_name='qty'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN qty int NOT NULL DEFAULT 1;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipe_ingredients'
      AND column_name='role'
  ) THEN
    ALTER TABLE public.blacksmith_recipe_ingredients
      ADD COLUMN role text NOT NULL DEFAULT 'metal';
  END IF;
END $$;

DROP INDEX IF EXISTS uq_bsmith_ing;
CREATE UNIQUE INDEX uq_bsmith_ing
ON blacksmith_recipe_ingredients (recipe_code, input_code, role);

-- ─────────────────────────────────────────────
-- 0) CLEANUP (тільки наші коди)
-- ─────────────────────────────────────────────
DELETE FROM blacksmith_recipe_ingredients
WHERE recipe_code LIKE 'bs:forge:helm_t%';

DELETE FROM blacksmith_recipes
WHERE code LIKE 'bs:forge:helm_t%';

-- ─────────────────────────────────────────────
-- 1) TEMP recipes source (50 штук)
-- ─────────────────────────────────────────────
CREATE TEMP TABLE tmp_bsmith_helm_recipes (
  code text,
  name text,
  level_req int,
  craft_time_sec int,
  slot text,
  forge_hits int,
  base_progress_per_hit double precision,
  heat_sensitivity double precision,
  rhythm_min_ms int,
  rhythm_max_ms int,
  output_kind text,
  output_code text,
  output_amount int,
  type text,
  notes text,
  json_data jsonb
) ON COMMIT DROP;

INSERT INTO tmp_bsmith_helm_recipes
(code,name,level_req,craft_time_sec,slot,forge_hits,base_progress_per_hit,heat_sensitivity,rhythm_min_ms,rhythm_max_ms,output_kind,output_code,output_amount,type,notes,json_data)
VALUES
('bs:forge:helm_t01','Кування: Залізний капор новака',1,180,'helmet',40,1.0/40,0.62,120,220,'item','helm_t01',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',1,'group','forge')),
('bs:forge:helm_t02','Кування: Залізна шапка під шолом',2,184,'helmet',42,1.0/42,0.62,120,220,'item','helm_t02',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',2,'group','forge')),
('bs:forge:helm_t03','Кування: Клепаний налобник',3,188,'helmet',44,1.0/44,0.63,120,220,'item','helm_t03',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',3,'group','forge')),
('bs:forge:helm_t04','Кування: Мисюрка новака',4,192,'helmet',46,1.0/46,0.63,120,220,'item','helm_t04',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',4,'group','forge')),
('bs:forge:helm_t05','Кування: Кольчужна шапка',5,196,'helmet',48,1.0/48,0.64,120,220,'item','helm_t05',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',5,'group','forge')),
('bs:forge:helm_t06','Кування: Степовий шолом',6,200,'helmet',50,1.0/50,0.64,120,220,'item','helm_t06',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',6,'group','forge')),
('bs:forge:helm_t07','Кування: Лісова мисюрка',7,204,'helmet',52,1.0/52,0.65,120,220,'item','helm_t07',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',7,'group','forge')),
('bs:forge:helm_t08','Кування: Дружинний шолом',8,208,'helmet',54,1.0/54,0.65,120,220,'item','helm_t08',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',8,'group','forge')),
('bs:forge:helm_t09','Кування: Шолом сторожа',9,212,'helmet',56,1.0/56,0.66,120,220,'item','helm_t09',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',9,'group','forge')),
('bs:forge:helm_t10','Кування: Шолом варти',10,216,'helmet',58,1.0/58,0.66,120,220,'item','helm_t10',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',10,'group','forge')),

('bs:forge:helm_t11','Кування: Мисюрка майстра',11,220,'helmet',62,1.0/62,0.66,120,220,'item','helm_t11',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',11,'group','forge')),
('bs:forge:helm_t12','Кування: Шолом ремісника',12,224,'helmet',64,1.0/64,0.66,120,220,'item','helm_t12',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',12,'group','forge')),
('bs:forge:helm_t13','Кування: Кований бацинет',13,228,'helmet',66,1.0/66,0.66,120,220,'item','helm_t13',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',13,'group','forge')),
('bs:forge:helm_t14','Кування: Шолом подорожнього',14,232,'helmet',68,1.0/68,0.66,120,220,'item','helm_t14',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',14,'group','forge')),
('bs:forge:helm_t15','Кування: Шолом загартований',15,236,'helmet',70,1.0/70,0.66,120,220,'item','helm_t15',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',15,'group','forge')),
('bs:forge:helm_t16','Кування: Шолом клинцевий',16,240,'helmet',72,1.0/72,0.66,120,220,'item','helm_t16',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',16,'group','forge')),
('bs:forge:helm_t17','Кування: Мисюрка дружинника',17,244,'helmet',74,1.0/74,0.66,120,220,'item','helm_t17',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',17,'group','forge')),
('bs:forge:helm_t18','Кування: Шолом з ребром',18,248,'helmet',76,1.0/76,0.66,120,220,'item','helm_t18',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',18,'group','forge')),
('bs:forge:helm_t19','Кування: Шолом степовика',19,252,'helmet',78,1.0/78,0.66,120,220,'item','helm_t19',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',19,'group','forge')),
('bs:forge:helm_t20','Кування: Шолом козацький',20,256,'helmet',80,1.0/80,0.66,120,220,'item','helm_t20',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',20,'group','forge')),

('bs:forge:helm_t21','Кування: Шолом із кварцовим ребром',21,260,'helmet',86,1.0/86,0.65,120,220,'item','helm_t21',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',21,'group','forge')),
('bs:forge:helm_t22','Кування: Бацинет з оніксом',22,264,'helmet',88,1.0/88,0.65,120,220,'item','helm_t22',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',22,'group','forge')),
('bs:forge:helm_t23','Кування: Мисюрка з кальцитом',23,268,'helmet',90,1.0/90,0.65,120,220,'item','helm_t23',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',23,'group','forge')),
('bs:forge:helm_t24','Кування: Шолом із бурштином',24,272,'helmet',92,1.0/92,0.65,120,220,'item','helm_t24',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',24,'group','forge')),
('bs:forge:helm_t25','Кування: Шолом з нефритом',25,276,'helmet',94,1.0/94,0.65,120,220,'item','helm_t25',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',25,'group','forge')),
('bs:forge:helm_t26','Кування: Шолом з лазуритом',26,280,'helmet',96,1.0/96,0.65,120,220,'item','helm_t26',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',26,'group','forge')),
('bs:forge:helm_t27','Кування: Шолом з серпентином',27,284,'helmet',98,1.0/98,0.65,120,220,'item','helm_t27',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',27,'group','forge')),
('bs:forge:helm_t28','Кування: Шолом з бірюзою',28,288,'helmet',100,1.0/100,0.65,120,220,'item','helm_t28',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',28,'group','forge')),
('bs:forge:helm_t29','Кування: Шолом з малахітом',29,292,'helmet',102,1.0/102,0.65,120,220,'item','helm_t29',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',29,'group','forge')),
('bs:forge:helm_t30','Кування: Шолом із рогокаменем',30,296,'helmet',104,1.0/104,0.65,120,220,'item','helm_t30',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',30,'group','forge')),

('bs:forge:helm_t31','Кування: Крицевий шолом з оніксом',31,300,'helmet',112,1.0/112,0.64,120,220,'item','helm_t31',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',31,'group','forge')),
('bs:forge:helm_t32','Кування: Крицевий бацинет з кварцом',32,304,'helmet',114,1.0/114,0.64,120,220,'item','helm_t32',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',32,'group','forge')),
('bs:forge:helm_t33','Кування: Шолом з бурштином і кальцитом',33,308,'helmet',116,1.0/116,0.64,120,220,'item','helm_t33',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',33,'group','forge')),
('bs:forge:helm_t34','Кування: Шолом з нефритом і серпентином',34,312,'helmet',118,1.0/118,0.64,120,220,'item','helm_t34',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',34,'group','forge')),
('bs:forge:helm_t35','Кування: Шолом з лазуритом і бірюзою',35,316,'helmet',120,1.0/120,0.64,120,220,'item','helm_t35',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',35,'group','forge')),
('bs:forge:helm_t36','Кування: Шолом з малахітом і оніксом',36,320,'helmet',122,1.0/122,0.64,120,220,'item','helm_t36',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',36,'group','forge')),
('bs:forge:helm_t37','Кування: Шолом з рогокаменем і кварцом',37,324,'helmet',124,1.0/124,0.64,120,220,'item','helm_t37',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',37,'group','forge')),
('bs:forge:helm_t38','Кування: Шолом з нефритом і бурштином',38,328,'helmet',126,1.0/126,0.64,120,220,'item','helm_t38',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',38,'group','forge')),
('bs:forge:helm_t39','Кування: Шолом з серпентином і кальцитом',39,332,'helmet',128,1.0/128,0.64,120,220,'item','helm_t39',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',39,'group','forge')),
('bs:forge:helm_t40','Кування: Шолом з лазуритом і малахітом',40,336,'helmet',130,1.0/130,0.64,120,220,'item','helm_t40',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',40,'group','forge')),

('bs:forge:helm_t41','Кування: Обереговий шолом білокаменю',41,340,'helmet',140,1.0/140,0.63,120,220,'item','helm_t41',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',41,'group','forge')),
('bs:forge:helm_t42','Кування: Обереговий бацинет сріблокаменю',42,344,'helmet',142,1.0/142,0.63,120,220,'item','helm_t42',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',42,'group','forge')),
('bs:forge:helm_t43','Кування: Обереговий шолом з громокаменем',43,348,'helmet',144,1.0/144,0.63,120,220,'item','helm_t43',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',43,'group','forge')),
('bs:forge:helm_t44','Кування: Обереговий шолом з перуновим кременем',44,352,'helmet',146,1.0/146,0.63,120,220,'item','helm_t44',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',44,'group','forge')),
('bs:forge:helm_t45','Кування: Обереговий шолом небесного каменю',45,356,'helmet',148,1.0/148,0.63,120,220,'item','helm_t45',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',45,'group','forge')),
('bs:forge:helm_t46','Кування: Обереговий шолом світлокаменю',46,360,'helmet',150,1.0/150,0.63,120,220,'item','helm_t46',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',46,'group','forge')),
('bs:forge:helm_t47','Кування: Обереговий шолом зіркового кварцу',47,364,'helmet',152,1.0/152,0.63,120,220,'item','helm_t47',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',47,'group','forge')),

('bs:forge:helm_t48','Кування: Шолом Перуна',48,372,'helmet',168,1.0/168,0.62,120,220,'item','helm_t48',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',48,'group','forge')),
('bs:forge:helm_t49','Кування: Бацинет Перуна',49,380,'helmet',172,1.0/172,0.62,120,220,'item','helm_t49',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',49,'group','forge')),
('bs:forge:helm_t50','Кування: Вінець Грому',50,388,'helmet',176,1.0/176,0.62,120,220,'item','helm_t50',1,'forge',NULL, jsonb_build_object('slot','helmet','tier',50,'group','forge'));

-- ─────────────────────────────────────────────
-- 2) UPSERT у blacksmith_recipes
-- ─────────────────────────────────────────────
INSERT INTO blacksmith_recipes
  (code, name, prof_key, level_req, craft_time_sec,
   slot, forge_hits, base_progress_per_hit, heat_sensitivity,
   rhythm_min_ms, rhythm_max_ms,
   output_kind, output_code, output_amount,
   type, notes, json_data)
SELECT
  t.code, t.name, 'blacksmith', t.level_req, t.craft_time_sec,
  t.slot, t.forge_hits, t.base_progress_per_hit, t.heat_sensitivity,
  t.rhythm_min_ms, t.rhythm_max_ms,
  t.output_kind, t.output_code, t.output_amount,
  t.type, t.notes, t.json_data
FROM tmp_bsmith_helm_recipes t
ON CONFLICT (code) DO UPDATE SET
  name = EXCLUDED.name,
  prof_key = EXCLUDED.prof_key,
  level_req = EXCLUDED.level_req,
  craft_time_sec = EXCLUDED.craft_time_sec,
  slot = EXCLUDED.slot,
  forge_hits = EXCLUDED.forge_hits,
  base_progress_per_hit = EXCLUDED.base_progress_per_hit,
  heat_sensitivity = EXCLUDED.heat_sensitivity,
  rhythm_min_ms = EXCLUDED.rhythm_min_ms,
  rhythm_max_ms = EXCLUDED.rhythm_max_ms,
  output_kind = EXCLUDED.output_kind,
  output_code = EXCLUDED.output_code,
  output_amount = EXCLUDED.output_amount,
  type = EXCLUDED.type,
  notes = EXCLUDED.notes,
  json_data = EXCLUDED.json_data,
  updated_at = now();

-- ─────────────────────────────────────────────
-- 2.9) backward-compat: якщо існує output_item_code — заповнюємо його з output_code
-- ─────────────────────────────────────────────
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema='public'
      AND table_name='blacksmith_recipes'
      AND column_name='output_item_code'
  ) THEN
    UPDATE public.blacksmith_recipes
    SET output_item_code = COALESCE(output_item_code, output_code)
    WHERE code LIKE 'bs:forge:helm_t%'
      AND output_item_code IS NULL;
  END IF;
END $$;

-- ─────────────────────────────────────────────
-- 3) INGREDIENTS — 1..50 (metal + stone)
-- ─────────────────────────────────────────────
INSERT INTO blacksmith_recipe_ingredients (recipe_code, input_kind, input_code, qty, role) VALUES
  -- 1-10
  ('bs:forge:helm_t01','material','smith_ingot_zalizna',2,'metal'),
  ('bs:forge:helm_t01','material','smith_sand_sieved',1,'stone'),

  ('bs:forge:helm_t02','material','smith_ingot_zalizna',2,'metal'),
  ('bs:forge:helm_t02','material','smith_block_kamin_richkovyi',1,'stone'),

  ('bs:forge:helm_t03','material','smith_ingot_zalizna',3,'metal'),
  ('bs:forge:helm_t03','material','smith_sand_sieved',1,'stone'),

  ('bs:forge:helm_t04','material','smith_ingot_zalizna',3,'metal'),
  ('bs:forge:helm_t04','material','smith_block_piskovyk',1,'stone'),

  ('bs:forge:helm_t05','material','smith_ingot_zalizna',4,'metal'),
  ('bs:forge:helm_t05','material','smith_lime_burned',1,'stone'),

  ('bs:forge:helm_t06','material','smith_ingot_zalizna',4,'metal'),
  ('bs:forge:helm_t06','material','smith_block_kamin_richkovyi',2,'stone'),

  ('bs:forge:helm_t07','material','smith_ingot_zalizna',5,'metal'),
  ('bs:forge:helm_t07','material','smith_block_piskovyk',1,'stone'),

  ('bs:forge:helm_t08','material','smith_ingot_zalizna',5,'metal'),
  ('bs:forge:helm_t08','material','smith_block_hranit',1,'stone'),

  ('bs:forge:helm_t09','material','smith_ingot_zalizna',6,'metal'),
  ('bs:forge:helm_t09','material','smith_lime_burned',2,'stone'),

  ('bs:forge:helm_t10','material','smith_ingot_zalizna',6,'metal'),
  ('bs:forge:helm_t10','material','smith_block_hranit',1,'stone'),

  -- 11-20
  ('bs:forge:helm_t11','material','smith_ingot_zalizna',6,'metal'),
  ('bs:forge:helm_t11','material','smith_ingot_midna',1,'metal'),
  ('bs:forge:helm_t11','material','smith_block_piskovyk',2,'stone'),

  ('bs:forge:helm_t12','material','smith_ingot_zalizna',6,'metal'),
  ('bs:forge:helm_t12','material','smith_ingot_midna',2,'metal'),
  ('bs:forge:helm_t12','material','smith_lime_burned',2,'stone'),

  ('bs:forge:helm_t13','material','smith_ingot_zalizna',7,'metal'),
  ('bs:forge:helm_t13','material','smith_ingot_marhantseva',1,'metal'),
  ('bs:forge:helm_t13','material','smith_block_hranit',2,'stone'),

  ('bs:forge:helm_t14','material','smith_ingot_zalizna',7,'metal'),
  ('bs:forge:helm_t14','material','smith_ingot_midna',2,'metal'),
  ('bs:forge:helm_t14','material','smith_block_kamin_richkovyi',3,'stone'),

  ('bs:forge:helm_t15','material','smith_ingot_zalizna',8,'metal'),
  ('bs:forge:helm_t15','material','smith_ingot_marhantseva',1,'metal'),
  ('bs:forge:helm_t15','material','smith_block_piskovyk',3,'stone'),

  ('bs:forge:helm_t16','material','smith_ingot_zalizna',8,'metal'),
  ('bs:forge:helm_t16','material','smith_ingot_midna',2,'metal'),
  ('bs:forge:helm_t16','material','smith_lime_burned',3,'stone'),

  ('bs:forge:helm_t17','material','smith_ingot_zalizna',9,'metal'),
  ('bs:forge:helm_t17','material','smith_ingot_marhantseva',2,'metal'),
  ('bs:forge:helm_t17','material','smith_block_hranit',2,'stone'),

  ('bs:forge:helm_t18','material','smith_ingot_zalizna',9,'metal'),
  ('bs:forge:helm_t18','material','smith_ingot_midna',3,'metal'),
  ('bs:forge:helm_t18','material','smith_block_piskovyk',3,'stone'),

  ('bs:forge:helm_t19','material','smith_ingot_zalizna',10,'metal'),
  ('bs:forge:helm_t19','material','smith_ingot_marhantseva',2,'metal'),
  ('bs:forge:helm_t19','material','smith_block_hranit',3,'stone'),

  ('bs:forge:helm_t20','material','smith_ingot_zalizna',10,'metal'),
  ('bs:forge:helm_t20','material','smith_ingot_midna',3,'metal'),
  ('bs:forge:helm_t20','material','smith_block_kamin_richkovyi',4,'stone'),

  -- 21-50
  ('bs:forge:helm_t21','material','smith_ingot_zalizna',11,'metal'),
  ('bs:forge:helm_t21','material','smith_ingot_marhantseva',2,'metal'),
  ('bs:forge:helm_t21','material','smith_block_hranit',4,'stone'),
  ('bs:forge:helm_t21','material','jewel_quartz_prozorii',1,'stone'),

  ('bs:forge:helm_t22','material','smith_ingot_zalizna',11,'metal'),
  ('bs:forge:helm_t22','material','smith_ingot_midna',3,'metal'),
  ('bs:forge:helm_t22','material','smith_block_piskovyk',4,'stone'),
  ('bs:forge:helm_t22','material','jewel_oniks_temnyi',1,'stone'),

  ('bs:forge:helm_t23','material','smith_ingot_zalizna',12,'metal'),
  ('bs:forge:helm_t23','material','smith_ingot_marhantseva',2,'metal'),
  ('bs:forge:helm_t23','material','smith_lime_burned',4,'stone'),
  ('bs:forge:helm_t23','material','jewel_kaltsyt_polished',1,'stone'),

  ('bs:forge:helm_t24','material','smith_ingot_zalizna',12,'metal'),
  ('bs:forge:helm_t24','material','smith_ingot_midna',3,'metal'),
  ('bs:forge:helm_t24','material','smith_block_hranit',4,'stone'),
  ('bs:forge:helm_t24','material','jewel_amber_burshtyn',1,'stone'),

  ('bs:forge:helm_t25','material','smith_ingot_zalizna',13,'metal'),
  ('bs:forge:helm_t25','material','smith_ingot_marhantseva',3,'metal'),
  ('bs:forge:helm_t25','material','smith_block_piskovyk',5,'stone'),
  ('bs:forge:helm_t25','material','jewel_nefryt_temnyi',1,'stone'),

  ('bs:forge:helm_t26','material','smith_ingot_zalizna',13,'metal'),
  ('bs:forge:helm_t26','material','smith_ingot_midna',4,'metal'),
  ('bs:forge:helm_t26','material','smith_block_hranit',5,'stone'),
  ('bs:forge:helm_t26','material','jewel_quartz_prozorii',1,'stone'),

  ('bs:forge:helm_t27','material','smith_ingot_zalizna',14,'metal'),
  ('bs:forge:helm_t27','material','smith_ingot_marhantseva',3,'metal'),
  ('bs:forge:helm_t27','material','smith_block_piskovyk',5,'stone'),
  ('bs:forge:helm_t27','material','jewel_oniks_temnyi',1,'stone'),

  ('bs:forge:helm_t28','material','smith_ingot_zalizna',14,'metal'),
  ('bs:forge:helm_t28','material','smith_ingot_midna',4,'metal'),
  ('bs:forge:helm_t28','material','smith_block_hranit',5,'stone'),
  ('bs:forge:helm_t28','material','jewel_kaltsyt_polished',1,'stone'),

  ('bs:forge:helm_t29','material','smith_ingot_zalizna',15,'metal'),
  ('bs:forge:helm_t29','material','smith_ingot_marhantseva',4,'metal'),
  ('bs:forge:helm_t29','material','smith_block_piskovyk',6,'stone'),
  ('bs:forge:helm_t29','material','jewel_amber_burshtyn',1,'stone'),

  ('bs:forge:helm_t30','material','smith_ingot_zalizna',15,'metal'),
  ('bs:forge:helm_t30','material','smith_ingot_midna',5,'metal'),
  ('bs:forge:helm_t30','material','smith_block_hranit',6,'stone'),
  ('bs:forge:helm_t30','material','jewel_nefryt_temnyi',1,'stone'),

  ('bs:forge:helm_t31','material','smith_ingot_zalizna',16,'metal'),
  ('bs:forge:helm_t31','material','smith_ingot_marhantseva',5,'metal'),
  ('bs:forge:helm_t31','material','smith_block_hranit',6,'stone'),
  ('bs:forge:helm_t31','material','jewel_quartz_prozorii',1,'stone'),

  ('bs:forge:helm_t32','material','smith_ingot_zalizna',16,'metal'),
  ('bs:forge:helm_t32','material','smith_ingot_midna',6,'metal'),
  ('bs:forge:helm_t32','material','smith_block_piskovyk',6,'stone'),
  ('bs:forge:helm_t32','material','jewel_oniks_temnyi',1,'stone'),

  ('bs:forge:helm_t33','material','smith_ingot_zalizna',17,'metal'),
  ('bs:forge:helm_t33','material','smith_ingot_marhantseva',5,'metal'),
  ('bs:forge:helm_t33','material','smith_lime_burned',6,'stone'),
  ('bs:forge:helm_t33','material','jewel_kaltsyt_polished',1,'stone'),

  ('bs:forge:helm_t34','material','smith_ingot_zalizna',17,'metal'),
  ('bs:forge:helm_t34','material','smith_ingot_midna',6,'metal'),
  ('bs:forge:helm_t34','material','smith_block_kamin_richkovyi',7,'stone'),
  ('bs:forge:helm_t34','material','jewel_amber_burshtyn',1,'stone'),

  ('bs:forge:helm_t35','material','smith_ingot_zalizna',18,'metal'),
  ('bs:forge:helm_t35','material','smith_ingot_marhantseva',6,'metal'),
  ('bs:forge:helm_t35','material','smith_block_hranit',7,'stone'),
  ('bs:forge:helm_t35','material','jewel_nefryt_temnyi',1,'stone'),

  ('bs:forge:helm_t36','material','smith_ingot_zalizna',18,'metal'),
  ('bs:forge:helm_t36','material','smith_ingot_midna',7,'metal'),
  ('bs:forge:helm_t36','material','smith_block_piskovyk',7,'stone'),
  ('bs:forge:helm_t36','material','jewel_quartz_prozorii',1,'stone'),

  ('bs:forge:helm_t37','material','smith_ingot_zalizna',19,'metal'),
  ('bs:forge:helm_t37','material','smith_ingot_marhantseva',6,'metal'),
  ('bs:forge:helm_t37','material','smith_lime_burned',7,'stone'),
  ('bs:forge:helm_t37','material','jewel_oniks_temnyi',1,'stone'),

  ('bs:forge:helm_t38','material','smith_ingot_zalizna',19,'metal'),
  ('bs:forge:helm_t38','material','smith_ingot_midna',7,'metal'),
  ('bs:forge:helm_t38','material','smith_block_kamin_richkovyi',8,'stone'),
  ('bs:forge:helm_t38','material','jewel_kaltsyt_polished',1,'stone'),

  ('bs:forge:helm_t39','material','smith_ingot_zalizna',20,'metal'),
  ('bs:forge:helm_t39','material','smith_ingot_marhantseva',7,'metal'),
  ('bs:forge:helm_t39','material','smith_block_hranit',8,'stone'),
  ('bs:forge:helm_t39','material','jewel_amber_burshtyn',1,'stone'),

  ('bs:forge:helm_t40','material','smith_ingot_zalizna',20,'metal'),
  ('bs:forge:helm_t40','material','smith_ingot_midna',8,'metal'),
  ('bs:forge:helm_t40','material','smith_block_piskovyk',8,'stone'),
  ('bs:forge:helm_t40','material','jewel_nefryt_temnyi',1,'stone'),

  ('bs:forge:helm_t41','material','smith_ingot_zalizna',22,'metal'),
  ('bs:forge:helm_t41','material','smith_ingot_marhantseva',8,'metal'),
  ('bs:forge:helm_t41','material','smith_block_hranit',9,'stone'),
  ('bs:forge:helm_t41','material','jewel_quartz_prozorii',1,'stone'),

  ('bs:forge:helm_t42','material','smith_ingot_zalizna',23,'metal'),
  ('bs:forge:helm_t42','material','smith_ingot_midna',9,'metal'),
  ('bs:forge:helm_t42','material','smith_block_piskovyk',9,'stone'),
  ('bs:forge:helm_t42','material','jewel_oniks_temnyi',1,'stone'),

  ('bs:forge:helm_t43','material','smith_ingot_zalizna',24,'metal'),
  ('bs:forge:helm_t43','material','smith_ingot_marhantseva',9,'metal'),
  ('bs:forge:helm_t43','material','smith_lime_burned',9,'stone'),
  ('bs:forge:helm_t43','material','jewel_kaltsyt_polished',1,'stone'),

  ('bs:forge:helm_t44','material','smith_ingot_zalizna',25,'metal'),
  ('bs:forge:helm_t44','material','smith_ingot_midna',10,'metal'),
  ('bs:forge:helm_t44','material','smith_block_kamin_richkovyi',10,'stone'),
  ('bs:forge:helm_t44','material','jewel_amber_burshtyn',1,'stone'),

  ('bs:forge:helm_t45','material','smith_ingot_zalizna',26,'metal'),
  ('bs:forge:helm_t45','material','smith_ingot_marhantseva',10,'metal'),
  ('bs:forge:helm_t45','material','smith_block_hranit',10,'stone'),
  ('bs:forge:helm_t45','material','jewel_nefryt_temnyi',1,'stone'),

  ('bs:forge:helm_t46','material','smith_ingot_zalizna',27,'metal'),
  ('bs:forge:helm_t46','material','smith_ingot_midna',11,'metal'),
  ('bs:forge:helm_t46','material','smith_block_piskovyk',11,'stone'),
  ('bs:forge:helm_t46','material','jewel_quartz_prozorii',1,'stone'),

  ('bs:forge:helm_t47','material','smith_ingot_zalizna',28,'metal'),
  ('bs:forge:helm_t47','material','smith_ingot_marhantseva',11,'metal'),
  ('bs:forge:helm_t47','material','smith_lime_burned',11,'stone'),
  ('bs:forge:helm_t47','material','jewel_oniks_temnyi',1,'stone'),

  ('bs:forge:helm_t48','material','smith_ingot_zalizna',30,'metal'),
  ('bs:forge:helm_t48','material','smith_ingot_midna',12,'metal'),
  ('bs:forge:helm_t48','material','smith_block_hranit',12,'stone'),
  ('bs:forge:helm_t48','material','jewel_kaltsyt_polished',1,'stone'),

  ('bs:forge:helm_t49','material','smith_ingot_zalizna',32,'metal'),
  ('bs:forge:helm_t49','material','smith_ingot_marhantseva',12,'metal'),
  ('bs:forge:helm_t49','material','smith_block_kamin_richkovyi',12,'stone'),
  ('bs:forge:helm_t49','material','jewel_amber_burshtyn',1,'stone'),

  ('bs:forge:helm_t50','material','smith_ingot_zalizna',34,'metal'),
  ('bs:forge:helm_t50','material','smith_ingot_midna',13,'metal'),
  ('bs:forge:helm_t50','material','smith_block_hranit',13,'stone'),
  ('bs:forge:helm_t50','material','jewel_nefryt_temnyi',1,'stone');

COMMIT;