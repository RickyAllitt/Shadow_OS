from flask import Flask
from config import Config
from .extensions import db

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    from .extensions import login_manager, csrf
    login_manager.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    from .extensions import scheduler
    try:
        scheduler.init_app(app)
        if not scheduler.running:
            scheduler.start()
    except Exception:
        # Scheduler might be already running during tests
        pass
    
    login_manager.login_view = 'auth.login'

    # Register Blueprints
    from .routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from .routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    return app
