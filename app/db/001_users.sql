-- users
CREATE TABLE users (
  id UUID PRIMARY KEY,
  email VARCHAR(320) UNIQUE,
  password_hash VARCHAR(255),
  telegram_id BIGINT UNIQUE,
  telegram_username VARCHAR(64),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL
);

-- auth_sessions (refresh rotation)
CREATE TABLE auth_sessions (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  refresh_hash CHAR(64) NOT NULL,
  user_agent VARCHAR(255),
  ip VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL,
  rotated_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);
CREATE INDEX idx_auth_sessions_hash ON auth_sessions(refresh_hash);

-- wallet
CREATE TABLE wallet (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  chervontsi BIGINT NOT NULL DEFAULT 0,
  kleidony BIGINT NOT NULL DEFAULT 0
);

-- daily_rolls
CREATE TABLE daily_rolls (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  day_key DATE NOT NULL,
  selected_variant CHAR(1) NOT NULL DEFAULT 'A',
  roll_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  claimed_at TIMESTAMPTZ,
  pity_epic INT NOT NULL DEFAULT 0,
  pity_legendary INT NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, day_key)
);

-- tutorial_state
CREATE TABLE tutorial_state (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  step INT NOT NULL DEFAULT 1,
  completed BOOLEAN NOT NULL DEFAULT FALSE,
  flags JSONB NOT NULL DEFAULT '{}'::jsonb,
  rewards_claimed JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL
);

-- achievements (content)
CREATE TABLE achievements (
  id VARCHAR(32) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  category VARCHAR(32) NOT NULL,
  rarity VARCHAR(16) NOT NULL,
  hidden BOOLEAN NOT NULL DEFAULT FALSE,
  condition_json JSONB NOT NULL,
  reward_json JSONB NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- user_achievements
CREATE TABLE user_achievements (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  achievement_id VARCHAR(32) NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
  progress INT NOT NULL DEFAULT 0,
  claimed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (user_id, achievement_id)
);

-- heroes/items/item_instances/inventory/equipment/runs/bosses/guilds/quests/shop
-- (скелетні таблиці; контент зберігайте JSONB + інстанси окремо)
CREATE TABLE heroes (
  id VARCHAR(64) PRIMARY KEY,
  data JSONB NOT NULL
);

CREATE TABLE items (
  id VARCHAR(64) PRIMARY KEY,
  data JSONB NOT NULL
);

CREATE TABLE item_instances (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_id VARCHAR(64) NOT NULL REFERENCES items(id),
  rarity VARCHAR(16) NOT NULL,
  affixes JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE inventory (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  item_instance_id UUID NOT NULL REFERENCES item_instances(id) ON DELETE CASCADE,
  qty INT NOT NULL DEFAULT 1,
  PRIMARY KEY (user_id, item_instance_id)
);

CREATE TABLE equipment (
  user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  slots JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE runs (
  id UUID PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  mode VARCHAR(16) NOT NULL,
  state JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ
);

CREATE TABLE bosses (
  id VARCHAR(64) PRIMARY KEY,
  data JSONB NOT NULL
);

CREATE TABLE guilds (
  id UUID PRIMARY KEY,
  name VARCHAR(64) UNIQUE NOT NULL,
  tag VARCHAR(8) UNIQUE NOT NULL,
  join_code VARCHAR(16) UNIQUE NOT NULL,
  owner_user_id UUID NOT NULL REFERENCES users(id),
  data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE quests (
  id VARCHAR(64) PRIMARY KEY,
  data JSONB NOT NULL
);

CREATE TABLE shop (
  id VARCHAR(64) PRIMARY KEY,
  data JSONB NOT NULL
);