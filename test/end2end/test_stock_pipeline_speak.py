"""On the stock pipeline, "say X" routes to speak and the skill repeats X.

``speak.intent`` holds two kinds of lines: ``{sentence}`` lines, which capture
the phrase, and example lines with a literal payload and no slot, which teach
the m2v prototype what a real request looks like. Padacioso matches an example
line exactly, so the payload reaches the handler only when a ``{sentence}``
line with the same leading words also matches. A locale whose example lines
start with words that no ``{sentence}`` line starts with makes the skill
answer with silence.

This test boots the pipeline that ovos-config ships, not ovoscope's default,
with each padatious stage replaced by the padacioso stage of the same tier.
It checks the phrase the handler receives in ``sentence``, and it checks every
example line of every locale.
"""
import re
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_config.config import LocalConf
from ovos_config.locations import DEFAULT_CONFIG
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
STOCK_PIPELINE = [stage.replace("ovos-padatious-pipeline-plugin", "ovos-padacioso-pipeline-plugin")
                  for stage in LocalConf(DEFAULT_CONFIG)["intents"]["pipeline"]]
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


@pytest.fixture(scope="module")
def stock(request):
    lang = request.param
    minicroft = get_minicroft([SKILL_ID], max_wait=200, lang=lang,
                              default_pipeline=STOCK_PIPELINE)
    yield lang, minicroft
    minicroft.stop()


def _route(minicroft, lang, utterance):
    session = Session(f"stock-{lang}-{utterance}")
    session.lang = lang
    session.pipeline = list(STOCK_PIPELINE)
    message = Message("recognizer_loop:utterance", {"utterances": [utterance], "lang": lang},
                      {"session": session.serialize(), "source": "A", "destination": "B"})
    capture = CaptureSession(minicroft, eof_msgs=["ovos.utterance.handled"])
    capture.capture(message, timeout=60)
    return next((m for m in capture.finish() if m.msg_type.startswith(f"{SKILL_ID}:")), None)


@pytest.mark.parametrize("stock", sorted(SPEAK), indirect=True)
def test_say_routes_to_speak_with_the_phrase(stock):
    lang, minicroft = stock
    wrong = []
    for utterance, phrase in SPEAK[lang]:
        intent = _route(minicroft, lang, utterance)
        got = (intent.msg_type, (intent.data.get("sentence") or "").lower()) if intent else None
        if got != (f"{SKILL_ID}:speak", phrase.lower()):
            wrong.append(f"{utterance!r}: expected speak with {phrase!r}, got {got}")
    for utterance in NOT_SPEAK.get(lang, []):
        intent = _route(minicroft, lang, utterance)
        if intent and intent.msg_type == f"{SKILL_ID}:speak":
            wrong.append(f"{utterance!r}: must not route to speak, got {intent.data.get('sentence')!r}")
    assert not wrong, "\n".join(wrong)


@pytest.mark.parametrize("stock", LOCALES, indirect=True)
def test_every_example_line_carries_its_phrase(stock):
    lang, minicroft = stock
    silent = []
    for line in _example_lines(lang):
        intent = _route(minicroft, lang, line)
        if intent and intent.msg_type == f"{SKILL_ID}:speak" and not (intent.data.get("sentence") or "").strip():
            silent.append(line)
    assert not silent, f"[{lang}] speak matched with no sentence, so the skill says nothing: {silent}"
