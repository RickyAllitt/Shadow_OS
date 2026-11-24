"""
Background tasks, written as idempotent "catch-up" checks.

Instead of firing at exact clock times (which silently never happen if the process is asleep or
wasn't running), one tick asks "what is due right now that hasn't been sent yet?" and records what
it sent. The tick runs every 5 minutes in-process (see register_background_jobs) and can also be
triggered over HTTP by an external cron (/tasks/run), which wakes sleeping free-tier hosts.

    Reminders        each player's own reminder time, once per game day     services.send_due_reminders
    Deadline nudges  08:00 in each player's timezone, once per local day    send_due_deadline_reminders
    Weekly Report    any time after Monday 08:00 Madrid, once per week      send_weekly_reports_if_due
"""
import fcntl
import os
import tempfile
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import ActivityEvent, Notification, Player, Quest

TICK_MINUTES = 5
DEADLINE_HOUR = 8
WEEKLY_REPORT_HOUR = 8          # Monday, GAME_TIMEZONE (the league's shared week)
READ_NOTIFICATION_TTL_DAYS = 7


def _sent_since(player_id, kind, since_utc):
    return ActivityEvent.query.filter(
        ActivityEvent.player_id == player_id, ActivityEvent.kind == kind,
        ActivityEvent.occurred_at >= since_utc.replace(tzinfo=None)).first() is not None


# ---------------------------------------------------------------- deadline nudges

def send_due_deadline_reminders(app_instance, now=None):
    """
    From 08:00 in each player's timezone, once per local day: quests due today / tomorrow.
    Quest due dates are stored as the local wall-clock time the player entered, so they're
    compared with the player's local time (not UTC).
    """
    from app.league import record
    from app.services import create_notification, player_tz
    with app_instance.app_context():
        now = now or datetime.now(timezone.utc)
        sent = 0
        for player in Player.query.filter_by(setup_complete=True).all():
            if player.is_on_vacation:
                continue
            tz = player_tz(player)
            local_now = now.astimezone(tz)
            if local_now.hour < DEADLINE_HOUR:
                continue
            local_midnight_utc = tz.localize(datetime(local_now.year, local_now.month, local_now.day)).astimezone(timezone.utc)
            if _sent_since(player.id, 'deadline_check', local_midnight_utc):
                continue

            wall_now = local_now.replace(tzinfo=None)
            today_end = wall_now.replace(hour=23, minute=59, second=59, microsecond=0)
            tomorrow_end = today_end + timedelta(days=1)
            open_quests = Quest.query.filter(Quest.player_id == player.id, Quest.is_completed.is_(False),
                                             Quest.is_daily.is_(False), Quest.is_penalty.is_(False),
                                             Quest.due_date.isnot(None))
            for q in open_quests.filter(Quest.due_date >= wall_now, Quest.due_date <= today_end):
                create_notification(player.id, f"REMINDER: '{q.title}' is due TODAY.", "warning")
            for q in open_quests.filter(Quest.due_date > today_end, Quest.due_date <= tomorrow_end):
                create_notification(player.id, f"HEADS UP: '{q.title}' is due tomorrow.", "info")
            record(player, 'deadline_check', when=now)
            db.session.commit()
            sent += 1
        return sent


# ---------------------------------------------------------------- weekly report

def weekly_report_due_at(now=None):
    """UTC time from which this week's report (about last week) may be sent."""
    from app.league import week_start_for
    from app.services import GAME_TIMEZONE
    week = week_start_for(now)
    return GAME_TIMEZONE.localize(datetime(week.year, week.month, week.day, WEEKLY_REPORT_HOUR)).astimezone(timezone.utc)


def send_weekly_reports_if_due(app_instance, now=None):
    """After Monday 08:00 (Madrid): each active player gets last week's report once."""
    from app.kpi import weekly_report
    from app.league import record, week_start_for
    from app.services import create_notification, trigger_push_notification
    with app_instance.app_context():
        now = now or datetime.now(timezone.utc)
        if now < weekly_report_due_at(now):
            return 0
        week = week_start_for(now)
        sent = 0
        for player in Player.query.filter_by(setup_complete=True).all():
            if ActivityEvent.query.filter_by(player_id=player.id, kind='report_sent', week_start=week).first():
                continue
            record(player, 'report_sent', when=now)  # mark first, so an error never causes repeats
            r = weekly_report(player, now=now)
            if r['has_activity']:
                placing = f" League #{r['placing']}." if r['placing'] else ""
                msg = (f"WEEKLY SYSTEM REPORT: {r['perfect_days']}/{r['days_tracked'] or 7} perfect days, "
                       f"{r['points']:.0f} pts.{placing} Focus next: {r['weakest']['name']}.")
                create_notification(player.id, msg, "info")
                trigger_push_notification(player.id, "Weekly System Report", msg, url="/report")
                sent += 1
            db.session.commit()
        return sent


# ---------------------------------------------------------------- housekeeping & tick

def purge_old_notifications(app_instance, now=None):
    with app_instance.app_context():
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=READ_NOTIFICATION_TTL_DAYS)
        n = Notification.query.filter(Notification.is_read.is_(True),
                                      Notification.created_at < cutoff.replace(tzinfo=None)).delete()
        db.session.commit()
        return n


def run_due_tasks(app_instance, now=None):
    """One tick: run every due task. A failure in one task never blocks the others."""
    from app.services import send_due_reminders
    results = {}
    for name, task in (('reminders', send_due_reminders), ('deadlines', send_due_deadline_reminders),
                       ('weekly_reports', send_weekly_reports_if_due), ('purged', purge_old_notifications)):
        try:
            results[name] = task(app_instance, now)
        except Exception as exc:  # keep ticking; surface the error in logs and the HTTP response
            with app_instance.app_context():
                db.session.rollback()
            app_instance.logger.exception("Background task %s failed", name)
            results[name] = f"error: {exc.__class__.__name__}"
    return results


# ---------------------------------------------------------------- in-process scheduler

_lock_handle = None


def acquire_scheduler_lock(path=None):
    """
    Only one process per machine runs the in-process scheduler (gunicorn starts several workers,
    each calling create_app). Returns True if this process holds the lock.
    """
    global _lock_handle
    if _lock_handle is not None:
        return True
    path = path or os.environ.get('SCHEDULER_LOCK_FILE') or os.path.join(tempfile.gettempdir(), 'shadow_os_scheduler.lock')
    handle = open(path, 'a')
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    _lock_handle = handle
    return True


def register_background_jobs(app, scheduler):
    """Start the 5-minute tick, whatever way the app was started (gunicorn, run.py, flask run)."""
    if app.config.get('TESTING') or os.environ.get('SCHEDULER_ENABLED', '1') == '0':
        return False
    # Flask's debug reloader runs a watcher parent + a serving child (WERKZEUG_RUN_MAIN=true);
    # only the child should schedule. run.py marks the reloader case with SHADOW_RELOADER.
    if os.environ.get('SHADOW_RELOADER') == '1' and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return False
    if not acquire_scheduler_lock():
        app.logger.info("Background jobs already running in another process.")
        return False
    if not scheduler.running:
        scheduler.init_app(app)  # re-configuring a running scheduler is not allowed
    if not scheduler.get_job('due_tasks'):
        scheduler.add_job(id='due_tasks', func=run_due_tasks, args=[app], trigger='interval',
                          minutes=TICK_MINUTES, coalesce=True, max_instances=1, misfire_grace_time=600,
                          next_run_time=datetime.now(timezone.utc) + timedelta(seconds=30))
    if not scheduler.running:
        scheduler.start()
    print(f">> SYSTEM: Background jobs running (every {TICK_MINUTES} min, pid {os.getpid()}).", flush=True)
    return True
