import pytest
from app.models import Player, Quest, QuestComment
from app.extensions import db
from datetime import datetime

def test_quest_progress(app):
    """Test setting and retrieving quest progress."""
    with app.app_context():
        user = Player(name="ProgressTester")
        db.session.add(user)
        db.session.commit()
        
        quest = Quest(title="Progress Task", player=user, progress=0)
        db.session.add(quest)
        db.session.commit()
        
        # Action: Update progress
        quest.progress = 50
        db.session.commit()
        
        q = db.session.get(Quest, quest.id)
        assert q.progress == 50

def test_quest_comments(app):
    """Test adding comments to a quest."""
    with app.app_context():
        user = Player(name="CommentTester")
        db.session.add(user)
        db.session.commit()
        
        quest = Quest(title="Comment Task", player=user)
        db.session.add(quest)
        db.session.commit()
        
        # Action: Add comment
        comment = QuestComment(content="Doing great!", quest_id=quest.id)
        db.session.add(comment)
        db.session.commit()
        
        # Verify relationship (assuming backref 'comments' exists or we query directly)
        q = db.session.get(Quest, quest.id)
        assert len(q.comments) == 1
        assert q.comments[0].content == "Doing great!"
