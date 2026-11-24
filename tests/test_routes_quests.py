"""Quest lifecycle routes: add (AI), edit, abandon, breakdown, calendar, verification page."""
from datetime import datetime
from unittest.mock import patch

from app.extensions import db
from app.models import Player, Quest, QuestComment
from app.routes.main import parse_datetime_input


def me():
    db.session.expire_all()
    return Player.query.filter_by(name="AuthUser").first()


def make_quest(**kw):
    q = Quest(player=me(), **{'title': 'Quest', 'rank': 'E', **kw})
    db.session.add(q)
    db.session.commit()
    return q.id


# --- helpers ---

def test_parse_datetime_input_formats():
    assert parse_datetime_input('2026-10-25T14:30') == datetime(2026, 10, 25, 14, 30)
    assert parse_datetime_input('2026-10-25') == datetime(2026, 10, 25)
    assert parse_datetime_input('not a date') is None
    assert parse_datetime_input('') is None


# --- add quest ---

def test_add_quest_auto_rank_uses_normalized_ai_output(auth_client, app, csrf_token):
    with patch('app.ai_guardian.TheArchitect.analyze_quest', return_value={'rank': 'b', 'stat': 'SEN', 'xp': 999}):
        page = auth_client.post('/add_quest', data={'title': 'Meditate daily', 'rank': 'Auto',
                                                     'csrf_token': csrf_token}, follow_redirects=True).data
    q = Quest.query.filter_by(title='Meditate daily').first()
    assert (q.rank, q.stat_reward, q.xp_reward) == ('B', 'SNS', 0)
    assert b'System Analysis: Rank B | Stat SNS' in page


def test_add_quest_with_dates_priority_and_daily(auth_client, app, csrf_token):
    auth_client.post('/add_quest', data={'title': 'Dated', 'rank': 'zz', 'stat': 'agi', 'priority': '9',
                                         'start_date': '2026-12-01T09:00', 'due_date': '2026-12-02',
                                         'is_daily': 'on', 'csrf_token': csrf_token})
    q = Quest.query.filter_by(title='Dated').first()
    assert q.rank == 'E'  # invalid rank falls back
    assert q.stat_reward == 'AGI'
    assert q.priority == 4  # clamped to 1-4
    assert q.is_daily
    assert q.start_date == datetime(2026, 12, 1, 9, 0) and q.due_date == datetime(2026, 12, 2)


# --- verify / complete ---

def test_complete_get_shows_oath_page(auth_client, app):
    qid = make_quest(title='Swear Me')
    page = auth_client.get(f'/complete/{qid}').data
    assert b'VERIFY COMPLETION' in page and b'Swear Me' in page


def test_complete_missing_quest_redirects(auth_client):
    assert auth_client.get('/complete/9999').status_code == 302


# --- edit quest ---

def test_edit_normal_quest_updates_fields_comment_and_progress(auth_client, app, csrf_token):
    qid = make_quest(title='Old', rank='E', stat_reward='INT', xp_reward=500)
    page = auth_client.get(f'/edit_quest/{qid}').data
    assert b'EDIT QUEST' in page

    auth_client.post(f'/edit_quest/{qid}', data={
        'title': 'New', 'description': 'Details', 'rank': 'a', 'stat': 'SEN', 'priority': '1',
        'start_date': '2026-12-01T10:00', 'due_date': '2026-12-05', 'progress': '60',
        'new_comment': '  progress note  ', 'is_daily': 'on', 'csrf_token': csrf_token})
    q = db.session.get(Quest, qid)
    db.session.refresh(q)
    assert (q.title, q.description, q.rank, q.stat_reward, q.priority, q.progress) == ('New', 'Details', 'A', 'SNS', 1, 60)
    assert q.is_daily and q.xp_reward == 0
    assert q.due_date == datetime(2026, 12, 5)
    assert QuestComment.query.filter_by(quest_id=qid).one().content == 'progress note'


def test_edit_daily_core_fields_requires_coins(auth_client, app, csrf_token):
    qid = make_quest(title='Daily', is_daily=True, stat_reward='STR', priority=4)
    page = auth_client.post(f'/edit_quest/{qid}', data={'title': 'Renamed', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'requires 250 Coins' in page
    assert db.session.get(Quest, qid).title == 'Daily'


def test_edit_daily_core_fields_with_coins(auth_client, app, csrf_token):
    p = me(); p.coins = 300; db.session.commit()
    qid = make_quest(title='Daily', is_daily=True, stat_reward='STR', priority=4)
    auth_client.post(f'/edit_quest/{qid}', data={'title': 'Renamed', 'csrf_token': csrf_token})
    db.session.expire_all()
    assert db.session.get(Quest, qid).title == 'Renamed'
    assert me().coins == 50


def test_edit_daily_description_only_is_free(auth_client, app, csrf_token):
    qid = make_quest(title='Daily', is_daily=True, stat_reward='STR', priority=4)
    auth_client.post(f'/edit_quest/{qid}', data={'description': 'just notes', 'csrf_token': csrf_token})
    db.session.expire_all()
    assert db.session.get(Quest, qid).description == 'just notes'
    assert me().coins == 0


def test_edit_other_players_quest_blocked(auth_client, app, csrf_token):
    other = Player(name='Other'); db.session.add(other); db.session.commit()
    q = Quest(title='Theirs', player=other); db.session.add(q); db.session.commit()
    auth_client.post(f'/edit_quest/{q.id}', data={'title': 'Hacked', 'csrf_token': csrf_token})
    db.session.expire_all()
    assert db.session.get(Quest, q.id).title == 'Theirs'
    assert auth_client.get('/edit_quest/9999').status_code == 302


# --- abandon quest ---

def test_abandon_normal_quest_is_free(auth_client, app, csrf_token):
    qid = make_quest()
    auth_client.post(f'/delete_quest/{qid}', data={'csrf_token': csrf_token})
    assert db.session.get(Quest, qid) is None


def test_abandon_daily_costs_500_coins(auth_client, app, csrf_token):
    p = me(); p.coins = 600; db.session.commit()
    qid = make_quest(is_daily=True)
    auth_client.post(f'/delete_quest/{qid}', data={'csrf_token': csrf_token})
    db.session.expire_all()
    assert db.session.get(Quest, qid) is None
    assert me().coins == 100


def test_abandon_daily_without_coins_is_refused(auth_client, app, csrf_token):
    qid = make_quest(is_daily=True)
    page = auth_client.get(f'/delete_quest/{qid}', follow_redirects=True).data
    assert b'INSUFFICIENT FUNDS' in page
    page = auth_client.post(f'/delete_quest/{qid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Insufficient Coins' in page
    assert db.session.get(Quest, qid) is not None


def test_abandon_other_players_quest_blocked(auth_client, app, csrf_token):
    other = Player(name='Other2'); db.session.add(other); db.session.commit()
    q = Quest(title='Theirs', player=other); db.session.add(q); db.session.commit()
    auth_client.post(f'/delete_quest/{q.id}', data={'csrf_token': csrf_token})
    assert db.session.get(Quest, q.id) is not None


# --- architect breakdown ---

def test_breakdown_confirmation_page(auth_client, app):
    qid = make_quest(title='Big Project')
    assert b'ARCHITECT INTERFACE' in auth_client.get(f'/architect/breakdown/{qid}').data


def test_breakdown_creates_normalized_subquests(auth_client, app, csrf_token):
    qid = make_quest(title='Big Project', stat_reward='SEN')
    steps = ['Plain string step', {'step': 'Draft plan', 'rank': 'x', 'priority': 9}, {'step': 'Ship', 'rank': 'b', 'priority': 1}]
    with patch('app.ai_guardian.TheArchitect.decompose_task', return_value=steps):
        page = auth_client.post(f'/architect/breakdown/{qid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Decomposition Complete: 3 sub-quests created' in page
    draft = Quest.query.filter_by(title='Draft plan').one()
    ship = Quest.query.filter_by(title='Ship').one()
    assert (draft.rank, draft.priority, draft.stat_reward, draft.xp_reward) == ('E', 4, 'SNS', 0)
    assert (ship.rank, ship.priority) == ('B', 1)
    assert Quest.query.filter_by(title='Plain string step').one().rank == 'E'


def test_breakdown_handles_ai_failure_and_empty_result(auth_client, app, csrf_token):
    qid = make_quest(title='Big Project')
    with patch('app.ai_guardian.TheArchitect.decompose_task', side_effect=RuntimeError('boom')):
        page = auth_client.post(f'/architect/breakdown/{qid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'critical error' in page
    with patch('app.ai_guardian.TheArchitect.decompose_task', return_value=[]):
        page = auth_client.post(f'/architect/breakdown/{qid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'could not decompose' in page
    assert Quest.query.count() == 1


def test_breakdown_of_other_players_quest_blocked(auth_client, app):
    other = Player(name='Other3'); db.session.add(other); db.session.commit()
    q = Quest(title='Theirs', player=other); db.session.add(q); db.session.commit()
    page = auth_client.get(f'/architect/breakdown/{q.id}', follow_redirects=True).data
    assert b'access denied' in page


# --- calendar ---

def test_calendar_shows_quests_due_this_month(auth_client, app):
    now = datetime.now()
    make_quest(title='Calendar Item', rank='A', due_date=datetime(now.year, now.month, 15, 9, 30))
    make_quest(title='Minor Item', rank='E', due_date=datetime(now.year, now.month, 16, 10, 0))
    page = auth_client.get('/calendar').data
    assert b'Calendar Item' in page and b'Minor Item' in page
    assert b'cal-quest cal-quest-major' in page  # B+ ranks get the highlighted border


def test_calendar_month_navigation_wraps(auth_client):
    assert b'January' in auth_client.get('/calendar/2026/13').data
    assert b'December' in auth_client.get('/calendar/2026/0').data


# --- completion popups ---

def test_completion_popups_for_evolution_rank_up_title_and_penalty(auth_client, app, csrf_token):
    from app.services import seed_titles
    seed_titles()
    p = me()
    p.job_class, p.level, p.xp, p.xp_required = 'Tank', 19, 0, 100
    p.strength = p.intelligence = p.agility = p.vitality = p.sense = 30
    p.in_penalty_zone = True
    db.session.commit()
    qid = make_quest(title='PENALTY: Survive', rank='S', is_penalty=True)
    boss = make_quest(title='Boss', rank='S')

    page = auth_client.post(f'/complete/{qid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'PENALTY CLEARED' in page

    page = auth_client.post(f'/complete/{boss}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'CLASS EVOLVED: You are now a Juggernaut!' in page
    assert b'RANK UP: You have reached' in page
    assert b'TITLE UNLOCKED: The Awakened' in page  # first title shown on completion, not a later dashboard visit


def test_dashboard_weekly_reset_popup(auth_client, app):
    from datetime import timedelta, timezone as tz
    p = me(); p.gold = 300; p.last_weekly_reset = datetime.now(tz.utc) - timedelta(days=8); db.session.commit()
    page = auth_client.get('/').data
    assert 'WEEKLY RESET: Gold halved (300 → 150 G).'.encode() in page
    assert me().gold == 150
