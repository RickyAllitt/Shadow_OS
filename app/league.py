"""
Weekly leagues, A/S rank caps, rivals and overtake alerts.

League points = base XP earned this week / 10 (XP before personal bonuses). Rewards are fixed per
action, so a Lv 40 and a Lv 12 hunter score the same for the same effort. The game week starts at the
Monday 01:00 reset (GAME_TIMEZONE), the same boundary as the weekly Gold reset.
"""
import os
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import ActivityEvent, Notification, Player, Quest, Rivalry

# League points = base XP / 10, i.e. XP before personal bonuses (INT, class, titles, sleep), so the
# same effort scores the same for every hunter. An instant-level-up S-rank counts as 1,000 XP.
LEAGUE_XP_PER_POINT = 10
S_RANK_LEAGUE_XP = 1000

# Max A/S rank quests a hunter can create (or promote to) per week. Dailies and penalties don't count.
WEEKLY_RANK_CAPS = {'S': 1, 'A': 3}
RANK_ORDER = ['E', 'D', 'C', 'B', 'A', 'S']


# ---------------------------------------------------------------- weeks

def week_start_for(dt=None):
    """Monday date of the game week containing dt (aware or naive-UTC datetime)."""
    from app.services import GAME_TIMEZONE, get_latest_daily_reset_time
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    day = get_latest_daily_reset_time(dt.astimezone(GAME_TIMEZONE)).date()  # the "game day"
    return day - timedelta(days=day.weekday())


def week_ends_at(week_start):
    """UTC datetime of the reset that closes the week."""
    from app.services import GAME_TIMEZONE, RESET_HOUR
    nxt = week_start + timedelta(days=7)
    return GAME_TIMEZONE.localize(datetime(nxt.year, nxt.month, nxt.day, RESET_HOUR)).astimezone(timezone.utc)


# ---------------------------------------------------------------- recording

def record(player, kind, *, points=0.0, minutes=0, success=None, rank=None, when=None):
    event = ActivityEvent(player_id=player.id, kind=kind, points=round(points, 3), minutes=minutes,
                          success=success, rank=rank, week_start=week_start_for(when))
    if when is not None:
        event.occurred_at = when
    db.session.add(event)
    return event


def record_points(player, kind, base_xp, minutes=0):
    """Log league points (base XP / 10), then tell anyone this hunter just passed in the league."""
    if base_xp <= 0:
        return
    week = week_start_for()
    before = weekly_points(player.id, week)
    record(player, kind, points=base_xp / LEAGUE_XP_PER_POINT, minutes=minutes)
    db.session.flush()
    notify_overtaken(player, before, weekly_points(player.id, week), week)


# ---------------------------------------------------------------- standings

def weekly_points(player_id, week):
    total = db.session.query(db.func.coalesce(db.func.sum(ActivityEvent.points), 0.0)).filter(
        ActivityEvent.player_id == player_id, ActivityEvent.week_start == week).scalar()
    return round(float(total), 1)


def _daily_rate(player, week, now):
    """Share of days this week with every daily done (closed days + today if already complete)."""
    results = ActivityEvent.query.filter_by(player_id=player.id, week_start=week, kind='daily_result').all()
    done, days = sum(1 for e in results if e.success), len(results)
    if week == week_start_for(now):
        dailies = Quest.query.filter_by(player_id=player.id, is_daily=True).all()
        days += 1
        done += 1 if dailies and all(q.is_completed for q in dailies) else 0
    return round(100.0 * done / days) if days else 0


def standings(week=None, now=None):
    """League table for a week: [{'player', 'points', 'daily_rate', 'focus_hours', 'position'}], best first."""
    now = now or datetime.now(timezone.utc)
    week = week or week_start_for(now)
    rows = []
    for p in Player.query.filter_by(setup_complete=True).all():
        events = ActivityEvent.query.filter_by(player_id=p.id, week_start=week)
        rows.append({
            'player': p,
            'points': weekly_points(p.id, week),
            'daily_rate': _daily_rate(p, week, now),
            'focus_hours': round(sum(e.minutes or 0 for e in events.filter_by(kind='focus')) / 60, 1),
        })
    rows.sort(key=lambda r: (-r['points'], -r['daily_rate'], -r['focus_hours'], r['player'].name.lower()))
    for i, r in enumerate(rows, 1):
        r['position'] = i
    return rows


def notify_overtaken(player, before, after, week):
    """Notify (and push) hunters whose weekly score this player just passed. Once per pair per week."""
    from app.services import trigger_push_notification
    for other in Player.query.filter(Player.id != player.id, Player.setup_complete.is_(True)).all():
        theirs = weekly_points(other.id, week)
        if not (before <= theirs < after) or theirs <= 0:
            continue
        msg = f"LEAGUE: {player.name} just overtook you this week ({after:.0f} pts vs your {theirs:.0f})."
        already = Notification.query.filter(
            Notification.player_id == other.id,
            Notification.message.like(f"LEAGUE: {player.name} just overtook you%"),
            Notification.created_at >= week_ends_at(week) - timedelta(days=7),
        ).first()
        if already:
            continue
        db.session.add(Notification(player_id=other.id, message=msg, category='warning'))
        trigger_push_notification(other.id, "OVERTAKEN", msg, url="/leaderboard")


# ---------------------------------------------------------------- rank caps & review

def rank_slots_used(player, week=None):
    week = week or week_start_for()
    used = dict.fromkeys(WEEKLY_RANK_CAPS, 0)
    for e in ActivityEvent.query.filter_by(player_id=player.id, week_start=week, kind='rank_claim'):
        if e.rank in used:
            used[e.rank] += 1
    return used


def rank_slots_left(player):
    used = rank_slots_used(player)
    return {r: max(0, cap - used[r]) for r, cap in WEEKLY_RANK_CAPS.items()}


def architect_review(title, requested):
    """
    Second opinion on self-assigned A/S ranks. The Architect can only LOWER a rank, and only
    when the real model answered (the keyword fallback is too crude to overrule a player).
    Disable with ARCHITECT_RANK_REVIEW=0. Returns (rank, message or None).
    """
    if requested not in WEEKLY_RANK_CAPS or os.environ.get('ARCHITECT_RANK_REVIEW', '1') == '0':
        return requested, None
    from app.ai_guardian import TheArchitect
    assessed = TheArchitect.assess_rank(title)
    if assessed and RANK_ORDER.index(assessed) < RANK_ORDER.index(requested):
        return assessed, f"The Architect assessed '{title}' as Rank {assessed} (you chose {requested})."
    return requested, None


def claim_rank(player, requested, title=None, review=True):
    """
    Apply the Architect review (manual picks) and the weekly A/S caps. Consumes a slot when an A/S
    rank is granted. Over-cap requests drop to the next rank with a free slot (S -> A -> B).
    Returns (granted_rank, [messages]).
    """
    messages = []
    rank = requested
    if review and title:
        rank, note = architect_review(title, rank)
        if note:
            messages.append(note)

    left = rank_slots_left(player)
    granted = rank
    while granted in WEEKLY_RANK_CAPS and left[granted] <= 0:
        granted = RANK_ORDER[RANK_ORDER.index(granted) - 1]
    if granted != rank:
        messages.append(f"Weekly Rank {rank} limit reached ({WEEKLY_RANK_CAPS[rank]}/week, resets Monday 01:00). "
                        f"Set to Rank {granted}.")
    if granted in WEEKLY_RANK_CAPS:
        record(player, 'rank_claim', rank=granted)
    return granted, messages


# ---------------------------------------------------------------- rivals

def set_rival(player, rival):
    if rival is None or rival.id == player.id:
        return False, "Choose another hunter as your rival."
    if player.rivalry:
        player.rivalry.rival_id = rival.id
        player.rivalry.created_at = datetime.now(timezone.utc)
    else:
        db.session.add(Rivalry(player_id=player.id, rival_id=rival.id))
    db.session.commit()
    return True, f"RIVAL SET: {rival.name}. May the stronger hunter win."


def clear_rival(player):
    if player.rivalry:
        db.session.delete(player.rivalry)
        db.session.commit()
    return True, "Rivalry dissolved."


def rival_summary(player, now=None):
    """This week's duel plus the all-time weekly record since the rivalry started."""
    rivalry = player.rivalry
    if not rivalry:
        return None
    now = now or datetime.now(timezone.utc)
    week = week_start_for(now)
    rival = rivalry.rival
    record_ = {'wins': 0, 'losses': 0, 'draws': 0}
    w = week_start_for(rivalry.created_at)
    while w < week:  # only completed weeks count toward the record
        mine, theirs = weekly_points(player.id, w), weekly_points(rival.id, w)
        if mine or theirs:
            record_['wins' if mine > theirs else 'losses' if theirs > mine else 'draws'] += 1
        w += timedelta(days=7)
    me_pts, rival_pts = weekly_points(player.id, week), weekly_points(rival.id, week)
    return {
        'rival': rival,
        'me': {'points': me_pts, 'daily_rate': _daily_rate(player, week, now)},
        'them': {'points': rival_pts, 'daily_rate': _daily_rate(rival, week, now)},
        'leading': 'me' if me_pts > rival_pts else 'them' if rival_pts > me_pts else 'tie',
        'record': record_,
        'week_ends': week_ends_at(week),
    }


# ---------------------------------------------------------------- weekly results

def weekly_results_message(player, now=None):
    """
    Once per week (first dashboard visit after the reset): last week's placing and winner.
    Returns the message, or None if already shown / nobody scored.
    """
    now = now or datetime.now(timezone.utc)
    week = week_start_for(now)
    if ActivityEvent.query.filter_by(player_id=player.id, week_start=week, kind='league_seen').first():
        return None
    record(player, 'league_seen')
    db.session.commit()
    last = week - timedelta(days=7)
    table = [r for r in standings(last, now=now) if r['points'] > 0]
    if not table:
        return None
    winner = table[0]
    mine = next((r for r in table if r['player'].id == player.id), None)
    if mine is None:
        return f"LAST WEEK'S LEAGUE: {winner['player'].name} won with {winner['points']:.0f} pts. You didn't score - this week is yours."
    more = " Full breakdown: SYSTEM COMMANDS → REPORT."
    if mine['position'] == 1:
        return f"LAST WEEK'S LEAGUE: YOU WON with {mine['points']:.0f} pts! 👑" + more
    return (f"LAST WEEK'S LEAGUE: You placed #{mine['position']} of {len(table)} with {mine['points']:.0f} pts. "
            f"Winner: {winner['player'].name} ({winner['points']:.0f} pts)." + more)
