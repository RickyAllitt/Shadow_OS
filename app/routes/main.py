from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import Player, Quest, RewardItem, QuestComment, PurchaseLog, Inventory, DailySnapshot, Notification, PushSubscription
from app.services import (check_weekly_reset, check_daily_reset, get_categorized_quests, 
                          calculate_rewards, process_quest_completion, 
                          calculate_total_stats, extract_shadow, start_vacation, end_vacation, allocate_attributes)
from datetime import datetime, timedelta, timezone

def parse_datetime_input(dt_str):
    if not dt_str:
        return None
    try:
        # Try datetime-local format ('2023-10-25T14:30')
        return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        try:
            # Fallback to pure date format ('2023-10-25')
            return datetime.strptime(dt_str, '%Y-%m-%d')
        except ValueError:
            return None

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required
def dashboard():
    if check_weekly_reset(current_user):
        flash("WEEKLY RESET: Gold has been reset to 0.", "system_popup")
    
    reset_occurred, msgs = check_daily_reset(current_user)
    if reset_occurred:
        flash("DAILY RESET: Daily quests have been refreshed.", "system_popup")
        for msg in msgs:
            flash(msg, "system_popup")

    player = current_user
    

    
    # Get Items
    dailies, scheduled, backlog = get_categorized_quests(player.id)
    
    # Onboarding Check
    if not player.setup_complete:
        return redirect(url_for('main.setup_page'))
    

    
    # Calculate Total Stats (Base + Equipment + Debuffs)
    total_stats = calculate_total_stats(player)
    
    return render_template('dashboard.html', player=player, stats=total_stats,
                           dailies=dailies, scheduled=scheduled, backlog=backlog)

from app.ai_guardian import TheArchitect

@bp.route('/add_quest', methods=['POST'])
@login_required
def add_quest():
    title = request.form.get('title')
    description = request.form.get('description')
    rank = request.form.get('rank')
    
    # Optional inputs
    stat = request.form.get('stat', 'INT') # Default if missing
    is_daily = 'is_daily' in request.form
    
    start_date = None
    due_date = None
    if request.form.get('start_date'):
        start_date = parse_datetime_input(request.form.get('start_date'))
    if request.form.get('due_date'):
        due_date = parse_datetime_input(request.form.get('due_date'))

    # Auto-Evaluation Logic
    if rank == 'Auto':
        analysis = TheArchitect.analyze_quest(title)
        rank = analysis['rank']
        xp = analysis['xp']
        stat = analysis['stat']
        flash(f"System Analysis: Rank {rank} | Stat {stat} | XP {xp}", "info")
    else:
        xp_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}
        # Use centralized logic
        xp, _, _ = calculate_rewards(rank)
    
    priority = int(request.form.get('priority', 4))
    
    quest = Quest(
        title=title, 
        description=description,
        rank=rank, 
        xp_reward=xp, 
        stat_reward=stat,
        player_id=current_user.id,
        is_daily=is_daily,
        start_date=start_date,
        due_date=due_date,
        priority=priority
    )
    
    db.session.add(quest)
    db.session.commit()
    
    flash(f"Quest '{title}' Accepted.", "system_popup")
    return redirect(url_for('main.dashboard'))

@bp.route('/complete/<int:id>', methods=['GET', 'POST'])
@login_required
@login_required
def complete_quest(id):
    quest = db.session.get(Quest, id)
    player = current_user
    
    if not quest:
        return redirect(url_for('main.dashboard'))
        
    # GET: Show Verification Page
    if request.method == 'GET':
        return render_template('verify_completion.html', quest=quest)
    
    # POST: Execute Completion
    xp_gain, gold_gain, coin_gain, level_up, daily_bonus, can_arise = process_quest_completion(player, quest)
    
    # Feedback
    msg = f"COMPLETE: {quest.title} | +{xp_gain} XP"
    if gold_gain > 0:
        msg += f" | +{gold_gain} G"
    if coin_gain > 0:
        msg += f" | +{coin_gain} C"
        
    flash(msg, "quest_complete")
    
    if daily_bonus:
            flash("DAILY BONUS: All tasks completed! +100 Gold | +20 Coins | +50 XP", "system_popup")
    
    if level_up:
        flash("LEVEL UP!", "levelup")
        
    # Check for Evolution (Service attaches this attribute temporarily)
    if hasattr(player, 'just_evolved') and player.just_evolved:
        flash(f"CLASS EVOLVED: You are now a {player.just_evolved}!", "system_popup")
        
    # Check for Rank Up
    if hasattr(player, 'just_ranked_up') and player.just_ranked_up:
        flash(f"RANK UP: You have reached {player.just_ranked_up}-Rank!", "system_popup")
        
    if quest.is_penalty:
        flash("PENALTY CLEARED. WELCOME BACK.", "system_popup")

    if can_arise:
        # Trigger 'Arise' Interaction via URL Param for reliability
        return redirect(url_for('main.dashboard', arise=quest.id))
    
    return redirect(url_for('main.dashboard'))



@bp.route('/buy/<int:item_id>', methods=['POST'])
@login_required
def buy_item(item_id):
    item = db.session.get(RewardItem, item_id)
    player = current_user
    
    # PENALTY CHECK
    # Removed: Shop is no longer locked during a penalty
    
    if not item:
        return redirect(url_for('main.dashboard'))
        
    # CHECK UNIQUE OWNERSHIP (For both Gold and Coins)
    # Users can only hold ONE copy of any item (Equipment or Special)
    exists = Inventory.query.filter_by(player_id=player.id, item_id=item.id).first()
    if exists:
            flash(f"You already own {item.name}. (Limit: 1)", "error")
            if request.args.get('json'):
                return jsonify({'success': False, 'message': f"You already own {item.name}."})
            return redirect(url_for('main.dashboard'))
        
    # stock check
    if item.stock != -1 and item.stock <= 0:
        flash("Out of Stock.", "error")
        return redirect(url_for('main.dashboard'))

    # Deduct Cost & Check Funds based on Currency
    if item.currency == 'coins':
        if player.coins < item.cost:
            if request.args.get('json'):
                return jsonify({'success': False, 'message': "Not enough coins."})
            flash("Not enough coins.", "error")
            return redirect(url_for('main.dashboard'))
        player.coins -= item.cost
    else:
        # Default to Gold
        if player.gold < item.cost:
            if request.args.get('json'):
                return jsonify({'success': False, 'message': "Insufficient Funds."})
            flash("Insufficient Funds.", "error")
            return redirect(url_for('main.dashboard'))
        player.gold -= item.cost
    
    # Decrease Stock if applicable (transaction approved)
    if item.stock != -1:
        item.stock -= 1

    if item.item_type == 'equipment':
        msg_text = f"Purchased {item.name}. Added to Inventory."
    else:
        msg_text = f"Purchased {item.name}. Added to Bag."
            
    # Always add to inventory
    new_inv = Inventory(player_id=player.id, item_id=item.id)
    db.session.add(new_inv)
    
    # Log purchase
    log = PurchaseLog(player_id=player.id, item_name=item.name, cost=item.cost, is_claimed=True, claimed_at=datetime.now(timezone.utc))
        
    db.session.add(log)
    db.session.commit()
    
    if request.args.get('json'):
        response_data = {
            'success': True, 
            'message': msg_text,
            'new_gold': player.gold,
            'new_coins': player.coins
        }
        
        # Include details for UI update (All items now create inventory records)
        if 'new_inv' in locals():
            response_data['item_details'] = {
                'name': item.name,
                'type': item.item_type,
                'stat_bonus': item.stat_bonus,
                'stat_value': item.stat_value,
                'inv_id': new_inv.id
            }
            
        return jsonify(response_data)

    flash(msg_text, "success")
    return redirect(url_for('main.dashboard'))

import calendar
from datetime import timedelta

@bp.route('/calendar')
@bp.route('/calendar/<int:year>/<int:month>')
@login_required
def calendar_view(year=None, month=None):
    now = datetime.now()
    if year is None: year = now.year
    if month is None: month = now.month
    
    # Adjust for month overflow/underflow (simple navigation logic)
    if month > 12:
        month = 1
        year += 1
    elif month < 1:
        month = 12
        year -= 1

    # Get Calendar Grid
    cal = calendar.monthcalendar(year, month)
    
    # Fetch Player's Active Quests with Due Dates
    # Filter: Belong to player, has due_date, due_date is in this month
    # Note: SQLite dates can be tricky. For robustness, we'll fetch all active active and filter python side
    # or simple range query.
    
    start_date = datetime(year, month, 1)
    # End date calculation
    if month == 12:
        end_date = datetime(year + 1, 1, 1)
    else:
        end_date = datetime(year, month + 1, 1)
        
    quests = Quest.query.filter(
        Quest.player_id == current_user.id,
        Quest.due_date >= start_date,
        Quest.due_date < end_date
    ).all()
    
    # Map Quests to Days
    quest_map = {}
    for q in quests:
        day = q.due_date.day
        if day not in quest_map:
            quest_map[day] = []
        quest_map[day].append(q)
        
    # Navigation Dates
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
        
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    return render_template('calendar.html', 
                           calendar=cal, 
                           year=year, 
                           month=month, 
                           month_name=calendar.month_name[month],
                           quest_map=quest_map,
                           prev_year=prev_year, prev_month=prev_month,
                           next_year=next_year, next_month=next_month)

@bp.route('/leaderboard')
@login_required
def leaderboard():
    # Top 20 players by Level DESC, then XP DESC
    leaderboard_data = Player.query.order_by(Player.level.desc(), Player.xp.desc()).limit(20).all()
    return render_template('leaderboard.html', leaderboard=leaderboard_data)

@bp.route('/profile/<int:player_id>')
@login_required
def public_profile(player_id):
    player = db.session.get(Player, player_id)
    if not player:
        flash("Player not found.", "error")
        return redirect(url_for('main.leaderboard'))
        
    return render_template('public_profile.html', player=player)

@bp.route('/log')
@login_required
def history_log():
    # Fetch all completed quests, ordered by most recent
    history = Quest.query.filter_by(player_id=current_user.id, is_completed=True).order_by(Quest.completed_at.desc()).all()
    return render_template('log.html', history=history)

@bp.route('/track_sleep', methods=['POST'])
@login_required
def track_sleep():
    player = current_user
    hours = float(request.form.get('hours'))
    
    player.last_sleep_duration = hours
    
    # Check for daily restriction
    today = datetime.now(timezone.utc).date()
    if player.last_sleep_log_date == today:
        flash("You have already logged sleep for today.", "system_popup")
        return redirect(url_for('main.dashboard'))
        
    player.last_sleep_log_date = today
    
    # --- THE SYSTEM LOGIC ---
    if hours >= 7.5:
        player.condition = "WELL RESTED"
        player.sleep_streak += 1
        # Buff: Restores HP/MP (Visual)
        flash(f"SLEEP: {hours}h. CONDITION: BEST. (XP GAIN +10%)", "system_popup")
        
    elif hours >= 6:
        player.condition = "NORMAL"
        flash(f"SLEEP: {hours}h. CONDITION: NORMAL.", "system_popup")
        
    else:
        player.condition = "TIRED"
        player.sleep_streak = 0
        # Debuff: Warning
        flash(f"SLEEP: {hours}h. WARNING: RECOVERY INCOMPLETE. (XP GAIN REDUCED)", "system_popup")
        
    db.session.commit()
    return redirect(url_for('main.dashboard'))

@bp.route('/delete_quest/<int:id>', methods=['GET', 'POST'])
@login_required
def delete_quest(id):
    quest = db.session.get(Quest, id)
    if not quest:
        return redirect(url_for('main.dashboard'))
    
    if quest.player_id != current_user.id:
        flash("Unauthorized.", "error")
        return redirect(url_for('main.dashboard'))
        
    # Calculate Cost
    # DAILY/PENALTY: 500 Coins
    # NORMAL: Free
    
    cost = 0
    currency = 'gold' # Default for template compatibility, though we switch to coins/free

    if quest.is_daily or quest.is_penalty:
        cost = 500
        currency = 'coins'
    
    if request.method == 'POST':
        if currency == 'coins':
            if current_user.coins >= cost:
                current_user.coins -= cost
                db.session.delete(quest)
                db.session.commit()
                flash(f"Quest Abandoned. You paid {cost} Coins to break your oath.", "system_popup")
                return redirect(url_for('main.dashboard'))
            else:
                flash(f"Insufficient Coins. You need {cost} C to abandon this duty.", "error_modal")
                return redirect(url_for('main.dashboard'))
        else:
            # Free
            db.session.delete(quest)
            db.session.commit()
            flash("Quest Abandoned.", "system_popup")
            return redirect(url_for('main.dashboard'))
    
    # GET: Pre-screen funds
    if currency == 'coins' and current_user.coins < cost:
         flash(f"INSUFFICIENT FUNDS: You need {cost} Coins to abandon this quest.", "error_modal")
         return redirect(url_for('main.dashboard'))
    
    return render_template('abandon_quest.html', quest=quest, cost=cost, currency=currency)

@bp.route('/edit_quest/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_quest(id):
    quest = db.session.get(Quest, id)
    if not quest:
         return redirect(url_for('main.dashboard'))
    
    if quest.player_id != current_user.id:
        flash("Unauthorized.", "error")
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        new_title = request.form.get('title')
        new_description = request.form.get('description')
        new_rank = request.form.get('rank')
        new_stat = request.form.get('stat')
        
        start_str = request.form.get('start_date')
        due_str = request.form.get('due_date')
        new_priority_str = request.form.get('priority')
        
        # Restriction Check for Dailies
        restricted_modified = False
        can_rewrite_reality = False
        
        if quest.is_daily:
            if new_title is not None and new_title != quest.title: restricted_modified = True
            if new_rank is not None and new_rank != quest.rank: restricted_modified = True
            if new_stat is not None and new_stat != quest.stat_reward: restricted_modified = True
            if new_priority_str is not None and int(new_priority_str) != quest.priority: restricted_modified = True
            
            if start_str is not None:
                new_start = parse_datetime_input(start_str)
                if new_start != quest.start_date: restricted_modified = True
            if due_str is not None:
                new_due = parse_datetime_input(due_str)
                if new_due != quest.due_date: restricted_modified = True
                
            if restricted_modified:
                cost = 250
                if current_user.coins >= cost:
                    current_user.coins -= cost
                    flash(f"Reality Rewritten. -{cost} Coins.", "system_popup")
                    can_rewrite_reality = True
                else:
                    flash(f"Insufficient Coins. Modifying a Daily Quest's core attributes requires {cost} Coins.", "error")
            
            # Apply restricted fields ONLY IF they weren't modified OR they paid for it
            if not restricted_modified or can_rewrite_reality:
                if new_title is not None: quest.title = new_title
                if new_rank is not None: quest.rank = new_rank
                if new_stat is not None: quest.stat_reward = new_stat
                if new_priority_str is not None: quest.priority = int(new_priority_str)
                if start_str is not None: quest.start_date = parse_datetime_input(start_str)
                if due_str is not None: quest.due_date = parse_datetime_input(due_str)
        else:
            # Normal Quest Logic
            if new_title is not None: quest.title = new_title
            if new_rank is not None: quest.rank = new_rank
            if new_stat is not None: quest.stat_reward = new_stat
            if new_priority_str is not None: quest.priority = int(new_priority_str)
            if start_str is not None: quest.start_date = parse_datetime_input(start_str)
            if due_str is not None: quest.due_date = parse_datetime_input(due_str)
            quest.is_daily = True if request.form.get('is_daily') else False

        # Non-restricted updates (ALWAYS updated)
        if new_description is not None:
            quest.description = new_description

        try:
             # Default to current progress if not provided
             quest.progress = int(request.form.get('progress', quest.progress))
        except ValueError:
             pass
             
        # New Comment
        new_comment_text = request.form.get('new_comment')
        if new_comment_text and new_comment_text.strip():
            comment = QuestComment(content=new_comment_text.strip(), quest_id=quest.id)
            db.session.add(comment)
        
        # Recalculate XP if rank changes
        xp_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}
        quest.xp_reward = xp_map.get(quest.rank, 10)
        
        db.session.commit()
        if not (quest.is_daily and restricted_modified and not can_rewrite_reality):
            flash("Quest updated.", "system_popup")
            
        return redirect(url_for('main.dashboard'))
        
    # Reuse dashboard? Or render a specific edit page?
    return render_template('edit_quest.html', quest=quest)

@bp.route('/architect/breakdown/<int:quest_id>', methods=['GET', 'POST'])
@login_required
def architect_breakdown(quest_id):
    quest = db.session.get(Quest, quest_id)
    if not quest or quest.player_id != current_user.id:
        flash("Quest not found or access denied.", "error")
        return redirect(url_for('main.dashboard'))

    # GET: Show Confirmation Page
    if request.method == 'GET':
        return render_template('confirm_breakdown.html', quest=quest)

    # POST: Execute Breakdown
    sub_tasks = TheArchitect.decompose_task(quest.title)
    
    if not sub_tasks or len(sub_tasks) == 0:
        flash("The Architect could not decompose this task.", "warning")
        return redirect(url_for('main.dashboard'))

    created_count = 0

    for task_data in sub_tasks:
        # Extract data (handle both string list and dict list for backward compatibility)
        if isinstance(task_data, str):
            title = task_data
            rank = 'E'
            priority = 4
        else:
            title = task_data.get('step', 'Unknown Task')
            rank = task_data.get('rank', 'E')
            priority = task_data.get('priority', 4)

        # Create sub-quest with explicit properties
        new_quest = Quest(
            title=title,
            rank=rank,
            xp_reward=10, # Could also ask AI for XP, but standard sub-task reward is fine
            stat_reward=quest.stat_reward or 'INT',
            player_id=current_user.id,
            is_daily=False, # Sub-tasks are usually one-off
            priority=priority
        )
        db.session.add(new_quest)
        created_count += 1
    
    db.session.commit()
    flash(f"Decomposition Complete: {created_count} sub-quests created.", "success")
    return redirect(url_for('main.dashboard'))

@bp.route('/claim_purchase/<int:log_id>', methods=['POST'])
@login_required
def claim_purchase(log_id):
    buy_log = db.session.get(PurchaseLog, log_id)
    
    if not buy_log or buy_log.player_id != current_user.id:
        flash("Invalid item.", "error")
        return redirect(url_for('main.dashboard'))
        
    if buy_log.is_claimed:
        flash("Already claimed.", "warning")
    else:
        buy_log.is_claimed = True
        buy_log.claimed_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Consumed: {buy_log.item_name}", "success")
        
    return redirect(url_for('main.dashboard'))

from app.services import equip_title_service

@bp.route('/equip_title/<int:title_id>', methods=['POST'])
@login_required
def equip_title_route(title_id):
    success, msg = equip_title_service(current_user, title_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
    return redirect(url_for('main.dashboard'))

@bp.route('/job_qualification')
@login_required
def job_qualification():
    if current_user.job_class != 'None':
        flash("You have already chosen a path.", "warning")
        return redirect(url_for('main.dashboard'))
    
    if current_user.level < 10:
        flash("You are not yet ready. (Level 10 Required)", "error")
        return redirect(url_for('main.dashboard'))
        
    return redirect(url_for('main.job_test'))

@bp.route('/job_test', methods=['GET', 'POST'])
@login_required
def job_test():
    if current_user.job_class != 'None':
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        q1 = request.form.get('q1')
        q2 = request.form.get('q2')
        q3 = request.form.get('q3')
        
        # Simple Logic: Majority wins. Tie-break: Q3 (Weapon)
        answers = [q1, q2, q3]
        counts = {'A': answers.count('A'), 'B': answers.count('B'), 'C': answers.count('C')}
        
        # Determine winner
        winner = max(counts, key=counts.get)
        
        # Handle Tie (if max count appears more than once, use Q3)
        if list(counts.values()).count(counts[winner]) > 1:
            winner = q3
            
        job_map = {
            'A': 'Assassin',
            'B': 'Mage',
            'C': 'Tank'
        }
        
        selected_class = job_map.get(winner, 'Fighter')
        
        current_user.job_class = selected_class
        db.session.commit()
        
        flash(f"SYSTEM: Class Change Complete. You are now a {selected_class.upper()}.", "system_popup")
        return redirect(url_for('main.dashboard'))
        
    return render_template('job_test.html')

from app.services import equip_item_service, unequip_item_service

@bp.route('/inventory')
@login_required
def inventory():
    return render_template('inventory.html', player=current_user)

@bp.route('/equip_item/<int:inv_id>', methods=['POST'])
@login_required
def equip_item_route(inv_id):
    success, msg = equip_item_service(current_user, inv_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")
        
    if request.form.get('redirect_to') == 'inventory':
        return redirect(url_for('main.inventory'))
    return redirect(url_for('main.dashboard'))

@bp.route('/unequip_item/<int:inv_id>', methods=['POST'])
@login_required
def unequip_item_route(inv_id):
    success, msg = unequip_item_service(current_user, inv_id)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")

    if request.form.get('redirect_to') == 'inventory':
        return redirect(url_for('main.inventory'))
    return redirect(url_for('main.dashboard'))

@bp.route('/update_penalty', methods=['POST'])
@login_required
def update_penalty():
    new_desc = request.form.get('penalty_description')
    
    if not new_desc or not new_desc.strip():
        flash("Description cannot be empty.", "error")
        return redirect(url_for('main.dashboard'))
        
    if current_user.coins < 250:
        flash("Msng. Funds. Rqd: 250 Coins.", "error") # Compact message for style
        return redirect(url_for('main.dashboard'))
        
    # Process Transaction
    current_user.coins -= 250
    current_user.penalty_description = new_desc.strip()
    db.session.commit()
    
    flash(f"PENALTY PROTOCOL REWRITTEN. -250 COINS.", "system_popup")
    return redirect(url_for('main.dashboard'))

@bp.route('/use_item/<int:inv_id>', methods=['POST'])
@login_required
def use_item_route(inv_id):
    """ Consumes a consumable item. """
    item_record = db.session.get(Inventory, inv_id)
    if not item_record or item_record.player_id != current_user.id:
        flash("Item not found.", "error")
        return redirect(url_for('main.dashboard'))
        
    if item_record.item.item_type == 'equipment':
        flash("Cannot consume equipment.", "error")
        return redirect(url_for('main.dashboard'))
        
    # Effect Logic
    item_def = item_record.item
    
    # SPECIAL ITEMS
    if item_def.name == "Elixir of Life":
        if current_user.condition == "WELL RESTED":
            flash("You are already fully rested. Save the Elixir.", "error")
            return redirect(url_for('main.inventory'))
            
        current_user.condition = "WELL RESTED"
        current_user.last_sleep_duration = max(8.0, current_user.last_sleep_duration or 0)
        current_user.sleep_streak += 1
        
        db.session.delete(item_record)
        db.session.commit()
        
        flash("ELIXIR OF LIFE CONSUMED: Fatigue cured. Condition restored to BEST.", "system_popup")
        return redirect(url_for('main.inventory'))
        
    if item_def.name == "Night Out with Friends":
        from app.services import auto_complete_dailies
        count, msg = auto_complete_dailies(current_user)
        flash(msg, "success" if count > 0 else "info")
        
        # Consume item
        db.session.delete(item_record)
        db.session.commit()
        
        return redirect(url_for('main.dashboard'))

    # Stat Boosts (Permanent)
    if item_def.stat_bonus and item_def.stat_value > 0:
        stat_map = {
            'STR': 'strength', 'INT': 'intelligence', 'AGI': 'agility', 'VIT': 'vitality', 'SNS': 'sense'
        }
        attr_name = stat_map.get(item_def.stat_bonus)
        if attr_name:
            current_val = getattr(current_user, attr_name)
            setattr(current_user, attr_name, current_val + item_def.stat_value)
            flash(f"Effect: {item_def.stat_bonus} increased by {item_def.stat_value}!", "levelup")
            
    item_name = item_def.name
    db.session.delete(item_record)
    db.session.commit()
    
    flash(f"Used: {item_name}", "success")
    
    if request.form.get('redirect_to') == 'inventory':
        return redirect(url_for('main.inventory'))
    return redirect(url_for('main.dashboard'))

@bp.route('/shop')
@login_required
def shop():
    player = current_user
    
    # Get shop items
    shop_items = RewardItem.query.filter(or_(RewardItem.stock == -1, RewardItem.stock > 0)).order_by(RewardItem.currency, RewardItem.item_type, RewardItem.cost).all()
    
    # Get purchase history since last reset
    purchase_history = []
    if player.last_weekly_reset:
         purchase_history = PurchaseLog.query.filter(
             PurchaseLog.player_id == player.id,
             PurchaseLog.purchased_at >= player.last_weekly_reset
         ).order_by(PurchaseLog.purchased_at.desc()).all()
         
         
    # Get IDs of owned items to handle "Sold Out" / "Owned" state
    owned_item_ids = {inv.item_id for inv in player.inventory}
         
    return render_template('shop.html', player=player, shop_items=shop_items, purchase_history=purchase_history, owned_item_ids=owned_item_ids)

@bp.route('/arise/<int:quest_id>', methods=['POST'])
@login_required
def arise_route(quest_id):
    success, msg = extract_shadow(current_user, quest_id)
    if success:
        flash(msg, "success") 
        flash(msg, "system_popup") 
        # Add visual flare trigger
        flash("shadow_born", "shadow_born")
    else:
        flash(msg, "error")
    return redirect(url_for('main.dashboard'))

@bp.route('/analytics')
@login_required
def analytics():
    # Fetch snapshots
    snapshots = DailySnapshot.query.filter_by(player_id=current_user.id).order_by(DailySnapshot.date.asc()).limit(30).all()
    
    # Heatmap Data (Last 365 Days)
    one_year_ago = datetime.now(timezone.utc).date() - timedelta(days=365)
    year_snapshots = DailySnapshot.query.filter(
        DailySnapshot.player_id == current_user.id,
        DailySnapshot.date >= one_year_ago
    ).all()
    activity_map = {s.date.strftime('%Y-%m-%d'): s.quests_completed for s in year_snapshots}
    
    # Prepare data for Chart.js
    dates = [s.date.strftime('%Y-%m-%d') for s in snapshots]
    
    # Growth metric: Total Stats (Sum of all attributes) - Shows daily effort better than Level
    growth_data = [s.total_stats for s in snapshots]
    if not growth_data and current_user.snapshots:
         # Fallback if snapshots exist but are empty for some reason
         growth_data = [s.level for s in snapshots]
         
    # If no snapshots yet, provide current state as a single point
    if not snapshots:
        dates = [datetime.now().strftime('%Y-%m-%d')]
        # Calculate current total stats
        current_total = current_user.strength + current_user.intelligence + current_user.agility + current_user.vitality + current_user.sense
        growth_data = [current_total]
    
    return render_template('analytics.html', dates=dates, growth_data=growth_data, activity_map=activity_map)

@bp.route('/focus')
@login_required
def focus_mode():
    return render_template('focus.html')


@bp.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    audio = request.json.get('audio')
    music = request.json.get('music')
    volume = request.json.get('volume')
    
    if audio is not None:
        current_user.settings_audio = audio
    if music is not None:
        current_user.settings_music = music
    if volume is not None:
        current_user.settings_volume = float(volume)
        
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/focus_complete', methods=['POST'])
@login_required
def focus_complete():
    try:
        minutes = int(request.json.get('minutes', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'msg': "Invalid duration."})
        
    if minutes < 1:
        return jsonify({'success': False, 'msg': "Too short."})
        
    # Rewards: Coins scale to 1 per 6 mins (10/hr). XP scales to ~2.5% of level cap per hour.
    coins = int(minutes / 6.0)
    
    xp_scaling_factor = 0.025
    xp_cap = current_user.xp_required if current_user.xp_required > 0 else 100
    xp = max(1, int((minutes / 60.0) * (xp_scaling_factor * xp_cap)))
    
    current_user.coins += coins
    current_user.xp += xp
    current_user.daily_focus_duration += minutes
    
    from app.services import process_level_up
    level_up = process_level_up(current_user)
    
    db.session.commit()
    
    if level_up:
        flash("LEVEL UP!", "levelup")
        
    if hasattr(current_user, 'just_evolved') and current_user.just_evolved:
        flash(f"CLASS EVOLVED: You are now a {current_user.just_evolved}!", "system_popup")
        
    if hasattr(current_user, 'just_ranked_up') and current_user.just_ranked_up:
        flash(f"RANK UP: You have reached {current_user.just_ranked_up}-Rank!", "system_popup")
    
    msg = f"FOCUS COMPLETE: {minutes}m. +{coins} Coins, +{xp} XP."
    return jsonify({'success': True, 'msg': msg})
@bp.route('/setup', methods=['GET', 'POST'])
@login_required
def setup_page():
    if current_user.setup_complete:
        flash("System already initialized.", "warning")
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        # 1. Create 4 Daily Quests
        q1 = request.form.get('quest1')
        q2 = request.form.get('quest2')
        q3 = request.form.get('quest3')
        q4 = request.form.get('quest4')
        
        # 2. Set Penalty Description
        penalty = request.form.get('penalty')
        
        if not all([q1, q2, q3, q4, penalty]):
            flash("ALL PARAMETERS REQUIRED FOR SYSTEM INITIALIZATION.", "error")
            return render_template('setup.html')
            
        # Create Quests
        quests_data = [
            {'title': q1, 'rank': request.form.get('quest1_rank', 'E'), 'stat': request.form.get('quest1_stat', 'STR'), 'desc': request.form.get('quest1_description')},
            {'title': q2, 'rank': request.form.get('quest2_rank', 'E'), 'stat': request.form.get('quest2_stat', 'STR'), 'desc': request.form.get('quest2_description')},
            {'title': q3, 'rank': request.form.get('quest3_rank', 'E'), 'stat': request.form.get('quest3_stat', 'STR'), 'desc': request.form.get('quest3_description')},
            {'title': q4, 'rank': request.form.get('quest4_rank', 'E'), 'stat': request.form.get('quest4_stat', 'STR'), 'desc': request.form.get('quest4_description')},
        ]

        xp_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}

        for q_data in quests_data:
            xp_reward = xp_map.get(q_data['rank'], 10)
            quest = Quest(
                title=q_data['title'],
                description=q_data['desc'],
                rank=q_data['rank'],
                xp_reward=xp_reward,
                stat_reward=q_data['stat'],
                player_id=current_user.id,
                is_daily=True
            )
            db.session.add(quest)
            
        # Update Player
        current_user.penalty_description = penalty
        current_user.penalty_detail = request.form.get('penalty_detail')
        current_user.setup_complete = True
        
        db.session.commit()
        
        flash("SYSTEM INITIALIZATION COMPLETE. WELCOME, PLAYER.", "levelup")
        return redirect(url_for('main.dashboard'))
        
    return render_template('setup.html')

@bp.route('/vacation/start', methods=['POST'])
@login_required
def start_vacation_route():
    days = int(request.form.get('days', 7))
    success, msg = start_vacation(current_user, days)
    if success:
        flash(msg, "system_popup")
    else:
        flash(msg, "system_popup")
    return redirect(url_for('main.dashboard'))

@bp.route('/vacation/end', methods=['POST'])
@login_required
def end_vacation_route():
    success, msg = end_vacation(current_user)
    if success:
        flash(msg, "system_popup")
    else:
        flash(msg, "error")
    return redirect(url_for('main.dashboard'))

# --- NOTIFICATION API ---

@bp.route('/api/notifications/all')
@login_required
def get_all_notifications():
    # Fetch all recent notifications for the Inbox
    notifs = Notification.query.filter_by(player_id=current_user.id).order_by(Notification.created_at.desc()).limit(50).all()
    data = [{
        'id': n.id,
        'message': n.message,
        'category': n.category,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat()
    } for n in notifs]
    return jsonify(data)

@bp.route('/api/notifications/mark_read', methods=['POST'])
@login_required
def mark_notifications_read():
    ids = request.json.get('ids', [])
    if ids:
        Notification.query.filter(Notification.id.in_(ids), Notification.player_id == current_user.id).update({Notification.is_read: True}, synchronize_session=False)
        db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/notifications/mark_read_all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(player_id=current_user.id, is_read=False).update({Notification.is_read: True}, synchronize_session=False)
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/notifications/clear', methods=['POST'])
@login_required
def clear_notifications():
    Notification.query.filter_by(player_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'success': True})

# --- WEB PUSH API ---

import os

@bp.route('/service-worker.js')
def service_worker():
    # Service worker needs to be at the root scope
    return send_from_directory('static', 'service-worker.js', mimetype='application/javascript')

@bp.route('/api/vapid_public_key')
def vapid_public_key():
    return jsonify({'public_key': os.getenv('VAPID_PUBLIC_KEY')})


@bp.route('/api/notifications/subscribe', methods=['POST'])
@login_required
def subscribe_push():
    sub_data = request.json
    if not sub_data or 'endpoint' not in sub_data or 'keys' not in sub_data:
        return jsonify({'error': 'Invalid subscription data'}), 400

    endpoint = sub_data['endpoint']
    p256dh = sub_data['keys'].get('p256dh')
    auth = sub_data['keys'].get('auth')

    # Check if this endpoint is already registered
    existing_sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    
    if existing_sub:
        # Update user binding if device transferred
        if existing_sub.player_id != current_user.id:
            existing_sub.player_id = current_user.id
            db.session.commit()
    else:
        new_sub = PushSubscription(
            player_id=current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth
        )
        db.session.add(new_sub)
        db.session.commit()

    return jsonify({'success': True})

@bp.route('/api/notifications/unsubscribe', methods=['POST'])
@login_required
def unsubscribe_push():
    sub_data = request.json
    if not sub_data or 'endpoint' not in sub_data:
        return jsonify({'error': 'Invalid unsubscribe data'}), 400

    endpoint = sub_data['endpoint']
    
    # Check if this endpoint is registered and delete it
    existing_sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing_sub:
        db.session.delete(existing_sub)
        db.session.commit()
        return jsonify({'success': True, 'msg': 'Subscription removed'})
        
    return jsonify({'success': False, 'msg': 'Subscription not found'}), 404

@bp.route('/allocate_points', methods=['POST'])
@login_required
def allocate_points():
    try:
        # Expecting JSON: {"STR": 1, "INT": 2, ...}
        # Or Form data if simpler? Let's support both but assume JSON for dynamic UI.
        data = request.json or request.form
        
        distribution = {
            'STR': int(data.get('STR', 0)),
            'INT': int(data.get('INT', 0)),
            'AGI': int(data.get('AGI', 0)),
            'VIT': int(data.get('VIT', 0)),
            'SNS': int(data.get('SNS', 0))
        }
        
    except (ValueError, TypeError):
        if request.json:
            return jsonify({'success': False, 'msg': "Invalid input."})
        flash("Invalid input.", "error")
        return redirect(url_for('main.dashboard'))
        
    success, msg = allocate_attributes(current_user, distribution)
    
    if request.json or request.is_json:
        return jsonify({'success': success, 'msg': msg})
        
    flash(msg, "success" if success else "error")
    return redirect(url_for('main.dashboard'))
