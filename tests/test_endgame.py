"""Gates, Red Gates, loot and sets, Shadow Army grades, Rank Assessments, Second Awakening, Ascension."""
import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from app import gates as G
from app import league, loot, progression as P, shadows
from app import services as S
from app.extensions import db
from app.models import Gate, Inventory, Player, PlayerTitle, Quest, RewardItem, Shadow, Title

from .utils import one_reset_ago


@pytest.fixture(autouse=True)
def _titles(app):
    S.seed_titles()
    db.session.commit()


def player(name='P', level=15, **kw):
    p = Player(name=name, setup_complete=True, level=level, xp_required=S.calculate_xp_required(level), **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def me():
    db.session.expire_all()
    return Player.query.filter_by(name='AuthUser').first()


def earlier(minutes=5):
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def complete_objectives(p, gate):
    """Log activity that satisfies every objective of an entered gate."""
    for o in json.loads(gate.objectives):
        for _ in range(o['target']):
            if o['type'] in ('quests', 'boss'):
                league.record(p, 'effort', rank=o['min_rank']).quest_id = 1
            elif o['type'] == 'focus':
                league.record(p, 'focus', minutes=o['target'])
                break
            elif o['type'] == 'perfect':
                league.record(p, 'daily_result', success=True)
            elif o['type'] == 'sleep':
                league.record(p, 'sleep').value = 8
    db.session.commit()


def entered_gate(p, kind='gate'):
    gate = {'gate': G.ensure_weekly_gate, 'red': lambda q: G.maybe_spawn_red_gate(q)}[kind](p)
    db.session.commit()
    ok, _ = G.enter(p, gate.id, now=earlier())
    assert ok
    return gate


# ---------------------------------------------------------------- weekly gates

def test_weekly_gate_unlocks_at_15_once_per_week(app):
    assert G.ensure_weekly_gate(player('Low', level=14)) is None
    p = player()
    gate = G.ensure_weekly_gate(p)
    db.session.commit()
    objectives = json.loads(gate.objectives)
    assert gate.kind == 'gate' and gate.grade == 'C' and gate.status == 'waiting'
    assert len(objectives) == 3 and objectives[-1] == {'type': 'boss', 'target': 1, 'min_rank': 'B'}
    assert G.ensure_weekly_gate(p) is None
    assert G.ensure_weekly_gate(player('Hi', level=55)).grade == 'A'


def test_gate_progress_comes_from_activity_log(app):
    p = player()
    gate = entered_gate(p)
    assert gate.status == 'active' and all(o['done'] == 0 for o in G.progress(gate))
    # activity before entering never counts; effort without a quest (focus effort) never counts as a quest
    league.record(p, 'effort', rank='S')
    db.session.commit()
    assert G.progress(gate)[-1]['done'] == 0
    complete_objectives(p, gate)
    assert all(o['complete'] for o in G.progress(gate))
    assert G.update_status(gate).startswith('GATE CLEARED')
    assert gate.status == 'cleared'


def test_objective_measurement_rules(app):
    p = player()
    gate = Gate(player_id=p.id, title='T', week_start=league.week_start_for(), status='active',
                entered_at=earlier(60).replace(tzinfo=None), expires_at=(earlier(-60)).replace(tzinfo=None),
                objectives=json.dumps([{'type': 'quests', 'target': 2, 'min_rank': 'C'},
                                       {'type': 'focus', 'target': 90},
                                       {'type': 'perfect', 'target': 1},
                                       {'type': 'sleep', 'target': 1}]))
    db.session.add(gate)
    for rank in ('D', 'C', 'S'):
        league.record(p, 'effort', rank=rank).quest_id = 7
    league.record(p, 'focus', minutes=50); league.record(p, 'focus', minutes=50)
    league.record(p, 'daily_result', success=False)
    league.record(p, 'sleep').value = 6.5
    db.session.commit()
    rows = G.progress(gate)
    assert [r['done'] for r in rows] == [2, 90, 0, 0]
    assert rows[0]['label'] == 'Clear 2 C-rank or higher quests' and rows[1]['pct'] == 100
    assert rows[2]['label'] == 'Finish all dailies on 1 day' and rows[3]['label'] == 'Log 7h+ of sleep on 1 night'


def test_claim_weekly_gate_rewards(app):
    p = player()
    gate = entered_gate(p)
    complete_objectives(p, gate)
    G.refresh(p)
    ok, msgs, endpoint = G.claim(p, gate.id, rng=random.Random(1))
    assert ok and endpoint is None and gate.status == 'claimed'
    xp = int(round(S.calculate_xp_required(15) * 0.25, -1))
    assert f"+{xp:,} XP, +100 Coins" in msgs[0] and msgs[1].startswith('LOOT DROPPED')
    assert Inventory.query.filter_by(player_id=p.id).count() == 1
    assert 'Gate Breaker' in [t.title.name for t in p.unlocked_titles]
    assert league.weekly_points(p.id, league.week_start_for()) == 0  # rewards never add league points
    ok, msgs, _ = G.claim(p, gate.id)
    assert not ok


def test_gate_guards_and_endings(app):
    p, other = player(), player('Other')
    gate = G.ensure_weekly_gate(p); db.session.commit()
    assert not G.enter(other, gate.id)[0] and not G.claim(other, gate.id)[0]
    assert not G.decline(other, gate.id)[0]
    assert not G.claim(p, gate.id)[0]  # not cleared
    assert G.decline(p, gate.id)[0] and gate.status == 'declined'
    assert not G.enter(p, gate.id)[0]

    # missed: enter_by passed
    q = player('Late')
    late = G.ensure_weekly_gate(q); late.enter_by = earlier(1).replace(tzinfo=None); db.session.commit()
    ok, msg = G.enter(q, late.id)
    assert not ok and late.status == 'missed'

    # failed: time ran out
    r = player('Slow')
    gate = entered_gate(r)
    gate.expires_at = earlier(1).replace(tzinfo=None)
    assert 'collapsed' in G.update_status(gate) and gate.status == 'failed'


def test_refresh_all_background(app):
    player('A'); player('B', level=3)
    assert G.refresh_all(app) == 0
    assert Gate.query.count() == 1


# ---------------------------------------------------------------- red gates

def test_red_gate_spawn_rules(app, monkeypatch):
    assert G.maybe_spawn_red_gate(player('Low', level=29)) is None
    p = player('Red', level=30)
    monkeypatch.setattr(G, 'RED_GATE_DAILY_CHANCE', 0)
    assert G.maybe_spawn_red_gate(p) is None
    monkeypatch.setattr(G, 'RED_GATE_DAILY_CHANCE', 100)
    gate = G.maybe_spawn_red_gate(p); db.session.commit()
    assert gate.kind == 'red' and gate.title.startswith('RED GATE') and gate.enter_by is not None
    assert json.loads(gate.objectives)[-1]['min_rank'] == 'A'
    assert G.maybe_spawn_red_gate(p) is None  # one a week


def test_red_gate_rewards_and_mythic(app, monkeypatch):
    monkeypatch.setattr(G, 'RED_GATE_DAILY_CHANCE', 100)
    p = player('Red', level=30)
    gate = entered_gate(p, 'red')
    assert G.duration(gate) == timedelta(hours=48)
    complete_objectives(p, gate); G.refresh(p)
    ok, msgs, _ = G.claim(p, gate.id, rng=random.Random(3))
    assert '+400 Coins' in msgs[0]  # B-grade at Lv 30: 200 x2
    item = Inventory.query.filter_by(player_id=p.id).one().item
    assert item.rarity in ('rare', 'epic')
    assert 'Red Gate Survivor' in [t.title.name for t in p.unlocked_titles]

    q = player('Mythic', level=80)
    gate = entered_gate(q, 'red')
    complete_objectives(q, gate); G.refresh(q)
    G.claim(q, gate.id, rng=random.Random(4))
    assert Inventory.query.filter_by(player_id=q.id).one().item.rarity == 'legendary'


# ---------------------------------------------------------------- loot

def test_rarity_is_gated_by_level(app):
    rng = random.Random(0)
    low = player('L', level=15)
    assert {loot.roll_rarity(low, rng) for _ in range(300)} == {'common', 'rare'}
    mid = player('M', level=30)
    assert 'epic' in {loot.roll_rarity(mid, rng) for _ in range(300)}
    assert loot.roll_rarity(low, rng, floor='epic') == 'rare'  # floor above unlocks: best unlocked
    high = player('H', level=60)
    assert 'legendary' in {loot.roll_rarity(high, rng) for _ in range(600)}


def test_grant_loot_and_salvage(app):
    p = player()
    msg = loot.grant_loot(p, random.Random(5), rarity='rare')
    item = Inventory.query.one().item
    assert msg.startswith('LOOT DROPPED: [RARE]') and item.currency == 'loot' and item.stock == 0
    assert 3 <= item.stat_value <= 4 and item.slot in loot.SLOTS
    coins = p.coins
    msg = loot.grant_loot(p, random.Random(5), rarity='rare')
    assert 'salvaged for 75 Coins' in msg and p.coins == coins + 75 and Inventory.query.count() == 1
    shop = RewardItem.query.filter((RewardItem.stock == -1) | (RewardItem.stock > 0)).all()
    assert item not in shop  # loot is never sold


def test_quest_drops(app):
    p = player()
    daily = Quest(title='D', rank='S', is_daily=True, player_id=p.id)
    big = Quest(title='A', rank='A', player_id=p.id)
    always = type('R', (), {'random': lambda self: 0.0, 'choice': random.choice, 'choices': random.choices,
                            'randint': random.randint})()
    assert loot.maybe_drop_from_quest(p, daily, always) is None
    assert loot.maybe_drop_from_quest(p, big, always).startswith('LOOT')
    never = type('R', (), {'random': lambda self: 0.99})()
    assert loot.maybe_drop_from_quest(p, big, never) is None
    assert loot.maybe_drop_from_quest(player('Young', level=14), big, always) is None


def test_quest_completion_announces_drops(auth_client, app, csrf_token, monkeypatch):
    p = me(); p.level = 20; p.xp_required = S.calculate_xp_required(20); db.session.commit()
    monkeypatch.setattr(loot, 'QUEST_DROP_CHANCE', {'A': 1.0})
    q = Quest(title='Ship it', rank='A', player=p); db.session.add(q); db.session.commit()
    page = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'LOOT DROPPED' in page


def _equip_set(p, name, pieces):
    for slot in list(loot.SETS[name]['pieces'])[:pieces]:
        spec = {'name': loot.SETS[name]['pieces'][slot], 'slot': slot, 'stat': 'STR', 'value': 10, 'set_name': name}
        row = loot._item_row(spec, 'legendary')
        db.session.add(Inventory(player_id=p.id, item_id=row.id, is_equipped=True))
    db.session.commit()


def test_set_bonuses(app):
    p = player('S', strength=10, agility=10, intelligence=10, vitality=10, sense=10)
    _equip_set(p, 'Abyssal Sovereign', 1)
    assert loot.set_stat_bonuses(p) == {} and loot.set_xp_bonus(p) == 0
    q = player('T', strength=10, agility=10, intelligence=10, vitality=10, sense=10)
    _equip_set(q, 'Abyssal Sovereign', 2)
    assert loot.set_stat_bonuses(q) == {'strength': 5, 'agility': 5}
    stats = S.calculate_total_stats(q)
    assert stats['agility'] == 10 + 5 and stats['strength'] == 10 + 20 + 5
    r = player('U')
    _equip_set(r, 'Starfall Archon', 4)
    assert loot.set_xp_bonus(r) == pytest.approx(0.05)
    assert S.xp_multiplier(r) == pytest.approx(S.xp_multiplier(player('V')) * 1.05)
    summary = loot.set_summaries(r)
    assert summary[0]['name'] == 'Starfall Archon' and summary[0]['four']


def test_inventory_shows_rarity_and_sets(auth_client, app):
    p = me()
    _equip_set(p, 'Unbroken Bastion', 2)
    page = auth_client.get('/inventory').data.decode()
    assert 'LEGENDARY SETS' in page and 'Unbroken Bastion' in page and '(ACTIVE)' in page
    assert '[LEGENDARY] Bastion' in page


# ---------------------------------------------------------------- shadow army

def test_shadow_grades_and_assignment(app):
    p = player('Lord', level=24)
    sh = Shadow(player_id=p.id, original_quest_name='Igris')
    q = Quest(title='Run', rank='C', is_daily=True, player=p)
    db.session.add_all([sh, q]); db.session.commit()
    ok, msg = shadows.assign(p, sh.id, q.id)
    assert not ok and 'Level 25' in msg
    p.level = 25
    assert shadows.assign(p, sh.id, q.id)[0] and sh.assigned_quest_id == q.id
    assert not shadows.assign(p, sh.id, 999)[0]
    assert not shadows.assign(player('X'), sh.id, q.id)[0]

    sh.kills = 9
    assert shadows.record_kill(p, q) == ['SHADOW PROMOTED: Igris is now a Knight!']
    assert shadows.grade_name(sh) == 'Knight' and shadows.next_grade(sh) == ('Elite', 30)
    assert shadows.army_weight(p) == 2
    sh.kills = 100
    assert shadows.grade_name(sh) == 'Marshal' and shadows.next_grade(sh) is None
    assert shadows.assign(p, sh.id, None)[0] and sh.assigned_quest_id is None


def test_commander_title_and_stat_weight(app):
    p = player('Lord', level=25, strength=100, agility=10, intelligence=10, vitality=10, sense=0)
    db.session.add(Shadow(player_id=p.id, original_quest_name='Beru', kills=60)); db.session.commit()
    assert S.calculate_total_stats(p)['strength'] == 104   # 4 x 1%
    assert 'Shadow Commander' in S.check_title_unlocks(p)


def test_completing_assigned_quest_promotes_shadow(auth_client, app, csrf_token):
    p = me(); p.level = 25; p.xp_required = S.calculate_xp_required(25)
    q = Quest(title='Pushups', rank='D', is_daily=True, player=p); db.session.add(q); db.session.commit()
    db.session.add(Shadow(player_id=p.id, original_quest_name='Tusk', kills=9, assigned_quest_id=q.id))
    db.session.commit()
    page = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Tusk is now a Knight' in page


def test_army_modal_assign_route(auth_client, app, csrf_token):
    p = me(); p.level = 30; db.session.commit()
    sh = Shadow(player_id=p.id, original_quest_name='Kaisel'); db.session.add(sh)
    q = Quest(title='Read', rank='D', is_daily=True, player=p); db.session.add(q); db.session.commit()
    page = auth_client.get('/').data.decode()
    assert 'SOLDIER · 0 kills' in page and 'Assign a shadow to a quest' in page
    auth_client.post(f'/shadows/{sh.id}/assign', data={'quest_id': q.id, 'csrf_token': csrf_token})
    assert db.session.get(Shadow, sh.id).assigned_quest_id == q.id


# ---------------------------------------------------------------- rank assessment

def _qualified(rank='C', level=40, stat=40, **kw):
    return player(f'Q{rank}{level}', level=level, rank=rank, strength=stat, agility=stat, intelligence=stat,
                  vitality=stat, sense=stat, **kw)


def test_rank_b_requires_assessment(app):
    p = _qualified()
    assert S.check_player_rank_up(p) == (False, None) and p.rank == 'C'
    exam = G.ensure_rank_exam(p); db.session.commit()
    assert exam.kind == 'exam' and exam.target_rank == 'B' and exam.enter_by is None
    assert G.ensure_rank_exam(p) is None
    assert G.duration(exam) == timedelta(days=7)
    assert G.ensure_rank_exam(_qualified(level=39)) is None
    assert G.ensure_rank_exam(_qualified(level=41, stat=30)) is None  # 150 total < 200


def test_lower_ranks_stay_automatic(app):
    p = player('E', level=10, rank='E', strength=10, agility=10, intelligence=10, vitality=10, sense=10)
    assert S.check_player_rank_up(p) == (True, 'D')


def test_passing_and_failing_exams(app):
    p = _qualified()
    exam = G.ensure_rank_exam(p); db.session.commit()
    G.enter(p, exam.id, now=earlier())
    complete_objectives(p, exam); G.refresh(p)
    ok, msgs, _ = G.claim(p, exam.id)
    assert ok and p.rank == 'B' and 'ASSESSMENT PASSED' in msgs[0]

    q = _qualified('B', 60, 70)
    exam = G.ensure_rank_exam(q); db.session.commit()
    G.enter(q, exam.id, now=earlier())
    exam.expires_at = earlier(1).replace(tzinfo=None)
    msgs = G.refresh(q)
    assert any('FAILED' in m for m in msgs) and exam.status == 'failed'
    assert G.ensure_rank_exam(q) is None                                  # retry cooldown
    assert G.ensure_rank_exam(q, now=datetime.now(timezone.utc) + timedelta(days=4)).target_rank == 'A'


def test_exams_cannot_be_declined(app):
    p = _qualified()
    exam = G.ensure_rank_exam(p); db.session.commit()
    assert not G.decline(p, exam.id)[0]


# ---------------------------------------------------------------- second awakening

_counter = iter(range(10_000))


def _awakened(line='Mage', spec=None):
    p = player(f'{line}{spec}{next(_counter)}', level=50, job_class={'Mage': 'Spellweaver', 'Tank': 'Iron Fortress',
                                                    'Assassin': 'Shadow Lord'}[line], specialization=spec)
    return p


def test_awakening_trial_and_choice(auth_client, app, csrf_token):
    assert G.ensure_awakening(player('NoClass', level=50)) is None
    assert G.ensure_awakening(player('Young', level=49, job_class='Mage')) is None

    p = me(); p.level = 50; p.job_class = 'Spellweaver'; p.xp_required = S.calculate_xp_required(50)
    db.session.commit()
    assert auth_client.get('/awakening').status_code == 302      # trial not cleared yet
    assert not P.choose_specialization(p, 'Sage')[0]
    gate = G.ensure_awakening(p); db.session.commit()
    G.enter(p, gate.id, now=earlier())
    complete_objectives(p, gate); G.refresh(p)
    r = auth_client.post(f'/gates/{gate.id}/claim', data={'csrf_token': csrf_token})
    assert r.headers['Location'].endswith('/awakening')
    page = auth_client.get('/awakening').data.decode()
    assert 'CHOOSE SAGE' in page and 'CHOOSE ELEMENTALIST' in page
    page = auth_client.post('/awakening', data={'specialization': 'Nope', 'csrf_token': csrf_token},
                            follow_redirects=True).data.decode()
    assert 'Unknown specialisation' in page
    page = auth_client.post('/awakening', data={'specialization': 'Sage', 'csrf_token': csrf_token},
                            follow_redirects=True).data.decode()
    assert 'you are now a Sage Mage' in page and me().specialization == 'Sage'
    assert G.ensure_awakening(me()) is None
    assert not P.choose_specialization(me(), 'Elementalist')[0]


def test_specialization_effects(app):
    assert P.class_coin_bonus(_awakened('Assassin', 'Blade')) == 0.20
    assert P.class_coin_bonus(_awakened('Assassin', 'Phantom')) == 0.10
    assert P.class_xp_bonus(_awakened('Mage', 'Elementalist')) == 0.15
    assert P.penalty_grace_days(_awakened('Tank', 'Warden')) == 2
    phantom = P.skill_info(_awakened('Assassin', 'Phantom'))
    assert phantom['cooldown_days'] == 3   # tier III (5 days) - 2
    sage = _awakened('Mage', 'Sage')
    sage.skill_armed = True
    assert P.insight_bonus_xp(sage, 120, 10, 1.0) == int(120 * 10 * 0.7)
    bulwark = _awakened('Tank', 'Bulwark')
    bulwark.xp_debt = 1000
    ok, msg = P.use_skill(bulwark)
    assert ok and bulwark.xp_debt == 300 and bulwark.skill_armed and 'shield raised' in msg


def test_warden_gets_two_grace_days(app):
    p = _awakened('Tank', 'Warden')
    p.consecutive_missed_days, p.last_daily_reset = 1, one_reset_ago()
    db.session.add(Quest(title='Daily', is_daily=True, player=p)); db.session.commit()
    S.check_daily_reset(p)
    assert p.consecutive_missed_days == 2 and not p.has_debuff


# ---------------------------------------------------------------- ascension

def test_ascension(auth_client, app, csrf_token):
    page = auth_client.post('/ascend', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Ascension requires Level 100' in page

    p = me(); p.level = 100; p.job_class = 'Monarch of Iron'; p.rank = 'S'; p.strength = 150
    p.xp_required = S.calculate_xp_required(100); db.session.commit()
    page = auth_client.get('/roadmap').data.decode()
    assert 'ASCENSION AVAILABLE' in page
    page = auth_client.post('/ascend', data={'csrf_token': csrf_token}, follow_redirects=True).data.decode()
    assert 'ASCENSION I' in page and 'TITLE UNLOCKED: Ascendant' in page
    p = me()
    assert (p.level, p.xp, p.ascensions, p.job_class, p.rank, p.strength) == (1, 0, 1, 'Monarch of Iron', 'S', 150)
    assert P.effective_level(p) == 101
    assert S.xp_multiplier(p) == pytest.approx(S.xp_multiplier(player('Fresh', level=1)) * 1.05)

    stones = P.milestones(p)
    assert all(m['reached'] for m in stones if m['level'] < 100)
    nxt = P.next_milestone(p)
    assert nxt['level'] == 100 and any(r['title'] == 'Ascension II' for r in nxt['rewards'])
    # unlocks follow effective level: the dashboard visit after ascending already opened this week's gate
    assert Gate.query.filter_by(player_id=p.id, kind='gate').count() == 1


# ---------------------------------------------------------------- dashboard & roadmap

def test_dashboard_gate_panel_flow(auth_client, app, csrf_token):
    p = me(); p.level = 15; p.xp_required = S.calculate_xp_required(15); db.session.commit()
    page = auth_client.get('/').data.decode()
    assert 'C-Rank Gate:' in page and 'ENTER' in page and 'DECLINE' in page and 'Closes ' in page
    gate = Gate.query.one()
    page = auth_client.post(f'/gates/{gate.id}/enter', data={'csrf_token': csrf_token},
                            follow_redirects=True).data.decode()
    assert 'ENTERED' in page and ' left' in page
    gate = Gate.query.one()
    gate.entered_at = earlier().replace(tzinfo=None); db.session.commit()
    complete_objectives(me(), gate)
    page = auth_client.get('/').data.decode()
    assert 'GATE CLEARED' in page and 'CLAIM REWARDS' in page
    page = auth_client.post(f'/gates/{gate.id}/claim', data={'csrf_token': csrf_token},
                            follow_redirects=True).data.decode()
    assert 'REWARDS: +' in page and 'TITLE UNLOCKED: Gate Breaker' in page
    assert b'CLAIM REWARDS' not in auth_client.get('/').data
    r = auth_client.post(f'/gates/{gate.id}/claim', data={'csrf_token': csrf_token}, follow_redirects=True)
    assert b'Clear the gate before claiming it' in r.data


def test_decline_route(auth_client, app, csrf_token):
    p = me(); p.level = 16; db.session.commit()
    auth_client.get('/')
    gate = Gate.query.one()
    auth_client.post(f'/gates/{gate.id}/decline', data={'csrf_token': csrf_token})
    assert db.session.get(Gate, gate.id).status == 'declined'


def test_roadmap_lists_new_unlocks(auth_client, app):
    page = auth_client.get('/roadmap').data.decode()
    for text in ('Gates open', 'Loot drops', 'Shadow Army ranks', 'Red Gates', 'Rank Assessment: B-Rank',
                 'Second Awakening', 'Legendary sets', 'Mythic Red Gates', 'Ascension I',
                 'Title: Sovereign Candidate', 'Title: Monarch'):
        assert text in page, text
    p = me(); p.job_class = 'Tank'; db.session.commit()
    page = auth_client.get('/roadmap').data.decode()
    assert 'Bulwark (fortify pays off debt AND raises the shield in a single use)' in page
