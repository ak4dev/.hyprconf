"""hyprconf.hyprpaper — read and write hyprpaper configuration.

hyprpaper.conf supports two styles:

  Line-based:
      preload  = ~/wallpaper/image.jpg
      wallpaper = eDP-1,~/wallpaper/image.jpg
      splash   = false
      ipc      = true

  Block-based (used when fit_mode etc. are needed):
      wallpaper {
          monitor  = eDP-1
          path     = ~/wallpaper/image.jpg
          fit_mode = cover
      }

  Variable assignments are also common:
      $wallpaper = ~/wallpaper/gruvbox.jpg

This module reads/writes all three forms.  Block-based wallpapers are
represented as ConfigBlock objects via block_conf; line-based entries and
top-level key=value settings are handled directly.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .block_conf import ConfigBlock, read_blocks, update_block_field, delete_block, add_block
from .file_edit  import read_lines, update_line, delete_line, append_block, delete_lines

# ─────────────────────────────────────────────────────────────────────────────
#  Path
# ─────────────────────────────────────────────────────────────────────────────

_CFG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HYPRPAPER_FILE = _CFG / "hypr" / "hyprpaper.conf"

# ─────────────────────────────────────────────────────────────────────────────
#  Regexes
# ─────────────────────────────────────────────────────────────────────────────

_COMMENT_RE   = re.compile(r"(^|\s)#.*$")
_PRELOAD_RE   = re.compile(r"^preload\s*=\s*(.+)$",           re.IGNORECASE)
_WALLPAPER_RE = re.compile(r"^wallpaper\s*=\s*([^,]*),\s*(.+)$", re.IGNORECASE)
_SETTING_RE   = re.compile(r"^(splash|ipc)\s*=\s*(.+)$",     re.IGNORECASE)
_VAR_RE       = re.compile(r"^\$([A-Za-z0-9_]+)\s*=\s*(.+)$")


def _strip(line: str) -> str:
    return _COMMENT_RE.sub("", line).strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PreloadEntry:
    """A ``preload = /path`` line."""
    path:      str
    file_path: Path
    line_idx:  int


@dataclass
class WallpaperLine:
    """A ``wallpaper = monitor,path`` line (non-block format)."""
    monitor:   str
    path:      str
    file_path: Path
    line_idx:  int


@dataclass
class SettingEntry:
    """A top-level setting (splash, ipc) or variable definition."""
    key:       str
    value:     str
    file_path: Path
    line_idx:  int


# ─────────────────────────────────────────────────────────────────────────────
#  Readers
# ─────────────────────────────────────────────────────────────────────────────

def read_preloads(path: Optional[Path] = None) -> list[PreloadEntry]:
    """Return all ``preload =`` entries."""
    p    = path or HYPRPAPER_FILE
    out: list[PreloadEntry] = []
    for i, raw in enumerate(read_lines(p)):
        s = _strip(raw)
        m = _PRELOAD_RE.match(s)
        if m:
            out.append(PreloadEntry(path=m.group(1).strip(), file_path=p, line_idx=i))
    return out


def read_wallpaper_lines(path: Optional[Path] = None) -> list[WallpaperLine]:
    """Return all ``wallpaper = monitor,path`` (line-based) entries."""
    p   = path or HYPRPAPER_FILE
    out: list[WallpaperLine] = []
    for i, raw in enumerate(read_lines(p)):
        s = _strip(raw)
        m = _WALLPAPER_RE.match(s)
        if m:
            out.append(WallpaperLine(
                monitor=m.group(1).strip(),
                path=m.group(2).strip(),
                file_path=p,
                line_idx=i,
            ))
    return out


def read_wallpaper_blocks(path: Optional[Path] = None) -> list[ConfigBlock]:
    """Return all ``wallpaper { ... }`` block entries."""
    return [b for b in read_blocks(path or HYPRPAPER_FILE) if b.block_type == "wallpaper"]


def read_settings(path: Optional[Path] = None) -> list[SettingEntry]:
    """Return top-level splash/ipc settings and variable definitions."""
    p   = path or HYPRPAPER_FILE
    out: list[SettingEntry] = []
    for i, raw in enumerate(read_lines(p)):
        s = _strip(raw)
        ms = _SETTING_RE.match(s)
        if ms:
            out.append(SettingEntry(key=ms.group(1), value=ms.group(2).strip(),
                                    file_path=p, line_idx=i))
            continue
        mv = _VAR_RE.match(s)
        if mv:
            out.append(SettingEntry(key=f"${mv.group(1)}", value=mv.group(2).strip(),
                                    file_path=p, line_idx=i))
    return out


def read_all(path: Optional[Path] = None) -> dict:
    """Return a combined view of hyprpaper.conf contents.

    Keys:
        preloads        — list[PreloadEntry]
        wallpaper_lines — list[WallpaperLine]
        wallpaper_blocks— list[ConfigBlock]
        settings        — list[SettingEntry]
    """
    p = path or HYPRPAPER_FILE
    return {
        "preloads":         read_preloads(p),
        "wallpaper_lines":  read_wallpaper_lines(p),
        "wallpaper_blocks": read_wallpaper_blocks(p),
        "settings":         read_settings(p),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Writers — preload
# ─────────────────────────────────────────────────────────────────────────────

def add_preload(wp_path: str, file: Optional[Path] = None) -> bool:
    """Append a ``preload = /path`` line.  Returns True on success."""
    return append_block(file or HYPRPAPER_FILE, f"preload = {wp_path}")


def delete_preload(file_path: Path, line_idx: int) -> bool:
    """Delete the preload line at *line_idx*."""
    return delete_line(file_path, line_idx)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers — wallpaper lines
# ─────────────────────────────────────────────────────────────────────────────

def set_wallpaper_line(
    monitor: str,
    wp_path: str,
    file: Optional[Path] = None,
) -> bool:
    """Set or create a ``wallpaper = monitor,path`` line.

    If an entry for *monitor* already exists it is updated in-place;
    otherwise a new line is appended.  Returns True on success.
    """
    f = file or HYPRPAPER_FILE
    for entry in read_wallpaper_lines(f):
        if entry.monitor == monitor:
            return update_line(f, entry.line_idx, f"wallpaper = {monitor},{wp_path}")
    return append_block(f, f"wallpaper = {monitor},{wp_path}")


def delete_wallpaper_line(file_path: Path, line_idx: int) -> bool:
    """Delete the wallpaper line at *line_idx*."""
    return delete_line(file_path, line_idx)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers — wallpaper blocks
# ─────────────────────────────────────────────────────────────────────────────

def add_wallpaper_block(
    monitor: str,
    wp_path: str,
    fit_mode: str = "cover",
    file: Optional[Path] = None,
) -> bool:
    """Append a ``wallpaper { ... }`` block.  Returns True on success."""
    fields: dict[str, str] = {"monitor": monitor, "path": wp_path}
    if fit_mode:
        fields["fit_mode"] = fit_mode
    return add_block(file or HYPRPAPER_FILE, "wallpaper", fields)


def update_wallpaper_block_field(
    path: Path,
    start_line: int,
    end_line: int,
    key: str,
    value: str,
) -> bool:
    """Update a field within a wallpaper block."""
    return update_block_field(path, start_line, end_line, key, value)


def delete_wallpaper_block(path: Path, start_line: int, end_line: int) -> bool:
    """Delete the wallpaper block spanning [start_line, end_line]."""
    return delete_block(path, start_line, end_line)


# ─────────────────────────────────────────────────────────────────────────────
#  Writers — settings
# ─────────────────────────────────────────────────────────────────────────────

def set_setting(key: str, value: str, file: Optional[Path] = None) -> bool:
    """Set a top-level setting (splash, ipc) or variable.

    Updates in-place if the setting exists, otherwise appends.
    Returns True on success.
    """
    f = file or HYPRPAPER_FILE
    for entry in read_settings(f):
        if entry.key.lower() == key.lower():
            if key.startswith("$"):
                line = f"{key} = {value}"
            else:
                line = f"{key} = {value}"
            return update_line(f, entry.line_idx, line)
    return append_block(f, f"{key} = {value}")
