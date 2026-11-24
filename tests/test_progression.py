"""Road to Monarch roadmap, class skills (Vanish / Insight / Fortify) and evolved-class bonuses."""
from datetime import datetime, timedelta, timezone

import pytest

from app import league, progression as P
from app import services as S
from app.extensions import db
from app.models import Player, Quest

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


NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)


# --- class lines ---

@pytest.mark.parametrize('job, line, tier', [
    ('Assassin', 'Assassin', 1), ('Shadow Assassin', 'Assassin', 2), ('Monarch of Shadows', 'Assassin', 6),
    ('Archmage', 'Mage', 2), ('Arcane Sage', 'Mage', 4), ('Titan', 'Tank', 4), ('Monarch of Iron', 'Tank', 6),
    ('None', None, 0), (None, None, 0), ('Bard', None, 0),
])
def test_base_class_and_tier(job, line, tier):
    assert P.base_class(job) == line
    assert P.class_tier(job) == tier


def test_evolved_classes_keep_their_passive_bonus(app):
    """Regression: bonuses used to check the exact base name and vanished at the Lv 20 evolution."""
    results = {}
    for job in ('None', 'Mage', 'Archmage', 'Assassin', 'Shadow Lord'):
        p = player(job, job_class=job, xp_required=100_000)
        q = Quest(title='A', rank='A', player=p); db.session.add(q); db.session.commit()
        results[job] = S.process_quest_completion(p, q)[:3]
    assert results['Archmage'][0] == results['Mage'][0] > results['None'][0]
    assert results['Shadow Lord'][2] == results['Assassin'][2] > results['None'][2]


def test_evolved_tank_keeps_penalty_grace(app):
    p = player(job_class='Juggernaut', last_daily_reset=one_reset_ago())
    db.session.add(Quest(title='Daily', is_daily=True, player=p)); db.session.commit()
    S.check_daily_reset(p)
    assert p.consecutive_missed_days == 1 and not p.has_debuff  # grace day, like a base Tank


# --- skills: info, cooldown, guards ---

def test_no_skill_before_job_change(app):
    p = player()
    assert P.skill_info(p) is None
    ok, msg = P.use_skill(p)
    assert not ok and 'Level 10' in msg


def test_skill_info_scales_with_tier(app):
    mage = P.skill_info(player('M', job_class='Mage'), NOW)
    assert (mage['full_name'], mage['cooldown_days'], mage['ready']) == ('Insight I', 7, True)
    assert 'x1.5 XP' in mage['effect']
    monarch = P.skill_info(player('MM', job_class='Monarch of Scrolls'), NOW)
    assert (monarch['full_name'], monarch['cooldown_days']) == ('Insight VI', 2)
    assert 'x2 XP' in monarch['effect']
    tank = P.skill_info(player('T', job_class='Iron Fortress'), NOW)
    assert tank['full_name'] == 'Fortify III' and '70%' in tank['effect']


def test_cooldown_and_already_active(app):
    p = player(job_class='Assassin')
    ok, msg = P.use_skill(p, NOW)
    assert ok and 'VANISH I' in msg and p.skill_armed
    assert P.skill_info(p, NOW)['armed']
    ok, msg = P.use_skill(p, NOW)
    assert not ok and 'already active' in msg

    p.skill_armed = False
    ok, msg = P.use_skill(p, NOW + timedelta(days=2))
    assert not ok and 'ready in 5d' in msg
    info = P.skill_info(p, NOW + timedelta(days=6, hours=23, minutes=30))
    assert not info['ready'] and info['ready_in'] == '1h'
    assert P.skill_info(p, NOW + timedelta(days=7))['ready']
    # naive datetimes from MySQL are treated as UTC
    p.skill_ready_at = (NOW + timedelta(days=1)).replace(tzinfo=None)
    assert P.skill_info(p, NOW)['ready_in'] == '1d 0h'


def test_using_a_skill_gives_no_league_points(app):
    p = player(job_class='Mage')
    P.use_skill(p)
    assert league.weekly_points(p.id, league.week_start_for()) == 0


# --- Vanish ---

def _close_day(p, done):
    db.session.add(Quest(title='Daily', is_daily=True, is_completed=done, player=p))
    p.last_daily_reset = one_reset_ago()
    db.session.commit()
    return S.check_daily_reset(p)


def test_vanish_forgives_a_missed_day_without_spending_freezes(app):
    p = player(job_class='Shadow Assassin', current_streak=5, highest_streak=5, streak_freezes=1)
    P.use_skill(p)
    _, msgs = _close_day(p, done=False)
    assert any('VANISH' in m for m in msgs)
    assert (p.current_streak, p.streak_freezes, p.consecutive_missed_days, p.penalties_count) == (5, 1, 0, 0)
    assert not p.has_debuff and not p.skill_armed


def test_vanish_is_spent_even_on_a_completed_day(app):
    p = player(job_class='Assassin', current_streak=2, highest_streak=2)
    P.use_skill(p)
    _close_day(p, done=True)
    assert p.current_streak == 3 and not p.skill_armed


# --- Insight ---

def test_insight_boosts_next_focus_session_only(auth_client, app, csrf_token):
    p = me(); p.job_class = 'Mage'; db.session.commit()
    auth_client.post('/skill/use', data={'csrf_token': csrf_token})
    assert me().skill_armed

    r = auth_client.post('/focus_complete', json={'minutes': 90}, headers={'X-CSRFToken': csrf_token}).get_json()
    # 90 min = 900 XP base; Insight I adds +50% on the first 60 min = +300
    assert '+1200 XP' in r['msg'] and '(INSIGHT +300 XP)' in r['msg']
    assert not me().skill_armed
    assert league.weekly_points(me().id, league.week_start_for()) == 90.0  # base XP only

    r = auth_client.post('/focus_complete', json={'minutes': 10}, headers={'X-CSRFToken': csrf_token}).get_json()
    assert 'INSIGHT' not in r['msg']


# --- Fortify ---

def test_fortify_pays_off_debt(app):
    p = player(job_class='Tank', xp_debt=801)
    ok, msg = P.use_skill(p)
    assert ok and p.xp_debt == 401 and '400 XP of debt cleared' in msg  # round-half-even and not p.skill_armed
    q = player('Q', job_class='World Guardian', xp_debt=500)   # tier 5: 90%
    P.use_skill(q)
    assert q.xp_debt == 50
    r = player('R', job_class='Monarch of Iron', xp_debt=500)  # tier 6: everything
    ok, msg = P.use_skill(r)
    assert r.xp_debt == 0 and 'DEBT CLEARED' in msg


def _failed_penalty_tank(**kw):
    # Tanks get one grace day, so the third missed day triggers the failure check.
    p = player(job_class='Tank', level=10, xp=50, xp_required=S.calculate_xp_required(10),
               consecutive_missed_days=3, in_penalty_zone=True, has_debuff=True,
               last_daily_reset=one_reset_ago(), **kw)
    db.session.add(Quest(title='Daily', is_daily=True, player=p))
    db.session.add(Quest(title='PENALTY: Survive', is_penalty=True, rank='A', player=p,
                         due_date=(datetime.now(timezone.utc) - timedelta(hours=2)).replace(tzinfo=None)))
    db.session.commit()
    return p


@pytest.mark.parametrize('hardcore', [False, True])
def test_fortify_shield_absorbs_failed_penalty(app, hardcore):
    p = _failed_penalty_tank(hardcore=hardcore)
    ok, msg = P.use_skill(p)
    assert ok and 'shield raised' in msg
    _, msgs = S.check_daily_reset(p)
    assert any('FORTIFY' in m for m in msgs)
    assert (p.level, p.xp_debt) == (10, 0) and not p.skill_armed
    assert not p.in_penalty_zone and Quest.query.filter_by(is_penalty=True, is_completed=False).count() == 0


def test_without_shield_tank_still_takes_debt(app):
    p = _failed_penalty_tank()
    _, msgs = S.check_daily_reset(p)
    assert any('XP DEBT' in m for m in msgs) and p.xp_debt > 0


# --- skill route & dashboard ---

def test_skill_route_and_dashboard_card(auth_client, app, csrf_token):
    assert b'USE SKILL' not in auth_client.get('/').data          # no class yet
    page = auth_client.post('/skill/use', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Level 10' in page

    p = me(); p.job_class = 'Juggernaut'; p.level = 20; db.session.commit()
    page = auth_client.get('/').data.decode()
    assert 'FORTIFY II' in page and 'USE SKILL' in page
    page = auth_client.post('/skill/use', data={'csrf_token': csrf_token}, follow_redirects=True).data.decode()
    assert 'shield raised' in page and 'ACTIVE' in page
    p = me(); p.skill_armed = False; db.session.commit()
    assert 'Ready in 6d' in auth_client.get('/').data.decode() or 'Ready in 5d 23h' in auth_client.get('/').data.decode()


def test_skill_route_ignores_foreign_referrer(auth_client, app, csrf_token):
    r = auth_client.post('/skill/use', data={'csrf_token': csrf_token}, headers={'Referer': 'https://evil.example/x'})
    assert r.headers['Location'].endswith('/')


# --- roadmap ---

def test_milestones_before_class(app):
    stones = P.milestones(player(level=12))
    levels = [m['level'] for m in stones]
    assert levels == sorted(levels) and levels[:4] == [10, 15, 20, 25]
    lv10 = stones[0]
    titles = [r['title'] for r in lv10['rewards']]
    assert titles[:2] == ['Job Change Trial', 'Class skill unlocked']
    assert 'Hunter Rank D' in titles and 'Title: The Awakened' in titles and lv10['reached']
    assert [r['title'] for r in stones[1]['rewards']] == ['Gates open', 'Loot drops']
    assert [r['title'] for r in stones[2]['rewards']][0] == 'Class Evolution II'
    assert any(r['title'] == 'Title: Demon Hunter' and '+10% XP' in r['detail'] for m in stones for r in m['rewards'])


def test_milestones_follow_class_line(app):
    stones = P.milestones(player(level=25, job_class='Shadow Assassin'))
    lv20 = next(m for m in stones if m['level'] == 20)
    assert [r['title'] for r in lv20['rewards']][:2] == ['Evolution: Shadow Assassin', 'Skill: Vanish II']
    lv100 = next(m for m in stones if m['level'] == 100)
    assert lv100['rewards'][0]['title'] == 'Evolution: Monarch of Shadows'


def test_next_milestone_progress(app):
    p = player(level=17, xp=0, xp_required=S.calculate_xp_required(17))
    nxt = P.next_milestone(p)
    assert nxt['level'] == 20 and nxt['levels_away'] == 3 and nxt['progress'] == 40  # 2 of 5 levels since Lv 15
    assert [m['level'] for m in nxt['after']] == [25, 30, 40]
    p.xp = p.xp_required // 2
    assert P.next_milestone(p)['progress'] == 50
    assert P.next_milestone(player('Max', level=100)) is None


def test_level_up_preview(app):
    p = player(level=10)
    assert P.level_up_preview(p, 9).startswith('UNLOCKED: Job Change Trial · Class skill unlocked')
    p.level = 11
    assert P.level_up_preview(p, 10) == 'NEXT: Gates open at LV 15 (4 levels away)'
    p.level = 19
    assert P.level_up_preview(p, 18).endswith('(1 level away)')
    p.level = 100
    assert P.level_up_preview(p, 99).startswith('UNLOCKED: Class Evolution VI')
    p.level = 101
    assert P.level_up_preview(p, 100) == ''


def test_roadmap_page_and_dashboard_panel(auth_client, app):
    page = auth_client.get('/').data.decode()
    assert 'ROAD TO MONARCH' in page and 'LV 10' in page and '9 levels away' in page

    p = me(); p.job_class = 'Archmage'; p.level = 22; db.session.commit()
    page = auth_client.get('/roadmap').data.decode()
    assert 'CLASS SKILL: INSIGHT' in page and 'Evolution: Spellweaver' in page
    assert page.count('UNLOCKED') >= 2 and 'NEXT ·' in page
    assert 'class="current"' in page  # tier II highlighted


def test_evolution_popup_mentions_skill_upgrade(auth_client, app, csrf_token):
    p = me(); p.job_class = 'Mage'; p.level = 19; p.xp = 0
    p.xp_required = S.calculate_xp_required(19); db.session.commit()
    q = Quest(title='Finish', rank='S', player=p); db.session.add(q); db.session.commit()
    page = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data.decode()
    assert 'CLASS EVOLVED: You are now a Archmage! Skill upgraded to Insight II' in page
    assert '20|1|UNLOCKED: Evolution: Archmage' in page


def test_guide_covers_endgame_systems(auth_client, app):
    page = auth_client.get('/').data.decode()
    for text in ('CLASS & SKILLS', 'a trial reveals your class', 'GATES & LOOT', 'HUNTER RANK', 'Rank Assessment',
                 'Shadow ranks (Lv 25)', 'ASCENSION', 'Road to Monarch</a>', 'Red Gates (Lv 30)'):
        assert text in page, text
    assert 'Vanish</strong>' not in page  # class details stay hidden before the Job Change
    p = me(); p.job_class = 'Mage'; db.session.commit()
    page = auth_client.get('/').data.decode()
    assert 'Vanish</strong>' in page and 'Second Awakening (Lv 50)' in page
