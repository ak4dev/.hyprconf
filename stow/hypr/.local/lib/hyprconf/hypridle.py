"""hyprconf.hypridle — read and write hypridle configuration.

Uses the generic block_conf parser.  Known block types:
    general, listener
"""

from __future__ import annotations

from pathlib import Path

from .block_conf import ConfigBlock, add_block, read_blocks
from .paths import HYPRIDLE_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_TYPES: tuple[str, ...] = ("general", "listener")

# Defaults mirror the shipped hypridle.conf invariant: every lock path goes
# through `loginctl lock-session` -> lock_cmd -> the supervised hyprlock.service
# user unit. Never template a raw `hyprlock` — an unsupervised locker dies
# across suspend/resume and leaves the session on the lockdead screen.
BLOCK_DEFAULTS: dict[str, dict[str, str]] = {
    "general": {
        "lock_cmd": "systemctl --user start hyprlock.service",
        "before_sleep_cmd": "loginctl lock-session && hyprctl dispatch dpms on",
        "after_sleep_cmd": "hyprland-wake-restore",
        "ignore_dbus_inhibit": "false",
    },
    "listener": {
        "timeout": "300",
        "on-timeout": "loginctl lock-session",
        "on-resume": "",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Readers
# ─────────────────────────────────────────────────────────────────────────────


def read_hypridle_blocks(path: Path | None = None) -> list[ConfigBlock]:
    """Return all blocks from hypridle.conf."""
    return read_blocks(path or HYPRIDLE_FILE)


def add_hypridle_block(
    block_type: str,
    overrides: dict[str, str] | None = None,
    path: Path | None = None,
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
