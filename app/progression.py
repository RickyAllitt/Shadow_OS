"""
Progression: the "Road to Monarch" roadmap and class skills.

Roadmap
    Every level that unlocks something (job change, class evolutions, Hunter Rank promotions,
    level titles, skill upgrades) is listed with what it gives, so players always see what is next.

Class skills
    Each class line has one active skill, unlocked with the class at Level 10. Every evolution
    (Lv 20/40/60/80/100) raises the skill's tier: a stronger effect and a shorter cooldown.
      Assassin  VANISH   Today becomes a rest day: missed dailies don't break the streak or count
                         towards penalties (applies at the next daily reset).
      Mage      INSIGHT  The next focus session earns bonus XP (first 60 minutes).
      Tank      FORTIFY  Pays off part of your XP debt now; with no debt, raises a shield that
                         absorbs the next failed penalty (no debt, no Hardcore level loss).
    Skill bonuses never change league points (the league counts base XP only).
"""
from datetime import datetime, timedelta, timezone

from app.extensions import db

CLASS_LINES = ('Assassin', 'Mage', 'Tank')
INSIGHT_MAX_MINUTES = 60


def _evolutions():
    from app.services import CLASS_EVOLUTIONS
    return CLASS_EVOLUTIONS


def base_class(job_class):
    """'Shadow Lord' -> 'Assassin'. Returns None for no class / unknown names."""
    parents = {child: parent for parent, (child, _lvl) in _evolutions().items()}
    seen = set()
    while job_class in parents and job_class not in seen:
        seen.add(job_class)
        job_class = parents[job_class]
    return job_class if job_class in CLASS_LINES else None


def class_tier(job_class):
    """1 for a base class, +1 per evolution (Monarch = 6). 0 with no class."""
    line = base_class(job_class)
    if not line:
        return 0
    tier, current = 1, line
    while current != job_class and current in _evolutions():
        current = _evolutions()[current][0]
        tier += 1
    return tier


def evolution_line(line):
    """[(class name, level reached)] for a whole line, starting with the base class at Lv 10."""
    path, current = [(line, 10)], line
    while current in _evolutions():
        current, level = _evolutions()[current]
        path.append((current, level))
    return path


ROMAN = ['', 'I', 'II', 'III', 'IV', 'V', 'VI']
COOLDOWN_DAYS = {1: 7, 2: 6, 3: 5, 4: 4, 5: 3, 6: 2}


def insight_multiplier(tier):
    return round(1.5 + 0.1 * (tier - 1), 2)       # x1.5 -> x2.0


def fortify_share(tier):
    return min(1.0, 0.5 + 0.1 * (tier - 1))       # 50% -> 100% of the debt


# Second Awakening (Lv 50): each line picks one of two specialisations
SPECIALIZATIONS = {
    'Assassin': {'Blade': "Your passive Coin bonus doubles to +20%.",
                 'Phantom': "Vanish recharges 2 days faster."},
    'Mage': {'Sage': "Insight covers focus sessions of up to 120 minutes.",
             'Elementalist': "Your passive XP bonus rises to +15%."},
    'Tank': {'Bulwark': "Fortify pays off debt AND raises the shield in a single use.",
             'Warden': "Two grace days before penalties instead of one."},
}


def insight_minutes(spec=None):
    return 120 if spec == 'Sage' else INSIGHT_MAX_MINUTES


def cooldown_days(tier, spec=None):
    return max(1, COOLDOWN_DAYS[tier] - (2 if spec == 'Phantom' else 0))


def class_coin_bonus(player):
    if base_class(player.job_class) != 'Assassin':
        return 0.0
    return 0.20 if player.specialization == 'Blade' else 0.10


def class_xp_bonus(player):
    if base_class(player.job_class) != 'Mage':
        return 0.0
    return 0.15 if player.specialization == 'Elementalist' else 0.10


def penalty_grace_days(player):
    if base_class(player.job_class) != 'Tank':
        return 0
    return 2 if player.specialization == 'Warden' else 1


def _fortify_text(t, spec=None):
    share = int(fortify_share(t) * 100)
    if spec == 'Bulwark':
        return f"Pay off {share}% of your XP debt and raise a shield that absorbs your next failed penalty."
    return (f"Pay off {share}% of your XP debt now. With no debt, "
            "raise a shield that absorbs your next failed penalty.")


CLASS_SKILLS = {
    'Assassin': {'name': 'Vanish', 'icon': 'ghost',
                 'effect': lambda t, spec=None: "Declare today a rest day: if you miss your dailies, your streak "
                                                "and penalty progress are untouched."},
    'Mage': {'name': 'Insight', 'icon': 'brain',
             'effect': lambda t, spec=None: f"Your next focus session earns x{insight_multiplier(t):g} XP "
                                            f"(first {insight_minutes(spec)} minutes)."},
    'Tank': {'name': 'Fortify', 'icon': 'shield', 'effect': _fortify_text},
}


def effective_level(player):
    """Level used for unlocks: every Ascension counts as 100 levels already climbed."""
    return (player.level or 1) + 100 * (player.ascensions or 0)


def _aware(dt):
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def skill_info(player, now=None):
    """Everything the UI needs about the player's skill, or None before the job change."""
    line, tier = base_class(player.job_class), class_tier(player.job_class)
    if not line:
        return None
    now = now or datetime.now(timezone.utc)
    spec = CLASS_SKILLS[line]
    ready_at = _aware(player.skill_ready_at)
    ready = ready_at is None or now >= ready_at
    return {
        'line': line, 'tier': tier, 'name': spec['name'], 'full_name': f"{spec['name']} {ROMAN[tier]}",
        'icon': spec['icon'], 'effect': spec['effect'](tier, player.specialization),
        'cooldown_days': cooldown_days(tier, player.specialization), 'specialization': player.specialization,
        'armed': bool(player.skill_armed), 'ready': ready and not player.skill_armed,
        'ready_in': None if ready else format_wait(ready_at - now),
    }


def format_wait(delta):
    hours = max(1, int(delta.total_seconds() // 3600) + (1 if delta.total_seconds() % 3600 else 0))
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if days else f"{hours}h"


def use_skill(player, now=None):
    """Activate the class skill. Returns (ok, message)."""
    info = skill_info(player, now)
    if not info:
        return False, "Your class skill unlocks with the Job Change at Level 10."
    if info['armed']:
        return False, f"{info['full_name']} is already active."
    if not info['ready']:
        return False, f"{info['full_name']} is recharging (ready in {info['ready_in']})."

    now = now or datetime.now(timezone.utc)
    line, tier = info['line'], info['tier']
    if line == 'Assassin':
        player.skill_armed = True
        msg = (f"{info['full_name'].upper()}: today is a rest day. If your dailies stay unfinished, "
               "the System will look the other way at the next reset.")
    elif line == 'Mage':
        player.skill_armed = True
        msg = (f"{info['full_name'].upper()}: your next focus session earns x{insight_multiplier(tier):g} XP "
               f"for up to {insight_minutes(player.specialization)} minutes.")
    else:
        debt = player.xp_debt or 0
        parts = []
        if debt > 0:
            paid = max(1, int(round(debt * fortify_share(tier))))
            player.xp_debt = debt - paid
            parts.append(f"{paid:,} XP of debt cleared" + (
                " (DEBT CLEARED)" if not player.xp_debt else f", {player.xp_debt:,} XP left"))
        if debt <= 0 or player.specialization == 'Bulwark':
            player.skill_armed = True
            parts.append("shield raised. It will absorb your next failed penalty")
        msg = f"{info['full_name'].upper()}: " + "; ".join(parts) + "."

    player.skill_ready_at = now + timedelta(days=info['cooldown_days'])
    from app.league import record
    record(player, 'skill', points=0)
    db.session.commit()
    return True, msg


def consume_armed(player, line):
    """True (and disarms) if the player's armed skill belongs to this class line."""
    if player.skill_armed and base_class(player.job_class) == line:
        player.skill_armed = False
        return True
    return False


def insight_bonus_xp(player, minutes, base_xp_per_minute, multiplier):
    """Extra XP for a focus session if Insight is armed (consumes it)."""
    if not consume_armed(player, 'Mage'):
        return 0
    mult = insight_multiplier(class_tier(player.job_class))
    covered = min(minutes, insight_minutes(player.specialization))
    return int(covered * base_xp_per_minute * (mult - 1) * multiplier)


# ---------------------------------------------------------------- roadmap

def _skill_upgrade_text(line, tier, spec=None):
    skill = CLASS_SKILLS[line]
    return (f"{skill['name']} {ROMAN[tier]}: {skill['effect'](tier, spec)} "
            f"Cooldown {cooldown_days(tier, spec)} days.")


ASCENSION_XP_BONUS = 0.05   # permanent personal XP per Ascension (never league points)


def can_ascend(player):
    return (player.level or 0) >= 100


def ascend(player):
    """Prestige: back to Lv 1, keeping class, skill, rank, stats, gear, shadows and titles."""
    from app.services import calculate_xp_required, check_title_unlocks
    if not can_ascend(player):
        return False, "Ascension requires Level 100."
    player.ascensions = (player.ascensions or 0) + 1
    player.level, player.xp = 1, 0
    player.xp_required = calculate_xp_required(1)
    check_title_unlocks(player)
    db.session.commit()
    n = player.ascensions
    return True, (f"ASCENSION {ROMAN[min(n, 6)] if n <= 6 else n}: you return to Level 1 with everything you earned "
                  f"and a permanent +{int(ASCENSION_XP_BONUS * 100 * n)}% XP. The climb begins again.")


def choose_specialization(player, name):
    from app.models import Gate
    line = base_class(player.job_class)
    if not line or player.specialization:
        return False, "No specialisation to choose."
    if not player.gates.filter(Gate.kind == 'awakening', Gate.status == 'claimed').first():
        return False, "Clear the Second Awakening trial first."
    if name not in SPECIALIZATIONS[line]:
        return False, "Unknown specialisation."
    player.specialization = name
    db.session.commit()
    return True, f"SECOND AWAKENING: you are now a {name} {line}. {SPECIALIZATIONS[line][name]}"


def milestones(player):
    """
    Ordered list of {'level', 'rewards': [{'icon', 'title', 'detail'}], 'reached'}.
    Class-specific rewards follow the player's line; before the job change they're described generically.
    """
    from app.services import RANK_REQUIREMENTS, TITLE_DEFINITIONS

    by_level = {}

    def add(level, icon, title, detail):
        by_level.setdefault(level, []).append({'icon': icon, 'title': title, 'detail': detail})

    line = base_class(player.job_class)
    if line:
        for tier, (name, level) in enumerate(evolution_line(line), start=1):
            if tier == 1:
                add(level, 'wand-sparkles', f"Job Change: {name}", "Your class and its passive bonus.")
            else:
                add(level, 'sparkles', f"Evolution: {name}", f"Class evolution {ROMAN[tier]}.")
            add(level, CLASS_SKILLS[line]['icon'],
                f"Skill: {CLASS_SKILLS[line]['name']} {ROMAN[tier]}",
                _skill_upgrade_text(line, tier, player.specialization))
    else:
        add(10, 'wand-sparkles', "Job Change Trial",
            "Five trials decide your class: Assassin, Mage or Tank, each with a passive bonus.")
        add(10, 'zap', "Class skill unlocked",
            "Vanish (rest day), Insight (bonus focus XP) or Fortify (debt relief and penalty shield).")
        for tier, level in enumerate((20, 40, 60, 80, 100), start=2):
            add(level, 'sparkles', f"Class Evolution {ROMAN[tier]}",
                f"A new class name and skill tier {ROMAN[tier]}: stronger effect, {COOLDOWN_DAYS[tier]}-day cooldown.")

    from app.gates import EXAM_RANKS
    for _current, (next_rank, req_level, req_stats) in RANK_REQUIREMENTS.items():
        if next_rank in EXAM_RANKS:
            add(req_level, 'medal', f"Rank Assessment: {next_rank}-Rank",
                f"A 7-day exam opens once you also have {req_stats} total base stats. Pass it to be promoted.")
        else:
            add(req_level, 'medal', f"Hunter Rank {next_rank}",
                f"Promotion to {next_rank}-Rank (also needs {req_stats} total base stats).")

    add(15, 'swords', "Gates open",
        "A Gate appears every week: 72 hours, two objectives and a boss. Clear it for bonus XP, Coins and loot.")
    add(15, 'gem', "Loot drops", "Equipment drops from Gates, and sometimes from B, A and S quests.")
    add(25, 'ghost', "Shadow Army ranks",
        "Assign a shadow to a quest. It grows each time you complete it: Soldier, Knight, Elite, Commander, Marshal.")
    add(30, 'triangle-alert', "Red Gates",
        "Rare surprise gates: 48 hours, harder objectives, double rewards and Rare-or-better loot. Optional.")
    add(30, 'gem', "Epic loot", "Epic equipment (+6 to +8) can now drop.")
    if line:
        specs = " or ".join(f"{name} ({text[0].lower()}{text[1:-1]})" for name, text in SPECIALIZATIONS[line].items())
        add(50, 'sparkles', "Second Awakening", f"A 7-day trial, then choose your path: {specs}.")
    else:
        add(50, 'sparkles', "Second Awakening", "A 7-day trial, then choose one of two specialisations for your class.")
    add(60, 'crown', "Legendary sets",
        "Legendary set pieces (+10 to +12) drop. 2 pieces: +5 to two stats. 4 pieces: +5% XP.")
    add(80, 'flame', "Mythic Red Gates", "Every Red Gate you clear drops a Legendary piece.")
    nxt = (player.ascensions or 0) + 1
    add(100, 'star', f"Ascension {ROMAN[nxt] if nxt <= 6 else nxt}",
        f"Return to Level 1 keeping everything, with a permanent +{int(ASCENSION_XP_BONUS * 100)}% XP per Ascension.")

    for t in TITLE_DEFINITIONS:
        if t['unlock_condition'] == 'level' and t['unlock_value'] > 1:
            buff = _buff_text(t['buff'])
            add(t['unlock_value'], 'tag', f"Title: {t['name']}", buff or "A new title to equip.")

    ascended = bool(player.ascensions)
    result = []
    for level in sorted(by_level):
        reached = player.level >= level or (ascended and level < 100)
        result.append({'level': level, 'rewards': by_level[level], 'reached': reached})
    return result


def _buff_text(buff):
    from app.services import _STAT_LABELS
    if 'xp' in buff:
        return f"+{int(buff['xp'] * 100)}% XP when equipped."
    if 'coins' in buff:
        return f"+{int(buff['coins'] * 100)}% Coins when equipped."
    if 'stat' in buff:
        field, value = buff['stat']
        return f"+{value} {_STAT_LABELS.get(field, field)} when equipped."
    if 'all' in buff:
        return f"+{buff['all']} to every stat when equipped."
    return ''


def next_milestone(player):
    """The first unreached milestone plus progress towards it, or None once everything is reached."""
    stones = milestones(player)
    upcoming = [m for m in stones if not m['reached']]
    if not upcoming:
        return None
    target = upcoming[0]
    previous = max([m['level'] for m in stones if m['level'] <= player.level] + [1])
    span = max(1, target['level'] - previous)
    within = (player.level - previous) + (player.xp / player.xp_required if player.xp_required else 0)
    return {**target, 'levels_away': target['level'] - player.level,
            'progress': max(0, min(100, round(within / span * 100))),
            'after': upcoming[1:4]}


def level_up_preview(player, previous_level):
    """One line for the level-up overlay: what this level-up unlocked, else what comes next."""
    unlocked = [r['title'] for m in milestones(player)
                if previous_level < m['level'] <= player.level for r in m['rewards']]
    if unlocked:
        return "UNLOCKED: " + " · ".join(unlocked)
    nxt = next_milestone(player)
    if not nxt:
        return ""
    away = nxt['levels_away']
    return f"NEXT: {nxt['rewards'][0]['title']} at LV {nxt['level']} ({away} level{'s' if away != 1 else ''} away)"
