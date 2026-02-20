-- руда/каміння -> коваль
UPDATE items
SET use_professions = ARRAY['blacksmith']
WHERE category LIKE 'ore_%' OR code LIKE 'ore_%';
