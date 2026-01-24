from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db
from app.models import Player, Quest, RewardItem, QuestComment
from app.services import check_weekly_reset, check_daily_reset, get_categorized_quests
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

@bp.route('/add_quest', methods=['POST'])
@login_required
def add_quest():
    title = request.form.get('title')
    rank = request.form.get('rank')
    stat = request.form.get('stat')
    
    # Dates
    start_str = request.form.get('start_date')
    due_str = request.form.get('due_date')
    
    start_date = datetime.strptime(start_str, '%Y-%m-%d') if start_str else None
    due_date = datetime.strptime(due_str, '%Y-%m-%d') if due_str else None
    
    # Daily Checkbox
    is_daily = True if request.form.get('is_daily') else False
    
    # Simple logic: Higher rank = More XP
    xp_map = {'E': 10, 'D': 20, 'C': 50, 'B': 100, 'A': 200, 'S': 500}
    
    new_quest = Quest(
        title=title, 
        rank=rank, 
        stat_reward=stat, 
        xp_reward=xp_map.get(rank, 10), 
        player=current_user,
        start_date=start_date,
        due_date=due_date,
        is_daily=is_daily
    )
    db.session.add(new_quest)
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
        quest.is_completed = True
        player.xp += quest.xp_reward
        
        # Stat Buff Logic
        if quest.stat_reward == 'STR': player.strength += 1
        elif quest.stat_reward == 'INT': player.intelligence += 1
        elif quest.stat_reward == 'AGI': player.agility += 1
        
        # Level Up Logic
        if player.xp >= player.xp_required:
            player.level += 1
            player.xp -= player.xp_required
            player.xp_required = int(player.xp_required * 1.2)
            
            # TRIGGER THE NOTIFICATION
            flash('LEVEL UP!', 'levelup') 
            
        db.session.commit()
        
    return redirect(url_for('main.dashboard'))

@bp.route('/trigger_penalty')
@login_required
def trigger_penalty():
    player = current_user
    player.in_penalty_zone = True
    
    # Create the Punishment Quest
    punishment = Quest(
        title="PENALTY: 4 Hours No Phone",
        rank="S", # Hard
        xp_reward=0, # No gain, just survival
        gold_reward=0,
        is_penalty=True,
        stat_reward="VIT" # You strictly gain discipline (VIT)
    )
    db.session.add(punishment)
    db.session.commit()
    
    flash("YOU HAVE ENTERED THE PENALTY ZONE.", "penalty")
    return redirect(url_for('main.dashboard'))

@bp.route('/clear_penalty/<int:quest_id>')
@login_required
def clear_penalty(quest_id):
    quest = db.session.get(Quest, quest_id)
    player = current_user
    
    if quest.is_penalty:
        db.session.delete(quest) # Remove the quest
        player.in_penalty_zone = False
        flash("SURVIVAL COMPLETE. PENALTY LIFTED.", "success")
        db.session.commit()
        
    return redirect(url_for('main.dashboard'))

@bp.route('/buy/<int:item_id>')
@login_required
def buy_item(item_id):
    player = current_user
    item = db.session.get(RewardItem, item_id)
    
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for('main.dashboard'))

    # RULE 1: The Penalty Zone Lock
    if player.in_penalty_zone:
        flash("⛔ ACCESS DENIED: Complete Penalty Quest first.", "error")
        return redirect(url_for('main.dashboard'))

    # RULE 2: Gold Check
    if player.gold >= item.cost:
        # Transaction
        player.gold -= item.cost
        
        # Handle Limited Stock (if item is not infinite)
        if item.stock > 0:
            item.stock -= 1
            
        db.session.commit()
        
        # Success Feedback
        flash(f"PURCHASE SUCCESSFUL: {item.name}", "success")
        
    else:
        flash("INSUFFICIENT FUNDS.", "error")

    return redirect(url_for('main.dashboard'))

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

