from app.models import Player, Quest, RewardItem
from app.extensions import db

def test_new_player(app):
    """Test player creation with default values."""
    with app.app_context():
        player = Player(name="Test Hunter")
        db.session.add(player)
        db.session.commit()
        
        retrieved = Player.query.first()
        assert retrieved.name == "Test Hunter"
        assert retrieved.level == 1
        assert retrieved.xp == 0
        assert retrieved.condition == "Normal"

def test_quest_creation(app):
    """Test quest creation and attributes."""
    with app.app_context():
        player = Player(name="TestPlayer")
        db.session.add(player)
        db.session.commit()
        
        quest = Quest(title="Daily Pushups", rank="E", xp_reward=10, player=player)
        db.session.add(quest)
        db.session.commit()
        
        retrieved = Quest.query.first()
        assert retrieved.title == "Daily Pushups"
        assert retrieved.rank == "E"
        assert retrieved.xp_reward == 10
        assert not retrieved.is_completed

def test_shop_item(app):
    """Test shop item creation."""
    with app.app_context():
        item = RewardItem(name="Potion", cost=50, stock=5)
        db.session.add(item)
        db.session.commit()
        
        retrieved = RewardItem.query.first()
        assert retrieved.name == "Potion"
        assert retrieved.cost == 50
        assert retrieved.stock == 5
