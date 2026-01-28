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

def test_categorization_helpers(app):
    """Test any helper logic for sorting tasks (if moved to model/service)."""
    # This might be tested via integration in routes, but good to keep in mind.
    pass
