"""AI client error handling, heuristics, schema upgrades and database URL configuration."""
import importlib
import io
import json
import urllib.error
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ai_guardian import TheArchitect, DEFAULT_GEMINI_MODEL
from app.extensions import db
from app.models import Player


# --- Gemini HTTP client ---

def _response(body, status=200):
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = body.encode() if isinstance(body, str) else body
    ctx = MagicMock()
    ctx.__enter__.return_value = resp
    ctx.__exit__.return_value = None
    return ctx


def _gemini(text):
    return json.dumps({'candidates': [{'content': {'parts': [{'text': text}]}}]})


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.delenv('GEMINI_MODEL', raising=False)


def test_llm_request_uses_v1beta_and_header_key(api_key, monkeypatch):
    with patch('urllib.request.urlopen', return_value=_response(_gemini('{"ok": 1}'))) as urlopen:
        assert TheArchitect._call_llm('prompt') == {'ok': 1}
    req = urlopen.call_args.args[0]
    assert req.full_url == f'https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent'
    assert 'key=' not in req.full_url
    assert req.get_header('X-goog-api-key') == 'test-key'
    body = json.loads(req.data)
    assert body['generationConfig'] == {'responseMimeType': 'application/json'}

    monkeypatch.setenv('GEMINI_MODEL', 'custom-model')
    with patch('urllib.request.urlopen', return_value=_response(_gemini('{}'))) as urlopen:
        TheArchitect._call_llm('prompt')
    assert '/models/custom-model:generateContent' in urlopen.call_args.args[0].full_url


def test_llm_text_mode_and_markdown_stripping(api_key):
    with patch('urllib.request.urlopen', return_value=_response(_gemini('```json\n{"a": 2}\n```'))):
        assert TheArchitect._call_llm('p') == {'a': 2}
    with patch('urllib.request.urlopen', return_value=_response(_gemini('plain words'))) as urlopen:
        assert TheArchitect._call_llm('p', json_mode=False) == 'plain words'
    assert 'generationConfig' not in json.loads(urlopen.call_args.args[0].data)


@pytest.mark.parametrize('failure', [
    _response(_gemini('not json at all')),                                   # unparseable model output
    _response('', status=503),                                               # non-200 without raising
    _response('', status=429),
    urllib.error.HTTPError('u', 429, 'quota', {}, io.BytesIO(b'')),           # quota
    urllib.error.HTTPError('u', 500, 'err', {}, io.BytesIO(b'server error')),
    TimeoutError('slow'),                                                    # network problems
    _response('{"unexpected": "shape"}'),                                    # missing candidates
])
def test_llm_failures_return_none(api_key, failure):
    kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
    with patch('urllib.request.urlopen', **kwargs):
        assert TheArchitect._call_llm('p') is None


def test_llm_without_key_returns_none(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    with patch('urllib.request.urlopen') as urlopen:
        assert TheArchitect._call_llm('p') is None
        assert not urlopen.called


def test_prompt_input_is_sanitized():
    assert TheArchitect._sanitize_input(' ```ignore``` ### <b>x</b> ') == 'ignore  &lt;b&gt;x&lt;/b&gt;'
    assert TheArchitect._sanitize_input(None) == ''


# --- heuristics ---

@pytest.mark.parametrize('title, stat, rank', [
    ('Go for a run', 'STR', 'E'),
    ('Meditate', 'SNS', 'E'),
    ('Cook dinner', 'VIT', 'E'),
    ('Read a book', 'INT', 'E'),
    ('Pay the bills', 'AGI', 'E'),
    ('Study for exam', 'INT', 'C'),
    ('Finish thesis', 'INT', 'B'),
])
def test_heuristic_analysis(title, stat, rank):
    result = TheArchitect._heuristic_analysis(title)
    assert (result['stat'], result['rank']) == (stat, rank)


# --- response coercion ---

@pytest.mark.parametrize('llm, expected', [
    ({'rank': 'B', 'stat': 'STR'}, {'rank': 'B', 'stat': 'STR', 'xp': 50}),
    ({'rank': 'B', 'stat': 'STR', 'xp': 'lots'}, {'rank': 'B', 'stat': 'STR', 'xp': 50}),
    ({'rank': 3, 'stat': 7, 'xp': '120'}, {'rank': '3', 'stat': '7', 'xp': 120}),
])
def test_analyze_quest_coerces_llm_output(llm, expected):
    with patch.object(TheArchitect, '_call_llm', return_value=llm):
        assert TheArchitect.analyze_quest('anything') == expected


def test_analyze_quest_falls_back_on_bad_shape():
    with patch.object(TheArchitect, '_call_llm', return_value={'rank': 'B'}):
        assert TheArchitect.analyze_quest('Go for a run')['stat'] == 'STR'


def test_decompose_task_validation_and_fallback():
    raw = [{'step': 'A'}, {'step': 'B', 'rank': 5, 'priority': 'urgent'}, 'junk', {'rank': 'S'}]
    with patch.object(TheArchitect, '_call_llm', return_value=raw):
        steps = TheArchitect.decompose_task('x')
    assert steps == [{'step': 'A', 'rank': 'E', 'priority': 4}, {'step': 'B', 'rank': 'E', 'priority': 4}]

    with patch.object(TheArchitect, '_call_llm', return_value=['junk']):
        fallback = TheArchitect.decompose_task('Build app')
    assert [s['step'] for s in fallback] == ['Research: Build app', 'Drafting: Build app',
                                            'Execution: Build app', 'Review: Build app']


# --- schema upgrades ---

def test_schema_upgrades_on_sqlite_normalize_conditions(app):
    from app.schema_upgrades import run_schema_upgrades
    db.session.add_all([Player(name='A', condition='Healthy'), Player(name='B', condition='Normal'),
                        Player(name='C', condition='TIRED')])
    db.session.commit()
    run_schema_upgrades()
    run_schema_upgrades()  # idempotent
    db.session.expire_all()
    assert sorted(p.condition for p in Player.query) == ['NORMAL', 'NORMAL', 'TIRED']


@pytest.mark.parametrize('dialect, current, expected_sql', [
    ('postgresql', 64, 'ALTER TABLE "player" ALTER COLUMN "password_hash" TYPE VARCHAR(255)'),
    ('mysql', 64, 'ALTER TABLE `player` MODIFY `password_hash` VARCHAR(255)'),
    ('postgresql', 255, None),   # already wide enough
    ('oracle', 64, None),        # unsupported dialect: logged, not altered
])
def test_widen_varchar_per_dialect(app, dialect, current, expected_sql):
    from app import schema_upgrades
    conn = MagicMock()
    engine = MagicMock()
    engine.dialect.name = dialect
    engine.begin.return_value.__enter__.return_value = conn
    inspector = MagicMock()
    inspector.get_table_names.return_value = ['player']
    inspector.get_columns.return_value = [{'name': 'password_hash', 'type': SimpleNamespace(length=current)}]

    with patch.object(schema_upgrades, 'db', SimpleNamespace(engine=engine)), \
            patch.object(schema_upgrades, 'inspect', return_value=inspector):
        schema_upgrades._widen_varchar('player', 'password_hash', 255)

    if expected_sql:
        assert str(conn.execute.call_args.args[0]) == expected_sql
    else:
        assert not conn.execute.called


# --- config: DATABASE_URL handling ---

@pytest.mark.parametrize('url, expected', [
    ('postgres://u:p@h/db', 'postgresql://u:p@h/db'),
    ('mysql://u:p@h/db', 'mysql+pymysql://u:p@h/db'),
    ('mysql+mysqldb://u:p@h/db', 'mysql+pymysql://u:p@h/db'),
    ('mysql://u:p@h/db?ssl_mode=REQUIRED', 'mysql+pymysql://u:p@h/db'),
    ('mysql://u:p@h/db?ssl_mode=REQUIRED&charset=utf8', 'mysql+pymysql://u:p@h/db?charset=utf8'),
    (None, 'sqlite:///system.db'),
])
def test_database_url_rewrites(monkeypatch, url, expected):
    import config
    if url is None:
        monkeypatch.delenv('DATABASE_URL', raising=False)
    else:
        monkeypatch.setenv('DATABASE_URL', url)
    try:
        assert importlib.reload(config).Config.SQLALCHEMY_DATABASE_URI == expected
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_secret_key_from_env_or_random(monkeypatch):
    import config
    try:
        monkeypatch.setenv('SECRET_KEY', 'from-env')
        assert importlib.reload(config).Config.SECRET_KEY == 'from-env'
        monkeypatch.delenv('SECRET_KEY')
        k1 = importlib.reload(config).Config.SECRET_KEY
        k2 = importlib.reload(config).Config.SECRET_KEY
        assert len(k1) == 64 and k1 != k2 and k1 != 'system_access_key_123'
    finally:
        monkeypatch.undo()
        importlib.reload(config)


# --- table creation when the DB user may not create foreign keys (TiDB error 1142) ---

def _references_denied():
    import pymysql
    from sqlalchemy.exc import OperationalError
    return OperationalError('CREATE TABLE activity_event (...)', {},
                            pymysql.err.OperationalError(1142, "REFERENCES command denied to user 'x'@'%' for table 'player'"))


def test_create_tables_falls_back_without_foreign_keys(app, monkeypatch):
    from sqlalchemy import inspect as sa_inspect
    from app import schema_upgrades
    from app.models import ActivityEvent, Kudos, Player
    # Simulate an existing production DB that has the old tables but not the new ones
    for name in ('kudos', 'raid_contribution', 'raid', 'personal_reward', 'rivalry', 'activity_event'):
        db.metadata.tables[name].drop(db.engine)
    real_create_all = db.create_all
    monkeypatch.setattr(db, 'create_all', lambda: (_ for _ in ()).throw(_references_denied()))

    schema_upgrades.create_tables()

    insp = sa_inspect(db.engine)
    assert {'activity_event', 'rivalry', 'personal_reward', 'raid', 'raid_contribution', 'kudos'} <= set(insp.get_table_names())
    assert insp.get_foreign_keys('activity_event') == []          # created without DB-level FKs
    assert {i['name'] for i in insp.get_indexes('activity_event')} >= {'ix_activity_event_player_id', 'ix_activity_event_week_start'}
    # ...and the app still works on them, including ORM cascades
    p = Player(name='NoFK'); db.session.add(p); db.session.commit()
    db.session.add(ActivityEvent(player_id=p.id, kind='quest', points=1, week_start=__import__('datetime').date(2026, 11, 23)))
    db.session.commit()
    db.session.delete(p); db.session.commit()
    assert ActivityEvent.query.count() == 0
    monkeypatch.setattr(db, 'create_all', real_create_all)


def test_create_tables_reraises_other_errors(app, monkeypatch):
    import pymysql
    from sqlalchemy.exc import OperationalError
    from app import schema_upgrades
    boom = OperationalError('CREATE TABLE x', {}, pymysql.err.OperationalError(2003, "Can't connect"))
    monkeypatch.setattr(db, 'create_all', lambda: (_ for _ in ()).throw(boom))
    with pytest.raises(OperationalError):
        schema_upgrades.create_tables()


def test_create_tables_normal_path(app):
    from app import schema_upgrades
    schema_upgrades.create_tables()  # all tables already exist: no-op, no error
