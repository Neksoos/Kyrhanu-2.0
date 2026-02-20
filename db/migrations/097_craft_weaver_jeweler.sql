-- Додати професію ткач
INSERT INTO professions (code, name, descr, kind, min_level)
VALUES ('weaver', 'Ткач', 'Виготовляє тканини та легкі обладунки', 'craft', 1)
ON CONFLICT DO NOTHING;

-- Таблиці для універсального craft
CREATE TABLE IF NOT EXISTS craft_recipes (
    code TEXT PRIMARY KEY,
    profession_code TEXT REFERENCES professions(code),
    name TEXT NOT NULL,
    descr TEXT,
    result_item_code TEXT NOT NULL,
    result_qty INT DEFAULT 1,
    level_required INT DEFAULT 1,
    energy_cost INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS craft_recipe_ingredients (
    recipe_code TEXT REFERENCES craft_recipes(code) ON DELETE CASCADE,
    item_code TEXT NOT NULL,
    qty INT NOT NULL
);

-- Jeweler recipes
INSERT INTO craft_recipes
(code, profession_code, name, descr, result_item_code)
VALUES
('jewel_ring_basic','jeweler','Просте кільце','Срібне кільце','ring_basic'),
('jewel_amulet_basic','jeweler','Амулет сили','Дає невеликий бонус','amulet_basic');

-- Weaver recipes
INSERT INTO craft_recipes
(code, profession_code, name, descr, result_item_code)
VALUES
('weaver_cloth','weaver','Тканина','Проста тканина','cloth_basic'),
('weaver_robe','weaver','Роба','Легка роба','robe_basic');

-- Ingredients
INSERT INTO craft_recipe_ingredients VALUES
('jewel_ring_basic','ore_metal_t1',2),
('jewel_ring_basic','ore_gem_t1',1),
('jewel_amulet_basic','ore_metal_t1',1),
('jewel_amulet_basic','ore_gem_t1',2),

('weaver_cloth','fiber_t1',3),
('weaver_robe','cloth_basic',2);