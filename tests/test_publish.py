"""scripts/publish, the dev -> stable release pipeline, end to end against a throwaway
repository: a bare origin seeded with the script and VERSION, a clone of it on dev, and a
recording `make` on PATH. Nothing in this checkout is read through git, pushed or tagged."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import git

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISH = "scripts/publish"


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    seed = tmp_path / "seed"
    for rel in (PUBLISH, "VERSION"):
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_bytes((REPO_ROOT / rel).read_bytes())
    git(seed, "init", "-q", "-b", "dev")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    git(tmp_path, "clone", "-q", "--branch", "dev", "origin.git", "clone")
    return tmp_path / "clone"


def publish(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    bins = clone.parent / "bins"
    bins.mkdir(exist_ok=True)
    make = bins / "make"
    make.write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$1" >> "$FAKE_CALLS"\n')
    make.chmod(make.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "FAKE_CALLS": str(clone.parent / "make-calls")}
    env["PATH"] = f"{bins}:{env['PATH']}"
    cmd = ["bash", PUBLISH, *args]
    return subprocess.run(cmd, cwd=clone, capture_output=True, text=True, timeout=120, env=env)


def gates(clone: Path) -> list[str]:
    calls = clone.parent / "make-calls"
    return calls.read_text().splitlines() if calls.exists() else []


def tag(clone: Path) -> str:
    return "v" + (clone / "VERSION").read_text().strip()


def test_publish_promotes_dev_to_stable(clone: Path) -> None:
    """Gates in CI's order, the annotated tag at HEAD, one atomic push of dev, stable and the
    tag; a rerun reuses the tag at HEAD, which is how a run that died on the push resumes."""
    head = git(clone, "rev-parse", "HEAD")
    result = publish(clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert gates(clone) == ["lint", "shellcheck", "test"]
    assert git(clone, "rev-parse", "HEAD") == head, "the release needs no commit of its own"
    assert git(clone, "status", "--porcelain") == ""
    assert git(clone, "cat-file", "-t", tag(clone)) == "tag", "the release tag is annotated"
    origin = clone.parent / "origin.git"
    assert git(origin, "rev-parse", "refs/heads/dev") == head
    assert git(origin, "rev-parse", "refs/heads/stable") == head
    assert git(origin, "rev-list", "-n1", f"refs/tags/{tag(clone)}") == head
    # `git branch -f stable` exits 128 with stable checked out in another worktree (git 2.55).
    assert git(clone, "branch", "--list", "stable") == ""
    again = publish(clone)
    assert again.returncode == 0, again.stdout + again.stderr
    assert git(origin, "rev-parse", "refs/heads/stable") == head


def test_a_rejected_push_moves_no_ref_at_all(clone: Path) -> None:
    """--atomic: with stable refused (a pre-receive hook as an outage), nothing moves."""
    origin = clone.parent / "origin.git"
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "while read -r _ _ ref; do\n"
        '  [ "$ref" = refs/heads/stable ] && { echo "simulated outage" >&2; exit 1; }\n'
        "done\n"
        "exit 0\n"
    )
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
    before = git(origin, "rev-parse", "refs/heads/dev")
    assert publish(clone).returncode != 0
    assert git(origin, "rev-parse", "refs/heads/dev") == before
    assert git(origin, "branch", "--list", "stable") == "" and git(origin, "tag", "--list") == ""


def test_a_tag_on_another_commit_is_refused(clone: Path) -> None:
    git(clone, "tag", "-a", tag(clone), "-m", "older release")
    (clone / "f").write_text("new work\n")
    git(clone, "add", "f")
    git(clone, "commit", "-q", "-m", "feat: new work")
    git(clone, "push", "-q", "origin", "dev")
    result = publish(clone)
    assert result.returncode != 0 and "already exists on another commit" in result.stderr
    assert git(clone.parent / "origin.git", "branch", "--list", "stable") == ""


def test_publish_refuses_off_dev_with_a_dirty_tree_or_with_arguments(clone: Path) -> None:
    result = publish(clone, "--dry-run")
    assert result.returncode != 0 and "takes no arguments" in result.stderr
    (clone / "scratch").write_text("uncommitted\n")
    result = publish(clone)
    assert result.returncode != 0 and "uncommitted changes" in result.stderr
    (clone / "scratch").unlink()
    git(clone, "checkout", "-q", "-b", "feature")
    result = publish(clone)
    assert result.returncode != 0 and "not on dev" in result.stderr
    assert gates(clone) == [], "every refusal comes before the gates"
    assert git(clone.parent / "origin.git", "branch", "--list", "stable") == ""
