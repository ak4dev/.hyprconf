"""hyprconf.keybinds — read and write Hyprland keybinds.

Keybinds live in keybinds.conf (sourced by hyprland.conf).

Format:
    bind[flags] = MODS, KEY, DISPATCHER, ARGS
    e.g. bind = $mainMod, T, exec, alacritty
         bindl = , XF86AudioPlay, exec, playerctl play-pause
         bindel = , XF86MonBrightnessUp, exec, brightnessctl set 5%+

Bind flags (may be combined): l (locked), r (release), e (repeat),
                               n (non-consuming), m (mouse), t (transparent).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

from .file_edit import (
    SOURCE_RE,
    append_block,
    read_lines,
    resolve_source_paths,
    strip_comment,
    update_line,
)
from .paths import KEYBINDS_FILE

# ─────────────────────────────────────────────────────────────────────────────
#  Data types
# ─────────────────────────────────────────────────────────────────────────────


class KeybindEntry(NamedTuple):
    kind: str  # bind / bindl / bindel / etc.
    mods: str  # e.g. "$mainMod SHIFT" or ""
    key: str  # e.g. "T" or "XF86AudioPlay"
    dispatcher: str  # e.g. "exec"
    args: str  # e.g. "alacritty"
    file_path: Path  # source file
    line_idx: int  # 0-based line index in file_path
    raw_line: str  # verbatim line (for display / round-trip)


# ─────────────────────────────────────────────────────────────────────────────
#  Parsing
# ─────────────────────────────────────────────────────────────────────────────

_BIND_RE = re.compile(r"^(bind[a-zA-Z]*)\s*=\s*(.+)$")
_VAR_RE = re.compile(r"^\$([A-Za-z0-9_]+)\s*=\s*(.+)$")


def _expand_vars(text: str, vars_: dict[str, str]) -> str:
    for name, val in vars_.items():
        text = text.replace(f"${name}", val)
    return text


def read_keybinds_with_location(
    path: Path | None = None,
    *,
    follow_sources: bool = False,
) -> list[KeybindEntry]:
    """Parse keybinds from *path*, returning entries with file+line location.

    When *follow_sources* is True, ``source =`` directives are recursively
    followed (useful for reading the full effective config).  By default only
    *path* itself is parsed (keybinds.conf is a flat file).

    Variable substitutions (``$mainMod``) are expanded in the returned data
    but the ``raw_line`` field always preserves the original text.
    """
    if path is None:
        path = KEYBINDS_FILE

    entries: list[KeybindEntry] = []
    seen: set[Path] = set()

    def _parse(p: Path, inherited_vars: dict[str, str]) -> None:
        if p in seen or not p.exists():
            return
        seen.add(p)
        local_vars: dict[str, str] = dict(inherited_vars)
        lines = read_lines(p)
        for idx, raw in enumerate(lines):
            stripped = strip_comment(raw)
            if not stripped:
                continue
            mv = _VAR_RE.match(stripped)
            if mv:
                local_vars[mv.group(1)] = mv.group(2).strip()
                continue
            if follow_sources:
                ms = SOURCE_RE.match(stripped)
                if ms:
                    for sp in resolve_source_paths(ms.group(1), p.parent):
                        _parse(sp, local_vars)
                    continue
            mb = _BIND_RE.match(stripped)
            if mb:
                kind = mb.group(1)
                parts = [s.strip() for s in mb.group(2).split(",")]
                while len(parts) < 4:
                    parts.append("")
                mods = _expand_vars(parts[0], local_vars)
                key = _expand_vars(parts[1], local_vars)
                disp = parts[2]
                args = _expand_vars(",".join(parts[3:]), local_vars)
                entries.append(
                    KeybindEntry(
                        kind=kind,
                        mods=mods,
                        key=key,
                        dispatcher=disp,
                        args=args.strip(),
                        file_path=p,
                        line_idx=idx,
                        raw_line=raw,
                    )
                )

    _parse(path, {})
    return entries


# ─────────────────────────────────────────────────────────────────────────────
#  Writers
# ─────────────────────────────────────────────────────────────────────────────


def _format_bind_line(kind: str, mods: str, key: str, dispatcher: str, args: str) -> str:
    """Produce a canonical ``bind = …`` line."""
    kind = kind.strip() or "bind"
    mods = mods.strip()
    key = key.strip()
    disp = dispatcher.strip()
    args = args.strip()
    # Align nicely: pad mods and key fields
    return f"{kind} = {mods}, {key}, {disp}, {args}"


def add_keybind(
    kind: str, mods: str, key: str, dispatcher: str, args: str, file: Path | None = None
) -> bool:
    """Append a new keybind to *file* (default: keybinds.conf).

    Returns True on success.
    """
    if file is None:
        file = KEYBINDS_FILE
    line = _format_bind_line(kind, mods, key, dispatcher, args)
    return append_block(file, line)


def update_keybind(
    file_path: Path, line_idx: int, kind: str, mods: str, key: str, dispatcher: str, args: str
) -> bool:
    """Replace the keybind at *line_idx* in *file_path*.

    Returns True on success.
    """
    line = _format_bind_line(kind, mods, key, dispatcher, args)
    return update_line(file_path, line_idx, line)
