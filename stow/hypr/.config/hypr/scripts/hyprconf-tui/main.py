#!/usr/bin/env python3
# hyprconf-tui — Hyprland configuration TUI
# Part of hyprconf: https://github.com/ak4dev/.hyprconf
from __future__ import annotations

import argparse
import glob as _glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── Shared hyprconf library ────────────────────────────────────────────────
sys.path.insert(0, str(Path.home() / ".local" / "lib"))
from hyprconf.schema import (    # noqa: E402
    OPTION_SCHEMA,
    SECTION_ORDER,
    SECTION_LABELS,
)
from hyprconf.config import (    # noqa: E402
    OVERRIDES_FILE as _OVERRIDES_FILE,
    MANAGED_MARKER as _MANAGED_MARKER,
    read_persisted as _lib_read_persisted,
    save_pending   as _lib_save_pending,
)
from hyprconf.hyprctl import (   # noqa: E402
    get_option  as _lib_hyprctl_get,
    set_option  as _lib_hyprctl_apply,
    is_active   as _lib_hyprland_active,
    get_monitors as _lib_get_monitors,
)
from hyprconf.keybinds import (  # noqa: E402
    read_keybinds_with_location  as _lib_keybinds_with_loc,
    add_keybind                  as _lib_add_keybind,
    delete_keybind               as _lib_delete_keybind,
    update_keybind               as _lib_update_keybind,
)
from hyprconf.rules import (     # noqa: E402
    read_window_rules_with_location    as _lib_win_rules,
    read_workspace_rules_with_location as _lib_wksp_rules,
    add_window_rule                    as _lib_add_win_rule,
    add_workspace_rule                 as _lib_add_wksp_rule,
    delete_rule                        as _lib_delete_rule,
    update_window_rule                 as _lib_update_win_rule,
    update_workspace_rule              as _lib_update_wksp_rule,
)
from hyprconf.monitors import (  # noqa: E402
    read_monitor_configs as _lib_monitor_configs,
    upsert_monitor       as _lib_upsert_monitor,
    delete_monitor       as _lib_delete_monitor,
    MONITORS_FILE,
)
from hyprconf.hyprlock import (  # noqa: E402
    read_hyprlock_blocks   as _lib_lock_blocks,
    add_hyprlock_block     as _lib_add_lock_block,
    delete_hyprlock_block  as _lib_delete_lock_block,
    update_hyprlock_field  as _lib_update_lock_field,
    BLOCK_TYPES            as _LOCK_BLOCK_TYPES,
)
from hyprconf.hypridle import (  # noqa: E402
    read_hypridle_blocks   as _lib_idle_blocks,
    add_hypridle_block     as _lib_add_idle_block,
    delete_hypridle_block  as _lib_delete_idle_block,
    update_hypridle_field  as _lib_update_idle_field,
    BLOCK_TYPES            as _IDLE_BLOCK_TYPES,
)
from hyprconf.hyprpaper import (  # noqa: E402
    read_all               as _lib_paper_read_all,
    read_wallpaper_blocks  as _lib_paper_wp_blocks,
    read_wallpaper_lines   as _lib_paper_wp_lines,
    read_preloads          as _lib_paper_preloads,
    read_settings          as _lib_paper_settings,
    add_preload            as _lib_add_preload,
    add_wallpaper_block    as _lib_add_wp_block,
    delete_preload         as _lib_delete_preload,
    delete_wallpaper_line  as _lib_delete_wp_line,
    delete_wallpaper_block as _lib_delete_wp_block,
    update_wallpaper_block_field as _lib_update_wp_field,
    set_setting            as _lib_paper_set_setting,
    set_wallpaper_line     as _lib_set_wp_line,
)
from hyprconf.block_conf import (  # noqa: E402
    update_block_field as _lib_update_block_field,
    delete_block       as _lib_delete_block,
)
from hyprconf.file_edit import ( # noqa: E402
    update_line  as _lib_update_line,
    delete_line  as _lib_delete_line,
    append_block as _lib_append_block,
    read_lines   as _lib_read_lines,
)

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.message import Message
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

# ──────────────────────────────────────────────────────────────────────────────
#  Paths
# ──────────────────────────────────────────────────────────────────────────────

CFG_HOME         = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
HYPR_DIR         = CFG_HOME / "hypr"
OVERRIDES_FILE   = _OVERRIDES_FILE
THEME_DIR        = HYPR_DIR / "scripts" / "theme-switcher" / "themes"
CURRENT_THEME_F  = HYPR_DIR / ".current-theme"
THEME_SCRIPT     = HYPR_DIR / "scripts" / "theme-switcher" / "switch_theme.py"
KEYBINDS_CONF    = HYPR_DIR / "keybinds.conf"
HYPRLAND_CONF    = HYPR_DIR / "hyprland.conf"
HYPRLOCK_CONF    = HYPR_DIR / "hyprlock.conf"
HYPRIDLE_CONF    = HYPR_DIR / "hypridle.conf"
HYPRPAPER_CONF   = HYPR_DIR / "hyprpaper.conf"
WALLPAPER_DIR    = Path.home() / "wallpaper"
MANAGED_MARKER   = _MANAGED_MARKER

# Sections handled by file editing (not hyprctl keyword)
FILE_SECTIONS = {"keybinds", "window_rules", "workspace_rules",
                 "hyprlock", "hypridle", "hyprpaper", "monitors"}

# ──────────────────────────────────────────────────────────────────────────────
#  Theme colors (loaded once at startup, baked into CSS)
# ──────────────────────────────────────────────────────────────────────────────

def _load_theme_colors() -> dict[str, str]:
    defaults = {
        "background": "#1e1e2e",
        "foreground": "#cdd6f4",
        "accent":     "#89b4fa",
        "comment":    "#585b70",
        "name":       "default",
    }
    try:
        name = CURRENT_THEME_F.read_text().strip()
        data = json.loads((THEME_DIR / f"{name}.json").read_text())
        return {
            "background": data.get("background", defaults["background"]),
            "foreground": data.get("foreground", defaults["foreground"]),
            "accent":     data.get("accent",     defaults["accent"]),
            "comment":    data.get("comment",     defaults["comment"]),
            "name":       name,
        }
    except Exception:
        return defaults


def _dim(hex_color: str, factor: float = 0.7) -> str:
    """Return a slightly darkened version of a #rrggbb hex color."""
    try:
        c = hex_color.lstrip("#")
        if len(c) == 6:
            r = max(0, int(int(c[0:2], 16) * factor))
            g = max(0, int(int(c[2:4], 16) * factor))
            b = max(0, int(int(c[4:6], 16) * factor))
            return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        pass
    return hex_color


_TC   = _load_theme_colors()
_BG   = _TC["background"]
_FG   = _TC["foreground"]
_ACC  = _TC["accent"]
_CMT  = _TC["comment"]
_BG2  = _dim(_BG, 0.80)   # sidebar / header background
_BG3  = _dim(_BG, 0.88)   # table alternate row

# ──────────────────────────────────────────────────────────────────────────────
#  App CSS  (theme colors baked in at import time)
# ──────────────────────────────────────────────────────────────────────────────

APP_CSS = f"""
Screen {{
    background: {_BG};
    color: {_FG};
    layout: vertical;
}}

/* ── Header bar ─────────────────────────────────────────────── */
#brand-bar {{
    height: 1;
    layout: horizontal;
    background: {_BG2};
    padding: 0 2;
}}
#brand-left {{
    color: {_FG};
    text-style: bold;
    width: auto;
    padding-right: 1;
}}
#brand-status {{
    color: {_CMT};
    width: 1fr;
}}
#brand-right {{
    color: {_CMT};
    width: auto;
    text-align: right;
}}

/* ── Main layout ────────────────────────────────────────────── */
#main-pane {{
    height: 1fr;
    layout: horizontal;
}}

/* ── Sidebar ────────────────────────────────────────────────── */
#sidebar {{
    width: 22;
    border-right: solid {_CMT};
    height: 1fr;
    layout: vertical;
}}
#filter-input {{
    height: 1;
    border: none;
    background: {_BG};
    color: {_CMT};
    padding: 0 1;
    margin: 0;
}}
#filter-input:focus {{
    border: none;
    color: {_FG};
    background: {_BG};
}}
#sidebar-sep {{
    height: 1;
    color: {_CMT};
    background: {_BG2};
    padding: 0 1;
    content-align: left middle;
}}
#section-list {{
    background: {_BG2};
    border: none;
    padding: 0;
    height: 1fr;
    overflow-y: auto;
    overflow-x: hidden;
}}
ListView > ListItem {{
    padding: 0 1;
    background: {_BG2};
    color: {_FG};
    height: 1;
}}
ListView > ListItem.--highlight {{
    background: {_BG};
    color: {_ACC};
}}
ListView > ListItem.active-section > Label {{
    color: {_ACC};
    text-style: bold;
}}
ListView > ListItem.sep-item {{
    color: {_CMT};
    height: 1;
}}

/* ── Content pane ───────────────────────────────────────────── */
#content {{
    width: 1fr;
    height: 1fr;
    layout: vertical;
}}
#section-title {{
    height: 1;
    background: {_BG2};
    padding: 0 2;
    text-style: bold;
    color: {_ACC};
}}
#content-body {{
    height: 1fr;
}}
DataTable {{
    background: {_BG};
    color: {_FG};
    border: none;
    height: 1fr;
}}
DataTable > .datatable--header {{
    background: {_BG2};
    color: {_ACC};
    text-style: bold;
}}
DataTable > .datatable--cursor {{
    background: {_ACC};
    color: {_BG};
}}
DataTable > .datatable--even-row {{
    background: {_BG};
}}
DataTable > .datatable--odd-row {{
    background: {_BG3};
}}

/* ── Pending indicator ─────────────────────────────────────── */
#pending-bar {{
    height: 1;
    background: {_dim(_ACC, 0.3)};
    color: {_FG};
    padding: 0 2;
    display: none;
}}
#pending-bar.visible {{
    display: block;
}}

/* ── Edit modal ─────────────────────────────────────────────── */
EditScreen {{
    align: center middle;
    background: rgba(0, 0, 0, 0.7);
}}
#edit-dialog {{
    width: 64;
    height: auto;
    border: round {_ACC};
    padding: 1 2;
    background: {_BG2};
}}
#edit-title {{
    text-style: bold;
    color: {_ACC};
    margin-bottom: 0;
    height: 1;
}}
#edit-meta {{
    color: {_CMT};
    margin-bottom: 1;
}}
#edit-input {{
    background: {_BG};
    color: {_FG};
    border: tall {_CMT};
    height: 3;
    margin-bottom: 0;
}}
#edit-input:focus {{
    border: tall {_ACC};
}}
#edit-hint {{
    color: {_CMT};
    margin-top: 1;
    height: 1;
}}

/* ── Monitor edit modal ─────────────────────────────────────────── */
.mon-field-label {{
    color: {_FG};
    margin-top: 1;
    height: 1;
}}
.mon-field-hint {{
    color: {_CMT};
    height: 1;
}}
.mon-input {{
    background: {_BG};
    color: {_FG};
    border: tall {_CMT};
    margin-bottom: 0;
}}
.mon-input:focus {{
    border: tall {_ACC};
}}

/* ── Option-select modal ────────────────────────────────────── */
OptionSelectScreen {{
    align: center middle;
    background: rgba(0, 0, 0, 0.7);
}}
#select-dialog {{
    width: 56;
    height: auto;
    max-height: 24;
    border: round {_ACC};
    padding: 1 2;
    background: {_BG2};
}}
#select-dialog #option-list {{
    background: {_BG2};
    border: none;
    padding: 0;
    height: auto;
    max-height: 16;
    overflow-y: auto;
}}

/* ── Numeric slider modal ───────────────────────────────────── */
NumericEditScreen {{
    align: center middle;
    background: rgba(0, 0, 0, 0.7);
}}
#slider-dialog {{
    width: 68;
    height: auto;
    border: round {_ACC};
    padding: 1 2;
    background: {_BG2};
}}
SliderBar {{
    height: 3;
    color: {_FG};
    background: {_BG2};
    padding: 0 1;
    margin-bottom: 0;
}}
SliderBar:focus {{
    color: {_ACC};
}}
#slider-input {{
    background: {_BG};
    color: {_FG};
    border: tall {_CMT};
    height: 3;
    margin-top: 1;
}}
#slider-input:focus {{
    border: tall {_ACC};
}}

/* ── Monitor edit modal ─────────────────────────────────────── */
#monitor-dialog {{
    width: 72;
    height: auto;
    max-height: 85vh;
    border: round {_ACC};
    padding: 1 2;
    background: {_BG2};
    overflow-y: auto;
}}
.mon-section-header {{
    color: {_ACC};
    padding: 1 0 0 0;
    text-style: bold;
}}
"""

# ──────────────────────────────────────────────────────────────────────────────
#  Runtime helpers
# ──────────────────────────────────────────────────────────────────────────────

HYPRLAND_ACTIVE = bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))


def _run(args: list[str], timeout: float = 3.0) -> Optional[str]:
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def hyprctl_get(section: str, key: str) -> Optional[str]:
    return _lib_hyprctl_get(section, key)


def hyprctl_apply(section: str, key: str, value: str) -> bool:
    return _lib_hyprctl_apply(section, key, value)


def read_persisted(section: str, key: str) -> Optional[str]:
    return _lib_read_persisted(section, key)


def get_current_value(section: str, key: str, default: str,
                      pending: dict[str, dict[str, str]]) -> tuple[str, str]:
    """Return (value, source) where source in: pending | live | persisted | default."""
    if section in pending and key in pending[section]:
        return pending[section][key], "pending"
    if HYPRLAND_ACTIVE:
        live = hyprctl_get(section, key)
        if live is not None:
            return live, "live"
    persisted = read_persisted(section, key)
    if persisted is not None:
        return persisted, "persisted"
    return default, "default"


def save_pending(pending: dict[str, dict[str, str]]) -> tuple[bool, int]:
    """Write pending changes to the overrides file (delegates to shared lib)."""
    return _lib_save_pending(pending)


# ──────────────────────────────────────────────────────────────────────────────
#  Data helpers for read-only sections
# ──────────────────────────────────────────────────────────────────────────────

def get_monitors() -> list[dict]:
    if not HYPRLAND_ACTIVE:
        return []
    raw = _run(["hyprctl", "monitors", "-j"])
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def list_themes() -> list[str]:
    if not THEME_DIR.exists():
        return []
    return sorted(p.stem for p in THEME_DIR.glob("*.json"))


def current_theme_name() -> str:
    try:
        return CURRENT_THEME_F.read_text().strip()
    except Exception:
        return ""


def parse_keybinds() -> list[tuple[str, ...]]:
    """Return (kind, mods, key, dispatcher, args) tuples — no location data."""
    entries = _lib_keybinds_with_loc(KEYBINDS_CONF)
    return [(e.kind, e.mods or "—", e.key, e.dispatcher, e.args)
            for e in entries]


def _collect_rules(pattern: re.Pattern) -> list[str]:
    """Collect rule text lines matching pattern — kept for display compat."""
    if re.search(r'workspace', pattern.pattern, re.I):
        return [e.rule for e in _lib_wksp_rules(HYPRLAND_CONF)]
    return [e.rule for e in _lib_win_rules(HYPRLAND_CONF)]


def _read_file_lines(path: Path) -> list[str]:
    try:
        return path.read_text().splitlines()
    except OSError:
        return [f"(cannot read {path})"]


def _get_wallpapers() -> list[Path]:
    if not WALLPAPER_DIR.exists():
        return []
    exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
    return sorted(p for p in WALLPAPER_DIR.iterdir() if p.suffix.lower() in exts)


# ──────────────────────────────────────────────────────────────────────────────
#  Numeric range + enum label helpers  (used by modal screens)
# ──────────────────────────────────────────────────────────────────────────────

def _parse_numeric_range(
    description: str, type_: str
) -> tuple[float, float, float, float]:
    """Return (min_val, max_val, step, fine_step) parsed from a schema description."""
    # Match [X-Y] (handles negative lows like [-1.0-1.0]) or [X to Y]
    m = re.search(r'\[(-?\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\]', description)
    if not m:
        m = re.search(r'\[(-?\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\]',
                      description, re.IGNORECASE)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
    elif type_ == "float":
        lo, hi = 0.0, 1.0
    elif any(k in description.lower() for k in ("ms", "delay", "timeout")):
        lo, hi = 0.0, 2000.0
    elif any(k in description.lower() for k in ("fps", "hz", "rate")):
        lo, hi = 1.0, 240.0
    elif "px" in description.lower():
        lo, hi = 0.0, 100.0
    else:
        lo, hi = 0.0, 100.0

    span = max(hi - lo, 0.001)
    if type_ == "float":
        step      = max(0.01, round(span / 20, 4))
        fine_step = max(0.01, round(span / 100, 4))
        if fine_step >= step:
            fine_step = round(step / 5, 4)
    else:
        step      = max(1, int(round(span / 20)))
        fine_step = max(1, int(round(span / 100)))
        if fine_step >= step:
            fine_step = max(1, step // 5)

    return lo, hi, float(step), float(fine_step)


def _enrich_enum_labels(
    description: str, choices: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Attach inline N=label annotations from the schema description, if present."""
    annotated: dict[str, str] = {}
    for m in re.finditer(r'(\w+)=([^,\]\s][^,\]]*?)(?=[,\]\s]|$)', description):
        annotated[m.group(1).strip()] = m.group(2).strip()
    if not annotated:
        return choices
    return [
        (v, f"{v} — {annotated[v]}" if v in annotated else v)
        for v, _ in choices
    ]


def _parse_monitor_extras(extras: str) -> dict[str, str]:
    """Parse 'vrr, 2, bitdepth, 10, cm, hdr' → {'vrr': '2', 'bitdepth': '10', 'cm': 'hdr'}."""
    tokens = [t.strip() for t in extras.split(",") if t.strip()]
    result: dict[str, str] = {}
    i = 0
    while i + 1 < len(tokens):
        result[tokens[i].lower()] = tokens[i + 1]
        i += 2
    return result


# Matches an absolute monitor position like "1920x0" or "-100x200".
_ABS_POS_RE = re.compile(r'^(-?\d+)[xX](-?\d+)$')


def _compute_logical_size(
    phys_w: int, phys_h: int, scale: float, transform: int,
) -> tuple[float, float]:
    """Return (logical_width, logical_height) after applying scale and transform.

    Transforms 1/3/5/7 (90° / 270° rotations) swap the physical axes before
    dividing by scale, matching how Hyprland measures position offsets.
    """
    if transform in (1, 3, 5, 7):
        phys_w, phys_h = phys_h, phys_w
    return phys_w / scale, phys_h / scale


def _adjust_adjacent_monitor_positions(
    edited_name:   str,
    snapshot:      list[dict],  # ALL monitor dicts from hyprctl, captured BEFORE the edit
    old_lw:        float,       # old logical width  of the edited monitor
    old_lh:        float,       # old logical height of the edited monitor
    new_lw:        float,       # new logical width
    new_lh:        float,       # new logical height
) -> None:
    """Shift absolute-positioned monitors adjacent to the edited one to prevent overlaps.

    When the edited monitor's logical size grows (scale decreases, or a larger
    resolution is chosen), monitors that were sitting to its right or below can
    overlap the new extent.  This function shifts every such monitor — including
    chains — by the same delta so their relative layout is preserved.

    Monitors using auto / auto-right / etc. are intentionally skipped: Hyprland
    will recompute their positions automatically.  Only monitors with explicit
    numeric positions in monitors.conf need manual adjustment.
    """
    delta_w = new_lw - old_lw
    delta_h = new_lh - old_lh
    if abs(delta_w) < 0.5 and abs(delta_h) < 0.5:
        return

    edited = next((m for m in snapshot if m.get("name") == edited_name), None)
    if not edited:
        return

    old_x      = float(edited.get("x", 0))
    old_y      = float(edited.get("y", 0))
    old_right  = old_x + old_lw
    old_bottom = old_y + old_lh

    file_configs = _lib_monitor_configs()

    for mon in snapshot:
        mname = mon.get("name", "")
        if mname == edited_name:
            continue

        mx      = float(mon.get("x", 0))
        my      = float(mon.get("y", 0))
        m_w     = int(mon.get("width",  1920))
        m_h     = int(mon.get("height", 1080))
        m_tr    = int(mon.get("transform", 0) or 0)
        m_scale = float(mon.get("scale", 1.0) or 1.0)
        m_lw, m_lh = _compute_logical_size(m_w, m_h, m_scale, m_tr)

        file_mc = next((fc for fc in file_configs if fc.name == mname), None)
        if not file_mc:
            continue
        if file_mc.position.lower().startswith("auto"):
            continue  # Hyprland handles auto positions automatically

        pos_m = _ABS_POS_RE.match(file_mc.position.strip())
        if not pos_m:
            continue
        file_x = int(pos_m.group(1))
        file_y = int(pos_m.group(2))

        # ── Horizontal: shift monitors to the right of the edited monitor ──────
        # Use delta_w > 0 only (monitor grew) since shrinking just creates a gap.
        # All monitors in the affected column (mx >= old right edge, y-band
        # overlaps edited) receive the same delta, which correctly handles chains.
        if delta_w > 0.5 and mx >= old_right - 1:
            # Y-band overlap: mon's vertical range must intersect edited's range
            if not (my + m_lh <= old_y or my >= old_bottom):
                new_file_x = file_x + int(round(delta_w))
                new_pos = f"{new_file_x}x{file_y}"
                extras_str = file_mc.extras.strip()
                _lib_upsert_monitor(mname, file_mc.resolution, new_pos, file_mc.scale, extras_str)
                _run(["hyprctl", "keyword", "monitor",
                      f"{mname},{file_mc.resolution},{new_pos},{file_mc.scale}"
                      + (f",{extras_str}" if extras_str else "")])
                continue

        # ── Vertical: shift monitors below the edited monitor ─────────────────
        if delta_h > 0.5 and my >= old_bottom - 1:
            # X-band overlap: mon's horizontal range must intersect edited's range
            if not (mx + m_lw <= old_x or mx >= old_x + old_lw):
                new_file_y = file_y + int(round(delta_h))
                new_pos = f"{file_x}x{new_file_y}"
                extras_str = file_mc.extras.strip()
                _lib_upsert_monitor(mname, file_mc.resolution, new_pos, file_mc.scale, extras_str)
                _run(["hyprctl", "keyword", "monitor",
                      f"{mname},{file_mc.resolution},{new_pos},{file_mc.scale}"
                      + (f",{extras_str}" if extras_str else "")])


# ──────────────────────────────────────────────────────────────────────────────
#  Keybind edit / new screen
# ──────────────────────────────────────────────────────────────────────────────

class KeybindEditScreen(ModalScreen):
    """Add or edit a keybind."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    _FIELDS  = ("kb-kind", "kb-mods", "kb-key", "kb-disp", "kb-args")

    def __init__(self, kind: str = "bind", mods: str = "", key: str = "",
                 dispatcher: str = "", args: str = "") -> None:
        super().__init__()
        self._kind = kind
        self._mods = mods
        self._key  = key
        self._disp = dispatcher
        self._args = args

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label("   Keybind", id="edit-title")
            yield Label("  Bind type: bind  bindl  bindr  binde  bindm  bindel  etc.",
                        id="edit-meta")
            yield Label("  Mods: SUPER  SUPER SHIFT  ALT  CTRL  (empty = no modifier)",
                        classes="mon-field-hint")
            yield Label("  Bind type", classes="mon-field-label")
            yield Input(value=self._kind, id="kb-kind",  classes="mon-input",
                        select_on_focus=True)
            yield Label("  Modifiers  (e.g. $mainMod SHIFT)", classes="mon-field-label")
            yield Input(value=self._mods, id="kb-mods",  classes="mon-input",
                        select_on_focus=True)
            yield Label("  Key  (e.g. T, F1, XF86AudioPlay)", classes="mon-field-label")
            yield Input(value=self._key,  id="kb-key",   classes="mon-input",
                        select_on_focus=True)
            yield Label("  Dispatcher  (e.g. exec, togglefloating, workspace)",
                        classes="mon-field-label")
            yield Input(value=self._disp, id="kb-disp",  classes="mon-input",
                        select_on_focus=True)
            yield Label("  Arguments  (e.g. alacritty, 2, ...)",
                        classes="mon-field-label")
            yield Input(value=self._args, id="kb-args",  classes="mon-input",
                        select_on_focus=True)
            yield Label("  [Enter] next / apply on last   [Esc] cancel",
                        id="edit-hint")

    def on_mount(self) -> None:
        self.query_one("#kb-kind", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # kb-kind gets an arrow-selectable list instead of free text
        if event.input.id == "kb-kind":
            kind_opts = [
                ("bind",    "bind — standard keybind"),
                ("bindl",   "bindl — fires while locked"),
                ("bindr",   "bindr — fires on key release"),
                ("binde",   "binde — repeats while held"),
                ("bindm",   "bindm — mouse binding"),
                ("bindel",  "bindel — locked + on release"),
                ("bindrel", "bindrel — release binding"),
            ]
            current_kind = self.query_one("#kb-kind", Input).value.strip() or "bind"
            def _set_kind(val: Optional[str]) -> None:
                if val:
                    self.query_one("#kb-kind", Input).value = val
                self.query_one("#kb-mods", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("Bind type", kind_opts, current_kind),
                _set_kind,
            )
            return

        fields = list(self._FIELDS)
        idx = fields.index(event.input.id) if event.input.id in fields else -1
        if 0 <= idx < len(fields) - 1:
            self.query_one(f"#{fields[idx + 1]}", Input).focus()
        else:
            kind = self.query_one("#kb-kind", Input).value.strip() or "bind"
            mods = self.query_one("#kb-mods", Input).value.strip()
            key  = self.query_one("#kb-key",  Input).value.strip()
            disp = self.query_one("#kb-disp", Input).value.strip()
            args = self.query_one("#kb-args", Input).value.strip()
            if not key or not disp:
                self.notify("Key and Dispatcher are required.", severity="warning")
                return
            self.dismiss((kind, mods, key, disp, args))

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Rule edit / new screen
# ──────────────────────────────────────────────────────────────────────────────

class RuleEditScreen(ModalScreen):
    """Add or edit a window rule or workspace rule."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    _FIELDS_WIN  = ("rule-action", "rule-filter1", "rule-filter2")
    _FIELDS_WKSP = ("wksp-id", "wksp-opts")

    def __init__(self, rule_type: str = "window",
                 action: str = "", filter1: str = "",
                 filter2: str = "", wksp_id: str = "",
                 wksp_opts: str = "") -> None:
        super().__init__()
        self._rule_type = rule_type
        self._action    = action
        self._filter1   = filter1
        self._filter2   = filter2
        self._wksp_id   = wksp_id
        self._wksp_opts = wksp_opts

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            if self._rule_type == "window":
                yield Label("   Window Rule", id="edit-title")
                yield Label("  Rule actions: float  tile  fullscreen  pin  opacity F  size W H",
                            id="edit-meta")
                yield Label("  Filters: class:REGEX  title:REGEX  xwayland:0|1  floating:0|1",
                            classes="mon-field-hint")
                yield Label("  Action  (e.g. float, opacity 0.9, size 800 600)",
                            classes="mon-field-label")
                yield Input(value=self._action,  id="rule-action",  classes="mon-input",
                            select_on_focus=True)
                yield Label("  Filter 1  (e.g. class:Alacritty)",
                            classes="mon-field-label")
                yield Input(value=self._filter1, id="rule-filter1", classes="mon-input",
                            select_on_focus=True)
                yield Label("  Filter 2  (optional, e.g. title:.*)",
                            classes="mon-field-label")
                yield Input(value=self._filter2, id="rule-filter2", classes="mon-input",
                            select_on_focus=True)
                yield Label("  [Enter] next / apply on last   [Esc] cancel",
                            id="edit-hint")
            else:
                yield Label("   Workspace Rule", id="edit-title")
                yield Label("  Workspace ID: 1-10, special:NAME",
                            id="edit-meta")
                yield Label("  Options: monitor:NAME  default:true  persistent:true  on-created-empty:EXEC",
                            classes="mon-field-hint")
                yield Label("  Workspace ID  (e.g. 1, special:magic)",
                            classes="mon-field-label")
                yield Input(value=self._wksp_id,   id="wksp-id",   classes="mon-input",
                            select_on_focus=True)
                yield Label("  Options  (e.g. monitor:HDMI-A-1, default:true)",
                            classes="mon-field-label")
                yield Input(value=self._wksp_opts, id="wksp-opts", classes="mon-input",
                            select_on_focus=True)
                yield Label("  [Enter] next / apply on last   [Esc] cancel",
                            id="edit-hint")

    def on_mount(self) -> None:
        first_id = "rule-action" if self._rule_type == "window" else "wksp-id"
        self.query_one(f"#{first_id}", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        fields = self._FIELDS_WIN if self._rule_type == "window" else self._FIELDS_WKSP
        idx = fields.index(event.input.id) if event.input.id in fields else -1
        if 0 <= idx < len(fields) - 1:
            self.query_one(f"#{fields[idx + 1]}", Input).focus()
        else:
            self._submit()

    def _submit(self) -> None:
        if self._rule_type == "window":
            action  = self.query_one("#rule-action",  Input).value.strip()
            filter1 = self.query_one("#rule-filter1", Input).value.strip()
            filter2 = self.query_one("#rule-filter2", Input).value.strip()
            if not action:
                self.notify("Action is required.", severity="warning")
                return
            filters = [f for f in [filter1, filter2] if f]
            self.dismiss(("window", action, filters))
        else:
            wksp_id   = self.query_one("#wksp-id",   Input).value.strip()
            wksp_opts = self.query_one("#wksp-opts",  Input).value.strip()
            if not wksp_id:
                self.notify("Workspace ID is required.", severity="warning")
                return
            self.dismiss(("workspace", wksp_id, wksp_opts))

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Text line edit screen  (hyprlock / hypridle / hyprpaper lines)
# ──────────────────────────────────────────────────────────────────────────────

class TextLineEditScreen(ModalScreen):
    """Edit a single line in a config file."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, file_path: Path, line_idx: int, line_text: str,
                 prompt: str = "") -> None:
        super().__init__()
        self._file_path = file_path
        self._line_idx  = line_idx
        self._line_text = line_text
        self._prompt    = prompt

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label(
                f"   {self._file_path.name}  line {self._line_idx + 1}",
                id="edit-title",
            )
            if self._prompt:
                yield Label(f"  {self._prompt}", id="edit-meta")
            else:
                yield Label("  Edit the line below and press Enter to save.",
                            id="edit-meta")
            yield Label("  Delete all text and press Enter to remove the line.",
                        classes="mon-field-hint")
            yield Input(value=self._line_text, id="edit-input", select_on_focus=False)
            yield Label("  [Enter] save   [Esc] cancel", id="edit-hint")

    def on_mount(self) -> None:
        inp = self.query_one("#edit-input", Input)
        inp.focus()
        inp.action_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Modal edit screen
# ──────────────────────────────────────────────────────────────────────────────

class EditScreen(ModalScreen):

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        section: str,
        key: str,
        current: str,
        type_: str,
        default: str,
        description: str,
    ) -> None:
        super().__init__()
        self._section     = section
        self._key         = key
        self._current     = current
        self._type        = type_
        self._default     = default
        self._description = description

    def compose(self) -> ComposeResult:
        type_label = self._type.split(":")[0]
        choices_line = ""
        if self._type.startswith("enum:"):
            choices_line = "\n  choices: " + "  |  ".join(self._type[5:].split(","))
        with Container(id="edit-dialog"):
            yield Label(f"  {self._section}:{self._key}", id="edit-title")
            yield Label(
                f"  type: {type_label}   default: {self._default}\n"
                f"  {self._description}"
                + choices_line,
                id="edit-meta",
            )
            yield Input(value=self._current, id="edit-input", select_on_focus=False)
            yield Label("  [Enter] apply   [Esc] cancel", id="edit-hint")

    def on_mount(self) -> None:
        inp = self.query_one("#edit-input", Input)
        inp.focus()
        inp.action_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Monitor edit screen
# ──────────────────────────────────────────────────────────────────────────────

class MonitorEditScreen(ModalScreen):
    """Edit a single monitor's configuration."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    _FIELDS = (
        "mon-res", "mon-scale", "mon-pos", "mon-vrr",
        "mon-bitdepth", "mon-cm", "mon-sdrbrightness", "mon-sdrsaturation",
        "mon-transform", "mon-mirror",
    )

    def __init__(self, monitor: dict, extras: str = "", file_position: str = "") -> None:
        super().__init__()
        self._monitor = monitor
        self._name    = monitor.get("name", "")
        w             = monitor.get("width",  1920)
        h             = monitor.get("height", 1080)
        hz            = monitor.get("refreshRate", 60.0)
        self._res     = f"{w}x{h}@{hz:.2f}"
        self._scale   = str(monitor.get("scale", 1.0))
        x             = monitor.get("x", 0)
        y             = monitor.get("y", 0)
        # Prefer the persisted file position (e.g. "auto-right") over the
        # runtime-computed absolute coordinates from hyprctl so that Hyprland
        # can continue to auto-place monitors relative to the current scale.
        self._pos     = file_position if file_position else f"{x}x{y}"
        self._modes   = monitor.get("availableModes", [])
        ex = _parse_monitor_extras(extras)
        self._vrr           = ex.get("vrr", str(int(bool(monitor.get("vrr", False)))))
        self._bitdepth      = ex.get("bitdepth", "")
        self._cm            = ex.get("cm", "")
        self._sdrbrightness = ex.get("sdrbrightness", "1.0")
        self._sdrsaturation = ex.get("sdrsaturation", "1.0")
        self._transform     = ex.get("transform", "")
        self._mirror        = ex.get("mirror", "")

    def compose(self) -> ComposeResult:
        modes_str = "  " + "  ".join(self._modes[:6]) if self._modes else "  (unavailable)"
        with Container(id="monitor-dialog"):
            yield Label(f"  Monitor: {self._name}", id="edit-title")
            yield Label(f"  {self._monitor.get('description', '')}", id="edit-meta")

            # ── Basic ──────────────────────────────────────────────────
            yield Label("  ─── Basic", classes="mon-section-header")
            yield Label("  Resolution @ Hz  (Enter to choose from available modes)",
                        classes="mon-field-label")
            yield Label(modes_str, classes="mon-field-hint")
            yield Input(value=self._res,   id="mon-res",   classes="mon-input",
                        select_on_focus=False)
            yield Label("  Scale  (Enter to choose — or type a custom value)",
                        classes="mon-field-label")
            yield Input(value=self._scale, id="mon-scale", classes="mon-input",
                        select_on_focus=False)
            yield Label("  Position  XxY  (e.g. 0x0, auto, auto-right)",
                        classes="mon-field-label")
            yield Input(value=self._pos,   id="mon-pos",   classes="mon-input",
                        select_on_focus=False)
            yield Label("  VRR / Adaptive Sync  (Enter to choose)",
                        classes="mon-field-label")
            yield Input(value=self._vrr,   id="mon-vrr",   classes="mon-input",
                        select_on_focus=False)

            # ── Display quality ────────────────────────────────────────
            yield Label("  ─── Display quality", classes="mon-section-header")
            yield Label("  Bit depth  (Enter to choose; 10-bit requires HDR-capable output)",
                        classes="mon-field-label")
            yield Input(value=self._bitdepth, id="mon-bitdepth", classes="mon-input",
                        select_on_focus=False)
            yield Label("  Color management  (Enter to choose preset)",
                        classes="mon-field-label")
            yield Input(value=self._cm, id="mon-cm", classes="mon-input",
                        select_on_focus=False)
            yield Label("  SDR brightness  (HDR mode only; Enter to adjust [0.5–3.0])",
                        classes="mon-field-label")
            yield Input(value=self._sdrbrightness, id="mon-sdrbrightness",
                        classes="mon-input", select_on_focus=False)
            yield Label("  SDR saturation  (HDR mode only; Enter to adjust [0.0–2.0])",
                        classes="mon-field-label")
            yield Input(value=self._sdrsaturation, id="mon-sdrsaturation",
                        classes="mon-input", select_on_focus=False)

            # ── Advanced ───────────────────────────────────────────────
            yield Label("  ─── Advanced", classes="mon-section-header")
            yield Label("  Transform / rotation  (Enter to choose)",
                        classes="mon-field-label")
            yield Input(value=self._transform, id="mon-transform", classes="mon-input",
                        select_on_focus=False)
            yield Label("  Mirror  (optional — name of monitor to mirror, e.g. DP-1)",
                        classes="mon-field-label")
            yield Input(value=self._mirror, id="mon-mirror", classes="mon-input",
                        select_on_focus=False)

            yield Label(
                "  [Enter] open picker / apply on last   [Esc] cancel",
                id="edit-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#mon-res", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        fid = event.input.id

        if fid == "mon-res":
            if self._modes:
                mode_opts = [(m, m) for m in self._modes]
                current_res = self.query_one("#mon-res", Input).value.strip()
                def _apply_res(val: Optional[str]) -> None:
                    if val:
                        self.query_one("#mon-res", Input).value = val
                    self.query_one("#mon-scale", Input).focus()
                self.app.push_screen(
                    OptionSelectScreen(f"Resolution — {self._name}", mode_opts, current_res),
                    _apply_res,
                )
            else:
                self.query_one("#mon-scale", Input).focus()
            return

        if fid == "mon-scale":
            scale_opts = [
                ("1.0",  "1.0  — native (100 %)"),
                ("1.25", "1.25 — 125 %"),
                ("1.5",  "1.5  — 150 %"),
                ("2.0",  "2.0  — 200 % (HiDPI)"),
                ("auto", "auto — let Hyprland decide"),
            ]
            current_scale = self.query_one("#mon-scale", Input).value.strip()
            def _apply_scale(val: Optional[str]) -> None:
                if val:
                    self.query_one("#mon-scale", Input).value = val
                self.query_one("#mon-pos", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("Scale factor", scale_opts, current_scale),
                _apply_scale,
            )
            return

        if fid == "mon-pos":
            current_pos = self.query_one("#mon-pos", Input).value.strip()
            pos_opts: list[tuple[str, str]] = []
            # Prepend the current value if it's already non-auto (so user can confirm it)
            _auto_keys = {"auto", "auto-right", "auto-left", "auto-up", "auto-down"}
            if current_pos and current_pos not in _auto_keys:
                pos_opts.append((current_pos, f"{current_pos}  (current)"))
            pos_opts += [
                ("auto",       "auto        — let Hyprland decide"),
                ("auto-right", "auto-right  — to the right of existing monitors"),
                ("auto-left",  "auto-left   — to the left  of existing monitors"),
                ("auto-up",    "auto-up     — above existing monitors"),
                ("auto-down",  "auto-down   — below existing monitors"),
            ]
            def _apply_pos(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-pos", Input).value = val
                self.query_one("#mon-vrr", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("Position", pos_opts, current_pos),
                _apply_pos,
            )
            return

        if fid == "mon-vrr":
            vrr_opts = [
                ("0", "0 — off"),
                ("1", "1 — always on"),
                ("2", "2 — fullscreen only"),
            ]
            current_vrr = self.query_one("#mon-vrr", Input).value.strip()
            def _apply_vrr(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-vrr", Input).value = val
                self.query_one("#mon-bitdepth", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("VRR / Adaptive Sync", vrr_opts, current_vrr),
                _apply_vrr,
            )
            return

        if fid == "mon-bitdepth":
            bd_opts = [
                ("",   "— auto (default 8-bit)"),
                ("8",  "8  — standard 8-bit colour"),
                ("10", "10 — 10-bit wide colour (requires HDR-capable output)"),
            ]
            current_bd = self.query_one("#mon-bitdepth", Input).value.strip()
            def _apply_bd(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-bitdepth", Input).value = val
                self.query_one("#mon-cm", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("Bit depth", bd_opts, current_bd),
                _apply_bd,
            )
            return

        if fid == "mon-cm":
            cm_opts = [
                ("",        "— default (sRGB)"),
                ("auto",    "auto    — sRGB for 8-bit, wide for 10-bit if supported"),
                ("srgb",    "srgb    — sRGB primaries"),
                ("dcip3",   "dcip3   — DCI-P3 primaries"),
                ("dp3",     "dp3     — Apple P3 primaries"),
                ("adobe",   "adobe   — Adobe RGB primaries"),
                ("wide",    "wide    — BT.2020 wide gamut"),
                ("edid",    "edid    — primaries from EDID (may be inaccurate)"),
                ("hdr",     "hdr     — HDR PQ transfer function (experimental)"),
                ("hdredid", "hdredid — HDR PQ with EDID primaries (experimental)"),
            ]
            current_cm = self.query_one("#mon-cm", Input).value.strip()
            def _apply_cm(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-cm", Input).value = val
                self.query_one("#mon-sdrbrightness", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("Color management preset", cm_opts, current_cm),
                _apply_cm,
            )
            return

        if fid == "mon-sdrbrightness":
            current_sbr = self.query_one("#mon-sdrbrightness", Input).value.strip()
            def _apply_sbr(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-sdrbrightness", Input).value = val
                self.query_one("#mon-sdrsaturation", Input).focus()
            self.app.push_screen(
                NumericEditScreen(
                    "monitor", "sdrbrightness", current_sbr or "1.0",
                    "float", "1.0",
                    "SDR brightness multiplier in HDR mode. Typical range 1.0–2.0.",
                    0.5, 3.0, 0.05, 0.01,
                ),
                _apply_sbr,
            )
            return

        if fid == "mon-sdrsaturation":
            current_ssat = self.query_one("#mon-sdrsaturation", Input).value.strip()
            def _apply_ssat(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-sdrsaturation", Input).value = val
                self.query_one("#mon-transform", Input).focus()
            self.app.push_screen(
                NumericEditScreen(
                    "monitor", "sdrsaturation", current_ssat or "1.0",
                    "float", "1.0",
                    "SDR colour saturation multiplier in HDR mode. [0.0-2.0]",
                    0.0, 2.0, 0.05, 0.01,
                ),
                _apply_ssat,
            )
            return

        if fid == "mon-transform":
            tr_opts = [
                ("",  "— no transform"),
                ("0", "0 — normal"),
                ("1", "1 — 90°"),
                ("2", "2 — 180°"),
                ("3", "3 — 270°"),
                ("4", "4 — flipped"),
                ("5", "5 — flipped + 90°"),
                ("6", "6 — flipped + 180°"),
                ("7", "7 — flipped + 270°"),
            ]
            current_tr = self.query_one("#mon-transform", Input).value.strip()
            def _apply_tr(val: Optional[str]) -> None:
                if val is not None:
                    self.query_one("#mon-transform", Input).value = val
                self.query_one("#mon-mirror", Input).focus()
            self.app.push_screen(
                OptionSelectScreen("Display transform", tr_opts, current_tr),
                _apply_tr,
            )
            return

        if fid == "mon-mirror":
            self._submit()
            return

    def _submit(self) -> None:
        res   = self.query_one("#mon-res",          Input).value.strip()
        scale = self.query_one("#mon-scale",        Input).value.strip()
        pos   = self.query_one("#mon-pos",          Input).value.strip()
        vrr   = self.query_one("#mon-vrr",          Input).value.strip()
        bd    = self.query_one("#mon-bitdepth",     Input).value.strip()
        cm    = self.query_one("#mon-cm",           Input).value.strip()
        sbr   = self.query_one("#mon-sdrbrightness",Input).value.strip()
        ssat  = self.query_one("#mon-sdrsaturation",Input).value.strip()
        tr    = self.query_one("#mon-transform",    Input).value.strip()
        mir   = self.query_one("#mon-mirror",       Input).value.strip()

        keyword = f"{self._name},{res},{pos},{scale}"
        extras: list[str] = []
        if vrr in ("0", "1", "2"):
            extras += ["vrr", vrr]
        if bd in ("8", "10"):
            extras += ["bitdepth", bd]
        if cm:
            extras += ["cm", cm]
        if sbr not in ("", "1.0", "1"):
            extras += ["sdrbrightness", sbr]
        if ssat not in ("", "1.0", "1"):
            extras += ["sdrsaturation", ssat]
        if tr not in ("", "0"):
            extras += ["transform", tr]
        if mir:
            extras += ["mirror", mir]
        if extras:
            keyword += ", " + ", ".join(extras)
        self.dismiss(keyword)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Option-select screen  (arrow-navigable list of discrete choices)
# ──────────────────────────────────────────────────────────────────────────────

class OptionSelectScreen(ModalScreen):
    """Scrollable, arrow-navigable list that returns the chosen value."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        current: str = "",
    ) -> None:
        super().__init__()
        self._title   = title
        self._options = options   # [(value, display_label), ...]
        self._current = current

    def compose(self) -> ComposeResult:
        initial = next(
            (i for i, (v, _) in enumerate(self._options) if v == self._current), 0
        )
        items = [
            ListItem(
                Label(f"  {'▶' if v == self._current else ' '} {lbl}"),
                id=f"sel-opt-{i}",
            )
            for i, (v, lbl) in enumerate(self._options)
        ]
        with Container(id="select-dialog"):
            yield Label(f"  {self._title}", id="edit-title")
            yield ListView(*items, id="option-list", initial_index=initial)
            yield Label(
                "  [↑↓] navigate   [Enter] select   [Esc] cancel",
                id="edit-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#option-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("sel-opt-"):
            idx = int(item_id[8:])
            self.dismiss(self._options[idx][0])

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Numeric slider widget + screen
# ──────────────────────────────────────────────────────────────────────────────

class SliderBar(Static):
    """Focusable slider bar — arrow keys step through a numeric range."""

    can_focus = True

    BINDINGS = [
        Binding("left",        "step(-1)",  "◄",    show=False),
        Binding("right",       "step(1)",   "►",    show=False),
        Binding("shift+left",  "fine(-1)",  "◄◄",   show=False),
        Binding("shift+right", "fine(1)",   "►► ",  show=False),
        Binding("home",        "to_min",    "min",  show=False),
        Binding("end",         "to_max",    "max",  show=False),
    ]

    class Changed(Message):
        def __init__(self, value: float) -> None:
            super().__init__()
            self.value = value

    def __init__(
        self,
        value: float,
        min_val: float,
        max_val: float,
        step: float,
        fine_step: float,
        is_int: bool,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._min    = min_val
        self._max    = max_val
        self._step   = step
        self._fine   = fine_step
        self._is_int = is_int
        self._value  = self._clamp(value)
        self._BAR_W  = 32

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _precision(self) -> int:
        s = f"{self._fine:.10f}".rstrip("0")
        return len(s.split(".")[-1]) if "." in s else 2

    def _clamp(self, v: float) -> float:
        v = max(self._min, min(self._max, v))
        return round(v) if self._is_int else round(v, self._precision())

    def _fmt(self, v: float) -> str:
        return str(int(round(v))) if self._is_int else f"{v:.{self._precision()}f}"

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float) -> None:
        new = self._clamp(v)
        if new != self._value:
            self._value = new
            self._redraw()

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _redraw(self) -> None:
        span   = self._max - self._min or 1.0
        ratio  = max(0.0, min(1.0, (self._value - self._min) / span))
        filled = int(ratio * self._BAR_W)
        bar    = "█" * filled + "░" * (self._BAR_W - filled)

        val_str  = self._fmt(self._value)
        min_str  = self._fmt(self._min)
        max_str  = self._fmt(self._max)
        step_str = self._fmt(self._step)
        fine_str = self._fmt(self._fine)

        inner_w = self._BAR_W + 2
        pad     = max(inner_w - len(min_str) - len(max_str), len(val_str) + 2)
        mid_row = min_str + val_str.center(pad) + max_str

        self.update(
            f"  [{bar}]\n"
            f"  {mid_row}\n"
            f"  [←/→] ±{step_str}   [Shift+←/→] ±{fine_str}   [Home/End] min / max"
        )

    def on_mount(self) -> None:
        self._redraw()

    # ── Key actions ───────────────────────────────────────────────────────────

    def _move(self, delta: float) -> None:
        self._value = self._clamp(self._value + delta)
        self._redraw()
        self.post_message(self.Changed(self._value))

    def action_step(self, direction: int) -> None:
        self._move(direction * self._step)

    def action_fine(self, direction: int) -> None:
        self._move(direction * self._fine)

    def action_to_min(self) -> None:
        self._value = self._min
        self._redraw()
        self.post_message(self.Changed(self._value))

    def action_to_max(self) -> None:
        self._value = self._max
        self._redraw()
        self.post_message(self.Changed(self._value))


class NumericEditScreen(ModalScreen):
    """Slider + direct text input for int / float config values."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        section: str,
        key: str,
        current: str,
        type_: str,
        default: str,
        description: str,
        min_val: float,
        max_val: float,
        step: float,
        fine_step: float,
    ) -> None:
        super().__init__()
        self._section = section
        self._key     = key
        self._type    = type_
        self._default = default
        self._desc    = description
        self._is_int  = (type_ == "int")
        self._min     = min_val
        self._max     = max_val
        self._step    = step
        self._fine    = fine_step
        try:
            self._init_val = float(current)
        except ValueError:
            try:
                self._init_val = float(default)
            except ValueError:
                self._init_val = min_val

    def _fmt(self, v: float) -> str:
        if self._is_int:
            return str(int(round(v)))
        s = f"{self._fine:.10f}".rstrip("0")
        prec = len(s.split(".")[-1]) if "." in s else 2
        return f"{v:.{prec}f}"

    def compose(self) -> ComposeResult:
        init_str = self._fmt(self._init_val)
        with Container(id="slider-dialog"):
            yield Label(f"  {self._section}:{self._key}", id="edit-title")
            yield Label(
                f"  type: {self._type}   default: {self._default}"
                f"   range: [{self._fmt(self._min)}, {self._fmt(self._max)}]\n"
                f"  {self._desc}",
                id="edit-meta",
            )
            yield SliderBar(
                self._init_val, self._min, self._max,
                self._step, self._fine, self._is_int,
                id="num-slider",
            )
            yield Input(
                value=init_str,
                id="slider-input",
                placeholder="type for precision…",
                select_on_focus=True,
            )
            yield Label(
                "  [←/→] adjust   [Shift+←/→] fine   [Tab] type value   [Enter] apply   [Esc] cancel",
                id="edit-hint",
            )

    def on_mount(self) -> None:
        self.query_one("#num-slider", SliderBar).focus()

    @on(SliderBar.Changed)
    def _slider_moved(self, event: SliderBar.Changed) -> None:
        self.query_one("#slider-input", Input).value = self._fmt(event.value)

    @on(Input.Changed, "#slider-input")
    def _input_changed(self, event: Input.Changed) -> None:
        try:
            self.query_one("#num-slider", SliderBar).value = float(event.value)
        except ValueError:
            pass

    def on_key(self, event) -> None:
        if event.key == "enter":
            focused = self.focused
            if focused and getattr(focused, "id", "") == "num-slider":
                self._apply()
                event.stop()

    @on(Input.Submitted, "#slider-input")
    def _input_submitted(self, _) -> None:
        self._apply()

    def _apply(self) -> None:
        raw = self.query_one("#slider-input", Input).value.strip()
        try:
            v = max(self._min, min(self._max, float(raw)))
            self.dismiss(self._fmt(v))
        except ValueError:
            self.notify("Invalid number — enter a numeric value.", severity="warning")

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Main application
# ──────────────────────────────────────────────────────────────────────────────

class HyprconfApp(App):

    CSS = APP_CSS

    BINDINGS = [
        Binding("q",      "quit",           "Quit"),
        # Enter is handled exclusively via @on(DataTable.RowSelected) to avoid
        # double-calling action_edit_option when the DataTable's own binding
        # and the app-level binding both fire on the same keypress.
        Binding("space",  "toggle_bool",    "Toggle",  show=True,  priority=False),
        Binding("d",      "reset_option",   " Reset",  show=True),
        Binding("n",      "new_entry",      " New",    show=True),
        Binding("D",      "delete_entry",   " Delete", show=True),
        Binding("r",      "refresh",        "Refresh", show=True),
        Binding("s",      "save",           "Save",    show=True),
        Binding("/",      "focus_search",   "Filter",  show=True),
        Binding("escape", "escape_action",  "Clear",   show=False),
        Binding("tab",    "switch_focus",   "Switch pane", show=False),
        Binding("h",      "focus_sidebar",  "Sidebar", show=False),
        Binding("l",      "focus_table",    "Table",   show=False),
    ]

    def __init__(self, initial_section: Optional[str] = None, slim: bool = False) -> None:
        super().__init__()
        self._initial_section  = initial_section or "general"
        self._current_section  = self._initial_section
        self._slim             = slim
        self._row_keys: list[str] = []
        self._search_query     = ""
        self._search_visible   = False
        self._theme_name       = _TC["name"]
        # pending[section][key] = value_str  — changes not yet written to disk
        self._pending: dict[str, dict[str, str]] = {}
        self._monitor_refresh_started = False

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        session_note = "session active" if HYPRLAND_ACTIVE else "no Hyprland session — defaults shown"
        theme_info   = f"[theme: {self._theme_name}]"

        with Horizontal(id="brand-bar"):
            yield Static("hyprconf ░░▒▓", id="brand-left")
            yield Static(session_note,    id="brand-status")
            yield Static(theme_info,      id="brand-right")

        with Horizontal(id="main-pane"):
            if not self._slim:
                with Vertical(id="sidebar"):
                    yield Input(placeholder="/ filter...", id="filter-input")
                    yield Static("─" * 20, id="sidebar-sep")
                    yield ListView(*self._build_list_items(), id="section-list")

            with Vertical(id="content"):
                yield Static(f"  {SECTION_LABELS.get(self._initial_section, self._initial_section)}", id="section-title")
                yield Static("", id="pending-bar")
                yield DataTable(id="option-table", cursor_type="row", zebra_stripes=True)

        yield Footer()

    def _build_list_items(self) -> list[ListItem]:
        items: list[ListItem] = []
        for s in SECTION_ORDER:
            if s == "":
                items.append(ListItem(Label("  ─────────────"), id="sep-divider",
                                      classes="sep-item"))
            else:
                safe_id = "sec-" + s.replace(".", "__")
                label   = SECTION_LABELS.get(s, s)
                items.append(ListItem(Label(f"  {label}"), id=safe_id))
        return items

    # ── Mount ─────────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        if not HYPRLAND_ACTIVE:
            self.notify(
                "Hyprland session not detected — showing defaults. Runtime changes will be config-only.",
                severity="warning",
                timeout=6,
            )

        if not self._slim:
            self.query_one("#filter-input", Input).display = False

        self._load_section(self._initial_section)
        self._mark_active(self._initial_section)

        if not self._slim:
            lv = self.query_one("#section-list", ListView)
            for i, s in enumerate(SECTION_ORDER):
                if s == self._initial_section:
                    lv.index = i
                    break
            lv.focus()
        else:
            self.query_one("#option-table", DataTable).focus()

    # ── Section loading ───────────────────────────────────────────────────────

    def _mark_active(self, section: str) -> None:
        """Toggle the .active-section CSS class to highlight the current section."""
        if self._slim:
            return
        try:
            for item in self.query("#section-list ListItem"):
                item.remove_class("active-section")
            safe = "sec-" + section.replace(".", "__")
            self.query_one(f"#{safe}").add_class("active-section")
        except Exception:
            pass

    def _load_section(self, section: str) -> None:
        self._current_section = section
        label = SECTION_LABELS.get(section, section)

        # Update slim-mode header
        if self._slim:
            self.title = f"hyprconf — {label}"

        self.query_one("#section-title", Static).update(f"  {label}")
        table = self.query_one("#option-table", DataTable)
        table.clear(columns=True)
        self._row_keys = []

        if section == "monitors":
            self._fill_monitors(table)
            # Start the auto-refresh timer exactly once across the lifetime of
            # the app; the callback is a no-op when monitors is not active.
            if not self._monitor_refresh_started:
                self._monitor_refresh_started = True
                self.set_interval(2.0, self._refresh_monitors)
        elif section == "keybinds":
            self._fill_keybinds(table)
        elif section == "window_rules":
            self._fill_rules(table, re.compile(r"^windowrule"), "Window rule")
        elif section == "workspace_rules":
            self._fill_rules(table, re.compile(r"^workspace\s*="), "Workspace rule")
        elif section in ("hyprlock", "hypridle"):
            self._fill_blocks(table, section)
        elif section == "hyprpaper":
            self._fill_paper(table)
        elif section == "theme":
            self._fill_themes(table)
        elif section == "hardware":
            self._fill_hardware(table)
        elif section in OPTION_SCHEMA:
            self._fill_options(table, section)
        else:
            table.add_column("INFO")
            table.add_row(f"'{section}' is not a configurable section.")

        self._update_pending_bar()

    def _fill_options(self, table: DataTable, section: str) -> None:
        table.add_column("KEY",         width=28)
        table.add_column("VALUE",       width=22)
        table.add_column("DEFAULT",     width=14)
        table.add_column("DESCRIPTION", width=50)
        q = self._search_query
        for key, (type_, default, desc) in OPTION_SCHEMA[section].items():
            if q and q not in key.lower() and q not in desc.lower():
                continue
            val, source = get_current_value(section, key, default, self._pending)
            # Show parentheses for default values; asterisk for pending
            if source == "pending":
                val_cell = f"* {val}"
            elif source == "default":
                val_cell = f"({val})"
            else:
                val_cell = val
            table.add_row(key, val_cell, default, desc)
            self._row_keys.append(key)

    def _fill_monitors(self, table: DataTable) -> None:
        table.add_column("NAME",        width=14)
        table.add_column("DESCRIPTION", width=24)
        table.add_column("RESOLUTION",  width=12)
        table.add_column("REFRESH Hz",  width=10)
        table.add_column("SCALE",       width=7)
        table.add_column("POSITION",    width=10)
        table.add_column("WORKSPACE",   width=10)
        table.add_column("VRR",         width=5)
        monitors = get_monitors()
        if not monitors:
            msg = "(Hyprland not running)" if not HYPRLAND_ACTIVE else "(no monitors found)"
            table.add_row(msg, "", "", "", "", "", "", "")
            return
        q = self._search_query
        for m in monitors:
            name = m.get("name", "")
            if q and q not in name.lower():
                continue
            table.add_row(
                name,
                m.get("description", "")[:22],
                f"{m.get('width', 0)}x{m.get('height', 0)}",
                f"{m.get('refreshRate', 0):.2f}",
                f"{m.get('scale', 1.0):.2f}",
                f"{m.get('x', 0)},{m.get('y', 0)}",
                m.get("activeWorkspace", {}).get("name", ""),
                "on" if m.get("vrr") else "off",
            )
            self._row_keys.append(name)

    def _fill_keybinds(self, table: DataTable) -> None:
        table.add_column("TYPE",     width=10)
        table.add_column("MODS",     width=18)
        table.add_column("KEY",      width=14)
        table.add_column("DISPATCH", width=18)
        table.add_column("ARGUMENT", width=36)
        entries = _lib_keybinds_with_loc(KEYBINDS_CONF)
        q = self._search_query
        if not entries:
            table.add_row("(no keybinds found)", "", "", "", "")
            self._row_keys.append("")
            return
        for e in entries:
            row = (e.kind, e.mods or "—", e.key, e.dispatcher, e.args)
            if q and not any(q in part.lower() for part in row):
                continue
            table.add_row(*row)
            self._row_keys.append(f"__keybind__{e.file_path}::{e.line_idx}")

    def _fill_rules(self, table: DataTable, pat: re.Pattern, label: str) -> None:
        table.add_column("#",    width=5)
        table.add_column("RULE", width=110)
        is_workspace = "workspace" in label.lower()
        entries = _lib_wksp_rules(HYPRLAND_CONF) if is_workspace                   else _lib_win_rules(HYPRLAND_CONF)
        q = self._search_query
        if not entries:
            table.add_row("—", f"(no {label.lower()}s found)")
            self._row_keys.append("")
            return
        idx = 1
        for e in entries:
            if q and q not in e.rule.lower():
                continue
            table.add_row(str(idx), e.rule)
            self._row_keys.append(f"__rule__{e.file_path}::{e.line_idx}")
            idx += 1

    def _fill_blocks(self, table: DataTable, section: str) -> None:
        """Block-aware renderer for hyprlock and hypridle."""
        if section == "hyprlock":
            blocks = _lib_lock_blocks()
        else:
            blocks = _lib_idle_blocks()

        table.add_column("BLOCK / KEY", width=26)
        table.add_column("VALUE",       width=80)

        if not blocks:
            path_label = str(HYPRLOCK_CONF if section == "hyprlock" else HYPRIDLE_CONF)
            table.add_row("(empty)", f"No blocks found in {path_label}")
            return

        q = self._search_query
        for blk in blocks:
            # Block header row — not editable; D key will delete the whole block
            hdr_key = f"__blkhdr__{blk.file_path}::{blk.start_line}::{blk.end_line}"
            hdr_label = f"[{blk.block_type}]"
            if not q or q in blk.block_type.lower():
                table.add_row(hdr_label, "")
                self._row_keys.append(hdr_key)

            for field_key, field_val in blk.fields.items():
                if q and q not in field_key.lower() and q not in field_val.lower():
                    continue
                # Find the actual line number for this field
                line_idx = blk.field_line_idx(field_key)
                row_key = (
                    f"__blkfld__{blk.file_path}::{blk.start_line}::{blk.end_line}"
                    f"::{line_idx}::{field_key}"
                )
                table.add_row(f"  {field_key}", field_val)
                self._row_keys.append(row_key)

    def _fill_paper(self, table: DataTable) -> None:
        """Structured renderer for hyprpaper.conf."""
        table.add_column("TYPE / KEY", width=20)
        table.add_column("VALUE",      width=80)

        data = _lib_paper_read_all()
        q    = self._search_query

        # ── Settings and variables ────────────────────────────────────────────
        for s in data["settings"]:
            if q and q not in s.key.lower() and q not in s.value.lower():
                continue
            table.add_row(s.key, s.value)
            self._row_keys.append(f"__line__{s.file_path}::{s.line_idx}")

        # ── Preloads ─────────────────────────────────────────────────────────
        if data["preloads"]:
            table.add_row("", "")
            self._row_keys.append("__sep__")
            table.add_row("[preloads]", "")
            self._row_keys.append("__sep__")
            for p in data["preloads"]:
                if q and q not in p.path.lower():
                    continue
                table.add_row("  preload", p.path)
                self._row_keys.append(f"__line__{p.file_path}::{p.line_idx}")

        # ── Wallpaper lines ───────────────────────────────────────────────────
        if data["wallpaper_lines"]:
            table.add_row("", "")
            self._row_keys.append("__sep__")
            table.add_row("[wallpapers]", "")
            self._row_keys.append("__sep__")
            for w in data["wallpaper_lines"]:
                mon = w.monitor or "(all)"
                if q and q not in mon.lower() and q not in w.path.lower():
                    continue
                table.add_row(f"  wallpaper  {mon}", w.path)
                self._row_keys.append(f"__line__{w.file_path}::{w.line_idx}")

        # ── Wallpaper blocks ──────────────────────────────────────────────────
        if data["wallpaper_blocks"]:
            if not data["wallpaper_lines"]:
                table.add_row("", "")
                self._row_keys.append("__sep__")
                table.add_row("[wallpapers]", "")
                self._row_keys.append("__sep__")
            for blk in data["wallpaper_blocks"]:
                mon  = blk.fields.get("monitor", "") or "(all)"
                path = blk.fields.get("path", "")
                if q and q not in mon.lower() and q not in path.lower():
                    continue
                hdr_key = f"__blkhdr__{blk.file_path}::{blk.start_line}::{blk.end_line}"
                table.add_row(f"  [{mon}]", path)
                self._row_keys.append(hdr_key)
                for fk, fv in blk.fields.items():
                    if fk in ("monitor", "path"):
                        continue  # shown in header
                    line_idx = blk.field_line_idx(fk)
                    row_key  = (
                        f"__blkfld__{blk.file_path}::{blk.start_line}::{blk.end_line}"
                        f"::{line_idx}::{fk}"
                    )
                    table.add_row(f"    {fk}", fv)
                    self._row_keys.append(row_key)

        # ── Wallpaper picker ──────────────────────────────────────────────────
        wps = _get_wallpapers()
        if wps:
            table.add_row("", "")
            self._row_keys.append("__sep__")
            table.add_row("[~/wallpaper/]", "Enter to set as active wallpaper")
            self._row_keys.append("__sep__")
            for wp in wps:
                if q and q not in str(wp).lower():
                    continue
                table.add_row("  " + wp.name, str(wp))
                self._row_keys.append(f"__wp__{wp}")

    def _fill_themes(self, table: DataTable) -> None:
        table.add_column("THEME",  width=34)
        table.add_column("TYPE",   width=6)
        table.add_column("STATUS", width=10)
        themes = list_themes()
        q = self._search_query
        if not themes:
            table.add_row("(no themes found)", "", "")
            return
        for name in themes:
            try:
                data = json.loads((THEME_DIR / f"{name}.json").read_text())
            except Exception:
                data = {}
            appearance = data.get("appearance", "")
            if q and q not in name.lower() and q not in appearance.lower():
                continue
            status = " active" if name == self._theme_name else ""
            tag = "☀" if appearance == "light" else "☾"
            table.add_row(name, f" {tag}", status)
            self._row_keys.append(name)

    def _fill_hardware(self, table: DataTable) -> None:
        table.add_column("COMPONENT",  width=24)
        table.add_column("STATUS",     width=16)
        table.add_column("ACTION",     width=28)

        def _has_touchscreen() -> bool:
            for f in _glob.iglob("/sys/class/input/*/device/uevent"):
                try:
                    with open(f) as fh:
                        content = fh.read()
                    # Standard udev-tagged touchscreens (ELAN HID, etc.)
                    if "ID_INPUT_TOUCHSCREEN=1" in content:
                        return True
                    # Wacom I2C pen+touch digitizers (e.g. ThinkPad X13 Yoga):
                    # touch component is named "Wacom HID * Finger" on i2c bus
                    # but udev never sets ID_INPUT_TOUCHSCREEN=1 for wacom devices.
                    # Requiring i2c- bus avoids false-positives from USB Wacom tablets.
                    if ('NAME="Wacom' in content and 'Finger' in content
                            and 'PHYS="i2c-' in content):
                        return True
                except OSError:
                    pass
            return False

        def _has_accelerometer() -> bool:
            return bool(_glob.glob("/sys/bus/iio/devices/*/in_accel_x_raw"))

        def _proc_running(name: str) -> bool:
            try:
                r = subprocess.run(["pgrep", "-x", name], capture_output=True, timeout=5)
                return r.returncode == 0
            except FileNotFoundError:
                return False

        def _installed(name: str) -> bool:
            return shutil.which(name) is not None

        ts_det   = _has_touchscreen()
        acc_det  = _has_accelerometer()
        osk_inst = _installed("wvkbd-mobintl")
        osk_run  = _proc_running("wvkbd-mobintl")
        rot_inst = _installed("autorotate")
        rot_run  = _proc_running("autorotate")

        table.add_row("Touchscreen",
                      "✓ detected"   if ts_det   else "not detected", "")
        self._row_keys.append("")
        table.add_row("Accelerometer",
                      "✓ detected"   if acc_det  else "not detected", "")
        self._row_keys.append("")
        table.add_row("─" * 22, "─" * 14, "─" * 26)
        self._row_keys.append("")

        osk_status = "running" if osk_run else ("installed" if osk_inst else "not installed")
        table.add_row("OSK (wvkbd)",
                      osk_status,
                      "Enter → toggle" if osk_inst else "")
        self._row_keys.append("hw_osk_toggle" if osk_inst else "")

        rot_status = "running" if rot_run else ("installed" if rot_inst else "not installed")
        table.add_row("Auto-rotation",
                      rot_status,
                      "Enter → toggle" if rot_inst else "")
        self._row_keys.append("hw_rotate_toggle" if rot_inst else "")

    def _refresh_monitors(self) -> None:
        if self._current_section == "monitors":
            table = self.query_one("#option-table", DataTable)
            table.clear(columns=True)
            self._row_keys = []
            self._fill_monitors(table)

    # ── Pending-changes UI ────────────────────────────────────────────────────

    def _update_pending_bar(self) -> None:
        total = sum(len(v) for v in self._pending.values())
        bar = self.query_one("#pending-bar", Static)
        if total:
            bar.update(f"  {total} unsaved change(s) — press [s] to save to {OVERRIDES_FILE.name}")
            bar.add_class("visible")
        else:
            bar.remove_class("visible")

    # ── Sidebar navigation ────────────────────────────────────────────────────

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        item_id: str = event.item.id or ""
        if not item_id.startswith("sec-"):
            return
        section = item_id[4:].replace("__", ".")
        if section == self._current_section:
            return
        self._search_query = ""
        if self._search_visible and not self._slim:
            search = self.query_one("#filter-input", Input)
            search.value = ""
            search.display = False
            self._search_visible = False
        self._load_section(section)
        self._mark_active(section)

    # ── Row selection / Enter ─────────────────────────────────────────────────

    @on(DataTable.RowSelected)
    def on_row_selected(self, event: DataTable.RowSelected) -> None:
        section = self._current_section
        row_idx = event.cursor_row

        # ── Keybinds ─────────────────────────────────────────────────────────
        if section == "keybinds":
            if 0 <= row_idx < len(self._row_keys):
                rk = self._row_keys[row_idx]
                if rk.startswith("__keybind__"):
                    payload = rk[11:]
                    file_path, lidx = payload.rsplit("::", 1)
                    line_idx = int(lidx)
                    # Read the entry to pre-fill the modal
                    entries = _lib_keybinds_with_loc(Path(file_path))
                    entry = next((e for e in entries if e.line_idx == line_idx), None)
                    scr = KeybindEditScreen(
                        kind=entry.kind if entry else "bind",
                        mods=entry.mods if entry else "",
                        key=entry.key  if entry else "",
                        dispatcher=entry.dispatcher if entry else "",
                        args=entry.args if entry else "",
                    )
                    def _handle_kb_edit(result, _fp=Path(file_path), _li=line_idx):
                        if result is None:
                            return
                        kind, mods, key, disp, args = result
                        ok = _lib_update_keybind(_fp, _li, kind, mods, key, disp, args)
                        self.notify(f"Keybind updated" if ok else "Failed to update keybind",
                                    severity="information" if ok else "error")
                        self._load_section(section)
                    self.push_screen(scr, _handle_kb_edit)
            return

        # ── Window / workspace rules ──────────────────────────────────────────
        if section in ("window_rules", "workspace_rules"):
            if 0 <= row_idx < len(self._row_keys):
                rk = self._row_keys[row_idx]
                if rk.startswith("__rule__"):
                    payload = rk[8:]
                    file_path, lidx = payload.rsplit("::", 1)
                    line_idx = int(lidx)
                    lines_in_file = _lib_read_lines(Path(file_path))
                    current_line = lines_in_file[line_idx] if line_idx < len(lines_in_file) else ""
                    scr = TextLineEditScreen(Path(file_path), line_idx, current_line)
                    def _handle_rule_edit(result, _fp=Path(file_path), _li=line_idx):
                        if result is None:
                            return
                        ok = _lib_update_line(_fp, _li, result)
                        self.notify(f"Rule updated" if ok else "Failed to update rule",
                                    severity="information" if ok else "error")
                        self._load_section(section)
                    self.push_screen(scr, _handle_rule_edit)
            return

        # ── hyprlock / hypridle / hyprpaper ──────────────────────────────────
        if section in ("hyprlock", "hypridle", "hyprpaper"):
            if 0 <= row_idx < len(self._row_keys):
                rk = self._row_keys[row_idx]

                # Block field row — edit the value
                if rk.startswith("__blkfld__"):
                    # encoding: __blkfld__{file}::{start}::{end}::{line_idx}::{field_key}
                    payload = rk[10:]
                    parts = payload.split("::")
                    if len(parts) >= 5:
                        file_path = parts[0]
                        blk_start = int(parts[1])
                        blk_end   = int(parts[2])
                        line_idx  = int(parts[3])
                        field_key = "::".join(parts[4:])
                        lines_in_file = _lib_read_lines(Path(file_path))
                        if line_idx < len(lines_in_file):
                            _parts = lines_in_file[line_idx].split("=", 1)
                            current_val = _parts[1].strip() if len(_parts) > 1 else ""
                        else:
                            current_val = ""
                        label = f"{field_key} ="
                        scr   = TextLineEditScreen(Path(file_path), line_idx, current_val, prompt=label)
                        def _handle_blkfld_edit(
                            result, _fp=Path(file_path), _li=line_idx,
                            _fk=field_key,
                        ):
                            if result is None:
                                return
                            lines_now = _lib_read_lines(_fp)
                            if _li < len(lines_now):
                                indent = len(lines_now[_li]) - len(lines_now[_li].lstrip())
                                new_line = " " * indent + f"{_fk} = {result}"
                                ok = _lib_update_line(_fp, _li, new_line)
                            else:
                                ok = False
                            self.notify("Field updated" if ok else "Failed to update field",
                                        severity="information" if ok else "error")
                            self._load_section(section)
                        self.push_screen(scr, _handle_blkfld_edit)

                # Block header row — no action on Enter (D to delete)
                elif rk.startswith("__blkhdr__"):
                    self.notify("Press [d] to delete this block", severity="information")

                # Plain line row (settings, preloads, wallpaper lines in paper)
                elif rk.startswith("__line__"):
                    payload = rk[8:]
                    file_path, lidx = payload.rsplit("::", 1)
                    line_idx = int(lidx)
                    lines_in_file = _lib_read_lines(Path(file_path))
                    current_line  = lines_in_file[line_idx] if line_idx < len(lines_in_file) else ""
                    scr = TextLineEditScreen(Path(file_path), line_idx, current_line)
                    def _handle_line_edit(result, _fp=Path(file_path), _li=line_idx):
                        if result is None:
                            return
                        if result.strip() == "":
                            ok = _lib_delete_line(_fp, _li)
                            self.notify("Line deleted" if ok else "Failed to delete",
                                        severity="information" if ok else "error")
                        else:
                            ok = _lib_update_line(_fp, _li, result)
                            self.notify("Line updated" if ok else "Failed to update",
                                        severity="information" if ok else "error")
                        self._load_section(section)
                    self.push_screen(scr, _handle_line_edit)

                # Wallpaper picker row
                elif rk.startswith("__wp__"):
                    self._set_wallpaper(Path(rk[6:]))
            return

        # ── Monitors ─────────────────────────────────────────────────────────
        if section == "monitors":
            if 0 <= row_idx < len(self._row_keys) and self._row_keys[row_idx]:
                monitor_name = self._row_keys[row_idx]
                monitors = get_monitors()
                mon_data = next(
                    (m for m in monitors if m.get("name") == monitor_name), None
                )
                if mon_data is None:
                    self.notify(
                        f"Could not retrieve data for {monitor_name}",
                        severity="warning",
                    )
                    return

                # Read persisted extras (bitdepth, cm, sdrbrightness, etc.) from monitors.conf
                file_configs = _lib_monitor_configs()
                file_mc = next((mc for mc in file_configs if mc.name == monitor_name), None)
                file_extras   = file_mc.extras   if file_mc else ""
                file_position = file_mc.position if file_mc else ""

                # Snapshot ALL monitors now (before the edit dialog opens) so
                # that handle_monitor can detect which neighbours need adjusting.
                monitors_snapshot = monitors

                def handle_monitor(keyword: Optional[str]) -> None:
                    if not keyword:
                        return
                    # Apply at runtime
                    ok_rt = _run(["hyprctl", "keyword", "monitor", keyword])
                    # Parse keyword back into fields and persist to monitors.conf
                    parts = [p.strip() for p in keyword.split(",")]
                    if len(parts) >= 4:
                        _lib_upsert_monitor(
                            name=parts[0], resolution=parts[1],
                            position=parts[2], scale=parts[3],
                            extras=", ".join(parts[4:]) if len(parts) > 4 else "",
                        )
                        self.notify(f"Monitor saved: {parts[0]}")

                        # ── Adjust adjacent monitors if logical size changed ──────────
                        # Skip when: special res keyword, scale=auto, or transform changed
                        # (transform swap changes which axis is "width" — safer to skip).
                        new_res   = parts[1]
                        new_scale_s = parts[3]
                        new_extras_d = _parse_monitor_extras(", ".join(parts[4:]) if len(parts) > 4 else "")
                        new_tr = int(new_extras_d.get("transform", "0") or "0")
                        old_tr = int(mon_data.get("transform", 0) or 0)
                        res_m  = re.match(r'^(\d+)[xX](\d+)', new_res)
                        if res_m and new_scale_s not in ("auto", "") and new_tr == old_tr:
                            try:
                                old_scale = float(mon_data.get("scale", 1.0) or 1.0)
                                new_scale = float(new_scale_s)
                                old_lw, old_lh = _compute_logical_size(
                                    int(mon_data.get("width", 1920)),
                                    int(mon_data.get("height", 1080)),
                                    old_scale, old_tr,
                                )
                                new_lw, new_lh = _compute_logical_size(
                                    int(res_m.group(1)), int(res_m.group(2)),
                                    new_scale, new_tr,
                                )
                                _adjust_adjacent_monitor_positions(
                                    parts[0], monitors_snapshot, old_lw, old_lh, new_lw, new_lh,
                                )
                            except (ValueError, ZeroDivisionError):
                                pass
                    elif ok_rt is not None:
                        self.notify(f"Monitor configured: {keyword}")
                    else:
                        self.notify(f"hyprctl rejected: {keyword}", severity="error")
                    self._refresh_monitors()

                self.push_screen(MonitorEditScreen(mon_data, file_extras, file_position), handle_monitor)
            return

        # ── Hardware ─────────────────────────────────────────────────────────
        if section == "hardware":
            if 0 <= row_idx < len(self._row_keys):
                rk = self._row_keys[row_idx]
                if rk == "hw_osk_toggle":
                    pid_r = subprocess.run(
                        ["pgrep", "-x", "wvkbd-mobintl"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if pid_r.returncode == 0:
                        for pid in pid_r.stdout.split():
                            try:
                                subprocess.run(["kill", pid], check=True)
                            except subprocess.CalledProcessError:
                                pass
                        self.notify("OSK stopped")
                    else:
                        launcher = shutil.which("wvkbd-launcher")
                        if launcher:
                            try:
                                subprocess.Popen([launcher])
                                self.notify("OSK started")
                            except OSError as e:
                                self.notify(f"Failed to start OSK: {e}", severity="error")
                        else:
                            self.notify("wvkbd-launcher not found", severity="error")
                    self._load_section("hardware")
                elif rk == "hw_rotate_toggle":
                    pid_r = subprocess.run(
                        ["pgrep", "-x", "autorotate"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if pid_r.returncode == 0:
                        for pid in pid_r.stdout.split():
                            try:
                                subprocess.run(["kill", pid], check=True)
                            except subprocess.CalledProcessError:
                                pass
                        self.notify("Auto-rotation stopped")
                    else:
                        rotbin = shutil.which("autorotate")
                        if rotbin:
                            try:
                                subprocess.Popen([rotbin])
                                self.notify("Auto-rotation started")
                            except OSError as e:
                                self.notify(f"Failed to start auto-rotation: {e}", severity="error")
                        else:
                            self.notify("autorotate not found", severity="error")
                    self._load_section("hardware")
            return

        # ── Theme picker ─────────────────────────────────────────────────────
        if section == "theme":
            if 0 <= row_idx < len(self._row_keys):
                self._apply_theme(self._row_keys[row_idx])
            return

        # ── All OPTION_SCHEMA sections ────────────────────────────────────────
        self.action_edit_option()

    def _apply_theme(self, name: str) -> None:
        if not THEME_SCRIPT.exists():
            self.notify("theme-switcher script not found", severity="error")
            return
        try:
            subprocess.run(
                ["python3", str(THEME_SCRIPT), name],
                check=True, capture_output=True, timeout=60,
            )
            self._theme_name = name
            self.query_one("#brand-right", Static).update(f"[theme: {name}]")
            self.notify(f"Theme applied: {name}")
            self._load_section("theme")
        except subprocess.CalledProcessError as e:
            err = e.stderr.decode(errors="replace").strip() if e.stderr else str(e)
            self.notify(f"Theme failed: {err}", severity="error")

    def _set_wallpaper(self, path: Path) -> None:
        if not path.exists():
            self.notify(f"File not found: {path}", severity="error")
            return
        # hyprpaper has its own IPC — use `hyprctl hyprpaper wallpaper` not
        # `hyprctl keyword`, which only applies to Hyprland config sections.
        out = _run(["hyprctl", "hyprpaper", "wallpaper", f",{path}"])
        if out is not None:
            self.notify(f"Wallpaper set: {path.name}")
        else:
            self.notify(f"Selected: {path.name}  (edit hyprpaper.conf manually to persist)")

    def _new_block_entry(self, section: str, block_types: list) -> None:
        """Prompt for block type then add a new block with defaults."""
        label = "hyprlock" if section == "hyprlock" else "hypridle"
        opts  = [(bt, bt) for bt in block_types]

        def _handle(btype: Optional[str]) -> None:
            if not btype:
                return
            if section == "hyprlock":
                ok = _lib_add_lock_block(btype)
            else:
                ok = _lib_add_idle_block(btype)
            self.notify(
                f"Block [{btype}] added" if ok else "Failed to add block",
                severity="information" if ok else "error",
            )
            self._load_section(section)

        self.push_screen(OptionSelectScreen(f"Add {label} block", opts), _handle)

    def _new_paper_entry(self) -> None:
        """Add a new wallpaper entry to hyprpaper.conf."""
        scr = TextLineEditScreen(
            HYPRPAPER_CONF, -1, "",
            prompt="Wallpaper path (absolute, e.g. /home/user/wallpaper/bg.jpg):",
        )
        def _handle(result) -> None:
            if not result or not result.strip():
                return
            wp_path = result.strip()
            ok = _lib_add_preload(wp_path)
            if ok:
                ok2 = _lib_add_wp_block("", wp_path)
            else:
                ok2 = False
            if ok and ok2:
                self.notify("Wallpaper entry added")
            elif ok and not ok2:
                self.notify("Preload added but wallpaper line failed", severity="warning")
            else:
                self.notify("Failed to add wallpaper entry", severity="error")
            self._load_section("hyprpaper")
        self.push_screen(scr, _handle)

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_new_entry(self) -> None:
        """Open a modal to add a new entry for the current file-based section."""
        section = self._current_section
        if section == "keybinds":
            def _handle(result) -> None:
                if result is None:
                    return
                kind, mods, key, disp, args = result
                ok = _lib_add_keybind(kind, mods, key, disp, args, KEYBINDS_CONF)
                self.notify(f"Keybind added" if ok else "Failed to add keybind",
                            severity="information" if ok else "error")
                self._load_section(section)
            self.push_screen(KeybindEditScreen(), _handle)

        elif section == "window_rules":
            def _handle(result) -> None:
                if result is None:
                    return
                rule_type, action_or_id, filters_or_opts = result
                ok = _lib_add_win_rule(action_or_id, filters_or_opts)
                self.notify("Window rule added" if ok else "Failed to add rule",
                            severity="information" if ok else "error")
                self._load_section(section)
            self.push_screen(RuleEditScreen(rule_type="window"), _handle)

        elif section == "workspace_rules":
            def _handle(result) -> None:
                if result is None:
                    return
                rule_type, wksp_id, opts = result
                ok = _lib_add_wksp_rule(wksp_id, opts)
                self.notify("Workspace rule added" if ok else "Failed to add rule",
                            severity="information" if ok else "error")
                self._load_section(section)
            self.push_screen(RuleEditScreen(rule_type="workspace"), _handle)

        elif section == "hyprlock":
            self._new_block_entry("hyprlock", list(_LOCK_BLOCK_TYPES))

        elif section == "hypridle":
            self._new_block_entry("hypridle", list(_IDLE_BLOCK_TYPES))

        elif section == "hyprpaper":
            self._new_paper_entry()

        elif section == "monitors":
            # New monitor: open MonitorEditScreen with an empty/placeholder dict
            blank = {"name": "", "description": "", "width": 1920, "height": 1080,
                     "refreshRate": 60.0, "scale": 1.0, "x": 0, "y": 0,
                     "vrr": False, "availableModes": []}
            scr = MonitorEditScreen(blank, "", "auto")
            def _handle(keyword: Optional[str]) -> None:
                if not keyword:
                    return
                ok_rt = _run(["hyprctl", "keyword", "monitor", keyword])
                parts = [p.strip() for p in keyword.split(",")]
                if len(parts) >= 4:
                    _lib_upsert_monitor(
                        name=parts[0], resolution=parts[1],
                        position=parts[2], scale=parts[3],
                        extras=", ".join(parts[4:]) if len(parts) > 4 else "",
                    )
                    self.notify(f"Monitor added: {parts[0]}")
                self._refresh_monitors()
            self.push_screen(scr, _handle)
        else:
            self.notify(f"New entry not supported for: {section}", severity="warning")

    def action_delete_entry(self) -> None:
        """Delete the currently selected row from its config file."""
        section = self._current_section
        table   = self.query_one("#option-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._row_keys):
            return
        rk = self._row_keys[row_idx]

        def _do_delete(file_path: Path, line_idx: int, label: str) -> None:
            ok = _lib_delete_line(file_path, line_idx)
            self.notify(f"{label} deleted" if ok else f"Failed to delete {label}",
                        severity="information" if ok else "error")
            self._load_section(section)

        if rk.startswith("__keybind__"):
            payload = rk[11:]
            fp, li = payload.rsplit("::", 1)
            _do_delete(Path(fp), int(li), "Keybind")

        elif rk.startswith("__rule__"):
            payload = rk[8:]
            fp, li = payload.rsplit("::", 1)
            _do_delete(Path(fp), int(li), "Rule")

        elif rk.startswith("__line__"):
            payload = rk[8:]
            fp, li = payload.rsplit("::", 1)
            _do_delete(Path(fp), int(li), "Line")

        elif rk.startswith("__blkhdr__") or rk.startswith("__blkfld__"):
            # Both header and field rows delete the whole block
            prefix = "__blkhdr__" if rk.startswith("__blkhdr__") else "__blkfld__"
            payload = rk[len(prefix):]
            parts = payload.split("::")
            file_path  = parts[0]
            blk_start  = int(parts[1])
            blk_end    = int(parts[2])
            if section == "hyprlock":
                blocks = _lib_lock_blocks()
            elif section == "hypridle":
                blocks = _lib_idle_blocks()
            else:
                from hyprconf.block_conf import read_blocks
                from hyprconf.hyprpaper import HYPRPAPER_CONF as _PAPER_CONF
                blocks = read_blocks(Path(file_path))
            blk = next(
                (b for b in blocks
                 if b.start_line == blk_start and b.end_line == blk_end),
                None,
            )
            if blk is None:
                self.notify("Block no longer found (stale row?)", severity="warning")
                self._load_section(section)
                return
            from hyprconf.block_conf import delete_block as _delete_block
            ok = _delete_block(blk)
            self.notify(
                f"Block [{blk.block_type}] deleted" if ok else "Failed to delete block",
                severity="information" if ok else "error",
            )
            self._load_section(section)

        elif section == "monitors" and rk:
            # Delete monitor from monitors.conf by name
            mon_cfg = _lib_monitor_configs(MONITORS_FILE)
            mc = next((m for m in mon_cfg if m.name == rk), None)
            if mc:
                ok = _lib_delete_monitor(mc.file_path, mc.line_idx)
                # Also apply disable at runtime if active
                _run(["hyprctl", "keyword", "monitor", f"{rk},disable"])
                self.notify(f"Monitor {rk} removed" if ok else "Failed to remove monitor",
                            severity="information" if ok else "error")
                self._refresh_monitors()
            else:
                self.notify(f"Monitor {rk!r} not found in monitors.conf",
                            severity="warning")
        else:
            self.notify("Nothing to delete here.", severity="warning")

    def action_edit_option(self) -> None:
        section = self._current_section
        if section not in OPTION_SCHEMA:
            return
        table   = self.query_one("#option-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._row_keys):
            return
        key = self._row_keys[row_idx]
        if key not in OPTION_SCHEMA[section]:
            return
        type_, default, desc = OPTION_SCHEMA[section][key]
        current, _ = get_current_value(section, key, default, self._pending)

        # Booleans are toggled in-place; everything else gets the modal.
        if type_ == "bool":
            new_val = "false" if current.lower() in ("true", "1") else "true"
            self._commit(section, key, new_val, row_idx)
            return

        def handle_result(new_value: Optional[str]) -> None:
            if new_value is None or new_value == current:
                return
            self._commit(section, key, new_value, row_idx)

        if type_.startswith("enum:"):
            raw_choices = [v.strip() for v in type_[5:].split(",") if v.strip()]
            choices = [(v, v) for v in raw_choices]
            opts = _enrich_enum_labels(desc, choices)
            self.push_screen(
                OptionSelectScreen(f"{section} › {key}", opts, current),
                handle_result,
            )
        elif type_ in ("int", "float"):
            lo, hi, step, fine = _parse_numeric_range(desc, type_)
            self.push_screen(
                NumericEditScreen(section, key, current, type_, default, desc,
                                  lo, hi, step, fine),
                handle_result,
            )
        else:
            self.push_screen(
                EditScreen(section, key, current, type_, default, desc),
                handle_result,
            )

    def action_toggle_bool(self) -> None:
        section = self._current_section
        if section not in OPTION_SCHEMA:
            return
        table   = self.query_one("#option-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._row_keys):
            return
        key = self._row_keys[row_idx]
        if key not in OPTION_SCHEMA[section]:
            return
        type_, default, _ = OPTION_SCHEMA[section][key]
        if type_ != "bool":
            return
        current, _ = get_current_value(section, key, default, self._pending)
        new_val = "false" if current.lower() in ("true", "1") else "true"
        self._commit(section, key, new_val, row_idx)

    def action_reset_option(self) -> None:
        section = self._current_section
        if section not in OPTION_SCHEMA:
            return
        table   = self.query_one("#option-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._row_keys):
            return
        key = self._row_keys[row_idx]
        if key not in OPTION_SCHEMA[section]:
            return
        _, default, _ = OPTION_SCHEMA[section][key]
        # Remove from pending, apply default at runtime
        if section in self._pending:
            self._pending[section].pop(key, None)
            if not self._pending[section]:
                del self._pending[section]
        hyprctl_apply(section, key, default)
        self.notify(f"Reset {section}:{key} → {default}")
        self._load_section(section)
        table = self.query_one("#option-table", DataTable)
        if row_idx < table.row_count:
            table.move_cursor(row=row_idx)

    def action_save(self) -> None:
        if not self._pending:
            self.notify("Nothing to save.")
            return
        ok, n = save_pending(self._pending)
        if ok:
            self._pending.clear()
            self._update_pending_bar()
            self.notify(f"Saved {n} change(s) to {OVERRIDES_FILE.name}")
        else:
            self.notify("Save failed — check file permissions.", severity="error")

    def on_unmount(self) -> None:
        """Auto-save any pending changes when the app exits (q, Ctrl+C, or any other exit)."""
        if self._pending:
            ok, n = save_pending(self._pending)
            if not ok:
                import sys
                print(
                    "hyprconf-tui: WARNING — auto-save on exit failed. "
                    "Pending changes were not written to disk.",
                    file=sys.stderr,
                )

    def action_quit(self) -> None:
        self.exit()

    def action_refresh(self) -> None:
        self._load_section(self._current_section)
        self.notify(f"Refreshed: {self._current_section}")

    def action_focus_search(self) -> None:
        if self._slim:
            return
        search = self.query_one("#filter-input", Input)
        search.display = True
        self._search_visible = True
        search.focus()

    def action_escape_action(self) -> None:
        if self._search_visible:
            search = self.query_one("#filter-input", Input)
            search.value = ""
            search.display = False
            self._search_visible = False
            self._search_query = ""
            self._load_section(self._current_section)
            self.query_one("#option-table", DataTable).focus()

    def action_switch_focus(self) -> None:
        if self._slim:
            return
        focused = self.focused
        try:
            sidebar = self.query_one("#section-list", ListView)
        except Exception:
            return

        # Walk up the DOM to detect whether focus is inside the sidebar
        in_sidebar = False
        node = focused
        while node is not None:
            if node is sidebar:
                in_sidebar = True
                break
            node = getattr(node, "parent", None)

        if in_sidebar:
            self.query_one("#option-table", DataTable).focus()
        else:
            sidebar.focus()

    def action_focus_sidebar(self) -> None:
        if not self._slim:
            self.query_one("#section-list", ListView).focus()

    def action_focus_table(self) -> None:
        self.query_one("#option-table", DataTable).focus()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _commit(self, section: str, key: str, value: str, row_idx: int) -> None:
        """Apply a value at runtime (if possible) and stage it as pending."""
        applied = hyprctl_apply(section, key, value)
        status  = "applied" if applied else "config-only"

        if section not in self._pending:
            self._pending[section] = {}
        self._pending[section][key] = value

        self.notify(f"{section}:{key} = {value}  [{status}]")
        self._load_section(section)
        self._update_pending_bar()

        table = self.query_one("#option-table", DataTable)
        if row_idx < table.row_count:
            table.move_cursor(row=row_idx)

    # ── Input events ──────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._search_query = event.value.lower()
            self._load_section(self._current_section)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter-input":
            self.query_one("#option-table", DataTable).focus()


# ──────────────────────────────────────────────────────────────────────────────
#  Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    all_sections = [s for s in SECTION_ORDER if s]

    parser = argparse.ArgumentParser(
        description="hyprconf TUI — Hyprland configuration suite",
        prog="hyprconf tui",
    )
    parser.add_argument(
        "--section", "-s",
        metavar="SECTION",
        help=f"Open at section. Available: {', '.join(all_sections)}",
    )
    parser.add_argument(
        "--slim",
        action="store_true",
        help="Slim mode: hide sidebar (auto-enabled when --section is given)",
    )
    args = parser.parse_args()

    section = args.section
    # Normalise section name (dots and underscores are interchangeable)
    if section:
        # Try exact match first, then normalised
        normalised = section.replace("-", "_").replace(".", "_")
        for s in all_sections:
            if s == section or s.replace(".", "_") == normalised:
                section = s
                break
        else:
            parser.error(
                f"Unknown section: {args.section}\n"
                f"Valid sections: {', '.join(all_sections)}"
            )

    # --slim without --section: show slim view at default section
    slim = args.slim or (section is not None)

    HyprconfApp(initial_section=section, slim=slim).run()


if __name__ == "__main__":
    main()
