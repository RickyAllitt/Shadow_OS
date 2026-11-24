"""The Job Change trial: hidden scoring, balance, tie-breaks, page content and the reveal."""
import itertools
import random
import re

import pytest

from app.extensions import db
from app.job_trial import QUESTIONS, CLASS_ORDER, CLASS_PROFILES, questions_for_display, score_answers
from app.models import Player


def answers_for(*option_ids):
    return {q['id']: opt for q, opt in zip(QUESTIONS, option_ids)}


# --- scoring ---

def test_question_set_is_balanced():
    """Every question gives each class exactly one 2-point and one 1-point option."""
    for q in QUESTIONS:
        assert len(q['options']) == 3
        for cls in CLASS_ORDER:
            pts = sorted(o['weights'].get(cls, 0) for o in q['options'])
            assert pts == [0, 1, 2], (q['id'], cls)


def test_every_class_is_reachable_and_no_single_answer_decides():
    outcomes = {}
    all_combos = itertools.product(*[[o['id'] for o in q['options']] for q in QUESTIONS])
    for combo in all_combos:
        cls, _ = score_answers(answers_for(*combo))
        outcomes.setdefault(cls, 0)
        outcomes[cls] += 1
        for q, opt in zip(QUESTIONS, combo):
            outcomes.setdefault((q['id'], opt), set()).add(cls)
    assert all(outcomes[c] > 0 for c in CLASS_ORDER)
    # Whatever you pick on any one question, more than one class is still possible
    for q in QUESTIONS:
        for o in q['options']:
            assert len(outcomes[(q['id'], o['id'])]) > 1, o['id']
    # Roughly even split across all 243 answer combinations
    counts = [outcomes[c] for c in CLASS_ORDER]
    assert max(counts) - min(counts) <= 30, counts


def test_consistent_answers_pick_that_class():
    mage = [next(o['id'] for o in q['options'] if o['weights'].get('Mage') == 2) for q in QUESTIONS]
    assert score_answers(answers_for(*mage))[0] == 'Mage'


def test_ties_are_broken_by_the_final_question():
    # gate-walls A2 M1 | healer-guard T2 M1 | blade-ask M2 T1 | night-chance A2 T1 | gain-home T2 M1
    combo = ('gate-walls', 'healer-guard', 'blade-ask', 'night-chance', 'gain-home')
    cls, scores = score_answers(answers_for(*combo))
    assert scores == {'Assassin': 4, 'Mage': 5, 'Tank': 6} and cls == 'Tank'

    # With the current questions an exact tie can't happen (each answer moves 3 points unevenly)
    for combo in itertools.product(*[[o['id'] for o in q['options']] for q in QUESTIONS]):
        _, scores = score_answers(answers_for(*combo))
        assert len({v for v in scores.values() if v == max(scores.values())}) == 1
        assert sorted(scores.values()).count(max(scores.values())) == 1


def test_tie_break_safeguard(monkeypatch):
    """If the question set is ever edited so ties are possible, the final answer decides."""
    from app import job_trial
    qs = [
        {'id': 'one', 'options': [{'id': 'one-a', 'weights': {'Assassin': 1, 'Mage': 1}}]},
        {'id': 'gain', 'options': [{'id': 'gain-m', 'weights': {'Mage': 1, 'Assassin': 1}},
                                   {'id': 'gain-a', 'weights': {'Assassin': 1, 'Mage': 1, 'Tank': 0}}]},
    ]
    monkeypatch.setattr(job_trial, 'QUESTIONS', qs)
    monkeypatch.setattr(job_trial, '_OPTIONS', {q['id']: {o['id']: o for o in q['options']} for q in qs})
    # Equal final weights -> fixed CLASS_ORDER decides
    assert job_trial.score_answers({'one': 'one-a', 'gain': 'gain-m'})[0] == 'Assassin'
    qs[1]['options'][0]['weights'] = {'Mage': 2, 'Assassin': 0}
    qs[0]['options'][0]['weights'] = {'Assassin': 2, 'Mage': 0}
    # Assassin 2, Mage 2 -> final question favoured Mage
    assert job_trial.score_answers({'one': 'one-a', 'gain': 'gain-m'})[0] == 'Mage'


@pytest.mark.parametrize('answers', [
    {},
    answers_for('gate-walls', 'healer-guard', 'blade-ask', 'night-chance'),          # one missing
    answers_for('gate-walls', 'healer-guard', 'blade-ask', 'night-chance', 'gate-first'),  # option from another question
    answers_for('gate-walls', 'healer-guard', 'blade-ask', 'night-chance', 'Mage'),        # forged value
])
def test_incomplete_or_forged_answers_are_rejected(answers):
    assert score_answers(answers) == (None, None)


def test_display_hides_weights_and_shuffles():
    shown = questions_for_display(random.Random(1))
    assert all('weights' not in o for q in shown for o in q['options'])
    orders = {tuple(o['id'] for o in questions_for_display(random.Random(seed))[0]['options']) for seed in range(20)}
    assert len(orders) > 1


# --- routes ---

def _eligible(level=10):
    p = Player.query.filter_by(name="AuthUser").first()
    p.level = level
    db.session.commit()
    return p


def test_trial_requires_level_10_even_by_direct_url(auth_client, app):
    _eligible(level=9)
    page = auth_client.get('/job_test', follow_redirects=True).data
    assert b'Level 10 Required' in page


def test_trial_page_never_names_a_class(auth_client, app):
    _eligible()
    page = auth_client.get('/job_test').data.decode()
    assert 'JOB CHANGE QUEST' in page and 'TRIAL I // THE GATE' in page
    for cls in CLASS_ORDER:
        assert re.search(rf'\b{cls}\b', page, re.I) is None, cls  # whole words ("image" contains "mage")
    assert len(re.findall(r'type="radio"', page)) == 15


def test_trial_rejects_incomplete_submission(auth_client, app, csrf_token):
    _eligible()
    page = auth_client.post('/job_test', data={'gate': 'gate-walls', 'csrf_token': csrf_token}).data
    assert b'The trial is incomplete' in page
    assert Player.query.filter_by(name="AuthUser").first().job_class == 'None'


def test_trial_assigns_class_and_reveals_it(auth_client, app, csrf_token):
    _eligible()
    tank = [next(o['id'] for o in q['options'] if o['weights'].get('Tank') == 2) for q in QUESTIONS]
    page = auth_client.post('/job_test', data={**answers_for(*tank), 'csrf_token': csrf_token}).data.decode()
    db.session.expire_all()
    assert Player.query.filter_by(name="AuthUser").first().job_class == 'Tank'
    assert 'JOB CHANGE COMPLETE' in page and 'TANK' in page
    assert CLASS_PROFILES['Tank']['bonus'] in page
    assert 'Juggernaut' in page and 'Monarch of Iron' in page  # evolution path
    # Refreshing / revisiting after the change goes back to the dashboard
    assert auth_client.get('/job_test').status_code == 302
