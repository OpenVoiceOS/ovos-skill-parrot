"""Multilingual golden-utterance end-to-end coverage for ovos-skill-parrot.

test_golden_utterances.py (superseded by this file) only exercised en-US.
This skill registers six Padatious/Padacioso file-intents (speak,
repeat_tts, repeat_stt, did_you_hear_me, start_parrot, stop_parrot); every
locale under locale/ ships real .intent content for all six. Each golden
row is a literal resolution of that locale's own .intent template lines --
(a|b) alternatives and [a|b]/(a|) optional groups resolve to one concrete
choice -- with speak.intent's {sentence} free slot filled with a fixed
"hello world" placeholder (the slot generalizes to any text; it is not a
closed vocabulary to translate). No translated or invented prose is
introduced.

Unlike ovos-skill-alerts' shared-MiniCroft-with-secondary-langs approach
(blocked by ovoscope#179 at multi-locale scale), this suite follows the
ovos-skill-date-time per-locale pattern (test/end2end/test_intents_it_it.py
on that repo's dev branch): one MiniCroft is booted per locale, in turn,
torn down when the module's tests finish. Only the pure-Python, swig-free
padacioso template engine is booted (no padatious training phase, so no
"mycroft.skills.trained" wait across many locales).
"""
import hashlib
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"

PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-low",
]

END2END_DIR = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]

LANGS = [
    "ca-ES", "da-DK", "de-DE", "en-US", "es-ES", "eu-ES", "fa-IR", "fr-FR",
    "gl-ES", "it-IT", "kab", "nl-NL", "oc-FR", "pt-BR", "pt-PT", "sv-SE",
]

CROSS_LANG_NEGATIVES = [
    ("tell me a joke", "de-DE", "other-skill (jokes) phrasing, german session"),
    ("what's the weather", "fr-FR", "other-skill (weather) phrasing, french session"),
    ("play some music", "es-ES", "other-skill (music) phrasing, spanish session"),
]


def _candidates(skill_id: str, intent_label: str) -> set:
    base = intent_label[:-len(".intent")] if intent_label.endswith(".intent") else intent_label
    return {f"{skill_id}:{intent_label}", f"{skill_id}:{base}"}


def _load_rows(lang):
    path = END2END_DIR / f"golden_utterances_{lang}.jsonl"
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = []
for _lang in LANGS:
    for _row in _load_rows(_lang):
        ALL_ROWS.append(_row)


def _golden_id(row):
    return f"{row['lang']}-{row['intent_label']}-{row['utterance']}"


GOLDEN_ROWS = [pytest.param(r, id=_golden_id(r)) for r in ALL_ROWS]

# One MiniCroft alive at a time. get_minicroft(lang=...) saves the process
# default-session lang at boot and restores it at stop(), so two MiniCrofts
# alive together each hold the OTHER one's lang as "original", and stopping
# them in any order but last-in-first-out leaves the process default on a
# foreign locale. Sixteen of them stopped in dict order left it on pt-PT,
# and every en-US MiniCroft booted later in the same process loaded the
# skill in pt-PT: test_intents_en_us.py failed 6, test_issue_125.py 2. The
# rows are ordered by locale, so the previous MiniCroft is stopped the
# moment the locale changes and the restore chain stays one deep.
_CURRENT = {"lang": None, "mc": None, "error": None}


def _resource_digest(root: Path) -> dict:
    """Map every locale file under ``root`` to a digest of its bytes."""
    locale = root / "locale"
    out = {}
    for path in sorted(locale.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(locale))] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return out


def _assert_the_loaded_skill_matches_this_checkout(mc):
    """The rows come from the checkout; the loaded skill must match it.

    This runner reads its golden rows out of the working tree, but the core
    loads the skill through the venv's ``opm.skill`` entry point. With a
    non-editable install of an OLDER commit, the rows describe intent lines
    the loaded skill does not have, and the suite fails exactly the freshly
    added rows -- two on it-IT against the merge base, where the same tree
    installed editable passed all 36 (harness, T-3347,
    knowledge/wiki/audits/harness/parrot-154-fresh-intent-lines.md).

    That reads as "the new lines are wrong" when the lines are right and the
    environment is stale, which is the most expensive kind of red: it sends
    a reviewer to the resource files.

    What matters is the CONTENT, not the path. A non-editable install is
    normal and correct: the shared workflows install the package and run the
    suite from the checkout, so on a runner the loaded skill legitimately
    lives in site-packages while the rows come from
    /home/runner/work/... Comparing paths would fail every CI run of every
    gold runner in the fleet and prove nothing. Comparing the locale files
    byte for byte passes an install of this commit and fails a stale one,
    which is the defect the guard is named for.

    This rides the boot path rather than living in a test of its own. A
    separate test would have to boot a MiniCroft to have one to look at, and
    under a filtered run (`-k it-IT`) that is a locale the selected rows do
    not want, so it would add a stop-and-boot cycle the suite would not
    otherwise do. The cost is that the message arrives on the first row of
    each locale rather than on a test named for it.
    """
    loaded = Path(mc.plugin_skills[SKILL_ID].instance.root_dir).resolve()
    if loaded == REPO_ROOT:
        return
    here, there = _resource_digest(REPO_ROOT), _resource_digest(loaded)
    if here == there:
        return
    differing = sorted(set(here) ^ set(there)) or sorted(
        name for name in here if here[name] != there.get(name))
    raise AssertionError(
        "the core loaded a copy of this skill whose locale files are not the "
        "ones this runner reads its rows from, so a row failure below would "
        "say nothing about the rows:\n"
        f"  rows and locale files: {REPO_ROOT}\n"
        f"  loaded skill root_dir: {loaded}\n"
        f"  locale files that differ ({len(differing)}): "
        f"{', '.join(differing[:5])}{' ...' if len(differing) > 5 else ''}\n"
        "Reinstall in this tree: unset VIRTUAL_ENV; "
        'uv pip install --python .venv/bin/python --prerelease=allow -e ".[test]"'
    )


def _get_minicroft(lang):
    """The MiniCroft for ``lang``, or the guard's failure for every row of it.

    The guard ran after the cache was filled, so once it raised, the next row
    of the same locale found a cache entry, returned it and never called the
    guard again: one row per locale reported the stale install and the rest ran
    against the mismatched copy and reported their own verdicts. The failure is
    recorded with the entry now, and re-raised for every row of that locale, so
    a mismatched install cannot be reported once and then run on.
    """
    if _CURRENT["lang"] != lang:
        _stop_current()
        # the handle is kept whatever the guard says: an unverified MiniCroft
        # still has to be stopped, or it holds the process default language.
        _CURRENT["mc"] = get_minicroft([SKILL_ID], max_wait=150, lang=lang,
                                       default_pipeline=PIPELINE)
        _CURRENT["lang"] = lang
        try:
            _assert_the_loaded_skill_matches_this_checkout(_CURRENT["mc"])
        except AssertionError as mismatch:
            _CURRENT["error"] = mismatch
    if _CURRENT["error"] is not None:
        raise _CURRENT["error"]
    return _CURRENT["mc"]


def _stop_current():
    if _CURRENT["mc"] is not None:
        _CURRENT["mc"].stop()
    _CURRENT["mc"] = None
    _CURRENT["lang"] = None
    _CURRENT["error"] = None


@pytest.fixture(scope="module", autouse=True)
def _stop_last_minicroft():
    yield
    _stop_current()


def _types(mc, text, lang, session_id):
    session = Session(session_id)
    session.lang = lang
    session.pipeline = list(PIPELINE)
    session.blacklisted_intents = []
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": lang},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(mc, eof_msgs=["mycroft.skill.handler.start"])
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


@pytest.mark.timeout(180)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=_golden_id)
def test_golden_utterance_multilang(row):
    mc = _get_minicroft(row["lang"])
    candidates = _candidates(SKILL_ID, row["intent_label"])
    types = _types(mc, row["utterance"], row["lang"], f"golden-{_golden_id(row)}")
    assert any(t in candidates for t in types), (
        f"[{row['lang']}] {row['utterance']!r}: expected one of {sorted(candidates)!r}, got {types!r}"
    )


@pytest.mark.timeout(180)
@pytest.mark.parametrize("negative", CROSS_LANG_NEGATIVES, ids=lambda n: f"{n[1]}-{n[0]}")
def test_cross_language_negative(negative):
    text, lang, _why = negative
    mc = _get_minicroft(lang)
    types = _types(mc, text, lang, f"negative-{lang}-{text}")
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"[{lang}] {text!r} was incorrectly claimed by {SKILL_ID}"
