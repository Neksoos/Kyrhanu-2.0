-- самоцвіти/камені (якщо ти ювелірку відділяєш) -> ювелір
UPDATE items
SET use_professions = ARRAY['jeweler']
WHERE category = 'ks' OR code LIKE 'ore_gem_%';
