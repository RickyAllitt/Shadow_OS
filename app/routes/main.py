from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import Player, Quest, RewardItem, QuestComment
from app.services import check_weekly_reset, check_daily_reset, get_categorized_quests, calculate_rewards, process_quest_completion
from datetime import datetime

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required
def dashboard():
    if check_weekly_reset(current_user):
        flash("WEEKLY RESET: Gold has been reset to 0.", "warning")
    
    if check_daily_reset(current_user):
        flash("DAILY RESET: Daily quests have been refreshed.", "info")

    player = current_user
    
    # FETCH ALL ACTIVE QUESTS via Service
    dailies, scheduled, backlog = get_categorized_quests(player.id)
    
    # Get shop items (where stock is infinite (-1) OR stock > 0)
    shop_items = RewardItem.query.filter(or_(RewardItem.stock == -1, RewardItem.stock > 0)).all()
    
    return render_template('dashboard.html', player=player, 
                           dailies=dailies, scheduled=scheduled, backlog=backlog, 
                           shop_items=shop_items)

from app.ai_guardian import TheArchitect

@bp.route('/add_quest', methods=['POST'])
@login_required
def add_quest():
    title = request.form.get('title')
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
        xp, _ = calculate_rewards(rank)
    
    quest = Quest(
        title=title, 
        rank=rank, 
        xp_reward=xp, 
        stat_reward=stat,
        player_id=current_user.id,
        is_daily=is_daily,
        start_date=start_date,
        due_date=due_date
    )
    
    db.session.add(quest)
    db.session.commit()
    
    flash(f"Quest '{title}' Accepted.", "success")
    return redirect(url_for('main.dashboard'))

@bp.route('/complete/<int:id>', methods=['GET', 'POST'])
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
    if not quest.is_completed:
        xp_gain, gold_gain, level_up = process_quest_completion(player, quest)
        
        # Feedback
        flash(f"COMPLETE: {quest.title} | +{xp_gain} XP | +{gold_gain} G", "success")
        
        if level_up:
            flash("LEVEL UP!", "levelup")
            
        if quest.is_penalty:
            flash("PENALTY CLEARED. WELCOME BACK.", "success")
        
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
        if item.stock != -1 and item.stock <= 0:
            flash("Out of Stock.", "error")
        else:
            player.gold -= item.cost
            if item.stock > 0:
                item.stock -= 1
            db.session.commit()
            flash(f"Purchased: {item.name}", "success")
    else:
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
    
    # --- THE SYSTEM LOGIC ---
    if hours >= 7.5:
        player.condition = "WELL RESTED"
        player.sleep_streak += 1
        # Buff: Restores HP/MP (Visual)
        flash(f"SLEEP: {hours}h. CONDITION: BEST. (XP GAIN +10%)", "success")
        
    elif hours >= 6:
        player.condition = "NORMAL"
        flash(f"SLEEP: {hours}h. CONDITION: NORMAL.", "success")
        
    else:
        player.condition = "TIRED"
        player.sleep_streak = 0
        # Debuff: Warning
        flash(f"SLEEP: {hours}h. WARNING: RECOVERY INCOMPLETE. (XP GAIN REDUCED)", "error")
        
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
            flash(f"Quest Abandoned. You lost {penalty} G.", "warning")
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
        quest.title = request.form.get('title')
        quest.rank = request.form.get('rank')
        quest.stat_reward = request.form.get('stat')
        
        start_str = request.form.get('start_date')
        due_str = request.form.get('due_date')
        
        quest.start_date = datetime.strptime(start_str, '%Y-%m-%d') if start_str else None
        quest.due_date = datetime.strptime(due_str, '%Y-%m-%d') if due_str else None
        
        quest.is_daily = True if request.form.get('is_daily') else False
        
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
        flash("Quest updated.", "success")
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


