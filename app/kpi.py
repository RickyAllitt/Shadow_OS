"""
Life Balance (real-life KPIs), measured quests and the weekly System Report.

Life Balance is separate from the RPG attributes on purpose: attributes are permanent character
power (they drive XP/coin bonuses, titles, rank-ups), while Life Balance answers "where has my
effort actually gone lately?". Every completed quest, focus session and good night's sleep logs
'effort units' to one area. Units fade with a 14-day half-life, so a neglected area visibly drops.

    area score (0-100) = 100 * (1 - e^(-decayed_units / SCORE_SCALE))

Calibration: one E-rank daily per day in an area settles around 55; two dailies plus the odd
B-rank quest lands in the 80s-90s.
"""
import math
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import ActivityEvent, Quest

AREAS = ('STR', 'INT', 'AGI', 'VIT', 'SNS')
AREA_NAMES = {'STR': 'Strength', 'INT': 'Intelligence', 'AGI': 'Agility', 'VIT': 'Vitality', 'SNS': 'Sense'}
AREA_HINTS = {
    'STR': 'gym, sport, physical training',
    'INT': 'study, reading, coding, deep work',
    'AGI': 'admin, errands, beating procrastination',
    'VIT': 'sleep, nutrition, health',
    'SNS': 'meditation, people, networking, creativity',
}

RANK_UNITS = {'E': 1, 'D': 2, 'C': 3, 'B': 5, 'A': 8, 'S': 13}
HALF_LIFE_DAYS = 14
WINDOW_DAYS = 60           # older effort is < 5% weight; ignore it
SCORE_SCALE = 25.0
FOCUS_MINUTES_PER_UNIT = 25
FOCUS_AREA = 'INT'
SLEEP_UNITS = ((7.5, 3.0), (6.0, 1.5))   # hours >= threshold -> VIT units


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


# ---------------------------------------------------------------- recording

def record_effort(player, stat, units, rank=None, quest_id=None):
    from app.league import record
    from app.services import normalize_stat
    if units <= 0:
        return None
    event = record(player, 'effort', rank=rank)
    event.stat, event.units, event.quest_id = normalize_stat(stat), units, quest_id
    return event


def record_quest_effort(player, quest):
    if quest.is_penalty:
        return None
    return record_effort(player, quest.stat_reward, RANK_UNITS.get(quest.rank, 1), rank=quest.rank, quest_id=quest.id)


def record_focus_effort(player, minutes):
    return record_effort(player, FOCUS_AREA, minutes / FOCUS_MINUTES_PER_UNIT)


def record_sleep(player, hours):
    from app.league import record
    event = record(player, 'sleep')
    event.value = hours
    for threshold, units in SLEEP_UNITS:
        if hours >= threshold:
            record_effort(player, 'VIT', units)
            break
    return event


# ---------------------------------------------------------------- Life Balance

def area_scores(player, at=None):
    """{area: 0-100} as of `at` (default now). Works historically since events are timestamped."""
    at = _utc(at or datetime.now(timezone.utc))
    since = at - timedelta(days=WINDOW_DAYS)
    raw = dict.fromkeys(AREAS, 0.0)
    events = ActivityEvent.query.filter(
        ActivityEvent.player_id == player.id, ActivityEvent.kind == 'effort',
        ActivityEvent.occurred_at >= since.replace(tzinfo=None), ActivityEvent.occurred_at <= at.replace(tzinfo=None))
    for e in events:
        if e.stat in raw:
            age_days = max(0.0, (at - _utc(e.occurred_at)).total_seconds() / 86400)
            raw[e.stat] += (e.units or 0) * 0.5 ** (age_days / HALF_LIFE_DAYS)
    return {a: round(100 * (1 - math.exp(-raw[a] / SCORE_SCALE))) for a in AREAS}


def life_balance(player, at=None):
    """Scores with 7-day trends plus the strongest and weakest areas."""
    at = _utc(at or datetime.now(timezone.utc))
    now, before = area_scores(player, at), area_scores(player, at - timedelta(days=7))
    areas = [{'code': a, 'name': AREA_NAMES[a], 'hint': AREA_HINTS[a], 'score': now[a],
              'trend': now[a] - before[a]} for a in AREAS]
    ranked = sorted(areas, key=lambda x: x['score'])
    return {
        'areas': areas,
        'overall': round(sum(now.values()) / len(AREAS)),
        'weakest': ranked[0],
        'strongest': ranked[-1],
        'previous': before,
    }


# ---------------------------------------------------------------- measured quests

def _period_start(player, quest):
    """Dailies count today's amount (since the last 01:00 reset); one-off quests count everything."""
    if quest.is_daily and player.last_daily_reset:
        return _utc(player.last_daily_reset).replace(tzinfo=None)
    return None


def metric_total(player, quest):
    q = db.session.query(db.func.coalesce(db.func.sum(ActivityEvent.value), 0.0)).filter(
        ActivityEvent.player_id == player.id, ActivityEvent.kind == 'metric', ActivityEvent.quest_id == quest.id)
    start = _period_start(player, quest)
    if start is not None:
        q = q.filter(ActivityEvent.occurred_at >= start)
    return float(q.scalar())


def log_metric(player, quest, amount):
    """
    Log an amount toward a measured quest. Updates the progress bar and returns
    (total, reached_target). The caller completes the quest when the target is reached.
    """
    from app.league import record
    event = record(player, 'metric')
    event.value, event.quest_id = float(amount), quest.id
    db.session.flush()
    total = metric_total(player, quest)
    quest.progress = min(100, int(100 * total / quest.metric_target))
    return total, total >= quest.metric_target


def metric_history(player, quest, days=30, now=None):
    """[(date, total)] per game day for the last `days` days (dailies) - for trend charts."""
    from app.services import get_latest_daily_reset_time, player_tz
    tz = player_tz(player)
    now = _utc(now or datetime.now(timezone.utc))
    since = now - timedelta(days=days)
    totals = {}
    for e in ActivityEvent.query.filter(ActivityEvent.player_id == player.id, ActivityEvent.kind == 'metric',
                                        ActivityEvent.quest_id == quest.id,
                                        ActivityEvent.occurred_at >= since.replace(tzinfo=None)):
        day = get_latest_daily_reset_time(_utc(e.occurred_at), tz).date()
        totals[day] = totals.get(day, 0.0) + (e.value or 0)
    today = get_latest_daily_reset_time(now, tz).date()
    return [(d, round(totals.get(d, 0.0), 2)) for d in (today - timedelta(days=i) for i in range(days - 1, -1, -1))]


def format_amount(value):
    return f"{value:g}"


# ---------------------------------------------------------------- weekly System Report

def weekly_report(player, week=None, now=None):
    """Everything that happened in one game week (default: last completed week)."""
    from app import league
    now = _utc(now or datetime.now(timezone.utc))
    if week is None:
        week = league.week_start_for(now) - timedelta(days=7)
    week_end = league.week_ends_at(week)
    week_begin = week_end - timedelta(days=7)
    events = ActivityEvent.query.filter_by(player_id=player.id, week_start=week).all()
    by_kind = {}
    for e in events:
        by_kind.setdefault(e.kind, []).append(e)

    days = by_kind.get('daily_result', [])
    perfect = sum(1 for e in days if e.success)
    quests = [e for e in by_kind.get('effort', []) if e.rank]
    rank_counts = {r: sum(1 for e in quests if e.rank == r) for r in ('S', 'A', 'B', 'C', 'D', 'E')}
    sleeps = [e.value for e in by_kind.get('sleep', []) if e.value is not None]

    table = league.standings(week, now=now)
    placing = next((r for r in table if r['player'].id == player.id), None)
    scored = [r for r in table if r['points'] > 0]

    duel = None
    if player.rivalry:
        rival = player.rivalry.rival
        mine, theirs = league.weekly_points(player.id, week), league.weekly_points(rival.id, week)
        duel = {'rival': rival, 'me': mine, 'them': theirs,
                'result': 'WON' if mine > theirs else 'LOST' if theirs > mine else 'DRAW'}

    # For the week in progress, measure "now" rather than decaying toward a future week end
    balance_end, balance_start = area_scores(player, min(week_end, now)), area_scores(player, week_begin)
    areas = [{'code': a, 'name': AREA_NAMES[a], 'start': balance_start[a], 'end': balance_end[a],
              'change': balance_end[a] - balance_start[a]} for a in AREAS]
    weakest = min(areas, key=lambda x: x['end'])

    measures = []
    for q in Quest.query.filter(Quest.player_id == player.id, Quest.metric_target.isnot(None)).all():
        if not q.is_measured:
            continue
        logged = [e for e in by_kind.get('metric', []) if e.quest_id == q.id]
        history = metric_history(player, q, days=7, now=week_end - timedelta(seconds=1)) if q.is_daily else []
        measures.append({
            'quest': q,
            'total': round(sum(e.value or 0 for e in logged), 2),
            'days_on_target': sum(1 for _, v in history if v >= q.metric_target) if q.is_daily else None,
        })

    return {
        'week_start': week, 'week_end': week_end, 'is_current': week == league.week_start_for(now),
        'points': league.weekly_points(player.id, week),
        'placing': placing['position'] if placing and placing['points'] > 0 else None,
        'competitors': len(scored),
        'winner': scored[0]['player'] if scored else None,
        'duel': duel,
        'days_tracked': len(days), 'perfect_days': perfect,
        'quests_completed': len(quests), 'rank_counts': rank_counts,
        'focus_hours': round(sum(e.minutes or 0 for e in by_kind.get('focus', [])) / 60, 1),
        'sleep_avg': round(sum(sleeps) / len(sleeps), 1) if sleeps else None, 'sleep_nights': len(sleeps),
        'areas': areas, 'weakest': weakest,
        'measures': measures,
        'has_activity': bool(events),
    }
