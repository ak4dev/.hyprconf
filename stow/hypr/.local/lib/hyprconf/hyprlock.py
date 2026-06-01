"""hyprconf.hyprlock — read and write hyprlock configuration.

Uses the generic block_conf parser.  Known block types:
    general, background, label, input-field, shape

Each block is returned as a ConfigBlock with fully parsed fields.
Writers provide block-level CRUD.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .block_conf import ConfigBlock, read_blocks, update_block_field, delete_block, add_block
from .paths import HYPRLOCK_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_TYPES: tuple[str, ...] = ("general", "background", "label", "input-field", "shape")

# Default field values used when the user creates a new block.
BLOCK_DEFAULTS: dict[str, dict[str, str]] = {
    "general": {
        "disable_loading_bar": "false",
        "hide_cursor":         "true",
        "grace":               "0",
        "no_fade_in":          "false",
    },
    "background": {
        "monitor":     "",
        "path":        "screenshot",
        "blur_passes": "3",
        "blur_size":   "7",
        "brightness":  "0.7",
        "contrast":    "0.9",
        "vibrancy":    "0.1696",
    },
    "label": {
        "monitor":     "",
        "text":        "hello",
        "color":       "rgba(255, 255, 255, 0.9)",
        "font_size":   "24",
        "font_family": "JetBrainsMono Nerd Font",
        "position":    "0, 0",
        "halign":      "center",
        "valign":      "center",
    },
    "input-field": {
        "monitor":           "",
        "size":              "200, 50",
        "outline_thickness": "3",
        "dots_size":         "0.33",
        "dots_spacing":      "0.15",
        "outer_color":       "rgb(151515)",
        "inner_color":       "rgb(200, 200, 200)",
        "font_color":        "rgb(10, 10, 10)",
        "fade_on_empty":     "true",
        "position":          "0, -80",
        "halign":            "center",
        "valign":            "center",
    },
    "shape": {
        "monitor":  "",
        "size":     "100, 100",
        "color":    "rgba(255, 255, 255, 0.1)",
        "position": "0, 0",
        "halign":   "center",
        "valign":   "center",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
#  Readers
# ─────────────────────────────────────────────────────────────────────────────

def read_hyprlock_blocks(path: Optional[Path] = None) -> list[ConfigBlock]:
    """Return all blocks from hyprlock.conf."""
    return read_blocks(path or HYPRLOCK_FILE)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

def update_hyprlock_field(
    path: Path,
    start_line: int,
    end_line: int,
    key: str,
    value: str,
) -> bool:
    """Update a single field within a hyprlock block."""
    return update_block_field(path, start_line, end_line, key, value)


def delete_hyprlock_block(path: Path, start_line: int, end_line: int) -> bool:
    """Delete the block spanning [start_line, end_line]."""
    return delete_block(path, start_line, end_line)


def add_hyprlock_block(
    block_type: str,
    overrides: Optional[dict[str, str]] = None,
    path: Optional[Path] = None,
) -> bool:
    """Append a new block of *block_type* to hyprlock.conf.

    *overrides* are merged on top of the block's default fields.
    Returns True on success.
    """
    if path is None:
        path = HYPRLOCK_FILE
    fields = dict(BLOCK_DEFAULTS.get(block_type, {}))
    if overrides:
        fields.update(overrides)
    return add_block(path, block_type, fields)
