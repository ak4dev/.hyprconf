"""
Unit tests for the dev → stable release model.

Validates the static invariants that the release pipeline depends on:
  - .gitattributes has the correct export-ignore entries
  - hyprconf.__version__ is a valid semver string
  - setup.sh declares the correct branch constant (stable)
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

# Paths that must be excluded from the release archive via export-ignore.
EXPORT_IGNORE_PATHS = [
    "tests/",
    "scripts/",
    ".github/",
    "AGENTS.md",
    "Makefile",
    "pyproject.toml",
]


# ---------------------------------------------------------------------------
# .gitattributes
# ---------------------------------------------------------------------------

def test_gitattributes_has_all_export_ignore_entries() -> None:
    """Every dev-only path carries export-ignore in .gitattributes."""
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    for path in EXPORT_IGNORE_PATHS:
        assert f"{path} export-ignore" in text, (
            f"Missing 'export-ignore' rule for {path!r} in .gitattributes"
        )


def test_gitattributes_has_no_stow_export_ignore() -> None:
    """stow/ must NOT be export-ignored — it is the core install payload."""
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "stow/ export-ignore" not in text
    assert "stow export-ignore" not in text


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

def test_hyprconf_version_is_semver() -> None:
    """__version__ in hyprconf/__init__.py is a valid semver string."""
    init_path = (
        REPO_ROOT
        / "stow" / "hypr" / ".local" / "lib" / "hyprconf" / "__init__.py"
    )
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match, f"__version__ not found in {init_path}"
    version = match.group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.\w+-]+)?", version), (
        f"__version__ {version!r} does not look like a semver string"
    )


# ---------------------------------------------------------------------------
# setup.sh branch constants
# ---------------------------------------------------------------------------

def test_setup_sh_stable_branch_constant() -> None:
    """setup.sh declares HYPRCONF_STABLE_BRANCH=\"stable\"."""
    text = (REPO_ROOT / "setup.sh").read_text(encoding="utf-8")
    assert 'HYPRCONF_STABLE_BRANCH="stable"' in text, (
        'setup.sh must define HYPRCONF_STABLE_BRANCH="stable"'
    )


def test_setup_sh_clone_tries_stable() -> None:
    """setup.sh clones the stable branch in clone_or_update_repo."""
    text = (REPO_ROOT / "setup.sh").read_text(encoding="utf-8")
    assert '_clone_repo_branch "$HYPRCONF_STABLE_BRANCH"' in text, (
        "clone_or_update_repo must clone HYPRCONF_STABLE_BRANCH"
    )


# ---------------------------------------------------------------------------
# scripts/publish
# ---------------------------------------------------------------------------

def test_publish_script_exists_and_is_readable() -> None:
    """scripts/publish exists and is a shell script."""
    publish = REPO_ROOT / "scripts" / "publish"
    assert publish.exists(), "scripts/publish does not exist"
    text = publish.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash"), (
        "scripts/publish must start with '#!/usr/bin/env bash'"
    )


def test_publish_script_references_stable_branch() -> None:
    """scripts/publish promotes to 'stable', not the old filtered branch."""
    text = (REPO_ROOT / "scripts" / "publish").read_text(encoding="utf-8")
    assert 'STABLE_BRANCH="stable"' in text, (
        'scripts/publish must define STABLE_BRANCH="stable"'
    )


def test_publish_script_builds_archive_with_worktree_attributes() -> None:
    """scripts/publish uses --worktree-attributes so export-ignore rules apply."""
    text = (REPO_ROOT / "scripts" / "publish").read_text(encoding="utf-8")
    assert "--worktree-attributes" in text, (
        "scripts/publish must pass --worktree-attributes to git archive"
    )


def test_publish_script_has_dry_run_flag() -> None:
    """scripts/publish supports --dry-run (skip branch/tag pushes)."""
    text = (REPO_ROOT / "scripts" / "publish").read_text(encoding="utf-8")
    assert "--dry-run" in text
