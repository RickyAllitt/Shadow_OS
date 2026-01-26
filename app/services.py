from app.extensions import db
from app.models import Player, RewardItem, Quest, Title, PlayerTitle, Inventory, Shadow

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
        # Title handling happens in process_quest_completion or manual checks now
        # We assume migration script handles default title assignment for new players via default in DB or signals?
        # Better: Assign default title here if it exists
        default_title = Title.query.filter_by(name="E-Rank Hunter").first()
        if default_title:
             new_player.current_title = default_title
             
             # Also unlock it
             assoc = PlayerTitle(player=new_player, title=default_title)
             db.session.add(assoc)

    # 2. Create Default Shop Items (Rewards)
    if not RewardItem.query.first():
        default_rewards = [
            RewardItem(name="Night Out with Friends", cost=600, stock=-1, item_type='consumable'),
            RewardItem(name="Novice Dagger", cost=100, stock=1, currency='coins', item_type='equipment', stat_bonus='STR', stat_value=2),
            RewardItem(name="Apprentice Grimoire", cost=100, stock=1, currency='coins', item_type='equipment', stat_bonus='INT', stat_value=2),
            RewardItem(name="Iron Shield", cost=100, stock=1, currency='coins', item_type='equipment', stat_bonus='VIT', stat_value=2),
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
    """ Returns (XP, Gold, Coins) based on Rank """
    rewards = {
        'E': (10, 0, 0),
        'D': (25, 0, 0),
        'C': (60, 0, 0),
        'B': (150, 150, 10),
        'A': (500, 300, 25),
        'S': (1000, 600, 50)
    }
    return rewards.get(rank, (10, 0, 0))

def process_quest_completion(player, quest):
    """ Handles all rewards, stats, and level up logic. """
    if quest.is_completed:
        return # Already done
        
    quest.is_completed = True
    quest.completed_at = datetime.now(timezone.utc)
    
    # 1. Calculate Rewards
    base_xp, base_gold, base_coins = calculate_rewards(quest.rank)
    if quest.xp_reward: # Override if set on quest
        base_xp = quest.xp_reward
        
    # User Rule: Dailies give NO Gold and NO XP (individually).
    if quest.is_daily:
        base_gold = 0
        base_xp = 0
        base_coins = 0
        
    # INT Multiplier: +5% per 10 INT
    int_multiplier = 1 + (player.intelligence / 10) * 0.05
    xp_gain = int(base_xp * int_multiplier)
    
    # --- CLASS BONUSES ---
    # Assassin: +10% Gold
    if player.job_class == 'Assassin':
        base_gold = int(base_gold * 1.10)
        
    # Mage: +10% XP
    if player.job_class == 'Mage':
        xp_gain = int(xp_gain * 1.10)

    player.xp += xp_gain
    player.gold += base_gold
    player.coins += base_coins
    
    # 2. Apply Stat Buffs
    _apply_quest_stat_reward(player, quest)
    
    # 3. Daily Completion Bonus (+100 Gold + 50 XP)
    daily_bonus = False
    if quest.is_daily:
        daily_bonus = _check_and_apply_daily_bonus(player)

    # 4. Level Up Logic (Moved after all XP gains)
    initial_level = player.level
    while player.xp >= player.xp_required:
        player.level += 1
        player.xp -= player.xp_required
        player.xp_required = calculate_xp_required(player.level)
        
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

    # 5. Penalty Clearance
    if quest.is_penalty:
        player.in_penalty_zone = False
        player.consecutive_missed_days = 0 # Mercy reset
        player.has_debuff = False
        
    db.session.commit()
    
    can_arise = (quest.rank == 'S')
    return xp_gain, base_gold, base_coins, (player.level > initial_level), daily_bonus, can_arise

def _apply_quest_stat_reward(player, quest):
    """Helper to apply stat rewards from a quest."""
    if quest.stat_reward == 'STR': player.strength += 1
    elif quest.stat_reward == 'INT': player.intelligence += 1
    elif quest.stat_reward == 'AGI': player.agility += 1
    elif quest.stat_reward == 'VIT': player.vitality += 1
    elif quest.stat_reward == 'SNS': player.sense += 1

def _check_and_apply_daily_bonus(player):
    """Checks if all dailies are done and applies bonus if not claimed yet."""
    dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
    # Check if ALL dailies are now completed
    all_completed = all(q.is_completed for q in dailies)
    
    if all_completed:
        # Check if bonus already claimed today
        now = datetime.now(timezone.utc)
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Use player.last_daily_bonus if exists
        last_bonus = player.last_daily_bonus
        if last_bonus and last_bonus.tzinfo is None:
            last_bonus = last_bonus.replace(tzinfo=timezone.utc)
            
        if not last_bonus or last_bonus < today_midnight:
            player.gold += 100
            player.xp += 50 # Bonus XP
            player.coins += 20 # Bonus Coins
            player.last_daily_bonus = now
            print(f">> Daily Bonus Granted for {player.name}")
            return True
    return False

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
            
            # --- CLASS BONUS: TANK ---
            # Tanks ignore the first day of failure (Grace Period)
            effective_missed_days = player.consecutive_missed_days
            if player.job_class == 'Tank':
                effective_missed_days = max(0, effective_missed_days - 1)
            
            # Stage 1: Debuff (Immediate)
            if effective_missed_days >= 1:
                player.has_debuff = True
            
            # Stage 2: Penalty Zone (2 Days Missed -> Tanks: 3 Days)
            if effective_missed_days >= 2:
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

            # Stage 3: Level Down (3 Days Missed -> Tanks: 4 Days)
            if effective_missed_days >= 3:
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
            return False, f"Slot {target_slot} already occupied by {occupied.item.name}"
    
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

def ensure_welcome_quest(player):
    """
    Checks if the player has any quests at all.
    If not, seeds a tutorial quest.
    """
    quest_count = Quest.query.filter_by(player_id=player.id).count()
    quest_count = Quest.query.filter_by(player_id=player.id).count()
    if quest_count == 0:
        # 1. Tutorial Quest
        welcome_quest = Quest(
            title="Welcome to the System: Create a Task",
            rank="E",
            player_id=player.id,
            xp_reward=50,
            gold_reward=10,
            stat_reward="INT", # Learning the system
            is_daily=False
        )
        db.session.add(welcome_quest)
        
        # 2. Default Dailies x3
        default_dailies = [
            Quest(title="Morning Routine", rank="E", player_id=player.id, xp_reward=10, gold_reward=5, stat_reward="VIT", is_daily=True),
            Quest(title="Exercise / Workout", rank="D", player_id=player.id, xp_reward=25, gold_reward=10, stat_reward="STR", is_daily=True),
            Quest(title="Study / Work Focus", rank="D", player_id=player.id, xp_reward=25, gold_reward=10, stat_reward="INT", is_daily=True)
        ]
        db.session.add_all(default_dailies)
        
        db.session.commit()
        return True
    return False

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
                
    # Shadow Army Buffs (Percentage Scaling)
    # Each Shadow gives +1% All Stats (default)
    shadow_count = len(player.shadows)
    if shadow_count > 0:
        multiplier = 1 + (shadow_count * 0.01) # e.g. 5 shadows = 1.05x
        for key in stats:
            stats[key] = int(stats[key] * multiplier)
                
    # Penalty Debuff (-20%)
    if player.has_debuff:
        for key in stats:
            stats[key] = int(stats[key] * 0.8)
            
    return stats
