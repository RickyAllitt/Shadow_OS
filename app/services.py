from app.extensions import db
from app.models import Player, RewardItem, Quest

def seed_database():
    """Populates the database with initial game state."""
    
    # 1. Create the Player (The User)
    if not Player.query.first():
        new_player = Player(
            name="Player One",          
            title="E-Rank Student",
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

    # 2. Create Default Shop Items (Rewards)
    if not RewardItem.query.first():
        default_rewards = [
            RewardItem(name="1 Hour Guilt-Free Laziness", cost=100, stock=-1),
            RewardItem(name="Cheat Meal", cost=300, stock=-1),
            RewardItem(name="Night Out with Friends", cost=600, stock=-1),
            RewardItem(name="Buy New Game/Gadget", cost=2000, stock=1), 
        ]
        db.session.add_all(default_rewards)
        print(">> Shop Stocked.")

    db.session.commit()

from datetime import datetime, timedelta, timezone

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

    now = datetime.now(timezone.utc)
    
    # Find the most recent Sunday at 23:59:59 (or Monday 00:00)
    # Strategy: Start from 'now' and subtract days until we hit Sunday.
    # weekday(): Mon=0, Sun=6
    days_since_sunday = (now.weekday() + 1) % 7
    # If today is Sunday, we want the PREVIOUS Sunday if we are not yet at night? 
    # Or simpler: The reset happens at Sunday 23:59.
    
    # Let's say reset time is Monday 00:00:00
    days_since_monday = now.weekday() # Mon=0
    
    # Get the most recent Monday 00:00
    # Note: replace(tzinfo=...) needed if original was unaware, but here 'now' is aware.
    # Actually, simplistic logic:
    last_monday = now - timedelta(days=days_since_monday, hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    
    # If player's last reset was BEFORE this last Monday, trigger reset.
    # Ensure comparison is offset-aware vs offset-aware.
    if player.last_weekly_reset.tzinfo is None:
        # Fallback for old data: assume UTC
        player.last_weekly_reset = player.last_weekly_reset.replace(tzinfo=timezone.utc)

    if player.last_weekly_reset < last_monday:
        player.gold = 0
        player.last_weekly_reset = now
        db.session.commit()
        return True
        
    return False

def calculate_xp_required(level):
    """ Exponential Curve: Next Level = Previous * 1.25 """
    # Base is 100 for Level 1 -> 2
    return int(100 * (1.25 ** (level - 1)))

def calculate_rewards(rank):
    """ Returns (XP, Gold) based on Rank """
    rewards = {
        'E': (10, 5),
        'D': (25, 20),
        'C': (60, 50),
        'B': (150, 200),
        'A': (500, 1000),
        'S': (1000, 2500)
    }
    return rewards.get(rank, (10, 5))

def process_quest_completion(player, quest):
    """ Handles all rewards, stats, and level up logic. """
    if quest.is_completed:
        return # Already done
        
    quest.is_completed = True
    quest.completed_at = datetime.now(timezone.utc)
    
    # 1. Calculate Rewards
    base_xp, base_gold = calculate_rewards(quest.rank)
    if quest.xp_reward: # Override if set on quest
        base_xp = quest.xp_reward
        
    # INT Multiplier: +5% per 10 INT
    int_multiplier = 1 + (player.intelligence / 10) * 0.05
    xp_gain = int(base_xp * int_multiplier)
    
    player.xp += xp_gain
    player.gold += base_gold
    
    # 2. Stat Buffs
    if quest.stat_reward == 'STR': player.strength += 1
    elif quest.stat_reward == 'INT': player.intelligence += 1
    elif quest.stat_reward == 'AGI': player.agility += 1
    elif quest.stat_reward == 'VIT': player.vitality += 1
    elif quest.stat_reward == 'SNS': player.sense += 1
    
    # 3. Level Up Logic
    if player.xp >= player.xp_required:
        player.level += 1
        player.xp -= player.xp_required
        player.xp_required = calculate_xp_required(player.level)
        # Note: Flash handling must be done in route
        
    # 4. Penalty Clearance
    if quest.is_penalty:
        player.in_penalty_zone = False
        player.consecutive_missed_days = 0 # Mercy reset
        player.has_debuff = False
        
    db.session.commit()
    return xp_gain, base_gold, (player.xp >= player.xp_required)

def check_daily_reset(player):
    """
    Checks if a new day has started.
    Implements the "System" Penalty Protocol: Debuff -> Lockout -> Level Down.
    """
    if not player.last_daily_reset:
        player.last_daily_reset = datetime.now(timezone.utc)
        db.session.commit()
        return False
        
    now = datetime.now(timezone.utc)
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if player.last_daily_reset.tzinfo is None:
         player.last_daily_reset = player.last_daily_reset.replace(tzinfo=timezone.utc)
    
    if player.last_daily_reset < today_midnight:
        # A new day has dawned. Judgment Time.
        
        dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
        
        # Calculate Completion from Yesterday
        # Since we haven't reset them yet, verify if they are marked complete.
        total_dailies = len(dailies)
        completed_dailies = sum(1 for q in dailies if q.is_completed)
        
        success = (total_dailies == 0) or (completed_dailies == total_dailies)
        
        if not success:
            # FAILURE LOGIC
            player.consecutive_missed_days += 1
            
            # Stage 1: Debuff (Immediate)
            player.has_debuff = True
            
            # Stage 2: Penalty Zone (2 Days Missed)
            if player.consecutive_missed_days >= 2:
                player.in_penalty_zone = True
                
                # Check if penalty quest exists, if not create one
                existing_penalty = Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).first()
                if not existing_penalty:
                    penalty = Quest(
                        title="PENALTY: Survival", 
                        rank="S", 
                        player_id=player.id,
                        xp_reward=0, 
                        gold_reward=0,
                        stat_reward="VIT",
                        is_penalty=True,
                        due_date=now + timedelta(hours=12)
                    )
                    db.session.add(penalty)

            # Stage 3: Level Down (3 Days Missed)
            if player.consecutive_missed_days >= 3:
                if player.level > 1:
                    player.level -= 1
                    player.xp = 0 # Reset XP bar
                    player.xp_required = calculate_xp_required(player.level)
                    # Stat Loss (Random or Fixed? Let's do -1 all for massive pain)
                    player.strength = max(1, player.strength - 1)
                    player.intelligence = max(1, player.intelligence - 1)
                    player.agility = max(1, player.agility - 1)
                    player.sense = max(1, player.sense - 1)
                    player.vitality = max(1, player.vitality - 1)
                    
                player.consecutive_missed_days = 0 # The debt is paid in blood
                player.in_penalty_zone = False # Unlocked, but broken
                player.has_debuff = False # Removed, but stats are lower permanently
        
        else:
            # SUCCESS LOGIC
            player.consecutive_missed_days = 0
            player.has_debuff = False
            
        # Reset Dailies for Today
        for quest in dailies:
            quest.is_completed = False
            
        player.last_daily_reset = now
        db.session.commit()
        return True
        
    return False

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
            
    # Sort Scheduled
    scheduled.sort(key=lambda x: x.due_date if x.due_date else datetime.max.replace(tzinfo=timezone.utc))
    
    return dailies, scheduled, backlog
