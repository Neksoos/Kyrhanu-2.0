ALTER TABLE players
  ADD COLUMN IF NOT EXISTS equipped_frame_sku text,
  ADD COLUMN IF NOT EXISTS equipped_name_sku  text;