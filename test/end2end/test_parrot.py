from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.log import LOG

from ovoscope import CaptureSession, End2EndTest, get_minicroft


class TestParrotSkill(TestCase):

    def setUp(self):
        LOG.set_level("DEBUG")
        self.skill_id = "ovos-skill-parrot.openvoiceos"
        self.minicroft = get_minicroft([self.skill_id])
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

    def test_speak_intent(self):
        """`say hello world` -> speak.intent -> handle_speak -> self.speak(...)

        We assert the skeleton (utterance -> activate -> intent -> handler
        start/complete -> handled) and ignore the speak message itself, because
        the echoed text and its bus namespace vary across stacks.
        """
        session = Session("123")
        session.pipeline = ["ovos-padatious-pipeline-plugin-high"]

        message = Message(
            "recognizer_loop:utterance",
            {"utterances": ["say hello world"], "lang": "en-US"},
            {"session": session.serialize()},
        )

        expected_messages = [
            message,
            Message(f"{self.skill_id}.activate", {}),  # skill is activated
            # OVOS-INTENT-2/PIPELINE-1: the per-skill dispatch topic drops the
            # ".intent" suffix present in the intent file/label.
            Message(f"{self.skill_id}:speak", {}),  # intent triggers
            Message("mycroft.skill.handler.start",
                    {"name": "ParrotSkill.handle_speak"}),
            # here the skill emits the echoed sentence via speak(...), ignored
            Message("mycroft.skill.handler.complete",
                    {"name": "ParrotSkill.handle_speak"}),
            Message("ovos.utterance.handled", {}),
        ]

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=self.ignore_messages,
            source_message=message,
            expected_messages=expected_messages,
        )

        test.execute()

    def test_speak_intent_echoes_the_input_phrase(self):
        """A routing-only check (message flow reaches ``handle_speak``, speak
        content ignored) is satisfied by a handler that echoes ANY text, or a
        fixed string, or nothing at all. The parrot's whole job is to say back
        what it was told, so assert the spoken text equals the phrase that
        went in -- not merely that some speak happened.

        Two different phrases are driven through the same handler so a
        wrong implementation that echoes one fixed sentence (which would
        pass a weaker "did it speak" check for either phrase individually)
        fails here on whichever phrase does not match that fixed string.
        """
        for phrase in ["hello world", "the quick brown fox jumps"]:
            with self.subTest(phrase=phrase):
                session = Session(f"echo-{phrase}")
                session.pipeline = ["ovos-padatious-pipeline-plugin-high"]
                message = Message(
                    "recognizer_loop:utterance",
                    {"utterances": [f"say {phrase}"], "lang": "en-US"},
                    {"session": session.serialize(), "source": "A", "destination": "B"},
                )
                capture = CaptureSession(self.minicroft)
                capture.capture(message, timeout=15)
                messages = capture.finish()
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
