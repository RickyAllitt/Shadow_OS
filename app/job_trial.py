"""
The Job Change Trial (unlocked at Level 10).

Five scenario questions. Every option quietly feeds TWO classes (2 points to one, 1 to another),
and each question gives every class exactly one primary and one secondary option, so no single
answer decides the outcome and the scoring is balanced. Options are shuffled when shown, never
name a class, and the weights only live here on the server.

Ties are broken by the final question ("what did you gain?"), then by the fixed CLASS_ORDER.
"""
import random

CLASS_ORDER = ('Assassin', 'Mage', 'Tank')

QUESTIONS = [
    {
        'id': 'gate',
        'title': 'TRIAL I // THE GATE',
        'prompt': 'The gate shudders. Something enormous is waiting on the other side.',
        'options': [
            {'id': 'gate-walls', 'text': 'Circle the walls. There is always a way in that nobody else has used.',
             'weights': {'Assassin': 2, 'Mage': 1}},
            {'id': 'gate-listen', 'text': 'Stop. Listen. Count the heartbeats behind the door before you move.',
             'weights': {'Mage': 2, 'Tank': 1}},
            {'id': 'gate-first', 'text': 'Step through first, so the others never have to.',
             'weights': {'Tank': 2, 'Assassin': 1}},
        ],
    },
    {
        'id': 'healer',
        'title': 'TRIAL II // THE FALL',
        'prompt': "Your party's healer collapses. The monsters haven't noticed... yet.",
        'options': [
            {'id': 'healer-guard', 'text': 'Drag them behind you and plant your feet.',
             'weights': {'Tank': 2, 'Mage': 1}},
            {'id': 'healer-strike', 'text': "The boss's guard is down. This is the opening. Take it.",
             'weights': {'Assassin': 2, 'Tank': 1}},
            {'id': 'healer-pattern', 'text': 'Replay every attack it has made. There is a tell. Find it.',
             'weights': {'Mage': 2, 'Assassin': 1}},
        ],
    },
    {
        'id': 'blade',
        'title': 'TRIAL III // THE OFFER',
        'prompt': 'A hooded merchant offers you a cursed relic. Its power is immense.',
        'options': [
            {'id': 'blade-take', 'text': 'Take it. Power is power. Curses are a problem for later.',
             'weights': {'Assassin': 2, 'Mage': 1}},
            {'id': 'blade-ask', 'text': 'Ask what the curse costs, and who paid it last.',
             'weights': {'Mage': 2, 'Tank': 1}},
            {'id': 'blade-refuse', 'text': 'Refuse. Some prices are paid by the people standing behind you.',
             'weights': {'Tank': 2, 'Assassin': 1}},
        ],
    },
    {
        'id': 'night',
        'title': 'TRIAL IV // 3:00 AM',
        'prompt': 'You wake in the dark. Something will not let you sleep.',
        'options': [
            {'id': 'night-plan', 'text': "A plan that isn't finished yet.",
             'weights': {'Mage': 2, 'Assassin': 1}},
            {'id': 'night-door', 'text': "A door you can't remember locking.",
             'weights': {'Tank': 2, 'Mage': 1}},
            {'id': 'night-chance', 'text': 'An opportunity someone else might take before you.',
             'weights': {'Assassin': 2, 'Tank': 1}},
        ],
    },
    {
        'id': 'gain',
        'title': 'FINAL TRIAL // SILENCE',
        'prompt': 'The battle is over. In the silence, the System asks: what did you gain?',
        'options': [
            {'id': 'gain-took', 'text': "Nothing I didn't take for myself.",
             'weights': {'Assassin': 2, 'Tank': 1}},
            {'id': 'gain-understand', 'text': 'Understanding.',
             'weights': {'Mage': 2, 'Assassin': 1}},
            {'id': 'gain-home', 'text': 'Everyone came home.',
             'weights': {'Tank': 2, 'Mage': 1}},
        ],
    },
]

TIE_BREAK_QUESTION = 'gain'

CLASS_PROFILES = {
    'Assassin': {
        'tagline': 'Strike first. Leave nothing behind.',
        'description': 'You move where others hesitate and claim what others leave on the table.',
        'bonus': '+10% Coins from every quest',
        'color': '#ff4d6d',
        'sigil': 'sword',
    },
    'Mage': {
        'tagline': 'Knowledge is the sharpest weapon.',
        'description': 'You win before the fight begins, by seeing the pattern no one else can.',
        'bonus': '+10% XP from every quest',
        'color': '#7b9bff',
        'sigil': 'wand-sparkles',
    },
    'Tank': {
        'tagline': 'Nothing gets past you.',
        'description': 'You are the wall the others stand behind, and you do not break.',
        'bonus': 'One-day grace before penalties take hold',
        'color': '#ffb347',
        'sigil': 'shield',
    },
}

_OPTIONS = {q['id']: {o['id']: o for o in q['options']} for q in QUESTIONS}


def questions_for_display(rng=random):
    """Questions with options in a fresh random order and without their weights."""
    shown = []
    for q in QUESTIONS:
        options = [{'id': o['id'], 'text': o['text']} for o in q['options']]
        rng.shuffle(options)
        shown.append({'id': q['id'], 'title': q['title'], 'prompt': q['prompt'], 'options': options})
    return shown


def score_answers(answers):
    """
    answers: {question_id: option_id}. Returns (class_name, scores) or (None, None) if any
    question is unanswered or has an option that does not belong to it.
    """
    scores = dict.fromkeys(CLASS_ORDER, 0)
    for q in QUESTIONS:
        option = _OPTIONS[q['id']].get(answers.get(q['id']))
        if option is None:
            return None, None
        for cls, pts in option['weights'].items():
            scores[cls] += pts

    best = max(scores.values())
    leaders = [c for c in CLASS_ORDER if scores[c] == best]
    if len(leaders) > 1:
        final = _OPTIONS[TIE_BREAK_QUESTION][answers[TIE_BREAK_QUESTION]]['weights']
        leaders.sort(key=lambda c: -final.get(c, 0))  # stable: CLASS_ORDER breaks any remaining tie
    return leaders[0], scores
