"""Per-player timezones, personal reminders, raids, kudos (Hall of Feats) and the installable app."""
import json
import os
from datetime import datetime, timedelta, timezone

import pytz
import pytest

from app import services as S
from app import social, league
from app.extensions import db
from app.models import ActivityEvent, Kudos, Notification, Player, Quest, Raid, RaidContribution


def player(name='P', **kw):
    p = Player(name=name, setup_complete=True, **kw)
    p.set_password('pw')
    db.session.add(p)
    db.session.commit()
    return p


def me():
    db.session.expire_all()
    return Player.query.filter_by(name='AuthUser').first()


def local(tz_name, *args):
    return pytz.timezone(tz_name).localize(datetime(*args)).astimezone(timezone.utc)


# --- timezones ---

def test_daily_reset_is_one_am_in_the_players_timezone(app):
    ny = player('NY', timezone='America/New_York')
    # 00:30 New York -> still the previous game day; 01:05 -> new day
    assert S.get_latest_daily_reset_time(local('America/New_York', 2026, 11, 24, 0, 30), S.player_tz(ny)) == \
        pytz.timezone('America/New_York').localize(datetime(2026, 11, 23, 1, 0))
    assert S.get_latest_daily_reset_time(local('America/New_York', 2026, 11, 24, 1, 5), S.player_tz(ny)).day == 24


def test_reset_runs_on_the_players_clock(app):
    tz = pytz.timezone('Asia/Tokyo')
    p = player('Tokyo', timezone='Asia/Tokyo')
    latest = S.get_latest_daily_reset_time(tz=tz).astimezone(timezone.utc)
    p.last_daily_reset = latest + timedelta(minutes=1)  # already reset today in Tokyo
    db.session.commit()
    assert S.check_daily_reset(p) == (False, [])
    p.last_daily_reset = latest - timedelta(minutes=1)  # Tokyo's 01:00 has just passed
    assert S.check_daily_reset(p)[0] is True


def test_unknown_timezone_falls_back(app):
    p = player('Weird', timezone='Mars/Olympus')
    assert S.player_tz(p) is S.GAME_TIMEZONE
    assert S.is_valid_timezone('Europe/London') and not S.is_valid_timezone('Mars/Olympus')


def test_locale_settings_route(auth_client, app, csrf_token):
    r = auth_client.post('/settings/locale', data={'timezone': 'America/Chicago', 'reminder_time': '21:30',
                                                   'csrf_token': csrf_token}, follow_redirects=True)
    assert b'daily reminder at 21:30' in r.data
    assert (me().timezone, me().reminder_time) == ('America/Chicago', '21:30')
    auth_client.post('/settings/locale', data={'timezone': 'America/Chicago', 'reminder_time': '', 'csrf_token': csrf_token})
    assert me().reminder_time is None
    page = auth_client.post('/settings/locale', data={'timezone': 'Nowhere/Land', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'Unknown timezone' in page and me().timezone == 'America/Chicago'
    page = auth_client.post('/settings/locale', data={'reminder_time': '25:99', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'must look like 21:00' in page


def test_registration_records_device_timezone(client, app, csrf_token):
    for name, tz, expected in (('Lisbon', 'Europe/Lisbon', 'Europe/Lisbon'), ('Bogus', 'Not/AZone', 'Europe/Madrid')):
        client.post('/register', data={'username': name, 'password': 'pw', 'confirm': 'pw', 'timezone': tz,
                                       'csrf_token': csrf_token})
        assert Player.query.filter_by(name=name).one().timezone == expected


def test_penalty_deadline_shown_in_viewer_timezone(auth_client, app):
    p = me(); p.timezone = 'America/New_York'; p.in_penalty_zone = True; db.session.commit()
    due = datetime(2026, 11, 25, 6, 0)  # naive UTC = 01:00 New York
    db.session.add(Quest(title='PENALTY: run', is_penalty=True, player=p, due_date=due)); db.session.commit()
    page = auth_client.get('/').data
    assert b'DEADLINE: 25/11 01:00 (your time)' in page


# --- reminders ---

def _with_dailies(p, done=(False, False)):
    for i, d in enumerate(done):
        db.session.add(Quest(title=f'D{i}', is_daily=True, is_completed=d, player=p))
    db.session.commit()


def test_reminder_due_time_in_player_timezone(app):
    p = player('NY', timezone='America/New_York', reminder_time='21:00')
    at = local('America/New_York', 2026, 11, 24, 12, 0)
    assert S.reminder_due_at(p, at) == local('America/New_York', 2026, 11, 24, 21, 0)
    p.reminder_time = '00:30'  # after midnight belongs to the end of the same game day
    assert S.reminder_due_at(p, at) == local('America/New_York', 2026, 11, 25, 0, 30)
    p.reminder_time = None
    assert S.reminder_due_at(p, at) is None


def test_reminder_sent_once_when_dailies_unfinished(app):
    p = player('Me', timezone='Europe/London', reminder_time='20:00', current_streak=4)
    _with_dailies(p, (True, False))
    before = local('Europe/London', 2026, 11, 24, 19, 55)
    after = local('Europe/London', 2026, 11, 24, 20, 3)
    assert S.send_due_reminders(app, before) == 0
    assert S.send_due_reminders(app, after) == 1
    assert S.send_due_reminders(app, after + timedelta(minutes=5)) == 0  # once per game day
    msg = Notification.query.one().message
    assert '1 daily left before your 01:00 reset' in msg and '4-day streak' in msg
    # next game day it fires again
    assert S.send_due_reminders(app, after + timedelta(days=1)) == 1


@pytest.mark.parametrize('setup', ['all_done', 'vacation', 'off', 'no_dailies'])
def test_no_reminder_when_not_needed(app, setup):
    p = player('Me', reminder_time='20:00', is_on_vacation=(setup == 'vacation'))
    if setup == 'off':
        p.reminder_time = None
    if setup != 'no_dailies':
        _with_dailies(p, (True, True) if setup == 'all_done' else (False,))
    db.session.commit()
    assert S.send_due_reminders(app, local('Europe/Madrid', 2026, 11, 24, 23, 0)) == 0


# --- raids ---

def test_create_raid_validation_and_limit(app):
    p = player('Leader')
    for args, err in ((('', 'km', 10, 7), 'title and a unit'), (('Run', 'km', 0, 7), 'positive'),
                      (('Run', 'km', 10, 0), 'Duration'), (('Run', 'km', 10, 91), 'Duration')):
        raid, msg = social.create_raid(p, *args)
        assert raid is None and err in msg
    for i in range(social.MAX_ACTIVE_RAIDS):
        assert social.create_raid(p, f'Raid {i}', 'km', 10, 7)[0]
    raid, msg = social.create_raid(p, 'One too many', 'km', 10, 7)
    assert raid is None and 'already 5 active raids' in msg


def test_new_raid_notifies_everyone_else(app):
    leader, friend = player('Leader'), player('Friend')
    social.create_raid(leader, 'Read 1000 pages', 'pages', 1000, 30, 'INT')
    assert [n.player_id for n in Notification.query] == [friend.id]


def test_contributions_complete_raid_and_reward_contributors(app):
    a, b, bystander = player('A', xp_required=10_000), player('B', xp_required=10_000), player('C')
    raid, _ = social.create_raid(a, 'Run 100 km', 'km', 100, 30, 'STR')
    assert social.contribute(a, raid, 40)[1].startswith('LOGGED: +40 km · 40/100 (40%)')
    assert raid.status == 'active' and a.xp == 0  # individual logs earn no XP
    ok, msg = social.contribute(b, raid, 70)
    assert ok and 'RAID CLEARED' in msg and raid.status == 'completed'
    for p in (a, b):
        db.session.refresh(p)
        assert (p.xp, p.coins) == (social.RAID_REWARD_XP, social.RAID_REWARD_COINS)
        assert league.weekly_points(p.id, league.week_start_for()) == 50.0
    assert db.session.get(Player, bystander.id).xp == 0
    assert ActivityEvent.query.filter_by(kind='effort', stat='STR').count() == 2  # Life Balance credit
    assert social.contribute(a, raid, 5) == (False, "This raid is no longer active.")


def test_raid_rejects_bad_amounts_and_expires(app):
    p = player('P')
    raid, _ = social.create_raid(p, 'Swim', 'laps', 50, 1)
    assert social.contribute(p, raid, 0)[0] is False
    social.contribute(p, raid, 10)
    raid.ends_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.session.commit()
    expired = social.finalize_expired_raids()
    assert expired == [raid] and raid.status == 'failed'
    assert 'RAID FAILED' in Notification.query.filter_by(player_id=p.id).first().message


def test_cancel_rules(app):
    leader, friend = player('Leader'), player('Friend')
    raid, _ = social.create_raid(leader, 'Steps', 'k', 500, 10)
    assert social.cancel_raid(friend, raid)[0] is False
    social.contribute(friend, raid, 5)
    assert 'already contributed' in social.cancel_raid(leader, raid)[1]
    solo, _ = social.create_raid(leader, 'Solo', 'k', 5, 3)
    social.contribute(leader, solo, 1)
    assert social.cancel_raid(leader, solo)[0] and solo.status == 'cancelled'


def test_raid_pages_and_routes(auth_client, app, csrf_token):
    page = auth_client.get('/raids').data
    assert b'RAIDS' in page and b'No active raids' in page
    r = auth_client.post('/raids/new', data={'title': 'Run 100 km', 'unit': 'km', 'target': '100', 'days': '30',
                                             'stat': 'STR', 'csrf_token': csrf_token}, follow_redirects=True)
    assert b'RAID STARTED' in r.data and b'CONTRIBUTE' in r.data
    raid = Raid.query.one()
    page = auth_client.post(f'/raids/{raid.id}/log', data={'amount': '12.5', 'csrf_token': csrf_token},
                            follow_redirects=True).data
    assert b'LOGGED: +12.5 km' in page and b'AuthUser' in page
    assert b'Run 100 km' in auth_client.get('/').data  # dashboard ACTIVE RAIDS panel
    assert b'Target and duration must be numbers' in auth_client.post(
        '/raids/new', data={'title': 'x', 'unit': 'x', 'target': 'a', 'days': '1', 'csrf_token': csrf_token},
        follow_redirects=True).data
    assert b'Raid not found' in auth_client.get('/raids/999', follow_redirects=True).data


def test_deleting_a_raid_creator_keeps_the_raid(app):
    leader, friend = player('Leader'), player('Friend')
    raid, _ = social.create_raid(leader, 'Steps', 'k', 500, 10)
    social.contribute(friend, raid, 5)
    db.session.delete(leader); db.session.commit()
    raid = db.session.get(Raid, raid.id)
    assert raid.created_by is None and raid.total == 5


# --- kudos ---

def _s_rank_clear(p, title='Marathon'):
    q = Quest(title=title, rank='S', player=p, xp_reward=0)
    db.session.add(q); db.session.commit()
    S.process_quest_completion(p, q)
    return ActivityEvent.query.filter_by(player_id=p.id, kind='effort', rank='S').one()


def test_hall_of_feats_lists_recent_s_ranks(app):
    p = player('Hero')
    _s_rank_clear(p)
    daily = Quest(title='Daily S', rank='S', is_daily=True, player=p); db.session.add(daily); db.session.commit()
    S.process_quest_completion(p, daily)
    feats = social.recent_feats()
    assert [(f['player'].name, f['title']) for f in feats] == [('Hero', 'Marathon')]


def test_kudos_give_change_remove_and_notify(app):
    hero, fan = player('Hero'), player('Fan')
    event = _s_rank_clear(hero)
    ok, msg = social.give_kudos(fan, event, '🔥')
    assert ok and Kudos.query.one().emoji == '🔥'
    assert '🔥 Fan cheered your S-rank: Marathon' in Notification.query.filter_by(player_id=hero.id).one().message
    assert social.give_kudos(fan, event, '👑')[1] == 'Changed to 👑.'
    assert social.give_kudos(fan, event, '👑')[1] == 'Kudos removed.' and Kudos.query.count() == 0
    assert social.give_kudos(hero, event, '🔥')[1] == "You can't give kudos to yourself."
    assert social.give_kudos(fan, event, '💩')[1] == 'Unknown reaction.'
    other = ActivityEvent(player_id=hero.id, kind='effort', rank='B', week_start=league.week_start_for())
    db.session.add(other); db.session.commit()
    assert social.give_kudos(fan, other, '🔥')[1] == 'You can only cheer S-rank clears.'


def test_kudos_route_and_leaderboard_feed(auth_client, app, csrf_token):
    hero = player('Hero')
    event = _s_rank_clear(hero, 'Ironman')
    auth_client.post(f'/kudos/{event.id}', data={'emoji': '💪', 'csrf_token': csrf_token})
    page = auth_client.get('/leaderboard').data.decode()
    assert 'HALL OF FEATS' in page and 'Ironman' in page
    assert 'kudos-btn mine' in page and '💪 1' in page


def test_deleting_a_hero_removes_their_feats_and_kudos(app):
    hero, fan = player('Hero'), player('Fan')
    social.give_kudos(fan, _s_rank_clear(hero), '🔥')
    db.session.delete(hero); db.session.commit()
    assert Kudos.query.count() == 0 and social.recent_feats() == []


# --- installable app ---

def test_manifest_offline_page_and_icons(client, app):
    r = client.get('/manifest.webmanifest')
    assert r.mimetype == 'application/manifest+json'
    m = json.loads(r.data)
    assert m['display'] == 'standalone' and m['start_url'] == '/'
    sizes = {(i['sizes'], i['purpose']) for i in m['icons']}
    assert {('192x192', 'any'), ('512x512', 'any'), ('512x512', 'maskable')} <= sizes
    static = os.path.join(app.root_path, 'static')
    for icon in m['icons']:
        assert os.path.exists(os.path.join(static, icon['src'].split('/static/')[1]))
    for extra in ('apple-touch-icon.png', 'badge-72.png', 'favicon-32.png'):
        assert os.path.exists(os.path.join(static, 'icons', extra))
    assert b'NO SIGNAL' in client.get('/offline').data
    sw = client.get('/service-worker.js')
    assert b"OFFLINE_URL = '/offline'" in sw.data and b'badge-72.png' in sw.data
    sw.close()
    login = client.get('/login').data
    assert b'rel="manifest"' in login and b'apple-touch-icon' in login


# --- icons ---

def test_icon_helper_and_sprite(app):
    from flask import render_template_string
    with app.test_request_context():
        out = render_template_string("{{ icon('skull') }}")
        assert out == ('<svg class="icon icon-skull " aria-hidden="true" focusable="false">'
                       '<use href="/static/icons/sprite.svg#i-skull"></use></svg>')
        labelled = render_template_string("{{ icon('crown', 'icon-gold', label='Leader <1>') }}")
        assert 'role="img" aria-label="Leader &lt;1&gt;"' in labelled and 'icon-gold' in labelled
        with pytest.raises(ValueError, match="Unknown icon 'nope'"):
            render_template_string("{{ icon('nope') }}")
    static = os.path.join(app.root_path, 'static', 'icons')
    assert os.path.exists(os.path.join(static, 'LUCIDE_LICENSE.txt'))
    assert 'ISC' in open(os.path.join(static, 'sprite.svg')).readline()


def test_pages_render_icons_not_emojis(auth_client, app):
    import re
    pictorial = re.compile('[\U0001F300-\U0001FAFF]')
    page = auth_client.get('/').data.decode()
    assert '#i-coins' in page and '#i-bell' in page
    # The dashboard body no longer uses pictorial emojis (tooltips/titles may still describe them)
    visible = re.sub(r'title="[^"]*"', '', page)
    for kudos in social.KUDOS_EMOJI:  # reactions intentionally stay emojis (also listed in the Guide)
        visible = visible.replace(kudos, '')
    assert not pictorial.search(visible), pictorial.findall(visible)[:5]
