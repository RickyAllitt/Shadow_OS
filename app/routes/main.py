from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import Player, Quest, RewardItem, QuestComment, PurchaseLog, Inventory, DailySnapshot
from app.services import (check_weekly_reset, check_daily_reset, get_categorized_quests, 
                          calculate_rewards, process_quest_completion, ensure_welcome_quest, 
                          calculate_total_stats, extract_shadow, start_vacation, end_vacation)
from datetime import datetime, timezone

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required
def dashboard():
    if check_weekly_reset(current_user):
        flash("WEEKLY RESET: Gold has been reset to 0.", "system_popup")
    
    if check_daily_reset(current_user):
        flash("DAILY RESET: Daily quests have been refreshed.", "system_popup")

    player = current_user
    
    check_daily_reset(player)
    
    # Get Items
    dailies, scheduled, backlog = get_categorized_quests(player.id)
    
    # Onboarding Check
    if not player.setup_complete:
        return redirect(url_for('main.setup_page'))
    
    # Get Items
    dailies, scheduled, backlog = get_categorized_quests(player.id)
    
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
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
    if request.form.get('due_date'):
        due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d')

    # Auto-Evaluation Logic
    if rank == 'Auto':
        analysis = TheArchitect.analyze_quest(title)
        rank = analysis['rank']
        xp = analysis['xp']
        stat = analysis['stat']
        flash(f"System Analysis: Rank {rank} | Stat {stat} | XP {xp}", "info")
    else:
        xp_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}
        # Use centralized logic, or stick to this if we want to preview?
        # Better:
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



@bp.route('/buy/<int:item_id>')
@login_required
def buy_item(item_id):
    item = db.session.get(RewardItem, item_id)
    player = current_user
    
    # PENALTY CHECK
    if player.in_penalty_zone:
        flash("SYSTEM LOCK: Cannot access shop in Penalty Zone.", "error")
        return redirect(url_for('main.dashboard'))
    
    if not item:
        return redirect(url_for('main.dashboard'))
        
    if player.gold >= item.cost:
        # Check stock
        if item.stock != -1:
            if item.stock <= 0:
                flash("Out of Stock.", "error")
                return redirect(url_for('main.dashboard'))
            else:
                item.stock -= 1

        # Deduct Cost
        if item.currency == 'coins':
            if player.coins < item.cost:
               flash("Not enough coins.", "error")
               return redirect(url_for('main.dashboard'))
            player.coins -= item.cost
        else:
            player.gold -= item.cost
            
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
    else:
        if request.args.get('json'):
             return jsonify({'success': False, 'message': "Insufficient Funds."})
        flash("Insufficient Funds.", "error")
    
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
        
    # Calculate Penalty
    # E: 10, D: 20, C: 50, B: 100, A: 200, S: 500
    penalty_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}
    penalty = penalty_map.get(quest.rank, 10)
    
    if request.method == 'POST':
        # Check if user has enough gold
        if current_user.gold >= penalty:
            current_user.gold -= penalty
            db.session.delete(quest)
            db.session.commit()
            flash(f"Quest Abandoned. You lost {penalty} G.", "system_popup")
        else:
             # Should be caught by GET check generally, but for safety:
            flash("You cannot afford to run away. Earn more gold or finish the quest.", "error_modal")
            
        return redirect(url_for('main.dashboard'))
    
    # GET: Pre-screen funds
    if current_user.gold < penalty:
        flash(f"INSUFFICIENT FUNDS: You need {penalty} G to abandon this quest.", "error_modal")
        return redirect(url_for('main.dashboard'))
    
    return render_template('abandon_quest.html', quest=quest, penalty=penalty)

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
        # Restriction Check for Dailies
        if quest.is_daily:
            # Only allow progress and comments
            try:
                 quest.progress = int(request.form.get('progress', 0))
            except ValueError:
                 pass
                 
            # New Comment
            new_comment_text = request.form.get('new_comment')
            if new_comment_text and new_comment_text.strip():
                comment = QuestComment(content=new_comment_text.strip(), quest_id=quest.id)
                db.session.add(comment)
                
            db.session.commit()
            flash("Daily Quest updated (Progress/Notes only).", "system_popup")
            return redirect(url_for('main.dashboard'))

        # Normal Quest Logic
        quest.title = request.form.get('title')
        quest.description = request.form.get('description')
        quest.rank = request.form.get('rank')
        quest.stat_reward = request.form.get('stat')
        
        start_str = request.form.get('start_date')
        due_str = request.form.get('due_date')
        
        quest.start_date = datetime.strptime(start_str, '%Y-%m-%d') if start_str else None
        quest.due_date = datetime.strptime(due_str, '%Y-%m-%d') if due_str else None
        
        quest.is_daily = True if request.form.get('is_daily') else False
        quest.priority = int(request.form.get('priority', 4))
        
        # Progress
        try:
             quest.progress = int(request.form.get('progress', 0))
        except ValueError:
             pass
             
        # New Comment
        new_comment_text = request.form.get('new_comment')
        if new_comment_text and new_comment_text.strip():
            comment = QuestComment(content=new_comment_text.strip(), quest_id=quest.id)
            db.session.add(comment)
        
        # Recalculate XP if rank changes? Yes.
        xp_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}
        quest.xp_reward = xp_map.get(quest.rank, 10)
        
        db.session.commit()
        flash("Quest updated.", "system_popup")
        return redirect(url_for('main.dashboard'))
        
    # Reuse dashboard? Or render a specific edit page?
    # Simple edit page.
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
    for task_title in sub_tasks:
        # Create sub-quest with explicit properties
        new_quest = Quest(
            title=task_title,
            rank='E',
            xp_reward=10,
            stat_reward=quest.stat_reward or 'INT',
            player_id=current_user.id,
            is_daily=False # Sub-tasks are usually one-off
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
         
    return render_template('shop.html', player=player, shop_items=shop_items, purchase_history=purchase_history)

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
    
    # Prepare data for Chart.js
    dates = [s.date.strftime('%Y-%m-%d') for s in snapshots]
    # Simple growth metric: Level
    levels = [s.level for s in snapshots]
    
    # Stats for Radar
    stats = {
        'STR': current_user.strength,
        'INT': current_user.intelligence,
        'AGI': current_user.agility,
        'VIT': current_user.vitality,
        'SNS': current_user.sense
    }
    
    return render_template('analytics.html', dates=dates, levels=levels, stats=stats)

@bp.route('/focus')
@login_required
def focus_mode():
    return render_template('focus.html')

@bp.route('/focus_complete', methods=['POST'])
@login_required
def focus_complete():
    try:
        minutes = int(request.json.get('minutes', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'msg': "Invalid duration."})
        
    if minutes < 1:
        return jsonify({'success': False, 'msg': "Too short."})
        
    # Rewards: 1 Coin/min, 2 XP/min (Conservative)
    coins = minutes * 1
    xp = minutes * 2
    
    current_user.coins += coins
    current_user.xp += xp
    current_user.daily_focus_duration += minutes
    
    db.session.commit()
    
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
        for title in [q1, q2, q3, q4]:
            quest = Quest(
                title=title,
                rank='E',
                xp_reward=10,
                stat_reward='STR', # Default, user can edit later
                player_id=current_user.id,
                is_daily=True
            )
            db.session.add(quest)
            
        # Update Player
        current_user.penalty_description = penalty
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
