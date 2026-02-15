begin;

create extension if not exists pgcrypto;
create extension if not exists citext;

-- USERS
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  telegram_id bigint unique,
  telegram_username text,
  email citext unique,
  password_hash text,
  created_at timestamptz not null default now(),
  last_login timestamptz,
  linked_at timestamptz,
  flags jsonb not null default '{}'::jsonb
);

-- AUTH SESSIONS (refresh tokens)
create table if not exists auth_sessions (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  refresh_token_hash text not null unique,
  user_agent text not null default '',
  ip inet,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);
create index if not exists idx_auth_sessions_user on auth_sessions(user_id);

-- CHARACTERS (daily fateborn)
create table if not exists characters (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  day_key date not null,
  archetype text not null,
  stats_seed int not null,
  generated_stats jsonb not null,
  level int not null default 1,
  xp int not null default 0,
  created_at timestamptz not null default now(),
  unique (user_id, day_key)
);
create index if not exists idx_characters_user_day on characters(user_id, day_key);

-- ITEMS CATALOG
create table if not exists items (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  rarity smallint not null default 1,
  slot text not null,
  base_stats jsonb not null default '{}'::jsonb,
  tags text[] not null default '{}'::text[],
  created_at timestamptz not null default now()
);

-- ITEM INSTANCES (random rolls)
create table if not exists item_instances (
  id uuid primary key,
  item_id uuid not null references items(id) on delete restrict,
  user_id uuid not null references users(id) on delete cascade,
  roll_seed int not null,
  rolled_stats jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_item_instances_user on item_instances(user_id);

-- INVENTORY
create table if not exists inventories (
  id uuid primary key,
  user_id uuid not null unique references users(id) on delete cascade,
  capacity int not null default 60,
  created_at timestamptz not null default now()
);

create table if not exists inventory_items (
  inventory_id uuid not null references inventories(id) on delete cascade,
  item_instance_id uuid not null references item_instances(id) on delete cascade,
  quantity int not null default 1,
  primary key (inventory_id, item_instance_id)
);

-- EQUIPMENT
create table if not exists equipment_slots (
  id uuid primary key,
  character_id uuid not null references characters(id) on delete cascade,
  slot text not null,
  item_instance_id uuid references item_instances(id) on delete set null,
  unique (character_id, slot)
);

-- RUNS / DUNGEONS
create table if not exists runs (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  character_id uuid not null references characters(id) on delete cascade,
  seed bigint not null,
  status text not null default 'active',
  state jsonb not null default '{}'::jsonb,
  outcome jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);
create index if not exists idx_runs_user on runs(user_id);

create table if not exists encounters (
  id uuid primary key,
  run_id uuid not null references runs(id) on delete cascade,
  idx int not null,
  kind text not null,
  seed bigint not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists idx_encounters_run on encounters(run_id);

-- SEASONS / BATTLE PASS
create table if not exists seasons (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  theme text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  is_active boolean not null default false,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists battle_pass_levels (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null references seasons(id) on delete cascade,
  level int not null,
  xp_required int not null,
  free_reward jsonb not null default '{}'::jsonb,
  premium_reward jsonb not null default '{}'::jsonb,
  unique (season_id, level)
);

create table if not exists user_battle_pass (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  season_id uuid not null references seasons(id) on delete cascade,
  xp int not null default 0,
  premium boolean not null default false,
  claimed_free_up_to int not null default 0,
  claimed_premium_up_to int not null default 0,
  unique (user_id, season_id)
);

-- BOSSES
create table if not exists boss_templates (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  description text,
  base_hp bigint not null,
  base_attack int not null default 10,
  mechanics jsonb not null default '{}'::jsonb,
  art_url text,
  created_at timestamptz not null default now()
);

create table if not exists live_bosses (
  id uuid primary key default gen_random_uuid(),
  boss_template_id uuid not null references boss_templates(id) on delete restrict,
  season_id uuid references seasons(id) on delete set null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  max_hp bigint not null,
  hp bigint not null,
  state jsonb not null default '{}'::jsonb,
  status text not null default 'active',
  created_at timestamptz not null default now()
);
create index if not exists idx_live_bosses_active on live_bosses(status, starts_at);

create table if not exists boss_damage (
  id uuid primary key,
  live_boss_id uuid not null references live_bosses(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  damage bigint not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_boss_damage_boss on boss_damage(live_boss_id);
create index if not exists idx_boss_damage_user on boss_damage(user_id);

-- QUESTS / REWARDS
create table if not exists quest_templates (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  description text not null,
  cadence text not null check (cadence in ('daily','weekly')),
  goal jsonb not null default '{}'::jsonb,
  reward jsonb not null default '{}'::jsonb,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists user_quests (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  quest_template_id uuid not null references quest_templates(id) on delete cascade,
  day_key date not null,
  progress int not null default 0,
  completed_at timestamptz,
  claimed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, quest_template_id, day_key)
);

create table if not exists reward_claims (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  source text not null,
  source_id uuid,
  payload jsonb not null default '{}'::jsonb,
  claimed_at timestamptz not null default now()
);

-- GUILDS
create table if not exists guilds (
  id uuid primary key,
  name text not null,
  tag text not null,
  owner_user_id uuid not null references users(id) on delete restrict,
  join_code text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists guild_members (
  guild_id uuid not null references guilds(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  role text not null default 'member',
  joined_at timestamptz not null default now(),
  primary key (guild_id, user_id)
);
create index if not exists idx_guild_members_user on guild_members(user_id);

create table if not exists guild_activities (
  id uuid primary key default gen_random_uuid(),
  guild_id uuid not null references guilds(id) on delete cascade,
  user_id uuid references users(id) on delete set null,
  kind text not null,
  data jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists guild_boss_damage (
  id uuid primary key,
  guild_id uuid not null references guilds(id) on delete cascade,
  live_boss_id uuid not null references live_bosses(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  damage bigint not null,
  created_at timestamptz not null default now(),
  unique (guild_id, live_boss_id, user_id)
);

-- ECONOMY
create table if not exists currencies (
  code text primary key,
  name text not null,
  is_premium boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists wallets (
  user_id uuid not null references users(id) on delete cascade,
  currency_code text not null references currencies(code) on delete restrict,
  balance bigint not null default 0,
  primary key (user_id, currency_code)
);

create table if not exists transactions (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  currency_code text not null references currencies(code) on delete restrict,
  amount bigint not null,
  reason text not null,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_transactions_user on transactions(user_id);

create table if not exists shop_offers (
  id uuid primary key default gen_random_uuid(),
  season_id uuid references seasons(id) on delete set null,
  code text not null unique,
  title text not null,
  description text not null,
  price jsonb not null default '{}'::jsonb,
  rewards jsonb not null default '{}'::jsonb,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists purchases (
  id uuid primary key,
  user_id uuid not null references users(id) on delete cascade,
  offer_id uuid not null references shop_offers(id) on delete restrict,
  provider text not null,
  provider_payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  created_at timestamptz not null default now()
);
create index if not exists idx_purchases_user on purchases(user_id);

-- ANTI-CHEAT / LOGGING minimal
create table if not exists request_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete set null,
  route text not null,
  method text not null,
  ip inet,
  user_agent text,
  status int,
  took_ms int,
  created_at timestamptz not null default now()
);

create table if not exists suspicious_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete set null,
  kind text not null,
  severity smallint not null default 1,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

commit;