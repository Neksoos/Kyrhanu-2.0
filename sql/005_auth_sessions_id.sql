begin;

-- Ensure the `id` column on auth_sessions has a default UUID.
-- Earlier schema versions defined `id uuid` without a default, which caused
-- inserts without an explicit id to fail. This migration adds a default
-- expression using `gen_random_uuid()` so that inserts will automatically
-- generate a unique id when none is provided.

alter table if exists auth_sessions
  alter column id set default gen_random_uuid();

commit;