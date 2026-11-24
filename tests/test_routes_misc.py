"""Remaining routes: focus, setup, vacation, analytics, leaderboard/profile/log, notifications & push API,
settings, sleep tracking, class selection, auth edge cases."""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import (Player, Quest, Notification, PushSubscription, DailySnapshot)

from .utils import get_csrf_from_response


def me():
    db.session.expire_all()
    return Player.query.filter_by(name="AuthUser").first()


def hdr(token):
    return {'X-CSRFToken': token}


# --- focus ---

def test_focus_page_renders(auth_client):
    assert b'CONFIGURE PROTOCOL' in auth_client.get('/focus').data


def test_focus_complete_validation(auth_client, csrf_token):
    assert auth_client.post('/focus_complete', json={'minutes': 'x'}, headers=hdr(csrf_token)).get_json()['msg'] == 'Invalid duration.'
    assert auth_client.post('/focus_complete', json={'minutes': 0}, headers=hdr(csrf_token)).get_json()['msg'] == 'Too short.'
    # Empty / non-object body must not crash
    assert auth_client.post('/focus_complete', data='[]', content_type='application/json', headers=hdr(csrf_token)).get_json()['msg'] == 'Too short.'


def test_focus_complete_rewards_and_popup(auth_client, app, csrf_token):
    p = me(); p.xp_required = 1000; db.session.commit()
    r = auth_client.post('/focus_complete', json={'minutes': 60}, headers=hdr(csrf_token)).get_json()
    assert r['success'] and r['msg'] == 'FOCUS COMPLETE: 60m. +10 Coins, +600 XP.'  # 600 XP / hour
    p = me()
    assert (p.coins, p.xp, p.daily_focus_duration) == (10, 600, 60)
    assert b'FOCUS COMPLETE: 60m' in auth_client.get('/').data  # popup on next page


def test_focus_complete_can_level_up(auth_client, app, csrf_token):
    p = me(); p.xp = 99; p.xp_required = 100; db.session.commit()
    auth_client.post('/focus_complete', json={'minutes': 10}, headers=hdr(csrf_token))  # +100 XP
    assert me().level == 2
    assert b'data-category="levelup">2|1|NEXT: Job Change Trial at LV 10 (8 levels away)<' in auth_client.get('/').data


# --- onboarding ---

def test_setup_flow(auth_client, app, csrf_token):
    p = me(); p.setup_complete = False; db.session.commit()
    assert auth_client.get('/').headers['Location'].endswith('/setup')
    assert b'INITIALIZE SYSTEM' in auth_client.get('/setup').data

    page = auth_client.post('/setup', data={'quest1': 'A', 'csrf_token': csrf_token}).data
    assert b'ALL PARAMETERS REQUIRED' in page

    form = {f'quest{i}': f'Daily {i}' for i in range(1, 5)}
    form.update({'quest1_rank': 'd', 'quest2_stat': 'SEN', 'penalty': '50 Burpees', 'penalty_detail': 'No breaks',
                 'csrf_token': csrf_token})
    auth_client.post('/setup', data=form)
    p = me()
    dailies = Quest.query.filter_by(player_id=p.id, is_daily=True).order_by(Quest.id).all()
    assert len(dailies) == 4 and dailies[0].rank == 'D' and dailies[1].stat_reward == 'SNS'
    assert p.setup_complete and p.penalty_description == '50 Burpees' and p.penalty_detail == 'No breaks'

    page = auth_client.get('/setup', follow_redirects=True).data
    assert b'System already initialized' in page


# --- vacation ---

def test_vacation_routes(auth_client, app, csrf_token):
    page = auth_client.post('/vacation/end', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'You are not on vacation' in page
    page = auth_client.post('/vacation/start', data={'days': '99', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'1-30 days' in page
    page = auth_client.post('/vacation/start', data={'days': 'abc', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'1-30 days' in page

    page = auth_client.post('/vacation/start', data={'days': '7', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'VACATION ACTIVATED' in page and me().is_on_vacation
    auth_client.post('/vacation/end', data={'csrf_token': csrf_token})
    assert not me().is_on_vacation
    page = auth_client.post('/vacation/start', data={'days': '3', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'MONTHLY LIMIT EXCEEDED' in page


# --- read-only pages ---

def test_analytics_with_and_without_snapshots(auth_client, app):
    assert auth_client.get('/analytics').status_code == 200
    p = me()
    db.session.add(DailySnapshot(player_id=p.id, date=datetime.now(timezone.utc).date() - timedelta(days=1),
                                 level=1, xp=0, total_stats=42, quests_completed=3))
    db.session.commit()
    page = auth_client.get('/analytics').data
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat().encode()
    assert yesterday in page and b'42' in page


def test_leaderboard_profile_and_log(auth_client, app):
    p = me()
    db.session.add(Quest(title='Done Thing', player=p, is_completed=True, completed_at=datetime.now(timezone.utc)))
    db.session.commit()
    assert b'AuthUser' in auth_client.get('/leaderboard').data
    assert b'AuthUser' in auth_client.get(f'/profile/{p.id}').data
    assert b'Player not found' in auth_client.get('/profile/9999', follow_redirects=True).data
    assert b'Done Thing' in auth_client.get('/log').data


def test_unauthenticated_pages_redirect_to_login(client):
    for url in ('/', '/shop', '/inventory', '/analytics', '/api/notifications/all'):
        r = client.get(url)
        assert r.status_code == 302 and '/login' in r.headers['Location'], url


# --- notifications API ---

def test_notification_api(auth_client, app, csrf_token):
    p = me()
    other = Player(name='Stranger'); db.session.add(other); db.session.commit()
    n1 = Notification(player_id=p.id, message='one'); n2 = Notification(player_id=p.id, message='two')
    theirs = Notification(player_id=other.id, message='not yours')
    db.session.add_all([n1, n2, theirs]); db.session.commit()

    data = auth_client.get('/api/notifications/all').get_json()
    assert {n['message'] for n in data} == {'one', 'two'}

    auth_client.post('/api/notifications/mark_read', json={'ids': [n1.id, theirs.id, 'junk']}, headers=hdr(csrf_token))
    db.session.expire_all()
    assert n1.is_read and not n2.is_read and not theirs.is_read
    assert auth_client.post('/api/notifications/mark_read', json={'ids': 'nope'}, headers=hdr(csrf_token)).get_json()['success']

    auth_client.post('/api/notifications/mark_read_all', headers=hdr(csrf_token))
    db.session.expire_all()
    assert n2.is_read and not theirs.is_read

    auth_client.post('/api/notifications/clear', headers=hdr(csrf_token))
    assert Notification.query.filter_by(player_id=p.id).count() == 0
    assert Notification.query.filter_by(player_id=other.id).count() == 1


# --- web push API ---

SUB = {'endpoint': 'https://push.example/abc', 'keys': {'p256dh': 'key', 'auth': 'secret'}}


def test_push_subscribe_validation(auth_client, csrf_token):
    for bad in ({}, {'endpoint': 'x'}, {'endpoint': 'x', 'keys': 'nope'}, {'endpoint': 'x', 'keys': {'p256dh': 'k'}}):
        assert auth_client.post('/api/notifications/subscribe', json=bad, headers=hdr(csrf_token)).status_code == 400


def test_push_subscribe_and_rebind(auth_client, app, csrf_token):
    assert auth_client.post('/api/notifications/subscribe', json=SUB, headers=hdr(csrf_token)).get_json()['success']
    sub = PushSubscription.query.one()
    assert sub.player_id == me().id
    # Same device endpoint registered by another account moves to the current user
    other = Player(name='PrevOwner'); db.session.add(other); db.session.commit()
    sub.player_id = other.id; db.session.commit()
    auth_client.post('/api/notifications/subscribe', json=SUB, headers=hdr(csrf_token))
    db.session.expire_all()
    assert PushSubscription.query.one().player_id == me().id


def test_push_unsubscribe(auth_client, app, csrf_token):
    assert auth_client.post('/api/notifications/unsubscribe', json={}, headers=hdr(csrf_token)).status_code == 400
    assert auth_client.post('/api/notifications/unsubscribe', json={'endpoint': 'nope'}, headers=hdr(csrf_token)).status_code == 404

    other = Player(name='Owner'); db.session.add(other); db.session.commit()
    db.session.add(PushSubscription(player_id=other.id, endpoint='https://push.example/other', p256dh='k', auth='a'))
    db.session.commit()
    # Cannot remove someone else's subscription
    assert auth_client.post('/api/notifications/unsubscribe', json={'endpoint': 'https://push.example/other'},
                            headers=hdr(csrf_token)).status_code == 404

    auth_client.post('/api/notifications/subscribe', json=SUB, headers=hdr(csrf_token))
    r = auth_client.post('/api/notifications/unsubscribe', json={'endpoint': SUB['endpoint']}, headers=hdr(csrf_token))
    assert r.get_json()['success']
    assert PushSubscription.query.count() == 1


def test_service_worker_and_vapid_key(client, monkeypatch):
    r = client.get('/service-worker.js')
    assert r.status_code == 200 and r.mimetype == 'application/javascript'
    r.close()
    monkeypatch.setenv('VAPID_PUBLIC_KEY', 'PUBKEY')
    assert client.get('/api/vapid_public_key').get_json() == {'public_key': 'PUBKEY'}


# --- settings & sleep ---

def test_update_settings(auth_client, app, csrf_token):
    r = auth_client.post('/update_settings', json={'audio': False, 'music': False, 'volume': '0.2', 'popups': 0},
                         headers=hdr(csrf_token))
    assert r.get_json()['success']
    p = me()
    assert (p.settings_audio, p.settings_music, p.settings_volume, p.settings_popups) == (False, False, 0.2, False)


def test_popups_off_turns_system_popups_into_toasts(auth_client, app):
    p = me(); p.settings_popups = False; db.session.commit()
    page = auth_client.get('/').data
    assert b'window.popupsEnabled = false' in page


def test_track_sleep_conditions(auth_client, app, csrf_token):
    for hours, condition, streak in (('8', 'WELL RESTED', 1), ('6.5', 'NORMAL', 1), ('4', 'TIRED', 0)):
        p = me(); p.last_sleep_log_date = None; db.session.commit()
        auth_client.post('/track_sleep', data={'hours': hours, 'csrf_token': csrf_token})
        p = me()
        assert (p.condition, p.sleep_streak) == (condition, streak), hours


# --- class selection ---

def test_job_qualification_guards(auth_client, app):
    page = auth_client.get('/job_qualification', follow_redirects=True).data
    assert b'Level 10 Required' in page
    p = me(); p.job_class = 'Mage'; db.session.commit()
    page = auth_client.get('/job_qualification', follow_redirects=True).data
    assert b'already chosen a path' in page
    assert auth_client.get('/job_test').status_code == 302


# --- dashboard ---

def test_dashboard_runs_daily_reset(auth_client, app):
    p = me(); p.last_daily_reset = datetime.now(timezone.utc) - timedelta(days=2); db.session.commit()
    page = auth_client.get('/').data
    assert b'DAILY RESET' in page


# --- auth edge cases ---

def _register(client, token, name, pw, confirm=None):
    return client.post('/register', data={'username': name, 'password': pw, 'confirm': pw if confirm is None else confirm,
                                          'csrf_token': token}, follow_redirects=True).data


def test_register_errors(client, app, csrf_token):
    assert b'Passwords do not match' in _register(client, csrf_token, 'Hunter', 'a', 'b')
    assert b'Password required' in _register(client, csrf_token, 'Hunter', '')
    assert b'1-50 characters' in _register(client, csrf_token, 'x' * 51, 'pw')
    assert b'Registration Complete' in _register(client, csrf_token, '  Hunter  ', 'pw')
    assert Player.query.filter_by(name='Hunter').count() == 1  # name was trimmed
    assert b'already taken' in _register(client, csrf_token, 'Hunter', 'pw')


def test_login_errors_and_logged_in_redirects(client, app, csrf_token):
    p = Player(name='Known'); p.set_password('right'); db.session.add(p); db.session.commit()
    page = client.post('/login', data={'username': 'Known', 'password': 'wrong', 'csrf_token': csrf_token}).data
    assert b'Invalid Credentials' in page
    page = client.post('/login', data={'username': 'Nobody', 'password': 'x', 'csrf_token': csrf_token}).data
    assert b'Invalid Credentials' in page

    client.post('/login', data={'username': 'Known', 'password': 'right', 'csrf_token': csrf_token})
    assert client.get('/login').status_code == 302
    assert client.get('/register').status_code == 302


def test_login_requires_csrf_token(client, app):
    p = Player(name='Known'); p.set_password('right'); db.session.add(p); db.session.commit()
    r = client.post('/login', data={'username': 'Known', 'password': 'right'})
    assert r.status_code == 400


def test_delete_account(auth_client, app):
    token = get_csrf_from_response(auth_client.get('/'))
    page = auth_client.post('/delete_account', data={'csrf_token': token}, follow_redirects=True).data
    assert b'Account Deleted' in page
    assert Player.query.filter_by(name='AuthUser').count() == 0
