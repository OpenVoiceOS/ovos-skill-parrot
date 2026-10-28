"""End-to-end intent routing for the pt-PT locale.

The pt-PT locale ships intent files for all six intents; without them the
skill loads and answers nothing at all in European Portuguese, which no
en-US test can detect. One utterance per intent, taken from the locale's
own templates, so removing a pt-PT file turns this module red.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LANG = "pt-PT"

# the handlers echo dialog whose text/namespace varies across stacks; ignore the
# spoken output so the assertion covers only the deterministic intent binding.
_IGNORE = ["speak", "ovos.utterance.speak", "mycroft.audio.play_sound"]


class TestParrotIntentsPtPT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang=LANG)

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _run(self, text, session_id):
        session = Session(session_id)
        session.lang = LANG
        session.pipeline = list(PIPELINE)
        session.blacklisted_intents = []
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": LANG},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft, ignore_messages=_IGNORE)
        capture.capture(utterance, timeout=30)
        return [m.msg_type for m in capture.finish()]

    def test_start_parrot(self):
        text = "ativa o modo papagaio"
        TALLY.assert_routed(text, f"{SKILL_ID}:start_parrot", self._run(text, "pt-start"))

    def test_stop_parrot(self):
        text = "desliga o modo papagaio"
        TALLY.assert_routed(text, f"{SKILL_ID}:stop_parrot", self._run(text, "pt-stop"))

    def test_speak(self):
        text = "diz olá bom dia"
        TALLY.assert_routed(text, f"{SKILL_ID}:speak", self._run(text, "pt-speak"))

    def test_did_you_hear_me(self):
        text = "ouviste-me"
        TALLY.assert_routed(text, f"{SKILL_ID}:did_you_hear_me", self._run(text, "pt-hear"))

    def test_repeat_stt(self):
        text = "o que é que eu disse"
        TALLY.assert_routed(text, f"{SKILL_ID}:repeat_stt", self._run(text, "pt-stt"))

    def test_repeat_tts(self):
        text = "o que é que disseste"
        TALLY.assert_routed(text, f"{SKILL_ID}:repeat_tts", self._run(text, "pt-tts"))


if __name__ == "__main__":
    unittest.main()
