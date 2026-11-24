from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import login_required, current_user
from sqlalchemy import or_
from app.extensions import db, csrf
from app.models import Player, Quest, RewardItem, QuestComment, PurchaseLog, Inventory, DailySnapshot, Notification, PushSubscription, Title, Raid
from app.services import (check_weekly_reset, check_daily_reset, get_categorized_quests, 
                          process_quest_completion, 
                          calculate_total_stats, extract_shadow, start_vacation, end_vacation, allocate_attributes,
                          normalize_stat, check_title_unlocks, get_arise_candidates,
                          xp_multiplier, coin_multiplier, CONDITION_WELL_RESTED, CONDITION_NORMAL,
                          CONDITION_TIRED)
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

VALID_RANKS = ('E', 'D', 'C', 'B', 'A', 'S')

def normalize_rank(rank, default='E'):
    code = str(rank or '').strip().upper()
    return code if code in VALID_RANKS else default

def parse_priority(value, default=4):
    try:
        return min(4, max(1, int(value)))
    except (TypeError, ValueError):
        return default

def parse_metric_fields(form):
    """(target, unit) for a measured quest, or (None, None) when left blank / invalid."""
    raw_target = (form.get('metric_target') or '').strip()
    unit = (form.get('metric_unit') or '').strip()[:20]
    if not raw_target:
        return None, None
    try:
        target = float(raw_target)
    except ValueError:
        return None, None
    if not (0 < target <= 1_000_000):
        return None, None
    return target, unit or 'units'

def json_body():
    """Request JSON as a dict; {} for missing, malformed or non-object bodies."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}

def level_up_flash(player):
    """'<new level>|<levels gained>': parsed by SystemUI for the level-up overlay."""
    return f"{player.level}|{max(1, getattr(player, 'levels_gained', 1))}"

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required
def dashboard():
    if check_weekly_reset(current_user):
        before = getattr(current_user, 'weekly_gold_before', None)
        flash(f"WEEKLY RESET: Gold halved ({before:,} → {current_user.gold:,} G)." if before is not None
              else "WEEKLY RESET: Gold halved.", "system_popup")
    
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
    

    
    # Catch up on titles earned outside a level-up (streaks, stats, coins)
    for name in check_title_unlocks(player):
        flash(f"TITLE UNLOCKED: {name}", "system_popup")

    # Once a week: how last week's league ended
    from app import league, kpi, social
    social.finalize_expired_raids()
    results = league.weekly_results_message(player)
    if results:
        flash(results, "system_popup")

    # Calculate Total Stats (Base + Equipment + Debuffs)
    total_stats = calculate_total_stats(player)

    # Shadow extraction: candidates for the Army panel, plus the prompt right after an S-Rank clear
    arise_candidates = get_arise_candidates(player)
    arise_quest = None
    arise_id = request.args.get('arise', type=int)
    if arise_id:
        arise_quest = next((q for q in arise_candidates if q.id == arise_id), None)

    return render_template('dashboard.html', player=player, stats=total_stats,
                           dailies=dailies, scheduled=scheduled, backlog=backlog,
                           arise_candidates=arise_candidates, arise_quest=arise_quest,
                           all_titles=Title.query.order_by(Title.id).all(),
                           duel=league.rival_summary(player),
                           active_raids=Raid.query.filter_by(status='active').order_by(Raid.ends_at).limit(3).all(),
                           balance=kpi.life_balance(player),
                           metric_totals={q.id: kpi.metric_total(player, q)
                                          for q in dailies + scheduled + backlog if q.is_measured},
                           fmt=kpi.format_amount,
                           rank_slots=league.rank_slots_left(player),
                           rank_caps=league.WEEKLY_RANK_CAPS)

from app.ai_guardian import TheArchitect
from app.league import claim_rank

@bp.route('/add_quest', methods=['POST'])
@login_required
def add_quest():
    title = (request.form.get('title') or '').strip()
    description = request.form.get('description')
    rank = request.form.get('rank')

    if not title:
        flash("Quest title required.", "error")
        return redirect(url_for('main.dashboard'))
    title = title[:100]

    # Optional inputs
    stat = normalize_stat(request.form.get('stat'))
    is_daily = 'is_daily' in request.form
    
    start_date = None
    due_date = None
    if request.form.get('start_date'):
        start_date = parse_datetime_input(request.form.get('start_date'))
    if request.form.get('due_date'):
        due_date = parse_datetime_input(request.form.get('due_date'))

    # Auto-Evaluation Logic
    auto_ranked = rank == 'Auto'
    if auto_ranked:
        analysis = TheArchitect.analyze_quest(title)
        rank = normalize_rank(analysis.get('rank'))
        stat = normalize_stat(analysis.get('stat'))
        flash(f"System Analysis: Rank {rank} | Stat {stat}", "info")
    else:
        rank = normalize_rank(rank)

    # Weekly A/S caps (+ Architect second opinion on hand-picked A/S). Dailies give no rank XP: exempt.
    if not is_daily:
        rank, notes = claim_rank(current_user, rank, title, review=not auto_ranked)
        for note in notes:
            flash(note, "system_popup")

    # XP comes from the rank at completion time (see RANK_XP); xp_reward is legacy and unused.
    xp = 0

    priority = parse_priority(request.form.get('priority'))
    metric_target, metric_unit = parse_metric_fields(request.form)

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
        priority=priority,
        metric_target=metric_target,
        metric_unit=metric_unit,
    )
    
    db.session.add(quest)
    db.session.commit()
    
    flash(f"Quest '{title}' Accepted.", "system_popup")
    return redirect(url_for('main.dashboard'))

@bp.route('/complete/<int:id>', methods=['GET', 'POST'])
@login_required
def complete_quest(id):
    quest = db.session.get(Quest, id)
    player = current_user

    if not quest or quest.player_id != player.id:
        flash("Quest not found.", "error")
        return redirect(url_for('main.dashboard'))
        
    if quest.is_completed:
        flash(f"'{quest.title}' is already complete.", "info")
        return redirect(url_for('main.dashboard'))

    from app import kpi

    # GET: Show Verification Page (measured quests ask how much was done)
    if request.method == 'GET':
        total = kpi.metric_total(player, quest) if quest.is_measured else 0
        return render_template('verify_completion.html', quest=quest, metric_total=total,
                               fmt=kpi.format_amount)

    # Measured quest: log the amount; complete only once the target is reached
    metric_note = None
    if quest.is_measured:
        try:
            amount = float(request.form.get('amount', ''))
        except ValueError:
            amount = 0
        if not (0 < amount <= 1_000_000):
            flash(f"Enter how many {quest.metric_unit} you did.", "error")
            return redirect(url_for('main.complete_quest', id=quest.id))
        total, reached = kpi.log_metric(player, quest, amount)
        progress = f"{kpi.format_amount(total)}/{kpi.format_amount(quest.metric_target)} {quest.metric_unit}"
        if not reached:
            db.session.commit()
            flash(f"LOGGED: +{kpi.format_amount(amount)} {quest.metric_unit} · {progress}"
                  f"{' today' if quest.is_daily else ''}", "success")
            return redirect(url_for('main.dashboard'))
        metric_note = progress

    # POST: Execute Completion
    player.debt_paid = 0  # transient per-request counter (see services.add_xp)
    xp_gain, gold_gain, coin_gain, level_up, daily_bonus, can_arise = process_quest_completion(player, quest)
    
    # Feedback: only list what was actually gained
    parts = [f"COMPLETE: {quest.title}"]
    if metric_note:
        parts.append(metric_note)
    if quest.rank == 'S' and not quest.is_daily and not quest.is_penalty:
        parts.append("INSTANT LEVEL UP")
    elif xp_gain > 0:
        parts.append(f"+{xp_gain} XP")
    if getattr(player, 'debt_paid', 0):
        parts.append(f"{player.debt_paid} XP to debt ({player.xp_debt:,} left)" if player.xp_debt
                     else f"{player.debt_paid} XP to debt (DEBT CLEARED)")
    if gold_gain > 0:
        parts.append(f"+{gold_gain} G")
    if coin_gain > 0:
        parts.append(f"+{coin_gain} C")
    if quest.is_daily and not daily_bonus:
        dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
        parts.append(f"Dailies {sum(q.is_completed for q in dailies)}/{len(dailies)}")

    flash(" | ".join(parts), "quest_complete")
    
    if daily_bonus:
        bonus = getattr(player, 'daily_bonus_rewards', None) or {}
        flash(f"DAILY BONUS: All tasks completed! +{bonus.get('gold', 100)} Gold | "
              f"+{bonus.get('coins', 50)} Coins | +{bonus.get('xp', 0)} XP | "
              f"+{bonus.get('points', 3)} Ability Points", "system_popup")
    
    if level_up:
        flash(level_up_flash(player), "levelup")

    # Check for Evolution (Service attaches this attribute temporarily)
    if hasattr(player, 'just_evolved') and player.just_evolved:
        flash(f"CLASS EVOLVED: You are now a {player.just_evolved}!", "system_popup")
        
    # Check for Rank Up
    if hasattr(player, 'just_ranked_up') and player.just_ranked_up:
        flash(f"RANK UP: You have reached {player.just_ranked_up}-Rank!", "system_popup")
        
    if quest.is_penalty:
        flash("PENALTY CLEARED. WELCOME BACK.", "system_popup")

    for name in getattr(player, 'new_titles', []):
        flash(f"TITLE UNLOCKED: {name}", "system_popup")

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
        Quest.due_date < end_date,
        Quest.is_penalty == False
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
    from app import league, social
    view = 'all' if request.args.get('view') == 'all' else 'week'
    week = league.week_start_for()
    all_time = Player.query.order_by(Player.level.desc(), Player.xp.desc()).limit(20).all()
    last_week = [r for r in league.standings(week - timedelta(days=7)) if r['points'] > 0]
    return render_template('leaderboard.html', view=view, leaderboard=all_time,
                           weekly=league.standings(week), week_start=week,
                           week_ends=league.week_ends_at(week),
                           last_champion=last_week[0] if last_week else None,
                           rival_id=current_user.rivalry.rival_id if current_user.rivalry else None,
                           feats=social.recent_feats(), kudos_emoji=social.KUDOS_EMOJI)


# --- Raids (shared goals) ---

@bp.route('/raids')
@login_required
def raids():
    from app import social
    from app.models import Raid
    social.finalize_expired_raids()
    active = Raid.query.filter_by(status='active').order_by(Raid.ends_at).all()
    past = Raid.query.filter(Raid.status != 'active').order_by(Raid.created_at.desc()).limit(20).all()
    return render_template('raids.html', active=active, past=past, max_active=social.MAX_ACTIVE_RAIDS,
                           max_days=social.MAX_RAID_DAYS, reward_xp=social.RAID_REWARD_XP,
                           reward_coins=social.RAID_REWARD_COINS)


@bp.route('/raids/new', methods=['POST'])
@login_required
def create_raid_route():
    from app import social
    try:
        target = float(request.form.get('target', ''))
        days = int(request.form.get('days', ''))
    except ValueError:
        flash("Target and duration must be numbers.", "error")
        return redirect(url_for('main.raids'))
    raid, msg = social.create_raid(current_user, request.form.get('title'), request.form.get('unit'),
                                   target, days, request.form.get('stat', 'STR'))
    flash(msg, "system_popup" if raid else "error")
    return redirect(url_for('main.raid_detail', raid_id=raid.id) if raid else url_for('main.raids'))


@bp.route('/raids/<int:raid_id>')
@login_required
def raid_detail(raid_id):
    from app import social
    from app.models import Raid
    social.finalize_expired_raids()
    raid = db.session.get(Raid, raid_id)
    if not raid:
        flash("Raid not found.", "error")
        return redirect(url_for('main.raids'))
    return render_template('raid_detail.html', raid=raid, ranking=social.raid_leaderboard(raid),
                           reward_xp=social.RAID_REWARD_XP, reward_coins=social.RAID_REWARD_COINS)


@bp.route('/raids/<int:raid_id>/log', methods=['POST'])
@login_required
def raid_log(raid_id):
    from app import social
    from app.models import Raid
    raid = db.session.get(Raid, raid_id)
    if not raid:
        flash("Raid not found.", "error")
        return redirect(url_for('main.raids'))
    try:
        amount = float(request.form.get('amount', ''))
    except ValueError:
        amount = 0
    ok, msg = social.contribute(current_user, raid, amount)
    flash(msg, ("system_popup" if raid.status == 'completed' else "success") if ok else "error")
    return redirect(url_for('main.raid_detail', raid_id=raid.id))


@bp.route('/raids/<int:raid_id>/cancel', methods=['POST'])
@login_required
def raid_cancel(raid_id):
    from app import social
    from app.models import Raid
    raid = db.session.get(Raid, raid_id)
    if not raid:
        flash("Raid not found.", "error")
        return redirect(url_for('main.raids'))
    ok, msg = social.cancel_raid(current_user, raid)
    flash(msg, "info" if ok else "error")
    return redirect(url_for('main.raids') if ok else url_for('main.raid_detail', raid_id=raid.id))


# --- Kudos on S-rank clears ---

@bp.route('/kudos/<int:event_id>', methods=['POST'])
@login_required
def give_kudos_route(event_id):
    from app import social
    from app.models import ActivityEvent
    ok, msg = social.give_kudos(current_user, db.session.get(ActivityEvent, event_id), request.form.get('emoji', ''))
    flash(msg, "success" if ok else "error")
    return redirect(url_for('main.leaderboard') + '#feats')


@bp.route('/rival/<int:player_id>', methods=['POST'])
@login_required
def set_rival_route(player_id):
    from app.league import set_rival
    ok, msg = set_rival(current_user, db.session.get(Player, player_id))
    flash(msg, "system_popup" if ok else "error")
    return redirect(request.referrer or url_for('main.leaderboard'))


@bp.route('/rival/clear', methods=['POST'])
@login_required
def clear_rival_route():
    from app.league import clear_rival
    _, msg = clear_rival(current_user)
    flash(msg, "info")
    return redirect(request.referrer or url_for('main.leaderboard'))

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
    try:
        hours = float(request.form.get('hours'))
    except (TypeError, ValueError):
        flash("Invalid sleep duration.", "error")
        return redirect(url_for('main.dashboard'))
    if not (0 <= hours <= 24):
        flash("Sleep duration must be between 0 and 24 hours.", "error")
        return redirect(url_for('main.dashboard'))

    # One log per game day (01:00-01:00 in the player's timezone)
    from app.services import get_latest_daily_reset_time, player_tz
    today = get_latest_daily_reset_time(tz=player_tz(player)).date()
    if player.last_sleep_log_date == today:
        flash("You have already logged sleep for today.", "system_popup")
        return redirect(url_for('main.dashboard'))

    player.last_sleep_duration = hours
    player.last_sleep_log_date = today
    from app.kpi import record_sleep
    record_sleep(player, hours)
    
    # --- THE SYSTEM LOGIC ---
    if hours >= 7.5:
        player.condition = CONDITION_WELL_RESTED
        player.sleep_streak += 1
        # Buff: Restores HP/MP (Visual)
        flash(f"SLEEP: {hours}h. CONDITION: BEST. (XP GAIN +10%)", "system_popup")
        
    elif hours >= 6:
        player.condition = CONDITION_NORMAL
        flash(f"SLEEP: {hours}h. CONDITION: NORMAL.", "system_popup")
        
    else:
        player.condition = CONDITION_TIRED
        player.sleep_streak = 0
        # Debuff: Warning
        flash(f"SLEEP: {hours}h. WARNING: RECOVERY INCOMPLETE. (XP GAIN -50%)", "system_popup")
        
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
        if new_rank is not None:
            new_rank = normalize_rank(new_rank, default=quest.rank)
        if new_stat is not None:
            new_stat = normalize_stat(new_stat, default=quest.stat_reward or 'INT')
        
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
            if new_priority_str is not None and parse_priority(new_priority_str, quest.priority) != quest.priority: restricted_modified = True
            
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
                if new_priority_str is not None: quest.priority = parse_priority(new_priority_str, quest.priority)
                if start_str is not None: quest.start_date = parse_datetime_input(start_str)
                if due_str is not None: quest.due_date = parse_datetime_input(due_str)
        else:
            # Normal Quest Logic
            if new_title is not None: quest.title = new_title
            will_be_daily = bool(request.form.get('is_daily'))
            if new_rank is not None and new_rank != quest.rank and not will_be_daily:
                # Promotions to A/S use a weekly slot (and get the Architect's second opinion)
                new_rank, notes = claim_rank(current_user, new_rank, quest.title)
                for note in notes:
                    flash(note, "system_popup")
            if new_rank is not None: quest.rank = new_rank
            if new_stat is not None: quest.stat_reward = new_stat
            if new_priority_str is not None: quest.priority = parse_priority(new_priority_str, quest.priority)
            if start_str is not None: quest.start_date = parse_datetime_input(start_str)
            if due_str is not None: quest.due_date = parse_datetime_input(due_str)
            quest.is_daily = True if request.form.get('is_daily') else False

        # Non-restricted updates (ALWAYS updated, free even for dailies)
        if new_description is not None:
            quest.description = new_description
        if 'metric_target' in request.form:
            quest.metric_target, quest.metric_unit = parse_metric_fields(request.form)

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
        
        # XP is scaled from rank + level at completion time
        quest.xp_reward = 0
        
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
    from app.ai_guardian import TheArchitect
    
    try:
        sub_tasks = TheArchitect.decompose_task(quest.title)
    except Exception as e:
        print(f"Architect breakdown exception: {e}")
        flash("The Architect encountered a critical error during task breakdown. Please try again.", "error")
        return redirect(url_for('main.dashboard'))
    
    if not sub_tasks or len(sub_tasks) == 0:
        flash("The Architect could not decompose this task.", "warning")
        return redirect(url_for('main.dashboard'))

    created_count = 0
    cap_notes = []

    for task_data in sub_tasks:
        # Extract data (handle both string list and dict list for backward compatibility)
        if isinstance(task_data, str):
            title = task_data
            rank = 'E'
            priority = 4
        else:
            title = task_data.get('step', 'Unknown Task')
            rank = normalize_rank(task_data.get('rank', 'E'))
            priority = parse_priority(task_data.get('priority', 4))
        # AI-assigned sub-quest ranks still count toward the weekly A/S caps
        rank, notes = claim_rank(current_user, rank, review=False)
        cap_notes.extend(notes)

        # Create sub-quest with explicit properties
        new_quest = Quest(
            title=str(title)[:100],
            rank=rank,
            xp_reward=0, # Scaled from rank + level at completion
            stat_reward=normalize_stat(quest.stat_reward),
            player_id=current_user.id,
            is_daily=False, # Sub-tasks are usually one-off
            priority=priority
        )
        db.session.add(new_quest)
        created_count += 1
    
    db.session.commit()
    flash(f"Decomposition Complete: {created_count} sub-quests created.", "success")
    for note in dict.fromkeys(cap_notes):  # de-duplicated, in order
        flash(note, "system_popup")
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

    return redirect(request.referrer or url_for('main.dashboard'))

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
    from app.job_trial import questions_for_display, score_answers, CLASS_PROFILES
    from app.services import class_evolution_path

    if current_user.job_class != 'None':
        return redirect(url_for('main.dashboard'))
    if current_user.level < 10:
        flash("You are not yet ready. (Level 10 Required)", "error")
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        chosen_class, _ = score_answers(request.form)
        if chosen_class is None:
            flash("The trial is incomplete. Answer every question.", "error")
            return render_template('job_test.html', questions=questions_for_display())

        current_user.job_class = chosen_class
        db.session.commit()
        # Reveal page (not a redirect): refreshing it just returns to the dashboard via the guard above
        return render_template('job_result.html', job_class=chosen_class,
                               profile=CLASS_PROFILES[chosen_class],
                               evolution_path=class_evolution_path(chosen_class))

    return render_template('job_test.html', questions=questions_for_display())

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
        if current_user.condition == CONDITION_WELL_RESTED:
            flash("You are already fully rested. Save the Elixir.", "error")
            return redirect(url_for('main.inventory'))
            
        current_user.condition = CONDITION_WELL_RESTED
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
            flash(f"Effect: {item_def.stat_bonus} increased by {item_def.stat_value}!", "success")
            
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
         
    from app.models import PersonalReward
    personal_rewards = PersonalReward.query.filter_by(player_id=player.id).order_by(PersonalReward.cost).all()
    to_redeem = PurchaseLog.query.filter_by(player_id=player.id, is_claimed=False) \
        .order_by(PurchaseLog.purchased_at.desc()).all()

    return render_template('shop.html', player=player, shop_items=shop_items, purchase_history=purchase_history,
                           owned_item_ids=owned_item_ids, personal_rewards=personal_rewards, to_redeem=to_redeem)

@bp.route('/arise/<int:quest_id>', methods=['POST'])
@login_required
def arise_route(quest_id):
    success, msg = extract_shadow(current_user, quest_id)
    if success:
        flash(msg, "arise_trigger")  # Shown as a popup with the Arise sound/VFX
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
    
    from app import kpi
    now_utc = datetime.now(timezone.utc)
    balance_now = kpi.area_scores(current_user, now_utc)
    balance_month_ago = kpi.area_scores(current_user, now_utc - timedelta(days=30))
    measures = []
    for q in Quest.query.filter(Quest.player_id == current_user.id, Quest.metric_target.isnot(None)).order_by(Quest.id):
        if q.is_measured:
            history = kpi.metric_history(current_user, q, days=30, now=now_utc)
            measures.append({'id': q.id, 'title': q.title, 'unit': q.metric_unit, 'target': q.metric_target,
                             'daily': q.is_daily, 'labels': [d.strftime('%d/%m') for d, _ in history],
                             'values': [v for _, v in history]})

    return render_template('analytics.html', dates=dates, growth_data=growth_data, activity_map=activity_map,
                           areas=list(kpi.AREAS), balance_now=[balance_now[a] for a in kpi.AREAS],
                           balance_before=[balance_month_ago[a] for a in kpi.AREAS], measures=measures)


@bp.route('/report')
@bp.route('/report/<week>')
@login_required
def weekly_report(week=None):
    """Weekly System Report. Default: last completed week; /report/YYYY-MM-DD for any week."""
    from app import kpi, league
    current_week = league.week_start_for()
    try:
        week_start = league.week_start_for(datetime.strptime(week, '%Y-%m-%d') + timedelta(hours=12)) if week \
            else current_week - timedelta(days=7)
    except ValueError:
        flash("Unknown week.", "error")
        return redirect(url_for('main.weekly_report'))
    report = kpi.weekly_report(current_user, week_start)
    return render_template('report.html', r=report,
                           prev_week=week_start - timedelta(days=7),
                           next_week=week_start + timedelta(days=7) if week_start < current_week else None,
                           fmt=kpi.format_amount)

@bp.route('/focus')
@login_required
def focus_mode():
    return render_template('focus.html')


@bp.route('/settings/locale', methods=['POST'])
@login_required
def update_locale():
    """Timezone (daily reset is 01:00 there) and daily reminder time."""
    from app.services import is_valid_timezone
    tz_name = (request.form.get('timezone') or '').strip()
    reminder = (request.form.get('reminder_time') or '').strip()
    if tz_name and not is_valid_timezone(tz_name):
        flash(f"Unknown timezone: {tz_name}", "error")
        return redirect(request.referrer or url_for('main.dashboard'))
    if reminder:
        try:
            datetime.strptime(reminder, '%H:%M')
        except ValueError:
            flash("Reminder time must look like 21:00.", "error")
            return redirect(request.referrer or url_for('main.dashboard'))
    if tz_name:
        current_user.timezone = tz_name
    current_user.reminder_time = reminder or None
    db.session.commit()
    flash(f"Saved: timezone {current_user.timezone}, "
          + (f"daily reminder at {reminder}." if reminder else "daily reminder off."), "success")
    return redirect(request.referrer or url_for('main.dashboard'))


@bp.route('/settings/hardcore', methods=['POST'])
@login_required
def toggle_hardcore():
    from app.services import set_hardcore
    ok, msg = set_hardcore(current_user, request.form.get('enable') == '1')
    flash(msg, "system_popup" if ok else "error")
    return redirect(request.referrer or url_for('main.dashboard'))


# --- Personal real-life rewards (priced in Gold by the player) ---

@bp.route('/rewards/add', methods=['POST'])
@login_required
def add_personal_reward():
    from app.models import PersonalReward
    name = (request.form.get('name') or '').strip()[:60]
    try:
        cost = int(request.form.get('cost', ''))
    except ValueError:
        cost = 0
    if not name or not (1 <= cost <= 1_000_000):
        flash("Give your reward a name and a Gold price (1 - 1,000,000).", "error")
    elif len(current_user.personal_rewards) >= 30:
        flash("You can have up to 30 personal rewards.", "error")
    else:
        db.session.add(PersonalReward(player_id=current_user.id, name=name, cost=cost))
        db.session.commit()
        flash(f"Reward added: {name} ({cost:,} G).", "success")
    return redirect(url_for('main.shop') + '#my-rewards')


@bp.route('/rewards/<int:reward_id>/delete', methods=['POST'])
@login_required
def delete_personal_reward(reward_id):
    from app.models import PersonalReward
    reward = db.session.get(PersonalReward, reward_id)
    if reward and reward.player_id == current_user.id:
        db.session.delete(reward)
        db.session.commit()
        flash(f"Removed: {reward.name}.", "info")
    return redirect(url_for('main.shop') + '#my-rewards')


@bp.route('/rewards/<int:reward_id>/buy', methods=['POST'])
@login_required
def buy_personal_reward(reward_id):
    from app.models import PersonalReward
    reward = db.session.get(PersonalReward, reward_id)
    if not reward or reward.player_id != current_user.id:
        flash("Reward not found.", "error")
    elif current_user.gold < reward.cost:
        flash(f"Not enough Gold: {reward.name} costs {reward.cost:,} G (you have {current_user.gold:,}).", "error")
    else:
        current_user.gold -= reward.cost
        db.session.add(PurchaseLog(player_id=current_user.id, item_name=reward.name, cost=reward.cost, is_claimed=False))
        db.session.commit()
        flash(f"REWARD UNLOCKED: {reward.name}. Enjoy it, then tap MARK CLAIMED under Ready to Enjoy.", "system_popup")
    return redirect(url_for('main.shop') + '#my-rewards')


@bp.route('/update_settings', methods=['POST'])
@login_required
def update_settings():
    audio = json_body().get('audio')
    music = json_body().get('music')
    volume = json_body().get('volume')
    popups = json_body().get('popups')
    
    if audio is not None:
        current_user.settings_audio = audio
    if music is not None:
        current_user.settings_music = music
    if volume is not None:
        current_user.settings_volume = float(volume)
    if popups is not None:
        current_user.settings_popups = bool(popups)
        
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/focus_complete', methods=['POST'])
@login_required
def focus_complete():
    try:
        minutes = int(json_body().get('minutes', 0))
    except (ValueError, TypeError):
        return jsonify({'success': False, 'msg': "Invalid duration."})
        
    if minutes < 1:
        return jsonify({'success': False, 'msg': "Too short."})
        
    # Rewards: 10 Coins/hour, 600 XP/hour (before bonuses).
    coins = int(minutes / 6.0 * coin_multiplier(current_user))
    
    from app.services import FOCUS_XP_PER_MINUTE
    base_xp = minutes * FOCUS_XP_PER_MINUTE
    xp = max(1, int(base_xp * xp_multiplier(current_user)))
    
    from app.league import record_points
    from app.kpi import record_focus_effort
    record_points(current_user, 'focus', base_xp, minutes=minutes)
    record_focus_effort(current_user, minutes)

    from app.services import add_xp
    current_user.debt_paid = 0  # transient per-request counter (see services.add_xp)
    current_user.coins += coins
    add_xp(current_user, xp)
    current_user.daily_focus_duration += minutes
    
    from app.services import process_level_up
    level_up = process_level_up(current_user)
    
    db.session.commit()
    
    if level_up:
        flash(level_up_flash(current_user), "levelup")

    if hasattr(current_user, 'just_evolved') and current_user.just_evolved:
        flash(f"CLASS EVOLVED: You are now a {current_user.just_evolved}!", "system_popup")
        
    if hasattr(current_user, 'just_ranked_up') and current_user.just_ranked_up:
        flash(f"RANK UP: You have reached {current_user.just_ranked_up}-Rank!", "system_popup")
    
    for name in getattr(current_user, 'new_titles', []):
        flash(f"TITLE UNLOCKED: {name}", "system_popup")

    msg = f"FOCUS COMPLETE: {minutes}m. +{coins} Coins, +{xp} XP."
    if getattr(current_user, 'debt_paid', 0):
        msg += f" ({current_user.debt_paid} XP paid off debt)"
    flash(msg, "system_popup")  # Shown on the next page load (focus page reloads / redirects)
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

        for q_data in quests_data:
            quest = Quest(
                title=q_data['title'][:100],
                description=q_data['desc'],
                rank=normalize_rank(q_data['rank']),
                xp_reward=0,  # Dailies award no XP; kept at 0 for consistency
                stat_reward=normalize_stat(q_data['stat'], default='STR'),
                player_id=current_user.id,
                is_daily=True
            )
            db.session.add(quest)
            
        # Update Player
        current_user.penalty_description = penalty
        current_user.penalty_detail = request.form.get('penalty_detail')
        current_user.setup_complete = True
        
        db.session.commit()
        
        flash("SYSTEM INITIALIZATION COMPLETE. WELCOME, PLAYER.", "system_popup")
        return redirect(url_for('main.dashboard'))
        
    return render_template('setup.html')

@bp.route('/vacation/start', methods=['POST'])
@login_required
def start_vacation_route():
    try:
        days = int(request.form.get('days', 7))
    except (TypeError, ValueError):
        days = 0
    if not (1 <= days <= 30):
        flash("Vacation length must be 1-30 days.", "error")
        return redirect(url_for('main.dashboard'))
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
    ids = json_body().get('ids', [])
    ids = [i for i in ids if isinstance(i, int)] if isinstance(ids, list) else []
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

@bp.route('/tasks/run', methods=['GET', 'POST'])
@csrf.exempt
def run_tasks_endpoint():
    """
    Wake-up hook for external cron services (free hosts sleep, and nothing runs while asleep).
    Disabled unless CRON_SECRET is set; the secret must be sent as the X-Cron-Secret header
    (or "Authorization: Bearer <secret>"), never in the URL.
    """
    import hmac
    from flask import current_app
    from app.tasks import run_due_tasks
    secret = os.environ.get('CRON_SECRET', '')
    if not secret:
        return jsonify({'error': 'not found'}), 404
    sent = request.headers.get('X-Cron-Secret', '')
    auth = request.headers.get('Authorization', '')
    if not sent and auth.startswith('Bearer '):
        sent = auth[len('Bearer '):]
    if not hmac.compare_digest(sent.encode(), secret.encode()):
        return jsonify({'error': 'forbidden'}), 403
    return jsonify({'ok': True, 'results': run_due_tasks(current_app._get_current_object())})


@bp.route('/manifest.webmanifest')
def web_manifest():
    """Installable app (PWA) manifest."""
    icon = lambda name, size, purpose='any': {'src': url_for('static', filename=f'icons/{name}'),
                                             'sizes': f'{size}x{size}', 'type': 'image/png', 'purpose': purpose}
    manifest = {
        'name': 'Shadow OS',
        'short_name': 'Shadow OS',
        'description': 'Gamified self-improvement: quests, streaks, leagues and raids.',
        'id': '/',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#050505',
        'theme_color': '#050505',
        'icons': [icon('icon-192.png', 192), icon('icon-512.png', 512), icon('maskable-512.png', 512, 'maskable')],
        'shortcuts': [
            {'name': 'Focus', 'url': '/focus', 'icons': [icon('icon-192.png', 192)]},
            {'name': 'Leaderboard', 'url': '/leaderboard', 'icons': [icon('icon-192.png', 192)]},
            {'name': 'Raids', 'url': '/raids', 'icons': [icon('icon-192.png', 192)]},
        ],
    }
    response = jsonify(manifest)
    response.mimetype = 'application/manifest+json'
    return response


@bp.route('/offline')
def offline():
    """Shown by the service worker when there is no connection."""
    return render_template('offline.html')


@bp.route('/api/vapid_public_key')
def vapid_public_key():
    return jsonify({'public_key': os.getenv('VAPID_PUBLIC_KEY')})


@bp.route('/api/notifications/subscribe', methods=['POST'])
@login_required
def subscribe_push():
    sub_data = json_body()
    keys = sub_data.get('keys')
    endpoint = sub_data.get('endpoint')
    if not isinstance(endpoint, str) or not endpoint or not isinstance(keys, dict) \
            or not isinstance(keys.get('p256dh'), str) or not isinstance(keys.get('auth'), str):
        return jsonify({'error': 'Invalid subscription data'}), 400

    p256dh = keys['p256dh']
    auth = keys['auth']

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
    sub_data = json_body()
    if not sub_data or 'endpoint' not in sub_data:
        return jsonify({'error': 'Invalid unsubscribe data'}), 400

    endpoint = sub_data['endpoint']
    
    # Check if this endpoint is registered and delete it
    existing_sub = PushSubscription.query.filter_by(endpoint=endpoint, player_id=current_user.id).first()
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
        data = request.get_json(silent=True) or request.form
        
        distribution = {
            'STR': int(data.get('STR', 0)),
            'INT': int(data.get('INT', 0)),
            'AGI': int(data.get('AGI', 0)),
            'VIT': int(data.get('VIT', 0)),
            'SNS': int(data.get('SNS', 0))
        }
        
    except (ValueError, TypeError):
        if request.is_json:
            return jsonify({'success': False, 'msg': "Invalid input."})
        flash("Invalid input.", "error")
        return redirect(url_for('main.dashboard'))
        
    success, msg = allocate_attributes(current_user, distribution)
    
    if request.is_json:
        return jsonify({'success': success, 'msg': msg})
        
    flash(msg, "success" if success else "error")
    return redirect(url_for('main.dashboard'))
