begin;

-- add new currency 'dust' if not exists
insert into currencies (code, name, is_premium)
values ('dust', 'Курганний Пил', false)
on conflict (code) do nothing;

-- insert extended quest templates (daily and weekly)
insert into quest_templates (code, name, description, cadence, goal, reward, active)
values
  -- daily quests (new codes, leaving existing ones intact)
  ('Q_DAILY_RUN_1','Забіг у Курган','Заверши 1 забіг у Курган.','daily',
   '{"type":"runs_finish","amount":1}'::jsonb,
   '{"gold":70,"dust":10,"bp_xp":250}'::jsonb,
   true),
  ('Q_DAILY_BOSS_1','Удар по Вію','Завдай 1 удар Світовому Босу.','daily',
   '{"type":"boss_attack","amount":1}'::jsonb,
   '{"gold":50,"dust":5,"bp_xp":200}'::jsonb,
   true),
  ('Q_DAILY_EQUIP_1','Оберіг на день','Екіпіруй 1 предмет.','daily',
   '{"type":"equip","amount":1}'::jsonb,
   '{"gold":30,"shards":1,"bp_xp":200}'::jsonb,
   true),
  -- weekly quests
  ('Q_WEEKLY_RUN_5','Тиждень у Курганах','Заверши 5 забігів.','weekly',
   '{"type":"runs_finish","amount":5}'::jsonb,
   '{"gold":250,"dust":80,"bp_xp":600}'::jsonb,
   true),
  ('Q_WEEKLY_BOSS_10','Бий, доки туман не впаде','Зроби 10 ударів по Світовому Босу.','weekly',
   '{"type":"boss_attack","amount":10}'::jsonb,
   '{"gold":200,"shards":2,"bp_xp":500}'::jsonb,
   true),
  ('Q_WEEKLY_SALVAGE_10','Пил Кургану','Розбери 10 предметів на пил.','weekly',
   '{"type":"salvage","amount":10}'::jsonb,
   '{"gold":150,"dust":120,"bp_xp":400}'::jsonb,
   true),
  ('Q_WEEKLY_GUILD_3','Сила братства','Зроби 3 гільдійні дії (атака/внесок).','weekly',
   '{"type":"guild_actions","amount":3}'::jsonb,
   '{"gold":150,"shards":1,"bp_xp":400}'::jsonb,
   true),
  ('Q_WEEKLY_STREAK_5','Стежка повернень','Зайди в гру 5 днів цього тижня.','weekly',
   '{"type":"login_days","amount":5}'::jsonb,
   '{"gold":120,"shards":1,"bp_xp":300}'::jsonb,
   true),
  ('Q_WEEKLY_CRAFT_2','Коваль туману','Скрафти або покращи предмет 2 рази.','weekly',
   '{"type":"craft_or_upgrade","amount":2}'::jsonb,
   '{"gold":180,"dust":80,"bp_xp":450}'::jsonb,
   true)
on conflict (code) do nothing;

-- insert extended item catalog (ethno UA pixel items)
insert into items (code, name, slot, rarity, base_stats, tags)
values
  ('w_rusty_saber','Іржава шабля','weapon',1,'{"atk":2}'::jsonb, array['drop','weapon']),
  ('w_molfar_stick','Палиця мольфара','weapon',2,'{"atk":4,"luck":1}'::jsonb, array['drop','magic']),
  ('w_sich_saber','Шабля Січі','weapon',3,'{"atk":6,"crit":2}'::jsonb, array['drop','set:sich']),
  ('w_plastun_knife','Ніж пластуна','weapon',2,'{"atk":4,"spd":1}'::jsonb, array['drop','scout']),
  ('w_berehynia_mace','Булава берегині','weapon',3,'{"atk":5,"def":2}'::jsonb, array['drop','ward']),
  ('w_mavka_thorn','Колючка мавки','weapon',3,'{"atk":6,"luck":2}'::jsonb, array['drop','set:mavka']),
  ('w_iron_kosa','Залізна коса','weapon',4,'{"atk":8,"crit":3}'::jsonb, array['drop','epic']),
  ('w_kurhan_relic_blade','Реліквійний клинок Кургану','weapon',5,'{"atk":10,"boss_dmg_pct":3}'::jsonb, array['drop','set:kurhan','legendary']),
  ('w_silver_trembita','Срібна трембіта-спис','weapon',4,'{"atk":8,"spd":2}'::jsonb, array['drop','epic']),
  ('w_ritual_sickle','Обрядовий серп','weapon',2,'{"atk":3,"crit":1}'::jsonb, array['drop']),
  ('w_hunter_bow','Лук степового мисливця','weapon',3,'{"atk":5,"spd":2}'::jsonb, array['drop','scout']),
  ('w_charak_rune','Руна характерника','weapon',4,'{"atk":7,"luck":3}'::jsonb, array['drop','magic','epic']),
  ('h_traveler_cap','Шапка мандрівника','head',1,'{"def":1}'::jsonb, array['drop','starter']),
  ('h_sich_kuchma','Кучма Січі','head',3,'{"hp":10,"def":2}'::jsonb, array['drop','set:sich']),
  ('h_molfar_hood','Каптур мольфара','head',2,'{"luck":2}'::jsonb, array['drop','magic']),
  ('h_plastun_bandana','Пов’язка пластуна','head',2,'{"spd":1,"crit":1}'::jsonb, array['drop','scout']),
  ('h_mavka_wreath','Вінок мавки','head',3,'{"luck":3}'::jsonb, array['drop','set:mavka']),
  ('h_iron_helm','Залізний шолом','head',2,'{"def":3}'::jsonb, array['drop']),
  ('h_kurhan_mask','Курганна маска','head',4,'{"def":3,"boss_dmg_pct":1}'::jsonb, array['drop','set:kurhan','epic']),
  ('h_berehynia_crown','Вінець берегині','head',4,'{"hp":18,"luck":2}'::jsonb, array['drop','ward','epic']),
  ('h_steppe_goggles','Окуляри степу','head',1,'{"spd":1}'::jsonb, array['drop']),
  ('h_legend_sich_helm','Шолом Отамана','head',5,'{"hp":25,"def":4}'::jsonb, array['drop','set:sich','legendary']),
  ('a_patch_coat','Латанка','armor',1,'{"hp":6}'::jsonb, array['drop']),
  ('a_sich_zhupan','Жупан Січі','armor',3,'{"hp":14,"def":2}'::jsonb, array['drop','set:sich']),
  ('a_molfar_robes','Ризи мольфара','armor',2,'{"luck":2,"def":1}'::jsonb, array['drop','magic']),
  ('a_plastun_leather','Шкіра пластуна','armor',2,'{"spd":2}'::jsonb, array['drop','scout']),
  ('a_mavka_mist_cloak','Плащ мавчиного туману','armor',3,'{"luck":2,"spd":1}'::jsonb, array['drop','set:mavka']),
  ('a_iron_scale','Луска залізна','armor',3,'{"def":4}'::jsonb, array['drop']),
  ('a_berehynia_wrap','Покров берегині','armor',4,'{"hp":22,"def":3}'::jsonb, array['drop','ward','epic']),
  ('a_kurhan_plate','Панцир Кургану','armor',4,'{"def":5,"boss_dmg_pct":1}'::jsonb, array['drop','set:kurhan','epic']),
  ('a_steppe_mail','Степова кольчуга','armor',2,'{"def":2,"hp":8}'::jsonb, array['drop']),
  ('a_legend_mavka_skin','Шкіра Мавчиної Ночі','armor',5,'{"luck":6,"spd":3}'::jsonb, array['drop','set:mavka','legendary']),
  ('c_thread_obeirih','Нитка-оберіг','charm',1,'{"luck":1}'::jsonb, array['drop','starter']),
  ('c_kurhan_amulet','Курганний амулет','charm',4,'{"crit":3,"luck":3}'::jsonb, array['drop','epic']),
  ('c_berehynia_ring','Перстень берегині','charm',2,'{"hp":10,"luck":2}'::jsonb, array['drop','ward']),
  ('c_molfar_talisman','Талісман мольфара','charm',3,'{"crit":2,"luck":3}'::jsonb, array['drop','magic']),
  ('c_plastun_whistle','Свисток пластуна','charm',2,'{"spd":1,"crit":1}'::jsonb, array['drop','scout']),
  ('c_sich_badge','Значок Січі','charm',3,'{"atk":2,"def":1}'::jsonb, array['drop','set:sich']),
  ('c_mavka_dew','Роса мавки','charm',3,'{"luck":4}'::jsonb, array['drop','set:mavka']),
  ('c_kurhan_sigil','Печатка Кургану','charm',5,'{"boss_dmg_pct":3,"luck":4}'::jsonb, array['drop','set:kurhan','legendary']),
  ('c_black_salt','Чорна сіль','charm',1,'{"def":1}'::jsonb, array['drop']),
  ('c_kupala_wreath_knot','Вузол Купала','charm',2,'{"hp":8,"luck":1}'::jsonb, array['drop','event'])
on conflict (code) do nothing;

-- generate 50 battle pass levels for current season (S1_KURHANY) if not exists
do $$
declare
  s_id uuid;
  lvl int;
  xp int;
begin
  select id into s_id from seasons where code='S1_KURHANY' limit 1;
  if s_id is null then
    -- no season found
    return;
  end if;
  for lvl in 1..50 loop
    xp := 450 + (lvl - 1) * 15;
    insert into battle_pass_levels (season_id, level, xp_required, free_reward, premium_reward)
    values (
      s_id,
      lvl,
      xp,
      -- define free reward: gold/dust and shards occasionally
      case
        when lvl % 5 = 0 then jsonb_build_object('gold', 120 + (lvl / 5) * 10, 'shards', 1)
        when lvl % 3 = 0 then jsonb_build_object('dust', 30 + (lvl / 3) * 5)
        else jsonb_build_object('gold', 80 + (lvl * 2))
      end,
      -- premium reward: cosmetics or reroll tokens every 10 levels
      case
        when lvl % 10 = 0 then jsonb_build_object('reroll_token', 1, 'cosmetic', concat('reward_', lvl))
        when lvl % 5 = 0 then jsonb_build_object('cosmetic', concat('frame_', lvl))
        else jsonb_build_object('dust', 50 + (lvl * 2))
      end
    ) on conflict (season_id, level) do nothing;
  end loop;
end $$;

commit;