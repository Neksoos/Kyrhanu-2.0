-- DB_CLEANUP_CANDIDATES.sql
-- Date: 2026-02-20
--
-- IMPORTANT:
-- 1) DO NOT run blindly in production.
-- 2) First run the verification SELECTs.
-- 3) Prefer RENAMING to __deprecated__ first. DROP only after a few deploy cycles.

BEGIN;

-- =========================
-- Candidate #1: item_equipment_stats
-- Evidence:
--  - Mentioned in migration 074 as "старий експеримент"
--  - Not referenced by backend code queries
-- =========================
SELECT to_regclass('public.item_equipment_stats') AS exists_item_equipment_stats;
-- If exists, check if it has rows:
-- SELECT COUNT(*) FROM item_equipment_stats;

-- Safe step: rename (keeps data)
DO $$
BEGIN
  IF to_regclass('public.item_equipment_stats') IS NOT NULL THEN
    EXECUTE 'ALTER TABLE item_equipment_stats RENAME TO __deprecated__item_equipment_stats__20260220';
  END IF;
END $$;

-- Optional later (after verification):
-- DROP TABLE IF EXISTS __deprecated__item_equipment_stats__20260220 CASCADE;


-- =========================
-- Candidate #2 (RISK): zastavy
-- Evidence:
--  - No backend SQL queries reference the table name
--  - Code appears to use forts/* tables for "застави" gameplay
-- RISK: table may still contain legacy data used manually / externally.
-- =========================
SELECT to_regclass('public.zastavy') AS exists_zastavy;
-- If exists, inspect:
-- \d+ zastavy
-- SELECT COUNT(*) FROM zastavy;
-- Check dependencies:
-- SELECT conname, conrelid::regclass, confrelid::regclass FROM pg_constraint
--  WHERE confrelid = 'zastavy'::regclass OR conrelid='zastavy'::regclass;

-- Safe step: rename first (ONLY after you confirm it's unused):
-- DO $$
-- BEGIN
--   IF to_regclass('public.zastavy') IS NOT NULL THEN
--     EXECUTE 'ALTER TABLE zastavy RENAME TO __deprecated__zastavy__20260220';
--   END IF;
-- END $$;

-- Optional later:
-- DROP TABLE IF EXISTS __deprecated__zastavy__20260220 CASCADE;


-- =========================
-- Candidate #3 (UNKNOWN): forum_category_requests
-- There is schema/migration support, but no query usage yet.
-- Keep it unless you confirm you don't need category request workflow.
-- =========================
SELECT to_regclass('public.forum_category_requests') AS exists_forum_category_requests;
-- Safe rename (ONLY if you confirm feature is not used):
-- DO $$
-- BEGIN
--   IF to_regclass('public.forum_category_requests') IS NOT NULL THEN
--     EXECUTE 'ALTER TABLE forum_category_requests RENAME TO __deprecated__forum_category_requests__20260220';
--   END IF;
-- END $$;

COMMIT;
