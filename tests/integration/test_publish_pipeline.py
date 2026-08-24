"""
Integration tests for the omarchy → stable release pipeline.

These tests exercise subprocess-level behaviour:
  - git archive produces a correctly filtered release tarball
  - scripts/publish --dry-run runs end-to-end without network access

They run as part of tier-2 (integration): no Omarchy host, no network, and
nothing in this checkout is pushed, tagged or mutated.
"""

from __future__ import annotations

import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# The branch scripts/publish promotes from (its WORK_BRANCH).
WORK_BRANCH = "omarchy"

# Paths that must be absent from the release archive.
EXPORT_IGNORED = [
    "tests/",
    "scripts/",
    ".github/",
    "web/",
    "docs/",
    "AGENTS.md",
    "Makefile",
    ".editorconfig",
    "pyproject.toml",
    "__pycache__/",
]

# Paths that must be present in the release archive — the overlay's install
# payload, rooted at the .hyprconf/ prefix install.sh expects.
REQUIRED_IN_ARCHIVE = [
    ".hyprconf/install.sh",
    ".hyprconf/hypr/",
    ".hyprconf/lib/",
    ".hyprconf/bin/",
    ".hyprconf/packages",
    ".hyprconf/plugins/",
    ".hyprconf/themes/",
    ".hyprconf/zsh/",
    ".hyprconf/kitty/",
    ".hyprconf/hooks/",
    ".hyprconf/infra/",
]


def _git(*args: str, cwd: Path = REPO_ROOT, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# git archive
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def release_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the release archive once and share it across tests in this module.

    scripts/publish archives ``HEAD`` after its pre-flight has proven the tree
    clean, i.e. index == HEAD. To assert the same thing on a checkout that may
    have staged-but-uncommitted changes (a restructure in flight) the archive is
    cut from the *index* tree instead — identical to HEAD whenever publish would
    run. The index is copied and new objects land in a scratch object directory
    (the real store is only an alternate), so this never mutates the checkout.
    """
    tmp = tmp_path_factory.mktemp("archive")
    scratch_objects = tmp / "objects"
    scratch_objects.mkdir()
    index_copy = tmp / "index"
    index_copy.write_bytes(Path(_git("rev-parse", "--git-path", "index")).read_bytes())

    env = dict(os.environ)
    env["GIT_INDEX_FILE"] = str(index_copy)
    env["GIT_OBJECT_DIRECTORY"] = str(scratch_objects)
    env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(
        (REPO_ROOT / _git("rev-parse", "--git-path", "objects")).resolve()
    )
    tree = _git("write-tree", env=env)

    archive = tmp / "release.tar.gz"
    _git(
        "archive",
        "--worktree-attributes",
        "--format=tar.gz",
        "--prefix=.hyprconf/",
        "-o",
        str(archive),
        tree,
        env=env,
    )
    return archive


def test_git_archive_excludes_dev_only_paths(release_archive: Path) -> None:
    """Release archive must not contain tests/, scripts/, .github/, web/, docs/, etc."""
    with tarfile.open(release_archive) as tf:
        members = [m.name for m in tf.getmembers()]

    for excluded in EXPORT_IGNORED:
        hits = [m for m in members if f"/{excluded}" in m or m.endswith(f"/{excluded}")]
        assert not hits, f"Export-ignored path {excluded!r} found in archive: {hits[:3]}"
    pyc = [m for m in members if m.endswith(".pyc")]
    assert not pyc, f"Compiled Python found in archive: {pyc[:3]}"


def test_git_archive_includes_required_paths(release_archive: Path) -> None:
    """Release archive must contain the overlay's install payload roots."""
    with tarfile.open(release_archive) as tf:
        members = [m.name for m in tf.getmembers()]

    for required in REQUIRED_IN_ARCHIVE:
        assert any(m.startswith(required) for m in members), (
            f"Required path {required!r} missing from release archive"
        )


def test_git_archive_prefix_is_hyprconf(release_archive: Path) -> None:
    """Every archive entry must be rooted at .hyprconf/."""
    with tarfile.open(release_archive) as tf:
        members = [m.name for m in tf.getmembers()]
    non_prefixed = [m for m in members if not m.startswith(".hyprconf")]
    assert not non_prefixed, f"Archive entries without .hyprconf/ prefix: {non_prefixed[:5]}"


# ---------------------------------------------------------------------------
# scripts/publish dry-run
# ---------------------------------------------------------------------------


def _on_work_branch_with_clean_tree() -> bool:
    """Return True iff we are on the omarchy branch with an unmodified working tree."""
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if branch.stdout.strip() != WORK_BRANCH:
        return False
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return status.stdout.strip() == ""


def test_publish_help_describes_omarchy_to_stable() -> None:
    """``scripts/publish --help`` prints the usage header and exits 0 without touching git."""
    result = subprocess.run(
        ["bash", "scripts/publish", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--dry-run" in result.stdout
    assert "omarchy" in result.stdout and "stable" in result.stdout
    assert "lib/hyprconf/__init__.py" in result.stdout
    assert not re.search(r"\b(vm|install)\b.*tier", result.stdout, re.IGNORECASE), (
        "help text still advertises the deleted VM/install tiers"
    )


def test_publish_dry_run_succeeds(tmp_path: Path) -> None:
    """scripts/publish --dry-run completes end-to-end, hermetically.

    The pipeline runs against an isolated clone whose ``origin`` is the local
    source repo, so its ``git fetch origin omarchy`` needs no network or remote
    auth (a transient fetch failure against the real remote used to abort the
    run and flake CI) and shares no ``.git`` with parallel xdist workers.

    Flags used:
      --dry-run       build archive locally, skip branch/tag pushes
      --skip-tests    skip the lint gates + test suite (already running it here)
      --skip-tag      skip annotated tag creation
    """
    if not _on_work_branch_with_clean_tree():
        pytest.skip(f"Not on {WORK_BRANCH} branch with a clean working tree")

    # Clone the (omarchy, clean) source repo to an isolated tree. `git clone
    # <path>` points the clone's origin at the local REPO_ROOT, so the publish's
    # `git fetch origin omarchy` resolves locally — no network, no shared .git.
    clone = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", "--quiet", "--branch", WORK_BRANCH, str(REPO_ROOT), str(clone)],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    result = subprocess.run(
        [
            "bash",
            "scripts/publish",
            "--dry-run",
            "--skip-tests",
            "--skip-tag",
        ],
        cwd=clone,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"scripts/publish --dry-run failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The pipeline must emit the "Done" confirmation.
    assert "Done" in result.stdout, f"Expected 'Done' in publish output:\n{result.stdout}"
    # A release archive must have been written to the clone's dist/.
    dist_archives = list((clone / "dist").glob("hyprconf-*.tar.gz"))
    assert dist_archives, "No hyprconf-*.tar.gz found in dist/ after --dry-run"
    # Dry-run must leave the clone clean: the bump is reverted, nothing committed.
    status = _git("status", "--porcelain", cwd=clone)
    assert status == "", f"--dry-run left the clone dirty:\n{status}"
    assert _git("rev-parse", "HEAD", cwd=clone) == _git(
        "rev-parse", f"origin/{WORK_BRANCH}", cwd=clone
    )


def test_publish_script_updates_local_stable_branch() -> None:
    """scripts/publish must update the local stable branch after pushing to origin.

    ``git push origin HEAD:stable`` alone updates the remote ref but leaves the
    local ``stable`` branch at its old position, so ``stable`` and
    ``origin/stable`` diverge after every release. The publish must run
    ``git branch -f stable HEAD`` immediately after the push.
    """
    text = (REPO_ROOT / "scripts" / "publish").read_text()
    # The fix must appear: force-move the local stable branch after the push.
    assert "git branch -f" in text, (
        "scripts/publish must run 'git branch -f <stable> HEAD' after pushing "
        "to origin/stable to keep the local branch in sync"
    )
    # Specifically it must update the stable branch, not some other branch.
    assert re.search(r'git branch -f[^"]*"?\$\{?STABLE_BRANCH\}?"?\s+HEAD', text), (
        "scripts/publish must force-move the local stable branch to HEAD "
        "after 'git push origin HEAD:stable'"
    )
