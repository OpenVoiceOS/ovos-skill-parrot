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
        # `parrot_start` dialog is randomized (9 variants), so the resulting
        # speak messages are non-deterministic; ignore them and only assert
        # the deterministic intent skeleton
        self.ignore_messages = [
            "speak",
            "ovos.utterance.speak",  # speak under ovos.* namespace
        ]

    def tearDown(self):
        if self.minicroft:
            self.minicroft.stop()
        LOG.set_level("CRITICAL")

    def test_start_parrot(self):
        session = Session("123")
        session.pipeline = ["ovos-padatious-pipeline-plugin-high"]

        message = Message("recognizer_loop:utterance",
                          {"utterances": ["start parrot"], "lang": "en-US"},
                          {"session": session.serialize()})

        expected_messages = [
            message,
            Message("ovos-skill-parrot.openvoiceos.activate", {}),
            Message("ovos-skill-parrot.openvoiceos:start_parrot.intent", {}),

            Message("mycroft.skill.handler.start", {
                "name": "ParrotSkill.handle_start_parrot_intent"
            }),
            Message("mycroft.skill.handler.complete", {
                "name": "ParrotSkill.handle_start_parrot_intent"
            }),

            Message("ovos.utterance.handled", {}),
        ]

        test = End2EndTest(
            minicroft=self.minicroft,
            skill_ids=[self.skill_id],
            eof_msgs=["ovos.utterance.handled"],
            flip_points=["recognizer_loop:utterance"],
            ignore_messages=self.ignore_messages,
            source_message=message,
            expected_messages=expected_messages,
        )

        test.execute()
