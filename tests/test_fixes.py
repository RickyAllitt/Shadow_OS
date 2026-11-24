"""Regression tests for ownership checks, input validation and stat naming."""
from app.models import Player, Quest
from app.extensions import db
from app.services import normalize_stat, allocate_attributes, _apply_quest_stat_reward, process_quest_completion


def _make_player(name, **kwargs):
    p = Player(name=name, setup_complete=True, **kwargs)
    p.set_password("pass")
    db.session.add(p)
    db.session.commit()
    return p


def test_cannot_complete_other_players_quest(auth_client, app, csrf_token):
    with app.app_context():
        other = _make_player("Victim")
        quest = Quest(title="Not Yours", rank="B", player=other)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id

    assert auth_client.get(f'/complete/{quest_id}').status_code == 302
    auth_client.post(f'/complete/{quest_id}', data={'csrf_token': csrf_token})

    with app.app_context():
        assert not db.session.get(Quest, quest_id).is_completed
        assert Player.query.filter_by(name="AuthUser").first().xp == 0


def test_normalize_stat():
    assert normalize_stat('SEN') == 'SNS'
    assert normalize_stat('sns') == 'SNS'
    assert normalize_stat('STR') == 'STR'
    assert normalize_stat('bogus') == 'INT'
    assert normalize_stat(None, default='STR') == 'STR'


def test_legacy_sen_quest_awards_sense(app):
    with app.app_context():
        p = _make_player("SenseUser")
        before = p.sense
        _apply_quest_stat_reward(p, Quest(title="Meditate", rank="B", stat_reward="SEN"))
        assert p.sense == before + 1


def test_new_quests_use_fixed_rank_xp(auth_client, app, csrf_token):
    """The same B-rank quest is worth the same XP at Lv 1 and Lv 20."""
    for title in ('Low', 'High'):
        # STR reward so the first quest's +1 stat doesn't change the INT XP bonus for the second
        auth_client.post('/add_quest', data={'title': title, 'rank': 'B', 'stat': 'STR', 'csrf_token': csrf_token})
    with app.app_context():
        p = Player.query.filter_by(name="AuthUser").first()
        p.xp_required = 10_000_000  # avoid level-up noise
        low, *_ = process_quest_completion(p, Quest.query.filter_by(title='Low').first())
        p.level = 20
        high, *_ = process_quest_completion(p, Quest.query.filter_by(title='High').first())
        assert low == high == int(300 * 1.005)  # 1 INT => +0.5%


def test_add_quest_requires_title(auth_client, app, csrf_token):
    auth_client.post('/add_quest', data={'title': '  ', 'rank': 'C', 'csrf_token': csrf_token})
    with app.app_context():
        assert Quest.query.count() == 0


def test_negative_attribute_allocation_rejected(app):
    with app.app_context():
        p = _make_player("Exploiter", attribute_points=5)
        before_int = p.intelligence
        ok, _ = allocate_attributes(p, {'STR': -10, 'INT': 15, 'AGI': 0, 'VIT': 0, 'SNS': 0})
        assert not ok
        assert p.intelligence == before_int
        assert p.attribute_points == 5


def test_track_sleep_invalid_input(auth_client, app, csrf_token):
    resp = auth_client.post('/track_sleep', data={'hours': 'abc', 'csrf_token': csrf_token}, follow_redirects=True)
    assert resp.status_code == 200
    resp = auth_client.post('/track_sleep', data={'hours': '99', 'csrf_token': csrf_token}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        p = Player.query.filter_by(name="AuthUser").first()
        assert p.last_sleep_log_date is None


def test_second_sleep_log_does_not_overwrite(auth_client, app, csrf_token):
    auth_client.post('/track_sleep', data={'hours': '8', 'csrf_token': csrf_token})
    auth_client.post('/track_sleep', data={'hours': '3', 'csrf_token': csrf_token})
    with app.app_context():
        assert Player.query.filter_by(name="AuthUser").first().last_sleep_duration == 8.0


def test_daily_bonus_message_matches_rewards(auth_client, app, csrf_token):
    with app.app_context():
        p = Player.query.filter_by(name="AuthUser").first()
        q = Quest(title="Only Daily", rank="E", is_daily=True, player=p)
        db.session.add(q)
        db.session.commit()
        qid = q.id
    resp = auth_client.post(f'/complete/{qid}', data={'csrf_token': csrf_token}, follow_redirects=True)
    assert b"+50 Coins" in resp.data
    assert b"+500 XP" in resp.data   # fixed all-dailies bonus
    assert b"COMPLETE: Only Daily | +40 XP" in resp.data  # each daily now earns its rank XP
