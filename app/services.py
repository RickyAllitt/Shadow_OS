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
            RewardItem(name="1 Hour Gaming / Netflix", cost=100, stock=-1),
            RewardItem(name="Cheat Meal", cost=300, stock=-1),
            RewardItem(name="Night Out with Friends", cost=500, stock=-1),
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

def check_daily_reset(player):
    """
    Checks if a new day has started (Midnight).
    If so, un-completes Daily Quests.
    """
    if not player.last_daily_reset:
        player.last_daily_reset = datetime.now(timezone.utc)
        db.session.commit()
        return False
        
    now = datetime.now(timezone.utc)
    # Reset threshold: Today at 00:00:00
    today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if player.last_daily_reset.tzinfo is None:
         player.last_daily_reset = player.last_daily_reset.replace(tzinfo=timezone.utc)
    
    if player.last_daily_reset < today_midnight:
        # It's a new day! Reset dailies.
        dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
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
        elif q.start_date or q.due_date:
            scheduled.append(q)
        else:
            backlog.append(q)
            
    # Sort Scheduled
    scheduled.sort(key=lambda x: x.due_date if x.due_date else datetime.max.replace(tzinfo=timezone.utc))
    
    return dailies, scheduled, backlog

def check_for_penalties(player):
    """
    Checks if any Daily Quests were missed yesterday.
    If yes, trigger the Penalty Zone.
    """
    # 1. Get all daily quests
    dailies = Quest.query.filter_by(is_daily=True).all()
    
    # Placeholder logic for now
    pass
