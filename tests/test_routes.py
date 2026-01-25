import pytest
from app.models import Player, Quest, RewardItem
from app.extensions import db

@pytest.fixture
def auth_client(client, app):
    """Register and login a user."""
    with app.app_context():
        # Create a user in the DB
        u = Player(name="AuthUser")
        u.set_password("password")
        u.gold = 100 
        db.session.add(u)
        db.session.commit()
    
    # Login via route
    client.post('/login', data={'username': 'AuthUser', 'password': 'password'})
    return client

def test_dashboard_access(auth_client):
    """Test that the dashboard loads correctly."""
    response = auth_client.get('/')
    assert response.status_code == 200
    assert b"SYSTEM INTERFACE" in response.data

def test_add_quest(auth_client, app):
    """Test adding a new quest."""
    response = auth_client.post('/add_quest', data={
        'title': 'New Quest',
        'rank': 'C',
        'stat': 'STR'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    
    with app.app_context():
        quest = Quest.query.filter_by(title='New Quest').first()
        assert quest is not None
        assert quest.rank == 'C'

def test_complete_quest(auth_client, app):
    """Test completing a quest gives XP."""
    with app.app_context():
        # Setup quest
        auth_user = Player.query.filter_by(name="AuthUser").first()
        quest = Quest(title="Task", xp_reward=50, player=auth_user)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id
    
    # Action
    response = auth_client.post(f'/complete/{quest_id}', follow_redirects=True)
    assert response.status_code == 200
    
    # Assert
    with app.app_context():
        player = Player.query.filter_by(name="AuthUser").first()
        assert player.xp == 50
        
        quest = db.session.get(Quest, quest_id)
        assert quest.is_completed

def test_buy_item_success(client, app):
    """Test buying an item with enough gold."""
    with app.app_context():
        user = Player(name="RichBuyer", gold=200)
        user.set_password("pass")
        db.session.add(user)
        # Stock = 1 (Finite)
        item = RewardItem(name="Potion", cost=50, stock=1)
        db.session.add(item)
        db.session.commit()
        item_id = item.id
        
    client.post('/login', data={'username': 'RichBuyer', 'password': 'pass'})
        
    response = client.get(f'/buy/{item_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b"Purchased: Potion" in response.data
    
    with app.app_context():
        user = Player.query.filter_by(name="RichBuyer").first()
        assert user.gold == 150
        item = db.session.get(RewardItem, item_id)
        assert item.stock == 0

def test_buy_item_insufficient_funds(client, app):
    """Test buying an item without enough gold."""
    with app.app_context():
        p = Player(name="PoorUser")
        p.set_password("pass")
        p.gold = 0
        db.session.add(p)

        item = RewardItem(name="Luxury", cost=1000)
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    client.post('/login', data={'username': 'PoorUser', 'password': 'pass'})

    response = client.get(f'/buy/{item_id}', follow_redirects=True)
    assert response.status_code == 200
    # Should verify stock didn't change (still -1) and funds still 0
    with app.app_context():
        item = db.session.get(RewardItem, item_id)
        assert item.stock == -1

def test_abandon_page_load(auth_client, app):
    """Test accessing the abandon page."""
    with app.app_context():
        # Setup
        user = Player.query.filter_by(name="AuthUser").first()
        quest = Quest(title="To Abandon", rank="E", player=user)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id
        
    response = auth_client.get(f'/delete_quest/{quest_id}')
    assert response.status_code == 200
    assert b"ABANDON QUEST" in response.data

def test_abandon_success(auth_client, app):
    """Test actually deleting the quest (paying penalty)."""
    with app.app_context():
        user = Player.query.filter_by(name="AuthUser").first()
        user.gold = 100 
        quest = Quest(title="To Delete", rank="E", player=user)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id
        
    # POST to confirm deletion
    response = auth_client.post(f'/delete_quest/{quest_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b"Quest Abandoned" in response.data
    
    with app.app_context():
        assert db.session.get(Quest, quest_id) is None
        user = Player.query.filter_by(name="AuthUser").first()
        assert user.gold == 90 # 100 - 10

def test_abandon_prescreen_rich(auth_client, app):
    """Test accessing abandon page WITH enough gold."""
    with app.app_context():
        user = Player.query.filter_by(name="AuthUser").first()
        user.gold = 100
        quest = Quest(title="To Keep", rank="C", player=user)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id
        
    response = auth_client.get(f'/delete_quest/{quest_id}')
    assert response.status_code == 200
    assert b"ABANDON QUEST" in response.data

def test_abandon_prescreen_poor(client, app):
    """Test accessing abandon page WITHOUT enough gold (Should redirect)."""
    with app.app_context():
        user = Player(name="PoorUserPrescreen")
        user.set_password("pass")
        user.gold = 10 
        db.session.add(user)
        
        quest = Quest(title="To Keep", rank="C", player=user)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id
        
    client.post('/login', data={'username': 'PoorUserPrescreen', 'password': 'pass'})
        
    response = client.get(f'/delete_quest/{quest_id}', follow_redirects=True)
    assert response.status_code == 200
    # Should be back on dashboard
    assert b"SYSTEM INTERFACE" in response.data
    # Should see the error flash/modal message
    assert b"INSUFFICIENT FUNDS" in response.data

def test_abandon_insufficient_funds(client, app):
    """Test POSTing to delete without enough gold (Hacking attempt)."""
    with app.app_context():
        user = Player(name="PoorHacker", gold=0)
        user.set_password("pass")
        db.session.add(user)
        
        quest = Quest(title="To Keep", rank="E", player=user)
        db.session.add(quest)
        db.session.commit()
        quest_id = quest.id
        
    client.post('/login', data={'username': 'PoorHacker', 'password': 'pass'})
        
    response = client.post(f'/delete_quest/{quest_id}', follow_redirects=True)
    assert response.status_code == 200
    # Using shorter substring to avoid mismatch logic
    assert b"You cannot afford" in response.data
    
    with app.app_context():
        assert db.session.get(Quest, quest_id) is not None
