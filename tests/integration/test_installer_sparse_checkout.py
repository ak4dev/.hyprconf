"""
Integration tests for the sparse-checkout configuration in install/install.sh
and setup.sh.

These tests verify:
1. Both scripts use ``--no-cone`` mode (not ``--cone``), which is required
   because REPO_SPARSE_PATHS / HYPRCONF_SPARSE_PATHS contain bare file names
   (e.g. README.md, packages, setup.sh) in addition to directory names.  Cone
   mode only accepts directory patterns and raises a fatal error on file names.
2. The sparse-paths arrays actually contain file-level entries.
3. A real git repository can be sparse-checked-out with those file patterns
   in ``--no-cone`` mode without error.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
INSTALL_SH = REPO_ROOT / "install" / "install.sh"
SETUP_SH = REPO_ROOT / "setup.sh"

# File-level entries that must appear in the sparse-paths arrays and that
# cone mode would reject.
EXPECTED_FILE_ENTRIES = {"README.md", "packages", "setup.sh"}


# ---------------------------------------------------------------------------
# Static analysis: --no-cone must be used, --cone must not
# ---------------------------------------------------------------------------

def test_install_sh_uses_no_cone_in_apply_sparse_checkout() -> None:
    """apply_sparse_checkout in install/install.sh must use --no-cone."""
    text = INSTALL_SH.read_text()
    # Locate the function body
    match = re.search(
        r"apply_sparse_checkout\(\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert match, "apply_sparse_checkout() function not found in install/install.sh"
    body = match.group(1)
    assert "--no-cone" in body, (
        "apply_sparse_checkout must use 'git sparse-checkout init --no-cone'; "
        "cone mode rejects file-level sparse paths"
    )
    assert "--cone" not in body.replace("--no-cone", ""), (
        "apply_sparse_checkout must NOT use bare '--cone'; "
        "cone mode rejects file names like README.md"
    )


def test_setup_sh_uses_no_cone_in_apply_repo_sparse_checkout() -> None:
    """_apply_repo_sparse_checkout in setup.sh must use --no-cone."""
    text = SETUP_SH.read_text()
    match = re.search(
        r"_apply_repo_sparse_checkout\(\)\s*\{(.*?)\n\}",
        text,
        re.DOTALL,
    )
    assert match, "_apply_repo_sparse_checkout() function not found in setup.sh"
    body = match.group(1)
    assert "--no-cone" in body, (
        "_apply_repo_sparse_checkout must use 'git sparse-checkout init --no-cone'"
    )
    assert "--cone" not in body.replace("--no-cone", ""), (
        "_apply_repo_sparse_checkout must NOT use bare '--cone'"
    )


# ---------------------------------------------------------------------------
# Static analysis: sparse-paths arrays must contain file-level entries
# ---------------------------------------------------------------------------

def _extract_bash_array(text: str, name: str) -> list[str]:
    """Return the values of a bash ``declare -ra NAME=( ... )`` array."""
    match = re.search(
        rf"declare\s+-r[a-z]*\s+{re.escape(name)}\s*=\s*\((.*?)\)",
        text,
        re.DOTALL,
    )
    assert match, f"{name} array not found"
    raw = match.group(1)
    return [token for token in re.split(r"\s+", raw.strip()) if token]


def test_repo_sparse_paths_contains_file_entries() -> None:
    """REPO_SPARSE_PATHS must include bare file names that require --no-cone."""
    text = INSTALL_SH.read_text()
    paths = set(_extract_bash_array(text, "REPO_SPARSE_PATHS"))
    missing = EXPECTED_FILE_ENTRIES - paths
    assert not missing, (
        f"REPO_SPARSE_PATHS is missing expected file entries: {missing}"
    )


def test_hyprconf_sparse_paths_contains_file_entries() -> None:
    """HYPRCONF_SPARSE_PATHS must include bare file names that require --no-cone."""
    text = SETUP_SH.read_text()
    paths = set(_extract_bash_array(text, "HYPRCONF_SPARSE_PATHS"))
    missing = EXPECTED_FILE_ENTRIES - paths
    assert not missing, (
        f"HYPRCONF_SPARSE_PATHS is missing expected file entries: {missing}"
    )


# ---------------------------------------------------------------------------
# Functional: --no-cone accepts file patterns without error
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository with files and directories."""
    repo = tmp_path / "origin"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=main", str(repo)],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"],
                   check=True, capture_output=True)
    # Mimic repo structure: top-level files + a directory
    (repo / "README.md").write_text("# test\n")
    (repo / "packages").write_text("zsh\n")
    (repo / "setup.sh").write_text("#!/usr/bin/env bash\n")
    stow_dir = repo / "stow"
    stow_dir.mkdir()
    (stow_dir / "dotfile").write_text("dotfile content\n")
    subprocess.run(["git", "-C", str(repo), "add", "."],
                   check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"],
                   check=True, capture_output=True)
    return repo


def test_no_cone_sparse_checkout_accepts_file_patterns(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """
    Cloning with --sparse and then applying --no-cone sparse-checkout set
    with file-level patterns must succeed (exit 0) and check out those files.
    """
    clone = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "--depth=1", "--sparse", str(temp_git_repo), str(clone)],
        check=True, capture_output=True,
    )
    # Switch to --no-cone mode
    result = subprocess.run(
        ["git", "-C", str(clone), "sparse-checkout", "init", "--no-cone"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"sparse-checkout init --no-cone failed: {result.stderr}"

    # Apply file + directory patterns (same as REPO_SPARSE_PATHS)
    patterns = ["README.md", "packages", "setup.sh", "stow"]
    result = subprocess.run(
        ["git", "-C", str(clone), "sparse-checkout", "set"] + patterns,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"sparse-checkout set failed with --no-cone and file patterns: {result.stderr}"
    )

    # Verify the file-level entries are checked out
    for fname in ["README.md", "packages", "setup.sh"]:
        assert (clone / fname).exists(), (
            f"{fname} should be checked out after --no-cone sparse-checkout set"
        )


def test_cone_mode_fails_on_file_patterns(
    temp_git_repo: Path, tmp_path: Path
) -> None:
    """
    Cone mode must reject file-level patterns — this confirms why --no-cone
    is necessary.  If git ever changes this behaviour the test will catch it.
    """
    clone = tmp_path / "clone_cone"
    subprocess.run(
        ["git", "clone", "--depth=1", "--sparse", str(temp_git_repo), str(clone)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(clone), "sparse-checkout", "init", "--cone"],
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "-C", str(clone), "sparse-checkout", "set",
         "README.md", "packages", "setup.sh", "stow"],
        capture_output=True, text=True,
    )
    # Cone mode must fail (non-zero exit) or emit a fatal error for file names.
    failed = result.returncode != 0 or "fatal" in result.stderr.lower()
    assert failed, (
        "Expected cone mode to fail on file-level sparse paths, but it succeeded. "
        "If git changed this behaviour, --no-cone may no longer be required — "
        "re-evaluate the fix."
    )
