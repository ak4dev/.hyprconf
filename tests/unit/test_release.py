"""
Unit tests for the omarchy → stable release model.

Validates the static invariants that the release pipeline depends on:
  - .gitattributes export-ignores every dev-only path and never the install payload
  - hyprconf.__version__ (lib/hyprconf/__init__.py) is a valid semver string
  - scripts/publish gates on the omarchy working branch and promotes to stable
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
PUBLISH = REPO_ROOT / "scripts" / "publish"
VERSION_FILE = REPO_ROOT / "lib" / "hyprconf" / "__init__.py"

# Paths that must be excluded from the release archive via export-ignore.
EXPORT_IGNORE_PATHS = [
    "tests/",
    "scripts/",
    ".github/",
    "web/",
    "docs/",
    "AGENTS.md",
    "Makefile",
    ".editorconfig",
    "pyproject.toml",
    "**/__pycache__/",
    "*.pyc",
]

# The overlay's install payload — everything install.sh needs from the archive.
# None of these may ever carry export-ignore.
INSTALL_PAYLOAD = [
    "install.sh",
    "hypr/",
    "lib/",
    "tui/",
    "bin/",
    "packages",
    "plugins/",
    "themes/",
    "zsh/",
    "kitty/",
    "fastfetch/",
    "hooks/",
    "infra/",
    "wallpapers/",
]


def _export_ignore_patterns() -> list[str]:
    """Return the pattern half of every ``<pattern> export-ignore`` line."""
    text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    patterns: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *attrs = line.split()
        if "export-ignore" in attrs:
            patterns.append(pattern)
    return patterns


# ---------------------------------------------------------------------------
# .gitattributes
# ---------------------------------------------------------------------------


def test_gitattributes_has_all_export_ignore_entries() -> None:
    """Every dev-only path carries export-ignore in .gitattributes."""
    patterns = _export_ignore_patterns()
    for path in EXPORT_IGNORE_PATHS:
        assert path in patterns, f"Missing 'export-ignore' rule for {path!r} in .gitattributes"


@pytest.mark.parametrize("payload", INSTALL_PAYLOAD)
def test_gitattributes_never_export_ignores_install_payload(payload: str) -> None:
    """The install payload must NOT be export-ignored — install.sh needs it."""
    name = payload.rstrip("/")
    for pattern in _export_ignore_patterns():
        assert pattern.rstrip("/").lstrip("/") != name, (
            f".gitattributes export-ignores install payload {payload!r} via {pattern!r}"
        )


@pytest.mark.parametrize("payload", INSTALL_PAYLOAD)
def test_install_payload_is_tracked(payload: str) -> None:
    """Every install payload root exists in the checkout (a typo here would ship nothing)."""
    assert (REPO_ROOT / payload.rstrip("/")).exists(), f"install payload {payload!r} missing"


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_hyprconf_version_is_semver() -> None:
    """__version__ in lib/hyprconf/__init__.py is a valid semver string."""
    text = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert match, f"__version__ not found in {VERSION_FILE}"
    version = match.group(1)
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.\w+-]+)?", version), (
        f"__version__ {version!r} does not look like a semver string"
    )


def test_publish_script_reads_version_from_lib() -> None:
    """scripts/publish bumps/reads the version from lib/hyprconf/__init__.py only."""
    text = PUBLISH.read_text(encoding="utf-8")
    assert 'VERSION_FILE_REL="lib/hyprconf/__init__.py"' in text, (
        "scripts/publish must point VERSION_FILE_REL at lib/hyprconf/__init__.py"
    )
    assert "stow/" not in text, "scripts/publish still references the retired stow/ tree"


# ---------------------------------------------------------------------------
# scripts/publish
# ---------------------------------------------------------------------------


def test_publish_script_exists_and_is_readable() -> None:
    """scripts/publish exists and is a shell script."""
    assert PUBLISH.exists(), "scripts/publish does not exist"
    text = PUBLISH.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash"), (
        "scripts/publish must start with '#!/usr/bin/env bash'"
    )


def test_publish_script_references_stable_branch() -> None:
    """scripts/publish promotes to 'stable', not the old filtered branch."""
    text = PUBLISH.read_text(encoding="utf-8")
    assert 'STABLE_BRANCH="stable"' in text, 'scripts/publish must define STABLE_BRANCH="stable"'


def test_publish_script_gates_on_omarchy_work_branch() -> None:
    """scripts/publish promotes omarchy → stable: one WORK_BRANCH variable, no 'dev' left."""
    text = PUBLISH.read_text(encoding="utf-8")
    assert 'WORK_BRANCH="omarchy"' in text, 'scripts/publish must define WORK_BRANCH="omarchy"'
    # The branch gate and the up-to-date check must both go through WORK_BRANCH.
    assert '[[ "$current_branch" == "$WORK_BRANCH" ]]' in text
    assert 'git fetch origin "$WORK_BRANCH"' in text
    assert 'git push origin "$WORK_BRANCH"' in text
    # The retired dev branch must not be referenced anywhere (code or comments);
    # the negative lookbehind keeps ``/dev/null`` redirects out of the match.
    assert not re.search(r"(?<!/)\bdev\b", text), (
        "scripts/publish still references the retired dev branch"
    )
    # The promotion itself targets STABLE_BRANCH with a lease.
    assert 'git push --force-with-lease origin HEAD:"${STABLE_BRANCH}"' in text


def test_publish_script_has_no_vm_or_install_tiers() -> None:
    """Tiers 4/5 (VM + install) are deleted — publish must not reference them."""
    text = PUBLISH.read_text(encoding="utf-8")
    for needle in (
        "tests/vm",
        "tests/install",
        "VM_RUN_SCRIPT",
        "INSTALL_VM",
        "INSTALL_IMAGE",
        "INSTALL_META",
        "test-vm",
        "test-install",
        "build_image.sh",
        "Tier 4",
        "Tier 5",
    ):
        assert needle not in text, f"scripts/publish still references {needle!r}"
    # Tiers 1-3 remain the release test gate.
    assert "make test 2>&1" in text, "scripts/publish must run tiers 1-3 via make test"


def test_publish_script_keeps_lint_gates() -> None:
    """scripts/publish runs the same lint gates CI enforces before releasing."""
    text = PUBLISH.read_text(encoding="utf-8")
    assert "make lint 2>&1" in text
    assert "make shellcheck 2>&1" in text


def test_publish_script_builds_archive_with_worktree_attributes() -> None:
    """scripts/publish uses --worktree-attributes so export-ignore rules apply."""
    text = PUBLISH.read_text(encoding="utf-8")
    assert "--worktree-attributes" in text, (
        "scripts/publish must pass --worktree-attributes to git archive"
    )
    assert '--prefix=".hyprconf/"' in text, "release archive must be rooted at .hyprconf/"


def test_publish_script_has_dry_run_flag() -> None:
    """scripts/publish supports --dry-run (skip branch/tag pushes) and the --skip-* flags."""
    text = PUBLISH.read_text(encoding="utf-8")
    for flag in ("--dry-run", "--skip-bump", "--skip-tests", "--skip-tag"):
        assert f"{flag})" in text, f"scripts/publish must accept {flag}"
