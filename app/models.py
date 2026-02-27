from .extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timezone
import hashlib
import os

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Player, int(user_id))

class Player(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    quests = db.relationship('Quest', backref='player', lazy=True, cascade="all, delete-orphan")
    
    # --- AUTHENTICATION ---
    password_hash = db.Column(db.String(64))
    salt = db.Column(db.String(32))

    def set_password(self, password):
        self.salt = os.urandom(16).hex()
        self.password_hash = hashlib.sha256((self.salt + password).encode('utf-8')).hexdigest()

    def check_password(self, password):
        return self.password_hash == hashlib.sha256((self.salt + password).encode('utf-8')).hexdigest()
    
    # --- PROGRESSION ---
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=0)
    job_class = db.Column(db.String(50), default='None')
    rank = db.Column(db.String(1), default='E') # New Rank System
    xp_required = db.Column(db.Integer, default=100)
    attribute_points = db.Column(db.Integer, default=0) # Unspent Ability Points

    # Replaced simple string with relationship, but keeping string for fallback or efficiency? 
    # Let's map it to the relationship now.
    current_title_id = db.Column(db.Integer, db.ForeignKey('title.id'), nullable=True)
    current_title = db.relationship('Title', foreign_keys=[current_title_id])
    
    # Many-to-Many for Unlocked Titles
    unlocked_titles = db.relationship('PlayerTitle', back_populates='player', lazy='dynamic', cascade="all, delete-orphan")
    
    # Helper to get display title
    @property
    def title_display(self):
        return self.current_title.name if self.current_title else "Noob"
    
    # --- ECONOMY (The Reward) ---
    gold = db.Column(db.Integer, default=0) 
    coins = db.Column(db.Integer, default=0) # Permanent
    last_weekly_reset = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_daily_reset = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # --- RECOVERY SYSTEM ---
    last_sleep_duration = db.Column(db.Float, default=0.0) # Hours slept
    last_sleep_log_date = db.Column(db.Date, nullable=True) # Track the last date (YYYY-MM-DD) sleep was logged
    sleep_streak = db.Column(db.Integer, default=0) # Days with 7+ hours
    daily_focus_duration = db.Column(db.Integer, default=0) # Minutes dedicated to "The Void" today
    
    # --- ONBOARDING & CORE ---
    setup_complete = db.Column(db.Boolean, default=False)
    penalty_description = db.Column(db.String(255), default="Survival") # Custom punishment
    penalty_detail = db.Column(db.Text, nullable=True) # Long-form description
    penalties_count = db.Column(db.Integer, default=0) # Track number of times in Penalty Zone

    
    # Condition affects XP gain. 
    # "Healthy" (100% XP), "Well Rested" (110% XP), "Exhausted" (50% XP)
    condition = db.Column(db.String(20), default="Normal")
    
    # --- ATTRIBUTES (Mapped to Life Areas) ---
    strength = db.Column(db.Integer, default=1)     # Gym / Diet adherence
    intelligence = db.Column(db.Integer, default=1) # Uni / Coding / Reading
    agility = db.Column(db.Integer, default=1)      # Speed of task completion / Procrastination killer
    sense = db.Column(db.Integer, default=1)        # Meditation / Socializing / Networking
    vitality = db.Column(db.Integer, default=1)     # Sleep / Health / Energy
    
    # --- THE PENALTY SYSTEM ---
    # If True, the UI turns RED and user cannot buy from shop until penalty is cleared.
    in_penalty_zone = db.Column(db.Boolean, default=False)
    # last_daily_reset defined above
    last_daily_bonus = db.Column(db.DateTime, nullable=True) # Track if +100g prompt claimed today
    consecutive_missed_days = db.Column(db.Integer, default=0)
    has_debuff = db.Column(db.Boolean, default=False)
    current_streak = db.Column(db.Integer, default=0)
    highest_streak = db.Column(db.Integer, default=0)
    # If set, this is the deadline for the "System" penalty quest.
    penalty_deadline = db.Column(db.DateTime, nullable=True) 

    # --- VACATION SYSTEM ---
    is_on_vacation = db.Column(db.Boolean, default=False)
    vacation_start_date = db.Column(db.DateTime, nullable=True)
    vacation_end_date = db.Column(db.DateTime, nullable=True)
    last_vacation_date = db.Column(db.DateTime, nullable=True)
    vacation_count = db.Column(db.Integer, default=0)

    # --- SETTINGS ---
    settings_audio = db.Column(db.Boolean, default=True)
    settings_music = db.Column(db.Boolean, default=True)
    settings_volume = db.Column(db.Float, default=0.5)

class Quest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True) # Optional detailed description
    rank = db.Column(db.String(10), default="E") 
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False) 
    
    # Rewards
    xp_reward = db.Column(db.Integer, default=10)
    gold_reward = db.Column(db.Integer, default=0)
    stat_reward = db.Column(db.String(20), nullable=True) # "STR", "INT"
    
    # Mechanics
    is_daily = db.Column(db.Boolean, default=False) # Resets every 24h
    is_completed = db.Column(db.Boolean, default=False)
    
    # If this is a Penalty Quest (e.g. "Run 10km"), it offers NO rewards, only survival.
    is_penalty = db.Column(db.Boolean, default=False) 
    
    # Failure Condition (for daily use)
    start_date = db.Column(db.DateTime, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Progress (0-100)
    progress = db.Column(db.Integer, default=0)
    
    priority = db.Column(db.Integer, default=4) # 1=Critical, 2=High, 3=Medium, 4=Low

    comments = db.relationship('QuestComment', backref='quest', lazy=True, cascade="all, delete-orphan")

class QuestComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quest_id = db.Column(db.Integer, db.ForeignKey('quest.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class RewardItem(db.Model):
    """ The Shop: Spending Gold on Real Life Luxuries """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # e.g. "1 Hour Video Games"
    cost = db.Column(db.Integer, nullable=False) # e.g. 50 Gold
    currency = db.Column(db.String(20), default='gold') # 'gold' or 'coins'
    stock = db.Column(db.Integer, default=-1) # -1 = Infinite
    
    # New Inventory Props
    item_type = db.Column(db.String(20), default='consumable') # 'consumable', 'equipment'
    stat_bonus = db.Column(db.String(20), nullable=True) # e.g. 'STR'
    stat_value = db.Column(db.Integer, default=0) # e.g. 2
    slot = db.Column(db.String(20), nullable=True) # 'weapon', 'armor', 'accessory'

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('reward_item.id'), nullable=False)
    is_equipped = db.Column(db.Boolean, default=False)
    acquired_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', backref=db.backref('inventory', lazy=True, cascade="all, delete-orphan"))
    item = db.relationship('RewardItem')

class PurchaseLog(db.Model):
    """ History of purchased items. Resets on weekly reset (Sunday). """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    item_name = db.Column(db.String(100), nullable=False) # Snapshot of name
    cost = db.Column(db.Integer, nullable=False) # Snapshot of cost
    purchased_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Claim Logic
    is_claimed = db.Column(db.Boolean, default=False)
    claimed_at = db.Column(db.DateTime, nullable=True)

    player = db.relationship('Player', backref=db.backref('purchase_history', cascade="all, delete-orphan"))

class DailySnapshot(db.Model):
    """ Tracks player progress over time for Analytics. """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    player = db.relationship('Player', backref=db.backref('snapshots', cascade="all, delete-orphan"))
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    
    level = db.Column(db.Integer)
    xp = db.Column(db.Integer)
    total_stats = db.Column(db.Integer) # Sum of stats
    quests_completed = db.Column(db.Integer, default=0) # Heatmap Data
    
    # Snapshot of core stats
    strength = db.Column(db.Integer)
    intelligence = db.Column(db.Integer)
    agility = db.Column(db.Integer)
    vitality = db.Column(db.Integer)
    sense = db.Column(db.Integer)
    
class Title(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    buff_description = db.Column(db.String(100), nullable=True) # e.g. "ALL STATS +1" (Visual for now)
    
    # Unlock Logic
    unlock_condition = db.Column(db.String(20), nullable=False) # 'level', 'streak_sleep', 'streak_daily', 'manual'
    unlock_value = db.Column(db.Integer, default=0) # e.g. Level 10
    
class PlayerTitle(db.Model):
    """ Association table for unlocked titles """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    title_id = db.Column(db.Integer, db.ForeignKey('title.id'))
    unlocked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    player = db.relationship('Player', back_populates='unlocked_titles')
    title = db.relationship('Title')

class Shadow(db.Model):
    """ 
    The Shadow Army. 
    S-Rank Quests that have been completed and 'Arised'.
    Provide permanent passive buffs.
    """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    original_quest_name = db.Column(db.String(100), nullable=False)
    rank = db.Column(db.String(10), default='S')
    extracted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Buff Logic
    buff_type = db.Column(db.String(50), default='ALL_STATS') # 'ALL_STATS', 'STR', etc.
    buff_value = db.Column(db.Integer, default=1) # +1% or +1 Flat
    
    player = db.relationship('Player', backref=db.backref('shadows', lazy=True, cascade="all, delete-orphan"))

class Notification(db.Model):
    """
    System Notifications (Alerts, Reminders, Warnings).
    """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(20), default="info") # info, warning, error, success
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', backref=db.backref('notifications', lazy='dynamic', cascade="all, delete-orphan"))
