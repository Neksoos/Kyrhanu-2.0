begin;

create extension if not exists pgcrypto;
create extension if not exists citext;

-- USERS
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  telegram_id bigint unique,
  telegram_username text,
  -- Human-friendly name for display purposes. Defaults to 'Player' for new rows.
  display_name text not null default 'Player',
  email citext unique,
  password_hash text,
  created_at timestamptz not null default now(),
  last_login timestamptz,
  linked_at timestamptz,
  flags jsonb not null default '{}'::jsonb
);

-- інші таблиці лишились без змін…