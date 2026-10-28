"""Golden rows route to their intent on the m2v prototype pipeline, and
negative rows reach no intent of this skill."""
import hashlib
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovoscope.routing import TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-parrot.openvoiceos"
END2END_DIR = Path(__file__).parent
REPO_ROOT = Path(__file__).resolve().parents[2]


def _rows(prefix):
    rows = []
    for path in sorted(END2END_DIR.glob(f"{prefix}*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    return rows


GOLDEN = _rows("golden_utterances_")
NEGATIVE = _rows("negative_utterances_")
_booted = {}


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


@pytest.fixture(scope="module")
def engine_for():
    def engine(lang):
        if lang not in _booted:
            for minicroft in _booted.values():
                minicroft.stop()
            _booted.clear()
            _booted[lang] = get_prototype_minicroft([SKILL_ID], lang=lang)
            _assert_the_loaded_skill_matches_this_checkout(_booted[lang])
        return _booted[lang].intents.pipeline_plugins["ovos-m2v-prototype-pipeline"]
    yield engine
    for minicroft in _booted.values():
        minicroft.stop()


def _routed(engine, utterance, lang):
    message = Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang}, {"lang": lang})
    match = engine.match_low([utterance], lang, message)
    return [match.match_type] if match else []


def _row_id(row):
    return f"{row['lang']}:{row['utterance']}"


@pytest.mark.parametrize("row", GOLDEN, ids=_row_id)
def test_golden_row_routes_to_its_intent(engine_for, row):
    fired = _routed(engine_for(row["lang"]), row["utterance"], row["lang"])
    TALLY.assert_routed(row["utterance"], f"{SKILL_ID}:{row['intent_label']}", fired)


@pytest.mark.parametrize("row", NEGATIVE, ids=_row_id)
def test_negative_row_reaches_no_intent_of_the_skill(engine_for, row):
    fired = _routed(engine_for(row["lang"]), row["utterance"], row["lang"])
    TALLY.assert_not_routed(row["utterance"],
                            [t for t in fired if t.startswith(f"{SKILL_ID}:")], fired)


def test_every_negative_file_has_a_golden_file():
    negative = {row["lang"] for row in NEGATIVE}
    golden = {row["lang"] for row in GOLDEN}
    assert negative <= golden, f"negatives without golden rows: {sorted(negative - golden)}"


def test_every_shipping_locale_has_a_golden_file():
    golden = {p.stem.split("_", 2)[2] for p in END2END_DIR.glob("golden_utterances_*.jsonl")}
    locale_root = END2END_DIR.parents[1] / "locale"
    shipping = {d.name for d in locale_root.iterdir() if d.is_dir() and any(d.rglob("*.intent"))}
    assert golden == shipping, f"golden files {sorted(golden ^ shipping)} differ from shipping locales"
