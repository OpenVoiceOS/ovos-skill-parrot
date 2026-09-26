"""The gold runner's stale-install guard, tested without booting anything.

``_assert_the_loaded_skill_matches_this_checkout`` is what separates "the rows
passed" from "the rows were asserted against the locale files in this tree".
The runner reads its rows from the checkout while the core loads the skill
through the venv's ``opm.skill`` entry point, so a non-editable install of an
older commit makes the suite fail exactly the freshly added rows and blame the
resource files. Two on it-IT against parrot#154's merge base, where the same
tree installed editable passed all 36 (harness T-3347,
``knowledge/wiki/audits/harness/parrot-154-fresh-intent-lines.md``).

The guard compares locale CONTENT, not paths, and these tests are mostly here
to pin that. A non-editable install is normal: the shared workflows install the
package and run the suite from the checkout, so on a GitHub runner the loaded
skill lives in ``/opt/hostedtoolcache/.../site-packages/ovos_skill_parrot``
while the rows come from ``/home/runner/work/...``. A path comparison fails
that, which is every CI run of every gold runner in the fleet, while proving
nothing about the rows. Measured: the first version of this guard compared paths
and turned this repository's own CI red on 16 locales and 5 Pythons.

The guard's docstring explains why it rides the boot path instead of living in a
test that needs a core. That argument is about a MiniCroft; the predicate itself
reads two directories, so it can be pinned with temporary trees and no boot.
"""
import shutil
from pathlib import Path

import pytest

from . import test_golden_utterances_multilang as runner
from .test_golden_utterances_multilang import (
    REPO_ROOT, SKILL_ID, _assert_the_loaded_skill_matches_this_checkout,
)


class _StubInstance:
    def __init__(self, root_dir):
        self.root_dir = str(root_dir)


class _StubLoader:
    def __init__(self, root_dir):
        self.instance = _StubInstance(root_dir)


class _CountingStubMinicroft:
    """A stub the runner's own cache can hold: it also counts its stop()."""

    def __init__(self, root_dir):
        self.plugin_skills = {SKILL_ID: _StubLoader(root_dir)}
        self.stops = 0

    def stop(self):
        self.stops += 1


class _StubMinicroft:
    """Only what the guard reads: plugin_skills[SKILL_ID].instance.root_dir."""

    def __init__(self, root_dir):
        self.plugin_skills = {SKILL_ID: _StubLoader(root_dir)}


def _install_copy(tmp_path: Path) -> Path:
    """A copy of this skill's locale tree, standing in for an install."""
    root = tmp_path / "site-packages" / "ovos_skill_parrot"
    shutil.copytree(REPO_ROOT / "locale", root / "locale")
    return root


def test_the_checkout_itself_is_accepted():
    """The editable case: root_dir is the checkout, so there is nothing to
    compare and the guard returns before reading any file."""
    _assert_the_loaded_skill_matches_this_checkout(_StubMinicroft(REPO_ROOT))


def test_an_identical_install_is_accepted(tmp_path):
    """The case a path comparison got wrong, and the reason for this rewrite.

    An install of THIS commit is what CI does on every push. Its locale files
    are identical to the checkout's, so the rows are asserted against exactly
    the content in the tree and the guard must stay quiet.
    """
    _assert_the_loaded_skill_matches_this_checkout(
        _StubMinicroft(_install_copy(tmp_path)))


def test_an_install_with_a_changed_line_is_rejected(tmp_path):
    """The T-3347 defect in miniature: the installed copy is a different tree.

    A stale install differs from the checkout in the locale files the rows
    depend on. One changed line is enough to make every row that needs it fail
    for a reason the row cannot express.
    """
    installed = _install_copy(tmp_path)
    target = installed / "locale" / "it-IT" / "did_you_hear_me.intent"
    target.write_text("mi puoi sentire?\n", encoding="utf-8")
    with pytest.raises(AssertionError) as caught:
        _assert_the_loaded_skill_matches_this_checkout(_StubMinicroft(installed))
    message = str(caught.value)
    assert str(installed) in message, "the failure must name what was loaded"
    assert str(REPO_ROOT) in message, "the failure must name the checkout"
    assert "did_you_hear_me.intent" in message, \
        "the failure must name the file that differs"
    assert "-e " in message, "the failure must say how to fix it"


def test_an_install_missing_a_file_is_rejected(tmp_path):
    """The shape of a genuinely older install: a file the checkout has added
    does not exist there at all."""
    installed = _install_copy(tmp_path)
    (installed / "locale" / "it-IT" / "did_you_hear_me.intent").unlink()
    with pytest.raises(AssertionError) as caught:
        _assert_the_loaded_skill_matches_this_checkout(_StubMinicroft(installed))
    assert "did_you_hear_me.intent" in str(caught.value)


def test_an_install_with_an_extra_file_is_rejected(tmp_path):
    """The reverse: the installed copy is NEWER than the checkout. Just as
    wrong, and a symmetric difference catches it where a one-way walk would
    not."""
    installed = _install_copy(tmp_path)
    (installed / "locale" / "it-IT" / "invented.intent").write_text(
        "qualcosa\n", encoding="utf-8")
    with pytest.raises(AssertionError) as caught:
        _assert_the_loaded_skill_matches_this_checkout(_StubMinicroft(installed))
    assert "invented.intent" in str(caught.value)


@pytest.fixture
def stubbed_boot(monkeypatch):
    """Drive the runner's cache without booting anything.

    ``_get_minicroft`` is the code under test here, not the predicate: the
    defect was the ORDER of the cache write and the guard call, so it can only
    be pinned through the cache.
    """
    booted = []

    def _fake_get_minicroft(skill_ids, **kwargs):
        mc = _CountingStubMinicroft(_fake_get_minicroft.root_dir)
        booted.append(mc)
        return mc

    _fake_get_minicroft.root_dir = REPO_ROOT
    monkeypatch.setattr(runner, "get_minicroft", _fake_get_minicroft)
    monkeypatch.setattr(runner, "_CURRENT",
                        {"lang": None, "mc": None, "error": None})
    yield _fake_get_minicroft, booted


def test_a_matching_install_is_cached_and_booted_once(stubbed_boot):
    """The normal path: two rows of one locale share one MiniCroft."""
    fake, booted = stubbed_boot
    first = runner._get_minicroft("it-IT")
    second = runner._get_minicroft("it-IT")
    assert first is second
    assert len(booted) == 1, "the second row must not boot a second MiniCroft"


def test_every_row_of_a_locale_fails_on_a_stale_install(stubbed_boot, tmp_path):
    """The defect this test exists for.

    The guard used to run after the cache was filled, so the SECOND row of a
    locale was served the cached MiniCroft and never reached the guard: the
    stale install was reported once per locale and every later row ran against
    the mismatched copy. Both rows must fail, with the same message.
    """
    fake, booted = stubbed_boot
    fake.root_dir = _install_copy(tmp_path)
    (fake.root_dir / "locale" / "it-IT" / "did_you_hear_me.intent").write_text(
        "mi puoi sentire?\n", encoding="utf-8")

    with pytest.raises(AssertionError) as first:
        runner._get_minicroft("it-IT")
    with pytest.raises(AssertionError) as second:
        runner._get_minicroft("it-IT")

    assert "did_you_hear_me.intent" in str(first.value)
    assert str(second.value) == str(first.value), \
        "the second row must fail for the same reason, not run on"
    assert len(booted) == 1, "the failure must not re-boot per row"


def test_the_unverified_minicroft_is_still_stopped(stubbed_boot, tmp_path):
    """A MiniCroft that failed the guard still holds the process default lang.

    It is kept in the cache for exactly that reason: the locale change (and the
    module teardown) must be able to stop it.
    """
    fake, booted = stubbed_boot
    fake.root_dir = _install_copy(tmp_path)
    (fake.root_dir / "locale" / "it-IT" / "invented.intent").write_text(
        "qualcosa\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        runner._get_minicroft("it-IT")
    runner._stop_current()
    assert booted[0].stops == 1


def test_the_failure_does_not_leak_into_the_next_locale(stubbed_boot, tmp_path):
    """A recorded failure is the current locale's, not the suite's.

    After a stale-install failure on one locale, a locale change re-boots and
    re-verifies. With a matching install, the next locale must run.
    """
    fake, booted = stubbed_boot
    fake.root_dir = _install_copy(tmp_path)
    (fake.root_dir / "locale" / "it-IT" / "invented.intent").write_text(
        "qualcosa\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        runner._get_minicroft("it-IT")

    fake.root_dir = REPO_ROOT
    mc = runner._get_minicroft("de-DE")
    assert mc is booted[-1]
    assert runner._CURRENT["error"] is None
