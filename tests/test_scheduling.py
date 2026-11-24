import pytest
from app.models import Player, Quest
from app.extensions import db
from app.services import check_daily_reset
from datetime import datetime, timedelta

def test_quest_dates(app):
    """Test assigning start and end dates to a quest."""
    with app.app_context():
        user = Player(name="DateTester")
        db.session.add(user)
        db.session.commit()
        
        start = datetime.now()
        end = datetime.now() + timedelta(days=1)
        
        quest = Quest(title="Dated Task", player=user, start_date=start, due_date=end)
        db.session.add(quest)
        db.session.commit()
        
        q = Quest.query.first()
        assert q.start_date is not None
        assert q.due_date is not None

def test_daily_reset_logic(app):
    """Test that daily quests un-complete after reset."""
    with app.app_context():
        # Setup: Player with a completed daily quest yesterday
        user = Player(name="DailyTester")
        # Reset happened 2 days ago
        user.last_daily_reset = datetime.now() - timedelta(days=2) 
        db.session.add(user)
        db.session.commit()
        
        quest = Quest(title="Daily Routine", player=user, is_daily=True, is_completed=True)
        db.session.add(quest)
        db.session.commit()
        
        # Action: Check reset
        was_reset, msgs = check_daily_reset(user)
        
        assert was_reset is True
        
        # Verify quest is un-completed
        q = db.session.get(Quest, quest.id)
        assert q.is_completed is False
        
        # Verify simple quest is NOT un-completed
        quest2 = Quest(title="One Time", player=user, is_daily=False, is_completed=True)
        db.session.add(quest2)
        db.session.commit()
        
        # Trigger reset again (force time travel hack or just check logic isolation)
        # Re-verify daily logic doesn't touch non-dailies.
        # Since we just reset, let's pretend we reset again for a new day
        user.last_daily_reset = datetime.now() - timedelta(days=2)
        check_daily_reset(user)
        
        q2 = db.session.get(Quest, quest2.id)
        assert q2.is_completed is True # Should stay completed

from app.services import (
    check_daily_reset, check_weekly_reset, get_latest_daily_reset_time,
    GAME_TIMEZONE, RESET_HOUR, _check_and_apply_daily_bonus
)
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

def test_get_latest_daily_reset_time():
    """Verify get_latest_daily_reset_time correctly calculates 1:00 AM boundary."""
    # Before 1:00 AM (e.g. 00:30 on Sept 10) -> latest reset was Sept 9 at 01:00
    dt_before = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 0, 30))
    latest_before = get_latest_daily_reset_time(dt_before)
    assert latest_before.year == 2026
    assert latest_before.month == 9
    assert latest_before.day == 9
    assert latest_before.hour == RESET_HOUR
    assert latest_before.minute == 0

    # Exactly 1:00 AM (01:00 on Sept 10) -> latest reset is Sept 10 at 01:00
    dt_at = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 1, 0))
    latest_at = get_latest_daily_reset_time(dt_at)
    assert latest_at.year == 2026
    assert latest_at.month == 9
    assert latest_at.day == 10
    assert latest_at.hour == RESET_HOUR

    # Afternoon (14:30 on Sept 10) -> latest reset is Sept 10 at 01:00
    dt_after = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 14, 30))
    latest_after = get_latest_daily_reset_time(dt_after)
    assert latest_after.year == 2026
    assert latest_after.month == 9
    assert latest_after.day == 10
    assert latest_after.hour == RESET_HOUR

def test_daily_reset_one_am_boundary(app):
    """Test that daily reset triggers after 1:00 AM, but not before 1:00 AM."""
    with app.app_context():
        user = Player(name="BoundaryTester")
        db.session.add(user)
        db.session.commit()

        quest = Quest(title="1AM Daily", player=user, is_daily=True, is_completed=True)
        db.session.add(quest)
        db.session.commit()

        # Set last_daily_reset to Sept 9 at 15:00 UTC (after Sept 9 1am reset)
        user.last_daily_reset = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)
        db.session.commit()

        # Simulated current time: Sept 10 at 00:30 in Madrid (which is Sept 9 22:30 UTC)
        # It is NOT 1:00 AM yet on Sept 10!
        mock_now_game = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 0, 30))
        mock_now_utc = mock_now_game.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: mock_now_utc if tz else mock_now_utc.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            reset_occurred, msgs = check_daily_reset(user)
            assert reset_occurred is False
            q = db.session.get(Quest, quest.id)
            assert q.is_completed is True # Still completed before 1am!

        # Simulated current time: Sept 10 at 01:05 in Madrid (Sept 9 23:05 UTC)
        # It IS now past 1:00 AM on Sept 10!
        mock_now_game_after = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 1, 5))
        mock_now_utc_after = mock_now_game_after.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: mock_now_utc_after if tz else mock_now_utc_after.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            reset_occurred, msgs = check_daily_reset(user)
            assert reset_occurred is True
            q = db.session.get(Quest, quest.id)
            assert q.is_completed is False # Uncompleted after 1am!

def test_weekly_reset_one_am_boundary(app):
    """Test that weekly reset occurs at Monday 1:00 AM, not Monday 00:00."""
    with app.app_context():
        user = Player(name="WeeklyBoundaryTester", gold=500)
        db.session.add(user)
        db.session.commit()

        # Last weekly reset was last week
        user.last_weekly_reset = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc) # Sunday noon
        db.session.commit()

        # Monday 2026-09-07 at 00:30 AM (before 1:00 AM)
        mon_before_1am = GAME_TIMEZONE.localize(datetime(2026, 9, 7, 0, 30))
        mon_before_utc = mon_before_1am.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: mon_before_utc if tz else mon_before_utc.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            reset_occurred = check_weekly_reset(user)
            assert reset_occurred is False
            assert user.gold == 500 # Gold not reset yet before 1am Monday!

        # Monday 2026-09-07 at 01:05 AM (after 1:00 AM)
        mon_after_1am = GAME_TIMEZONE.localize(datetime(2026, 9, 7, 1, 5))
        mon_after_utc = mon_after_1am.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: mon_after_utc if tz else mon_after_utc.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            reset_occurred = check_weekly_reset(user)
            assert reset_occurred is True
            assert user.gold == 250 # Gold halved at 1am Monday (500 -> 250)

def test_daily_bonus_one_am_boundary(app):
    """Test that daily bonus eligibility refreshes at 1:00 AM."""
    with app.app_context():
        user = Player(name="BonusBoundaryTester")
        db.session.add(user)
        db.session.commit()

        d1 = Quest(title="Daily1", player=user, is_daily=True, is_completed=True)
        db.session.add(d1)
        db.session.commit()

        # Step 1: User claims daily bonus on Sept 9 at 23:30 Madrid (Sept 9 21:30 UTC)
        t1_game = GAME_TIMEZONE.localize(datetime(2026, 9, 9, 23, 30))
        t1_utc = t1_game.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: t1_utc if tz else t1_utc.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            applied = _check_and_apply_daily_bonus(user)
            assert applied is True
            assert user.last_daily_bonus is not None

        # Step 2: At Sept 10 at 00:30 Madrid (still before 1:00 AM), bonus cannot be claimed again
        t2_game = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 0, 30))
        t2_utc = t2_game.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: t2_utc if tz else t2_utc.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            applied = _check_and_apply_daily_bonus(user)
            assert applied is False

        # Step 3: At Sept 10 at 01:05 Madrid (after 1:00 AM), new cycle starts, bonus CAN be claimed!
        t3_game = GAME_TIMEZONE.localize(datetime(2026, 9, 10, 1, 5))
        t3_utc = t3_game.astimezone(timezone.utc)

        with patch('app.services.datetime') as mock_dt:
            mock_dt.now.side_effect = lambda tz=None: t3_utc if tz else t3_utc.replace(tzinfo=None)
            mock_dt.combine = datetime.combine
            mock_dt.min = datetime.min

            applied = _check_and_apply_daily_bonus(user)
            assert applied is True


