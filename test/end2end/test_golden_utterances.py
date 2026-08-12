"""Golden-utterance end-to-end coverage for ovos-skill-parrot (en-US).

The golden corpus (``golden_utterances.jsonl``) is a vendored slice of the
shared ovoscope golden-utterance dataset, keyed by
``skill_id == "ovos-skill-parrot.openvoiceos"``. Every row is a realistic
utterance a user might actually say, together with the intent it must route
to. This suite drives each row through a single, shared ``MiniCroft`` and
asserts the skill's Padatious intent binding, plus a handful of confusable
utterances lifted from *other* skills' corpus slices to prove this skill does
not over-claim them.

Naming note: the corpus encodes multi-word intents with dots (e.g.
``"repeat.stt.intent"``, ``"did.you.hear.me.intent"``) but this skill's
locale files/intent ids use underscores (``repeat_stt.intent``,
``did_you_hear_me.intent``) and the runtime intent name emitted on
``ovos.intent.matched`` drops the ``.intent`` suffix entirely (OVOS-INTENT-2
naming). ``_normalize_intent_label`` bridges the two so the assertion
compares against the real, current intent identity rather than the corpus's
literal string.
"""
import json
import unittest
from pathlib import Path

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
LANG = "en-US"

_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
]

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"

# utterances lifted verbatim from OTHER skills' golden-utterance slices,
# picked because they share parrot-adjacent vocabulary ("tell me", "say").
# "say a joke" (icanhazdadjokes) was deliberately excluded: it also matches
# this skill's speak.intent template ("say {sentence}") by design, so it is
# not a confusable pair, it's a genuine (and expected) two-skill overlap.
NEGATIVE_UTTERANCES = [
    ("tell me a joke", "ovos-skill-icanhazdadjokes.openvoiceos"),
    ("Tell me my fortune", "ovos-skill-randomness.openvoiceos"),
    ("can you tell me the weather", "ovos-skill-weather.openvoiceos"),
    ("Tell me about the movie Stripes", "ovos-skill-moviemaster.openvoiceos"),
    ("tell me the word of the day", "ovos-skill-word-of-the-day.openvoiceos"),
    ("what does word net say about word", "ovos-skill-wordnet.openvoiceos"),
    ("can you tell me the spelling of word", "ovos-skill-spelling.openvoiceos"),
]


def _normalize_intent_label(intent_label: str) -> str:
    """corpus "did.you.hear.me.intent" -> runtime "did_you_hear_me"."""
    base = intent_label[:-len(".intent")] if intent_label.endswith(".intent") else intent_label
    return base.replace(".", "_")


def _load_golden_rows():
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


GOLDEN_ROWS = _load_golden_rows()


class TestParrotGoldenUtterances(unittest.TestCase):
    """One MiniCroft boot for the whole suite; per-utterance capture below."""

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
        # blacklisted_intents defaults to None on a fresh Session, which
        # crashes the padacioso pipeline (NoneType membership test).
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

    def test_golden_utterances(self):
        """Every golden row must route to its expected padatious intent."""
        assert GOLDEN_ROWS, "golden_utterances.jsonl produced no rows"
        failures = []
        for i, row in enumerate(GOLDEN_ROWS):
            expected = f"{SKILL_ID}:{_normalize_intent_label(row['intent_label'])}"
            with self.subTest(utterance=row["utterance"]):
                messages = self._capture(row["utterance"], f"golden-{i}")
                got = self._matched_intent_name(messages)
                if got != expected:
                    failures.append((row["utterance"], expected, got))
        if failures:
            details = "\n".join(
                f"  {u!r}: expected {exp!r}, got {got!r}" for u, exp, got in failures
            )
            self.fail(f"{len(failures)}/{len(GOLDEN_ROWS)} golden utterances mis-routed:\n{details}")

    def test_repeat_handlers_complete_without_error_on_fresh_session(self):
        """Regression: repeat_tts/repeat_stt must not raise on a session that
        has never had a prior ``speak`` (repeat_tts) / never mattered before
        (repeat_stt) event recorded for it.

        A brand-new session only gets its ``parrot_sessions`` entry from
        ``on_utterance`` (fired for the very same ``recognizer_loop:utterance``
        message that triggers the intent match), which never populated
        ``prev_tts`` (only ``on_speak`` does that). Before the fix,
        ``handle_repeat_tts`` indexed ``self.parrot_sessions[sid]["prev_tts"]``
        directly and raised ``KeyError: 'prev_tts'`` after the intent had
        already correctly matched and dispatched -- observable on the bus as
        ``mycroft.skill.handler.error`` / ``ovos.intent.handler.error``
        instead of a normal ``mycroft.skill.handler.complete``.
        """
        cases = [
            ("Can you repeat that?", "repeat_tts"),
            ("What did I just say?", "repeat_stt"),
        ]
        failures = []
        for i, (text, intent_name) in enumerate(cases):
            with self.subTest(utterance=text, intent_name=intent_name):
                messages = self._capture(text, f"repeat-regression-{i}")
                handler_name = f"ParrotSkill.handle_{intent_name}"

                error_messages = [
                    m for m in messages
                    if m.msg_type in ("mycroft.skill.handler.error", "ovos.intent.handler.error")
                ]
                complete_messages = [
                    m for m in messages
                    if m.msg_type == "mycroft.skill.handler.complete"
                    and m.data.get("name") == handler_name
                ]
                spoke = any(
                    m.msg_type in ("speak", "ovos.utterance.speak") for m in messages
                )

                if error_messages:
                    failures.append(
                        f"{text!r} ({intent_name}): handler errored: "
                        f"{[m.data for m in error_messages]}"
                    )
                elif not complete_messages:
                    failures.append(
                        f"{text!r} ({intent_name}): no {handler_name!r} "
                        f"mycroft.skill.handler.complete observed"
                    )
                elif not spoke:
                    failures.append(f"{text!r} ({intent_name}): handler never spoke")

        if failures:
            self.fail("repeat handler regression:\n" + "\n".join(f"  {f}" for f in failures))

    def test_negative_confusables_not_claimed(self):
        """Utterances belonging to other skills must not be claimed by parrot."""
        assert len(NEGATIVE_UTTERANCES) >= 5
        failures = []
        for i, (text, source_skill) in enumerate(NEGATIVE_UTTERANCES):
            with self.subTest(utterance=text, source_skill=source_skill):
                messages = self._capture(text, f"negative-{i}")
                claimed = any(
                    m.msg_type.startswith(f"{SKILL_ID}:") for m in messages
                )
                if claimed:
                    failures.append((text, source_skill))
        if failures:
            details = "\n".join(f"  {u!r} (from {s})" for u, s in failures)
            self.fail(f"parrot incorrectly claimed {len(failures)} confusable utterance(s):\n{details}")


if __name__ == "__main__":
    unittest.main()
