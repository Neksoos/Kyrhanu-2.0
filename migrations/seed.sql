-- Seed content for Cursed Mounds
-- Ukrainian ethno-mythological content

-- Heroes and archetypes reference data (used by generator, not DB table)
-- This is documentation of the content system:

/*
ARCHETYPES:
- kharakternyk (козак-характерник): stealth, fire resistance, mystical
- znahar (знахар): healing, herbs, divination
- lirnyk (лірник): music, morale, spirit calling
- bortnyk (бортник): nature, bees, forest magic
- chumak (чумак): endurance, salt trade, steppe wisdom
- koval (коваль): crafting, strength, rune magic
- vertokhv (верховинець): mountain, wind, eagle spirit
- chornoknyzhnyk (чорнокнижник): forbidden knowledge, high risk/reward
*/

INSERT INTO seasons (name, theme, starts_at, ends_at, bp_base_price, bp_premium_price, is_active) VALUES
('Купала 2024', 'kupala', NOW(), NOW() + INTERVAL '90 days', 499, 999, TRUE),
('Зажинки', 'harvest', NOW() + INTERVAL '90 days', NOW() + INTERVAL '180 days', 499, 999, FALSE),
('Маланка', 'winter', NOW() + INTERVAL '180 days', NOW() + INTERVAL '270 days', 599, 1199, FALSE);

-- Initial live boss template (spawns via LiveOps system)
INSERT INTO live_bosses (
    name, description, total_health, current_health, 
    status, spawn_at, despawn_at,
    reward_chervontsi_pool, reward_kleynodu_pool, special_drops
) VALUES 
(
    'Польовий Біс із Житомирських Орлів',
    'Колись він був звичайним чумаком, але сіль із проклятого озера перетворила його на жагучу тінь. Блудить степами, плутає дороги, краде сни.',
    10000000, 10000000,
    'spawning',
    NOW() + INTERVAL '1 hour',
    NOW() + INTERVAL '25 hours',
    5000000, 5000,
    '["amulet_cursed_salt", "skin_bis_shadow", "title_saltwalker"]'::jsonb
);

-- Create initial live events (LiveOps system will manage these)
INSERT INTO live_events (event_type, name, description, config, starts_at, ends_at, is_active) VALUES
(
    'double_drop',
    'Подвійна Доля',
    'Усі кургани дають подвійну славу та черевонці. Час копати!',
    '{"multiplier": 2, "applies_to": ["glory", "chervontsi"]}'::jsonb,
    NOW(),
    NOW() + INTERVAL '3 days',
    TRUE
),
(
    'boss_rush',
    'Ніч Половика',
    'Польові біси виходять частіше. Більше босів — більше нагород!',
    '{"boss_spawn_rate": 3, "health_multiplier": 0.8}'::jsonb,
    NOW() + INTERVAL '3 days',
    NOW() + INTERVAL '6 days',
    FALSE
);