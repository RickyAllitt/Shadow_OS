"""
Shadow Army grades (Lv 25). A shadow can be assigned to one of your quests; every completion of that
quest counts as a kill. Kills promote the shadow, and each grade multiplies its stat buff.
"""
from app.extensions import db
from app.models import Quest, Shadow

SHADOW_LEVEL = 25
GRADES = (('Soldier', 0), ('Knight', 10), ('Elite', 30), ('Commander', 60), ('Marshal', 100))


def grade_index(shadow):
    kills = shadow.kills or 0
    return max(i for i, (_name, need) in enumerate(GRADES) if kills >= need)


def grade_name(shadow):
    return GRADES[grade_index(shadow)][0]


def next_grade(shadow):
    i = grade_index(shadow)
    return GRADES[i + 1] if i + 1 < len(GRADES) else None


def buff_weight(shadow):
    """Soldier counts once in the army buff, Knight twice ... Marshal five times."""
    return grade_index(shadow) + 1


def army_weight(player):
    return sum(buff_weight(s) for s in player.shadows)


def assign(player, shadow_id, quest_id):
    from app.progression import effective_level
    if effective_level(player) < SHADOW_LEVEL:
        return False, f"Shadow commands unlock at Level {SHADOW_LEVEL}."
    shadow = db.session.get(Shadow, shadow_id)
    if not shadow or shadow.player_id != player.id:
        return False, "Shadow not found."
    if not quest_id:
        shadow.assigned_quest_id = None
        db.session.commit()
        return True, f"{shadow.original_quest_name} stands down."
    quest = db.session.get(Quest, quest_id)
    if not quest or quest.player_id != player.id or quest.is_penalty:
        return False, "Quest not found."
    shadow.assigned_quest_id = quest.id
    db.session.commit()
    return True, f"{shadow.original_quest_name} now hunts alongside \"{quest.title}\"."


def record_kill(player, quest):
    """Called on every quest completion. Returns promotion messages."""
    messages = []
    for shadow in player.shadows:
        if shadow.assigned_quest_id == quest.id:
            before = grade_index(shadow)
            shadow.kills = (shadow.kills or 0) + 1
            if grade_index(shadow) > before:
                messages.append(f"SHADOW PROMOTED: {shadow.original_quest_name} is now a {grade_name(shadow)}!")
    return messages


def max_grade(player):
    return max((grade_index(s) for s in player.shadows), default=-1)
