"""Tests for hyprconf.hyprpaper — hyprpaper config reader/writer."""

from __future__ import annotations

from pathlib import Path

from hyprconf.hyprpaper import (
    add_preload,
    add_wallpaper_block,
    delete_preload,
    delete_wallpaper_line,
    read_all,
    read_preloads,
    read_settings,
    read_wallpaper_blocks,
    read_wallpaper_lines,
    set_setting,
    set_wallpaper_line,
    update_wallpaper_block_field,
)

LINE_BASED_CONF = """\
$wallpaper = ~/wallpapers/gruvbox.jpg

preload = ~/wallpapers/gruvbox.jpg
preload = ~/wallpapers/catppuccin.jpg

wallpaper = HDMI-A-1,~/wallpapers/gruvbox.jpg
wallpaper = DP-1,~/wallpapers/catppuccin.jpg

splash = false
ipc = true
"""

BLOCK_BASED_CONF = """\
preload = ~/wallpapers/gruvbox.jpg

wallpaper {
    monitor = HDMI-A-1
    path = ~/wallpapers/gruvbox.jpg
    fit_mode = cover
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _paper_file(hypr_dir: Path, content: str = LINE_BASED_CONF) -> Path:
    p = hypr_dir / "hyprpaper.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_preloads
# ---------------------------------------------------------------------------


def test_reads_preloads(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    preloads = read_preloads(p)
    assert len(preloads) == 2
    paths = [pr.path for pr in preloads]
    assert "~/wallpapers/gruvbox.jpg" in paths
    assert "~/wallpapers/catppuccin.jpg" in paths


def test_preload_line_idx(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    preloads = read_preloads(p)
    for pr in preloads:
        assert pr.line_idx >= 0
        assert pr.file_path == p


def test_read_preloads_empty_file(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "")
    assert read_preloads(p) == []


def test_read_preloads_missing_file(hypr_dir: Path) -> None:
    assert read_preloads(hypr_dir / "nonexistent.conf") == []


# ---------------------------------------------------------------------------
# read_wallpaper_lines
# ---------------------------------------------------------------------------


def test_reads_wallpaper_lines(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    lines = read_wallpaper_lines(p)
    assert len(lines) == 2
    monitors = [w.monitor for w in lines]
    assert "HDMI-A-1" in monitors
    assert "DP-1" in monitors


def test_wallpaper_line_path(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    lines = read_wallpaper_lines(p)
    hdmi = next(w for w in lines if w.monitor == "HDMI-A-1")
    assert hdmi.path == "~/wallpapers/gruvbox.jpg"


# ---------------------------------------------------------------------------
# read_wallpaper_blocks
# ---------------------------------------------------------------------------


def test_reads_wallpaper_blocks(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, BLOCK_BASED_CONF)
    blocks = read_wallpaper_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].block_type == "wallpaper"
    assert blocks[0].fields["monitor"] == "HDMI-A-1"
    assert blocks[0].fields["fit_mode"] == "cover"


def test_reads_no_blocks_from_line_based(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, LINE_BASED_CONF)
    # wallpaper = MONITOR,PATH lines are NOT blocks
    blocks = read_wallpaper_blocks(p)
    assert blocks == []


# ---------------------------------------------------------------------------
# read_settings
# ---------------------------------------------------------------------------


def test_reads_settings(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    settings = read_settings(p)
    keys = {s.key.lower() for s in settings}
    assert "splash" in keys
    assert "ipc" in keys


def test_reads_variable_definition(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    settings = read_settings(p)
    var = next((s for s in settings if s.key.startswith("$")), None)
    assert var is not None
    assert var.key == "$wallpaper"
    assert "gruvbox" in var.value


def test_setting_value(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    settings = read_settings(p)
    splash = next(s for s in settings if s.key.lower() == "splash")
    assert splash.value == "false"


# ---------------------------------------------------------------------------
# read_all
# ---------------------------------------------------------------------------


def test_read_all_keys(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    result = read_all(p)
    assert "preloads" in result
    assert "wallpaper_lines" in result
    assert "wallpaper_blocks" in result
    assert "settings" in result


def test_read_all_counts(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir)
    result = read_all(p)
    assert len(result["preloads"]) == 2
    assert len(result["wallpaper_lines"]) == 2


# ---------------------------------------------------------------------------
# add_preload
# ---------------------------------------------------------------------------


def test_add_preload(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "")
    assert add_preload("~/wallpapers/new.jpg", file=p) is True
    preloads = read_preloads(p)
    assert len(preloads) == 1
    assert preloads[0].path == "~/wallpapers/new.jpg"


def test_add_preload_preserves_existing(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "preload = ~/a.jpg\n")
    add_preload("~/b.jpg", file=p)
    preloads = read_preloads(p)
    assert len(preloads) == 2


# ---------------------------------------------------------------------------
# delete_preload
# ---------------------------------------------------------------------------


def test_delete_preload(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "preload = ~/a.jpg\npreload = ~/b.jpg\n")
    preloads = read_preloads(p)
    first = preloads[0]
    assert delete_preload(first.file_path, first.line_idx) is True
    remaining = read_preloads(p)
    assert len(remaining) == 1
    assert remaining[0].path == "~/b.jpg"


# ---------------------------------------------------------------------------
# set_wallpaper_line
# ---------------------------------------------------------------------------


def test_set_wallpaper_line_appends(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "")
    assert set_wallpaper_line("HDMI-A-1", "~/wallpapers/gruvbox.jpg", file=p) is True
    lines = read_wallpaper_lines(p)
    assert len(lines) == 1
    assert lines[0].monitor == "HDMI-A-1"


def test_set_wallpaper_line_updates_existing(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "wallpaper = HDMI-A-1,~/old.jpg\n")
    set_wallpaper_line("HDMI-A-1", "~/new.jpg", file=p)
    lines = read_wallpaper_lines(p)
    assert len(lines) == 1
    assert lines[0].path == "~/new.jpg"


def test_set_wallpaper_line_preserves_other_monitors(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "wallpaper = HDMI-A-1,~/a.jpg\nwallpaper = DP-1,~/b.jpg\n")
    set_wallpaper_line("HDMI-A-1", "~/new.jpg", file=p)
    lines = read_wallpaper_lines(p)
    dp1 = next(l for l in lines if l.monitor == "DP-1")
    assert dp1.path == "~/b.jpg"  # unchanged


# ---------------------------------------------------------------------------
# delete_wallpaper_line
# ---------------------------------------------------------------------------


def test_delete_wallpaper_line(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "wallpaper = HDMI-A-1,~/a.jpg\nwallpaper = DP-1,~/b.jpg\n")
    lines = read_wallpaper_lines(p)
    first = lines[0]
    assert delete_wallpaper_line(first.file_path, first.line_idx) is True
    remaining = read_wallpaper_lines(p)
    assert len(remaining) == 1


# ---------------------------------------------------------------------------
# add_wallpaper_block
# ---------------------------------------------------------------------------


def test_add_wallpaper_block(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "")
    assert add_wallpaper_block("HDMI-A-1", "~/wallpapers/gruvbox.jpg", file=p) is True
    blocks = read_wallpaper_blocks(p)
    assert len(blocks) == 1
    assert blocks[0].fields["monitor"] == "HDMI-A-1"
    assert blocks[0].fields["path"] == "~/wallpapers/gruvbox.jpg"
    assert blocks[0].fields["fit_mode"] == "cover"


# ---------------------------------------------------------------------------
# set_setting
# ---------------------------------------------------------------------------


def test_set_setting_appends(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "")
    assert set_setting("splash", "true", file=p) is True
    settings = read_settings(p)
    splash = next(s for s in settings if s.key.lower() == "splash")
    assert splash.value == "true"


def test_set_setting_updates_existing(hypr_dir: Path) -> None:
    p = _paper_file(hypr_dir, "splash = false\n")
    set_setting("splash", "true", file=p)
    settings = read_settings(p)
    assert len([s for s in settings if s.key.lower() == "splash"]) == 1
    splash = next(s for s in settings if s.key.lower() == "splash")
    assert splash.value == "true"


# ---------------------------------------------------------------------------
# update_wallpaper_block_field (covers L228)
# ---------------------------------------------------------------------------


def test_update_wallpaper_block_field(hypr_dir: Path) -> None:
    from hyprconf.hyprpaper import (
        HYPRPAPER_FILE,
        add_wallpaper_block,
        read_wallpaper_blocks,
    )

    HYPRPAPER_FILE.write_text("")
    add_wallpaper_block("eDP-1", "/tmp/wall.png", "cover", file=HYPRPAPER_FILE)
    blocks = read_wallpaper_blocks(HYPRPAPER_FILE)
    assert len(blocks) == 1
    b = blocks[0]
    ok = update_wallpaper_block_field(HYPRPAPER_FILE, b.start_line, b.end_line, "fit_mode", "fill")
    assert ok is True
    assert "fill" in HYPRPAPER_FILE.read_text()


# ---------------------------------------------------------------------------
# set_setting with $variable key (covers L250: key.startswith("$") branch)
# ---------------------------------------------------------------------------


def test_set_setting_updates_variable_key(hypr_dir: Path) -> None:
    from hyprconf.hyprpaper import HYPRPAPER_FILE, read_settings, set_setting

    HYPRPAPER_FILE.write_text("$WALLPAPER = /old/path\n")
    result = set_setting("$WALLPAPER", "/new/path", file=HYPRPAPER_FILE)
    assert result is True
    settings = read_settings(HYPRPAPER_FILE)
    entry = next(s for s in settings if s.key == "$WALLPAPER")
    assert entry.value == "/new/path"
