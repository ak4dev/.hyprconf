"""Tests for hyprconf.file_edit — the atomic line-editing primitives."""

from __future__ import annotations

from pathlib import Path

import pytest
from hyprconf.file_edit import (
    append_block,
    delete_line,
    delete_lines,
    insert_line,
    insert_lines,
    read_lines,
    update_line,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "test.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_lines
# ---------------------------------------------------------------------------


def test_read_lines_normal(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\nc\n")
    assert read_lines(p) == ["a", "b", "c"]


def test_read_lines_missing_file(tmp_path: Path) -> None:
    assert read_lines(tmp_path / "nonexistent.conf") == []


def test_read_lines_empty_file(tmp_path: Path) -> None:
    p = _file(tmp_path, "")
    assert read_lines(p) == []


# ---------------------------------------------------------------------------
# update_line
# ---------------------------------------------------------------------------


def test_update_line_first(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\nc\n")
    assert update_line(p, 0, "X") is True
    assert read_lines(p) == ["X", "b", "c"]


def test_update_line_last(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\nc\n")
    assert update_line(p, 2, "Z") is True
    assert read_lines(p)[2] == "Z"


def test_update_line_out_of_range(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\n")
    assert update_line(p, 99, "X") is False
    assert read_lines(p) == ["a", "b"]


def test_update_line_negative_index(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\n")
    assert update_line(p, -1, "X") is False


# ---------------------------------------------------------------------------
# delete_line
# ---------------------------------------------------------------------------


def test_delete_line_middle(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\nc\n")
    assert delete_line(p, 1) is True
    assert read_lines(p) == ["a", "c"]


def test_delete_line_only_line(tmp_path: Path) -> None:
    p = _file(tmp_path, "only\n")
    assert delete_line(p, 0) is True
    assert read_lines(p) == []


def test_delete_line_out_of_range(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\n")
    assert delete_line(p, 5) is False


# ---------------------------------------------------------------------------
# delete_lines
# ---------------------------------------------------------------------------


def test_delete_lines_range(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\nc\nd\n")
    assert delete_lines(p, 1, 2) is True
    assert read_lines(p) == ["a", "d"]


def test_delete_lines_entire_file(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\nc\n")
    assert delete_lines(p, 0, 2) is True
    assert read_lines(p) == []


def test_delete_lines_invalid_range(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\n")
    assert delete_lines(p, 1, 0) is False  # start > end
    assert delete_lines(p, 0, 99) is False  # end out of range


# ---------------------------------------------------------------------------
# append_block
# ---------------------------------------------------------------------------


def test_append_block_to_empty(tmp_path: Path) -> None:
    p = _file(tmp_path, "")
    assert append_block(p, "new line") is True
    assert read_lines(p) == ["new line"]


def test_append_block_adds_separator(tmp_path: Path) -> None:
    p = _file(tmp_path, "existing\n")
    append_block(p, "new line")
    lines = read_lines(p)
    # There should be a blank separator between existing and new content
    assert lines[0] == "existing"
    assert lines[-1] == "new line"
    assert "" in lines  # separator present


def test_append_block_multiline(tmp_path: Path) -> None:
    p = _file(tmp_path, "")
    append_block(p, "line1\nline2\nline3")
    assert read_lines(p) == ["line1", "line2", "line3"]


def test_append_block_creates_parent_dirs(tmp_path: Path) -> None:
    p = tmp_path / "deep" / "nested" / "file.conf"
    assert append_block(p, "content") is True
    assert p.exists()


# ---------------------------------------------------------------------------
# insert_line / insert_lines
# ---------------------------------------------------------------------------


def test_insert_line_at_start(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\n")
    assert insert_line(p, 0, "X") is True
    assert read_lines(p) == ["X", "a", "b"]


def test_insert_line_at_end(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nb\n")
    assert insert_line(p, 99, "Z") is True
    assert read_lines(p)[-1] == "Z"


def test_insert_lines_batch(tmp_path: Path) -> None:
    p = _file(tmp_path, "a\nd\n")
    assert insert_lines(p, 1, ["b", "c"]) is True
    assert read_lines(p) == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# Atomicity: write never partially corrupts a file
# ---------------------------------------------------------------------------


def test_update_line_is_atomic(tmp_path: Path) -> None:
    """A successful update should not leave temp files behind."""
    p = _file(tmp_path, "a\nb\nc\n")
    update_line(p, 0, "X")
    tmp_files = list(tmp_path.glob(".hyprconf-tmp-*"))
    assert tmp_files == [], "Temp file should be cleaned up after write"


# ---------------------------------------------------------------------------
# _write_lines — exception cleanup (covers L47-52)
# ---------------------------------------------------------------------------


def test_write_lines_cleans_up_tmp_on_error(tmp_path: Path) -> None:
    """If an error occurs mid-write, the temp file should be removed."""
    import unittest.mock as _mock

    from hyprconf.file_edit import _write_lines

    p = tmp_path / "subdir" / "test.conf"
    p.parent.mkdir()
    p.write_text("original\n")

    with _mock.patch("os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            _write_lines(p, ["new content"])

    # Original file must be untouched
    assert p.read_text() == "original\n"
    # No temp files should linger
    assert list(tmp_path.glob("**/.hyprconf-tmp-*")) == []


def test_write_lines_follows_symlink(tmp_path: Path) -> None:
    """_write_lines must write to the symlink TARGET, not replace the symlink.

    Regression: os.replace(tmp, symlink_path) was replacing the symlink
    itself with a real file.  On the next sync, detect_gpu_and_link_monitor_config
    would rm -f that real file and recreate the symlink to the unchanged
    original target — silently discarding the user's edits.
    """
    from hyprconf.file_edit import _write_lines

    target = tmp_path / "laptopMonitors.conf"
    target.write_text("monitor=eDP-1,preferred,auto,auto\n")

    link = tmp_path / "monitors.conf"
    link.symlink_to(target)

    _write_lines(link, ["monitor=eDP-1,preferred,auto,auto,transform,1"])

    # The symlink must still be a symlink pointing to the same target
    assert link.is_symlink()
    assert link.resolve() == target.resolve()

    # The TARGET (stow file) must have the new content
    assert "transform,1" in target.read_text()

    # The symlink must also read back the new content
    assert "transform,1" in link.read_text()


# ---------------------------------------------------------------------------
# OSError paths in mutation primitives (covers L99-100, 115-116, 131-132, 147-148)
# ---------------------------------------------------------------------------


def test_append_block_returns_false_on_oserror(tmp_path: Path) -> None:
    import unittest.mock as _mock

    from hyprconf.file_edit import append_block

    p = tmp_path / "test.conf"
    p.write_text("line\n")
    with _mock.patch("hyprconf.file_edit._write_lines", side_effect=OSError("nope")):
        result = append_block(p, "new block")
    assert result is False


def test_delete_lines_returns_false_on_oserror(tmp_path: Path) -> None:
    import unittest.mock as _mock

    from hyprconf.file_edit import delete_lines

    p = tmp_path / "test.conf"
    p.write_text("a\nb\nc\n")
    with _mock.patch("hyprconf.file_edit._write_lines", side_effect=OSError("nope")):
        result = delete_lines(p, 0, 1)
    assert result is False


def test_insert_lines_returns_false_on_oserror(tmp_path: Path) -> None:
    import unittest.mock as _mock

    from hyprconf.file_edit import insert_lines

    p = tmp_path / "test.conf"
    p.write_text("a\nb\n")
    with _mock.patch("hyprconf.file_edit._write_lines", side_effect=OSError("nope")):
        result = insert_lines(p, 0, ["new"])
    assert result is False


def test_insert_line_returns_false_on_oserror(tmp_path: Path) -> None:
    import unittest.mock as _mock

    from hyprconf.file_edit import insert_line

    p = tmp_path / "test.conf"
    p.write_text("a\nb\n")
    with _mock.patch("hyprconf.file_edit._write_lines", side_effect=OSError("nope")):
        result = insert_line(p, 0, "new")
    assert result is False


# ---------------------------------------------------------------------------
# _write_lines double-exception: os.replace raises AND os.unlink raises
# (covers L50-51: the inner except OSError: pass inside the outer except)
# ---------------------------------------------------------------------------


def test_write_lines_double_exception_is_ignored(tmp_path: Path) -> None:
    """If os.replace AND os.unlink both raise, _write_lines re-raises the replace error."""
    import unittest.mock as _mock

    from hyprconf.file_edit import _write_lines

    p = tmp_path / "double.conf"
    p.write_text("original\n")

    def bad_replace(src, dst):
        raise OSError("replace failed")

    def bad_unlink(path):
        raise OSError("unlink failed")

    with _mock.patch("os.replace", bad_replace), _mock.patch("os.unlink", bad_unlink):
        try:
            _write_lines(p, ["new content"])
            raise AssertionError("Expected OSError")
        except OSError as e:
            assert "replace failed" in str(e)

    # Original file must be unchanged since replace failed
    assert p.read_text() == "original\n"


# ---------------------------------------------------------------------------
# strip_comment / COMMENT_RE
# ---------------------------------------------------------------------------


def test_strip_comment_removes_inline_comment() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("key = value  # comment") == "key = value"


def test_strip_comment_removes_line_comment() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("# full line comment") == ""


def test_strip_comment_preserves_plain_line() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("key = value") == "key = value"


def test_strip_comment_strips_surrounding_whitespace() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("   key = value   ") == "key = value"


def test_strip_comment_preserves_hex_color_6() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("col.active_border = #ff0000") == "col.active_border = #ff0000"


def test_strip_comment_preserves_hex_color_8() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("col.active_border = #ff0000ee") == "col.active_border = #ff0000ee"


def test_strip_comment_preserves_hex_with_trailing_comment() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("col = #ff0000 # red") == "col = #ff0000"


def test_strip_comment_preserves_multiple_hex() -> None:
    from hyprconf.file_edit import strip_comment

    result = strip_comment("gradient = #aabbcc #ddeeff 45deg")
    assert result == "gradient = #aabbcc #ddeeff 45deg"


def test_strip_comment_on_hash_only_line() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("#") == ""


def test_strip_comment_preserves_midline_hex_with_comment() -> None:
    from hyprconf.file_edit import strip_comment

    result = strip_comment("col = #112233 #445566  # gradient colors")
    assert result == "col = #112233 #445566"


def test_strip_comment_preserves_hex_color_3() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("color = #abc") == "color = #abc"


def test_strip_comment_preserves_hex_color_4() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("color = #abcd") == "color = #abcd"


def test_strip_comment_preserves_hex_3_with_trailing_comment() -> None:
    from hyprconf.file_edit import strip_comment

    assert strip_comment("color = #f0a # accent") == "color = #f0a"
