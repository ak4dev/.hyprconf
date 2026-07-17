"""Vendored VS Code theme extensions must be complete and loadable.

Regression guard: the dracula extension was vendored together with its
upstream repo's .gitignore, whose `/theme/` rule silently kept the actual
theme JSON payload out of git — the extension shell synced fine, VSCodium had
no Dracula theme to load, and the present-but-broken directory suppressed the
marketplace-install fallback in update_vscode(). These tests fail on any
vendored extension whose declared payload (themes, entry points, icon) does
not ship, and on any nested .gitignore that could eat payload files again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXT_ROOT = REPO_ROOT / "theme" / ".vscode-oss" / "extensions"

EXTENSIONS = sorted(p for p in EXT_ROOT.iterdir() if p.is_dir())


def _package(ext: Path) -> dict:
    return json.loads((ext / "package.json").read_text(encoding="utf-8"))


def test_vendored_extensions_present() -> None:
    assert EXTENSIONS, f"no vendored extensions found under {EXT_ROOT}"


@pytest.mark.parametrize("ext", EXTENSIONS, ids=lambda p: p.name)
def test_declared_theme_payloads_ship(ext: Path) -> None:
    themes = _package(ext).get("contributes", {}).get("themes", [])
    assert themes, f"{ext.name}: package.json contributes no themes"
    for entry in themes:
        rel = entry.get("path")
        assert rel, f"{ext.name}: theme entry {entry.get('label')!r} has no path"
        payload = ext / rel
        assert payload.is_file(), f"{ext.name}: declared theme payload missing: {rel}"
        # A theme payload must itself be valid JSON or VSCodium loads nothing.
        json.loads(payload.read_text(encoding="utf-8"))


@pytest.mark.parametrize("ext", EXTENSIONS, ids=lambda p: p.name)
def test_declared_entry_points_and_icon_ship(ext: Path) -> None:
    pkg = _package(ext)
    for key in ("main", "browser", "icon"):
        rel = pkg.get(key)
        if isinstance(rel, str) and rel and not rel.startswith("vscode-test-web"):
            assert (ext / rel).is_file(), f"{ext.name}: declared {key} missing: {rel}"


@pytest.mark.parametrize("ext", EXTENSIONS, ids=lambda p: p.name)
def test_no_nested_gitignore(ext: Path) -> None:
    strays = [p.relative_to(ext) for p in ext.rglob(".gitignore")]
    assert not strays, (
        f"{ext.name}: nested .gitignore {strays} — an upstream ignore file "
        "inside a vendored tree silently excludes payload files from git"
    )
