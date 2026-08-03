"""Every repo-owned path a shipped Hyprland config references must ship.

Regression guard: the adjust-gaps helper was deleted while keybinds.conf
still bound Super+Shift+=/- to ~/.config/hypr/scripts/adjust-gaps — Hyprland
executes a bind whose target is missing as a silent no-op, so the breakage
never surfaced. These tests map every ~/-anchored script/binary reference in
the shipped hypr configs back to the stow tree and fail on danglers.

Runtime-generated files (monitors.lua, theme-colors.lua, the conf.d/ local
override) and local wallpaper assets are deliberately out of scope: only
prefixes whose content is repo-shipped are validated.

Hyprland's own compositor config (hyprland/keybinds/gestures/monitors) is Lua
as of 0.55+ (`--` comments); hypridle/hyprlock/hyprpaper/hyprlauncher/kitty/
btop are separate programs still on hyprlang `.conf` (`#` comments) — both
are scanned here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR_CONF_DIR = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr"

# ~/-anchored prefixes that must resolve inside the repo's stow packages.
PREFIX_MAP = {
    "~/.config/hypr/scripts/": "stow/hypr/.config/hypr/scripts/",
    "~/.config/quickshell/": "stow/quickshell/.config/quickshell/",
    "~/.local/bin/": "stow/hypr/.local/bin/",
}

PATH_RE = re.compile(r"~/[\w./-]+")

CONF_FILES = sorted(HYPR_CONF_DIR.rglob("*.conf")) + sorted(HYPR_CONF_DIR.rglob("*.lua"))


def test_conf_files_found() -> None:
    assert CONF_FILES, f"no .conf/.lua files found under {HYPR_CONF_DIR}"


@pytest.mark.parametrize("conf", CONF_FILES, ids=lambda p: p.name)
def test_referenced_repo_paths_ship_in_stow_tree(conf: Path) -> None:
    comment = "--" if conf.suffix == ".lua" else "#"
    missing = []
    for line in conf.read_text(encoding="utf-8").splitlines():
        code = line.split(comment, 1)[0]
        for token in PATH_RE.findall(code):
            for prefix, stow_prefix in PREFIX_MAP.items():
                if token.startswith(prefix):
                    rel = stow_prefix + token[len(prefix) :]
                    if not (REPO_ROOT / rel).exists():
                        missing.append(f"{conf.relative_to(HYPR_CONF_DIR)}: {token}")
    assert not missing, "config references paths the stow tree does not ship:\n" + "\n".join(
        missing
    )
