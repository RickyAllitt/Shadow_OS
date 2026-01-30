from app.models import Player
from app.extensions import db

def test_password_hashing(app):
    """Test that passwords are hashed and salted."""
    with app.app_context():
        u = Player(name="SecureUser")
        u.set_password("secret")
        
        assert u.password_hash is not None
        assert u.password_hash != "secret"
        assert u.salt is not None
        assert u.check_password("secret")
        assert not u.check_password("wrong")

def test_login_flow(client, app, csrf_token):
    """Test registration and login."""
    # Register
    response = client.post('/register', data={
        'username': 'NewHunter',
        'password': 'password123',
        'confirm': 'password123',
        'csrf_token': csrf_token
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Registration Complete" in response.data
    
    # Login
    response = client.post('/login', data={
        'username': 'NewHunter',
        'password': 'password123',
        'csrf_token': csrf_token
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"System Access Granted" in response.data
    
    # Access Dashboard (Redirects to Setup)
    response = client.get('/', follow_redirects=True)
    assert response.status_code == 200
    assert b"INITIALIZE SYSTEM" in response.data
    
    # Logout
    response = client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b"System Access Terminated" in response.data
