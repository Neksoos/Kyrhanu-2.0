begin;

-- currencies
insert into currencies (code, name, is_premium) values
  ('gold','Золото', false),
  ('shards','Осколки', false),
  ('dust','Курганний пил', false),
  ('stars','Telegram Stars', true)
on conflict do nothing;

-- season
insert into seasons (code, name, theme, starts_at, ends_at, is_active, meta)
values (
  'S1_KURHANY',
  'Сезон I: Кургани Січі',
  'Козацькі поховання, прокляті печаті, туман мавок',
  now() - interval '3 days',
  now() + interval '45 days',
  true,
  '{"banner":"season1","event":"launch"}'::jsonb
)
on conflict (code) do update set is_active=true;

-- boss template
insert into boss_templates (code, name, description, base_hp, base_attack, mechanics, art_url)
values (
  'BOSS_VII',
  'Вій-Курганник',
  'Стародавній дух, що прокинувся під каменем кургану.',
  250000,
  12,
  '{"phases":[{"hp_pct":70,"effect":"fog"},{"hp_pct":30,"effect":"rage"}]}'::jsonb,
  null
)
on conflict (code) do nothing;

-- live boss (active)
do $$
declare
  s_id uuid;
  bt_id uuid;
begin
  select id into s_id from seasons where code='S1_KURHANY' limit 1;
  select id into bt_id from boss_templates where code='BOSS_VII' limit 1;

  insert into live_bosses (boss_template_id, season_id, starts_at, ends_at, max_hp, hp, state, status)
  values (bt_id, s_id, now() - interval '1 hour', now() + interval '6 days', 250000, 250000, '{}'::jsonb, 'active');
exception when unique_violation then
  null;
end $$;

-- quest templates (3)
insert into quest_templates (code, name, description, cadence, goal, reward, active)
values
  ('Q_DAILY_RUN','Забіг у Курган','Заверши 1 забіг у Курган.', 'daily', '{"type":"runs_finish","amount":1}'::jsonb, '{"gold":60}'::jsonb, true),
  ('Q_DAILY_BOSS','Удар по Вію','Завдай 1 удар Світовому Босу.', 'daily', '{"type":"boss_attack","amount":1}'::jsonb, '{"gold":40}'::jsonb, true),
  ('Q_DAILY_EQUIP','Оберіг на день','Екіпіруй 1 предмет.', 'daily', '{"type":"equip","amount":1}'::jsonb, '{"gold":30}'::jsonb, true)
on conflict (code) do nothing;

-- item catalog (starter + few)
insert into items (code, name, rarity, slot, base_stats, tags)
values
  ('starter_hat','Шапка мандрівника', 1, 'head', '{"def":1}'::jsonb, array['starter']),
  ('starter_blade','Клинок-оберіг', 1, 'weapon', '{"atk":2}'::jsonb, array['starter']),
  ('starter_charm','Нитка-оберіг', 1, 'charm', '{"luck":1}'::jsonb, array['starter']),
  ('molfar_staff','Палиця мольфара', 2, 'weapon', '{"atk":4,"crit":1}'::jsonb, array['magic']),
  ('kozaks_saber','Шабля Січі', 3, 'weapon', '{"atk":6,"crit":2}'::jsonb, array['cossack']),
  ('berehynia_ring','Перстень берегині', 2, 'charm', '{"hp":10,"luck":2}'::jsonb, array['ward']),
  ('plastikan_boots','Чоботи пластуна', 2, 'armor', '{"spd":2}'::jsonb, array['scout']),
  ('kurhan_amulet','Курганний амулет', 4, 'charm', '{"crit":3,"luck":3}'::jsonb, array['epic'])
on conflict (code) do nothing;

-- shop offers
do $$
declare s_id uuid;
begin
  select id into s_id from seasons where code='S1_KURHANY' limit 1;

  insert into shop_offers (season_id, code, title, description, price, rewards, starts_at, ends_at, active)
  values
    (s_id, 'OFFER_BP_PREMIUM', 'Преміум Battle Pass', 'Косметика + QoL нагороди сезону.', '{"currency":"stars","amount":300}'::jsonb, '{"premium_bp":true}'::jsonb, now() - interval '1 day', now() + interval '45 days', true),
    (s_id, 'OFFER_REROLL', 'Рерол Фатального Героя', 'Додатковий рерол сьогодні (1 шт).', '{"currency":"stars","amount":50}'::jsonb, '{"reroll_token":1}'::jsonb, now() - interval '1 day', now() + interval '45 days', true);
exception when unique_violation then null;
end $$;

commit;