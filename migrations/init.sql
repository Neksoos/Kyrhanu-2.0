-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    auth_provider VARCHAR(20) DEFAULT 'email',
    provider_id VARCHAR(100),

    display_name VARCHAR(100),
    avatar_url VARCHAR(500),
    age_verified BOOLEAN DEFAULT FALSE,
    accepted_tos BOOLEAN DEFAULT FALSE,
    accepted_privacy BOOLEAN DEFAULT FALSE,

    chervontsi BIGINT DEFAULT 0,
    kleynodu INTEGER DEFAULT 0,

    level INTEGER DEFAULT 1,
    experience BIGINT DEFAULT 0,
    glory BIGINT DEFAULT 0,
    energy INTEGER DEFAULT 100,
    max_energy INTEGER DEFAULT 100,
    energy_last_refill TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    anomaly_score FLOAT DEFAULT 0.0,
    last_tap_at TIMESTAMP WITH TIME ZONE,
    tap_pattern_data JSONB DEFAULT '{}',

    referral_code VARCHAR(20) UNIQUE,
    referred_by INTEGER REFERENCES users(id),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    banned_at TIMESTAMP WITH TIME ZONE,
    ban_reason VARCHAR(255),

    role VARCHAR(20) DEFAULT 'player'
);

-- Basic indexes
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

-- Speed index (non-unique) for provider lookups
CREATE INDEX IF NOT EXISTS ix_users_provider ON users(auth_provider, provider_id);

-- ✅ Critical: prevent duplicate players for same provider id (telegram/web)
-- Works only when provider_id is not NULL.
CREATE UNIQUE INDEX IF NOT EXISTS ux_users_provider_notnull
ON users (auth_provider, provider_id)
WHERE provider_id IS NOT NULL;

-- Helpful leaderboard / activity indexes
CREATE INDEX IF NOT EXISTS ix_users_glory ON users(glory DESC);
CREATE INDEX IF NOT EXISTS ix_users_active ON users(last_active_at);
CREATE INDEX IF NOT EXISTS ix_users_referral ON users(referral_code);

-- Daily rolls
CREATE TABLE IF NOT EXISTS daily_rolls (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_date DATE NOT NULL,
    hero_name VARCHAR(100) NOT NULL,
    hero_archetype VARCHAR(50) NOT NULL,
    hero_stats JSONB NOT NULL,
    hero_level INTEGER DEFAULT 1,
    mound_story TEXT NOT NULL,
    amulet_name VARCHAR(100) NOT NULL,
    amulet_power INTEGER DEFAULT 0,
    choice_made VARCHAR(20),
    glory_delta INTEGER DEFAULT 0,
    chervontsi_earned BIGINT DEFAULT 0,
    result_text TEXT,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(user_id, day_date)
);

CREATE INDEX IF NOT EXISTS ix_daily_rolls_user_date ON daily_rolls(user_id, day_date);
CREATE INDEX IF NOT EXISTS ix_daily_rolls_date ON daily_rolls(day_date);

-- Guilds
CREATE TABLE IF NOT EXISTS guilds (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    tag VARCHAR(10),
    description TEXT,
    emblem_url VARCHAR(500),
    treasury_chervontsi BIGINT DEFAULT 0,
    boost_active_until TIMESTAMP WITH TIME ZONE,
    total_glory BIGINT DEFAULT 0,
    member_count INTEGER DEFAULT 0,
    max_members INTEGER DEFAULT 50,
    current_war_id INTEGER,
    war_wins INTEGER DEFAULT 0,
    war_losses INTEGER DEFAULT 0,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Guild members
CREATE TABLE IF NOT EXISTS guild_members (
    id SERIAL PRIMARY KEY,
    guild_id INTEGER NOT NULL REFERENCES guilds(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'member',
    contribution_points BIGINT DEFAULT 0,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_guild_members_guild ON guild_members(guild_id);
CREATE INDEX IF NOT EXISTS ix_guild_members_user ON guild_members(user_id);

-- Guild wars
CREATE TABLE IF NOT EXISTS guild_wars (
    id SERIAL PRIMARY KEY,
    season_id INTEGER NOT NULL,
    attacker_guild_id INTEGER NOT NULL REFERENCES guilds(id),
    defender_guild_id INTEGER NOT NULL REFERENCES guilds(id),
    status VARCHAR(20) DEFAULT 'active',
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
    attacker_score BIGINT DEFAULT 0,
    defender_score BIGINT DEFAULT 0,
    winner_guild_id INTEGER REFERENCES guilds(id),
    battle_log JSONB DEFAULT '[]'
);

-- Live bosses
CREATE TABLE IF NOT EXISTS live_bosses (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    image_url VARCHAR(500),
    total_health BIGINT NOT NULL,
    current_health BIGINT NOT NULL,
    damage_multiplier FLOAT DEFAULT 1.0,
    status VARCHAR(20) DEFAULT 'spawning',
    spawn_at TIMESTAMP WITH TIME ZONE NOT NULL,
    despawn_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reward_chervontsi_pool BIGINT DEFAULT 0,
    reward_kleynodu_pool INTEGER DEFAULT 0,
    special_drops JSONB DEFAULT '[]',
    top_attackers JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_live_bosses_status ON live_bosses(status);
CREATE INDEX IF NOT EXISTS ix_live_bosses_spawn ON live_bosses(spawn_at);

-- Boss attacks (high volume table)
CREATE TABLE IF NOT EXISTS boss_attacks (
    id BIGSERIAL PRIMARY KEY,
    boss_id INTEGER NOT NULL REFERENCES live_bosses(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    damage_dealt BIGINT NOT NULL,
    attack_type VARCHAR(20) DEFAULT 'normal',
    used_kleynodu INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_boss_attacks_boss ON boss_attacks(boss_id);
CREATE INDEX IF NOT EXISTS ix_boss_attacks_user ON boss_attacks(user_id);
CREATE INDEX IF NOT EXISTS ix_boss_attacks_boss_user ON boss_attacks(boss_id, user_id);
CREATE INDEX IF NOT EXISTS ix_boss_attacks_created ON boss_attacks(created_at);

-- Inventory
CREATE TABLE IF NOT EXISTS inventory_items (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_type VARCHAR(50) NOT NULL,
    item_key VARCHAR(100) NOT NULL,
    quantity INTEGER DEFAULT 1,
    quality INTEGER DEFAULT 1,
    acquired_from VARCHAR(50),
    acquired_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_equipped BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_inventory_user ON inventory_items(user_id);
CREATE INDEX IF NOT EXISTS ix_inventory_type ON inventory_items(item_type);

-- Shop purchases
CREATE TABLE IF NOT EXISTS shop_purchases (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    pack_key VARCHAR(50) NOT NULL,
    kleynodu_amount INTEGER NOT NULL,
    price_usd FLOAT NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(20) DEFAULT 'pending',
    payment_provider VARCHAR(50),
    client_ip VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_purchases_user ON shop_purchases(user_id);
CREATE INDEX IF NOT EXISTS ix_purchases_status ON shop_purchases(status);

-- Seasons
CREATE TABLE IF NOT EXISTS seasons (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    theme VARCHAR(50) NOT NULL,
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
    bp_base_price INTEGER DEFAULT 499,
    bp_premium_price INTEGER DEFAULT 999,
    is_active BOOLEAN DEFAULT TRUE
);

-- Live events
CREATE TABLE IF NOT EXISTS live_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    config JSONB DEFAULT '{}',
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    total_participants INTEGER DEFAULT 0,
    total_actions BIGINT DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_live_events_active ON live_events(is_active, ends_at);
CREATE INDEX IF NOT EXISTS ix_live_events_type ON live_events(event_type);

-- Analytics events (partitioned by time in production)
CREATE TABLE IF NOT EXISTS analytics_events (
    id BIGSERIAL PRIMARY KEY,
    event_name VARCHAR(100) NOT NULL,
    user_id INTEGER REFERENCES users(id),
    session_id VARCHAR(100),
    properties JSONB DEFAULT '{}',
    client_timestamp TIMESTAMP WITH TIME ZONE,
    ab_test_group VARCHAR(20),
    ab_test_id VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_analytics_name ON analytics_events(event_name);
CREATE INDEX IF NOT EXISTS ix_analytics_user ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS ix_analytics_session ON analytics_events(session_id);
CREATE INDEX IF NOT EXISTS ix_analytics_name_time ON analytics_events(event_name, created_at);
CREATE INDEX IF NOT EXISTS ix_analytics_ab ON analytics_events(ab_test_id, ab_test_group);

-- A/B test assignments
CREATE TABLE IF NOT EXISTS ab_test_assignments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    test_name VARCHAR(50) NOT NULL,
    group_name VARCHAR(20) NOT NULL,
    assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(user_id, test_name)
);

CREATE INDEX IF NOT EXISTS ix_ab_user ON ab_test_assignments(user_id);
CREATE INDEX IF NOT EXISTS ix_ab_test ON ab_test_assignments(test_name);