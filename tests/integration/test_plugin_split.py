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

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
PLUGINS = REPO_ROOT / "plugins"
PLUGIN_NAMES = sorted(p.name for p in PLUGINS.iterdir() if p.is_dir())
# A git identity, so a fresh CI container's commits need none configured.
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "testuser",
    "GIT_AUTHOR_EMAIL": "testuser@example.invalid",
    "GIT_COMMITTER_NAME": "testuser",
    "GIT_COMMITTER_EMAIL": "testuser@example.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120, env=GIT_ENV
    )
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


def _contract():
    """The unit suite's contract functions, loaded by path: the integration
    suite runs on its own (`make test-integration`), with no package path
    to tests/unit on sys.path."""
    source = REPO_ROOT / "tests" / "unit" / "test_plugins.py"
    spec = importlib.util.spec_from_file_location("plugin_contract", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def payload_repo(tmp_path: Path) -> Path:
    """A repository holding the checkout's plugins/ tree as one commit —
    the shape the split runs against."""
    repo = tmp_path / "repo"
    shutil.copytree(PLUGINS, repo / "plugins")
    _git(repo, "init", "-q", "-b", "dev")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "plugins")
    return repo


@pytest.mark.parametrize("name", PLUGIN_NAMES)
def test_subtree_split_of_each_plugin_is_an_installable_repository(
    payload_repo: Path, name: str, tmp_path: Path
) -> None:
    branch = f"plugins/{name}"
    _git(payload_repo, "subtree", "split", f"--prefix=plugins/{name}", "-b", branch)
    clone = tmp_path / "clone" / name
    _git(tmp_path, "clone", "-q", "--branch", branch, str(payload_repo), str(clone))

    # The folder's own files are the repository's root — manifest.json where
    # omarchy-plugin-add looks for it — and nothing of the monorepo around it.
    assert (clone / "manifest.json").is_file()
    assert sorted(p.name for p in clone.iterdir() if p.name != ".git") == sorted(
        p.name for p in (PLUGINS / name).iterdir()
    )
    contract = _contract()
    assert contract.validator_problems(clone) == []
    assert contract.publishable_problems(clone) == []
    for script in (clone / "bin").glob("*") if (clone / "bin").is_dir() else ():
        assert os.access(script, os.X_OK), (
            f"{name}/bin/{script.name} lost its exec bit in the split"
        )
