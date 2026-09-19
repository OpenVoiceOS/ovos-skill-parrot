"""Regression coverage for OpenVoiceOS/ovos-skill-parrot#125.

``speak.intent``'s greedy ``repeat {sentence}`` template shadowed
``repeat_stt``/``repeat_tts`` variant phrasings that don't exactly match one
of those intents' canonical lines (third-person / inserted-word variants),
and ``stop_parrot.intent`` was missing several common stop phrasings.

Two layers are probed:

* a raw ``padacioso.IntentContainer`` built from *all* of this skill's
  ``locale/en-US/*.intent`` files together, verifying the new lines resolve
  to the correct intent (or, for the "repeat after me" case, that ``speak``'s
  captured slot excludes the anchor rather than swallowing it) -- this is
  the container-level view the issue's shadow report was based on;
* the shipped ``MiniCroft`` pipeline (padatious high -> padacioso high ->
  padacioso medium, the same stack ``test_golden_utterances.py`` drives),
  verifying the slot-length tie-break resolves each new phrasing to the
  correct skill intent end-to-end.
"""
import glob
import os
import unittest

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft
from padacioso import IntentContainer

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LANG = "en-US"
LOCALE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "locale", "en-US",
)

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
]


def _build_raw_container(cache_dir):
    container = IntentContainer(cache_dir)
    for path in glob.glob(os.path.join(LOCALE_DIR, "*.intent")):
        name = os.path.basename(path)[: -len(".intent")]
        lines = [l for l in open(path, encoding="utf-8").read().splitlines() if l.strip()]
        container.add_intent(name, lines)
    return container


class TestRawContainerVariants(unittest.TestCase):
    """Container-level probe: every new/variant phrasing resolves correctly."""

    @classmethod
    def setUpClass(cls):
        cls.container = _build_raw_container(os.path.join("/tmp", "parrot_issue125_probe_cache"))

    def _resolve(self, text):
        return self.container.calc_intent(text)

    def test_repeat_stt_variants(self):
        for text in [
            "repeat what I just said",
            "repeat what I said",
            "tell me what you just heard",
            "tell me what you heard",
            "what did you hear",
        ]:
            with self.subTest(utterance=text):
                self.assertEqual(self._resolve(text).get("name"), "repeat_stt")

    def test_repeat_tts_variants(self):
        for text in [
            "repeat what you just told me",
            "repeat what you told me",
            "what did you just tell me",
            "what did you tell me",
            "say it again",
        ]:
            with self.subTest(utterance=text):
                self.assertEqual(self._resolve(text).get("name"), "repeat_tts")

    def test_stop_parrot_variants(self):
        for text in [
            "quit parroting",
            "stop copying me",
            "turn off parrot mode",
            "parrot off",
        ]:
            with self.subTest(utterance=text):
                self.assertEqual(self._resolve(text).get("name"), "stop_parrot")

    def test_speak_still_greedy_on_plain_repeat(self):
        """The negative pair: "repeat hello world" still lands on speak."""
        result = self._resolve("repeat hello world")
        self.assertEqual(result.get("name"), "speak")
        self.assertEqual(result.get("entities", {}).get("sentence"), "hello world")

    def test_repeat_after_me_excludes_anchor_from_capture(self):
        """"repeat after me X" must not echo "after me" back as part of X."""
        result = self._resolve("repeat after me the shopping list")
        self.assertEqual(result.get("name"), "speak")
        sentence = result.get("entities", {}).get("sentence", "")
        self.assertNotIn("after me", sentence)
        self.assertEqual(sentence, "the shopping list")


class TestShippedPipelineVariants(unittest.TestCase):
    """Same phrasings through the real MiniCroft (padatious/padacioso stack)."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _capture(self, text, session_id):
        session = Session(session_id)
        session.lang = LANG
        session.pipeline = list(_PIPELINE)
        session.blacklisted_intents = []
        utterance = Message(
            "recognizer_loop:utterance",
            {"utterances": [text], "lang": LANG},
            {"session": session.serialize(), "source": "A", "destination": "B"},
        )
        capture = CaptureSession(self.minicroft, ignore_messages=[])
        capture.capture(utterance, timeout=30)
        return capture.finish()

    def _matched_intent_name(self, messages):
        for message in messages:
            if message.msg_type == "ovos.intent.matched":
                return message.data.get("intent_name")
        return None

    def _speak_sentence(self, messages):
        for message in messages:
            if message.msg_type in ("speak", "ovos.utterance.speak"):
                return message.data.get("utterance")
        return None

    def test_repeat_what_i_just_said_routes_to_repeat_stt(self):
        """The regression pair: variant phrasing must win over speak.intent."""
        messages = self._capture("repeat what I just said", "issue125-1")
        got = self._matched_intent_name(messages)
        self.assertEqual(got, f"{SKILL_ID}:repeat_stt")

    def test_repeat_hello_world_still_routes_to_speak(self):
        """Negative: a genuine echo request is not swallowed by repeat_stt."""
        messages = self._capture("repeat hello world", "issue125-2")
        got = self._matched_intent_name(messages)
        self.assertEqual(got, f"{SKILL_ID}:speak")
        self.assertEqual(self._speak_sentence(messages), "hello world")

    def test_new_stop_phrasings_route_to_stop_parrot(self):
        for i, text in enumerate([
            "quit parroting",
            "stop copying me",
            "turn off parrot mode",
            "parrot off",
        ]):
            with self.subTest(utterance=text):
                messages = self._capture(text, f"issue125-stop-{i}")
                got = self._matched_intent_name(messages)
                self.assertEqual(got, f"{SKILL_ID}:stop_parrot")


if __name__ == "__main__":
    unittest.main()
