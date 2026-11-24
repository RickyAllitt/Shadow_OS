from .extensions import db, login_manager
from flask_login import UserMixin
from datetime import datetime, timezone
import hashlib
import hmac
from werkzeug.security import generate_password_hash, check_password_hash

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Player, int(user_id))

class Player(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    quests = db.relationship('Quest', backref='player', lazy=True, cascade="all, delete-orphan")
    
    # --- AUTHENTICATION ---
    # Werkzeug hash string (algorithm + salt embedded). Legacy accounts store a bare
    # SHA-256 hex digest plus a separate `salt`; they are upgraded on next login.
    password_hash = db.Column(db.String(255))
    salt = db.Column(db.String(32))  # Legacy only; None for upgraded accounts

    def set_password(self, password):
        from flask import current_app, has_app_context
        # Werkzeug's default (scrypt) in production; tests may pick a cheaper method via config
        method = current_app.config.get('PASSWORD_HASH_METHOD') if has_app_context() else None
        self.password_hash = generate_password_hash(password, method=method) if method else generate_password_hash(password)
        self.salt = None

    def _is_legacy_hash(self):
        return bool(self.salt) and self.password_hash is not None and '$' not in self.password_hash

    def check_password(self, password):
        if not self.password_hash or password is None:
            return False
        if self._is_legacy_hash():
            legacy = hashlib.sha256((self.salt + password).encode('utf-8')).hexdigest()
            return hmac.compare_digest(self.password_hash, legacy)
        return check_password_hash(self.password_hash, password)

    def needs_rehash(self):
        return self._is_legacy_hash()
    
    # --- PROGRESSION ---
    level = db.Column(db.Integer, default=1)
    xp = db.Column(db.Integer, default=0)
    job_class = db.Column(db.String(50), default='None')
    rank = db.Column(db.String(1), default='E') # New Rank System
    xp_required = db.Column(db.Integer, default=160)  # = services.calculate_xp_required(1)
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
    condition = db.Column(db.String(20), default="NORMAL")
    
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

    # --- ACCOUNTABILITY (soft penalties) ---
    xp_debt = db.Column(db.Integer, default=0)              # owed XP: new XP pays this first
    streak_freezes = db.Column(db.Integer, default=0)       # earned every 7-day streak, max 2
    hardcore = db.Column(db.Boolean, default=False)         # opt-in: failed penalties cost a level
    hardcore_since = db.Column(db.DateTime, nullable=True)

    # --- CLASS SKILL (see app/progression.py) ---
    skill_ready_at = db.Column(db.DateTime, nullable=True)  # cooldown end (UTC); None = ready
    skill_armed = db.Column(db.Boolean, default=False)      # Vanish / Insight / Fortify shield waiting to trigger
    specialization = db.Column(db.String(20), nullable=True) # Second Awakening branch (Lv 50), e.g. 'Blade'
    ascensions = db.Column(db.Integer, default=0)            # prestige: times reset from Lv 100 to Lv 1

    # --- VACATION SYSTEM ---
    is_on_vacation = db.Column(db.Boolean, default=False)
    vacation_start_date = db.Column(db.DateTime, nullable=True)
    vacation_end_date = db.Column(db.DateTime, nullable=True)
    last_vacation_date = db.Column(db.DateTime, nullable=True)
    vacation_count = db.Column(db.Integer, default=0)

    # --- LOCALE & REMINDERS ---
    timezone = db.Column(db.String(50), default='Europe/Madrid')  # IANA name; daily reset is 01:00 local
    reminder_time = db.Column(db.String(5), default='18:00')     # 'HH:MM' local, or None/'' = off

    # --- SETTINGS ---
    settings_audio = db.Column(db.Boolean, default=True)
    settings_music = db.Column(db.Boolean, default=True)
    settings_volume = db.Column(db.Float, default=0.5)
    settings_popups = db.Column(db.Boolean, default=True)


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

    # Measured quests (optional): e.g. target 50, unit "pushups". Amounts are logged as ActivityEvents
    # (kind 'metric'); the quest completes when the logged total reaches the target.
    metric_target = db.Column(db.Float, nullable=True)
    metric_unit = db.Column(db.String(20), nullable=True)

    @property
    def is_measured(self):
        return bool(self.metric_target and self.metric_target > 0 and self.metric_unit)

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
    rarity = db.Column(db.String(12), nullable=True)   # loot only: common / rare / epic / legendary
    set_name = db.Column(db.String(40), nullable=True) # legendary set pieces (see app/loot.py)

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

    # Shadow Army grades (Lv 25): a shadow assigned to a quest grows each time you complete it
    assigned_quest_id = db.Column(db.Integer, nullable=True)
    kills = db.Column(db.Integer, default=0)
    
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

class PushSubscription(db.Model):
    """
    Stores browser Web Push subscription data for sending background notifications.
    """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    endpoint = db.Column(db.Text, nullable=False, unique=True)
    p256dh = db.Column(db.String(255), nullable=False)
    auth = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', backref=db.backref('push_subscriptions', lazy='dynamic', cascade="all, delete-orphan"))

class ActivityEvent(db.Model):
    """
    Append-only log of league-relevant activity. Weekly leagues, rank caps and rival records
    are computed from it, so nothing has to be reset when a new week starts.

    kind: 'quest' | 'focus' | 'daily_bonus' -> points (percent of a level earned)
          'daily_result'                     -> success (were all dailies done that day)
          'rank_claim'                       -> rank ('A' / 'S' slot used)
          'league_seen'                      -> weekly results popup shown
          'effort'                           -> stat + units (Life Balance input), rank, quest_id
          'metric'                           -> value logged toward a measured quest (quest_id)
          'sleep'                            -> value = hours slept
    """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False, index=True)
    occurred_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    week_start = db.Column(db.Date, nullable=False, index=True)  # Monday of the game week
    kind = db.Column(db.String(20), nullable=False)
    points = db.Column(db.Float, default=0.0)
    minutes = db.Column(db.Integer, default=0)
    success = db.Column(db.Boolean, nullable=True)
    rank = db.Column(db.String(2), nullable=True)
    stat = db.Column(db.String(3), nullable=True)
    units = db.Column(db.Float, default=0.0)
    value = db.Column(db.Float, nullable=True)
    quest_id = db.Column(db.Integer, nullable=True, index=True)  # no FK: history outlives deleted quests

    player = db.relationship('Player', backref=db.backref('activity', lazy='dynamic', cascade="all, delete-orphan"))


class Rivalry(db.Model):
    """ One chosen rival per player for the weekly head-to-head duel. """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False, unique=True)
    rival_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', foreign_keys=[player_id],
                             backref=db.backref('rivalry', uselist=False, cascade="all, delete-orphan"))
    rival = db.relationship('Player', foreign_keys=[rival_id],
                            backref=db.backref('rivaled_by', cascade="all, delete-orphan"))


class PersonalReward(db.Model):
    """ A real-life reward a player defines and prices themselves (bought with Gold). """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False, index=True)
    name = db.Column(db.String(60), nullable=False)
    cost = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', backref=db.backref('personal_rewards', lazy=True, cascade="all, delete-orphan"))


class Raid(db.Model):
    """ A shared goal everyone contributes to (e.g. 100 km run together in a month). """
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    target = db.Column(db.Float, nullable=False)
    stat = db.Column(db.String(3), default='STR')            # Life Balance area contributions count toward
    created_by = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ends_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(12), default='active')      # active | completed | failed | cancelled
    completed_at = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('Player', foreign_keys=[created_by],
                              backref=db.backref('raids_created', lazy=True))  # deleting a player nulls created_by
    contributions = db.relationship('RaidContribution', backref='raid', lazy=True, cascade="all, delete-orphan",
                                    order_by='RaidContribution.created_at.desc()')

    @property
    def total(self):
        return round(sum(c.amount for c in self.contributions), 2)

    @property
    def percent(self):
        return min(100, int(100 * self.total / self.target)) if self.target else 0


class RaidContribution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    raid_id = db.Column(db.Integer, db.ForeignKey('raid.id'), nullable=False, index=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    player = db.relationship('Player', backref=db.backref('raid_contributions', lazy=True, cascade="all, delete-orphan"))


class Kudos(db.Model):
    """ A reaction from one hunter on another's S-rank clear (an 'effort' ActivityEvent). """
    __table_args__ = (db.UniqueConstraint('event_id', 'from_player_id', name='uq_kudos_once'),)
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('activity_event.id'), nullable=False, index=True)
    from_player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    emoji = db.Column(db.String(8), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    event = db.relationship('ActivityEvent', backref=db.backref('kudos', lazy=True, cascade="all, delete-orphan"))
    from_player = db.relationship('Player', backref=db.backref('kudos_given', lazy=True, cascade="all, delete-orphan"))


class Gate(db.Model):
    """
    A timed challenge (see app/gates.py). Kinds: 'gate' (weekly, Lv 15), 'red' (rare, Lv 30),
    'exam' (Rank Assessment, Lv 40+) and 'awakening' (Second Awakening, Lv 50).
    Objectives are measured from the activity log between entered_at and expires_at.
    """
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False, index=True)
    kind = db.Column(db.String(12), nullable=False, default='gate')
    grade = db.Column(db.String(2), nullable=False, default='C')
    title = db.Column(db.String(80), nullable=False)
    objectives = db.Column(db.Text, nullable=False)          # JSON list of objective dicts
    target_rank = db.Column(db.String(2), nullable=True)     # exams: the rank being tested for
    week_start = db.Column(db.Date, nullable=False)
    appeared_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    enter_by = db.Column(db.DateTime, nullable=True)         # None = can be entered any time
    entered_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(12), nullable=False, default='waiting')
    # waiting -> active -> cleared -> claimed | failed ; waiting -> missed | declined
    finished_at = db.Column(db.DateTime, nullable=True)

    player = db.relationship('Player', backref=db.backref('gates', lazy='dynamic', cascade="all, delete-orphan"))
