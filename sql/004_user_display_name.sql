begin;

-- Ensure the `display_name` column exists on `users` table with a sane default.
-- Earlier versions of the schema did not include this field, which caused runtime
-- errors when the application attempted to select or insert `display_name`.
-- The default value mirrors the one used in the application code.

alter table if exists users
  add column if not exists display_name text not null default 'Player';

commit;