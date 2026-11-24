import os
from dotenv import load_dotenv

# Load environment variables BEFORE importing app to ensure Config gets DATABASE_URL
load_dotenv()

debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']
if __name__ == '__main__' and debug_mode:
    # The debug reloader runs a watcher + a serving child; background jobs run only in the child
    os.environ['SHADOW_RELOADER'] = '1'

from app import create_app
from app.extensions import db
from app.services import seed_database
from app.schema_upgrades import create_tables, run_schema_upgrades

# Background jobs are registered inside create_app (app/tasks.py), so they also run under gunicorn
# (wsgi.py imports this module, so the block below is skipped there).
app = create_app()


def init_database():
    """
    Create tables, apply schema upgrades and seed the shop, ONE process at a time.
    gunicorn starts several workers that each import this module; without the lock they race
    to CREATE the same new tables ("table already exists" crashes the deploy) and can insert
    duplicate shop items. Later workers wait, then find everything already in place.
    """
    import fcntl
    import tempfile
    lock_path = os.path.join(tempfile.gettempdir(), 'shadow_os_db_init.lock')
    with open(lock_path, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # blocks until other workers finish
        try:
            with app.app_context():
                create_tables()  # create_all, tolerant of users without the REFERENCES privilege
                run_schema_upgrades()
                seed_database()
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


init_database()

if __name__ == '__main__':
    app.run(debug=debug_mode)
