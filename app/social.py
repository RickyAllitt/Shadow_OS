"""
Social features: Raids (shared goals) and Kudos on S-rank clears (Hall of Feats).

Raids: anyone can start one; everyone can log contributions. Individual logs earn no XP (they would
be trivially farmable); when the target is reached before the deadline, every contributor gets
RAID_REWARD_XP / RAID_REWARD_COINS and league points. Logs do count toward Life Balance.
"""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import ActivityEvent, Kudos, Notification, Player, Quest, Raid, RaidContribution

RAID_REWARD_XP = 500
RAID_REWARD_COINS = 100
MAX_ACTIVE_RAIDS = 5
MAX_RAID_DAYS = 90
RAID_EFFORT_UNITS = 1          # Life Balance units per contribution
KUDOS_EMOJI = ('🔥', '👏', '💪', '👑')
FEAT_WINDOW_DAYS = 30


def _utc(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _notify(player_id, message, category='info', push_title=None, url='/'):
    from app.services import trigger_push_notification
    db.session.add(Notification(player_id=player_id, message=message, category=category))
    if push_title:
        trigger_push_notification(player_id, push_title, message, url=url)


# ---------------------------------------------------------------- raids

def finalize_expired_raids(now=None):
    """Mark active raids past their deadline as failed (lazily, whenever raids are viewed)."""
    now = now or datetime.now(timezone.utc)
    expired = Raid.query.filter(Raid.status == 'active', Raid.ends_at <= now.replace(tzinfo=None)).all()
    for raid in expired:
        raid.status = 'failed'
        for pid in {c.player_id for c in raid.contributions}:
            _notify(pid, f"RAID FAILED: '{raid.title}' ended at {raid.total:g}/{raid.target:g} {raid.unit}.")
    if expired:
        db.session.commit()
    return expired


def create_raid(player, title, unit, target, days, stat='STR'):
    from app.services import normalize_stat
    title, unit = (title or '').strip()[:80], (unit or '').strip()[:20]
    if not title or not unit:
        return None, "A raid needs a title and a unit (e.g. km)."
    if not (0 < target <= 10_000_000):
        return None, "Target must be a positive number."
    if not (1 <= days <= MAX_RAID_DAYS):
        return None, f"Duration must be 1-{MAX_RAID_DAYS} days."
    finalize_expired_raids()
    if Raid.query.filter_by(status='active').count() >= MAX_ACTIVE_RAIDS:
        return None, f"There are already {MAX_ACTIVE_RAIDS} active raids. Finish one first."
    raid = Raid(title=title, unit=unit, target=target, stat=normalize_stat(stat, default='STR'),
                created_by=player.id, ends_at=datetime.now(timezone.utc) + timedelta(days=days))
    db.session.add(raid)
    db.session.flush()
    for other in Player.query.filter(Player.id != player.id, Player.setup_complete.is_(True)):
        _notify(other.id, f"NEW RAID by {player.name}: {title} ({target:g} {unit} in {days} days). Join in!",
                push_title="New Raid", url=f"/raids/{raid.id}")
    db.session.commit()
    return raid, f"RAID STARTED: {title}. Rally your friends!"


def contribute(player, raid, amount):
    """Log a contribution. Returns (ok, message). Completes the raid when the target is reached."""
    from app.kpi import record_effort
    finalize_expired_raids()
    if raid.status != 'active':
        return False, "This raid is no longer active."
    if not (0 < amount <= 1_000_000):
        return False, f"Enter how many {raid.unit} you did."
    db.session.add(RaidContribution(raid_id=raid.id, player_id=player.id, amount=amount))
    record_effort(player, raid.stat, RAID_EFFORT_UNITS)
    db.session.flush()
    db.session.refresh(raid)
    if raid.total >= raid.target:
        _complete_raid(raid)
        db.session.commit()
        return True, f"RAID CLEARED: {raid.title}! Every contributor earns +{RAID_REWARD_XP} XP and +{RAID_REWARD_COINS} Coins."
    db.session.commit()
    return True, f"LOGGED: +{amount:g} {raid.unit} · {raid.total:g}/{raid.target:g} ({raid.percent}%)"


def _complete_raid(raid):
    from app.league import record_points
    from app.services import add_xp, process_level_up
    raid.status, raid.completed_at = 'completed', datetime.now(timezone.utc)
    for pid in {c.player_id for c in raid.contributions}:
        p = db.session.get(Player, pid)
        add_xp(p, RAID_REWARD_XP)
        p.coins += RAID_REWARD_COINS
        process_level_up(p)
        record_points(p, 'raid', RAID_REWARD_XP)
        _notify(pid, f"⚔️ RAID CLEARED: {raid.title}. +{RAID_REWARD_XP} XP, +{RAID_REWARD_COINS} Coins.",
                category='success', push_title="Raid cleared!", url=f"/raids/{raid.id}")


def cancel_raid(player, raid):
    others = {c.player_id for c in raid.contributions} - {player.id}
    if raid.created_by != player.id:
        return False, "Only the raid's creator can cancel it."
    if raid.status != 'active':
        return False, "This raid is no longer active."
    if others:
        return False, "Others have already contributed, so this raid can't be cancelled."
    raid.status = 'cancelled'
    db.session.commit()
    return True, f"Raid cancelled: {raid.title}."


def raid_leaderboard(raid):
    totals = {}
    for c in raid.contributions:
        totals[c.player] = totals.get(c.player, 0) + c.amount
    return sorted(((p, round(v, 2)) for p, v in totals.items()), key=lambda x: -x[1])


# ---------------------------------------------------------------- Hall of Feats & kudos

def recent_feats(days=FEAT_WINDOW_DAYS, now=None):
    """S-rank clears (non-penalty) from the last `days` days, newest first."""
    now = now or datetime.now(timezone.utc)
    events = ActivityEvent.query.filter(
        ActivityEvent.kind == 'effort', ActivityEvent.rank == 'S',
        ActivityEvent.occurred_at >= (now - timedelta(days=days)).replace(tzinfo=None),
    ).order_by(ActivityEvent.occurred_at.desc()).all()
    feats = []
    for e in events:
        quest = db.session.get(Quest, e.quest_id) if e.quest_id else None
        if quest is not None and (quest.is_daily or quest.is_penalty):
            continue
        counts = {}
        for k in e.kudos:
            counts[k.emoji] = counts.get(k.emoji, 0) + 1
        feats.append({'event': e, 'player': e.player, 'title': quest.title if quest else 'an S-rank quest',
                      'when': _utc(e.occurred_at), 'counts': counts,
                      'givers': {k.from_player_id: k.emoji for k in e.kudos}})
    return feats


def give_kudos(player, event, emoji):
    if emoji not in KUDOS_EMOJI:
        return False, "Unknown reaction."
    if event is None or event.kind != 'effort' or event.rank != 'S':
        return False, "You can only cheer S-rank clears."
    if event.player_id == player.id:
        return False, "You can't give kudos to yourself."
    existing = Kudos.query.filter_by(event_id=event.id, from_player_id=player.id).first()
    if existing:
        if existing.emoji == emoji:
            db.session.delete(existing)  # tapping the same reaction again removes it
            db.session.commit()
            return True, "Kudos removed."
        existing.emoji = emoji
        db.session.commit()
        return True, f"Changed to {emoji}."
    db.session.add(Kudos(event_id=event.id, from_player_id=player.id, emoji=emoji))
    quest = db.session.get(Quest, event.quest_id) if event.quest_id else None
    _notify(event.player_id, f"{emoji} {player.name} cheered your S-rank: {quest.title if quest else 'an S-rank quest'}",
            category='success', push_title="Kudos!", url="/leaderboard#feats")
    db.session.commit()
    return True, f"{emoji} sent to {event.player.name}!"
