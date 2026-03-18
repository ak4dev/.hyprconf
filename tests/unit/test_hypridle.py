"""Tests for hyprconf.hypridle — hypridle config block reader/writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from hyprconf.hypridle import (
    BLOCK_DEFAULTS,
    BLOCK_TYPES,
    add_hypridle_block,
    add_listener,
    delete_hypridle_block,
    read_hypridle_blocks,
    update_hypridle_field,
)

HYPRIDLE_CONF = """\
general {
    lock_cmd = pidof hyprlock || hyprlock
    before_sleep_cmd = hyprlock
    after_sleep_cmd = hyprctl dispatch dpms on
    ignore_dbus_inhibit = false
}

listener {
    timeout = 300
    on-timeout = hyprlock
}

listener {
    timeout = 600
    on-timeout = hyprctl dispatch dpms off
    on-resume = hyprctl dispatch dpms on
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _idle_file(hypr_dir: Path, content: str = HYPRIDLE_CONF) -> Path:
    p = hypr_dir / "hypridle.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_hypridle_blocks
# ---------------------------------------------------------------------------

def test_reads_all_blocks(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    assert len(blocks) == 3


def test_reads_general_block(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    general = next(b for b in blocks if b.block_type == "general")
    assert general.fields["lock_cmd"] == "pidof hyprlock || hyprlock"
    assert general.fields["ignore_dbus_inhibit"] == "false"


def test_reads_listener_blocks(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    listeners = [b for b in blocks if b.block_type == "listener"]
    assert len(listeners) == 2
    timeouts = {b.fields["timeout"] for b in listeners}
    assert timeouts == {"300", "600"}


def test_missing_file_returns_empty(hypr_dir: Path) -> None:
    p = hypr_dir / "nonexistent.conf"
    assert read_hypridle_blocks(p) == []


def test_empty_file_returns_empty(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    assert read_hypridle_blocks(p) == []


# ---------------------------------------------------------------------------
# update_hypridle_field
# ---------------------------------------------------------------------------

def test_update_general_field(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    general = next(b for b in blocks if b.block_type == "general")
    assert update_hypridle_field(p, general.start_line, general.end_line,
                                 "ignore_dbus_inhibit", "true") is True
    updated = read_hypridle_blocks(p)
    updated_general = next(b for b in updated if b.block_type == "general")
    assert updated_general.fields["ignore_dbus_inhibit"] == "true"


def test_update_listener_timeout(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    listener = next(b for b in blocks if b.block_type == "listener")
    update_hypridle_field(p, listener.start_line, listener.end_line, "timeout", "120")
    updated = read_hypridle_blocks(p)
    listener_updated = next(b for b in updated if b.block_type == "listener")
    assert listener_updated.fields["timeout"] == "120"


def test_update_inserts_new_field(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    general = next(b for b in blocks if b.block_type == "general")
    update_hypridle_field(p, general.start_line, general.end_line, "new_field", "value")
    updated = read_hypridle_blocks(p)
    gen = next(b for b in updated if b.block_type == "general")
    assert gen.fields["new_field"] == "value"


# ---------------------------------------------------------------------------
# delete_hypridle_block
# ---------------------------------------------------------------------------

def test_delete_listener_block(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    blocks = read_hypridle_blocks(p)
    listener = next(b for b in blocks if b.block_type == "listener")
    assert delete_hypridle_block(p, listener.start_line, listener.end_line) is True
    remaining = read_hypridle_blocks(p)
    assert len(remaining) == 2  # general + 1 listener


def test_delete_all_blocks(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir)
    while True:
        blocks = read_hypridle_blocks(p)
        if not blocks:
            break
        b = blocks[0]
        delete_hypridle_block(p, b.start_line, b.end_line)
    assert read_hypridle_blocks(p) == []


# ---------------------------------------------------------------------------
# add_hypridle_block
# ---------------------------------------------------------------------------

def test_add_general_block_uses_defaults(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    assert add_hypridle_block("general", path=p) is True
    blocks = read_hypridle_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].block_type == "general"
    assert "lock_cmd" in blocks[0].fields


def test_add_listener_block(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    add_hypridle_block("listener", path=p)
    blocks = read_hypridle_blocks(p)
    assert blocks[0].block_type == "listener"
    assert "timeout" in blocks[0].fields


def test_add_block_with_overrides(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    add_hypridle_block("listener", overrides={"timeout": "60", "on-timeout": "lock"}, path=p)
    blocks = read_hypridle_blocks(p)
    assert blocks[0].fields["timeout"] == "60"
    assert blocks[0].fields["on-timeout"] == "lock"


def test_add_listener_skips_empty_on_resume(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    add_hypridle_block("listener", path=p)
    text = p.read_text()
    # on-resume should not appear if empty
    assert "on-resume =" not in text


# ---------------------------------------------------------------------------
# add_listener convenience function
# ---------------------------------------------------------------------------

def test_add_listener_shortcut(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    assert add_listener("180", "hyprlock", path=p) is True
    blocks = read_hypridle_blocks(p)
    assert blocks[0].fields["timeout"] == "180"
    assert blocks[0].fields["on-timeout"] == "hyprlock"


def test_add_listener_with_on_resume(hypr_dir: Path) -> None:
    p = _idle_file(hypr_dir, "")
    add_listener("600", "hyprctl dispatch dpms off",
                 on_resume="hyprctl dispatch dpms on", path=p)
    blocks = read_hypridle_blocks(p)
    assert blocks[0].fields["on-resume"] == "hyprctl dispatch dpms on"


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

def test_block_types_known(hypr_dir: Path) -> None:
    assert "general" in BLOCK_TYPES
    assert "listener" in BLOCK_TYPES


def test_block_defaults_exist(hypr_dir: Path) -> None:
    assert "lock_cmd" in BLOCK_DEFAULTS["general"]
    assert "timeout" in BLOCK_DEFAULTS["listener"]
