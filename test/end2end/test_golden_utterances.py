"""Golden rows in every locale route to their intent on the m2v pipeline.

For each ``golden_utterances_<lang>.jsonl`` in this directory, one MiniCroft
loads the real skill in that language on the m2v prototype pipeline, the
model2vec engine built at boot from the skill's own ``.intent`` files. Each
row's utterance goes through that pipeline's high, medium and low tiers in
order, and the row passes when the first tier to match names its
``intent_label``. The engine embeds the utterance, so a row that no template
spells out word for word still matches when it means the same thing.

Each locale must pass at least ``MIN_MATCH_RATE`` of its rows. All rows run,
including rows marked ``needs_manual`` or ``machine_generated``, and the test
prints every row that misses with the intent that matched instead.

``negative_utterances_<lang>.jsonl`` holds requests for other skills. On the
same MiniCroft, each one must match none of this skill's intents, except a
claim recorded by name in ``NEGATIVE_KNOWN_CLAIMS``. Every intent with rows in a
locale must match at least ``MIN_MATCHED_ROWS_PER_INTENT`` of them.
"""
import hashlib
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovoscope import M2V_PUBLISHED_MODEL, get_m2v_minicroft
from ovoscope.golden_minicroft import warm_m2v_models

SKILL_ID = "ovos-skill-parrot.openvoiceos"
M2V_PROTOTYPE = "ovos-m2v-prototype-pipeline"
TIERS = ("high", "medium", "low")
# m2v gives some rows a different answer on each boot, so the test gates on
# the share of rows that match per locale, not on each row.
MIN_MATCH_RATE = 0.8
# every intent with rows in a locale must match at least this many of them,
# so a locale cannot lose a whole intent behind a good overall rate
MIN_MATCHED_ROWS_PER_INTENT = 1
# a negative the engine claims in two runs, by name: {lang: {utterance: intent}}.
# Any other claimed negative fails the locale.
NEGATIVE_KNOWN_CLAIMS = {}
END2END_DIR = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]


def _rows_by_lang(prefix="golden_utterances_"):
    rows = {}
    for path in sorted(END2END_DIR.glob(f"{prefix}*.jsonl")):
        lang = path.stem.removeprefix(prefix)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                assert row["lang"] == lang, f"{path.name}:{number} has lang {row['lang']!r}"
                rows.setdefault(lang, []).append(row)
    return rows


ROWS = _rows_by_lang()
NEGATIVES = _rows_by_lang("negative_utterances_")


def _resource_digest(root: Path) -> dict:
    """Map every locale file under ``root`` to a digest of its bytes."""
    locale = root / "locale"
    return {str(path.relative_to(locale)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(locale.rglob("*")) if path.is_file()}


def _assert_the_loaded_skill_matches_this_checkout(mc):
    """The rows come from the checkout; the loaded skill must match it.

    The core loads the skill through the venv's ``opm.skill`` entry point. A
    non-editable install is normal (CI installs the package and runs the suite
    from the checkout), so the guard compares locale CONTENT, not paths. A
    stale install of an older commit makes the freshly added rows fail and
    points the reader at resource files that are right.
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


def _matched_intent(engine, utterance, lang):
    message = Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang}, {"lang": lang})
    match = next(filter(None, (getattr(engine, f"match_{tier}")([utterance], lang, message)
                               for tier in TIERS)), None)
    return match.match_type if match else None


@pytest.mark.timeout(900)
@pytest.mark.parametrize("lang", sorted(ROWS))
def test_golden_rows_match_their_intent(lang):
    minicroft = get_m2v_minicroft([SKILL_ID], model=M2V_PUBLISHED_MODEL,
                                  lang=lang, classifier=False)
    try:
        _assert_the_loaded_skill_matches_this_checkout(minicroft)
        warm_m2v_models(minicroft)
        engine = minicroft.intents.pipeline_plugins[M2V_PROTOTYPE]
        misses = []
        matched = {}
        for row in ROWS[lang]:
            expected = f"{SKILL_ID}:{row['intent_label']}"
            got = _matched_intent(engine, row["utterance"], lang)
            matched.setdefault(row["intent_label"], 0)
            if got == expected:
                matched[row["intent_label"]] += 1
            else:
                misses.append(f"{row['utterance']!r}: expected {row['intent_label']}, got {got}")
        known = NEGATIVE_KNOWN_CLAIMS.get(lang, {})
        claimed = []
        for row in NEGATIVES.get(lang, []):
            got = _matched_intent(engine, row["utterance"], lang)
            if got and got.startswith(f"{SKILL_ID}:") and known.get(row["utterance"]) != got.split(":", 1)[1]:
                claimed.append(f"{row['utterance']!r}: claimed by {got}")
    finally:
        minicroft.stop()
    rate = 1 - len(misses) / len(ROWS[lang])
    print(f"[{lang}] {rate:.1%} of {len(ROWS[lang])} rows match", *misses, sep="\n  ")
    starved = sorted(label for label, n in matched.items() if n < MIN_MATCHED_ROWS_PER_INTENT)
    if NEGATIVES.get(lang):
        print(f"[{lang}] {len(claimed)} of {len(NEGATIVES[lang])} negatives claimed", *claimed, sep="\n  ")
    failures = []
    if rate < MIN_MATCH_RATE:
        failures.append(f"{rate:.1%} of rows match, below {MIN_MATCH_RATE:.0%}:\n  " + "\n  ".join(misses))
    if starved:
        failures.append(f"intents with fewer than {MIN_MATCHED_ROWS_PER_INTENT} matched rows: {starved}")
    if claimed:
        failures.append("negatives claimed by this skill:\n  " + "\n  ".join(claimed))
    assert not failures, f"[{lang}] " + f"\n[{lang}] ".join(failures)


def test_every_negative_file_has_a_golden_file():
    assert set(NEGATIVES) <= set(ROWS), f"negatives without golden rows: {sorted(set(NEGATIVES) - set(ROWS))}"


def test_every_shipping_locale_has_a_golden_file():
    golden = {p.stem.split("_", 2)[2] for p in END2END_DIR.glob("golden_utterances_*.jsonl")}
    locale_root = END2END_DIR.parents[1] / "locale"
    shipping = {d.name for d in locale_root.iterdir() if d.is_dir() and any(d.rglob("*.intent"))}
    assert golden == shipping, f"golden files {sorted(golden ^ shipping)} differ from shipping locales"
