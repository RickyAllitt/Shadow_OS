from app.extensions import db
from app.models import Player, RewardItem, Quest, Title, PlayerTitle, Inventory, Shadow, DailySnapshot

def seed_database():
    """Populates the database with initial game state."""
    
    # 1. Create the Player (The User)
    if not Player.query.first():
        new_player = Player(
            name="Player One",
            # Title is set via relationship logic now
            level=1,
            xp=0,
            xp_required=100,
            gold=0,
            last_sleep_duration=0, 
            condition="Normal",
            strength=5,      
            intelligence=5,
            agility=5,
            sense=5,
            vitality=5,
            in_penalty_zone=False
        )
        db.session.add(new_player)
        print(">> Player Created.")
        # Assign default title here if it exists
        default_title = Title.query.filter_by(name="E-Rank Hunter").first()
        if default_title:
             new_player.current_title = default_title
             
             # Also unlock it
             assoc = PlayerTitle(player=new_player, title=default_title)
             db.session.add(assoc)

    # 2. Create Default Shop Items (Rewards)
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

def check_weekly_reset(player):
    """
    Checks if the weekly reset (Sunday night) has passed since the last reset.
    If so, resets Gold to 0.
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
    now_game = now_utc.astimezone(GAME_TIMEZONE)
    
    # Reset is Sunday 23:59:59 Game Time
    # Logic: If last reset was in a previous week?
    # Simpler: Get start of current week (Monday 00:00) in Game Time.
    # If last reset < start of current week, trigger reset.
    
    today_game = now_game.date()
    start_of_week = today_game - timedelta(days=today_game.weekday()) # Monday
    reset_threshold = GAME_TIMEZONE.localize(datetime.combine(start_of_week, datetime.min.time()))
    
    # Convert player's last reset (stored as UTC usually or unaware) to Game Time aware
    last_reset_utc = player.last_weekly_reset
    if last_reset_utc.tzinfo is None:
        last_reset_utc = last_reset_utc.replace(tzinfo=timezone.utc)
    
    if last_reset_utc < reset_threshold:
        player.gold = 0
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
    """
    vapid_private_key = os.getenv("VAPID_PRIVATE_KEY")
    vapid_claims = {
        "sub": "mailto:admin@system.local" # Required by spec
    }

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
                vapid_claims=vapid_claims
            )
        except WebPushException as ex:
            print(">> Web Push Failed!", ex)
            # Remove expired subscription if the service reports it no longer valid (410 Gone or 404 Not Found)
            if ex.response is not None and getattr(ex.response, 'status_code', None) in [410, 404]:
                print(f">> Removing expired subscription endpoint: {sub.endpoint}")
                db.session.delete(sub)
                db.session.commit()
        except Exception as e:
            print(">> Unexpected Web Push Error:", e)

def calculate_xp_required(level):
    """ Exponential Curve: Next Level = Previous * 1.25 """
    # Base is 100 for Level 1 -> 2
    return int(100 * (1.25 ** (level - 1)))

def calculate_rewards(rank, player_level=1):
    """ Returns (XP, Gold, Coins) based on Rank and Scaled Level Cap """
    
    # 1. Calculate XP Requirement for current level
    xp_cap = calculate_xp_required(player_level)
    
    # 2. Define Percentages (Target: 2 Years to Lvl 100)
    percentages = {
        'E': 0.01,  # 1%
        'D': 0.02,  # 2%
        'C': 0.03,  # 3%
        'B': 0.05,  # 5%
        'A': 0.12,  # 12%
        'S': 0.0    # 0 here, handled via Instant Level Up
    }
    
    # 3. Calculate Scaled XP
    pct = percentages.get(rank, 0.0)
    scaled_xp = int(xp_cap * pct)
    
    # 4. Enforce Minimums (Base Values) so low levels don't get 0 XP
    min_xp = {
        'E': 1, 'D': 2, 'C': 5, 'B': 10, 'A': 25, 'S': 0
    }
    final_xp = max(min_xp.get(rank, 0), scaled_xp)
    
    # 5. Gold/Coins remain flat (Economy balance separate from Leveling)
    rewards_flat = {
        'E': (0, 0),
        'D': (0, 0),
        'C': (0, 0),
        'B': (50, 15),
        'A': (100, 30),
        'S': (250, 100)
    }
    gold, coins = rewards_flat.get(rank, (0, 0))
    
    return final_xp, gold, coins

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
        player.condition = "Healthy" # Full Recovery
        
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
    
    return player.level > initial_level

def process_quest_completion(player, quest):
    """ Handles all rewards, stats, and level up logic. """
    if quest.is_completed:
        return # Already done
        
    quest.is_completed = True
    quest.completed_at = datetime.now(timezone.utc)
    
    if quest.is_daily:
        quest.progress = 0
    
    # 1. Calculate Rewards
    # 1. Calculate Rewards (Pass Level for Scaling)
    base_xp, base_gold, base_coins = calculate_rewards(quest.rank, player.level)
    # If quest has explicit rewards set (>0), use them. Otherwise use rank-based.
    if quest.xp_reward and quest.xp_reward > 10: # 10 is the model default
        base_xp = quest.xp_reward
    if quest.gold_reward and quest.gold_reward > 0:
        base_gold = quest.gold_reward
        
    # User Rule: Dailies and Penalties give NO rewards.
    if quest.is_daily or quest.is_penalty:
        base_gold = 0
        base_xp = 0
        base_coins = 0
        
    # INT Multiplier: +5% per 10 INT
    int_multiplier = 1 + (player.intelligence / 10) * 0.05
    xp_gain = int(base_xp * int_multiplier)
    
    # AGI Multiplier: +5% Coins per 10 AGI
    agi_multiplier = 1 + (player.agility / 10) * 0.05
    coin_gain = int(base_coins * agi_multiplier)
    
    # --- CLASS BONUSES ---
    # Assassin: +10% Coins
    if player.job_class == 'Assassin':
        coin_gain = int(coin_gain * 1.10)
        
    # Mage: +10% XP
    if player.job_class == 'Mage':
        xp_gain = int(xp_gain * 1.10)

    player.xp += xp_gain
    player.gold += base_gold
    player.coins += coin_gain
    # S-RANK REWARD: INSTANT LEVEL UP
    if quest.rank == 'S' and not quest.is_penalty and not quest.is_daily:
        # Fill XP bar to max immediately so that they just level up ONE time
        # Do not add remaining to xp_gain, otherwise it counts as excess
        player.xp = player.xp_required
        print(f">> S-RANK BONUS: Instant Level Up for {player.name}")

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

def _apply_quest_stat_reward(player, quest):
    """Helper to apply stat rewards from a quest."""
    amount = 1
    if quest.rank == 'A':
        amount = 2
    elif quest.rank == 'S':
        amount = 3
        
    if quest.stat_reward == 'STR': player.strength += amount
    elif quest.stat_reward == 'INT': player.intelligence += amount
    elif quest.stat_reward == 'AGI': player.agility += amount
    elif quest.stat_reward == 'VIT': player.vitality += amount
    elif quest.stat_reward == 'SNS': player.sense += amount

def _check_and_apply_daily_bonus(player):
    """Checks if all dailies are done. Applies bonus if eligible. Clears penalty if active."""
    # Check if ALL dailies are now completed
    dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
    all_completed = all(q.is_completed for q in dailies)
    
    bonus_granted = False
    
    if all_completed:
        # 1. Daily Bonus Logic
        now_utc = datetime.now(timezone.utc)
        now_game = now_utc.astimezone(GAME_TIMEZONE)
        
        # Check against today's midnight in Game Time
        today_midnight_game = now_game.replace(hour=0, minute=0, second=0, microsecond=0)
        
        last_bonus = player.last_daily_bonus
        if last_bonus and last_bonus.tzinfo is None:
            last_bonus = last_bonus.replace(tzinfo=timezone.utc)
            
        # Optimization: We only care if last_bonus was BEFORE today_midnight.
        # But last_bonus is UTC. Convert logic.
        # If last_bonus < today_midnight_game (converted to UTC for comparison)
        today_midnight_utc = today_midnight_game.astimezone(timezone.utc)
        
        if not last_bonus or last_bonus < today_midnight_utc:
            # Scaled Daily Bonus: 10% of Level Cap
            xp_cap = calculate_xp_required(player.level)
            bonus_xp = int(xp_cap * 0.10)
            player.xp += bonus_xp
            
            player.gold += 100 
            player.coins += 50 
            player.attribute_points += 3 # Daily Ability Points
            player.condition = "Healthy" # Status Recovery
            
            player.last_daily_bonus = now_utc
            print(f">> Daily Bonus Granted for {player.name}")
            bonus_granted = True

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
    now_game = now_utc.astimezone(GAME_TIMEZONE)
    today_midnight_game = now_game.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # We compare everything in UTC to be safe with DB, but the "midnight point" is determined by Madrid time.
    today_midnight_utc = today_midnight_game.astimezone(timezone.utc)
    
    if player.last_daily_reset.tzinfo is None:
         player.last_daily_reset = player.last_daily_reset.replace(tzinfo=timezone.utc)
    
    # Catch-up Loop: Process EACH missed day
    messages = []
    days_processed = 0
    reset_occurred = False
    
    while player.last_daily_reset < today_midnight_utc:
        # Advance last_reset by 1 day
        # We process the day that just ended (last_daily_reset -> last_daily_reset + 1 day)
        # But efficiently, we just check "did we miss yesterday?"
        
        # Actually, simpler:
        # If last_reset was 2023-01-01 and today is 2023-01-03.
        # We need to process failure for 01-01 to 01-02, and 01-02 to 01-03.
        
        # Target for this iteration is the end of the "current" recorded day
        # We will simulate the check happening at midnight of the next day
        
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
        
        if not success:
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
            elif effective_missed_days > 1:
                player.has_debuff = True
            
            # Stage 2: Penalty Zone
            if effective_missed_days == 2:
                player.in_penalty_zone = True
                messages.append("SYSTEM ALERT: PENALTY ZONE ENTERED.")
                
                existing_penalty = Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).first()
                if not existing_penalty:
                    # Calculate deadline: Next Midnight in Madrid
                    # If we are in catch-up loop, we effectively set it relative to "now" since they just logged in?
                    # Yes, give them until the upcoming midnight to fix it.
                    deadline_game = today_midnight_game + timedelta(days=1)
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
            if effective_missed_days >= 3:
                if player.level > 1:
                    player.level = max(1, player.level - 3)
                    player.xp = 0 
                    player.xp_required = calculate_xp_required(player.level)
                    
                    endurance = (player.vitality / 10) * 0.1
                    loss = max(1, int(3 * (1.0 - endurance)))
                    
                    player.strength = max(1, player.strength - loss)
                    player.intelligence = max(1, player.intelligence - loss)
                    player.agility = max(1, player.agility - loss)
                    player.sense = max(1, player.sense - loss)
                    player.vitality = max(1, player.vitality - loss)
                    
                    messages.append("CRITICAL: PROLONGED ABSENCE. STATS REDUCED.")
                    
                    # Clear penalty
                    active_penalties = Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).all()
                    for p_quest in active_penalties:
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
            
        # Reset Dailies (Prepare for next day iteration)
        for quest in dailies:
            quest.is_completed = False
            
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
    print(f"Checking titles for {player.name}...")
    
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
                
        elif t.unlock_condition == 'streak_daily' or t.unlock_condition == 'streak_sleep':
            # Mapping 'streak_daily' to sleep_streak for now as it is the primary tracked streak
            if player.sleep_streak >= t.unlock_value:
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
            
    if new_unlocks:
        print(f"New Titles Unlocked: {new_unlocks}")
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

def check_class_evolution(player):
    """ Checks for Class Upgrades at Level 20, 40, 60, 80, 100. """
    evolution_map = {
        # Tier 1 -> Tier 2 (Level 20)
        "Assassin": ("Shadow Assassin", 20),
        "Mage": ("Archmage", 20),
        "Tank": ("Juggernaut", 20),
        
        # Tier 2 -> Tier 3 (Level 40)
        "Shadow Assassin": ("Shadow Lord", 40),
        "Archmage": ("Spellweaver", 40),
        "Juggernaut": ("Iron Fortress", 40),
        
        # Tier 3 -> Tier 4 (Level 60)
        "Shadow Lord": ("Nightwalker", 60),
        "Spellweaver": ("Arcane Sage", 60),
        "Iron Fortress": ("Titan", 60),
        
        # Tier 4 -> Tier 5 (Level 80)
        "Nightwalker": ("Eclipse Bringer", 80),
        "Arcane Sage": ("Void Walker", 80),
        "Titan": ("World Guardian", 80),
        
        # Tier 5 -> Tier 6 (Level 100)
        "Eclipse Bringer": ("Monarch of Shadows", 100),
        "Void Walker": ("Monarch of Scrolls", 100),
        "World Guardian": ("Monarch of Iron", 100)
    }
    
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
    
    if quest.rank != 'S' and not quest.is_penalty: # Allow Penalty extraction? No, only glory.
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

def allocate_attributes(player, distribution):
    """
    Allocates ability points to stats.
    distribution: dict {'STR': 0, 'INT': 0, ...}
    Returns: (Success, Message)
    """
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
    # Let's check duplicate original name to prevent spamming same quest?
    # For now, allow it.
    
    shadow = Shadow(
        player_id=player.id,
        original_quest_name=quest.title,
        rank=quest.rank,
        buff_type='ALL_STATS', # Default for now
        buff_value=1 # +1%
    )
    db.session.add(shadow)
    db.session.commit()
    
    return True, f"ARISE. {quest.title} has joined your Shadow Army."



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

def check_daily_completion_status(app_instance):
    """
    Scheduled Job (18:00): Checks if players have completed their dailies.
    If not, sends a WARNING notification.
    """
    with app_instance.app_context():
        players = Player.query.all()
        for player in players:
            if player.is_on_vacation:
                continue
                
            dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
            if not dailies:
                continue
                
            completed = sum(1 for q in dailies if q.is_completed)
            total = len(dailies)
            
            if completed < total:
                msg = f"SYSTEM ALERT: Daily Routine incomplete ({completed}/{total}). Failure will result in penalties at midnight."
                create_notification(player.id, msg, "warning")
                print(f">> Notification sent to {player.name}: Incomplete Dailies")

def check_upcoming_deadlines(app_instance):
    """
    Scheduled Job (08:00): Checks for quests due Today or Tomorrow.
    """
    with app_instance.app_context():
        # Clean up old read notifications first (maintain hygiene)
        # Delete read notifications older than 7 days
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        old_notifs = Notification.query.filter(Notification.is_read == True, Notification.created_at < cutoff).delete()
        db.session.commit()
        
        players = Player.query.all()
        now = datetime.now(timezone.utc)
        today_end = now.replace(hour=23, minute=59, second=59)
        tomorrow_end = today_end + timedelta(days=1)
        
        for player in players:
            if player.is_on_vacation:
                continue
                
            # Check Tasks Due Today (excluding Dailies as they are unspoken)
            urgent_tasks = Quest.query.filter(
                Quest.player_id == player.id,
                Quest.is_completed == False,
                Quest.is_daily == False,
                Quest.due_date >= now, 
                Quest.due_date <= today_end
            ).all()
            
            for task in urgent_tasks:
                create_notification(player.id, f"REMINDER: '{task.title}' is due TODAY.", "warning")
                
            # Check Tasks Due Tomorrow
            future_tasks = Quest.query.filter(
                Quest.player_id == player.id,
                Quest.is_completed == False,
                Quest.is_daily == False,
                Quest.due_date > today_end, 
                Quest.due_date <= tomorrow_end
            ).all()
            
            for task in future_tasks:
                create_notification(player.id, f"HEADS UP: '{task.title}' is due tomorrow.", "info")
