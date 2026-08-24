"""Every repo-owned path a shipped Hyprland config references must ship.

Regression guard: the adjust-gaps helper was deleted while keybinds.conf
still bound Super+Shift+=/- to ~/.config/hypr/scripts/adjust-gaps — Hyprland
executes a bind whose target is missing as a silent no-op, so the breakage
never surfaced. These tests map every ~/-anchored script/binary reference in
the shipped hypr/ Lua files back to the files install.sh ships (hypr/scripts/
-> ~/.config/hypr/scripts/, bin/ -> ~/.local/bin/) and fail on danglers.

Runtime-generated files (monitors.lua, the conf.d/ local override) and
Omarchy's own paths are deliberately out of scope: only prefixes whose content
is repo-shipped are validated. Hyprland's config is Lua (`--` comments); the
`.conf` branch is kept for any hyprlang file that may join hypr/ later.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HYPR_CONF_DIR = REPO_ROOT / "hypr"  # the overlay's shipped Hyprland Lua (override files + presets)

# ~/-anchored prefixes that must resolve to a file the overlay ships (install.sh
# copies hypr/scripts/* to ~/.config/hypr/scripts/ and bin/* to ~/.local/bin/).
PREFIX_MAP = {
    "~/.config/hypr/scripts/": "hypr/scripts/",
    "~/.local/bin/": "bin/",
}

PATH_RE = re.compile(r"~/[\w./-]+")

CONF_FILES = sorted(HYPR_CONF_DIR.rglob("*.conf")) + sorted(HYPR_CONF_DIR.rglob("*.lua"))


def test_conf_files_found() -> None:
    assert CONF_FILES, f"no .conf/.lua files found under {HYPR_CONF_DIR}"


@pytest.mark.parametrize("conf", CONF_FILES, ids=lambda p: p.name)
def test_referenced_repo_paths_ship_in_the_overlay(conf: Path) -> None:
    comment = "--" if conf.suffix == ".lua" else "#"
    missing = []
    for line in conf.read_text(encoding="utf-8").splitlines():
        code = line.split(comment, 1)[0]
        for token in PATH_RE.findall(code):
            for prefix, repo_prefix in PREFIX_MAP.items():
                if token.startswith(prefix):
                    rel = repo_prefix + token[len(prefix) :]
                    if not (REPO_ROOT / rel).exists():
                        missing.append(f"{conf.relative_to(HYPR_CONF_DIR)}: {token}")
    assert not missing, "config references paths the overlay does not ship:\n" + "\n".join(missing)
