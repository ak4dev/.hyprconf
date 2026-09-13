"""
Integration test for publishing a plugin folder as its own repository.

`omarchy plugin add <url>` clones a repository and expects manifest.json at
its root (bin/omarchy-plugin-add, Omarchy 4.0.2-1), so a plugin cannot be
added straight from this monorepo; the recipe in docs/CONTRIBUTING.md ›
Publishing a plugin is `git subtree split --prefix=plugins/<name>`. This runs
that split for every plugins/<name> folder inside a throwaway repository
seeded from the checkout's plugins/ tree, clones the split branch the way
the add command would, and holds the result to the contract
tests/unit/test_plugins.py pins for the folders in place: the validator's
checks, the publishable shape, the executable bit on the bundled feeders.
Nothing reads the repository the suite runs from through git, and nothing
is pushed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import git
from tests.unit.test_plugins import publishable_problems, validator_problems

REPO_ROOT = Path(__file__).parent.parent.parent
PLUGINS = REPO_ROOT / "plugins"
PLUGIN_NAMES = sorted(p.name for p in PLUGINS.iterdir() if p.is_dir())


@pytest.fixture
def payload_repo(tmp_path: Path) -> Path:
    """A repository holding the checkout's plugins/ tree as one commit —
    the shape the split runs against."""
    repo = tmp_path / "repo"
    shutil.copytree(PLUGINS, repo / "plugins")
    git(repo, "init", "-q", "-b", "dev")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "plugins")
    return repo


@pytest.mark.parametrize("name", PLUGIN_NAMES)
def test_subtree_split_of_each_plugin_is_an_installable_repository(
    payload_repo: Path, name: str, tmp_path: Path
) -> None:
    branch = f"plugins/{name}"
    git(payload_repo, "subtree", "split", f"--prefix=plugins/{name}", "-b", branch)
    clone = tmp_path / "clone" / name
    git(tmp_path, "clone", "-q", "--branch", branch, str(payload_repo), str(clone))

    # The folder's own files are the repository's root — manifest.json where
    # omarchy-plugin-add looks for it — and nothing of the monorepo around it.
    assert (clone / "manifest.json").is_file()
    assert sorted(p.name for p in clone.iterdir() if p.name != ".git") == sorted(
        p.name for p in (PLUGINS / name).iterdir()
    )
    # The same contract the folders keep in place — publishable_problems
    # includes the exec bit a split could drop (a shebang that is not 100755).
    assert validator_problems(clone) == []
    assert publishable_problems(clone) == []
