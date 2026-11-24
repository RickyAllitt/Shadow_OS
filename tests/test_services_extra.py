from .utils import one_reset_ago
"""Service-layer rules not covered elsewhere: vacation, penalties, push, scheduled jobs, equipment, progression."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from pywebpush import WebPushException

from app.extensions import db
from app.models import (Player, Quest, RewardItem, Inventory, Shadow, Title, PlayerTitle, Notification,
                        PushSubscription)
from app import services as S


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    db.session.add(p)
    db.session.commit()
    return p


def utc(**delta):
    return datetime.now(timezone.utc) + timedelta(**delta)


# --- vacation ---

def test_start_vacation_once_per_month(app):
    p = player()
    ok, msg = S.start_vacation(p, 5)
    assert ok and p.is_on_vacation and p.vacation_count == 1
    assert p.vacation_end_date - p.vacation_start_date == timedelta(days=5)
    ok, msg = S.start_vacation(p, 5)
    assert not ok and 'MONTHLY LIMIT' in msg


def test_end_vacation_stat_decay_and_vitality_mitigation(app):
    p = player(strength=10, intelligence=10, agility=10, sense=10, vitality=1,
               is_on_vacation=True, vacation_start_date=utc(days=-15))
    ok, msg = S.end_vacation(p)
    assert ok and not p.is_on_vacation and p.vacation_end_date is None
    assert p.strength == 9 and 'Stats reduced by 1' in msg  # 2 weeks * (1 - 0.01) -> 1

    tank = player(name='T', vitality=100, is_on_vacation=True, vacation_start_date=utc(days=-15))
    ok, msg = S.end_vacation(tank)
    assert tank.vitality == 100 and 'prevented all stat decay' in msg

    short = player(name='S', strength=5, is_on_vacation=True, vacation_start_date=utc(days=-2))
    ok, msg = S.end_vacation(short)
    assert short.strength == 5 and 'No stat reduction' in msg

    assert S.end_vacation(player(name='N')) == (False, "You are not on vacation.")


def test_daily_reset_paused_then_resumes_after_vacation(app):
    p = player(last_daily_reset=utc(days=-3), is_on_vacation=True,
               vacation_start_date=utc(days=-3), vacation_end_date=utc(days=2))
    assert S.check_daily_reset(p) == (False, [])
    p.vacation_end_date = utc(hours=-1)
    occurred, msgs = S.check_daily_reset(p)
    assert occurred and 'VACATION ENDED' in msgs[0] and not p.is_on_vacation


# --- penalty ladder ---

def test_first_reset_initializes_timestamp(app):
    p = player()
    p.last_daily_reset = None
    assert S.check_daily_reset(p) is False and p.last_daily_reset is not None


def _failed_penalty_player(**kw):
    p = player(level=10, xp=50, xp_required=S.calculate_xp_required(10), consecutive_missed_days=2,
               in_penalty_zone=True, has_debuff=True, strength=10, intelligence=10, agility=10, sense=10,
               vitality=10, last_daily_reset=one_reset_ago(), **kw)
    db.session.add(Quest(title='Daily', is_daily=True, player=p))
    db.session.add(Quest(title='PENALTY: Survive', is_penalty=True, rank='A', player=p,
                         due_date=utc(hours=-2).replace(tzinfo=None)))
    db.session.commit()
    return p


def test_failed_penalty_normal_mode_gives_xp_debt(app):
    p = _failed_penalty_player()
    occurred, msgs = S.check_daily_reset(p)
    assert occurred and any('XP DEBT 800 XP' in m for m in msgs)  # half of 1,610 = 805, rounded to 10
    assert (p.level, p.xp, p.strength, p.xp_debt) == (10, 50, 10, 800)
    assert not p.in_penalty_zone and not p.has_debuff and p.consecutive_missed_days == 0
    assert Quest.query.filter_by(is_penalty=True, is_completed=False).count() == 0


def test_failed_penalty_hardcore_loses_exactly_one_level(app):
    p = _failed_penalty_player(name='HC', hardcore=True)
    occurred, msgs = S.check_daily_reset(p)
    assert any('LEVEL LOST (now Lv 9)' in m for m in msgs)
    assert (p.level, p.xp, p.xp_required, p.strength, p.xp_debt) == (9, 0, S.calculate_xp_required(9), 10, 0)
    assert not p.in_penalty_zone


def test_no_level_down_while_penalty_deadline_pending(app):
    p = player(level=10, consecutive_missed_days=2, last_daily_reset=one_reset_ago())
    db.session.add(Quest(title='Daily', is_daily=True, player=p))
    db.session.add(Quest(title='PENALTY', is_penalty=True, player=p, due_date=utc(hours=5).replace(tzinfo=None)))
    db.session.commit()
    S.check_daily_reset(p)
    assert p.level == 10 and p.in_penalty_zone


def test_tank_gets_one_day_grace(app):
    p = player(job_class='Tank', last_daily_reset=one_reset_ago())
    db.session.add(Quest(title='Daily', is_daily=True, player=p)); db.session.commit()
    S.check_daily_reset(p)
    assert p.consecutive_missed_days == 1 and not p.has_debuff


def test_successful_day_builds_streak(app):
    p = player(current_streak=4, highest_streak=4, last_daily_reset=one_reset_ago())
    db.session.add(Quest(title='Daily', is_daily=True, is_completed=True, progress=50, player=p)); db.session.commit()
    S.check_daily_reset(p)
    q = Quest.query.one()
    assert (p.current_streak, p.highest_streak) == (5, 5)
    assert not q.is_completed and q.progress == 0


def test_long_absence_catch_up_is_capped(app):
    p = player(last_daily_reset=utc(days=-40))
    occurred, msgs = S.check_daily_reset(p)
    assert occurred and any('Hibernation' in m for m in msgs)


def test_weekly_reset_edge_cases(app):
    p = player(gold=500)
    p.last_weekly_reset = None
    assert S.check_weekly_reset(p) is False and p.last_weekly_reset is not None
    p.is_on_vacation = True
    p.last_weekly_reset = utc(days=-30)
    assert S.check_weekly_reset(p) is False and p.gold == 500
    p.is_on_vacation = False
    assert S.check_weekly_reset(p) is True and p.gold == 250  # halved


# --- web push ---

def _sub(p, endpoint='https://push.example/1'):
    s = PushSubscription(player_id=p.id, endpoint=endpoint, p256dh='k', auth='a')
    db.session.add(s); db.session.commit()
    return s


def test_push_requires_key_and_subscriptions(app, monkeypatch):
    p = player()
    monkeypatch.delenv('VAPID_PRIVATE_KEY', raising=False)
    with patch('app.services.webpush') as wp:
        S.trigger_push_notification(p.id, 'T', 'M')
        monkeypatch.setenv('VAPID_PRIVATE_KEY', 'priv')
        S.trigger_push_notification(p.id, 'T', 'M')  # no subscriptions
        assert not wp.called


def test_push_success_sends_payload(app, monkeypatch):
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'priv')
    p = player(); _sub(p)
    with patch('app.services.webpush') as wp:
        S.trigger_push_notification(p.id, 'Title', 'Body', url='/x')
    kwargs = wp.call_args.kwargs
    assert kwargs['subscription_info']['endpoint'] == 'https://push.example/1'
    assert '"title": "Title"' in kwargs['data'] and kwargs['ttl'] == 86400
    assert Notification.query.count() == 0


def test_push_gone_subscription_removed_and_errors_logged(app, monkeypatch):
    monkeypatch.setenv('VAPID_PRIVATE_KEY', 'priv')
    p = player(); _sub(p, 'https://push.example/gone'); _sub(p, 'https://push.example/broken')

    def fake(subscription_info, **kw):
        if subscription_info['endpoint'].endswith('gone'):
            raise WebPushException('gone', response=SimpleNamespace(status_code=410))
        raise RuntimeError('network down')

    with patch('app.services.webpush', side_effect=fake):
        S.trigger_push_notification(p.id, 'T', 'M')
    assert [s.endpoint for s in PushSubscription.query] == ['https://push.example/broken']
    log = Notification.query.one().message
    assert 'Push FAILED [410]' in log and 'network down' in log


# --- scheduled jobs ---

# --- equipment / stats ---

def _gear(name, slot, stat, value):
    i = RewardItem(name=name, cost=1, currency='coins', item_type='equipment', slot=slot, stat_bonus=stat, stat_value=value)
    db.session.add(i); db.session.commit()
    return i


def test_total_stats_with_gear_shadows_and_debuff(app):
    p = player(strength=10, intelligence=10, agility=10, vitality=10, sense=10)
    db.session.add(Inventory(player_id=p.id, item_id=_gear('Blade', 'weapon', 'STR', 5).id, is_equipped=True))
    db.session.add(Inventory(player_id=p.id, item_id=_gear('Hood', 'head', 'SNS', 3).id, is_equipped=False))
    db.session.commit()
    assert S.calculate_total_stats(p)['strength'] == 15 and S.calculate_total_stats(p)['sense'] == 10

    db.session.add(Shadow(player_id=p.id, original_quest_name='Raid')); db.session.commit()
    assert S.calculate_total_stats(p)['strength'] == 15  # int(15 * 1.0101)

    p.has_debuff = True
    assert S.calculate_total_stats(p)['strength'] == 12  # int(15 * 0.81)


def test_equip_service_rejects_other_players_items(app):
    owner, thief = player(name='Owner'), player(name='Thief')
    inv = Inventory(player_id=owner.id, item_id=_gear('Axe', 'weapon', 'STR', 1).id)
    db.session.add(inv); db.session.commit()
    assert S.equip_item_service(thief, inv.id) == (False, 'Item not found.')
    assert S.unequip_item_service(thief, inv.id) == (False, 'Item not found.')


# --- progression ---

def test_class_evolution_chain(app):
    p = player(job_class='Assassin', level=19)
    assert S.check_class_evolution(p) == (False, None)
    p.level = 20
    assert S.check_class_evolution(p) == (True, 'Shadow Assassin')
    p.level = 100
    names = [S.check_class_evolution(p)[1] for _ in range(4)]
    assert names == ['Shadow Lord', 'Nightwalker', 'Eclipse Bringer', 'Monarch of Shadows']
    assert S.check_class_evolution(p) == (False, None)


def test_rank_up_requires_level_and_stats(app):
    p = player(rank='E', level=10, strength=10, intelligence=10, agility=10, vitality=10, sense=9)
    assert S.check_player_rank_up(p) == (False, None)  # 49 total stats
    p.sense = 10
    assert S.check_player_rank_up(p) == (True, 'D')
    p.rank = 'S'
    assert S.check_player_rank_up(p) == (False, None)


def test_level_up_grants_stats_evolves_and_ranks(app):
    p = player(job_class='Mage', level=19, xp=10_000, xp_required=100,
               strength=20, intelligence=20, agility=20, vitality=20, sense=20)
    assert S.process_level_up(p)
    assert p.level > 19 and p.strength > 20
    assert p.job_class == 'Archmage' and p.just_evolved == 'Archmage'
    assert p.rank != 'E'


def test_class_bonuses_on_rewards(app):
    assassin = player(name='A', job_class='Assassin', xp_required=10_000)
    mage = player(name='M', job_class='Mage', xp_required=10_000)
    qa = Quest(title='QA', rank='B', player=assassin)
    qm = Quest(title='QM', rank='B', player=mage)
    db.session.add_all([qa, qm]); db.session.commit()
    _, _, coins_a, *_ = S.process_quest_completion(assassin, qa)
    xp_m, *_ = S.process_quest_completion(mage, qm)
    assert coins_a == int(int(15 * 1.005) * 1.10)
    assert xp_m == int(int(300 * 1.005) * 1.10)


def test_completed_quest_is_not_rewarded_twice(app):
    p = player(xp_required=10_000)
    q = Quest(title='Once', rank='C', player=p, xp_reward=100); db.session.add(q); db.session.commit()
    S.process_quest_completion(p, q)
    xp = p.xp
    assert S.process_quest_completion(p, q) is None and p.xp == xp


def test_titles_unlock_from_stats_and_coins(app):
    S.seed_titles()
    p = player(strength=50, coins=5000)
    unlocked = S.check_title_unlocks(p)
    assert {"Titan's Grip", 'Coin Hoarder'} <= set(unlocked)


def test_title_service_and_shadow_extraction_edge_cases(app):
    p = player()
    assert S.equip_title_service(p, 9999) == (False, 'Title not unlocked.')
    assert S.extract_shadow(p, 9999) == (False, 'Quest not found.')
    q = Quest(title='Not Yet', rank='S', player=p); db.session.add(q); db.session.commit()
    assert S.extract_shadow(p, q.id) == (False, 'Quest must be completed first.')
    q.is_completed = True; db.session.commit()
    assert S.extract_shadow(p, q.id)[0]
    assert S.extract_shadow(p, q.id) == (False, 'Already Arised.')
    weak = Quest(title='Weak', rank='C', player=p, is_completed=True); db.session.add(weak); db.session.commit()
    assert S.extract_shadow(p, weak.id) == (False, 'Only S-Rank feats can be extracted.')


def test_auto_complete_dailies(app):
    p = player(xp_required=10_000)
    assert S.auto_complete_dailies(p) == (0, 'No active daily quests to complete.')
    db.session.add(Quest(title='D', is_daily=True, player=p)); db.session.commit()
    count, _ = S.auto_complete_dailies(p)
    assert count == 1 and Quest.query.one().is_completed


def test_categorized_quests(app):
    p = player()
    db.session.add_all([
        Quest(title='Daily', is_daily=True, player=p),
        Quest(title='Later', player=p, due_date=datetime(2030, 1, 2)),
        Quest(title='Sooner', player=p, due_date=datetime(2030, 1, 1)),
        Quest(title='Penalty', player=p, is_penalty=True, due_date=datetime(2031, 1, 1)),
        Quest(title='Backlog', player=p),
        Quest(title='Hidden', player=p, is_completed=True),
    ])
    db.session.commit()
    dailies, scheduled, backlog = S.get_categorized_quests(p.id)
    assert [q.title for q in dailies] == ['Daily']
    assert [q.title for q in scheduled] == ['Sooner', 'Later', 'Penalty']
    assert [q.title for q in backlog] == ['Backlog']


def test_seed_database_is_idempotent(app):
    S.seed_database()
    items, titles = RewardItem.query.count(), Title.query.count()
    S.seed_database()
    assert RewardItem.query.count() == items > 20
    assert Title.query.count() == titles == len(S.TITLE_DEFINITIONS)
    assert Player.query.count() == 0  # no stray default player


def test_create_notification(app):
    p = player()
    S.create_notification(p.id, 'hello', 'success')
    n = Notification.query.one()
    assert (n.message, n.category, n.is_read) == ('hello', 'success', False)


def test_quest_stat_rewards_scale_with_rank(app):
    p = player(xp_required=10_000, sense=1, intelligence=1)
    for rank, stat in (('B', 'SNS'), ('A', 'SNS'), ('S', 'INT'), ('C', 'INT')):
        db.session.add(Quest(title=rank, rank=rank, stat_reward=stat, player=p))
    db.session.commit()
    for q in Quest.query.order_by(Quest.id):
        S.process_quest_completion(p, q)
    # S-Rank also triggers an instant level up (+1 to every stat)
    assert p.level == 2
    assert p.sense == 1 + 1 + 2 + 1      # B +1, A +2, level up +1
    assert p.intelligence == 1 + 3 + 1   # S +3, C gives no stat, level up +1


def test_flat_stat_title_bonus(app):
    S.seed_titles()
    p = player(strength=10)
    p.current_title = Title.query.filter_by(name='Wolf Slayer').first()  # STR +3
    assert S.calculate_total_stats(p)['strength'] == 13
    assert S.coin_multiplier(p) == 1.0


def test_allocate_nothing_is_rejected(app):
    p = player(attribute_points=3)
    assert S.allocate_attributes(p, {'STR': 0}) == (False, 'No points selected.')
    assert S.allocate_attributes(p, {'SNS': 2, 'AGI': 1})[0] and (p.sense, p.agility) == (3, 2)
