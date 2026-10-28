from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.log import LOG

from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft


class TestParrotSkill(TestCase):

    def setUp(self):
        LOG.set_level("DEBUG")
        self.skill_id = "ovos-skill-parrot.openvoiceos"
        self.minicroft = get_prototype_minicroft([self.skill_id], lang="en-US")
        # the spoken message echoes the (randomised / slot-extracted) sentence
        # and, on stacks with the bus-namespace migration enabled, is emitted
        # under the ovos.* namespace ("ovos.utterance.speak") instead of
        # "speak". Ignore both so the test asserts only the deterministic
        # message-flow skeleton and is robust to slot extraction + namespace.
        # The dispatcher additionally mirrors the intent lifecycle under the
        # OVOS-INTENT namespace ("ovos.intent.matched" / "ovos.intent.handler.*"
        # alongside the legacy "mycroft.skill.handler.*"); ignore those mirrors
        # so the skeleton stays a single canonical sequence.
        # a full-emit MockTTS also surfaces the audio-output span
        # ("recognizer_loop:audio_output_start"/"...end") around the echoed
        # speak; ignore those too so the skeleton is stable across ovoscope
        # versions.
        self.ignore_messages = [
            "speak",
            "ovos.utterance.speak",
            "ovos.intent.matched",
            "ovos.intent.handler.start",
            "ovos.intent.handler.complete",
            "recognizer_loop:audio_output_start",
            "recognizer_loop:audio_output_end",
        ]

    def tearDown(self):
        if self.minicroft:
            self.minicroft.stop()
        LOG.set_level("CRITICAL")

    def _say(self, utterance, session_id):
        """Speak ``utterance`` and return the captured messages; skip the
        test when m2v does not route it to speak.intent."""
        session = Session(session_id)
        session.lang = "en-US"
        session.pipeline = list(PIPELINE)
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": "en-US"},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft,
                                 eof_msgs=["ovos.utterance.handled"])
        capture.capture(message, timeout=15)
        messages = capture.finish()
        TALLY.assert_routed(utterance, f"{self.skill_id}:speak",
                            [m.msg_type for m in messages])
        return messages

    def test_speak_intent(self):
        """`say hello world` -> speak.intent -> handle_speak -> self.speak(...)

        We assert the skeleton (utterance -> activate -> intent -> handler
        start/complete -> handled) and ignore the speak message itself, because
        the echoed text and its bus namespace vary across stacks.
        """
        messages = [m for m in self._say("say hello world", "123")
                    if m.msg_type not in self.ignore_messages]
        self.assertEqual(
            [m.msg_type for m in messages],
            [
                "recognizer_loop:utterance",
                f"{self.skill_id}.activate",
                f"{self.skill_id}:speak",
                "mycroft.skill.handler.start",
                "mycroft.skill.handler.complete",
                "ovos.utterance.handled",
            ],
        )
        self.assertEqual(messages[3].data.get("name"), "ParrotSkill.handle_speak")
        self.assertEqual(messages[4].data.get("name"), "ParrotSkill.handle_speak")

    def _assert_echoes(self, phrase):
        messages = self._say(f"say {phrase}", f"echo-{phrase}")
        spoken = [m for m in messages
                  if m.msg_type in ("speak", "ovos.utterance.speak")]
        self.assertTrue(
            spoken,
            f"'say {phrase}' produced no speak message, got "
            f"{[m.msg_type for m in messages]}",
        )
        self.assertEqual(
            spoken[0].data.get("utterance"), phrase,
            f"parrot echoed {spoken[0].data.get('utterance')!r} for "
            f"input phrase {phrase!r}",
        )

    def test_speak_intent_echoes_the_input_phrase(self):
        """A routing-only check (message flow reaches ``handle_speak``, speak
        content ignored) is satisfied by a handler that echoes ANY text, or a
        fixed string, or nothing at all. The parrot's whole job is to say back
        what it was told, so assert the spoken text equals the phrase that
        went in -- not merely that some speak happened.

        Two different phrases are driven through the same handler (this test
        and the next) so a wrong implementation that echoes one fixed
        sentence fails on whichever phrase does not match that fixed string.
        """
        self._assert_echoes("hello world")

    def test_speak_intent_echoes_a_second_phrase(self):
        self._assert_echoes("the quick brown fox jumps")
