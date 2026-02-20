-- 090_add_player_actions.sql
--
-- Migration to create the player_actions table used for auditing actions
-- performed by players, administrators or the system.  Each row
-- represents a single event and stores structured context as JSON.

BEGIN;

CREATE TABLE IF NOT EXISTS player_actions (
    id SERIAL PRIMARY KEY,
    tg_id BIGINT NOT NULL,
    action_type TEXT NOT NULL,
    actor_type TEXT NOT NULL DEFAULT 'player',
    context JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_player_actions_tg_id ON player_actions(tg_id);
CREATE INDEX IF NOT EXISTS ix_player_actions_action_type ON player_actions(action_type);
CREATE INDEX IF NOT EXISTS ix_player_actions_created_at ON player_actions(created_at);

COMMIT;
