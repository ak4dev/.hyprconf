"""Tests for hyprconf.hypridle — hypridle config block reader/writer."""

from __future__ import annotations

from pathlib import Path

from hyprconf.hypridle import (
    BLOCK_DEFAULTS,
    BLOCK_TYPES,
    add_hypridle_block,
    read_hypridle_blocks,
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
# Schema constants
# ---------------------------------------------------------------------------


def test_block_types_known(hypr_dir: Path) -> None:
    assert "general" in BLOCK_TYPES
    assert "listener" in BLOCK_TYPES


def test_block_defaults_exist(hypr_dir: Path) -> None:
    assert "lock_cmd" in BLOCK_DEFAULTS["general"]
    assert "timeout" in BLOCK_DEFAULTS["listener"]
