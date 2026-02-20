BEGIN;

INSERT INTO professions (code, name, descr, kind, min_level, icon)
VALUES
  ('alchemist', 'Алхімік', 'Готує зілля та еліксири', 'craft', 1, '⚗️'),
  ('blacksmith', 'Коваль', 'Кує зброю та обладунки', 'craft', 1, '⚒️'),
  ('jeweler', 'Ювелір', 'Створює каблучки й амулети', 'craft', 1, '💍'),
  ('weaver', 'Ткач', 'Плете тканини та легкі шати', 'craft', 1, '🧵')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    descr = EXCLUDED.descr,
    kind = EXCLUDED.kind,
    icon = EXCLUDED.icon,
    updated_at = NOW();

ALTER TABLE items ADD COLUMN IF NOT EXISTS code TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS emoji TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS rarity TEXT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS stats JSONB;
ALTER TABLE items ADD COLUMN IF NOT EXISTS base_value INT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS sell_price INT;
ALTER TABLE items ADD COLUMN IF NOT EXISTS is_active BOOLEAN;
ALTER TABLE items ADD COLUMN IF NOT EXISTS slot TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS ux_items_code ON items(code);

INSERT INTO craft_materials (code, name, descr, profession, source_type, rarity)
VALUES
 ('fiber_t1','Льняне волокно','Базове волокно для пряжі.','ткач','fiber','Звичайний'),
 ('fiber_t2','Конопляне волокно','Міцне волокно для щільної тканини.','ткач','fiber','Добротний'),
 ('thread_t1','Груба нитка','Нитка для простого полотна.','ткач','fiber','Звичайний'),
 ('thread_t2','Міцна нитка','Нитка для ремісничого одягу.','ткач','fiber','Добротний'),
 ('cloth_t1','Лляне полотно','Легкий матеріал для шиття.','ткач','fiber','Звичайний'),
 ('cloth_t2','Посилене полотно','Покращене полотно для спорядження.','ткач','fiber','Рідкісний'),
 ('ore_metal_t1','Мідна руда','Базова руда для ювелірної оправи.','ювелір','metal','Звичайний'),
 ('ore_metal_t2','Срібна руда','Чистіша руда для коштовностей.','ювелір','metal','Добротний'),
 ('ore_gem_t1','Невеликий самоцвіт','Простий камінь для інкрустації.','ювелір','stone','Звичайний'),
 ('ore_gem_t2','Чистий самоцвіт','Камінь доброї якості для прикрас.','ювелір','stone','Рідкісний')
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    descr = EXCLUDED.descr,
    profession = EXCLUDED.profession,
    source_type = EXCLUDED.source_type,
    rarity = EXCLUDED.rarity,
    updated_at = NOW();

INSERT INTO items (code, name, emoji, category, rarity, slot, stats, base_value, sell_price, is_active)
VALUES
 ('ring_basic','Мідна каблучка','💍','jewelry','common','ring1','{"atk":1,"hp":8}'::jsonb,25,10,TRUE),
 ('ring_guard','Каблучка вартового','💍','jewelry','uncommon','ring2','{"def":2,"hp":12}'::jsonb,40,16,TRUE),
 ('ring_focus','Каблучка зосередження','💍','jewelry','rare','ring1','{"mp":18}'::jsonb,55,22,TRUE),
 ('ring_warden','Каблучка оборони','💍','jewelry','rare','ring2','{"def":4,"hp":18}'::jsonb,75,30,TRUE),
 ('amulet_basic','Амулет сили','🧿','jewelry','common','amulet','{"atk":2}'::jsonb,30,12,TRUE),
 ('amulet_mind','Амулет мудрості','🧿','jewelry','uncommon','amulet','{"mp":25}'::jsonb,48,20,TRUE),
 ('amulet_guard','Амулет захисту','🧿','jewelry','rare','amulet','{"def":5,"hp":20}'::jsonb,80,32,TRUE),
 ('cloth_basic','Грубе полотно','🧵','material','common',NULL,'{}'::jsonb,14,5,TRUE),
 ('robe_basic','Легка роба','🥋','armor_light','common','chest','{"def":2,"mp":8}'::jsonb,28,11,TRUE),
 ('robe_apprentice','Роба підмайстра','🥋','armor_light','uncommon','chest','{"def":4,"mp":14}'::jsonb,45,18,TRUE),
 ('cloak_basic','Подорожній плащ','🧥','armor_light','uncommon','cloak','{"def":3,"hp":12}'::jsonb,50,20,TRUE),
 ('pants_linen','Лляні штани','👖','armor_light','common','legs','{"def":2,"hp":10}'::jsonb,24,10,TRUE),
 ('pants_guard','Посилені штани','👖','armor_light','rare','legs','{"def":5,"hp":18}'::jsonb,64,25,TRUE)
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name,
    emoji = EXCLUDED.emoji,
    category = EXCLUDED.category,
    rarity = EXCLUDED.rarity,
    slot = EXCLUDED.slot,
    stats = EXCLUDED.stats,
    base_value = EXCLUDED.base_value,
    sell_price = EXCLUDED.sell_price,
    is_active = EXCLUDED.is_active;

INSERT INTO craft_recipes (code, profession_code, name, descr, result_item_code, result_qty, level_required, energy_cost)
VALUES
 ('jewel_ring_basic','jeweler','Проста каблучка','Базова мідна каблучка.','ring_basic',1,1,4),
 ('jewel_amulet_basic','jeweler','Амулет сили','Початковий амулет сили.','amulet_basic',1,1,5),
 ('jewel_ring_guard','jeweler','Каблучка вартового','Покращена захисна каблучка.','ring_guard',1,3,6),
 ('jewel_amulet_mind','jeweler','Амулет мудрості','Посилює магічну стійкість.','amulet_mind',1,4,7),
 ('jewel_ring_focus','jeweler','Каблучка фокусу','Підсилює запас мани.','ring_focus',1,5,8),
 ('jewel_ring_warden','jeweler','Каблучка оборони','Надійна бойова каблучка.','ring_warden',1,7,9),
 ('jewel_amulet_guard','jeweler','Амулет захисту','Рідкісний амулет оборони.','amulet_guard',1,8,10),
 ('jewel_gem_chip','jeweler','Огранка каменя','Підготовка самоцвіту до вставки.','ore_gem_t2',1,2,4),
 ('jewel_refine_metal','jeweler','Очищення металу','Підготовка металу до оправи.','ore_metal_t2',1,3,5),
 ('jewel_master_set','jeweler','Набір прикрас','Серія дрібних прикрас.','ring_basic',2,10,12),

 ('weaver_thread','weaver','Пряжа','Обробка волокна в нитку.','thread_t1',1,1,3),
 ('weaver_thread_fine','weaver','Міцна пряжа','Посилена нитка для шиття.','thread_t2',1,3,5),
 ('weaver_cloth','weaver','Тканина','Базове полотно.','cloth_basic',1,2,4),
 ('weaver_robe','weaver','Легка роба','Початкова роба з полотна.','robe_basic',1,3,6),
 ('weaver_robe_apprentice','weaver','Роба підмайстра','Покращена мана-роба.','robe_apprentice',1,5,8),
 ('weaver_cloak_basic','weaver','Подорожній плащ','Теплий плащ для мандрівки.','cloak_basic',1,4,7),
 ('weaver_pants_linen','weaver','Лляні штани','Базовий легкий захист.','pants_linen',1,2,5),
 ('weaver_pants_guard','weaver','Посилені штани','Покращений захист ніг.','pants_guard',1,6,9),
 ('weaver_cloth_refine','weaver','Посилене полотно','Підготовка рідкісної тканини.','cloth_t2',1,6,8),
 ('weaver_bundle','weaver','Пакунок тканин','Пакет базових матеріалів.','cloth_basic',2,8,10)
ON CONFLICT (code) DO UPDATE
SET profession_code = EXCLUDED.profession_code,
    name = EXCLUDED.name,
    descr = EXCLUDED.descr,
    result_item_code = EXCLUDED.result_item_code,
    result_qty = EXCLUDED.result_qty,
    level_required = EXCLUDED.level_required,
    energy_cost = EXCLUDED.energy_cost;

DELETE FROM craft_recipe_ingredients
WHERE recipe_code IN (
 'jewel_ring_basic','jewel_amulet_basic','jewel_ring_guard','jewel_amulet_mind','jewel_ring_focus','jewel_ring_warden','jewel_amulet_guard','jewel_gem_chip','jewel_refine_metal','jewel_master_set',
 'weaver_thread','weaver_thread_fine','weaver_cloth','weaver_robe','weaver_robe_apprentice','weaver_cloak_basic','weaver_pants_linen','weaver_pants_guard','weaver_cloth_refine','weaver_bundle'
);

INSERT INTO craft_recipe_ingredients (recipe_code, item_code, qty) VALUES
 ('jewel_ring_basic','ore_metal_t1',2),('jewel_ring_basic','ore_gem_t1',1),
 ('jewel_amulet_basic','ore_metal_t1',1),('jewel_amulet_basic','ore_gem_t1',2),
 ('jewel_ring_guard','ore_metal_t2',2),('jewel_ring_guard','ore_gem_t1',2),
 ('jewel_amulet_mind','ore_metal_t2',1),('jewel_amulet_mind','ore_gem_t2',2),
 ('jewel_ring_focus','ore_metal_t2',2),('jewel_ring_focus','ore_gem_t2',2),
 ('jewel_ring_warden','ore_metal_t2',3),('jewel_ring_warden','ore_gem_t2',2),
 ('jewel_amulet_guard','ore_metal_t2',2),('jewel_amulet_guard','ore_gem_t2',3),
 ('jewel_gem_chip','ore_gem_t1',2),
 ('jewel_refine_metal','ore_metal_t1',3),
 ('jewel_master_set','ore_metal_t2',4),('jewel_master_set','ore_gem_t2',4),

 ('weaver_thread','fiber_t1',2),
 ('weaver_thread_fine','fiber_t2',2),('weaver_thread_fine','thread_t1',1),
 ('weaver_cloth','thread_t1',2),('weaver_cloth','fiber_t1',1),
 ('weaver_robe','cloth_basic',2),('weaver_robe','thread_t1',1),
 ('weaver_robe_apprentice','cloth_t2',2),('weaver_robe_apprentice','thread_t2',2),
 ('weaver_cloak_basic','cloth_basic',2),('weaver_cloak_basic','thread_t2',1),
 ('weaver_pants_linen','cloth_basic',1),('weaver_pants_linen','thread_t1',1),
 ('weaver_pants_guard','cloth_t2',2),('weaver_pants_guard','thread_t2',2),
 ('weaver_cloth_refine','cloth_basic',2),('weaver_cloth_refine','thread_t2',1),
 ('weaver_bundle','cloth_t2',1),('weaver_bundle','thread_t2',2);

COMMIT;
