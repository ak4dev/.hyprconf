"""hyprconf.file_edit — generic line-based Hyprland config file editor.

Provides low-level primitives for reading, updating, inserting, and deleting
lines in any Hyprland config file.  Higher-level modules (keybinds, rules,
monitors) build on top of these functions.

All mutations are atomic: the file is written to a sibling temp file and then
renamed into place, so a crash mid-write can never corrupt the config.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
#  Shared parsing helpers (used by block_conf, hyprpaper, keybinds, monitors)
# ─────────────────────────────────────────────────────────────────────────────

SOURCE_RE = re.compile(r"^source\s*=\s*(.+)$")

COMMENT_RE = re.compile(
    r"(?<!\S)#"
    r"(?![0-9a-fA-F]{8}\b)"
    r"(?![0-9a-fA-F]{6}\b)"
    r"(?![0-9a-fA-F]{4}\b)"
    r"(?![0-9a-fA-F]{3}\b)"
    r".*$"
)


def strip_comment(line: str) -> str:
    """Remove an inline ``# …`` comment and surrounding whitespace."""
    return COMMENT_RE.sub("", line).strip()


def resolve_source_paths(directive_value: str, relative_to: Path) -> list[Path]:
    """Expand a ``source = …`` value to a list of concrete paths.

    Handles ``~``, environment variables, relative paths, and glob patterns.
    """
    raw = os.path.expanduser(os.path.expandvars(directive_value.strip()))
    src = Path(raw)
    if not src.is_absolute():
        src = relative_to / src
    if "*" in src.name:
        return sorted(src.parent.glob(src.name))
    return [src]


# ─────────────────────────────────────────────────────────────────────────────
#  Read helpers
# ─────────────────────────────────────────────────────────────────────────────


def read_lines(path: Path) -> list[str]:
    """Return the file's lines (without trailing newline on each).

    Returns an empty list if the file does not exist.
    """
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


# ─────────────────────────────────────────────────────────────────────────────
#  Atomic write helper
# ─────────────────────────────────────────────────────────────────────────────


def _write_lines(path: Path, lines: list[str]) -> None:
    """Write *lines* to *path* atomically (temp-file + rename).

    Resolves symlinks first so that ``os.replace`` updates the symlink
    *target* rather than replacing the symlink itself.  Without this,
    stow-managed paths (e.g. ``monitors.conf → laptopMonitors.conf``) would
    be converted to real files, which ``detect_gpu_and_link_monitor_config``
    then deletes on the next sync — silently discarding all edits.
    """
    body = "\n".join(lines) + ("\n" if lines else "")
    atomic_write_text(path, body)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write *content* to *path* atomically (temp-file + rename).

    Public helper for callers that produce already-joined text rather than a
    list of lines.  Resolves symlinks so the *target* is updated, not the
    link itself, matching the behaviour of :func:`_write_lines`.
    """
    if path.is_symlink() or path.exists():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".hyprconf-tmp-")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ─────────────────────────────────────────────────────────────────────────────
#  Mutation primitives
# ─────────────────────────────────────────────────────────────────────────────


def update_line(path: Path, line_idx: int, new_content: str) -> bool:
    """Replace line *line_idx* (0-based) with *new_content*.

    Returns True on success, False if the index is out of range.
    """
    lines = read_lines(path)
    if not (0 <= line_idx < len(lines)):
        return False
    lines[line_idx] = new_content
    _write_lines(path, lines)
    return True


def delete_line(path: Path, line_idx: int) -> bool:
    """Delete line *line_idx* (0-based).

    Returns True on success, False if the index is out of range.
    """
    lines = read_lines(path)
    if not (0 <= line_idx < len(lines)):
        return False
    del lines[line_idx]
    _write_lines(path, lines)
    return True


def append_block(path: Path, block: str) -> bool:
    """Append *block* (possibly multi-line) to the end of *path*.

    A blank line is inserted before the block if the file already has content.
    Returns True on success.
    """
    lines = read_lines(path)
    block_lines = block.splitlines()
    if lines and lines[-1].strip():
        lines.append("")  # blank separator
    lines.extend(block_lines)
    try:
        _write_lines(path, lines)
        return True
    except OSError:
        return False


def delete_lines(path: Path, start_idx: int, end_idx: int) -> bool:
    """Delete lines *start_idx* through *end_idx* inclusive (0-based).

    Returns True on success, False if the range is invalid.
    """
    lines = read_lines(path)
    if not (0 <= start_idx <= end_idx < len(lines)):
        return False
    del lines[start_idx : end_idx + 1]
    try:
        _write_lines(path, lines)
        return True
    except OSError:
        return False


def insert_lines(path: Path, line_idx: int, new_lines: list[str]) -> bool:
    """Insert *new_lines* before position *line_idx* (0-based).

    If *line_idx* >= len(lines), lines are appended.
    Returns True on success.
    """
    lines = read_lines(path)
    line_idx = min(line_idx, len(lines))
    lines[line_idx:line_idx] = new_lines
    try:
        _write_lines(path, lines)
        return True
    except OSError:
        return False
