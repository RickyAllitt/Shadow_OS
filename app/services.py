from app.extensions import db
from app.models import Player, RewardItem, Quest, Title, PlayerTitle, Inventory, Shadow, DailySnapshot

# --- CONDITION (sleep) ---
CONDITION_WELL_RESTED = "WELL RESTED"
CONDITION_NORMAL = "NORMAL"
CONDITION_TIRED = "TIRED"
CONDITION_XP_MULTIPLIERS = {CONDITION_WELL_RESTED: 1.10, CONDITION_TIRED: 0.5}

def condition_xp_multiplier(player):
    return CONDITION_XP_MULTIPLIERS.get((player.condition or '').upper(), 1.0)

def recover_condition(player):
    """'Full recovery' (level up / daily bonus) clears fatigue but keeps a Well Rested buff."""
    if (player.condition or '').upper() != CONDITION_WELL_RESTED:
        player.condition = CONDITION_NORMAL

# --- TITLES ---
# Single source of truth for titles. `buff` keys:
#   xp / coins: multiplier bonus (0.05 = +5%)   all: flat bonus to every stat
#   stat: (player_field, flat bonus)
TITLE_DEFINITIONS = [
    {'name': "E-Rank Hunter", 'description': "Every hunter starts somewhere.",
     'unlock_condition': 'level', 'unlock_value': 1, 'buff': {}},
    {'name': "The Awakened", 'description': "Reach Level 10.",
     'unlock_condition': 'level', 'unlock_value': 10, 'buff': {'xp': 0.05}},
    {'name': "Wolf Slayer", 'description': "Reach Level 25.",
     'unlock_condition': 'level', 'unlock_value': 25, 'buff': {'stat': ('strength', 3)}},
    {'name': "Demon Hunter", 'description': "Reach Level 50.",
     'unlock_condition': 'level', 'unlock_value': 50, 'buff': {'xp': 0.10}},
    {'name': "Iron Will", 'description': "Complete all dailies 7 days in a row.",
     'unlock_condition': 'streak_daily', 'unlock_value': 7, 'buff': {'all': 1}},
    {'name': "The One Who Overcame Adversity", 'description': "Complete all dailies 30 days in a row.",
     'unlock_condition': 'streak_daily', 'unlock_value': 30, 'buff': {'all': 3}},
    {'name': "Well-Rested Sage", 'description': "Sleep 7.5h+ for 7 nights in a row.",
     'unlock_condition': 'streak_sleep', 'unlock_value': 7, 'buff': {'stat': ('vitality', 2)}},
    {'name': "Scholar", 'description': "Reach 50 base Intelligence.",
     'unlock_condition': 'stat_intelligence', 'unlock_value': 50, 'buff': {'xp': 0.05}},
    {'name': "Titan's Grip", 'description': "Reach 50 base Strength.",
     'unlock_condition': 'stat_strength', 'unlock_value': 50, 'buff': {'stat': ('strength', 5)}},
    {'name': "Coin Hoarder", 'description': "Hold 5,000 Coins at once.",
     'unlock_condition': 'coins', 'unlock_value': 5000, 'buff': {'coins': 0.05}},
]
_TITLE_BUFFS = {t['name']: t['buff'] for t in TITLE_DEFINITIONS}
_STAT_LABELS = {'strength': 'STR', 'intelligence': 'INT', 'agility': 'AGI', 'vitality': 'VIT', 'sense': 'SNS'}

def describe_title_buff(buff):
    parts = []
    if buff.get('xp'): parts.append(f"XP +{int(buff['xp'] * 100)}%")
    if buff.get('coins'): parts.append(f"COINS +{int(buff['coins'] * 100)}%")
    if buff.get('all'): parts.append(f"ALL STATS +{buff['all']}")
    if buff.get('stat'):
        field, value = buff['stat']
        parts.append(f"{_STAT_LABELS.get(field, field.upper())} +{value}")
    return ", ".join(parts) or None

def active_title_buff(player):
    title = player.current_title
    return _TITLE_BUFFS.get(title.name, {}) if title else {}

def xp_multiplier(player):
    """Sleep condition x equipped title XP bonus x Hardcore bonus."""
    hardcore = 1 + HARDCORE_XP_BONUS if getattr(player, 'hardcore', False) else 1
    return condition_xp_multiplier(player) * (1 + active_title_buff(player).get('xp', 0)) * hardcore

def coin_multiplier(player):
    return 1 + active_title_buff(player).get('coins', 0)

def seed_titles():
    for t in TITLE_DEFINITIONS:
        row = Title.query.filter_by(name=t['name']).first()
        if not row:
            row = Title(name=t['name'])
            db.session.add(row)
        row.description = t['description']
        row.buff_description = describe_title_buff(t['buff'])
        row.unlock_condition = t['unlock_condition']
        row.unlock_value = t['unlock_value']

def seed_database():
    """Populates the database with initial game state (titles + shop stock)."""
    seed_titles()

    # Create Default Shop Items (Rewards)
    # Define all desired items
    desired_items = [
        # Gold Rewards (Real Life)
        {'name': "Night Out with Friends", 'cost': 600, 'stock': -1, 'currency': 'gold', 'item_type': 'consumable', 'stat_bonus': None, 'stat_value': 0, 'slot': None},
        
        # Coin Rewards (System Gear)
        # Weapons
        {'name': "Novice Dagger", 'cost': 100, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'STR', 'stat_value': 2, 'slot': 'weapon'},
        {'name': "Demon's Dagger", 'cost': 1200, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'STR', 'stat_value': 10, 'slot': 'weapon'},
        
        # Armor
        {'name': "Iron Shield", 'cost': 100, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'VIT', 'stat_value': 2, 'slot': 'accessory'},
        {'name': "Shadow Hood", 'cost': 300, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'AGI', 'stat_value': 3, 'slot': 'head'},
        {'name': "Hunter's Vest", 'cost': 500, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'VIT', 'stat_value': 5, 'slot': 'body'},
        {'name': "Assassin's Gloves", 'cost': 250, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'SNS', 'stat_value': 3, 'slot': 'accessory'},
        
        # Accessories
        {'name': "Apprentice Grimoire", 'cost': 100, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'INT', 'stat_value': 2, 'slot': 'accessory'},
        {'name': "Ring of Clarity", 'cost': 400, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'INT', 'stat_value': 5, 'slot': 'accessory'},
        
        # Coin Consumables
        {'name': "Elixir of Life", 'cost': 100, 'stock': -1, 'currency': 'coins', 'item_type': 'consumable', 'stat_bonus': None, 'stat_value': 0, 'slot': None},
        
        # Mid-Tier Gear (800-1200 Range)
        {'name': "High Orc's Helm", 'cost': 900, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'VIT', 'stat_value': 6, 'slot': 'head'},
        {'name': "Warden's Necklace", 'cost': 1000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'SNS', 'stat_value': 6, 'slot': 'accessory'},
        {'name': "Blue Venom Fang", 'cost': 1100, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'STR', 'stat_value': 8, 'slot': 'weapon'},
        
        # New High-Tier Gear (Expansion Phase 2)
        {'name': "Shadow Boots", 'cost': 600, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'AGI', 'stat_value': 5, 'slot': 'accessory'},
        {'name': "Knight Killer", 'cost': 2500, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'STR', 'stat_value': 15, 'slot': 'weapon'},
        {'name': "Baruka's Dagger", 'cost': 2000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'AGI', 'stat_value': 10, 'slot': 'weapon'},
        {'name': "Cloak of Shadows", 'cost': 1500, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'SNS', 'stat_value': 10, 'slot': 'accessory'},
        {'name': "Orb of Avarice", 'cost': 3000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'INT', 'stat_value': 20, 'slot': 'accessory'},
        {'name': "Red Knight's Helmet", 'cost': 1800, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'VIT', 'stat_value': 10, 'slot': 'head'},
        
        # S-Rank Endgame Gear (Years 1-2 Targets)
        {'name': "Demon King's Longsword", 'cost': 7500, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'STR', 'stat_value': 40, 'slot': 'weapon'},
        {'name': "Monarch's Domain", 'cost': 8500, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'INT', 'stat_value': 50, 'slot': 'accessory'},
        {'name': "Armor of the Sun", 'cost': 6000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'VIT', 'stat_value': 35, 'slot': 'body'},
        {'name': "Kamish's Wrath", 'cost': 15000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'STR', 'stat_value': 60, 'slot': 'weapon'},
        {'name': "Eyes of the Ruler", 'cost': 7000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'SNS', 'stat_value': 45, 'slot': 'head'},
        {'name': "Wings of the Void", 'cost': 10000, 'stock': 1, 'currency': 'coins', 'item_type': 'equipment', 'stat_bonus': 'AGI', 'stat_value': 50, 'slot': 'accessory'},
    ]

    for item_data in desired_items:
        if not RewardItem.query.filter_by(name=item_data['name']).first():
            new_item = RewardItem(
                name=item_data['name'],
                cost=item_data['cost'],
                stock=item_data['stock'],
                currency=item_data['currency'],
                item_type=item_data['item_type'],
                stat_bonus=item_data['stat_bonus'],
                stat_value=item_data['stat_value'],
                slot=item_data['slot']
            )
            db.session.add(new_item)
            print(f">> Created Shop Item: {item_data['name']}")

    print(">> Shop Stock Verified.")

    db.session.commit()

from datetime import datetime, timedelta, timezone
import pytz

GAME_TIMEZONE = pytz.timezone('Europe/Madrid')
RESET_HOUR = 1  # 1:00 AM Europe/Madrid

DEFAULT_TIMEZONE = 'Europe/Madrid'


def player_tz(player):
    """The player's own timezone (daily reset is 01:00 there). Falls back to GAME_TIMEZONE."""
    name = getattr(player, 'timezone', None) or DEFAULT_TIMEZONE
    try:
        return pytz.timezone(name)
    except pytz.UnknownTimeZoneError:
        return GAME_TIMEZONE


def is_valid_timezone(name):
    return bool(name) and name in pytz.all_timezones_set


def get_latest_daily_reset_time(dt_game=None, tz=None):
    """
    Returns the most recent 1:00 AM reset datetime in `tz` (default GAME_TIMEZONE).
    If it's currently before 1:00 AM, the most recent reset was yesterday at 1:00 AM.
    If it's at or after 1:00 AM, the most recent reset was today at 1:00 AM.
    """
    tz = tz or GAME_TIMEZONE
    if dt_game is None:
        dt_game = datetime.now(timezone.utc).astimezone(tz)
    else:
        dt_game = dt_game.astimezone(tz)
    if dt_game.hour < RESET_HOUR:
        base_date = dt_game.date() - timedelta(days=1)
    else:
        base_date = dt_game.date()
    return tz.localize(datetime.combine(base_date, datetime.min.time()).replace(hour=RESET_HOUR))

def check_weekly_reset(player):
    """
    Checks if the weekly reset (Sunday night / Monday morning at 1:00 AM) has passed since the last reset.
    If so, halves Gold (saving is possible, hoarding is not).
    Returns True if reset occurred.
    """
    if not player.last_weekly_reset:
        player.last_weekly_reset = datetime.now(timezone.utc)
        db.session.commit()
        return False

    if player.is_on_vacation:
        return False

    # Convert everything to Game Time for logic
    now_utc = datetime.now(timezone.utc)
    tz = player_tz(player)
    now_game = now_utc.astimezone(tz)

    # Reset is Sunday night / Monday 01:00:00 in the player's timezone
    # Logic: Get start of current week (Monday) in Game Time at RESET_HOUR (01:00).
    # If last reset < start of current week at RESET_HOUR, trigger reset.
    
    today_game = now_game.date()
    start_of_week = today_game - timedelta(days=today_game.weekday()) # Monday
    reset_threshold = tz.localize(datetime.combine(start_of_week, datetime.min.time()).replace(hour=RESET_HOUR))
    
    # If Monday 1:00 AM has not arrived yet, we are still in Sunday night
    if now_game < reset_threshold:
        return False
    
    # Convert player's last reset (stored as UTC usually or unaware) to Game Time aware
    last_reset_utc = player.last_weekly_reset
    if last_reset_utc.tzinfo is None:
        last_reset_utc = last_reset_utc.replace(tzinfo=timezone.utc)
    
    if last_reset_utc < reset_threshold:
        player.weekly_gold_before = player.gold  # transient, for the reset message
        player.gold = (player.gold or 0) // 2    # halve: keeps spending pressure but allows saving
        player.last_weekly_reset = now_utc
        db.session.commit()
        return True
        
    return False

import os
import json
from pywebpush import webpush, WebPushException
from app.models import PushSubscription

def trigger_push_notification(player_id, title, message, url="/"):
    """
    Sends a Web Push Notification to all devices registered by the player.
    Logs failures to the Notification table for live debugging.
    """
    from app.models import PushSubscription, Notification
    
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY")

    if not vapid_private_key:
        print(">> Web Push Error: VAPID_PRIVATE_KEY not configured.")
        return

    subscriptions = PushSubscription.query.filter_by(player_id=player_id).all()
    if not subscriptions:
        return

    payload = json.dumps({
        "title": title,
        "message": message,
        "url": url
    })

    log_msgs = []
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {
                        "p256dh": sub.p256dh,
                        "auth": sub.auth
                    }
                },
                data=payload,
                vapid_private_key=vapid_private_key,
                vapid_claims={"sub": "mailto:admin@shadow-os.onrender.com"},
                ttl=86400
            )
            # Success - intentionally not logging to avoid user spam
        except WebPushException as ex:
            error_status = getattr(ex.response, 'status_code', 'Unknown')
            log_msgs.append(f"Push FAILED [{error_status}]: {str(ex)}")
            print(">> Web Push Failed!", ex)
            # Remove expired subscription if the service reports it no longer valid (410 Gone or 404 Not Found)
            if error_status in [410, 404]:
                db.session.delete(sub)
                db.session.commit()
        except Exception as e:
            log_msgs.append(f"Push UNEXPECTED ERROR: {str(e)}")
            print(">> Unexpected Web Push Error:", e)

    # Save all push attempts as a direct system log for the user to debug on mobile
    if log_msgs:
        debug_msg = " | ".join(log_msgs)
        new_log = Notification(
            player_id=player_id,
            message=f"PUSH DEBUG: {debug_msg} -- Payload: {title}",
            category="system_popup"
        )
        db.session.add(new_log)
        db.session.commit()

# --- LEVELLING ECONOMY ---
# Gentle polynomial curve + fixed rewards: numbers stay readable (Lv 100 needs ~38k XP, not ~390 billion)
# and the same action earns the same XP at every level. A typical active day (4 dailies + bonus,
# 1.5h focus, a C and a B quest) is ~2,000 XP: about a level a day early on, ~18 days per level in
# the 90s, roughly 2 years to Lv 100.
XP_CURVE_BASE = 100
XP_CURVE_FACTOR = 60
XP_CURVE_EXPONENT = 1.4

RANK_XP = {'E': 40, 'D': 80, 'C': 150, 'B': 300, 'A': 600, 'S': 1000}  # non-daily S = instant level up
DAILY_BONUS_XP = 500          # all dailies done
FOCUS_XP_PER_MINUTE = 10      # 600 XP per hour of deep work
RANK_GOLD_COINS = {'E': (0, 0), 'D': (0, 0), 'C': (0, 0), 'B': (50, 15), 'A': (100, 30), 'S': (250, 100)}
# Big one-off quests stay meaningful at every level: non-daily B/A pay the higher of their fixed XP
# or this share of the current level (A-ranks are also capped at 3/week). League points use the
# fixed RANK_XP only, so higher levels gain no league advantage.
RANK_LEVEL_SHARE = {'B': 0.05, 'A': 0.15}

# --- ACCOUNTABILITY ---
XP_DEBT_SHARE = 0.5        # failed penalty (normal mode): owe half a level, capped at one level
HARDCORE_XP_BONUS = 0.10   # opt-in Hardcore: +10% XP, but a failed penalty costs one level
FREEZE_EVERY_DAYS = 7      # earn a streak freeze every 7-day streak...
MAX_STREAK_FREEZES = 2     # ...and bank at most this many


def calculate_xp_required(level):
    """ XP needed to go from `level` to `level + 1`: 100 + 60 * level^1.4, rounded to 10. """
    return int(round(XP_CURVE_BASE + XP_CURVE_FACTOR * max(1, level) ** XP_CURVE_EXPONENT, -1))


def calculate_rewards(rank, player_level=None, is_daily=False):
    """
    Returns (XP, Gold, Coins) for a quest rank. Fixed per rank, except non-daily B/A quests which pay
    at least RANK_LEVEL_SHARE of the current level's requirement (rounded to 10).
    """
    gold, coins = RANK_GOLD_COINS.get(rank, (0, 0))
    xp = RANK_XP.get(rank, 0)
    if player_level and not is_daily and rank in RANK_LEVEL_SHARE:
        xp = max(xp, int(round(RANK_LEVEL_SHARE[rank] * calculate_xp_required(player_level), -1)))
    return xp, gold, coins


def add_xp(player, amount):
    """
    Credit XP, paying off any XP debt first. Returns (credited_to_bar, paid_to_debt).
    Also records the payment on the player (transient) so routes can report it.
    """
    amount = max(0, int(amount))
    paid = min(player.xp_debt or 0, amount)
    if paid:
        player.xp_debt -= paid
        player.debt_paid = getattr(player, 'debt_paid', 0) + paid
    player.xp += amount - paid
    return amount - paid, paid


def apply_xp_debt(player):
    """Failed penalty in normal mode: owe half a level (total debt capped at one full level)."""
    added = int(round(player.xp_required * XP_DEBT_SHARE, -1))
    player.xp_debt = min((player.xp_debt or 0) + added, player.xp_required)
    return player.xp_debt


def set_hardcore(player, enabled):
    if enabled:
        if player.hardcore:
            return False, "Hardcore mode is already active."
        if player.in_penalty_zone:
            return False, "Clear the Penalty Zone before entering Hardcore mode."
        player.hardcore, player.hardcore_since = True, datetime.now(timezone.utc)
        db.session.commit()
        return True, "💀 HARDCORE MODE ENGAGED. +10% XP. A failed penalty now costs a level."
    if not player.hardcore:
        return False, "Hardcore mode is not active."
    player.hardcore, player.hardcore_since = False, None
    db.session.commit()
    return True, "Hardcore mode disabled. Your Hardcore streak has ended."

def process_level_up(player):
    """ Handles level up logic, stats, class evolution, rank up, and titles. """
    initial_level = player.level
    while player.xp >= player.xp_required:
        player.level += 1
        player.xp -= player.xp_required
        player.xp_required = calculate_xp_required(player.level)
        
        # Level Up Stat Bonus: +1 All Stats + Full Recovery
        player.strength += 1
        player.intelligence += 1
        player.agility += 1
        player.vitality += 1
        player.sense += 1
        recover_condition(player) # Full Recovery
        
        # Check Evolution immediately on level up
        evolved, new_class = check_class_evolution(player)
        if evolved:
             print(f">> CLASS EVOLUTION: {player.name} became {new_class}!")
             player.just_evolved = new_class
             
        # Check Rank Up
        ranked_up, new_rank = check_player_rank_up(player)
        if ranked_up:
             print(f">> RANK UP: {player.name} is now Rank {new_rank}!")
             player.just_ranked_up = new_rank
             
    # Check titles on every completion (level up or streak)
    check_title_unlocks(player)

    # Transient (not persisted): lets routes describe the level up
    player.levels_gained = getattr(player, 'levels_gained', 0) + (player.level - initial_level)
    return player.level > initial_level

def process_quest_completion(player, quest):
    """ Handles all rewards, stats, and level up logic. """
    if quest.is_completed:
        return # Already done
        
    quest.is_completed = True
    quest.completed_at = datetime.now(timezone.utc)
    
    if quest.is_daily:
        quest.progress = 0
    
    # 1. Calculate Rewards (fixed per rank; non-daily B/A scale with level)
    base_xp, base_gold, base_coins = calculate_rewards(quest.rank, player.level, quest.is_daily)
    league_xp = RANK_XP.get(quest.rank, 0)
    if quest.gold_reward and quest.gold_reward > 0:
        base_gold = quest.gold_reward

    # Dailies earn their rank XP (so every daily counts) but no Gold/Coins: those come from the
    # all-dailies bonus. Penalty quests give nothing: they only clear the penalty.
    if quest.is_daily:
        base_gold = base_coins = 0
    if quest.is_penalty:
        base_xp = base_gold = base_coins = league_xp = 0
    instant_level_up = quest.rank == 'S' and not quest.is_penalty and not quest.is_daily
    if instant_level_up:
        base_xp = 0  # the reward is the level itself
        
    # INT Multiplier: +5% per 10 INT
    int_multiplier = 1 + (player.intelligence / 10) * 0.05
    xp_gain = int(base_xp * int_multiplier)
    
    # Sleep condition (Well Rested +10% / Tired -50%) and equipped title bonus
    xp_gain = int(xp_gain * xp_multiplier(player))

    # AGI Multiplier: +5% Coins per 10 AGI
    agi_multiplier = 1 + (player.agility / 10) * 0.05
    coin_gain = int(base_coins * agi_multiplier * coin_multiplier(player))
    
    # --- CLASS BONUSES ---
    # Assassin: +10% Coins
    if player.job_class == 'Assassin':
        coin_gain = int(coin_gain * 1.10)
        
    # Mage: +10% XP
    if player.job_class == 'Mage':
        xp_gain = int(xp_gain * 1.10)

    add_xp(player, xp_gain)
    player.gold += base_gold
    player.coins += coin_gain
    # S-RANK REWARD: INSTANT LEVEL UP
    if instant_level_up:
        # Fill XP bar to max immediately so that they just level up ONE time
        player.xp = max(player.xp, player.xp_required)
        print(f">> S-RANK BONUS: Instant Level Up for {player.name}")

    from app.league import record_points, S_RANK_LEAGUE_XP
    from app.kpi import record_quest_effort
    # League points use base XP (before INT/class/title/sleep bonuses) so the league stays fair
    record_points(player, 'quest', S_RANK_LEAGUE_XP if instant_level_up else league_xp)
    record_quest_effort(player, quest)  # Life Balance: dailies count too

    # 2. Apply Stat Buffs (Only for Rank B+ and NOT Daily/Penalty)
    if quest.rank in ['B', 'A', 'S'] and not quest.is_daily and not quest.is_penalty:
        _apply_quest_stat_reward(player, quest)
    
    # 3. Daily Completion Bonus (+100 Gold + 50 XP)
    daily_bonus = False
    if quest.is_daily:
        daily_bonus = _check_and_apply_daily_bonus(player)

    # 4. Level Up Logic (Moved after all XP gains)
    initial_level = player.level
    process_level_up(player)

    # 5. Penalty Clearance
    if quest.is_penalty:
        player.in_penalty_zone = False
        player.consecutive_missed_days = 0 # Mercy reset
        player.has_debuff = False
        
    # 6. Heatmap Activity Tracking
    today_date = datetime.now(timezone.utc).date()
    # Find or Create Snapshot for TODAY to track activity in real-time
    existing = DailySnapshot.query.filter_by(player_id=player.id, date=today_date).first()
    
    current_total_stats = sum(calculate_total_stats(player).values())
    
    if not existing:
        existing = DailySnapshot(
            player_id=player.id,
            date=today_date,
            quests_completed=0
        )
        db.session.add(existing)
        print(f">> Created Daily Snapshot for {today_date}")
    else:
        print(f">> Updating Daily Snapshot for {today_date}")
        
    # Update Stats
    existing.level = player.level
    existing.xp = player.xp
    existing.total_stats = current_total_stats
    existing.strength = player.strength
    existing.intelligence = player.intelligence
    existing.agility = player.agility
    existing.vitality = player.vitality
    existing.sense = player.sense
        
    existing.quests_completed += 1
        
    db.session.commit()
    
    # Notify high-value achievements via Web Push
    if quest.rank in ['S', 'A'] and not quest.is_daily and not quest.is_penalty:
        msg = f"Quest '{quest.title}' Completed!"
        if player.level > initial_level:
             msg += " LEVEL UP!"
        trigger_push_notification(player.id, "High Rank Quest Cleared", msg)
        
    can_arise = (quest.rank == 'S')
    return xp_gain, base_gold, coin_gain, (player.level > initial_level), daily_bonus, can_arise

VALID_STATS = ('STR', 'INT', 'AGI', 'VIT', 'SNS')
_STAT_ALIASES = {'SEN': 'SNS', 'SENSE': 'SNS'}

def normalize_stat(stat, default='INT'):
    """Maps any stat code (incl. legacy 'SEN') to one of VALID_STATS."""
    if not stat:
        return default
    code = str(stat).strip().upper()
    code = _STAT_ALIASES.get(code, code)
    return code if code in VALID_STATS else default

def _apply_quest_stat_reward(player, quest):
    """Helper to apply stat rewards from a quest."""
    stat = normalize_stat(quest.stat_reward, default=None)
    amount = 1
    if quest.rank == 'A':
        amount = 2
    elif quest.rank == 'S':
        amount = 3
        
    if stat == 'STR': player.strength += amount
    elif stat == 'INT': player.intelligence += amount
    elif stat == 'AGI': player.agility += amount
    elif stat == 'VIT': player.vitality += amount
    elif stat == 'SNS': player.sense += amount

def _check_and_apply_daily_bonus(player):
    """Checks if all dailies are done. Applies bonus if eligible. Clears penalty if active."""
    # Check if ALL dailies are now completed
    dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
    all_completed = all(q.is_completed for q in dailies)
    
    bonus_granted = False
    
    if all_completed:
        # 1. Daily Bonus Logic
        now_utc = datetime.now(timezone.utc)
        tz = player_tz(player)
        now_game = now_utc.astimezone(tz)

        # Check against the latest 1:00 AM reset in the player's timezone
        latest_reset_game = get_latest_daily_reset_time(now_game, tz)
        
        last_bonus = player.last_daily_bonus
        if last_bonus and last_bonus.tzinfo is None:
            last_bonus = last_bonus.replace(tzinfo=timezone.utc)
            
        # Optimization: We only care if last_bonus was BEFORE latest_reset_utc.
        latest_reset_utc = latest_reset_game.astimezone(timezone.utc)
        
        if not last_bonus or last_bonus < latest_reset_utc:
            # All-dailies bonus (fixed)
            bonus_xp = DAILY_BONUS_XP
            add_xp(player, bonus_xp)
            
            player.gold += 100 
            player.coins += 50 
            player.attribute_points += 3 # Daily Ability Points
            recover_condition(player) # Status Recovery
            
            player.last_daily_bonus = now_utc
            # Transient (not persisted): lets the route report the real amounts
            player.daily_bonus_rewards = {'xp': bonus_xp, 'gold': 100, 'coins': 50, 'points': 3}
            from app.league import record_points
            record_points(player, 'daily_bonus', bonus_xp)
            print(f">> Daily Bonus Granted for {player.name}")
            bonus_granted = True

            # New: Push Notification for Daily Completion
            trigger_push_notification(
                player.id, 
                "Daily Routine Complete", 
                "All tasks finished! Bonus rewarded: +100G, +50C, +XP."
            )

        # 2. Penalty Redemption Logic
        # Independent of whether bonus was just granted or claimed previously.
        if player.consecutive_missed_days > 0:
            print(f">> REDEMPTION: {player.name} cleared penalty debt via hard work.")
            player.consecutive_missed_days = 0
            player.has_debuff = False
            player.in_penalty_zone = False

    return bonus_granted

def _create_daily_snapshot(player):
    """ Creates a historical record of the player's status for today (yesterday effectively). """
    # We record the state as it was "yesterday" (the day being closed out). 
    # Or simplified: Record CURRENT state as the snapshot for YESTERDAY'S DATE?
    # Actually, we are running this at the START of a new day, so we are snapshotting the result of the previous day.
    # Let's verify if a snapshot already defaults to 'now', which is 'today'. 
    # We want the date to be the day that just finished.
    
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    
    # Check if snapshot exists for yesterday
    snap = DailySnapshot.query.filter_by(player_id=player.id, date=yesterday).first()
    
    # Calculate stats for the snapshot
    current_total_stats = sum(calculate_total_stats(player).values())
    
    if not snap:
        snap = DailySnapshot(
            player_id=player.id,
            date=yesterday,
            quests_completed=0 # Should have been zero if not created by activity
        )
        db.session.add(snap)
        print(f">> Created Daily Snapshot for {yesterday}")
    else:
        print(f">> Updating Daily Snapshot for {yesterday}")

    # Update/Finalize Stats
    snap.level = player.level
    snap.xp = player.xp
    snap.total_stats = current_total_stats
    snap.strength = player.strength
    snap.intelligence = player.intelligence
    snap.agility = player.agility
    snap.vitality = player.vitality
    snap.sense = player.sense

def check_daily_reset(player):
    """
    Checks if a new day has started.
    Implements the "System" Penalty Protocol: Debuff -> Lockout -> Level Down.
    """
    if not player.last_daily_reset:
        player.last_daily_reset = datetime.now(timezone.utc)
        db.session.commit()
        return False
        
    if player.is_on_vacation:
        # Check if vacation has naturally ended
        now = datetime.now(timezone.utc)
        if player.vacation_end_date and now >= player.vacation_end_date.replace(tzinfo=timezone.utc):
            end_vacation(player)
            return True, ["VACATION ENDED. WELCOME BACK, HUNTER."] # Reset might occur after vacation ends
        return False, []

    now_utc = datetime.now(timezone.utc)
    now = now_utc
    tz = player_tz(player)
    now_game = now_utc.astimezone(tz)
    latest_reset_game = get_latest_daily_reset_time(now_game, tz)
    
    # We compare everything in UTC to be safe with DB; the reset point is 1:00 AM in the player's timezone.
    latest_reset_utc = latest_reset_game.astimezone(timezone.utc)
    
    if player.last_daily_reset.tzinfo is None:
         player.last_daily_reset = player.last_daily_reset.replace(tzinfo=timezone.utc)
    
    # Catch-up Loop: Process EACH missed day
    messages = []
    days_processed = 0
    reset_occurred = False
    
    while player.last_daily_reset < latest_reset_utc:
        # Advance last_reset by 1 day
        # We process the day that just ended (last_daily_reset -> last_daily_reset + 1 day)
        # But efficiently, we just check "did we miss yesterday?"
        
        # Actually, simpler:
        # If last_reset was 2023-01-01 and today is 2023-01-03.
        # We need to process failure for 01-01 to 01-02, and 01-02 to 01-03.
        
        # Target for this iteration is the end of the "current" recorded day
        # We will simulate the check happening at 1:00 AM of the next day
        
        # 1. Capture Analytics Snapshot (for the day being closed)
        _create_daily_snapshot(player)
        
        # 2. Reset Daily Variables
        player.daily_focus_duration = 0 
        
        dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
        total_dailies = len(dailies)
        completed_dailies = sum(1 for q in dailies if q.is_completed)
        
        # If we are catching up (i.e. this loop is running for a past date), the user definitely didn't log in to complete them
        # UNLESS they were completed before the user went offline? 
        # Actually, 'dailies' query gives current state. 
        # If I completed dailies on Jan 1st, then didn't login Jan 2nd.
        # Loop 1 (Jan 1->2): Dailies are complete. Success. Reset them.
        # Loop 2 (Jan 2->3): Dailies are now False (reset in Loop 1). Failure.
        
        success = (total_dailies == 0) or (completed_dailies == total_dailies)
        if total_dailies:
            from app.league import record
            record(player, 'daily_result', success=success, when=player.last_daily_reset)
        
        if not success and (player.streak_freezes or 0) > 0:
            # STREAK FREEZE: the bad day is forgiven (no streak loss, debuff or penalty progress)
            player.streak_freezes -= 1
            messages.append(f"❄️ STREAK FREEZE USED: your {player.current_streak}-day streak is safe "
                            f"({player.streak_freezes} left).")
            trigger_push_notification(player.id, "Streak Freeze used",
                                      f"You missed your dailies, but a freeze protected your {player.current_streak}-day streak.")
        elif not success:
            # FAILURE LOGIC
            player.current_streak = 0
            player.consecutive_missed_days += 1
            player.penalties_count += 1
            
            effective_missed_days = player.consecutive_missed_days
            if player.job_class == 'Tank':
                effective_missed_days = max(0, effective_missed_days - 1)
            
            # Stage 1: Debuff
            if effective_missed_days == 1:
                player.has_debuff = True
                messages.append("SYSTEM ALERT: Missed Dailies detected. Physical Condition degraded.")
                trigger_push_notification(
                    player.id,
                    "SYSTEM ALERT",
                    "Dailies missed. Your physical condition has degraded (Stat Debuff Applied)."
                )
            elif effective_missed_days > 1:
                player.has_debuff = True
            
            # Stage 2: Penalty Zone
            if effective_missed_days == 2:
                player.in_penalty_zone = True
                messages.append("SYSTEM ALERT: PENALTY ZONE ENTERED.")
                
                existing_penalty = Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).first()
                if not existing_penalty:
                    # Calculate deadline: next 1:00 AM in the player's timezone
                    # If we are in catch-up loop, we effectively set it relative to "now" since they just logged in?
                    # Yes, give them until the upcoming 1:00 AM to fix it.
                    # Localize the next reset explicitly (adding 24h to an aware time drifts an hour across DST)
                    deadline_game = tz.localize(datetime.combine(
                        latest_reset_game.date() + timedelta(days=1), datetime.min.time()).replace(hour=RESET_HOUR))
                    deadline_utc = deadline_game.astimezone(timezone.utc)

                    penalty = Quest(
                        title=f"PENALTY: {player.penalty_description}", 
                        description=player.penalty_detail,
                        rank="A", # CHANGED FROM S
                        player_id=player.id,
                        xp_reward=0, 
                        gold_reward=0,
                        stat_reward="VIT",
                        is_penalty=True,
                        due_date=deadline_utc
                    )
                    db.session.add(penalty)
                    trigger_push_notification(
                        player.id,
                        "SYSTEM ALERT",
                        "PENALTY ZONE ENTERED. Complete the Survival Quest immediately."
                    )
            elif effective_missed_days > 2:
                 player.in_penalty_zone = True

            # Stage 3: Level Down
            # Only level down if there are NO active penalties, OR if the active penalty deadline has strictly passed.
            active_penalty = Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).first()
            can_level_down = True
            
            if active_penalty and active_penalty.due_date:
                # Compare in UTC
                penalty_due_utc = active_penalty.due_date
                if penalty_due_utc.tzinfo is None:
                    penalty_due_utc = penalty_due_utc.replace(tzinfo=timezone.utc)
                
                # If we haven't reached the deadline, DO NOT level down yet.
                if now_utc < penalty_due_utc:
                    can_level_down = False
                    
            if effective_missed_days >= 3 and can_level_down:
                if player.hardcore:
                    # Opt-in Hardcore: lose exactly one level (no stat loss)
                    if player.level > 1:
                        player.level -= 1
                        player.xp = 0
                        player.xp_required = calculate_xp_required(player.level)
                    messages.append(f"💀 HARDCORE: PENALTY FAILED. LEVEL LOST (now Lv {player.level}).")
                else:
                    # Normal mode: XP debt instead of losing levels or stats
                    debt = apply_xp_debt(player)
                    messages.append(f"PENALTY FAILED: XP DEBT {debt:,} XP. New XP pays it off first.")

                # Clear penalty
                for p_quest in Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).all():
                    p_quest.is_completed = True
                    p_quest.completed_at = now

                player.consecutive_missed_days = 0
                player.in_penalty_zone = False
                player.has_debuff = False

        else:
            # SUCCESS LOGIC
            player.consecutive_missed_days = 0
            player.has_debuff = False
            
            player.current_streak += 1
            if player.current_streak > player.highest_streak:
                player.highest_streak = player.current_streak
            if player.current_streak % FREEZE_EVERY_DAYS == 0 and (player.streak_freezes or 0) < MAX_STREAK_FREEZES:
                player.streak_freezes = (player.streak_freezes or 0) + 1
                messages.append(f"❄️ STREAK FREEZE EARNED for a {player.current_streak}-day streak "
                                f"({player.streak_freezes}/{MAX_STREAK_FREEZES}).")
            
        # Reset Dailies (Prepare for next day iteration)
        for quest in dailies:
            quest.is_completed = False
            quest.progress = 0 # Bug fix: Ensure progress bars are emptied
            
        # Move last_daily_reset forward by 1 day
        player.last_daily_reset += timedelta(days=1)
        reset_occurred = True
        days_processed += 1
        
        # Safety Break (max 30 days catchup to prevent infinite loops or timeout)
        if days_processed > 30:
            player.last_daily_reset = now
            messages.append("SYSTEM: Hibernation detected. Time sync protocol engaged.")
            break
            
    if reset_occurred:
        player.last_daily_reset = now # Align exact time
        db.session.commit()
        return True, messages
        
    return False, []

def get_categorized_quests(player_id):
    """
    Fetches and categorizes quests for the dashboard.
    Returns: (dailies, scheduled, backlog)
    """
    all_quests = Quest.query.filter_by(player_id=player_id).all()
    
    dailies = []
    scheduled = []
    backlog = []
    for q in all_quests:
        # Filter logic:
        # Completed non-dailies are hidden.
        if q.is_completed and not q.is_daily:
            continue
            
        if q.is_daily:
            dailies.append(q)
        elif q.is_penalty:
            # Penalties go to scheduled or top of list? Let's put them in Scheduled for now with urgent marking?
            # Or simplified: Put usage in scheduled.
            scheduled.insert(0, q) # Urgent!
        elif q.start_date or q.due_date:
            scheduled.append(q)
        else:
            backlog.append(q)
            
    # Sort Scheduled: First by start_date/due_date, then by priority (1=Critical, 4=Low)
    # We use a large date for tasks without dates to put them at the end.
    def get_sort_key(q):
        dt = q.start_date or q.due_date
        if dt is None:
            return datetime.max.replace(tzinfo=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    scheduled.sort(key=lambda x: (get_sort_key(x), x.priority))
    
    
    return dailies, scheduled, backlog

def check_title_unlocks(player):
    """ Checks and unlocks titles based on player stats/milestones. """
    # 1. Get all titles NOT yet unlocked by player
    # subquery for titles player uses
    unlocked_ids = [t.title_id for t in player.unlocked_titles]
    potential_titles = Title.query.filter(Title.id.notin_(unlocked_ids)).all()
    
    new_unlocks = []
    
    for t in potential_titles:
        unlocked = False
        
        if t.unlock_condition == 'level':
            if player.level >= t.unlock_value:
                unlocked = True
                
        elif t.unlock_condition == 'streak_daily':
            if max(player.current_streak or 0, player.highest_streak or 0) >= t.unlock_value:
                unlocked = True

        elif t.unlock_condition == 'streak_sleep':
            if (player.sleep_streak or 0) >= t.unlock_value:
                unlocked = True

        # Stat Unlocks
        elif t.unlock_condition.startswith('stat_'):
            stat_name = t.unlock_condition.split('_')[1] # e.g. 'strength' from 'stat_strength'
            # getattr(player, 'strength')
            if hasattr(player, stat_name):
                current_val = getattr(player, stat_name)
                if current_val >= t.unlock_value:
                    unlocked = True
                    
        # Wealth Unlocks
        elif t.unlock_condition == 'gold':
            if player.gold >= t.unlock_value:
                unlocked = True
        elif t.unlock_condition == 'coins':
            if player.coins >= t.unlock_value:
                unlocked = True
                
        if unlocked:
            assoc = PlayerTitle(player=player, title=t)
            db.session.add(assoc)
            new_unlocks.append(t.name)
            if player.current_title is None:
                player.current_title = t  # Auto-equip the first title earned

    if new_unlocks:
        # Transient (not persisted): routes read this to announce unlocks
        player.new_titles = getattr(player, 'new_titles', []) + new_unlocks
        db.session.commit()
    
    return new_unlocks

def equip_title_service(player, title_id):
    """ Equips a title if unlocked. """
    association = PlayerTitle.query.filter_by(player_id=player.id, title_id=title_id).first()
    if not association:
        return False, "Title not unlocked."
    
    title = db.session.get(Title, title_id)
    if not title:
        return False, "Title not found."
        
    player.current_title = title
    db.session.commit()
    return True, f"Equipped title: {title.name}"

# Class -> (next class, level required). Base classes come from the Job Change trial (app/job_trial.py).
CLASS_EVOLUTIONS = {
    "Assassin": ("Shadow Assassin", 20),
    "Mage": ("Archmage", 20),
    "Tank": ("Juggernaut", 20),
    "Shadow Assassin": ("Shadow Lord", 40),
    "Archmage": ("Spellweaver", 40),
    "Juggernaut": ("Iron Fortress", 40),
    "Shadow Lord": ("Nightwalker", 60),
    "Spellweaver": ("Arcane Sage", 60),
    "Iron Fortress": ("Titan", 60),
    "Nightwalker": ("Eclipse Bringer", 80),
    "Arcane Sage": ("Void Walker", 80),
    "Titan": ("World Guardian", 80),
    "Eclipse Bringer": ("Monarch of Shadows", 100),
    "Void Walker": ("Monarch of Scrolls", 100),
    "World Guardian": ("Monarch of Iron", 100),
}

def class_evolution_path(job_class):
    """[(class, level), ...] for every evolution after job_class."""
    path = []
    while job_class in CLASS_EVOLUTIONS:
        job_class, level = CLASS_EVOLUTIONS[job_class]
        path.append((job_class, level))
    return path

def check_class_evolution(player):
    """ Checks for Class Upgrades at Level 20, 40, 60, 80, 100. """
    evolution_map = CLASS_EVOLUTIONS

    current_class = player.job_class
    if current_class in evolution_map:
        next_class, required_level = evolution_map[current_class]
        if player.level >= required_level:
            player.job_class = next_class
            # db.session.commit() # Caller handles commit
            return True, next_class
            
    return False, None

def check_player_rank_up(player):
    """ Checks if player qualifies for a higher Hunter Rank. """
    # Rank Requirements: (Level, Total Stats)
    rank_reqs = {
        'E': ('D', 10, 50),
        'D': ('C', 20, 100),
        'C': ('B', 40, 200),
        'B': ('A', 60, 350),
        'A': ('S', 80, 500)
    }
    
    if player.rank == 'S':
        return False, None

    next_rank, req_lvl, req_stats = rank_reqs.get(player.rank, (None, 999, 9999))
    
    if next_rank:
        total_stats = player.strength + player.agility + player.intelligence + player.vitality + player.sense
        if player.level >= req_lvl and total_stats >= req_stats:
            player.rank = next_rank
            return True, next_rank
            
    return False, None

def equip_item_service(player, inventory_id):
    """ Equips an item from inventory. """
    item_record = db.session.get(Inventory, inventory_id)
    if not item_record or item_record.player_id != player.id:
        return False, "Item not found."
    
    if item_record.item.item_type != 'equipment':
        return False, "Cannot equip this item."
        
    # Logic: Enforce "One Item per Slot"
    target_slot = item_record.item.slot
    if target_slot:
        # Check if slot is occupied
        occupied = db.session.query(Inventory).join(RewardItem).filter(
            Inventory.player_id == player.id,
            Inventory.is_equipped == True,
            RewardItem.slot == target_slot,
            Inventory.id != item_record.id 
        ).first()
        
        if occupied:
            # Auto-Unequip Logic
            unequip_item_service(player, occupied.id)
            # return False, f"Slot {target_slot} already occupied by {occupied.item.name}"
    
    item_record.is_equipped = True
    db.session.commit()
    return True, f"Equipped: {item_record.item.name}"

def unequip_item_service(player, inventory_id):
    """ Unequips an item. """
    item_record = db.session.get(Inventory, inventory_id)
    if not item_record or item_record.player_id != player.id:
        return False, "Item not found."
        
    item_record.is_equipped = False
    db.session.commit()
    return True, f"Unequipped: {item_record.item.name}"

def extract_shadow(player, quest_id):
    """ 
    Arise.
    Converts a completed S-Rank Quest into a Shadow Soldier. 
    """
    quest = db.session.get(Quest, quest_id)
    if not quest or quest.player_id != player.id:
        return False, "Quest not found."
    
    if quest.rank != 'S' or quest.is_penalty or quest.is_daily: # Only glory can be extracted.
         return False, "Only S-Rank feats can be extracted."
         
    if not quest.is_completed:
        return False, "Quest must be completed first."
        
    # Check if already extracted? (Unique constraint? Or just allow multiple?)
    shadow = Shadow.query.filter_by(original_quest_name=quest.title, player_id=player.id).first()
    if shadow:
        return False, "Already Arised."
        
    new_shadow = Shadow(
        player_id=player.id,
        original_quest_name=quest.title,
        rank=quest.rank, # Usually S
        buff_type='ALL_STATS', # Default
        buff_value=1
    )
    db.session.add(new_shadow)
    db.session.commit()
    
    return True, f"ARISE! {quest.title} has joined your army."

def get_arise_candidates(player):
    """Completed S-Rank (non-penalty) quests that have not been extracted yet."""
    extracted = {s.original_quest_name for s in player.shadows}
    quests = Quest.query.filter_by(player_id=player.id, rank='S', is_completed=True,
                                   is_penalty=False, is_daily=False).all()
    return [q for q in quests if q.title not in extracted]

def allocate_attributes(player, distribution):
    """
    Allocates ability points to stats.
    distribution: dict {'STR': 0, 'INT': 0, ...}
    Returns: (Success, Message)
    """
    if any(v < 0 for v in distribution.values()):
        return False, "Invalid allocation."

    total_requested = sum(distribution.values())
    
    if total_requested <= 0:
        return False, "No points selected."
        
    if total_requested > player.attribute_points:
        return False, "Not enough ability points."
        
    for stat, amount in distribution.items():
        if amount > 0:
            if stat == 'STR': player.strength += amount
            elif stat == 'INT': player.intelligence += amount
            elif stat == 'AGI': player.agility += amount
            elif stat == 'VIT': player.vitality += amount
            elif stat == 'SNS': player.sense += amount
            
    player.attribute_points -= total_requested
    db.session.commit()
    return True, "Attributes updated."

def calculate_total_stats(player):
    """
    Returns a dictionary of total stats (Base + Equipment + Buffs).
    """
    stats = {
        'strength': player.strength,
        'intelligence': player.intelligence,
        'agility': player.agility,
        'vitality': player.vitality,
        'sense': player.sense
    }
    
    # Add Equipment Bonuses
    for inv_item in player.inventory:
        if inv_item.is_equipped and inv_item.item.stat_bonus:
            # Standardizing: RewardItem.stat_bonus should match Player field names or simple map
            # Let's map STR -> strength
            mapper = {
                'STR': 'strength',
                'INT': 'intelligence',
                'AGI': 'agility',
                'VIT': 'vitality',
                'SNS': 'sense'
            }
            target_stat = mapper.get(inv_item.item.stat_bonus, inv_item.item.stat_bonus.lower())
            
            if target_stat in stats:
                stats[target_stat] += inv_item.item.stat_value
                
    # Equipped Title Bonuses
    buff = active_title_buff(player)
    if buff.get('all'):
        for key in stats:
            stats[key] += buff['all']
    if buff.get('stat'):
        field, value = buff['stat']
        if field in stats:
            stats[field] += value

    # Shadow Army Buffs (Commanding Presence: Base 1% + 0.1% per 10 SNS)
    shadow_count = len(player.shadows)
    if shadow_count > 0:
        sense_bonus = (player.sense / 10) * 0.001 # +0.1% per 10 SNS
        multiplier = 1 + (shadow_count * (0.01 + sense_bonus))
        for key in stats:
            stats[key] = int(stats[key] * multiplier)
                
    # Penalty Debuff (Physical Resilience: Base -20% + 1% per 10 STR)
    if player.has_debuff:
        resilience = (player.strength / 10) * 0.01 # +1% recovery per 10 STR
        penalty_factor = max(0.0, 0.8 + resilience) # 0.8 is base (-20%)
        for key in stats:
            stats[key] = int(stats[key] * min(1.0, penalty_factor))
            
    return stats

def auto_complete_dailies(player):
    """
    Called when 'Night Out with Friends' is used.
    Completes all active Daily Quests for the player.
    """
    dailies = Quest.query.filter_by(player_id=player.id, is_daily=True, is_completed=False).all()
    count = 0
    if not dailies:
        return 0, "No active daily quests to complete."
        
    for q in dailies:
        # We call process_quest_completion to handle rewards, XP, etc.
        # But wait, does 'Night Out' give rewards? Usually 'skip' mechanics might not, but 'completing daily tasks' implies success.
        # User said: "make claiming the day out with friends auto complete that days daily tasks"
        # I will assume full completion logic (XP, etc.) applies, as it's a paid item (600 Gold).
        process_quest_completion(player, q)
        count += 1
        
    db.session.commit()
    return count, f"Successfully completed {count} daily quests. Enjoy your night out!"
def start_vacation(player, days):
    """
    Activates vacation mode for the player.
    Can only be used once a month.
    """
    now = datetime.now(timezone.utc)
    
    # Check monthly limit
    if player.last_vacation_date:
        if player.last_vacation_date.month == now.month and player.last_vacation_date.year == now.year:
            return False, "MONTHLY LIMIT EXCEEDED: You have already used your vacation for this month."
            
    player.is_on_vacation = True
    player.vacation_start_date = now
    player.vacation_end_date = now + timedelta(days=days)
    player.last_vacation_date = now
    player.vacation_count += 1
    
    db.session.commit()
    return True, f"VACATION ACTIVATED: System frozen for {days} days."

def end_vacation(player):
    """
    Deactivates vacation mode and applies stat penalties if applicable.
    """
    if not player.is_on_vacation:
        return False, "You are not on vacation."
        
    now = datetime.now(timezone.utc)
    # Ensure start date is offset-aware
    start_date = player.vacation_start_date
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
        
    duration = now - start_date
    weeks = int(duration.days / 7)
    
    # Stat Penalty: -1 to every stat for every week ACTUALLY spent
    # Endurance (Vitality) reduces this loss by 10% per 10 VIT.
    if weeks > 0:
        endurance = (player.vitality / 10) * 0.1
        final_loss = max(0, int(weeks * (1.0 - endurance)))
        
        if final_loss > 0:
            player.strength = max(1, player.strength - final_loss)
            player.intelligence = max(1, player.intelligence - final_loss)
            player.agility = max(1, player.agility - final_loss)
            player.sense = max(1, player.sense - final_loss)
            player.vitality = max(1, player.vitality - final_loss)
            msg = f"VACATION OVER: You returned after {duration.days} days. Stats reduced by {final_loss} (Endurance mitigated {weeks - final_loss})."
        else:
            msg = f"VACATION OVER: You returned after {duration.days} days. Your high Vitality prevented all stat decay."
    else:
        msg = "VACATION OVER: Welcome back, Hunter. No stat reduction applied."
        
    player.is_on_vacation = False
    player.vacation_start_date = None
    player.vacation_end_date = None
    db.session.commit()
    return True, msg

# --- NOTIFICATION SYSTEM LOGIC ---
from app.models import Notification

def create_notification(player_id, message, category="info"):
    """ Helper to create a notification. """
    notif = Notification(player_id=player_id, message=message, category=category)
    db.session.add(notif)
    db.session.commit()

def reminder_due_at(player, now=None):
    """
    UTC datetime of this game day's reminder for the player, or None if reminders are off.
    A time before 01:00 (e.g. 00:30) belongs to the end of the current game day.
    """
    if not player.reminder_time:
        return None
    try:
        hour, minute = (int(x) for x in player.reminder_time.split(':'))
    except ValueError:
        return None
    tz = player_tz(player)
    game_day = get_latest_daily_reset_time(now or datetime.now(timezone.utc), tz).date()
    if (hour, minute) < (RESET_HOUR, 0):
        game_day += timedelta(days=1)
    return tz.localize(datetime(game_day.year, game_day.month, game_day.day, hour, minute)).astimezone(timezone.utc)


def send_due_reminders(app_instance, now=None):
    """
    Scheduled Job (every 5 minutes): at each player's own reminder time (in their timezone),
    if dailies are unfinished, send one reminder per game day (inbox + push).
    """
    from app.league import record
    from app.models import ActivityEvent
    with app_instance.app_context():
        now = now or datetime.now(timezone.utc)
        sent = 0
        for player in Player.query.filter_by(setup_complete=True).all():
            if player.is_on_vacation:
                continue
            due = reminder_due_at(player, now)
            if due is None or now < due:
                continue
            day_start = get_latest_daily_reset_time(now, player_tz(player)).astimezone(timezone.utc)
            already = ActivityEvent.query.filter(
                ActivityEvent.player_id == player.id, ActivityEvent.kind == 'reminder',
                ActivityEvent.occurred_at >= day_start.replace(tzinfo=None)).first()
            if already:
                continue
            dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
            left = sum(1 for q in dailies if not q.is_completed)
            if not dailies or left == 0:
                continue
            msg = (f"⏰ {left} dail{'y' if left == 1 else 'ies'} left before your 01:00 reset."
                   + (f" Your {player.current_streak}-day streak is on the line." if player.current_streak else ""))
            create_notification(player.id, msg, "warning")
            trigger_push_notification(player.id, "Daily Reminder", msg, url="/")
            record(player, 'reminder', when=now)
            db.session.commit()
            sent += 1
        return sent
