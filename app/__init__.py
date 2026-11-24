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
    csrf.init_app(app)
    
    # Background jobs: started here so they run however the app is launched (gunicorn, run.py, flask run).
    # One process per machine runs them (file lock); disabled in tests and with SCHEDULER_ENABLED=0.
    from .extensions import scheduler
    from .tasks import register_background_jobs
    register_background_jobs(app, scheduler)

    login_manager.login_view = 'auth.login'

    register_template_filters(app)

    # Register Blueprints
    from .routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from .routes.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    return app


def _sprite_icon_names(app):
    import os
    import re
    path = os.path.join(app.static_folder, 'icons', 'sprite.svg')
    with open(path, encoding='utf-8') as f:
        return frozenset(re.findall(r'<symbol id="i-([a-z0-9-]+)"', f.read()))


def register_template_filters(app):
    """Datetime helpers for values stored as naive UTC (e.g. penalty deadlines), plus icon()."""
    from flask import url_for
    from markupsafe import Markup, escape

    icon_names = _sprite_icon_names(app)

    @app.template_global('icon')
    def icon(name, cls='', label=None):
        """
        Inline SVG icon from static/icons/sprite.svg (Lucide). Sized to the text (1em) and coloured
        with currentColor. Decorative by default; pass label= for icons that carry meaning alone.
        """
        if name not in icon_names:
            raise ValueError(f"Unknown icon '{name}'. Add it to scripts/build_icon_sprite.py and rebuild.")
        href = url_for('static', filename='icons/sprite.svg') + f'#i-{name}'
        a11y = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true" focusable="false"'
        return Markup(f'<svg class="icon icon-{name} {escape(cls)}" {a11y}><use href="{href}"></use></svg>')

    from datetime import timezone
    from app.services import GAME_TIMEZONE

    def _as_utc(dt):
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)

    @app.template_filter('utc_iso')
    def utc_iso(dt):
        """ISO string with an explicit UTC offset, so browsers don't read it as local time."""
        return _as_utc(dt).isoformat() if dt else ''

    @app.template_filter('gate_time')
    def gate_time(dt, left=False):
        """Gate deadlines: 'Sun 01:00' in the viewer's timezone, or time remaining ('2d 5h')."""
        from datetime import datetime
        if not dt:
            return ''
        if left:
            from app.progression import format_wait
            delta = _as_utc(dt) - datetime.now(timezone.utc)
            return format_wait(delta) if delta.total_seconds() > 0 else '0h'
        return game_time(dt, '%a %H:%M')

    @app.template_filter('game_time')
    def game_time(dt, fmt='%d/%m %H:%M'):
        """Naive-UTC datetime shown in the viewer's timezone (GAME_TIMEZONE when logged out)."""
        from flask_login import current_user
        from app.services import player_tz
        tz = player_tz(current_user) if getattr(current_user, 'is_authenticated', False) else GAME_TIMEZONE
        return _as_utc(dt).astimezone(tz).strftime(fmt) if dt else ''
