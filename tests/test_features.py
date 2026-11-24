"""Tests for Shadow extraction, titles, sleep condition effects and global popups."""
from app.models import Player, Quest, Shadow, Title, Inventory, RewardItem
from app.extensions import db
from app.services import (seed_titles, check_title_unlocks, calculate_total_stats,
                          process_quest_completion, get_arise_candidates, extract_shadow,
                          TITLE_DEFINITIONS)


def _player(name="Hunter", **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password("pass")
    db.session.add(p)
    db.session.commit()
    return p


# --- Shadow Army ---

def test_s_rank_completion_offers_arise(auth_client, app, csrf_token):
    p = Player.query.filter_by(name="AuthUser").first()
    q = Quest(title="Slay the Dragon", rank="S", player=p)
    db.session.add(q)
    db.session.commit()

    resp = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token})
    assert resp.status_code == 302 and f'arise={q.id}' in resp.headers['Location']

    page = auth_client.get(resp.headers['Location']).data
    assert b'EXTRACTION AVAILABLE' in page
    assert f'/arise/{q.id}'.encode() in page


def test_arise_creates_shadow_and_clears_candidate(auth_client, app, csrf_token):
    p = Player.query.filter_by(name="AuthUser").first()
    q = Quest(title="Conquer Everest", rank="S", player=p, is_completed=True)
    db.session.add(q)
    db.session.commit()
    assert [c.id for c in get_arise_candidates(p)] == [q.id]

    page = auth_client.post(f'/arise/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert Shadow.query.filter_by(player_id=p.id).count() == 1
    assert get_arise_candidates(p) == []
    assert b'arise_trigger' in page  # routed to the ARISE popup


def test_penalty_and_daily_quests_cannot_be_extracted(app):
    p = _player()
    penalty = Quest(title="PENALTY: Survival", rank="A", player=p, is_penalty=True, is_completed=True)
    daily = Quest(title="Daily S", rank="S", player=p, is_daily=True, is_completed=True)
    db.session.add_all([penalty, daily])
    db.session.commit()
    assert not extract_shadow(p, penalty.id)[0]
    assert not extract_shadow(p, daily.id)[0]
    assert get_arise_candidates(p) == []


# --- Titles ---

def test_seed_titles_idempotent(app):
    seed_titles(); db.session.commit()
    seed_titles(); db.session.commit()
    assert Title.query.count() == len(TITLE_DEFINITIONS)


def test_titles_unlock_and_auto_equip(app):
    seed_titles()
    p = _player(level=12)
    unlocked = check_title_unlocks(p)
    assert "E-Rank Hunter" in unlocked and "The Awakened" in unlocked
    assert p.current_title is not None


def test_daily_streak_title_uses_daily_streak_not_sleep(app):
    seed_titles()
    p = _player(sleep_streak=10, current_streak=0, highest_streak=0)
    assert "Iron Will" not in check_title_unlocks(p)
    p.current_streak = 7
    assert "Iron Will" in check_title_unlocks(p)


def test_equipped_title_buffs_apply(app):
    seed_titles()
    p = _player(level=1)
    p.xp_required = 10_000
    p.current_title = Title.query.filter_by(name="Iron Will").first()  # ALL STATS +1
    base = calculate_total_stats(p)['strength']
    assert base == p.strength + 1

    p.current_title = Title.query.filter_by(name="The Awakened").first()  # XP +5%
    q = Quest(title="Q", rank="C", player=p)
    db.session.add(q); db.session.commit()
    xp_gain, *_ = process_quest_completion(p, q)
    assert xp_gain == int(int(150 * 1.005) * 1.05)  # C = 150; 1 INT => +0.5%, then title +5%


def test_dashboard_announces_title_unlock(auth_client, app):
    seed_titles(); db.session.commit()
    page = auth_client.get('/').data
    assert b'TITLE UNLOCKED: E-Rank Hunter' in page


# --- Sleep condition ---

def _xp_for(app, condition):
    p = _player(name=f"Sleeper-{condition}", condition=condition)
    p.xp_required = 10_000
    q = Quest(title="Q", rank="C", player=p)
    db.session.add(q); db.session.commit()
    return process_quest_completion(p, q)[0]


def test_condition_changes_xp(app):
    normal = _xp_for(app, "NORMAL")
    assert _xp_for(app, "WELL RESTED") == int(normal * 1.10)
    assert _xp_for(app, "TIRED") == int(normal * 0.5)


def test_level_up_cures_tired_but_keeps_well_rested(app):
    from app.services import process_level_up
    tired = _player(name="T", condition="TIRED", xp=200)
    rested = _player(name="R", condition="WELL RESTED", xp=200)
    process_level_up(tired); process_level_up(rested)
    assert tired.condition == "NORMAL"
    assert rested.condition == "WELL RESTED"


# --- Global popups ---

def test_system_popup_visible_off_dashboard(auth_client, app, csrf_token):
    p = Player.query.filter_by(name="AuthUser").first()
    elixir = RewardItem(name="Elixir of Life", cost=1, currency='coins', item_type='consumable')
    db.session.add(elixir); db.session.commit()
    inv = Inventory(player_id=p.id, item_id=elixir.id)
    db.session.add(inv); db.session.commit()

    page = auth_client.post(f'/use_item/{inv.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'ELIXIR OF LIFE CONSUMED' in page
    assert b'id="systemModal"' in page  # popup modal now exists on the inventory page


# --- Popup messages ---

def test_s_rank_message_and_level_up_payload(auth_client, app, csrf_token):
    p = Player.query.filter_by(name="AuthUser").first()
    q = Quest(title="Boss Raid", rank="S", player=p)
    db.session.add(q); db.session.commit()

    page = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'INSTANT LEVEL UP' in page
    assert b'+0 XP' not in page
    # Level-up overlay payload: "<new level>|<levels gained>"
    assert b'data-category="levelup">2|1<' in page


def test_daily_completion_shows_progress_not_zero_xp(auth_client, app, csrf_token):
    p = Player.query.filter_by(name="AuthUser").first()
    d1 = Quest(title="Pushups", rank="E", is_daily=True, player=p)
    d2 = Quest(title="Read", rank="E", is_daily=True, player=p)
    db.session.add_all([d1, d2]); db.session.commit()

    page = auth_client.post(f'/complete/{d1.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Dailies 1/2' in page
    assert b'+0 XP' not in page


def test_flashes_render_as_escaped_data(auth_client, app, csrf_token):
    p = Player.query.filter_by(name="AuthUser").first()
    q = Quest(title='<img src=x onerror=alert(1)>', rank="E", player=p)
    db.session.add(q); db.session.commit()

    page = auth_client.post(f'/complete/{q.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'<img src=x' not in page
    assert b'&lt;img src=x onerror=alert(1)&gt;' in page
    assert b'class="flash-data"' in page


# --- Penalty deadline timezone ---

def test_penalty_deadline_displayed_in_game_time(app):
    from datetime import datetime
    from flask import render_template_string
    due_utc = datetime(2026, 11, 24, 0, 0)  # stored naive UTC = 01:00 Madrid (CET, UTC+1)
    with app.test_request_context():
        assert render_template_string("{{ d | game_time('%H:%M') }}", d=due_utc) == "01:00"
        assert render_template_string("{{ d | utc_iso }}", d=due_utc) == "2026-11-24T00:00:00+00:00"


def test_penalty_deadline_is_next_reset_across_dst(app):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import patch
    from app.services import check_daily_reset, GAME_TIMEZONE
    p = _player(consecutive_missed_days=1, has_debuff=True)
    db.session.add(Quest(title="Daily", is_daily=True, player=p))
    # 29 Mar 2026: clocks go forward in Madrid. "Now" is 10:00 that day; last reset two days ago.
    now_utc = GAME_TIMEZONE.localize(datetime(2026, 3, 29, 10, 0)).astimezone(timezone.utc)
    p.last_daily_reset = now_utc - timedelta(days=1, hours=2)
    db.session.commit()
    with patch('app.services.datetime') as mock_dt:
        mock_dt.now.side_effect = lambda tz=None: now_utc if tz else now_utc.replace(tzinfo=None)
        mock_dt.combine = datetime.combine
        mock_dt.min = datetime.min
        check_daily_reset(p)
    penalty = Quest.query.filter_by(player_id=p.id, is_penalty=True).first()
    due_game = penalty.due_date.replace(tzinfo=timezone.utc).astimezone(GAME_TIMEZONE)
    assert (due_game.day, due_game.hour, due_game.minute) == (30, 1, 0)
