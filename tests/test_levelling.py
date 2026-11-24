"""Rebalanced levelling: gentle curve, fixed rewards, per-daily XP, focus pay, migration of old progress."""
from app.extensions import db
from app.models import Player, Quest
from app.schema_upgrades import run_schema_upgrades
from app import services as S


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def test_new_players_start_on_the_new_curve(client, app, csrf_token):
    assert player('Default').xp_required == 160
    client.post('/register', data={'username': 'Fresh', 'password': 'pw', 'confirm': 'pw', 'csrf_token': csrf_token})
    assert Player.query.filter_by(name='Fresh').one().xp_required == S.calculate_xp_required(1)


def test_migration_keeps_level_and_percent_progress(app):
    old_lv15 = player('Mid', level=15, xp=909, xp_required=2273)        # 40% through Lv 15 on the old curve
    old_lv50 = player('High', level=50, xp=5_000_000, xp_required=5_600_000)
    run_schema_upgrades()
    db.session.expire_all()
    mid, high = db.session.get(Player, old_lv15.id), db.session.get(Player, old_lv50.id)
    assert (mid.level, mid.xp_required, mid.xp) == (15, 2760, int(909 / 2273 * 2760))
    assert (high.level, high.xp_required) == (50, 14450) and high.xp < high.xp_required
    before = (mid.xp, high.xp)
    run_schema_upgrades()  # idempotent
    db.session.expire_all()
    assert (db.session.get(Player, mid.id).xp, db.session.get(Player, high.id).xp) == before


def test_each_daily_earns_rank_xp_but_no_gold(app):
    p = player(xp_required=10_000)
    d1 = Quest(title='Gym', rank='D', is_daily=True, player=p)
    d2 = Quest(title='Read', rank='E', is_daily=True, player=p)
    db.session.add_all([d1, d2]); db.session.commit()

    xp, gold, coins, _, bonus, _ = S.process_quest_completion(p, d1)
    assert (xp, gold, coins, bonus) == (80, 0, 0, False)  # partial day still pays
    xp, gold, coins, _, bonus, _ = S.process_quest_completion(p, d2)
    assert (xp, bonus) == (40, True)
    assert p.xp == 80 + 40 + S.DAILY_BONUS_XP
    assert (p.gold, p.coins, p.attribute_points) == (100, 50, 3)


def test_daily_s_rank_is_xp_not_an_instant_level(app):
    p = player(xp_required=10_000)
    q = Quest(title='Daily S', rank='S', is_daily=True, player=p); db.session.add(q); db.session.commit()
    xp, *_ = S.process_quest_completion(p, q)
    assert xp == int(S.RANK_XP['S'] * (1 + 1 / 10 * 0.05)) and p.level == 1  # 1 INT = +0.5%


def test_focus_hour_beats_the_daily_bonus(auth_client, app, csrf_token):
    assert 60 * S.FOCUS_XP_PER_MINUTE > S.DAILY_BONUS_XP
    # ~5-8% of a mid-game level per hour
    assert 0.05 <= 60 * S.FOCUS_XP_PER_MINUTE / S.calculate_xp_required(35) <= 0.08


def test_two_year_pacing_for_an_active_player():
    """A typical active day is ~2,000 XP; reaching Lv 100 should take roughly 1.5-2.5 years."""
    day = 4 * S.RANK_XP['E'] + S.DAILY_BONUS_XP + 90 * S.FOCUS_XP_PER_MINUTE + S.RANK_XP['C'] + S.RANK_XP['B']
    total = sum(S.calculate_xp_required(level) for level in range(1, 100))
    assert 1900 <= day <= 2100
    assert 1.5 <= total / day / 365 <= 2.5
