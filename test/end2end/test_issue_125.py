"""Regression coverage for OpenVoiceOS/ovos-skill-parrot#125.

``speak.intent``'s greedy ``repeat {sentence}`` template shadowed
``repeat_stt``/``repeat_tts`` variant phrasings that don't exactly match one
of those intents' canonical lines (third-person / inserted-word variants),
and ``stop_parrot.intent`` was missing several common stop phrasings.

A request routed to ``speak`` must also hand the handler the phrase without
the "after me" anchor.
"""
import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LANG = "en-US"

VARIANTS = [
    ("repeat what I just said", "repeat_stt"),
    ("repeat what I said", "repeat_stt"),
    ("tell me what you just heard", "repeat_stt"),
    ("tell me what you heard", "repeat_stt"),
    ("what did you hear", "repeat_stt"),
    ("repeat what you just told me", "repeat_tts"),
    ("repeat what you told me", "repeat_tts"),
    ("what did you just tell me", "repeat_tts"),
    ("what did you tell me", "repeat_tts"),
    ("say it again", "repeat_tts"),
    ("quit parroting", "stop_parrot"),
    ("stop copying me", "stop_parrot"),
    ("turn off parrot mode", "stop_parrot"),
    ("parrot off", "stop_parrot"),
]


@pytest.fixture(scope="module")
def minicroft():
    mc = get_prototype_minicroft([SKILL_ID], lang=LANG)
    yield mc
    mc.stop()


def _capture(minicroft, text, session_id):
    session = Session(session_id)
    session.lang = LANG
    session.pipeline = list(PIPELINE)
    session.blacklisted_intents = []
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(minicroft, ignore_messages=[])
    capture.capture(utterance, timeout=30)
    return capture.finish()


def _speak_sentence(messages):
    for message in messages:
        if message.msg_type in ("speak", "ovos.utterance.speak"):
            return message.data.get("utterance")
    return None


@pytest.mark.parametrize("text, intent", VARIANTS, ids=[v[0] for v in VARIANTS])
def test_variant_phrasing_routes_to_its_intent(minicroft, text, intent):
    """The regression pairs: a variant phrasing must win over speak.intent."""
    messages = _capture(minicroft, text, f"issue125-{text}")
    TALLY.assert_routed(text, f"{SKILL_ID}:{intent}",
                        [m.msg_type for m in messages])


def test_repeat_hello_world_still_routes_to_speak(minicroft):
    """Negative: a genuine echo request is not swallowed by repeat_stt."""
    text = "repeat hello world"
    messages = _capture(minicroft, text, "issue125-speak")
    TALLY.assert_routed(text, f"{SKILL_ID}:speak", [m.msg_type for m in messages])
    assert _speak_sentence(messages) == "hello world"


def test_repeat_after_me_excludes_anchor_from_capture(minicroft):
    """"repeat after me X" must not echo "after me" back as part of X."""
    text = "repeat after me the shopping list"
    messages = _capture(minicroft, text, "issue125-after-me")
    TALLY.assert_routed(text, f"{SKILL_ID}:speak", [m.msg_type for m in messages])
    assert _speak_sentence(messages) == "the shopping list"
