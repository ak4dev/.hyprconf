"""
Integration tests for the dev → stable release pipeline.

These tests exercise subprocess-level behaviour:
  - git archive produces a correctly filtered release tarball
  - scripts/publish --dry-run runs end-to-end without network access

They run as part of tier-2 (integration) so they do not require a VM.
"""

from __future__ import annotations

import subprocess
import tarfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# Paths that must be absent from the release archive.
EXPORT_IGNORED = [
    "tests/",
    "scripts/",
    ".github/",
    "AGENTS.md",
    "Makefile",
    "pyproject.toml",
]

# Paths that must be present in the release archive.
REQUIRED_IN_ARCHIVE = [
    ".hyprconf/stow/",
    ".hyprconf/setup.sh",
    ".hyprconf/install/",
    ".hyprconf/packages",
]


# ---------------------------------------------------------------------------
# git archive
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def release_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the release archive once and share it across tests in this module."""
    tmp = tmp_path_factory.mktemp("archive")
    archive = tmp / "release.tar.gz"
    result = subprocess.run(
        [
            "git",
            "archive",
            "--worktree-attributes",
            "--format=tar.gz",
            "--prefix=.hyprconf/",
            "-o",
            str(archive),
            "HEAD",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"git archive failed: {result.stderr}"
    return archive


def test_git_archive_excludes_dev_only_paths(release_archive: Path) -> None:
    """Release archive must not contain tests/, scripts/, .github/, etc."""
    with tarfile.open(release_archive) as tf:
        members = [m.name for m in tf.getmembers()]

    for excluded in EXPORT_IGNORED:
        hits = [m for m in members if f".hyprconf/{excluded}" in m]
        assert not hits, f"Export-ignored path {excluded!r} found in archive: {hits[:3]}"


def test_git_archive_includes_required_paths(release_archive: Path) -> None:
    """Release archive must contain stow/, setup.sh, install/, packages."""
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


def _on_dev_with_clean_tree() -> bool:
    """Return True iff we are on dev with an unmodified working tree."""
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if branch.stdout.strip() != "dev":
        return False
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return status.stdout.strip() == ""


def test_publish_dry_run_succeeds(tmp_path: Path) -> None:
    """scripts/publish --dry-run completes end-to-end, hermetically.

    The pipeline runs against an isolated clone whose ``origin`` is the local
    source repo, so its ``git fetch origin dev`` needs no network or remote auth
    (a transient fetch failure against the real remote used to abort the run and
    flake CI) and shares no ``.git`` with parallel xdist workers.

    Flags used:
      --dry-run       build archive locally, skip branch/tag pushes
      --skip-tests    skip the full test suite (already running it here)
      --skip-tag      skip annotated tag creation
    """
    if not _on_dev_with_clean_tree():
        pytest.skip("Not on dev branch with a clean working tree")

    # Clone the (dev, clean) source repo to an isolated tree. `git clone <path>`
    # points the clone's origin at the local REPO_ROOT, so the publish's
    # `git fetch origin dev` resolves locally — no network, no shared .git.
    clone = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", "--quiet", str(REPO_ROOT), str(clone)],
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


def test_publish_script_updates_local_stable_branch() -> None:
    """scripts/publish must update the local stable branch after pushing to origin.

    Previously, publish only ran ``git push origin HEAD:stable`` which updated
    the remote ref but left the local ``stable`` branch at its old position,
    causing ``local stable`` and ``origin/stable`` to diverge after every
    release.  The fix adds ``git branch -f stable HEAD`` immediately after the
    push.
    """
    text = (REPO_ROOT / "scripts" / "publish").read_text()
    # The fix must appear: force-move the local stable branch after the push.
    assert "git branch -f" in text, (
        "scripts/publish must run 'git branch -f <stable> HEAD' after pushing "
        "to origin/stable to keep the local branch in sync"
    )
    # Specifically it must update the stable branch, not some other branch.
    import re

    assert re.search(r'git branch -f[^"]*"?\$\{?STABLE_BRANCH\}?"?\s+HEAD', text), (
        "scripts/publish must force-move the local stable branch to HEAD "
        "after 'git push origin HEAD:stable'"
    )
