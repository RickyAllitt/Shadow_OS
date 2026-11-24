"""
Gunicorn settings (loaded automatically by `gunicorn wsgi:app` from the project root).

Gunicorn can import the app in the master process and fork workers from it. The master also runs
the background scheduler, so it holds database connections. A forked worker must never reuse them:
two processes on one TLS connection corrupt it ("SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC").
"""
import sys


def post_fork(server, worker):
    """Give each new worker its own connection pool (without closing the master's connections)."""
    run = sys.modules.get('run')
    if run is None:  # app not loaded in the master: the worker will create its own engine
        return
    from app.extensions import db
    with run.app.app_context():
        db.engine.dispose(close=False)
