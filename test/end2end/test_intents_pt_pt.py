"""End-to-end intent routing for the pt-PT locale.

The pt-PT locale ships intent files for all six intents; without them the
skill loads and answers nothing at all in European Portuguese, which no
en-US test can detect. One utterance per intent, taken from the locale's
own templates, so removing a pt-PT file turns this module red.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LANG = "pt-PT"

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
]

# the handlers echo dialog whose text/namespace varies across stacks; ignore the
# spoken output so the assertion covers only the deterministic intent binding.
_IGNORE = ["speak", "ovos.utterance.speak", "mycroft.audio.play_sound"]


class TestParrotIntentsPtPT(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID], lang=LANG)

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _run(self, text, session_id):
        session = Session(session_id)
        session.lang = LANG
        session.pipeline = list(_PIPELINE)
        # blacklisted_intents defaults to None on a fresh Session, which crashes
        # the padacioso pipeline (NoneType membership test) - force an empty list.
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
        types = self._run("ativa o modo papagaio", "pt-start")
        self.assertIn(f"{SKILL_ID}:start_parrot", types)

    def test_stop_parrot(self):
        types = self._run("desliga o modo papagaio", "pt-stop")
        self.assertIn(f"{SKILL_ID}:stop_parrot", types)

    def test_speak(self):
        types = self._run("diz olá bom dia", "pt-speak")
        self.assertIn(f"{SKILL_ID}:speak", types)

    def test_did_you_hear_me(self):
        types = self._run("ouviste-me", "pt-hear")
        self.assertIn(f"{SKILL_ID}:did_you_hear_me", types)

    def test_repeat_stt(self):
        types = self._run("o que é que eu disse", "pt-stt")
        self.assertIn(f"{SKILL_ID}:repeat_stt", types)

    def test_repeat_tts(self):
        types = self._run("o que é que disseste", "pt-tts")
        self.assertIn(f"{SKILL_ID}:repeat_tts", types)


if __name__ == "__main__":
    unittest.main()
