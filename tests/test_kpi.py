"""Life Balance scores, measured quests, sleep/focus effort and the weekly System Report."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text

from app import kpi, league
from app.extensions import db
from app.models import ActivityEvent, Notification, Player, Quest
from app.services import process_quest_completion
from app.tasks import send_weekly_reports_if_due


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def me():
    db.session.expire_all()
    return Player.query.filter_by(name='AuthUser').first()


def effort(p, stat, units, days_ago=0.0, rank=None, now=None):
    when = (now or datetime.now(timezone.utc)) - timedelta(days=days_ago)
    db.session.add(ActivityEvent(player_id=p.id, kind='effort', stat=stat, units=units, rank=rank,
                                 occurred_at=when.replace(tzinfo=None), week_start=league.week_start_for(when)))
    db.session.commit()


def score_for(units):
    import math
    return round(100 * (1 - math.exp(-units / kpi.SCORE_SCALE)))


# --- Life Balance maths ---

def test_effort_decays_with_two_week_half_life(app):
    p = player()
    effort(p, 'STR', 20)
    effort(p, 'INT', 20, days_ago=14)
    effort(p, 'AGI', 20, days_ago=61)  # outside the window
    scores = kpi.area_scores(p)
    assert scores['STR'] == score_for(20)
    assert scores['INT'] == score_for(10)
    assert scores['AGI'] == 0 and scores['VIT'] == 0


def test_score_calibration_one_daily_per_day(app):
    p = player()
    for d in range(60):
        effort(p, 'VIT', 1, days_ago=d)
    assert 50 <= kpi.area_scores(p)['VIT'] <= 60


def test_life_balance_trend_and_weakest(app):
    p = player()
    effort(p, 'STR', 15, days_ago=10)
    effort(p, 'STR', 15, days_ago=1)
    effort(p, 'INT', 3, days_ago=1)
    lb = kpi.life_balance(p)
    by = {a['code']: a for a in lb['areas']}
    assert by['STR']['trend'] > 0 and by['STR']['score'] > by['INT']['score']
    assert lb['strongest']['code'] == 'STR' and lb['weakest']['score'] == 0
    assert lb['overall'] == round(sum(a['score'] for a in lb['areas']) / 5)


def test_scores_can_be_computed_for_the_past(app):
    p = player()
    now = datetime.now(timezone.utc)
    effort(p, 'SNS', 25, days_ago=3)
    assert kpi.area_scores(p, now - timedelta(days=5))['SNS'] == 0
    assert kpi.area_scores(p, now)['SNS'] > 0


# --- effort sources ---

def test_quest_completion_logs_rank_weighted_effort(app):
    p = player(xp_required=10_000)
    quests = [Quest(title='Gym', rank='B', stat_reward='STR', player=p),
              Quest(title='Daily read', rank='E', stat_reward='SEN', is_daily=True, player=p),
              Quest(title='PENALTY', rank='A', is_penalty=True, stat_reward='VIT', player=p)]
    db.session.add_all(quests); db.session.commit()
    for q in quests:
        process_quest_completion(p, q)
    efforts = {(e.stat, e.units, e.rank) for e in ActivityEvent.query.filter_by(kind='effort')}
    assert efforts == {('STR', 5, 'B'), ('SNS', 1, 'E')}  # penalties don't count; SEN normalised


def test_focus_and_sleep_effort(auth_client, app, csrf_token):
    auth_client.post('/focus_complete', json={'minutes': 50}, headers={'X-CSRFToken': csrf_token})
    focus = ActivityEvent.query.filter_by(kind='effort', stat='INT').one()
    assert focus.units == 2.0

    auth_client.post('/track_sleep', data={'hours': '8', 'csrf_token': csrf_token})
    assert ActivityEvent.query.filter_by(kind='sleep').one().value == 8.0
    assert ActivityEvent.query.filter_by(kind='effort', stat='VIT').one().units == 3.0


@pytest.mark.parametrize('hours, units', [(6.5, 1.5), (4, None)])
def test_sleep_units_thresholds(app, hours, units):
    p = player()
    kpi.record_sleep(p, hours)
    db.session.commit()
    vit = ActivityEvent.query.filter_by(kind='effort', stat='VIT').first()
    assert (vit.units if vit else None) == units


# --- measured quests ---

def _add_measured(client, token, title='Pushups', target='50', unit='pushups', daily=True):
    data = {'title': title, 'rank': 'E', 'stat': 'STR', 'metric_target': target, 'metric_unit': unit,
            'csrf_token': token}
    if daily:
        data['is_daily'] = 'on'
    client.post('/add_quest', data=data)
    return Quest.query.filter_by(title=title).one()


def test_create_measured_quest_and_validation(auth_client, app, csrf_token):
    q = _add_measured(auth_client, csrf_token)
    assert q.is_measured and (q.metric_target, q.metric_unit) == (50, 'pushups')
    assert _add_measured(auth_client, csrf_token, 'No unit', '10', '').metric_unit == 'units'
    for bad in ('abc', '-5', '0'):
        assert not _add_measured(auth_client, csrf_token, f'Bad {bad}', bad, 'x').is_measured


def test_logging_accumulates_then_completes(auth_client, app, csrf_token):
    q = _add_measured(auth_client, csrf_token)
    page = auth_client.get(f'/complete/{q.id}').data
    assert b'How many pushups did you just do?' in page and b'value="50"' in page

    page = auth_client.post(f'/complete/{q.id}', data={'amount': '20', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'LOGGED: +20 pushups \xc2\xb7 20/50 pushups today' in page
    db.session.expire_all()
    q = db.session.get(Quest, q.id)
    assert not q.is_completed and q.progress == 40
    assert b'value="30"' in auth_client.get(f'/complete/{q.id}').data  # remaining pre-filled
    assert b'#i-ruler"></use></svg> 20/50 pushups' in auth_client.get('/').data  # badge on dashboard

    page = auth_client.post(f'/complete/{q.id}', data={'amount': '35', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'COMPLETE: Pushups | 55/50 pushups' in page
    db.session.expire_all()
    assert db.session.get(Quest, q.id).is_completed


def test_logging_rejects_bad_amounts(auth_client, app, csrf_token):
    q = _add_measured(auth_client, csrf_token)
    for bad in ('', 'lots', '0', '-3', '99999999'):
        page = auth_client.post(f'/complete/{q.id}', data={'amount': bad, 'csrf_token': csrf_token},
                                follow_redirects=True).data
        assert b'Enter how many pushups you did' in page
    assert ActivityEvent.query.filter_by(kind='metric').count() == 0


def test_daily_measure_counts_only_since_last_reset(app):
    p = player(last_daily_reset=datetime.now(timezone.utc) - timedelta(hours=2))
    q = Quest(title='Read', is_daily=True, metric_target=20, metric_unit='pages', player=p)
    db.session.add(q); db.session.commit()
    db.session.add(ActivityEvent(player_id=p.id, kind='metric', value=15, quest_id=q.id, week_start=league.week_start_for(),
                                 occurred_at=(datetime.now(timezone.utc) - timedelta(hours=5)).replace(tzinfo=None)))
    db.session.commit()
    assert kpi.metric_total(p, q) == 0  # yesterday's pages don't count today
    total, reached = kpi.log_metric(p, q, 20)
    assert (total, reached, q.progress) == (20, True, 100)


def test_one_off_measure_accumulates_across_days(app):
    p = player()
    q = Quest(title='Read a book', metric_target=300, metric_unit='pages', player=p)
    db.session.add(q); db.session.commit()
    db.session.add(ActivityEvent(player_id=p.id, kind='metric', value=120, quest_id=q.id, week_start=league.week_start_for(),
                                 occurred_at=(datetime.now(timezone.utc) - timedelta(days=3)).replace(tzinfo=None)))
    db.session.commit()
    total, reached = kpi.log_metric(p, q, 50)
    assert (total, reached, q.progress) == (170, False, 56)


def test_edit_measure_is_free_even_on_dailies(auth_client, app, csrf_token):
    q = _add_measured(auth_client, csrf_token)
    auth_client.post(f'/edit_quest/{q.id}', data={'metric_target': '80', 'metric_unit': 'reps', 'csrf_token': csrf_token})
    db.session.expire_all()
    q = db.session.get(Quest, q.id)
    assert (q.metric_target, q.metric_unit) == (80, 'reps') and me().coins == 0
    assert b'value="80.0"' in auth_client.get(f'/edit_quest/{q.id}').data
    auth_client.post(f'/edit_quest/{q.id}', data={'metric_target': '', 'csrf_token': csrf_token})
    db.session.expire_all()
    assert not db.session.get(Quest, q.id).is_measured


def test_completing_an_already_completed_quest_does_not_crash(auth_client, app, csrf_token):
    q = Quest(title='Done', rank='E', player=me(), is_completed=True)
    db.session.add(q); db.session.commit()
    r = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True)
    assert r.status_code == 200 and b'already complete' in r.data


def test_metric_history_buckets_by_game_day(app):
    p = player()
    q = Quest(title='Water', is_daily=True, metric_target=2, metric_unit='L', player=p)
    db.session.add(q); db.session.commit()
    now = datetime.now(timezone.utc)
    for days_ago, v in ((0, 1.0), (0, 0.5), (2, 2.0)):
        when = now - timedelta(days=days_ago)
        db.session.add(ActivityEvent(player_id=p.id, kind='metric', value=v, quest_id=q.id,
                                     occurred_at=when.replace(tzinfo=None), week_start=league.week_start_for(when)))
    db.session.commit()
    history = kpi.metric_history(p, q, days=5, now=now)
    assert len(history) == 5 and [v for _, v in history][-3:] == [2.0, 0.0, 1.5]


# --- pages ---

def test_dashboard_life_balance_panel(auth_client, app):
    effort(me(), 'STR', 40)
    page = auth_client.get('/').data
    assert b'LIFE BALANCE' in page and b'Neglected:' in page
    assert b'data-width="%d"' % score_for(40) in page


def test_analytics_has_radar_and_measure_charts(auth_client, app, csrf_token):
    q = _add_measured(auth_client, csrf_token)
    page = auth_client.get('/analytics').data
    assert b'id="balanceChart"' in page and f'id="measure-{q.id}"'.encode() in page
    assert b'PUSHUPS' in page


# --- weekly report ---

def _last_week_activity(p, rival=None):
    last = league.week_start_for() - timedelta(days=7)
    mid = league.week_ends_at(last) - timedelta(days=3)
    rows = [
        ActivityEvent(player_id=p.id, kind='quest', points=60, week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='effort', stat='STR', units=5, rank='B', week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='effort', stat='INT', units=1, rank='E', week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='focus', points=5, minutes=150, week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='sleep', value=7, week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='sleep', value=8, week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='daily_result', success=True, week_start=last, occurred_at=mid),
        ActivityEvent(player_id=p.id, kind='daily_result', success=False, week_start=last, occurred_at=mid),
    ]
    if rival:
        rows.append(ActivityEvent(player_id=rival.id, kind='quest', points=90, week_start=last, occurred_at=mid))
    db.session.add_all(rows)
    db.session.commit()
    return last


def test_weekly_report_contents(app):
    from app.models import Rivalry
    p, bro = player('Me'), player('Bro')
    db.session.add(Rivalry(player_id=p.id, rival_id=bro.id)); db.session.commit()
    last = _last_week_activity(p, rival=bro)
    r = kpi.weekly_report(p)
    assert r['week_start'] == last and not r['is_current'] and r['has_activity']
    assert (r['points'], r['placing'], r['competitors'], r['winner'].name) == (65, 2, 2, 'Bro')
    assert (r['perfect_days'], r['days_tracked']) == (1, 2)
    assert r['quests_completed'] == 2 and r['rank_counts']['B'] == 1 and r['rank_counts']['E'] == 1
    assert (r['focus_hours'], r['sleep_avg'], r['sleep_nights']) == (2.5, 7.5, 2)
    assert r['duel']['result'] == 'LOST'
    by = {a['code']: a for a in r['areas']}
    assert by['STR']['change'] > 0 and r['weakest']['end'] == 0


def test_report_pages(auth_client, app):
    _last_week_activity(me())
    page = auth_client.get('/report').data
    assert b'[ SYSTEM REPORT ]' in page and b'PERFECT DAYS' in page and b'2.5' in page
    this_week = league.week_start_for().isoformat()
    page = auth_client.get(f'/report/{this_week}').data
    assert b'still in progress' in page and b'Next week' not in page
    old = (league.week_start_for() - timedelta(days=70)).isoformat()
    assert b'No activity recorded' in auth_client.get(f'/report/{old}').data
    assert b'Unknown week' in auth_client.get('/report/not-a-date', follow_redirects=True).data


def test_monday_report_job_only_notifies_active_players(app):
    active, idle = player('Active'), player('Idle')
    _last_week_activity(active)
    send_weekly_reports_if_due(app, league.week_ends_at(league.week_start_for()) - timedelta(days=7) + timedelta(hours=8))
    notes = Notification.query.all()
    assert [n.player_id for n in notes] == [active.id]
    assert 'WEEKLY SYSTEM REPORT: 1/2 perfect days, 65 pts. League #1.' in notes[0].message


# --- schema upgrade for existing databases ---

def test_add_column_is_idempotent(app):
    from app.schema_upgrades import _add_column
    with db.engine.begin() as conn:
        conn.execute(text('CREATE TABLE legacy_t (id INTEGER PRIMARY KEY)'))
    _add_column('legacy_t', 'metric_target', 'FLOAT')
    _add_column('legacy_t', 'metric_target', 'FLOAT')
    _add_column('missing_table', 'x', 'FLOAT')
    assert 'metric_target' in {c['name'] for c in inspect(db.engine).get_columns('legacy_t')}


def test_current_week_report_matches_dashboard_scores(app):
    p = player()
    effort(p, 'VIT', 3)
    r = kpi.weekly_report(p, league.week_start_for())
    assert r['is_current']
    assert {a['code']: a['end'] for a in r['areas']} == kpi.area_scores(p)
