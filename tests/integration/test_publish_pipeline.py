"""
Integration tests for the omarchy → stable release pipeline.

scripts/publish --dry-run is run end-to-end against an isolated clone: no
Omarchy host, no network, and nothing in this checkout is pushed, tagged or
mutated. The static invariants of the script live in tests/unit/test_release.py.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# The branch scripts/publish promotes from (its WORK_BRANCH).
WORK_BRANCH = "omarchy"


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


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
    assert "archive" not in result.stdout.lower(), (
        "help text still advertises the deleted release archive"
    )


def test_publish_dry_run_succeeds(tmp_path: Path) -> None:
    """scripts/publish --dry-run completes end-to-end, hermetically.

    The pipeline runs against an isolated clone whose ``origin`` is the local
    source repo, so its ``git fetch origin omarchy`` needs no network or remote
    auth (a transient fetch failure against the real remote used to abort the
    run and flake CI) and shares no ``.git`` with parallel xdist workers.

    Flags used:
      --dry-run       run the gates, skip branch/tag pushes
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
    # Nothing is built: the promoted branch is the release (no dist/ tarball).
    assert not (clone / "dist").exists(), "--dry-run still wrote a dist/ archive"
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
