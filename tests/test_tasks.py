"""Background jobs: catch-up tasks, once-per-period dedupe, the /tasks/run hook and scheduler start-up."""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytz
import pytest
from flask_apscheduler import APScheduler

from app import league, tasks
from app.extensions import db
from app.models import ActivityEvent, Notification, Player, Quest


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def local(tz_name, *args):
    return pytz.timezone(tz_name).localize(datetime(*args)).astimezone(timezone.utc)


# --- deadline nudges ---

def test_deadline_nudges_use_local_time_once_per_day(app):
    p = player('NY', timezone='America/New_York')
    # Due dates are stored as the local wall-clock time the player typed
    db.session.add_all([
        Quest(title='Due Today', player_id=p.id, due_date=datetime(2026, 11, 24, 18, 0)),
        Quest(title='Due Tomorrow', player_id=p.id, due_date=datetime(2026, 11, 25, 9, 0)),
        Quest(title='Overdue', player_id=p.id, due_date=datetime(2026, 11, 24, 7, 0)),
        Quest(title='Far', player_id=p.id, due_date=datetime(2026, 11, 30, 9, 0)),
        Quest(title='Done', player_id=p.id, due_date=datetime(2026, 11, 24, 20, 0), is_completed=True),
    ])
    db.session.commit()
    assert tasks.send_due_deadline_reminders(app, local('America/New_York', 2026, 11, 24, 7, 30)) == 0  # before 08:00
    assert tasks.send_due_deadline_reminders(app, local('America/New_York', 2026, 11, 24, 8, 5)) == 1
    assert tasks.send_due_deadline_reminders(app, local('America/New_York', 2026, 11, 24, 15, 0)) == 0  # once per day
    assert sorted(n.message for n in Notification.query) == [
        "HEADS UP: 'Due Tomorrow' is due tomorrow.", "REMINDER: 'Due Today' is due TODAY."]
    assert tasks.send_due_deadline_reminders(app, local('America/New_York', 2026, 11, 25, 8, 0)) == 1  # next day


def test_deadline_nudges_catch_up_after_sleeping(app):
    """If the app was asleep at 08:00, the first tick afterwards still sends today's nudges."""
    p = player()
    db.session.add(Quest(title='Report', player_id=p.id, due_date=datetime(2026, 11, 24, 23, 0)))
    db.session.commit()
    assert tasks.send_due_deadline_reminders(app, local('Europe/Madrid', 2026, 11, 24, 16, 47)) == 1


# --- weekly report ---

def test_weekly_report_waits_for_monday_8am_then_sends_once(app):
    p = player()
    monday = league.week_start_for()
    last_week = monday - timedelta(days=7)
    db.session.add(ActivityEvent(player_id=p.id, kind='quest', points=42, week_start=last_week,
                                 occurred_at=datetime.combine(last_week, datetime.min.time()) + timedelta(days=2)))
    db.session.commit()
    due = tasks.weekly_report_due_at()
    assert due == local('Europe/Madrid', monday.year, monday.month, monday.day, 8, 0)
    assert tasks.send_weekly_reports_if_due(app, due - timedelta(minutes=1)) == 0
    assert tasks.send_weekly_reports_if_due(app, due + timedelta(hours=30)) == 1  # late (woke up Tuesday)
    assert tasks.send_weekly_reports_if_due(app, due + timedelta(hours=31)) == 0  # only once per week
    assert 'WEEKLY SYSTEM REPORT' in Notification.query.one().message


def test_weekly_report_skips_inactive_players_without_repeats(app):
    player('Idle')
    due = tasks.weekly_report_due_at()
    assert tasks.send_weekly_reports_if_due(app, due + timedelta(hours=1)) == 0
    assert Notification.query.count() == 0
    assert ActivityEvent.query.filter_by(kind='report_sent').count() == 1  # checked, won't recompute


# --- tick ---

def test_tick_runs_everything_and_isolates_failures(app, monkeypatch):
    old = Notification(player_id=player().id, message='old', is_read=True,
                       created_at=datetime.now(timezone.utc) - timedelta(days=30))
    db.session.add(old); db.session.commit()

    def boom(app_instance, now=None):
        raise RuntimeError('push service down')
    monkeypatch.setattr(tasks, 'send_due_deadline_reminders', boom)
    results = tasks.run_due_tasks(app)
    assert results['deadlines'] == 'error: RuntimeError'
    assert results['purged'] == 1 and set(results) == {'reminders', 'deadlines', 'weekly_reports', 'purged'}


# --- HTTP wake-up hook ---

def test_tasks_endpoint_disabled_without_secret(client, monkeypatch):
    monkeypatch.delenv('CRON_SECRET', raising=False)
    assert client.post('/tasks/run').status_code == 404


def test_tasks_endpoint_requires_secret_header(client, app, monkeypatch):
    monkeypatch.setenv('CRON_SECRET', 's3cret-value')
    assert client.post('/tasks/run').status_code == 403
    assert client.post('/tasks/run', headers={'X-Cron-Secret': 'wrong'}).status_code == 403
    assert client.get('/tasks/run?key=s3cret-value').status_code == 403  # never via URL
    r = client.post('/tasks/run', headers={'X-Cron-Secret': 's3cret-value'})  # no CSRF token needed
    assert r.status_code == 200 and r.get_json()['ok']
    assert set(r.get_json()['results']) == {'reminders', 'deadlines', 'weekly_reports', 'purged'}
    assert client.get('/tasks/run', headers={'Authorization': 'Bearer s3cret-value'}).status_code == 200


# --- scheduler start-up ---

def test_scheduler_not_started_in_tests_or_when_disabled(app, monkeypatch):
    s = APScheduler()
    assert tasks.register_background_jobs(app, s) is False  # TESTING
    app.config['TESTING'] = False
    monkeypatch.setenv('SCHEDULER_ENABLED', '0')
    assert tasks.register_background_jobs(app, s) is False
    monkeypatch.delenv('SCHEDULER_ENABLED')
    monkeypatch.setenv('SHADOW_RELOADER', '1')  # debug reloader's watcher process
    monkeypatch.delenv('WERKZEUG_RUN_MAIN', raising=False)
    assert tasks.register_background_jobs(app, s) is False
    app.config['TESTING'] = True


def test_scheduler_registers_tick(app, monkeypatch, tmp_path):
    app.config['TESTING'] = False
    monkeypatch.setenv('SCHEDULER_LOCK_FILE', str(tmp_path / 'lock'))
    monkeypatch.setattr(tasks, '_lock_handle', None)
    s = APScheduler()
    try:
        assert tasks.register_background_jobs(app, s) is True
        job = s.get_job('due_tasks')
        assert job is not None and job.trigger.interval == timedelta(minutes=tasks.TICK_MINUTES)
        assert tasks.register_background_jobs(app, s) is True and len(s.get_jobs()) == 1  # no duplicates
    finally:
        s.shutdown(wait=False)
        app.config['TESTING'] = True
        if tasks._lock_handle:
            tasks._lock_handle.close()
        monkeypatch.setattr(tasks, '_lock_handle', None)


def test_only_one_process_gets_the_scheduler_lock(tmp_path):
    """Simulates two gunicorn workers: the second process can't take the lock while the first holds it."""
    lock = tmp_path / 'scheduler.lock'
    code = ("import sys, time; sys.path.insert(0, {root!r}); from app.tasks import acquire_scheduler_lock; "
            "print(acquire_scheduler_lock({lock!r}), flush=True); time.sleep({hold})")
    root = os.getcwd()
    env = {**os.environ, 'SECRET_KEY': 'test'}  # keeps config quiet so stdout is just the result
    first = subprocess.Popen([sys.executable, '-c', code.format(root=root, lock=str(lock), hold=3)],
                             stdout=subprocess.PIPE, text=True, env=env)
    try:
        assert first.stdout.readline().strip() == 'True'
        second = subprocess.run([sys.executable, '-c', code.format(root=root, lock=str(lock), hold=0)],
                                capture_output=True, text=True, timeout=30, env=env)
        assert second.stdout.strip() == 'False'
    finally:
        first.kill()
        first.wait()
