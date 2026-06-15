"""Tests for hyprconf.hyprlock — hyprlock config block reader/writer."""

from __future__ import annotations

from pathlib import Path

from hyprconf.hyprlock import (
    BLOCK_DEFAULTS,
    BLOCK_TYPES,
    add_hyprlock_block,
    delete_hyprlock_block,
    read_hyprlock_blocks,
    update_hyprlock_field,
)

HYPRLOCK_CONF = """\
general {
    disable_loading_bar = false
    hide_cursor = true
    grace = 0
    no_fade_in = false
}

background {
    monitor =
    path = screenshot
    blur_passes = 3
    blur_size = 7
    brightness = 0.7
}

label {
    monitor =
    text = hello
    color = rgba(255, 255, 255, 0.9)
    font_size = 24
    font_family = JetBrainsMono Nerd Font
    position = 0, 0
    halign = center
    valign = center
}

input-field {
    monitor =
    size = 200, 50
    outline_thickness = 3
    inner_color = rgb(200, 200, 200)
    font_color = rgb(10, 10, 10)
    position = 0, -80
    halign = center
    valign = center
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lock_file(hypr_dir: Path, content: str = HYPRLOCK_CONF) -> Path:
    p = hypr_dir / "hyprlock.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_hyprlock_blocks
# ---------------------------------------------------------------------------


def test_reads_all_block_types(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    types = [b.block_type for b in blocks]
    assert "general" in types
    assert "background" in types
    assert "label" in types
    assert "input-field" in types


def test_reads_general_fields(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    general = next(b for b in blocks if b.block_type == "general")
    assert general.fields["hide_cursor"] == "true"
    assert general.fields["grace"] == "0"


def test_reads_background_fields(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    bg = next(b for b in blocks if b.block_type == "background")
    assert bg.fields["path"] == "screenshot"
    assert bg.fields["blur_passes"] == "3"
    assert bg.fields["brightness"] == "0.7"


def test_reads_input_field_block(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    inp = next(b for b in blocks if b.block_type == "input-field")
    assert inp.fields["size"] == "200, 50"
    assert inp.fields["halign"] == "center"


def test_missing_file_returns_empty(hypr_dir: Path) -> None:
    assert read_hyprlock_blocks(hypr_dir / "nonexistent.conf") == []


def test_empty_file_returns_empty(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir, "")
    assert read_hyprlock_blocks(p) == []


# ---------------------------------------------------------------------------
# update_hyprlock_field
# ---------------------------------------------------------------------------


def test_update_general_field(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    general = next(b for b in blocks if b.block_type == "general")
    assert (
        update_hyprlock_field(p, general.start_line, general.end_line, "hide_cursor", "false")
        is True
    )
    updated = read_hyprlock_blocks(p)
    gen = next(b for b in updated if b.block_type == "general")
    assert gen.fields["hide_cursor"] == "false"


def test_update_background_brightness(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    bg = next(b for b in blocks if b.block_type == "background")
    update_hyprlock_field(p, bg.start_line, bg.end_line, "brightness", "0.5")
    updated = read_hyprlock_blocks(p)
    bg2 = next(b for b in updated if b.block_type == "background")
    assert bg2.fields["brightness"] == "0.5"


def test_update_inserts_new_field(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    general = next(b for b in blocks if b.block_type == "general")
    update_hyprlock_field(p, general.start_line, general.end_line, "new_key", "new_value")
    updated = read_hyprlock_blocks(p)
    gen = next(b for b in updated if b.block_type == "general")
    assert gen.fields["new_key"] == "new_value"


# ---------------------------------------------------------------------------
# delete_hyprlock_block
# ---------------------------------------------------------------------------


def test_delete_label_block(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    blocks = read_hyprlock_blocks(p)
    label = next(b for b in blocks if b.block_type == "label")
    assert delete_hyprlock_block(p, label.start_line, label.end_line) is True
    remaining = read_hyprlock_blocks(p)
    assert not any(b.block_type == "label" for b in remaining)


def test_delete_preserves_other_blocks(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir)
    initial_count = len(read_hyprlock_blocks(p))
    blocks = read_hyprlock_blocks(p)
    label = next(b for b in blocks if b.block_type == "label")
    delete_hyprlock_block(p, label.start_line, label.end_line)
    remaining = read_hyprlock_blocks(p)
    assert len(remaining) == initial_count - 1


# ---------------------------------------------------------------------------
# add_hyprlock_block
# ---------------------------------------------------------------------------


def test_add_general_block_defaults(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir, "")
    assert add_hyprlock_block("general", path=p) is True
    blocks = read_hyprlock_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].block_type == "general"
    assert "hide_cursor" in blocks[0].fields


def test_add_background_block(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir, "")
    add_hyprlock_block("background", path=p)
    blocks = read_hyprlock_blocks(p)
    assert blocks[0].block_type == "background"
    assert blocks[0].fields["path"] == "screenshot"


def test_add_block_with_overrides(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir, "")
    add_hyprlock_block(
        "background", overrides={"path": "~/wallpaper.jpg", "brightness": "0.5"}, path=p
    )
    blocks = read_hyprlock_blocks(p)
    assert blocks[0].fields["path"] == "~/wallpaper.jpg"
    assert blocks[0].fields["brightness"] == "0.5"


def test_add_label_block(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir, "")
    add_hyprlock_block("label", overrides={"text": "Hello", "font_size": "32"}, path=p)
    blocks = read_hyprlock_blocks(p)
    assert blocks[0].fields["text"] == "Hello"
    assert blocks[0].fields["font_size"] == "32"


def test_add_input_field_block(hypr_dir: Path) -> None:
    p = _lock_file(hypr_dir, "")
    add_hyprlock_block("input-field", path=p)
    blocks = read_hyprlock_blocks(p)
    assert blocks[0].block_type == "input-field"
    assert "size" in blocks[0].fields


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------


def test_block_types_known(hypr_dir: Path) -> None:
    assert "general" in BLOCK_TYPES
    assert "background" in BLOCK_TYPES
    assert "label" in BLOCK_TYPES
    assert "input-field" in BLOCK_TYPES


def test_block_defaults_populated(hypr_dir: Path) -> None:
    assert "hide_cursor" in BLOCK_DEFAULTS["general"]
    assert "blur_passes" in BLOCK_DEFAULTS["background"]
    assert "font_size" in BLOCK_DEFAULTS["label"]
    assert "size" in BLOCK_DEFAULTS["input-field"]
