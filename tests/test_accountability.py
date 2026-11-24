"""Soft penalties (XP debt), opt-in Hardcore, streak freezes, Gold halving, personal rewards, B/A scaling."""
from datetime import timedelta

from app import league
from app import services as S
from app.extensions import db
from app.models import ActivityEvent, PersonalReward, Player, PurchaseLog, Quest

from .utils import one_reset_ago


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def me():
    db.session.expire_all()
    return Player.query.filter_by(name='AuthUser').first()


# --- XP debt ---

def test_new_xp_pays_debt_first(app):
    p = player(xp=100, xp_debt=250)
    assert S.add_xp(p, 200) == (0, 200)
    assert (p.xp, p.xp_debt) == (100, 50)
    assert S.add_xp(p, 80) == (30, 50)
    assert (p.xp, p.xp_debt) == (130, 0)


def test_debt_is_capped_at_one_level(app):
    p = player(xp_required=1000)
    assert S.apply_xp_debt(p) == 500
    assert S.apply_xp_debt(p) == 1000
    assert S.apply_xp_debt(p) == 1000


def test_completion_and_focus_report_debt(auth_client, app, csrf_token):
    p = me(); p.xp_debt = 100; db.session.commit()
    q = Quest(title='Pay', rank='C', player=p); db.session.add(q); db.session.commit()
    page = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'100 XP to debt (DEBT CLEARED)' in page
    assert me().xp_debt == 0 and me().xp == 50  # 150 - 100

    p = me(); p.xp_debt = 1000; db.session.commit()
    r = auth_client.post('/focus_complete', json={'minutes': 30}, headers={'X-CSRFToken': csrf_token}).get_json()
    assert '(300 XP paid off debt)' in r['msg'] and me().xp_debt == 700


def test_debt_shown_on_dashboard(auth_client, app):
    p = me(); p.xp_debt = 1234; db.session.commit()
    assert b'DEBT 1,234 XP' in auth_client.get('/').data


# --- Hardcore ---

def test_hardcore_toggle(auth_client, app, csrf_token):
    page = auth_client.post('/settings/hardcore', data={'enable': '1', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'HARDCORE MODE ENGAGED' in page
    p = me()
    assert p.hardcore and p.hardcore_since is not None
    assert b'#i-skull"></use></svg> HARDCORE' in auth_client.get('/').data
    assert b'aria-label="Hardcore"' in auth_client.get('/leaderboard').data
    assert b'Hardcore mode is already active' in auth_client.post(
        '/settings/hardcore', data={'enable': '1', 'csrf_token': csrf_token}, follow_redirects=True).data

    auth_client.post('/settings/hardcore', data={'enable': '0', 'csrf_token': csrf_token})
    p = me()
    assert not p.hardcore and p.hardcore_since is None


def test_cannot_enter_hardcore_during_penalty(app):
    p = player(in_penalty_zone=True)
    ok, msg = S.set_hardcore(p, True)
    assert not ok and 'Penalty Zone' in msg and not p.hardcore


def test_hardcore_xp_bonus_does_not_change_league_points(app):
    normal, hc = player('Normal', xp_required=10_000), player('HC', xp_required=10_000, hardcore=True)
    for p in (normal, hc):
        db.session.add(Quest(title=f'Q-{p.name}', rank='C', player=p))
    db.session.commit()
    xp_n, *_ = S.process_quest_completion(normal, Quest.query.filter_by(title='Q-Normal').one())
    xp_h, *_ = S.process_quest_completion(hc, Quest.query.filter_by(title='Q-HC').one())
    assert xp_h == int(xp_n * 1.10)
    week = league.week_start_for()
    assert league.weekly_points(normal.id, week) == league.weekly_points(hc.id, week) == 15.0


# --- streak freezes ---

def _day(p, done):
    db.session.add(Quest(title='Daily', is_daily=True, is_completed=done, player=p))
    p.last_daily_reset = one_reset_ago()
    db.session.commit()
    return S.check_daily_reset(p)


def test_freeze_earned_every_seven_days_max_two(app):
    p = player(current_streak=6, highest_streak=6)
    _, msgs = _day(p, done=True)
    assert p.current_streak == 7 and p.streak_freezes == 1 and any('FREEZE EARNED' in m for m in msgs)

    p.current_streak, p.streak_freezes = 13, 2
    Quest.query.delete(); db.session.commit()
    _day(p, done=True)
    assert p.current_streak == 14 and p.streak_freezes == 2  # bank is full


def test_freeze_protects_a_missed_day(app):
    p = player(current_streak=9, highest_streak=9, streak_freezes=1)
    _, msgs = _day(p, done=False)
    assert any('STREAK FREEZE USED' in m for m in msgs)
    assert (p.current_streak, p.streak_freezes) == (9, 0)
    assert p.consecutive_missed_days == 0 and not p.has_debuff and p.penalties_count == 0
    # The day is still honestly recorded as missed for completion-rate stats
    assert ActivityEvent.query.filter_by(kind='daily_result').one().success is False


def test_without_freezes_a_miss_breaks_the_streak(app):
    p = player(current_streak=9, highest_streak=9)
    _day(p, done=False)
    assert p.current_streak == 0 and p.consecutive_missed_days == 1 and p.has_debuff


def test_dashboard_shows_streak_and_freezes(auth_client, app):
    p = me(); p.current_streak = 8; p.streak_freezes = 1; db.session.commit()
    page = auth_client.get('/').data.decode()
    assert '#i-flame"></use></svg> 8 days' in page and '#i-snowflake"></use></svg> 1' in page


# --- personal rewards & Gold ---

def test_personal_reward_lifecycle(auth_client, app, csrf_token):
    for bad in ({'name': '', 'cost': '10'}, {'name': 'Free', 'cost': '0'}, {'name': 'X', 'cost': 'lots'}):
        page = auth_client.post('/rewards/add', data={**bad, 'csrf_token': csrf_token}, follow_redirects=True).data
        assert b'Give your reward a name' in page
    auth_client.post('/rewards/add', data={'name': 'Cinema night', 'cost': '400', 'csrf_token': csrf_token})
    reward = PersonalReward.query.one()
    assert (reward.name, reward.cost) == ('Cinema night', 400)

    page = auth_client.get('/shop').data
    assert b'MY REWARDS' in page and b'NEED 300 MORE G' in page  # AuthUser has 100 G

    page = auth_client.post(f'/rewards/{reward.id}/buy', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Not enough Gold' in page and me().gold == 100

    p = me(); p.gold = 1000; db.session.commit()
    page = auth_client.post(f'/rewards/{reward.id}/buy', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'REWARD UNLOCKED: Cinema night' in page and me().gold == 600
    log = PurchaseLog.query.one()
    assert not log.is_claimed and b'READY TO ENJOY' in auth_client.get('/shop').data

    r = auth_client.post(f'/claim_purchase/{log.id}', data={'csrf_token': csrf_token}, headers={'Referer': '/shop'})
    assert r.headers['Location'].endswith('/shop')
    db.session.expire_all()
    assert PurchaseLog.query.one().is_claimed

    auth_client.post(f'/rewards/{reward.id}/delete', data={'csrf_token': csrf_token})
    assert PersonalReward.query.count() == 0


def test_rewards_are_private(auth_client, app, csrf_token):
    other = player('Other', gold=5000)
    theirs = PersonalReward(player_id=other.id, name='Theirs', cost=10)
    db.session.add(theirs); db.session.commit()
    page = auth_client.post(f'/rewards/{theirs.id}/buy', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Reward not found' in page
    auth_client.post(f'/rewards/{theirs.id}/delete', data={'csrf_token': csrf_token})
    assert PersonalReward.query.count() == 1
    assert b'Theirs' not in auth_client.get('/shop').data


def test_reward_limit(auth_client, app, csrf_token):
    p = me()
    db.session.add_all([PersonalReward(player_id=p.id, name=f'R{i}', cost=1) for i in range(30)])
    db.session.commit()
    page = auth_client.post('/rewards/add', data={'name': 'One more', 'cost': '5', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'up to 30 personal rewards' in page


# --- B/A quests stay relevant ---

def test_high_level_a_rank_scales_but_league_uses_fixed_xp(app):
    p = player(level=50, xp_required=S.calculate_xp_required(50))
    q = Quest(title='Big project', rank='A', player=p); db.session.add(q); db.session.commit()
    xp, gold, coins, *_ = S.process_quest_completion(p, q)
    assert xp == int(2170 * 1.005)                 # 15% of 14,450 (rounded to 10), +0.5% INT
    assert (gold, coins) == (100, 30)
    assert league.weekly_points(p.id, league.week_start_for()) == 60.0   # fixed 600 XP / 10


def test_daily_a_rank_does_not_scale(app):
    p = player(level=50, xp_required=S.calculate_xp_required(50))
    q = Quest(title='Daily A', rank='A', is_daily=True, player=p); db.session.add(q); db.session.commit()
    xp, *_ = S.process_quest_completion(p, q)
    assert xp == int(600 * 1.005)
