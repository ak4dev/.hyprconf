"""
Integration tests for the dev → stable release pipeline.

scripts/publish runs end-to-end — the dry run and the real promotion — against
a throwaway repository built here: a bare ``origin`` seeded with the script and
the version file, and a clone of it on ``dev``. Nothing in this checkout is
read through git, pushed, tagged or mutated, and no network is touched; the
``make`` gates are a recording stub on PATH.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
PUBLISH = "scripts/publish"
VERSION_FILE = "lib/hyprconf/__init__.py"
VERSION_RE = re.compile(r'^__version__ = "(\d+)\.(\d+)\.(\d+)"$', re.M)
# A git identity, so a fresh CI container's commits and tags need none configured.
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "testuser",
    "GIT_AUTHOR_EMAIL": "testuser@example.invalid",
    "GIT_COMMITTER_NAME": "testuser",
    "GIT_COMMITTER_EMAIL": "testuser@example.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=60, env=GIT_ENV
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def _version(path: Path) -> tuple[int, int, int]:
    """The x.y.z in a version file, in the exact shape scripts/publish reads."""
    match = VERSION_RE.search(path.read_text(encoding="utf-8"))
    assert match, f'{path} has no `__version__ = "x.y.z"` line'
    return tuple(int(n) for n in match.groups())  # type: ignore[return-value]


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A clone on ``dev`` of a local bare origin that holds only
    scripts/publish and the version file, copied from this checkout."""
    seed = tmp_path / "seed"
    for rel in (PUBLISH, VERSION_FILE):
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_bytes((REPO_ROOT / rel).read_bytes())
    _git(seed, "init", "-q", "-b", "dev")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(tmp_path, "clone", "-q", "--bare", str(seed), "origin.git")
    _git(tmp_path, "clone", "-q", "--branch", "dev", "origin.git", "clone")
    return tmp_path / "clone"


def _publish(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run scripts/publish in the clone with a ``make`` stub first on PATH that
    records its target in <clone>/../make-calls and succeeds."""
    bins = clone.parent / "bins"
    bins.mkdir(exist_ok=True)
    make = bins / "make"
    make.write_text('#!/usr/bin/env bash\nprintf \'%s\\n\' "$1" >> "$FAKE_CALLS"\n')
    make.chmod(make.stat().st_mode | stat.S_IEXEC)
    env = {
        **GIT_ENV,
        "PATH": f"{bins}:{os.environ['PATH']}",
        "FAKE_CALLS": str(clone.parent / "make-calls"),
    }
    return subprocess.run(
        ["bash", PUBLISH, *args], cwd=clone, capture_output=True, text=True, timeout=120, env=env
    )


def _make_calls(clone: Path) -> list[str]:
    calls = clone.parent / "make-calls"
    return calls.read_text().splitlines() if calls.exists() else []


def test_publish_help_describes_dev_to_stable() -> None:
    """``scripts/publish --help`` prints the usage header and exits 0 without touching git."""
    result = subprocess.run(
        ["bash", PUBLISH, "--help"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "--dry-run" in result.stdout
    assert "dev" in result.stdout and "stable" in result.stdout
    assert VERSION_FILE in result.stdout


def test_publish_dry_run_runs_the_gates_and_pushes_nothing(clone: Path) -> None:
    before = _version(clone / VERSION_FILE)
    result = _publish(clone, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Done" in result.stdout
    # The CI gates, in CI's order, then nothing: the bump is reverted, no
    # commit, no tag, no push.
    assert _make_calls(clone) == ["lint", "shellcheck", "test"]
    assert _version(clone / VERSION_FILE) == before
    assert _git(clone, "status", "--porcelain") == ""
    assert _git(clone, "rev-parse", "HEAD") == _git(clone, "rev-parse", "origin/dev")
    assert _git(clone, "tag") == ""
    assert _git(clone.parent / "origin.git", "branch", "--list", "stable") == ""


def test_publish_promotes_dev_to_stable(clone: Path) -> None:
    """The real thing: bump, commit, push the bump to origin/dev, tag, push
    HEAD to origin/stable, move the local stable branch too."""
    major, minor, patch = _version(clone / VERSION_FILE)
    result = _publish(clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _make_calls(clone) == ["lint", "shellcheck", "test"]

    bumped = (major, minor, patch + 1)
    tag = "v{}.{}.{}".format(*bumped)
    assert _version(clone / VERSION_FILE) == bumped
    assert _git(clone, "status", "--porcelain") == ""
    head = _git(clone, "rev-parse", "HEAD")
    assert _git(clone, "log", "-1", "--pretty=%s") == f"release: [{tag}] bump version"
    origin = clone.parent / "origin.git"
    assert _git(origin, "rev-parse", "refs/heads/dev") == head
    assert _git(origin, "rev-parse", "refs/heads/stable") == head
    assert _git(origin, "rev-list", "-n1", f"refs/tags/{tag}") == head
    assert _git(clone, "rev-parse", "refs/heads/stable") == head
    assert _git(clone, "cat-file", "-t", tag) == "tag", "the release tag is annotated"


@pytest.mark.parametrize(
    ("flag", "bump"),
    [
        ("--minor", lambda M, m, p: (M, m + 1, 0)),
        ("--major", lambda M, m, p: (M + 1, 0, 0)),
        ("--skip-bump", lambda M, m, p: (M, m, p)),
    ],
)
def test_publish_bumps_the_requested_component(clone: Path, flag: str, bump) -> None:
    before = _version(clone / VERSION_FILE)
    result = _publish(clone, flag, "--skip-tests", "--skip-tag")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _make_calls(clone) == [], "--skip-tests skips every make gate"
    assert _version(clone / VERSION_FILE) == bump(*before)
    assert _git(clone, "tag") == "", "--skip-tag creates no tag"
    origin = clone.parent / "origin.git"
    assert _git(origin, "rev-parse", "refs/heads/stable") == _git(clone, "rev-parse", "HEAD")


def test_publish_rerun_after_a_failed_promotion_requires_skip_bump(clone: Path) -> None:
    """A publish that dies after its bump commit (here: the stable push is
    rejected once, simulating an outage) must not bump again on a naive
    rerun — that would strand the first tag locally forever and skip a
    version on stable. The rerun is refused, naming --skip-bump; with the
    flag, the promotion resumes and releases the version the first run cut."""
    origin = clone.parent / "origin.git"
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/usr/bin/env bash\n"
        "while read -r _ _ ref; do\n"
        '  if [ "$ref" = refs/heads/stable ] && [ ! -f flag-stable-once ]; then\n'
        "    touch flag-stable-once\n"
        '    echo "stable rejected (simulated outage)" >&2\n'
        "    exit 1\n"
        "  fi\n"
        "done\n"
        "exit 0\n"
    )
    hook.chmod(hook.stat().st_mode | stat.S_IEXEC)

    before = _version(clone / VERSION_FILE)
    released = (before[0], before[1], before[2] + 1)
    tag = "v{}.{}.{}".format(*released)
    first = _publish(clone, "--skip-tests")
    assert first.returncode != 0, "the stable push was rejected"
    # The bump commit reached origin/dev; stable never moved.
    assert _git(origin, "rev-parse", "refs/heads/dev") == _git(clone, "rev-parse", "HEAD")
    assert _git(origin, "branch", "--list", "stable") == ""

    rerun = _publish(clone, "--skip-tests")
    assert rerun.returncode != 0 and "--skip-bump" in rerun.stderr
    assert _version(clone / VERSION_FILE) == released, "no second bump"

    resume = _publish(clone, "--skip-tests", "--skip-bump")
    assert resume.returncode == 0, resume.stdout + resume.stderr
    head = _git(clone, "rev-parse", "HEAD")
    assert _git(origin, "rev-parse", "refs/heads/stable") == head
    assert _git(origin, "rev-list", "-n1", f"refs/tags/{tag}") == head


def test_publish_refuses_off_the_work_branch_or_with_a_dirty_tree(clone: Path) -> None:
    (clone / "scratch").write_text("uncommitted\n")
    result = _publish(clone, "--skip-tests")
    assert result.returncode != 0 and "Uncommitted changes" in result.stderr
    (clone / "scratch").unlink()

    _git(clone, "checkout", "-q", "-b", "feature")
    result = _publish(clone, "--skip-tests")
    assert result.returncode != 0 and "Must be on the dev branch" in result.stderr
    assert _git(clone.parent / "origin.git", "branch", "--list", "stable") == ""
