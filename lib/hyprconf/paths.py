"""hyprconf.paths — single source of truth for all XDG path constants.

Every module that needs a path to a Hyprland config file should import from
here rather than re-computing ``XDG_CONFIG_HOME`` locally.

hyprconf is an overlay on Omarchy, so the files here are Omarchy's own
override points under ``~/.config/hypr`` (``bindings.lua`` is ``require``d by
Omarchy's ``hyprland.lua`` after its defaults) plus the ``conf.d/`` files the
TUI writes at runtime, which install.sh's managed block in ``hyprland.lua``
``loadfile()``s. Omarchy's idle/lock/background live in its quickshell shell
(``omarchy-shell``), not in hypridle/hyprlock/hyprpaper — those programs are
not installed and have no config paths here; see ``hyprconf.omarchy``.
"""

from __future__ import annotations

import os
from pathlib import Path

CFG_HOME: Path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HYPR_DIR: Path = CFG_HOME / "hypr"

# Omarchy's ~/.config/hypr override points (install.sh symlinks the overlay's
# hypr/bindings.lua over the first). Hyprland's config is Lua as of 0.55+
# (hyprlang `.conf` is gone in 0.56 — see docs/hyprland-reference.md).
HYPRLAND_CONF: Path = HYPR_DIR / "hyprland.lua"
KEYBINDS_FILE: Path = HYPR_DIR / "bindings.lua"
MONITORS_FILE: Path = HYPR_DIR / "monitors.lua"

# Files written at runtime by hyprconf, each loaded (if present) by the
# managed block install.sh appends to ~/.config/hypr/hyprland.lua
# (hypr/hyprland.block.lua) — a missing one is a no-op.
OVERRIDES_FILE: Path = HYPR_DIR / "conf.d" / "local.lua"
WINRULES_FILE: Path = HYPR_DIR / "conf.d" / "windowrules.lua"
WKSPRULES_FILE: Path = HYPR_DIR / "conf.d" / "workspacerules.lua"
