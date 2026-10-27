"""End-to-end intent routing tests for the parrot-mode lifecycle (en-US).

``speak.intent`` is covered by :mod:`test_parrot`; these cases exercise the two
lifecycle intents it does not: entering parrot mode (``start_parrot.intent``)
and leaving it (``stop_parrot.intent``). Each utterance runs in its own session
with an explicit pipeline so the intents route to the skill rather than to the
global stop pipeline, and so parrot state never leaks between cases.
"""
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LANG = "en-US"

# the handlers echo dialog whose text/namespace varies across stacks; ignore the
# spoken output so the assertion covers only the deterministic intent binding.
_IGNORE = ["speak", "ovos.utterance.speak", "mycroft.audio.play_sound"]


class TestParrotLifecycleIntentsEnUS(unittest.TestCase):
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

    # OVOS-INTENT-2/PIPELINE-1: the per-skill dispatch topic no longer carries
    # the ".intent" suffix present in the intent file/label (same migration
    # already applied in ovos-skill-camera#63 / ovos-skill-ddg#137).

    def test_start_parrot(self):
        text = "start parrot"
        TALLY.assert_routed(text, f"{SKILL_ID}:start_parrot", self._run(text, "start-1"))

    def test_engage_parrot_mode(self):
        text = "engage parrot mode"
        TALLY.assert_routed(text, f"{SKILL_ID}:start_parrot", self._run(text, "start-2"))

    def test_repeat_everything(self):
        text = "repeat everything"
        TALLY.assert_routed(text, f"{SKILL_ID}:start_parrot", self._run(text, "start-3"))

    def test_stop_parroting(self):
        text = "stop parroting"
        TALLY.assert_routed(text, f"{SKILL_ID}:stop_parrot", self._run(text, "stop-1"))

    def test_stop_parrot_mode(self):
        text = "stop parrot mode"
        TALLY.assert_routed(text, f"{SKILL_ID}:stop_parrot", self._run(text, "stop-2"))

    def test_cancel_parroting(self):
        text = "cancel parroting"
        TALLY.assert_routed(text, f"{SKILL_ID}:stop_parrot", self._run(text, "stop-3"))


if __name__ == "__main__":
    unittest.main()
