""""Say X" routes to speak and the skill repeats X.

``speak.intent`` holds two kinds of lines: ``{sentence}`` lines, which capture
the phrase, and example lines with a literal payload and no slot, which teach
the m2v prototype what a real request looks like. A locale whose example
lines reach the handler with no ``sentence`` makes the skill answer with
silence.

It checks the phrase the handler receives in ``sentence``, and it checks every
example line of every locale.
"""
import re
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LOCALE = Path(__file__).resolve().parents[2] / "locale"
LOCALES = sorted(path.name for path in LOCALE.iterdir() if (path / "speak.intent").is_file())

# (utterance, the phrase the skill must repeat); no payload is an example line
SPEAK = {
    "en-US": [("say the train leaves at noon", "the train leaves at noon")],
    "de-DE": [("sage der Zug fährt um zwölf", "der Zug fährt um zwölf"),
              ("sag mir nach der Zug ist pünktlich", "der Zug ist pünktlich")],
    "es-ES": [("di el tren sale a mediodía", "el tren sale a mediodía")],
    "fr-FR": [("dis le train part à midi", "le train part à midi")],
    "pt-PT": [("diz o comboio parte às duas", "o comboio parte às duas")],
    "pt-BR": [("diga o trem sai ao meio dia", "o trem sai ao meio dia"),
              ("repita a reunião começa às três", "a reunião começa às três")],
    "ru-RU": [("повтори поезд уходит в полдень", "поезд уходит в полдень")],
}
# requests that start like a speak line but ask for something else
NOT_SPEAK = {
    "de-DE": ["sag mir, was ich eben gesagt habe"],
    "pt-BR": ["o que eu disse?", "repita o que eu acabei de dizer", "Diga-me o que eu disse."],
}


def _example_lines(lang):
    lines = (LOCALE / lang / "speak.intent").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines
            if line.strip() and "{" not in line and not re.search(r"[(\[]", line)]


SPEAK_CASES = [(lang, utterance, phrase)
               for lang in sorted(SPEAK) for utterance, phrase in SPEAK[lang]]
NOT_SPEAK_CASES = [(lang, utterance)
                   for lang in sorted(NOT_SPEAK) for utterance in NOT_SPEAK[lang]]


@pytest.fixture(scope="module")
def boot():
    """One MiniCroft per locale; the cases come in locale order, so the
    previous locale's MiniCroft stops before the next one boots."""
    booted = {}

    def _get(lang):
        if lang not in booted:
            for minicroft in booted.values():
                minicroft.stop()
            booted.clear()
            booted[lang] = get_prototype_minicroft([SKILL_ID], max_wait=200, lang=lang)
        return booted[lang]
    yield _get
    for minicroft in booted.values():
        minicroft.stop()


def _route(minicroft, lang, utterance):
    """The bus message types the request fired, and this skill's intent
    message (or None)."""
    session = Session(f"stock-{lang}-{utterance}")
    session.lang = lang
    session.pipeline = list(PIPELINE)
    message = Message("recognizer_loop:utterance", {"utterances": [utterance], "lang": lang},
                      {"session": session.serialize(), "source": "A", "destination": "B"})
    capture = CaptureSession(minicroft, eof_msgs=["ovos.utterance.handled"])
    capture.capture(message, timeout=60)
    messages = capture.finish()
    intent = next((m for m in messages if m.msg_type.startswith(f"{SKILL_ID}:")), None)
    return [m.msg_type for m in messages], intent


@pytest.mark.parametrize("lang, utterance, phrase", SPEAK_CASES,
                         ids=[f"{c[0]}-{c[1]}" for c in SPEAK_CASES])
def test_say_routes_to_speak_with_the_phrase(boot, lang, utterance, phrase):
    types, intent = _route(boot(lang), lang, utterance)
    TALLY.assert_routed(f"[{lang}] {utterance}", f"{SKILL_ID}:speak", types)
    assert (intent.data.get("sentence") or "").lower() == phrase.lower(), (
        f"{utterance!r}: expected speak with {phrase!r}, got {intent.data.get('sentence')!r}")


@pytest.mark.parametrize("lang, utterance", NOT_SPEAK_CASES,
                         ids=[f"{c[0]}-{c[1]}" for c in NOT_SPEAK_CASES])
def test_a_request_for_something_else_does_not_route_to_speak(boot, lang, utterance):
    types, _ = _route(boot(lang), lang, utterance)
    TALLY.assert_not_routed(f"[{lang}] {utterance}", [f"{SKILL_ID}:speak"], types)


@pytest.mark.parametrize("lang", LOCALES)
def test_every_example_line_carries_its_phrase(boot, lang):
    minicroft = boot(lang)
    silent = []
    for line in _example_lines(lang):
        _, intent = _route(minicroft, lang, line)
        if intent and intent.msg_type == f"{SKILL_ID}:speak" and not (intent.data.get("sentence") or "").strip():
            silent.append(line)
    assert not silent, f"[{lang}] speak matched with no sentence, so the skill says nothing: {silent}"
