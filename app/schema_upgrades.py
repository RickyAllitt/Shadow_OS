"""
Lightweight, idempotent schema upgrades for existing databases.

`db.create_all()` only creates missing tables; it never alters existing columns.
Anything that needs to change on a live database goes here and must be safe to
run on every startup.
"""
from sqlalchemy import inspect, or_, text

from app.extensions import db


def _widen_varchar(table, column, length):
    engine = db.engine
    dialect = engine.dialect.name
    if dialect == 'sqlite':
        return  # SQLite does not enforce VARCHAR lengths

    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    cols = {c['name']: c for c in inspector.get_columns(table)}
    col = cols.get(column)
    if col is None:
        return
    current = getattr(col['type'], 'length', None)
    if current is not None and current >= length:
        return

    if dialect == 'postgresql':
        stmt = f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE VARCHAR({length})'
    elif dialect in ('mysql', 'mariadb'):
        stmt = f'ALTER TABLE `{table}` MODIFY `{column}` VARCHAR({length})'
    else:
        print(f">> SCHEMA: Unsupported dialect '{dialect}', cannot widen {table}.{column}.")
        return

    with engine.begin() as conn:
        conn.execute(text(stmt))
    print(f">> SCHEMA: Widened {table}.{column} to VARCHAR({length}).")


def _add_column(table, column, ddl_type):
    """ALTER TABLE ... ADD COLUMN if the column is missing (SQLite, Postgres and MySQL)."""
    engine = db.engine
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return  # create_all() will build the table with every column
    if column in {c['name'] for c in inspector.get_columns(table)}:
        return
    quote = '`' if engine.dialect.name in ('mysql', 'mariadb') else '"'
    with engine.begin() as conn:
        conn.execute(text(f'ALTER TABLE {quote}{table}{quote} ADD COLUMN {quote}{column}{quote} {ddl_type}'))
    print(f">> SCHEMA: Added {table}.{column}.")


def _normalize_conditions():
    """Legacy rows used 'Healthy'/'Normal'; the game now uses NORMAL / WELL RESTED / TIRED."""
    from app.models import Player  # ORM update quotes the reserved word `condition` per dialect
    if 'player' not in inspect(db.engine).get_table_names():
        return
    count = Player.query.filter(
        or_(Player.condition.is_(None), Player.condition.in_(['Healthy', 'Normal']))
    ).update({Player.condition: 'NORMAL'}, synchronize_session=False)
    db.session.commit()
    if count:
        print(f">> SCHEMA: Normalized condition on {count} player(s).")


def _rescale_xp_to_current_curve():
    """
    When the XP curve changes, keep every player's level and their *percentage* through it.
    Idempotent: players already on the current curve are skipped.
    """
    from app.models import Player
    from app.services import calculate_xp_required
    if 'player' not in inspect(db.engine).get_table_names():
        return
    changed = 0
    for p in Player.query.all():
        new_req = calculate_xp_required(p.level or 1)
        if p.xp_required == new_req:
            continue
        old_req = p.xp_required or new_req
        progress = min(max((p.xp or 0) / old_req, 0.0), 0.999) if old_req > 0 else 0.0
        p.xp, p.xp_required = int(progress * new_req), new_req
        changed += 1
    if changed:
        db.session.commit()
        print(f">> SCHEMA: Rescaled XP for {changed} player(s) to the current level curve.")


def run_schema_upgrades():
    # Werkzeug password hashes are ~100-170 chars; the legacy column was VARCHAR(64).
    _widen_varchar('player', 'password_hash', 255)
    # Measured quests
    _add_column('quest', 'metric_target', 'FLOAT')
    _add_column('quest', 'metric_unit', 'VARCHAR(20)')
    # Life Balance / KPI fields on the activity log (for databases created mid-development)
    _add_column('activity_event', 'stat', 'VARCHAR(3)')
    _add_column('activity_event', 'units', 'FLOAT')
    _add_column('activity_event', 'value', 'FLOAT')
    _add_column('activity_event', 'quest_id', 'INTEGER')
    # Soft penalties: XP debt, streak freezes, opt-in Hardcore
    _add_column('player', 'xp_debt', 'INTEGER DEFAULT 0')
    _add_column('player', 'streak_freezes', 'INTEGER DEFAULT 0')
    _add_column('player', 'hardcore', 'BOOLEAN DEFAULT FALSE')
    _add_column('player', 'hardcore_since', 'TIMESTAMP')
    # Per-player timezone and reminder time
    _add_column('player', 'timezone', "VARCHAR(50) DEFAULT 'Europe/Madrid'")
    _add_column('player', 'reminder_time', "VARCHAR(5) DEFAULT '18:00'")
    _normalize_conditions()
    _rescale_xp_to_current_curve()
