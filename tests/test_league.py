from .utils import one_reset_ago
"""Weekly leagues, A/S rank caps + Architect review, rivals, overtake alerts and weekly results."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app import league
from app.extensions import db
from app.models import ActivityEvent, Notification, Player, Quest, Rivalry
from app.services import GAME_TIMEZONE, process_quest_completion, check_daily_reset


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def me():
    db.session.expire_all()
    return Player.query.filter_by(name='AuthUser').first()


def madrid(*args):
    return GAME_TIMEZONE.localize(datetime(*args)).astimezone(timezone.utc)


def add_points(p, pts, week=None, kind='quest', minutes=0):
    db.session.add(ActivityEvent(player_id=p.id, kind=kind, points=pts, minutes=minutes,
                                 week_start=week or league.week_start_for()))
    db.session.commit()


# --- weeks ---

def test_week_boundary_is_monday_1am_madrid():
    # Monday 23 Nov 2026
    assert league.week_start_for(madrid(2026, 11, 23, 0, 30)) == date(2026, 11, 16)  # still last week
    assert league.week_start_for(madrid(2026, 11, 23, 1, 5)) == date(2026, 11, 23)
    assert league.week_start_for(madrid(2026, 11, 29, 23, 59)) == date(2026, 11, 23)
    assert league.week_ends_at(date(2026, 11, 23)) == madrid(2026, 11, 30, 1, 0)
    assert league.week_start_for(datetime(2026, 11, 25, 12, 0)) == date(2026, 11, 23)  # naive = UTC


# --- points ---

def test_quest_points_are_base_xp_over_ten(app):
    """Personal XP bonuses (here 50 INT = +25%) don't inflate league points."""
    p = player(xp_required=10_000, intelligence=50)
    q = Quest(title='Q', rank='C', player=p); db.session.add(q); db.session.commit()
    xp_gain, *_ = process_quest_completion(p, q)
    assert xp_gain == 187  # 150 * 1.25
    assert league.weekly_points(p.id, league.week_start_for()) == 15.0


def test_s_rank_counts_as_fixed_points(app):
    for name, level in (('Low', 3), ('High', 60)):
        p = player(name, level=level, xp=10, xp_required=100 + level * 1000)
        q = Quest(title='Boss', rank='S', player=p); db.session.add(q); db.session.commit()
        process_quest_completion(p, q)
        assert league.weekly_points(p.id, league.week_start_for()) == 100.0
        assert p.level == level + 1


def test_daily_points_and_penalty_quests_score_nothing(app):
    p = player()
    d = Quest(title='D', rank='E', is_daily=True, player=p)
    pen = Quest(title='PENALTY', rank='A', is_penalty=True, player=p)
    db.session.add_all([d, pen]); db.session.commit()
    process_quest_completion(p, pen)
    assert league.weekly_points(p.id, league.week_start_for()) == 0
    process_quest_completion(p, d)
    assert league.weekly_points(p.id, league.week_start_for()) == 54.0  # daily 40 XP + bonus 500 XP


def test_focus_points_and_hours(auth_client, app, csrf_token):
    p = me(); p.xp_required = 1000; db.session.commit()
    auth_client.post('/focus_complete', json={'minutes': 90}, headers={'X-CSRFToken': csrf_token})
    row = next(r for r in league.standings() if r['player'].name == 'AuthUser')
    assert row['focus_hours'] == 1.5 and row['points'] == 90.0  # 900 base XP


def test_daily_results_feed_completion_rate(app):
    p = player(last_daily_reset=one_reset_ago())
    db.session.add(Quest(title='D', is_daily=True, is_completed=True, player=p)); db.session.commit()
    check_daily_reset(p)
    results = ActivityEvent.query.filter_by(player_id=p.id, kind='daily_result').all()
    assert len(results) == 1 and results[0].success


def test_standings_order_and_tiebreaks(app):
    a, b, c = player('Alpha'), player('Bravo'), player('Charlie')
    add_points(a, 30); add_points(b, 50); add_points(c, 30, kind='focus', minutes=120)
    rows = league.standings()
    assert [r['player'].name for r in rows] == ['Bravo', 'Charlie', 'Alpha']  # Charlie wins tie on focus
    assert [r['position'] for r in rows] == [1, 2, 3]
    assert all(r['player'].setup_complete for r in rows)


def test_daily_rate_counts_today_when_complete(app):
    p = player()
    week = league.week_start_for()
    db.session.add_all([
        ActivityEvent(player_id=p.id, kind='daily_result', success=True, week_start=week),
        ActivityEvent(player_id=p.id, kind='daily_result', success=False, week_start=week),
        Quest(title='D', is_daily=True, is_completed=True, player=p),
    ])
    db.session.commit()
    assert league.standings()[0]['daily_rate'] == 67  # 2 of 3 days


# --- overtake alerts ---

def test_overtake_notifies_once_per_week(app):
    leader, chaser = player('Leader'), player('Chaser')
    add_points(leader, 20)
    league.record_points(chaser, 'quest', 300)  # 0 -> 30 pts
    note = Notification.query.filter_by(player_id=leader.id).one()
    assert 'Chaser just overtook you' in note.message and note.category == 'warning'

    add_points(leader, 20)  # leader back ahead (40)
    league.record_points(chaser, 'quest', 200)  # 30 -> 50, passes again
    assert Notification.query.filter_by(player_id=leader.id).count() == 1
    assert Notification.query.filter_by(player_id=chaser.id).count() == 0


def test_no_overtake_alert_for_players_without_points(app):
    player('Idle')
    chaser = player('Chaser')
    league.record_points(chaser, 'quest', 100)
    assert Notification.query.count() == 0


# --- rank caps ---

def _add(client, token, title, rank, **extra):
    return client.post('/add_quest', data={'title': title, 'rank': rank, 'csrf_token': token, **extra},
                       follow_redirects=True).data


def test_weekly_s_and_a_caps(auth_client, app, csrf_token):
    _add(auth_client, csrf_token, 'Big One', 'S')
    page = _add(auth_client, csrf_token, 'Big Two', 'S')
    assert b'Weekly Rank S limit reached' in page
    assert Quest.query.filter_by(title='Big One').one().rank == 'S'
    assert Quest.query.filter_by(title='Big Two').one().rank == 'A'  # fell to the next free slot

    for i in range(3):
        _add(auth_client, csrf_token, f'Hard {i}', 'A')
    ranks = [q.rank for q in Quest.query.filter(Quest.title.like('Hard%')).order_by(Quest.id)]
    assert ranks == ['A', 'A', 'B']  # 'Big Two' already used one A slot
    assert league.rank_slots_left(me()) == {'S': 0, 'A': 0}


def test_dailies_are_exempt_and_deleting_does_not_refund(auth_client, app, csrf_token):
    _add(auth_client, csrf_token, 'Daily S', 'S', is_daily='on')
    assert Quest.query.filter_by(title='Daily S').one().rank == 'S'
    assert league.rank_slots_left(me())['S'] == 1

    _add(auth_client, csrf_token, 'Temp', 'S')
    qid = Quest.query.filter_by(title='Temp').one().id
    auth_client.post(f'/delete_quest/{qid}', data={'csrf_token': csrf_token})
    _add(auth_client, csrf_token, 'Again', 'S')
    assert Quest.query.filter_by(title='Again').one().rank == 'A'


def test_edit_promotion_uses_a_slot(auth_client, app, csrf_token):
    _add(auth_client, csrf_token, 'Grows', 'C')
    qid = Quest.query.filter_by(title='Grows').one().id
    auth_client.post(f'/edit_quest/{qid}', data={'rank': 'S', 'csrf_token': csrf_token})
    assert db.session.get(Quest, qid).rank == 'S'
    # Saving again without changing the rank doesn't use another slot
    auth_client.post(f'/edit_quest/{qid}', data={'rank': 'S', 'title': 'Grows!', 'csrf_token': csrf_token})
    assert league.rank_slots_used(me())['S'] == 1
    _add(auth_client, csrf_token, 'Other', 'C')
    other = Quest.query.filter_by(title='Other').one().id
    page = auth_client.post(f'/edit_quest/{other}', data={'rank': 'S', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'limit reached' in page and db.session.get(Quest, other).rank == 'A'


def test_breakdown_subquests_respect_caps(auth_client, app, csrf_token):
    _add(auth_client, csrf_token, 'Epic', 'C')
    qid = Quest.query.filter_by(title='Epic').one().id
    steps = [{'step': f'Step {i}', 'rank': 'S', 'priority': 2} for i in range(3)]
    with patch('app.ai_guardian.TheArchitect.decompose_task', return_value=steps):
        page = auth_client.post(f'/architect/breakdown/{qid}', data={'csrf_token': csrf_token},
                                follow_redirects=True).data
    ranks = [q.rank for q in Quest.query.filter(Quest.title.like('Step%')).order_by(Quest.id)]
    assert ranks == ['S', 'A', 'A'] and b'limit reached' in page


def test_slot_counts_shown_in_new_quest_form(auth_client, app, csrf_token):
    _add(auth_client, csrf_token, 'S one', 'S')
    page = auth_client.get('/').data
    assert b'Rank S (Life Changing) \xc2\xb7 0 left this week' in page
    assert b'Rank A (Critical) \xc2\xb7 3 left this week' in page


# --- Architect review ---

def test_architect_can_lower_but_not_raise_manual_ranks(auth_client, app, csrf_token):
    with patch('app.ai_guardian.TheArchitect.assess_rank', return_value='B') as assess:
        page = _add(auth_client, csrf_token, 'Tie shoelaces', 'S')
    assess.assert_called_once_with('Tie shoelaces')
    assert Quest.query.filter_by(title='Tie shoelaces').one().rank == 'B'
    assert b'The Architect assessed' in page
    assert league.rank_slots_left(me())['S'] == 1  # no slot used for the downgraded quest

    with patch('app.ai_guardian.TheArchitect.assess_rank', return_value='S'):
        _add(auth_client, csrf_token, 'Run a marathon', 'A')
    assert Quest.query.filter_by(title='Run a marathon').one().rank == 'A'


def test_review_skipped_when_unavailable_disabled_or_not_needed(auth_client, app, csrf_token, monkeypatch):
    with patch('app.ai_guardian.TheArchitect.assess_rank', return_value=None):
        _add(auth_client, csrf_token, 'Offline', 'S')
    assert Quest.query.filter_by(title='Offline').one().rank == 'S'  # player's word stands

    with patch('app.ai_guardian.TheArchitect.assess_rank') as assess:
        _add(auth_client, csrf_token, 'Low', 'C')  # only A/S are reviewed
        monkeypatch.setenv('ARCHITECT_RANK_REVIEW', '0')
        _add(auth_client, csrf_token, 'Switched off', 'A')
        with patch('app.ai_guardian.TheArchitect.analyze_quest', return_value={'rank': 'A', 'stat': 'INT'}):
            monkeypatch.delenv('ARCHITECT_RANK_REVIEW')
            _add(auth_client, csrf_token, 'Auto ranked', 'Auto')  # AI already chose it
        assert not assess.called


def test_assess_rank_parses_model_output():
    from app.ai_guardian import TheArchitect
    with patch.object(TheArchitect, '_call_llm', return_value={'rank': ' b '}):
        assert TheArchitect.assess_rank('x') == 'B'
    for bad in (None, {'rank': 'Z'}, {'nope': 1}, ['B']):
        with patch.object(TheArchitect, '_call_llm', return_value=bad):
            assert TheArchitect.assess_rank('x') is None


# --- rivals ---

def test_set_change_and_clear_rival(auth_client, app, csrf_token):
    bro, friend = player('Bro'), player('Friend')
    page = auth_client.post(f'/rival/{bro.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'RIVAL SET: Bro' in page and me().rivalry.rival_id == bro.id
    auth_client.post(f'/rival/{friend.id}', data={'csrf_token': csrf_token})
    assert Rivalry.query.count() == 1 and me().rivalry.rival_id == friend.id

    page = auth_client.post(f'/rival/{me().id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Choose another hunter' in page
    page = auth_client.post('/rival/9999', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Choose another hunter' in page

    auth_client.post('/rival/clear', data={'csrf_token': csrf_token})
    assert me().rivalry is None


def test_duel_summary_and_record(app):
    p, bro = player('Me'), player('Bro')
    week = league.week_start_for()
    db.session.add(Rivalry(player_id=p.id, rival_id=bro.id,
                           created_at=datetime.now(timezone.utc) - timedelta(days=30)))
    db.session.commit()
    for weeks_ago, mine, theirs in ((1, 50, 40), (2, 10, 60), (3, 30, 30), (4, 0, 0)):
        w = week - timedelta(days=7 * weeks_ago)
        if mine: add_points(p, mine, w)
        if theirs: add_points(bro, theirs, w)
    add_points(p, 12); add_points(bro, 20)

    duel = league.rival_summary(p)
    assert duel['rival'].name == 'Bro'
    assert (duel['me']['points'], duel['them']['points'], duel['leading']) == (12, 20, 'them')
    assert duel['record'] == {'wins': 1, 'losses': 1, 'draws': 1}  # empty week ignored
    assert league.rival_summary(bro) is None


def test_dashboard_duel_panel(auth_client, app, csrf_token):
    assert b'No rival yet' in auth_client.get('/').data
    bro = player('Bro')
    auth_client.post(f'/rival/{bro.id}', data={'csrf_token': csrf_token})
    add_points(me(), 25)
    page = auth_client.get('/').data
    assert b'WEEKLY DUEL' in page and b'LEADING' in page and b'Bro' in page


def test_deleting_a_rival_account_removes_the_rivalry(app):
    p, bro = player('Me'), player('Bro')
    db.session.add(Rivalry(player_id=p.id, rival_id=bro.id)); db.session.commit()
    db.session.delete(bro); db.session.commit()
    assert Rivalry.query.count() == 0


# --- leaderboard & weekly results ---

def test_leaderboard_views(auth_client, app):
    bro = player('Bro')
    add_points(bro, 40)
    add_points(bro, 99, week=league.week_start_for() - timedelta(days=7))
    page = auth_client.get('/leaderboard').data
    assert b'THIS WEEK' in page and b'CHALLENGE' in page and b"Last week's champion: <strong>Bro</strong>" in page
    assert page.index(b'Bro') < page.index(b'AuthUser')
    page = auth_client.get('/leaderboard?view=all').data
    assert b'LVL' in page and b'CHALLENGE' not in page


def test_weekly_results_popup_once(auth_client, app):
    bro = player('Bro')
    last = league.week_start_for() - timedelta(days=7)
    add_points(bro, 80, week=last)
    add_points(me(), 50, week=last)
    page = auth_client.get('/').data
    assert b"LAST WEEK&#39;S LEAGUE: You placed #2 of 2 with 50 pts. Winner: Bro (80 pts)." in page
    assert b"LAST WEEK" not in auth_client.get('/').data  # only once per week


@pytest.mark.parametrize('mine, expected', [
    (90, "YOU WON with 90 pts"),
    (0, "Bro won with 80 pts. You didn't score"),
])
def test_weekly_results_messages(app, mine, expected):
    p, bro = player('Me'), player('Bro')
    last = league.week_start_for() - timedelta(days=7)
    add_points(bro, 80, week=last)
    if mine:
        add_points(p, mine, week=last)
    assert expected in league.weekly_results_message(p)


def test_weekly_results_silent_when_nobody_scored(app):
    assert league.weekly_results_message(player()) is None
