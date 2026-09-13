"""
Integration tests for the dev → stable release pipeline.

scripts/publish runs end to end against a throwaway repository built here: a
bare ``origin`` seeded with the script and VERSION, and a clone of it on
``dev``. Nothing in this checkout is read through git, pushed, tagged or
mutated, and no network is touched; the ``make`` gates are a recording stub
on PATH.

The contract the script keeps: the three CI gates run, the tag VERSION names
is cut from the tested HEAD, and dev, stable and that tag move in ONE atomic
push — so a run that dies leaves origin exactly as it was and the rerun is
just a rerun. There is no bump commit, no resume flag and no half-published
state to detect.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import git

REPO_ROOT = Path(__file__).parent.parent.parent
PUBLISH = "scripts/publish"
SEED = (PUBLISH, "VERSION")


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A clone on ``dev`` of a local bare origin holding only scripts/publish
    and VERSION, copied from this checkout."""
    seed = tmp_path / "seed"
    for rel in SEED:
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_bytes((REPO_ROOT / rel).read_bytes())
    git(seed, "init", "-q", "-b", "dev")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    git(tmp_path, "clone", "-q", "--branch", "dev", "origin.git", "clone")
    return tmp_path / "clone"


def _publish(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run scripts/publish in the clone with a ``make`` stub first on PATH
    that records its target in <clone>/../make-calls and succeeds."""
    bins = clone.parent / "bins"
    bins.mkdir(exist_ok=True)
    make = bins / "make"
    make.write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$1" >> "$FAKE_CALLS"\n')
    make.chmod(make.stat().st_mode | stat.S_IEXEC)
    return subprocess.run(
        ["bash", PUBLISH, *args],
        cwd=clone,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            **os.environ,
            "PATH": f"{bins}:{os.environ['PATH']}",
            "FAKE_CALLS": str(clone.parent / "make-calls"),
        },
    )


def _gates(clone: Path) -> list[str]:
    calls = clone.parent / "make-calls"
    return calls.read_text().splitlines() if calls.exists() else []


def _tag(clone: Path) -> str:
    return "v" + (clone / "VERSION").read_text().strip()


def test_publish_promotes_dev_to_stable(clone: Path) -> None:
    """The gates run in CI's order, the annotated tag is cut at HEAD, and one
    atomic push leaves dev, stable and the tag on the exact sha the gates went
    green on — no bump commit, so HEAD is unchanged."""
    head = git(clone, "rev-parse", "HEAD")
    result = _publish(clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _gates(clone) == ["lint", "shellcheck", "test"]

    tag = _tag(clone)
    assert git(clone, "rev-parse", "HEAD") == head, "the release needs no commit of its own"
    assert git(clone, "status", "--porcelain") == ""
    assert git(clone, "cat-file", "-t", tag) == "tag", "the release tag is annotated"
    origin = clone.parent / "origin.git"
    assert git(origin, "rev-parse", "refs/heads/dev") == head
    assert git(origin, "rev-parse", "refs/heads/stable") == head
    assert git(origin, "rev-list", "-n1", f"refs/tags/{tag}") == head
    # The local stable branch is deliberately left alone: `git branch -f`
    # exits 128 when stable is checked out in another worktree (git 2.55),
    # which is the normal layout here, and nothing reads it.
    assert git(clone, "branch", "--list", "stable") == ""

    # A rerun reuses the tag already at HEAD instead of refusing it: that is
    # how a run that died on the push is resumed, and why nothing detects a
    # half-published state any more.
    again = _publish(clone)
    assert again.returncode == 0, again.stdout + again.stderr
    assert git(origin, "rev-parse", "refs/heads/stable") == head


def test_a_rejected_push_moves_no_ref_at_all(clone: Path) -> None:
    """--atomic is what replaced the resume logic: with the stable update
    refused (here a pre-receive hook standing in for an outage), dev does not
    move and the tag is not published either, so origin is exactly as it was."""
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

    result = _publish(clone)
    assert result.returncode != 0
    assert git(origin, "rev-parse", "refs/heads/dev") == before
    assert git(origin, "branch", "--list", "stable") == ""
    assert git(origin, "tag", "--list") == ""


def test_a_tag_on_another_commit_is_refused(clone: Path) -> None:
    """VERSION naming a tag that points at an older commit must refuse, or
    stable would be promoted while the tag describes a different release."""
    git(clone, "tag", "-a", _tag(clone), "-m", "older release")
    (clone / "f").write_text("new work\n")
    git(clone, "add", "f")
    git(clone, "commit", "-q", "-m", "feat: new work")
    git(clone, "push", "-q", "origin", "dev")

    result = _publish(clone)
    assert result.returncode != 0
    assert "already exists on another commit" in result.stderr
    origin = clone.parent / "origin.git"
    assert git(origin, "branch", "--list", "stable") == ""


def test_publish_refuses_off_dev_with_a_dirty_tree_or_with_arguments(clone: Path) -> None:
    result = _publish(clone, "--dry-run")
    assert result.returncode != 0 and "takes no arguments" in result.stderr

    (clone / "scratch").write_text("uncommitted\n")
    result = _publish(clone)
    assert result.returncode != 0 and "uncommitted changes" in result.stderr
    (clone / "scratch").unlink()

    git(clone, "checkout", "-q", "-b", "feature")
    result = _publish(clone)
    assert result.returncode != 0 and "not on dev" in result.stderr

    assert _gates(clone) == [], "every refusal comes before the gates"
    assert git(clone.parent / "origin.git", "branch", "--list", "stable") == ""
