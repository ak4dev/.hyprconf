"""Tests for hyprconf.block_conf — generic block-based config parser/writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from hyprconf.block_conf import (
    ConfigBlock,
    add_block,
    delete_block,
    read_blocks,
    update_block_field,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _conf(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.conf"
    p.write_text(content)
    return p


SIMPLE_CONF = """\
general {
    lock_cmd = pidof hyprlock || hyprlock
    before_sleep_cmd = hyprlock
}
"""

MULTI_BLOCK_CONF = """\
general {
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

LABELED_BLOCK_CONF = """\
background = main {
    path = ~/wallpaper.jpg
    blur_passes = 3
}
"""

SPLIT_BRACE_CONF = """\
general
{
    key = value
}
"""


# ---------------------------------------------------------------------------
# read_blocks
# ---------------------------------------------------------------------------

def test_read_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "empty.conf"
    p.write_text("")
    assert read_blocks(p) == []


def test_read_missing_file(tmp_path: Path) -> None:
    assert read_blocks(tmp_path / "missing.conf") == []


def test_read_single_block(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    blocks = read_blocks(p)
    assert len(blocks) == 1
    b = blocks[0]
    assert b.block_type == "general"
    assert b.fields["lock_cmd"] == "pidof hyprlock || hyprlock"
    assert b.fields["before_sleep_cmd"] == "hyprlock"


def test_read_multiple_blocks(tmp_path: Path) -> None:
    p = _conf(tmp_path, MULTI_BLOCK_CONF)
    blocks = read_blocks(p)
    assert len(blocks) == 3
    types = [b.block_type for b in blocks]
    assert types.count("listener") == 2
    assert types[0] == "general"


def test_read_block_fields_correct(tmp_path: Path) -> None:
    p = _conf(tmp_path, MULTI_BLOCK_CONF)
    listeners = [b for b in read_blocks(p) if b.block_type == "listener"]
    assert listeners[0].fields["timeout"] == "300"
    assert listeners[1].fields["timeout"] == "600"
    assert listeners[1].fields["on-resume"] == "hyprctl dispatch dpms on"


def test_read_labeled_block(tmp_path: Path) -> None:
    p = _conf(tmp_path, LABELED_BLOCK_CONF)
    blocks = read_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].block_type == "background"
    assert blocks[0].label == "main"
    assert blocks[0].fields["path"] == "~/wallpaper.jpg"


def test_read_split_brace_style(tmp_path: Path) -> None:
    p = _conf(tmp_path, SPLIT_BRACE_CONF)
    blocks = read_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].fields["key"] == "value"


def test_read_ignores_comments(tmp_path: Path) -> None:
    p = _conf(tmp_path, """\
# Top comment
general {
    # Inner comment
    key = value  # inline comment
}
""")
    blocks = read_blocks(p)
    assert blocks[0].fields["key"] == "value"


def test_block_line_indices(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    assert b.start_line == 0
    assert b.end_line == 3  # closing "}" on line index 3


def test_field_line_idx(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    idx = b.field_line_idx("lock_cmd")
    assert idx > 0
    from hyprconf.file_edit import read_lines
    line = read_lines(p)[idx]
    assert "lock_cmd" in line


def test_field_line_idx_missing_key(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    assert b.field_line_idx("nonexistent") == -1


# ---------------------------------------------------------------------------
# update_block_field
# ---------------------------------------------------------------------------

def test_update_existing_field(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    assert update_block_field(p, b.start_line, b.end_line, "lock_cmd", "hyprlock") is True
    b2 = read_blocks(p)[0]
    assert b2.fields["lock_cmd"] == "hyprlock"


def test_update_inserts_new_field(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    assert update_block_field(p, b.start_line, b.end_line, "new_key", "hello") is True
    b2 = read_blocks(p)[0]
    assert b2.fields["new_key"] == "hello"


def test_update_preserves_indentation(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    update_block_field(p, b.start_line, b.end_line, "lock_cmd", "new_cmd")
    from hyprconf.file_edit import read_lines
    lines = read_lines(p)
    lock_line = next(l for l in lines if "lock_cmd" in l)
    assert lock_line.startswith("    ")


# ---------------------------------------------------------------------------
# delete_block
# ---------------------------------------------------------------------------

def test_delete_only_block(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    assert delete_block(p, b.start_line, b.end_line) is True
    assert read_blocks(p) == []


def test_delete_one_of_many(tmp_path: Path) -> None:
    p = _conf(tmp_path, MULTI_BLOCK_CONF)
    blocks = read_blocks(p)
    # Delete the first listener (index 1)
    listener = blocks[1]
    delete_block(p, listener.start_line, listener.end_line)
    remaining = read_blocks(p)
    # Should have general + 1 listener left
    assert len(remaining) == 2
    assert remaining[0].block_type == "general"


# ---------------------------------------------------------------------------
# add_block
# ---------------------------------------------------------------------------

def test_add_block_to_empty(tmp_path: Path) -> None:
    p = tmp_path / "new.conf"
    p.write_text("")
    assert add_block(p, "general", {"key": "value"}) is True
    blocks = read_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].block_type == "general"
    assert blocks[0].fields["key"] == "value"


def test_add_block_with_label(tmp_path: Path) -> None:
    p = tmp_path / "new.conf"
    p.write_text("")
    add_block(p, "background", {"path": "~/wallpaper.jpg"}, label="main")
    from hyprconf.file_edit import read_lines
    content = "\n".join(read_lines(p))
    assert "background = main {" in content


def test_add_multiple_blocks(tmp_path: Path) -> None:
    p = tmp_path / "new.conf"
    p.write_text("")
    add_block(p, "listener", {"timeout": "300", "on-timeout": "lock"})
    add_block(p, "listener", {"timeout": "600", "on-timeout": "dpms off"})
    blocks = read_blocks(p)
    assert len(blocks) == 2
    assert blocks[0].fields["timeout"] == "300"
    assert blocks[1].fields["timeout"] == "600"


# ---------------------------------------------------------------------------
# ConfigBlock helpers
# ---------------------------------------------------------------------------

def test_config_block_get_default(tmp_path: Path) -> None:
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    assert b.get("lock_cmd") == "pidof hyprlock || hyprlock"
    assert b.get("missing_key", "fallback") == "fallback"


def test_config_block_display_title(tmp_path: Path) -> None:
    p = _conf(tmp_path, MULTI_BLOCK_CONF)
    blocks = read_blocks(p)
    listener = blocks[1]
    title = listener.display_title()
    assert "listener" in title
    assert "300" in title  # timeout shown in title


def test_config_block_is_disabled_false(tmp_path: Path) -> None:
    """ConfigBlock doesn't have is_disabled; that's on MonitorConfig."""
    p = _conf(tmp_path, SIMPLE_CONF)
    b = read_blocks(p)[0]
    # Verify basic field access works
    assert b.block_type == "general"
