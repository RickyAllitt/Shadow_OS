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
    xp_required = db.Column(db.Integer, default=100)
    title = db.Column(db.String(50), default="E-Rank Hunter")
    
    # --- ECONOMY (The Reward) ---
    gold = db.Column(db.Integer, default=0) 
    last_weekly_reset = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_daily_reset = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # --- RECOVERY SYSTEM ---
    last_sleep_duration = db.Column(db.Float, default=0.0) # Hours slept
    sleep_streak = db.Column(db.Integer, default=0) # Days with 7+ hours
    
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
    
    # New Strict Penalty Fields
    consecutive_missed_days = db.Column(db.Integer, default=0)
    has_debuff = db.Column(db.Boolean, default=False)
    # If set, this is the deadline for the "System" penalty quest.
    penalty_deadline = db.Column(db.DateTime, nullable=True) 

class Quest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
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
    stock = db.Column(db.Integer, default=-1) # -1 = Infinite
