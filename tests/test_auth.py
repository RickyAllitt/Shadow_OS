from app.models import Player
from app.extensions import db

def test_password_hashing(app):
    """Test that passwords use a salted Werkzeug KDF hash."""
    with app.app_context():
        u = Player(name="SecureUser")
        u.set_password("secret")

        assert u.password_hash is not None
        assert u.password_hash != "secret"
        assert '$' in u.password_hash  # method$salt$hash format
        assert not u.needs_rehash()
        assert u.check_password("secret")
        assert not u.check_password("wrong")

def test_legacy_password_upgraded_on_login(client, app, csrf_token):
    """Accounts with the old SHA-256 hash can still log in and are rehashed."""
    import hashlib
    with app.app_context():
        u = Player(name="LegacyUser", setup_complete=True)
        u.salt = "abcd1234"
        u.password_hash = hashlib.sha256(("abcd1234" + "oldpass").encode()).hexdigest()
        db.session.add(u)
        db.session.commit()
        assert u.needs_rehash()
        assert not u.check_password("wrong")

    response = client.post('/login', data={
        'username': 'LegacyUser', 'password': 'oldpass', 'csrf_token': csrf_token
    }, follow_redirects=True)
    assert b"System Access Granted" in response.data

    with app.app_context():
        u = Player.query.filter_by(name="LegacyUser").first()
        assert u.salt is None
        assert not u.needs_rehash()
        assert u.check_password("oldpass")

def test_register_rejects_empty_credentials(client, app, csrf_token):
    response = client.post('/register', data={
        'username': '   ', 'password': '', 'confirm': '', 'csrf_token': csrf_token
    }, follow_redirects=True)
    assert b"Hunter name must be" in response.data
    with app.app_context():
        assert Player.query.count() == 0

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


def test_production_password_hashing_uses_scrypt(app):
    """Tests use a fast hash via PASSWORD_HASH_METHOD; real deployments keep Werkzeug's scrypt default."""
    app.config['PASSWORD_HASH_METHOD'] = None
    u = Player(name="ProdHash")
    u.set_password("secret")
    assert u.password_hash.startswith('scrypt:') and u.check_password("secret")
