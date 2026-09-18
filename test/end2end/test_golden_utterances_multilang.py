"""Multilingual golden-utterance end-to-end coverage for ovos-skill-parrot.

test_golden_utterances.py (superseded by this file) only exercised en-US.
This skill registers six Padatious/Padacioso file-intents (speak,
repeat_tts, repeat_stt, did_you_hear_me, start_parrot, stop_parrot); every
locale under locale/ ships real .intent content for all six. Each golden
row is a literal resolution of that locale's own .intent template lines --
(a|b) alternatives and [a|b]/(a|) optional groups resolve to one concrete
choice -- with speak.intent's {sentence} free slot filled with a fixed
"hello world" placeholder (the slot generalizes to any text; it is not a
closed vocabulary to translate). No translated or invented prose is
introduced.

Unlike ovos-skill-alerts' shared-MiniCroft-with-secondary-langs approach
(blocked by ovoscope#179 at multi-locale scale), this suite follows the
ovos-skill-date-time per-locale pattern (test/end2end/test_intents_it_it.py
on that repo's dev branch): one MiniCroft is booted per locale, in turn,
torn down when the module's tests finish. Only the pure-Python, swig-free
padacioso template engine is booted (no padatious training phase, so no
"mycroft.skills.trained" wait across many locales).
"""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"

PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-low",
]

END2END_DIR = Path(__file__).parent

LANGS = [
    "ca-ES", "da-DK", "de-DE", "en-US", "es-ES", "eu-ES", "fa-IR", "fr-FR",
    "gl-ES", "it-IT", "kab", "nl-NL", "oc-FR", "pt-BR", "pt-PT", "sv-SE",
]

CROSS_LANG_NEGATIVES = [
    ("tell me a joke", "de-DE", "other-skill (jokes) phrasing, german session"),
    ("what's the weather", "fr-FR", "other-skill (weather) phrasing, french session"),
    ("play some music", "es-ES", "other-skill (music) phrasing, spanish session"),
]


def _candidates(skill_id: str, intent_label: str) -> set:
    base = intent_label[:-len(".intent")] if intent_label.endswith(".intent") else intent_label
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


GOLDEN_ROWS = [pytest.param(r, id=_golden_id(r)) for r in ALL_ROWS]

# One MiniCroft alive at a time. get_minicroft(lang=...) saves the process
# default-session lang at boot and restores it at stop(), so two MiniCrofts
# alive together each hold the OTHER one's lang as "original", and stopping
# them in any order but last-in-first-out leaves the process default on a
# foreign locale. Sixteen of them stopped in dict order left it on pt-PT,
# and every en-US MiniCroft booted later in the same process loaded the
# skill in pt-PT: test_intents_en_us.py failed 6, test_issue_125.py 2. The
# rows are ordered by locale, so the previous MiniCroft is stopped the
# moment the locale changes and the restore chain stays one deep.
_CURRENT = {"lang": None, "mc": None}


def _get_minicroft(lang):
    if _CURRENT["lang"] != lang:
        _stop_current()
        _CURRENT["mc"] = get_minicroft([SKILL_ID], max_wait=150, lang=lang,
                                       default_pipeline=PIPELINE)
        _CURRENT["lang"] = lang
    return _CURRENT["mc"]


def _stop_current():
    if _CURRENT["mc"] is not None:
        _CURRENT["mc"].stop()
    _CURRENT["mc"] = None
    _CURRENT["lang"] = None


@pytest.fixture(scope="module", autouse=True)
def _stop_last_minicroft():
    yield
    _stop_current()


def _types(mc, text, lang, session_id):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(PIPELINE)
    session.blacklisted_intents = []
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc, eof_msgs=["mycroft.skill.handler.start"])
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


@pytest.mark.timeout(180)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(row):
    mc = _get_minicroft(row["lang"])
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(mc, row["utterance"], row["lang"], f"golden-{_golden_id(row)}")
    assert any(t in candidates for t in types), (
        f"[{row['lang']}] {row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )


@pytest.mark.timeout(180)
@pytest.mark.parametrize("negative", CROSS_LANG_NEGATIVES, ids=lambda n: f"{n[1]}-{n[0]}")
def test_cross_language_negative(negative):
    text, lang, _why = negative
    mc = _get_minicroft(lang)
    types = _types(mc, text, lang, f"negative-{lang}-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"[{lang}] {text!r} was incorrectly claimed by {SKILL_ID}"
