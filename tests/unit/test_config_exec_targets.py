"""Every command a shipped Hyprland config runs must ship.

Regression guard: the gaps helper was once deleted while the keymap still
bound Super+Shift+=/- to it — Hyprland executes a bind whose target is missing
as a silent no-op, so the breakage never surfaced. These tests map every
hyprconf-* command and every ~/-anchored path the shipped hypr/ Lua files
name back to what install.sh ships (bin/hyprconf-* -> ~/.local/bin/) and fail
on danglers. The hotkey tools are bound by command name, the way Omarchy binds
its own, so nothing under ~/.config/hypr/ is referenced any more.

Runtime-generated files (monitors.lua) and Omarchy's own commands are
deliberately out of scope: only what the overlay ships is validated.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR_CONF_DIR = REPO_ROOT / "hypr"  # the overlay's shipped Hyprland Lua (override files + presets)

# ~/-anchored prefixes that must resolve to a file the overlay ships (install.sh
# installs bin/hyprconf-* to ~/.local/bin/).
PREFIX_MAP = {
    "~/.local/bin/": "bin/",
}

PATH_RE = re.compile(r"~/[\w./-]+")
# A hyprconf-* command named in a bind's dispatcher string.
TOOL_RE = re.compile(r'"(hyprconf-[\w-]+)(?:\s[^"]*)?"')

CONF_FILES = sorted(HYPR_CONF_DIR.rglob("*.lua"))


def test_conf_files_found() -> None:
    assert CONF_FILES, f"no .lua files found under {HYPR_CONF_DIR}"


@pytest.mark.parametrize("conf", CONF_FILES, ids=lambda p: p.name)
def test_referenced_repo_paths_ship_in_the_overlay(conf: Path) -> None:
    missing = []
    for line in conf.read_text(encoding="utf-8").splitlines():
        code = line.split("--", 1)[0]
        for token in PATH_RE.findall(code):
            for prefix, repo_prefix in PREFIX_MAP.items():
                if token.startswith(prefix):
                    rel = repo_prefix + token[len(prefix) :]
                    if not (REPO_ROOT / rel).exists():
                        missing.append(f"{conf.relative_to(HYPR_CONF_DIR)}: {token}")
    assert not missing, "config references paths the overlay does not ship:\n" + "\n".join(missing)


@pytest.mark.parametrize("conf", CONF_FILES, ids=lambda p: p.name)
def test_every_hyprconf_command_bound_ships_in_bin(conf: Path) -> None:
    missing = []
    for line in conf.read_text(encoding="utf-8").splitlines():
        code = line.split("--", 1)[0]
        for tool in TOOL_RE.findall(code):
            if not (REPO_ROOT / "bin" / tool).is_file():
                missing.append(f"{conf.relative_to(HYPR_CONF_DIR)}: {tool}")
    assert not missing, "config binds commands the overlay does not ship:\n" + "\n".join(missing)


def test_the_hotkey_tools_are_bound_by_name() -> None:
    """The monitor presets and the gaps keys run bin/ tools by command name —
    nothing under ~/.config/hypr/scripts/, which the overlay no longer
    installs (stage_hotkeys sweeps the old copies)."""
    code = "\n".join(
        ln.split("--", 1)[0] for ln in (HYPR_CONF_DIR / "bindings.lua").read_text().splitlines()
    )
    assert '"hyprconf-monitor-preset bedroom"' in code
    assert '"hyprconf-monitor-preset kitchen"' in code
    assert '"hyprconf-gaps +"' in code and '"hyprconf-gaps -"' in code
    assert "~/.config/hypr/scripts" not in code
