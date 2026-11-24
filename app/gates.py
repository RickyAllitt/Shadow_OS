"""
Gates: timed challenges measured from the activity log (nothing to type in, just play).

  gate       Lv 15+. One per game week. Appears on its own; you choose when to ENTER. 72 h to clear
             two objectives and a boss. Reward: bonus XP (a quarter level), Coins and a loot drop.
  red        Lv 30+. A rare surprise (about 1 day in 5, max one a week). Enter within 24 h, then 48 h
             to clear harder objectives. Reward: half a level, double Coins, Rare-or-better loot.
             Failing or declining costs nothing.
  exam       Rank Assessment. Promotions to B, A and S (Lv 40/60/80) need a 7-day exam once the level
             and stat requirements are met. Failing allows a retry 3 days later.
  awakening  Second Awakening, Lv 50 with a class. A 7-day trial; clearing it lets you pick a
             specialisation (see progression.SPECIALIZATIONS).

Gate rewards never add league points: the league only counts the work itself.
"""
import json
import random
import zlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import ActivityEvent, Gate

RANK_ORDER = 'EDCBAS'

GATE_LEVEL, RED_GATE_LEVEL, AWAKENING_LEVEL = 15, 30, 50
GATE_HOURS, RED_GATE_HOURS, RED_ENTER_HOURS, EXAM_DAYS = 72, 48, 24, 7
RED_GATE_DAILY_CHANCE = 20   # percent
EXAM_RETRY_DAYS = 3
EXAM_RANKS = ('B', 'A', 'S')

OBJECTIVE_LABELS = {
    'quests': "Clear {target} {min_rank}-rank or higher quests",
    'boss': "BOSS: clear a {min_rank}-rank or higher quest",
    'focus': "Focus for {target} minutes",
    'perfect': "Finish all dailies on {target} day{s}",
    'sleep': "Log 7h+ of sleep on {target} night{s}",
}

GATE_NAMES = {
    'gate': ('Hollow Barracks', 'Sunken Archive', 'Ashen Quarry', 'Frostbitten Den', 'Iron Catacombs',
             'Whispering Grove', 'Drowned Cathedral', 'Ember Mines'),
    'red': ('Crimson Labyrinth', 'Bleeding Citadel', 'Red Tundra', 'Scarlet Abyss'),
}


def now_utc():
    return datetime.now(timezone.utc)


def aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- objectives

def _grade_for(level):
    return 'C' if level < 25 else 'B' if level < 50 else 'A'


def _templates(grade, red=False):
    """Objective pool for a grade. Red gates ask for more in less time."""
    base = {
        'C': {'quests': (3, 'D'), 'focus': 60, 'perfect': 1, 'sleep': 2, 'boss': 'B'},
        'B': {'quests': (4, 'C'), 'focus': 120, 'perfect': 2, 'sleep': 2, 'boss': 'B'},
        'A': {'quests': (5, 'C'), 'focus': 180, 'perfect': 2, 'sleep': 3, 'boss': 'A'},
    }[grade]
    if red:
        base = {**base, 'quests': (base['quests'][0] + 1, base['quests'][1]),
                'focus': int(base['focus'] * 1.5), 'boss': 'A'}
        base['perfect'] = 1
    return base


def _objective(kind, spec):
    if kind == 'quests':
        return {'type': 'quests', 'target': spec[0], 'min_rank': spec[1]}
    if kind == 'boss':
        return {'type': 'boss', 'target': 1, 'min_rank': spec}
    return {'type': kind, 'target': spec}


def build_objectives(grade, rng, red=False):
    pool = _templates(grade, red)
    picks = rng.sample(['quests', 'focus', 'perfect', 'sleep'], 2)
    return [_objective(k, pool[k]) for k in picks] + [_objective('boss', pool['boss'])]


EXAM_OBJECTIVES = {
    'B': [('quests', (8, 'C')), ('focus', 300), ('perfect', 3), ('boss', 'A')],
    'A': [('quests', (10, 'C')), ('focus', 420), ('perfect', 4), ('boss', 'A')],
    'S': [('quests', (12, 'B')), ('focus', 600), ('perfect', 5), ('boss', 'S')],
}
AWAKENING_OBJECTIVES = [('quests', (10, 'C')), ('focus', 360), ('perfect', 4), ('boss', 'A')]


def objective_label(o):
    return OBJECTIVE_LABELS[o['type']].format(target=o['target'], min_rank=o.get('min_rank', ''),
                                              s='s' if o['target'] != 1 else '')


def _window(gate):
    return _naive(aware(gate.entered_at)), _naive(aware(gate.expires_at))


def measure(gate, objective):
    """Progress of one objective inside the gate's window."""
    if not gate.entered_at:
        return 0
    start, end = _window(gate)
    q = ActivityEvent.query.filter(ActivityEvent.player_id == gate.player_id,
                                   ActivityEvent.occurred_at >= start, ActivityEvent.occurred_at <= end)
    kind = objective['type']
    if kind in ('quests', 'boss'):
        ranks = RANK_ORDER[RANK_ORDER.index(objective['min_rank']):]
        return q.filter(ActivityEvent.kind == 'effort', ActivityEvent.quest_id.isnot(None),
                        ActivityEvent.rank.in_(list(ranks))).count()
    if kind == 'focus':
        return int(q.filter(ActivityEvent.kind == 'focus').with_entities(
            func.coalesce(func.sum(ActivityEvent.minutes), 0)).scalar() or 0)
    if kind == 'perfect':
        return q.filter(ActivityEvent.kind == 'daily_result', ActivityEvent.success.is_(True)).count()
    if kind == 'sleep':
        return q.filter(ActivityEvent.kind == 'sleep', ActivityEvent.value >= 7).count()
    return 0


def progress(gate):
    """[{'label', 'done', 'target', 'pct', 'complete', 'boss'}] for each objective."""
    rows = []
    for o in json.loads(gate.objectives):
        done = measure(gate, o)
        rows.append({'label': objective_label(o), 'done': min(done, o['target']), 'target': o['target'],
                     'pct': min(100, round(done / o['target'] * 100)), 'complete': done >= o['target'],
                     'boss': o['type'] == 'boss'})
    return rows


# ---------------------------------------------------------------- creation

def _rng(*parts):
    return random.Random(zlib.crc32('-'.join(str(p) for p in parts).encode()))


def _week():
    from app.league import week_start_for
    return week_start_for()


def _new_gate(player, kind, title, objectives, grade, enter_by=None, target_rank=None):
    gate = Gate(player_id=player.id, kind=kind, grade=grade, title=title, objectives=json.dumps(objectives),
                week_start=_week(), enter_by=_naive(enter_by) if enter_by else None, target_rank=target_rank,
                appeared_at=_naive(now_utc()))
    db.session.add(gate)
    return gate


def _notify(player, title, body):
    from app.services import trigger_push_notification
    trigger_push_notification(player.id, title, body)


def ensure_weekly_gate(player):
    from app.progression import effective_level
    if effective_level(player) < GATE_LEVEL:
        return None
    week = _week()
    if player.gates.filter_by(kind='gate', week_start=week).first():
        return None
    rng = _rng(player.id, week, 'gate')
    grade = _grade_for(player.level)
    title = f"{grade}-Rank Gate: {rng.choice(GATE_NAMES['gate'])}"
    from app.league import week_ends_at
    enter_by = week_ends_at(week)
    gate = _new_gate(player, 'gate', title, build_objectives(grade, rng), grade, enter_by=enter_by)
    _notify(player, "A GATE HAS APPEARED", f"{title}. Enter it this week.")
    return gate


def maybe_spawn_red_gate(player, now=None):
    from app.progression import effective_level
    if effective_level(player) < RED_GATE_LEVEL:
        return None
    now = now or now_utc()
    week = _week()
    if player.gates.filter_by(kind='red', week_start=week).first():
        return None
    if player.gates.filter(Gate.status.in_(('waiting', 'active')), Gate.kind == 'red').first():
        return None
    day = now.date().isoformat()
    if _rng(player.id, day, 'red').randrange(100) >= RED_GATE_DAILY_CHANCE:
        return None
    rng = _rng(player.id, day, 'red-content')
    grade = _grade_for(player.level)
    title = f"RED GATE: {rng.choice(GATE_NAMES['red'])}"
    gate = _new_gate(player, 'red', title, build_objectives(grade, rng, red=True), grade,
                     enter_by=now + timedelta(hours=RED_ENTER_HOURS))
    _notify(player, "WARNING: RED GATE", f"{title} opened. Enter within {RED_ENTER_HOURS}h or it closes.")
    return gate


def ensure_rank_exam(player, now=None):
    """Open a Rank Assessment once the player qualifies for B, A or S."""
    from app.services import RANK_REQUIREMENTS, total_base_stats
    if player.rank not in RANK_REQUIREMENTS:
        return None
    next_rank, req_level, req_stats = RANK_REQUIREMENTS[player.rank]
    if next_rank not in EXAM_RANKS or player.level < req_level or total_base_stats(player) < req_stats:
        return None
    open_exam = player.gates.filter(Gate.kind == 'exam', Gate.target_rank == next_rank,
                                    Gate.status.in_(('waiting', 'active', 'cleared'))).first()
    if open_exam:
        return None
    now = now or now_utc()
    last_fail = player.gates.filter(Gate.kind == 'exam', Gate.target_rank == next_rank,
                                    Gate.status == 'failed').order_by(Gate.finished_at.desc()).first()
    if last_fail and aware(last_fail.finished_at) + timedelta(days=EXAM_RETRY_DAYS) > now:
        return None
    objectives = [_objective(k, v) for k, v in EXAM_OBJECTIVES[next_rank]]
    gate = _new_gate(player, 'exam', f"RANK ASSESSMENT: {next_rank}-RANK", objectives, next_rank,
                     target_rank=next_rank)
    _notify(player, "RANK ASSESSMENT", f"You qualify for {next_rank}-Rank. Pass the assessment to be promoted.")
    return gate


def ensure_awakening(player):
    from app.progression import base_class, effective_level
    if player.specialization or not base_class(player.job_class) or effective_level(player) < AWAKENING_LEVEL:
        return None
    if player.gates.filter(Gate.kind == 'awakening', Gate.status.in_(('waiting', 'active', 'cleared'))).first():
        return None
    objectives = [_objective(k, v) for k, v in AWAKENING_OBJECTIVES]
    gate = _new_gate(player, 'awakening', "SECOND AWAKENING TRIAL", objectives, 'S')
    _notify(player, "SECOND AWAKENING", "Your power has hit its limit. A trial awaits.")
    return gate


# ---------------------------------------------------------------- lifecycle

def duration(gate):
    return {'gate': timedelta(hours=GATE_HOURS), 'red': timedelta(hours=RED_GATE_HOURS)}.get(
        gate.kind, timedelta(days=EXAM_DAYS))


def enter(player, gate_id, now=None):
    gate = db.session.get(Gate, gate_id)
    if not gate or gate.player_id != player.id:
        return False, "Gate not found."
    if gate.status != 'waiting':
        return False, "That gate can't be entered."
    now = now or now_utc()
    if gate.enter_by and aware(gate.enter_by) < now:
        gate.status, gate.finished_at = 'missed', _naive(now)
        db.session.commit()
        return False, "The gate has already closed."
    gate.status, gate.entered_at, gate.expires_at = 'active', _naive(now), _naive(now + duration(gate))
    db.session.commit()
    hours = int(duration(gate).total_seconds() // 3600)
    return True, f"ENTERED: {gate.title}. You have {hours} hours. Clear every objective."


def decline(player, gate_id, now=None):
    gate = db.session.get(Gate, gate_id)
    if not gate or gate.player_id != player.id or gate.status != 'waiting' or gate.kind in ('exam', 'awakening'):
        return False, "That gate can't be declined."
    gate.status, gate.finished_at = 'declined', _naive(now or now_utc())
    db.session.commit()
    return True, f"You turned away from {gate.title}."


def update_status(gate, now=None):
    """Advance one gate's state. Returns a message if something changed."""
    now = now or now_utc()
    if gate.status == 'waiting' and gate.enter_by and aware(gate.enter_by) < now:
        gate.status, gate.finished_at = 'missed', _naive(now)
        return None
    if gate.status != 'active':
        return None
    if all(o['complete'] for o in progress(gate)):
        gate.status, gate.finished_at = 'cleared', _naive(now)
        _notify(gate.player, "GATE CLEARED", f"{gate.title} cleared. Claim your rewards.")
        return f"GATE CLEARED: {gate.title}. Claim your rewards!"
    if aware(gate.expires_at) < now:
        gate.status, gate.finished_at = 'failed', _naive(now)
        if gate.kind == 'exam':
            return f"{gate.title} FAILED. You may retake it in {EXAM_RETRY_DAYS} days."
        return f"{gate.title} collapsed. Nothing was lost; another will come."
    return None


def refresh(player, now=None):
    """Spawn due gates and advance existing ones. Returns messages to show the player."""
    now = now or now_utc()
    ensure_weekly_gate(player)
    maybe_spawn_red_gate(player, now)
    ensure_rank_exam(player, now)
    ensure_awakening(player)
    messages = []
    for gate in player.gates.filter(Gate.status.in_(('waiting', 'active'))).all():
        msg = update_status(gate, now)
        if msg:
            messages.append(msg)
    db.session.commit()
    return messages


def refresh_all(app_instance, now=None):
    """Background tick: keep every player's gates current (so clears and spawns notify on time)."""
    from app.models import Player
    with app_instance.app_context():
        count = 0
        for player in Player.query.filter(Player.setup_complete.is_(True)).all():
            count += len(refresh(player, now))
        return count


def visible_gates(player):
    """Gates to show on the dashboard: waiting, active and unclaimed clears."""
    return player.gates.filter(Gate.status.in_(('waiting', 'active', 'cleared'))).order_by(Gate.id).all()


# ---------------------------------------------------------------- rewards

def claim(player, gate_id, rng=random):
    """Collect a cleared gate. Returns (ok, [messages], redirect_endpoint or None)."""
    from app import loot
    from app.services import add_xp, check_title_unlocks, process_level_up
    gate = db.session.get(Gate, gate_id)
    if not gate or gate.player_id != player.id:
        return False, ["Gate not found."], None
    if gate.status != 'cleared':
        return False, ["Clear the gate before claiming it."], None

    gate.status = 'claimed'
    messages, endpoint = [], None
    if gate.kind in ('gate', 'red'):
        share = 0.5 if gate.kind == 'red' else 0.25
        xp = int(round(player.xp_required * share, -1))
        coins = {'C': 100, 'B': 200, 'A': 350}.get(gate.grade, 100) * (2 if gate.kind == 'red' else 1)
        player.debt_paid = 0
        add_xp(player, xp)
        player.coins += coins
        messages.append(f"{gate.title} REWARDS: +{xp:,} XP, +{coins} Coins.")
        floor = 'rare' if gate.kind == 'red' else 'common'
        from app.progression import effective_level
        rarity = 'legendary' if gate.kind == 'red' and effective_level(player) >= 80 else None
        messages.append(loot.grant_loot(player, rng, floor=floor, rarity=rarity))
    elif gate.kind == 'exam':
        player.rank = gate.target_rank
        player.just_ranked_up = gate.target_rank
        messages.append(f"ASSESSMENT PASSED: you are now {gate.target_rank}-Rank!")
    elif gate.kind == 'awakening':
        messages.append("TRIAL CLEARED. Choose the path of your Second Awakening.")
        endpoint = 'main.awakening'

    process_level_up(player)
    check_title_unlocks(player)
    db.session.commit()
    return True, messages, endpoint


def cleared_count(player, kinds=('gate', 'red')):
    return player.gates.filter(Gate.kind.in_(kinds), Gate.status == 'claimed').count()
