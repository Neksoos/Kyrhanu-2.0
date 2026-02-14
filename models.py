"""
SQLAlchemy models for Cursed Mounds.
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, 
    BigInteger, Float, JSON, Text, Index, Enum, UniqueConstraint
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base
import enum


class UserRole(str, enum.Enum):
    PLAYER = "player"
    MODERATOR = "moderator"
    ADMIN = "admin"


class AuthProvider(str, enum.Enum):
    TELEGRAM = "telegram"
    EMAIL = "email"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, index=True, nullable=True)
    email = Column(String(255), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)  # For email auth
    auth_provider = Column(Enum(AuthProvider), default=AuthProvider.EMAIL)
    provider_id = Column(String(100), nullable=True)  # telegram_id or other
    
    # Profile
    display_name = Column(String(100), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    age_verified = Column(Boolean, default=False)
    accepted_tos = Column(Boolean, default=False)
    accepted_privacy = Column(Boolean, default=False)
    
    # Currencies
    chervontsi = Column(BigInteger, default=0)  # Soft currency
    kleynodu = Column(Integer, default=0)  # Premium currency (hard cap int)
    
    # Progression
    level = Column(Integer, default=1)
    experience = Column(BigInteger, default=0)
    glory = Column(BigInteger, default=0)  # Reputation/achievement score
    energy = Column(Integer, default=100)
    max_energy = Column(Integer, default=100)
    energy_last_refill = Column(DateTime(timezone=True), server_default=func.now())
    
    # Anti-cheat
    anomaly_score = Column(Float, default=0.0)  # 0-100, auto-ban at 100
    last_tap_at = Column(DateTime(timezone=True), nullable=True)
    tap_pattern_data = Column(JSON, default=dict)  # For behavioral analysis
    
    # Social
    referral_code = Column(String(20), unique=True, index=True)
    referred_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_active_at = Column(DateTime(timezone=True), server_default=func.now())
    banned_at = Column(DateTime(timezone=True), nullable=True)
    ban_reason = Column(String(255), nullable=True)
    
    # Relationships
    referrals = relationship("User", backref="referrer", remote_side=[id])
    guild_membership = relationship("GuildMember", uselist=False, back_populates="user")
    inventory_items = relationship("InventoryItem", back_populates="user")
    daily_rolls = relationship("DailyRoll", back_populates="user")
    
    __table_args__ = (
        Index('ix_users_glory', 'glory', postgresql_using='desc'),
        Index('ix_users_active', 'last_active_at'),
    )


class DailyRoll(Base):
    __tablename__ = "daily_rolls"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day_date = Column(DateTime(timezone=True), nullable=False, index=True)
    
    # Hero data (snapshot)
    hero_name = Column(String(100), nullable=False)
    hero_archetype = Column(String(50), nullable=False)
    hero_stats = Column(JSON, nullable=False)  # {strength, cunning, endurance, fate}
    hero_level = Column(Integer, default=1)
    
    # Session data
    mound_story = Column(Text, nullable=False)
    amulet_name = Column(String(100), nullable=False)
    amulet_power = Column(Integer, default=0)
    
    # Results
    choice_made = Column(String(20), nullable=True)  # accept, redeem, ignore
    glory_delta = Column(Integer, default=0)
    chervontsi_earned = Column(BigInteger, default=0)
    result_text = Column(Text, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="daily_rolls")
    
    __table_args__ = (
        UniqueConstraint('user_id', 'day_date', name='uq_daily_roll_user_date'),
        Index('ix_daily_rolls_date', 'day_date'),
    )


class Guild(Base):
    __tablename__ = "guilds"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    tag = Column(String(10), nullable=True)  # [KURGAN]
    description = Column(Text, nullable=True)
    emblem_url = Column(String(500), nullable=True)
    
    # Resources
    treasury_chervontsi = Column(BigInteger, default=0)
    boost_active_until = Column(DateTime(timezone=True), nullable=True)
    
    # Stats
    total_glory = Column(BigInteger, default=0)
    member_count = Column(Integer, default=0)
    max_members = Column(Integer, default=50)
    
    # War status
    current_war_id = Column(Integer, ForeignKey("guild_wars.id"), nullable=True)
    war_wins = Column(Integer, default=0)
    war_losses = Column(Integer, default=0)
    
    # Creator
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    members = relationship("GuildMember", back_populates="guild")
    current_war = relationship("GuildWar", foreign_keys=[current_war_id])


class GuildMember(Base):
    __tablename__ = "guild_members"
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(Integer, ForeignKey("guilds.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    role = Column(String(20), default="member")  # member, officer, leader
    contribution_points = Column(BigInteger, default=0)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    
    guild = relationship("Guild", back_populates="members")
    user = relationship("User", back_populates="guild_membership")


class GuildWar(Base):
    __tablename__ = "guild_wars"
    
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    attacker_guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=False)
    defender_guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=False)
    
    status = Column(String(20), default="active")  # active, ended, cancelled
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ends_at = Column(DateTime(timezone=True), nullable=False)
    
    attacker_score = Column(BigInteger, default=0)
    defender_score = Column(BigInteger, default=0)
    winner_guild_id = Column(Integer, ForeignKey("guilds.id"), nullable=True)
    
    # Live battle data (JSON for real-time updates)
    battle_log = Column(JSON, default=list)


class LiveBoss(Base):
    __tablename__ = "live_bosses"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    
    # Stats
    total_health = Column(BigInteger, nullable=False)
    current_health = Column(BigInteger, nullable=False)
    damage_multiplier = Column(Float, default=1.0)
    
    # Status
    status = Column(String(20), default="spawning")  # spawning, active, defeated, escaped
    spawn_at = Column(DateTime(timezone=True), nullable=False)
    despawn_at = Column(DateTime(timezone=True), nullable=False)
    
    # Rewards
    reward_chervontsi_pool = Column(BigInteger, default=0)
    reward_kleynodu_pool = Column(Integer, default=0)
    special_drops = Column(JSON, default=list)  # Item IDs
    
    # Participants (denormalized for speed)
    top_attackers = Column(JSON, default=list)  # [{user_id, damage, rank}]
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BossAttack(Base):
    __tablename__ = "boss_attacks"
    
    id = Column(BigInteger, primary_key=True)  # Big int for high volume
    boss_id = Column(Integer, ForeignKey("live_bosses.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    damage_dealt = Column(BigInteger, nullable=False)
    attack_type = Column(String(20), default="normal")  # normal, critical, special
    used_kleynodu = Column(Integer, default=0)  # Paid attacks
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_boss_attacks_boss_user', 'boss_id', 'user_id'),
        Index('ix_boss_attacks_created', 'created_at'),
    )


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    item_type = Column(String(50), nullable=False)  # artifact, skin, boost, material
    item_key = Column(String(100), nullable=False)  # Reference to item definition
    quantity = Column(Integer, default=1)
    quality = Column(Integer, default=1)  # 1-5 stars
    
    # Metadata
    acquired_from = Column(String(50), nullable=True)  # drop, purchase, gift, craft
    acquired_at = Column(DateTime(timezone=True), server_default=func.now())
    is_equipped = Column(Boolean, default=False)
    
    user = relationship("User", back_populates="inventory_items")


class ShopPurchase(Base):
    __tablename__ = "shop_purchases"
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    pack_key = Column(String(50), nullable=False)  # starter, warrior, etc.
    kleynodu_amount = Column(Integer, nullable=False)
    price_usd = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    
    # Payment status
    status = Column(String(20), default="pending")  # pending, completed, failed, refunded
    payment_provider = Column(String(50), nullable=True)  # stripe, paypal, crypto
    
    # Metadata
    client_ip = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)


class Season(Base):
    __tablename__ = "seasons"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)  # "Купала 2024", "Зажинки"
    theme = Column(String(50), nullable=False)  # kupala, harvest, winter
    
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    
    # Battle Pass
    bp_base_price = Column(Integer, default=499)  # kleynodu
    bp_premium_price = Column(Integer, default=999)
    
    is_active = Column(Boolean, default=True)


class LiveEvent(Base):
    __tablename__ = "live_events"
    
    id = Column(Integer, primary_key=True)
    event_type = Column(String(50), nullable=False)  # double_drop, boss_rush, etc.
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    config = Column(JSON, default=dict)  # Event-specific parameters
    
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Tracking
    total_participants = Column(Integer, default=0)
    total_actions = Column(BigInteger, default=0)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    
    id = Column(BigInteger, primary_key=True)
    event_name = Column(String(100), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(100), nullable=True, index=True)
    
    # Event data
    properties = Column(JSON, default=dict)
    client_timestamp = Column(DateTime(timezone=True), nullable=True)
    
    # A/B testing
    ab_test_group = Column(String(20), nullable=True)  # control, variant_a, etc.
    ab_test_id = Column(String(50), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('ix_analytics_events_name_time', 'event_name', 'created_at'),
        Index('ix_analytics_events_ab', 'ab_test_id', 'ab_test_group'),
    )


class ABTestAssignment(Base):
    __tablename__ = "ab_test_assignments"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    test_name = Column(String(50), nullable=False)
    group_name = Column(String(20), nullable=False)  # control, variant_a, variant_b
    
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('user_id', 'test_name', name='uq_ab_assignment'),
    )