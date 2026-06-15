"""
PII guard tests.

Configs under stow/ are symlinked into any user's $HOME, so they must never
carry a hardcoded /home/<user>/ path (that is both PII and broken on other
machines). The theme switcher used to write absolute include/color_theme paths
through the stow symlinks, leaking /home/<user>/ into the tracked repo — these
tests lock the door on that regressing.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
STOW_DIR = REPO_ROOT / "stow"

# /home/<name>/ — a real per-user absolute path. Generic placeholders
# (/home/$USER, /home/user, /home/<user>) are allowed.
HOME_PATH_RE = re.compile(r"/home/(?!\$|user\b|<|USER\b)[A-Za-z0-9._-]+/")


def _tracked_stow_text_files() -> list[Path]:
    files: list[Path] = []
    for p in STOW_DIR.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        # Skip compiled/byte artifacts and vendored payloads
        if "__pycache__" in p.parts or p.suffix in {".pyc", ".png", ".svg", ".ttf"}:
            continue
        try:
            files.append(p)
        except OSError:
            continue
    return files


def test_no_hardcoded_home_paths_in_stow() -> None:
    offenders: list[str] = []
    for f in _tracked_stow_text_files():
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary / unreadable — not a config we author
        for lineno, line in enumerate(text.splitlines(), 1):
            if HOME_PATH_RE.search(line):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Hardcoded /home/<user>/ paths found in stowed configs (use ~ or $HOME):\n"
        + "\n".join(offenders)
    )


def test_kitty_conf_uses_tilde_include() -> None:
    kitty = STOW_DIR / "kitty" / ".config" / "kitty" / "kitty.conf"
    text = kitty.read_text(encoding="utf-8")
    assert "/home/" not in text, "kitty.conf must not contain a hardcoded /home/ path"
    assert "include ~/.config/kitty/themes/" in text


# ---------------------------------------------------------------------------
# Root-cause regression: load_kitty_theme must write ~-relative includes for
# paths under $HOME (kitty.conf is stowed, so absolute paths would leak to git).
# ---------------------------------------------------------------------------


@pytest.fixture
def switch_theme_module():
    path = REPO_ROOT / "stow/hypr/.config/hypr/scripts/theme-switcher/switch_theme.py"
    spec = importlib.util.spec_from_file_location("switch_theme_pii", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_kitty_theme_writes_home_relative(tmp_path, monkeypatch, switch_theme_module):
    st = switch_theme_module
    # Make tmp_path act as $HOME so the theme file lives "under home".
    monkeypatch.setenv("HOME", str(tmp_path))
    kitty_conf = tmp_path / ".config" / "kitty" / "kitty.conf"
    kitty_conf.parent.mkdir(parents=True)
    kitty_conf.write_text("font_size 12.0\n")
    monkeypatch.setattr(st, "KITTY_CONFIG_FILE", str(kitty_conf))

    theme_conf = tmp_path / ".config" / "kitty" / "themes" / "generated.conf"
    theme_conf.parent.mkdir(parents=True)
    theme_conf.write_text("background #000000\n")

    st.load_kitty_theme(str(theme_conf))

    content = kitty_conf.read_text(encoding="utf-8")
    assert "include ~/.config/kitty/themes/generated.conf" in content
    assert str(tmp_path) not in content  # no absolute home path leaked
