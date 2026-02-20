-- трави -> зіллєвар
UPDATE items
SET use_professions = ARRAY['alchemist']
WHERE category LIKE 'herb_%' OR code LIKE 'herb_%';
