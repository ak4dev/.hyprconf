"""hyprconf.hypridle — read and write hypridle configuration.

Uses the generic block_conf parser.  Known block types:
    general, listener
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .block_conf import ConfigBlock, read_blocks, update_block_field, delete_block, add_block

# ─────────────────────────────────────────────────────────────────────────────
#  Path
# ─────────────────────────────────────────────────────────────────────────────

_CFG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HYPRIDLE_FILE = _CFG / "hypr" / "hypridle.conf"

# ─────────────────────────────────────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_TYPES: tuple[str, ...] = ("general", "listener")

BLOCK_DEFAULTS: dict[str, dict[str, str]] = {
    "general": {
        "lock_cmd":            "pidof hyprlock || hyprlock",
        "before_sleep_cmd":    "hyprlock",
        "after_sleep_cmd":     "hyprctl dispatch dpms on",
        "ignore_dbus_inhibit": "false",
    },
    "listener": {
        "timeout":    "300",
        "on-timeout": "hyprlock",
        "on-resume":  "",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Readers
# ─────────────────────────────────────────────────────────────────────────────

def read_hypridle_blocks(path: Optional[Path] = None) -> list[ConfigBlock]:
    """Return all blocks from hypridle.conf."""
    return read_blocks(path or HYPRIDLE_FILE)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

def update_hypridle_field(
    path: Path,
    start_line: int,
    end_line: int,
    key: str,
    value: str,
) -> bool:
    """Update a single field within a hypridle block."""
    return update_block_field(path, start_line, end_line, key, value)


def delete_hypridle_block(path: Path, start_line: int, end_line: int) -> bool:
    """Delete the block spanning [start_line, end_line]."""
    return delete_block(path, start_line, end_line)


def add_hypridle_block(
    block_type: str,
    overrides: Optional[dict[str, str]] = None,
    path: Optional[Path] = None,
) -> bool:
    """Append a new block of *block_type* to hypridle.conf.

    Returns True on success.
    """
    if path is None:
        path = HYPRIDLE_FILE
    fields = dict(BLOCK_DEFAULTS.get(block_type, {}))
    if overrides:
        fields.update(overrides)
    # For listener blocks, drop empty on-resume
    if block_type == "listener":
        fields = {k: v for k, v in fields.items() if v or k != "on-resume"}
    return add_block(path, block_type, fields)


def add_listener(
    timeout: str,
    on_timeout: str,
    on_resume: str = "",
    path: Optional[Path] = None,
) -> bool:
    """Convenience: append a listener block with the given values."""
    overrides: dict[str, str] = {"timeout": timeout, "on-timeout": on_timeout}
    if on_resume:
        overrides["on-resume"] = on_resume
    return add_hypridle_block("listener", overrides, path)
