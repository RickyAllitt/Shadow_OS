import pytest
from app import create_app
from app.extensions import db
from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use in-memory DB for tests
    WTF_CSRF_ENABLED = True # Enable CSRF to replicate production environment

@pytest.fixture
def app():
    app = create_app(TestConfig)
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

from .utils import get_csrf_from_response
from app.models import Player

@pytest.fixture
def auth_client(client, app):
    """Register and login a user."""
    with app.app_context():
        # Create a user in the DB
        u = Player(name="AuthUser", setup_complete=True)
        u.set_password("password")
        u.gold = 100 
        db.session.add(u)
        db.session.commit()
    
    # Login via route
    resp = client.get('/login')
    token = get_csrf_from_response(resp)
    client.post('/login', data={'username': 'AuthUser', 'password': 'password', 'csrf_token': token})
    return client

@pytest.fixture
def csrf_token(client):
    """Provides a valid CSRF token by fetching the dashboard (post-login usually)."""
    # Try dashboard first
    response = client.get('/')
    token = get_csrf_from_response(response)
    if token:
        return token
    # Fallback to login page
    response = client.get('/login')
    return get_csrf_from_response(response)
