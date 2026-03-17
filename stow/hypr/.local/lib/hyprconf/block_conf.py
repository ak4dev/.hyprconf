"""hyprconf.block_conf — generic parser/writer for block-based Hyprland config files.

Block format (used by hyprlock.conf, hypridle.conf):

    block_type {
        key = value
        key = value
    }

This module is the single reusable layer for all block-based configs.  Callers
(hyprlock.py, hypridle.py, hyprpaper.py) wrap it with type-specific knowledge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .file_edit import read_lines, append_block, update_line, delete_lines, insert_lines

# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

_COMMENT_RE  = re.compile(r"(^|\s)#.*$")
_KEY_VAL_RE  = re.compile(r"^\s*([A-Za-z0-9_\-\.]+)\s*=\s*(.*)$")
# Matches:  "block_type {" or "block_type = label {"  (brace may be absent for split-brace style)
_BLOCK_RE    = re.compile(r"^([A-Za-z0-9_\-]+)\s*(?:=\s*([^\{]+?))?\s*\{?\s*$")


def _strip(line: str) -> str:
    return _COMMENT_RE.sub("", line).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Data type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConfigBlock:
    """A single block from a block-based Hyprland config file."""

    block_type: str                   # e.g. "general", "listener", "background"
    fields:     dict[str, str]        # key → value pairs (in order)
    file_path:  Path
    start_line: int                   # 0-based index of opening line (e.g. "general {")
    end_line:   int                   # 0-based index of closing "}"
    label:      str = ""              # optional inline label (between "=" and "{")

    # ── Convenience helpers ───────────────────────────────────────────────────

    def get(self, key: str, default: str = "") -> str:
        return self.fields.get(key, default)

    def field_line_idx(self, key: str) -> int:
        """Return the absolute file line index for *key* within this block.

        Returns -1 if the key is not found.
        """
        lines = read_lines(self.file_path)
        for i in range(self.start_line, min(self.end_line + 1, len(lines))):
            m = _KEY_VAL_RE.match(_strip(lines[i]))
            if m and m.group(1) == key:
                return i
        return -1

    def display_title(self) -> str:
        """Short label for display in the TUI sidebar."""
        parts = [self.block_type]
        for hint_key in ("monitor", "timeout"):
            v = self.fields.get(hint_key, "")
            if v:
                parts.append(v)
                break
        return "  ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
#  Parser
# ─────────────────────────────────────────────────────────────────────────────

def read_blocks(path: Path) -> list[ConfigBlock]:
    """Parse all top-level blocks from *path*.

    Handles both single-line brace style:
        block_type {
            key = value
        }
    and split-brace style (rare but valid):
        block_type
        {
            key = value
        }

    Returns an empty list if the file does not exist.
    """
    if not path.exists():
        return []

    blocks: list[ConfigBlock] = []
    lines  = read_lines(path)
    i = 0

    while i < len(lines):
        s = _strip(lines[i])
        if not s:
            i += 1
            continue

        m = _BLOCK_RE.match(s)
        if not m:
            i += 1
            continue

        block_type = m.group(1)
        label      = (m.group(2) or "").strip()
        open_line  = i

        # If no "{" on this line, look ahead for it
        if "{" not in s:
            j = i + 1
            found_brace = False
            while j < len(lines):
                s2 = _strip(lines[j])
                if s2 == "{":
                    open_line  = j
                    found_brace = True
                    i = j + 1
                    break
                if s2:
                    break
                j += 1
            if not found_brace:
                i += 1
                continue
        else:
            i += 1

        # Collect fields until the closing "}"
        block_fields: dict[str, str] = {}
        closed = False
        while i < len(lines):
            s = _strip(lines[i])
            if s == "}":
                end_line = i
                blocks.append(ConfigBlock(
                    block_type=block_type,
                    fields=block_fields,
                    file_path=path,
                    start_line=open_line,
                    end_line=end_line,
                    label=label,
                ))
                i += 1
                closed = True
                break
            km = _KEY_VAL_RE.match(s)
            if km:
                block_fields[km.group(1)] = km.group(2).strip()
            i += 1

        if not closed:
            # Unclosed block — include what we have with end_line = last line
            end_line = i - 1
            blocks.append(ConfigBlock(
                block_type=block_type,
                fields=block_fields,
                file_path=path,
                start_line=open_line,
                end_line=end_line,
                label=label,
            ))

    return blocks


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────

def update_block_field(
    path: Path,
    start_line: int,
    end_line: int,
    key: str,
    value: str,
) -> bool:
    """Set *key* = *value* inside the block spanning [start_line, end_line].

    If the key already exists it is updated in-place.  If it does not exist,
    a new line is inserted before the closing brace.
    Returns True on success.
    """
    lines = read_lines(path)
    for i in range(start_line, min(end_line, len(lines))):
        m = _KEY_VAL_RE.match(_strip(lines[i]))
        if m and m.group(1) == key:
            # Preserve leading whitespace from the original line
            indent = len(lines[i]) - len(lines[i].lstrip())
            return update_line(path, i, " " * indent + f"{key} = {value}")

    # Key not found — insert before the closing brace
    if 0 <= end_line < len(lines):
        return insert_lines(path, end_line, ["    " + f"{key} = {value}"])
    return False


def delete_block(path: Path, start_line: int, end_line: int) -> bool:
    """Delete all lines from *start_line* to *end_line* inclusive.

    Also removes the blank line immediately preceding the block (if any),
    to avoid leaving double blank lines.
    Returns True on success.
    """
    lines = read_lines(path)
    actual_start = start_line
    # Absorb a preceding blank line so the file stays clean
    if actual_start > 0 and not lines[actual_start - 1].strip():
        actual_start -= 1
    return delete_lines(path, actual_start, end_line)


def add_block(
    path: Path,
    block_type: str,
    fields: dict[str, str],
    label: str = "",
) -> bool:
    """Append a new block to *path*.

    Returns True on success.
    """
    if label:
        header = f"{block_type} = {label} {{"
    else:
        header = f"{block_type} {{"
    body_lines = [header]
    for k, v in fields.items():
        body_lines.append(f"    {k} = {v}")
    body_lines.append("}")
    return append_block(path, "\n".join(body_lines))
