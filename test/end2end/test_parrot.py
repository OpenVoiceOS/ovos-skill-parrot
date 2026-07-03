from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovos_utils.log import LOG

from ovoscope import End2EndTest, get_minicroft


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
            Message(f"{self.skill_id}:speak.intent", {}),  # intent triggers
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
