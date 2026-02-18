-- Seed minimal gameplay content (idempotent)

-- Items (definitions) stored in items.data
INSERT INTO items (id, data)
VALUES
  (
    'rusty_saber',
    '{"name":"Rusty Saber","slot":"weapon","rarity":"common","stats":{"atk":2},"price":{"chervontsi":60}}'::jsonb
  ),
  (
    'leather_vest',
    '{"name":"Leather Vest","slot":"armor","rarity":"common","stats":{"hp":5},"price":{"chervontsi":55}}'::jsonb
  ),
  (
    'herbal_kit',
    '{"name":"Herbal Kit","slot":"trinket","rarity":"common","stats":{"skill":1},"price":{"chervontsi":40}}'::jsonb
  )
ON CONFLICT (id) DO NOTHING;

-- Shop offers (catalog)
INSERT INTO shop (id, data)
VALUES
  (
    'offer_rusty_saber',
    '{"item_id":"rusty_saber","price":{"chervontsi":60},"stock":999,"tag":"starter"}'::jsonb
  ),
  (
    'offer_leather_vest',
    '{"item_id":"leather_vest","price":{"chervontsi":55},"stock":999,"tag":"starter"}'::jsonb
  ),
  (
    'offer_herbal_kit',
    '{"item_id":"herbal_kit","price":{"chervontsi":40},"stock":999,"tag":"starter"}'::jsonb
  )
ON CONFLICT (id) DO NOTHING;

-- Achievements (minimal list so /achievements GET is not empty)
INSERT INTO achievements (id, name, category, rarity, hidden, condition_json, reward_json, is_active)
VALUES
  ('first_run', 'First Run', 'runs', 'common', FALSE, '{"type":"runs_finished","gte":1}'::jsonb, '{"type":"chervontsi","amount":50}'::jsonb, TRUE),
  ('first_buy', 'First Purchase', 'shop', 'common', FALSE, '{"type":"items_bought","gte":1}'::jsonb, '{"type":"chervontsi","amount":25}'::jsonb, TRUE)
ON CONFLICT (id) DO NOTHING;
