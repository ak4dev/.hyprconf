#!/usr/bin/env python3
# hyprconf-tui — Hyprland configuration TUI for an Omarchy system
# Part of hyprconf: https://github.com/ak4dev/.hyprconf
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
)

# ── Shared hyprconf library (install.sh symlinks lib/hyprconf there) ────────
sys.path.insert(0, str(Path.home() / ".local" / "lib"))
from hyprconf import omarchy as _omarchy  # noqa: E402
from hyprconf.config import read_persisted as _lib_read_persisted  # noqa: E402
from hyprconf.config import save_pending as _lib_save_pending  # noqa: E402
from hyprconf.file_edit import delete_line as _lib_delete_line  # noqa: E402
from hyprconf.file_edit import read_lines as _lib_read_lines  # noqa: E402
from hyprconf.file_edit import update_line as _lib_update_line  # noqa: E402
from hyprconf.hyprctl import apply_monitor as _lib_apply_monitor  # noqa: E402
from hyprconf.hyprctl import disable_monitor as _lib_disable_monitor  # noqa: E402
from hyprconf.hyprctl import get_monitors as _lib_get_monitors  # noqa: E402
from hyprconf.hyprctl import get_option as _lib_hyprctl_get  # noqa: E402
from hyprconf.hyprctl import set_option as _lib_hyprctl_apply  # noqa: E402
from hyprconf.keybinds import add_keybind as _lib_add_keybind  # noqa: E402
from hyprconf.keybinds import read_keybinds_with_location as _lib_keybinds_with_loc  # noqa: E402
from hyprconf.keybinds import update_keybind as _lib_update_keybind  # noqa: E402
from hyprconf.monitors import MONITORS_FILE  # noqa: E402
from hyprconf.monitors import delete_monitor as _lib_delete_monitor  # noqa: E402
from hyprconf.monitors import read_monitor_configs as _lib_monitor_configs  # noqa: E402
from hyprconf.monitors import upsert_monitor as _lib_upsert_monitor  # noqa: E402
from hyprconf.paths import HYPRLAND_CONF as _HYPRLAND_CONF  # noqa: E402
from hyprconf.paths import KEYBINDS_FILE as _KEYBINDS_FILE  # noqa: E402
from hyprconf.paths import OVERRIDES_FILE as _OVERRIDES_FILE  # noqa: E402
from hyprconf.rules import add_window_rule as _lib_add_win_rule  # noqa: E402
from hyprconf.rules import add_workspace_rule as _lib_add_wksp_rule  # noqa: E402
from hyprconf.rules import read_window_rules_with_location as _lib_win_rules  # noqa: E402
from hyprconf.rules import read_workspace_rules_with_location as _lib_wksp_rules  # noqa: E402
from hyprconf.schema import OPTION_SCHEMA, SECTION_LABELS, SECTION_ORDER  # noqa: E402

# ──────────────────────────────────────────────────────────────────────────────
#  Paths
# ──────────────────────────────────────────────────────────────────────────────

OVERRIDES_FILE = _OVERRIDES_FILE
KEYBINDS_CONF = _KEYBINDS_FILE
HYPRLAND_CONF = _HYPRLAND_CONF

# ──────────────────────────────────────────────────────────────────────────────
#  Theme colors (loaded once at startup, baked into CSS)
# ──────────────────────────────────────────────────────────────────────────────


def _load_theme_colors() -> dict[str, str]:
    """The TUI's palette: Omarchy's active theme (``current/theme/colors.toml``
    via :func:`hyprconf.omarchy.theme_colors`), with these defaults for any
    role it does not provide."""
    colors = {
        "background": "#1e1e2e",
        "foreground": "#cdd6f4",
        "accent": "#89b4fa",
        "comment": "#585b70",
    }
    colors.update(_omarchy.theme_colors())
    return colors


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


_TC = _load_theme_colors()
_BG = _TC["background"]
_FG = _TC["foreground"]
_ACC = _TC["accent"]
_CMT = _TC["comment"]
_BG2 = _dim(_BG, 0.80)  # sidebar / header background
_BG3 = _dim(_BG, 0.88)  # table alternate row

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


def hyprctl_get(section: str, key: str) -> str | None:
    return _lib_hyprctl_get(section, key)


def hyprctl_apply(section: str, key: str, value: str) -> bool:
    return _lib_hyprctl_apply(section, key, value)


def read_persisted(section: str, key: str) -> str | None:
    return _lib_read_persisted(section, key)


def get_current_value(
    section: str, key: str, default: str, pending: dict[str, dict[str, str]]
) -> tuple[str, str]:
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


def get_monitors() -> list[dict]:
    return _lib_get_monitors() if HYPRLAND_ACTIVE else []


# ──────────────────────────────────────────────────────────────────────────────
#  Numeric range + enum label helpers  (used by modal screens)
# ──────────────────────────────────────────────────────────────────────────────


def _parse_numeric_range(description: str, type_: str) -> tuple[float, float, float, float]:
    """Return (min_val, max_val, step, fine_step) parsed from a schema description."""
    # Match [X-Y] (handles negative lows like [-1.0-1.0]) or [X to Y]
    m = re.search(r"\[(-?\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\]", description)
    if not m:
        m = re.search(r"\[(-?\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\]", description, re.IGNORECASE)
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
        step = max(0.01, round(span / 20, 4))
        fine_step = max(0.01, round(span / 100, 4))
        if fine_step >= step:
            fine_step = round(step / 5, 4)
    else:
        step = max(1, int(round(span / 20)))
        fine_step = max(1, int(round(span / 100)))
        if fine_step >= step:
            fine_step = max(1, step // 5)

    return lo, hi, float(step), float(fine_step)


def _enrich_enum_labels(description: str, choices: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Attach inline N=label annotations from the schema description, if present."""
    annotated: dict[str, str] = {}
    for m in re.finditer(r"(\w+)=([^,\]\s][^,\]]*?)(?=[,\]\s]|$)", description):
        annotated[m.group(1).strip()] = m.group(2).strip()
    if not annotated:
        return choices
    return [(v, f"{v} — {annotated[v]}" if v in annotated else v) for v, _ in choices]


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
_ABS_POS_RE = re.compile(r"^(-?\d+)[xX](-?\d+)$")


def _compute_logical_size(
    phys_w: int,
    phys_h: int,
    scale: float,
    transform: int,
) -> tuple[float, float]:
    """Return (logical_width, logical_height) after applying scale and transform.

    Transforms 1/3/5/7 (90° / 270° rotations) swap the physical axes before
    dividing by scale, matching how Hyprland measures position offsets.
    """
    if transform in (1, 3, 5, 7):
        phys_w, phys_h = phys_h, phys_w
    return phys_w / scale, phys_h / scale


def _adjust_adjacent_monitor_positions(
    edited_name: str,
    snapshot: list[dict],  # ALL monitor dicts from hyprctl, captured BEFORE the edit
    old_lw: float,  # old logical width  of the edited monitor
    old_lh: float,  # old logical height of the edited monitor
    new_lw: float,  # new logical width
    new_lh: float,  # new logical height
) -> None:
    """Shift absolute-positioned monitors adjacent to the edited one to prevent overlaps.

    When the edited monitor's logical size grows (scale decreases, or a larger
    resolution is chosen), monitors that were sitting to its right or below can
    overlap the new extent.  This function shifts every such monitor — including
    chains — by the same delta so their relative layout is preserved.

    Monitors using auto / auto-right / etc. are intentionally skipped: Hyprland
    will recompute their positions automatically.  Only monitors with explicit
    numeric positions in monitors.lua need manual adjustment.
    """
    delta_w = new_lw - old_lw
    delta_h = new_lh - old_lh
    if abs(delta_w) < 0.5 and abs(delta_h) < 0.5:
        return

    edited = next((m for m in snapshot if m.get("name") == edited_name), None)
    if not edited:
        return

    old_x = float(edited.get("x", 0))
    old_y = float(edited.get("y", 0))
    old_right = old_x + old_lw
    old_bottom = old_y + old_lh

    file_configs = _lib_monitor_configs()

    for mon in snapshot:
        mname = mon.get("name", "")
        if mname == edited_name:
            continue

        mx = float(mon.get("x", 0))
        my = float(mon.get("y", 0))
        m_w = int(mon.get("width", 1920))
        m_h = int(mon.get("height", 1080))
        m_tr = int(mon.get("transform", 0) or 0)
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
                _lib_apply_monitor(mname, file_mc.resolution, new_pos, file_mc.scale, extras_str)
                continue

        # ── Vertical: shift monitors below the edited monitor ─────────────────
        if delta_h > 0.5 and my >= old_bottom - 1:
            # X-band overlap: mon's horizontal range must intersect edited's range
            if not (mx + m_lw <= old_x or mx >= old_x + old_lw):
                new_file_y = file_y + int(round(delta_h))
                new_pos = f"{file_x}x{new_file_y}"
                extras_str = file_mc.extras.strip()
                _lib_upsert_monitor(mname, file_mc.resolution, new_pos, file_mc.scale, extras_str)
                _lib_apply_monitor(mname, file_mc.resolution, new_pos, file_mc.scale, extras_str)


def _apply_monitor_keyword(
    keyword: str, mon_data: dict | None, snapshot: list[dict]
) -> tuple[str, str]:
    """The blocking half of a monitor edit: live-apply, persist, shift neighbours.

    *keyword* is the ``NAME,RES,POS,SCALE[, extras…]`` spec MonitorEditScreen
    returns; *mon_data* is the monitor's hyprctl record before the edit (None
    for a brand-new entry — nothing to shift then). Returns ``(message,
    severity)`` for the UI thread to show. Runs off the UI thread (see
    :meth:`HyprconfApp._in_background`): every step here shells out, and a
    frozen event pump is what let a second Enter re-open the editor.
    """
    parts = [p.strip() for p in keyword.split(",")]
    if len(parts) < 4:
        return f"Invalid monitor spec: {keyword}", "error"
    name, res, pos, scale = parts[:4]
    extras = ", ".join(parts[4:])

    applied = _lib_apply_monitor(name, res, pos, scale, extras)
    saved = _lib_upsert_monitor(name=name, resolution=res, position=pos, scale=scale, extras=extras)

    # ── Adjust adjacent monitors if logical size changed ──────────────────
    # Skip when: special res keyword, scale=auto, or transform changed
    # (transform swap changes which axis is "width" — safer to skip).
    if mon_data is not None and saved:
        new_tr = int(_parse_monitor_extras(extras).get("transform", "0") or "0")
        old_tr = int(mon_data.get("transform", 0) or 0)
        res_m = re.match(r"^(\d+)[xX](\d+)", res)
        if res_m and scale not in ("auto", "") and new_tr == old_tr:
            try:
                old_scale = float(mon_data.get("scale", 1.0) or 1.0)
                old_lw, old_lh = _compute_logical_size(
                    int(mon_data.get("width", 1920)),
                    int(mon_data.get("height", 1080)),
                    old_scale,
                    old_tr,
                )
                new_lw, new_lh = _compute_logical_size(
                    int(res_m.group(1)), int(res_m.group(2)), float(scale), new_tr
                )
                _adjust_adjacent_monitor_positions(name, snapshot, old_lw, old_lh, new_lw, new_lh)
            except (ValueError, ZeroDivisionError):
                pass

    if not saved:
        return f"Failed to save monitor {name} to {MONITORS_FILE.name}", "error"
    if applied:
        return f"Monitor {name}: applied and saved", "information"
    if HYPRLAND_ACTIVE:
        return f"Monitor {name}: saved, but hyprctl rejected the live change", "warning"
    return f"Monitor {name}: saved (no Hyprland session to apply to)", "information"


# ──────────────────────────────────────────────────────────────────────────────
#  Keybind edit / new screen
# ──────────────────────────────────────────────────────────────────────────────


class KeybindEditScreen(ModalScreen):
    """Add or edit a keybind."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Apply"),
    ]
    _FIELDS = ("kb-kind", "kb-mods", "kb-key", "kb-disp", "kb-args", "kb-desc")

    def __init__(
        self,
        kind: str = "bind",
        mods: str = "",
        key: str = "",
        dispatcher: str = "",
        args: str = "",
        description: str = "",
    ) -> None:
        super().__init__()
        self._kind = kind
        self._mods = mods
        self._key = key
        self._disp = dispatcher
        self._args = args
        self._desc = description

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label("   Keybind", id="edit-title")
            yield Label(
                "  Bind type: bind  bindl  bindr  binde  bindm  bindel  etc.", id="edit-meta"
            )
            yield Label(
                "  Mods: SUPER  SUPER SHIFT  ALT  CTRL  (empty = no modifier)",
                classes="mon-field-hint",
            )
            yield Label("  Bind type", classes="mon-field-label")
            yield Input(value=self._kind, id="kb-kind", classes="mon-input", select_on_focus=True)
            yield Label("  Modifiers  (e.g. $mainMod SHIFT)", classes="mon-field-label")
            yield Input(value=self._mods, id="kb-mods", classes="mon-input", select_on_focus=True)
            yield Label("  Key  (e.g. T, F1, XF86AudioPlay)", classes="mon-field-label")
            yield Input(value=self._key, id="kb-key", classes="mon-input", select_on_focus=True)
            yield Label(
                "  Dispatcher  (e.g. exec, togglefloating, workspace)", classes="mon-field-label"
            )
            yield Input(value=self._disp, id="kb-disp", classes="mon-input", select_on_focus=True)
            yield Label("  Arguments  (e.g. alacritty, 2, ...)", classes="mon-field-label")
            yield Input(value=self._args, id="kb-args", classes="mon-input", select_on_focus=True)
            yield Label(
                "  Description  (shown in Omarchy's SUPER+K keybindings menu)",
                classes="mon-field-label",
            )
            yield Input(value=self._desc, id="kb-desc", classes="mon-input", select_on_focus=True)
            yield Label(
                "  [Enter] next / apply on last   [Ctrl+S] apply   [Esc] cancel", id="edit-hint"
            )

    def on_mount(self) -> None:
        self.query_one(f"#{self._FIELDS[0]}", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # kb-kind gets an arrow-selectable list instead of free text
        if event.input.id == "kb-kind":
            kind_opts = [
                ("bind", "bind — standard keybind"),
                ("bindl", "bindl — fires while locked"),
                ("bindr", "bindr — fires on key release"),
                ("binde", "binde — repeats while held"),
                ("bindm", "bindm — mouse binding"),
                ("bindel", "bindel — locked + on release"),
                ("bindrel", "bindrel — release binding"),
            ]
            current_kind = self.query_one("#kb-kind", Input).value.strip() or "bind"

            def _set_kind(val: str | None) -> None:
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
            self.action_submit()

    def action_submit(self) -> None:
        kind = self.query_one("#kb-kind", Input).value.strip() or "bind"
        mods = self.query_one("#kb-mods", Input).value.strip()
        key = self.query_one("#kb-key", Input).value.strip()
        disp = self.query_one("#kb-disp", Input).value.strip()
        args = self.query_one("#kb-args", Input).value.strip()
        desc = self.query_one("#kb-desc", Input).value.strip()
        if not key or not disp:
            self.notify("Key and Dispatcher are required.", severity="warning")
            return
        self.dismiss((kind, mods, key, disp, args, desc))

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Rule edit / new screen
# ──────────────────────────────────────────────────────────────────────────────


class RuleEditScreen(ModalScreen):
    """Add or edit a window rule or workspace rule."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]
    _FIELDS_WIN = ("rule-action", "rule-filter1", "rule-filter2")
    _FIELDS_WKSP = ("wksp-id", "wksp-opts")

    def __init__(
        self,
        rule_type: str = "window",
        action: str = "",
        filter1: str = "",
        filter2: str = "",
        wksp_id: str = "",
        wksp_opts: str = "",
    ) -> None:
        super().__init__()
        self._rule_type = rule_type
        self._action = action
        self._filter1 = filter1
        self._filter2 = filter2
        self._wksp_id = wksp_id
        self._wksp_opts = wksp_opts

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            if self._rule_type == "window":
                yield Label("   Window Rule", id="edit-title")
                yield Label(
                    "  Rule actions: float  tile  fullscreen  pin  opacity F  size W H",
                    id="edit-meta",
                )
                yield Label(
                    "  Filters: class:REGEX  title:REGEX  xwayland:0|1  floating:0|1",
                    classes="mon-field-hint",
                )
                yield Label(
                    "  Action  (e.g. float, opacity 0.9, size 800 600)", classes="mon-field-label"
                )
                yield Input(
                    value=self._action, id="rule-action", classes="mon-input", select_on_focus=True
                )
                yield Label("  Filter 1  (e.g. class:Alacritty)", classes="mon-field-label")
                yield Input(
                    value=self._filter1,
                    id="rule-filter1",
                    classes="mon-input",
                    select_on_focus=True,
                )
                yield Label("  Filter 2  (optional, e.g. title:.*)", classes="mon-field-label")
                yield Input(
                    value=self._filter2,
                    id="rule-filter2",
                    classes="mon-input",
                    select_on_focus=True,
                )
                yield Label("  [Enter] next / apply on last   [Esc] cancel", id="edit-hint")
            else:
                yield Label("   Workspace Rule", id="edit-title")
                yield Label("  Workspace ID: 1-10, special:NAME", id="edit-meta")
                yield Label(
                    "  Options: monitor:NAME  default:true  persistent:true  on-created-empty:EXEC",
                    classes="mon-field-hint",
                )
                yield Label("  Workspace ID  (e.g. 1, special:magic)", classes="mon-field-label")
                yield Input(
                    value=self._wksp_id, id="wksp-id", classes="mon-input", select_on_focus=True
                )
                yield Label(
                    "  Options  (e.g. monitor:HDMI-A-1, default:true)", classes="mon-field-label"
                )
                yield Input(
                    value=self._wksp_opts, id="wksp-opts", classes="mon-input", select_on_focus=True
                )
                yield Label("  [Enter] next / apply on last   [Esc] cancel", id="edit-hint")

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
            action = self.query_one("#rule-action", Input).value.strip()
            filter1 = self.query_one("#rule-filter1", Input).value.strip()
            filter2 = self.query_one("#rule-filter2", Input).value.strip()
            if not action:
                self.notify("Action is required.", severity="warning")
                return
            filters = [f for f in [filter1, filter2] if f]
            self.dismiss(("window", action, filters))
        else:
            wksp_id = self.query_one("#wksp-id", Input).value.strip()
            wksp_opts = self.query_one("#wksp-opts", Input).value.strip()
            if not wksp_id:
                self.notify("Workspace ID is required.", severity="warning")
                return
            self.dismiss(("workspace", wksp_id, wksp_opts))

    def action_cancel(self) -> None:
        self.dismiss(None)


# ──────────────────────────────────────────────────────────────────────────────
#  Text line edit screen  (window / workspace rule lines)
# ──────────────────────────────────────────────────────────────────────────────


class TextLineEditScreen(ModalScreen):
    """Edit a single line in a config file."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, file_path: Path, line_idx: int, line_text: str, prompt: str = "") -> None:
        super().__init__()
        self._file_path = file_path
        self._line_idx = line_idx
        self._line_text = line_text
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Container(id="edit-dialog"):
            yield Label(
                f"   {self._file_path.name}  line {self._line_idx + 1}",
                id="edit-title",
            )
            if self._prompt:
                yield Label(f"  {self._prompt}", id="edit-meta")
            else:
                yield Label("  Edit the line below and press Enter to save.", id="edit-meta")
            yield Label(
                "  Delete all text and press Enter to remove the line.", classes="mon-field-hint"
            )
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
        self._section = section
        self._key = key
        self._current = current
        self._type = type_
        self._default = default
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
                f"  {self._description}" + choices_line,
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
    """Edit a single monitor's configuration.

    Dismisses with a ``NAME,RES,POS,SCALE[, extras…]`` spec (or None on
    cancel); the app turns that into an ``hl.monitor({ … })`` call for both
    the live apply and monitors.lua. Ctrl+S applies from any field, so the
    ten fields need not all be walked with Enter.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Apply"),
    ]
    _FIELDS = (
        "mon-res",
        "mon-scale",
        "mon-pos",
        "mon-vrr",
        "mon-bitdepth",
        "mon-cm",
        "mon-sdrbrightness",
        "mon-sdrsaturation",
        "mon-transform",
        "mon-mirror",
    )

    def __init__(self, monitor: dict, extras: str = "", file_position: str = "") -> None:
        super().__init__()
        self._monitor = monitor
        self._name = monitor.get("name", "")
        w = monitor.get("width", 1920)
        h = monitor.get("height", 1080)
        hz = monitor.get("refreshRate", 60.0)
        self._res = f"{w}x{h}@{hz:.2f}"
        self._scale = str(monitor.get("scale", 1.0))
        x = monitor.get("x", 0)
        y = monitor.get("y", 0)
        # Prefer the persisted file position (e.g. "auto-right") over the
        # runtime-computed absolute coordinates from hyprctl so that Hyprland
        # can continue to auto-place monitors relative to the current scale.
        self._pos = file_position if file_position else f"{x}x{y}"
        self._modes = monitor.get("availableModes", [])
        ex = _parse_monitor_extras(extras)
        self._vrr = ex.get("vrr", str(int(bool(monitor.get("vrr", False)))))
        self._bitdepth = ex.get("bitdepth", "")
        self._cm = ex.get("cm", "")
        self._sdrbrightness = ex.get("sdrbrightness", "1.0")
        self._sdrsaturation = ex.get("sdrsaturation", "1.0")
        self._transform = ex.get("transform", "")
        self._mirror = ex.get("mirror", "")

    def compose(self) -> ComposeResult:
        modes_str = "  " + "  ".join(self._modes[:6]) if self._modes else "  (unavailable)"
        with Container(id="monitor-dialog"):
            yield Label(f"  Monitor: {self._name}", id="edit-title")
            yield Label(f"  {self._monitor.get('description', '')}", id="edit-meta")

            # ── Basic ──────────────────────────────────────────────────
            yield Label("  ─── Basic", classes="mon-section-header")
            yield Label(
                "  Resolution @ Hz  (Enter to choose from available modes)",
                classes="mon-field-label",
            )
            yield Label(modes_str, classes="mon-field-hint")
            yield Input(value=self._res, id="mon-res", classes="mon-input", select_on_focus=False)
            yield Label(
                "  Scale  (Enter to choose — or type a custom value)", classes="mon-field-label"
            )
            yield Input(
                value=self._scale, id="mon-scale", classes="mon-input", select_on_focus=False
            )
            yield Label("  Position  XxY  (e.g. 0x0, auto, auto-right)", classes="mon-field-label")
            yield Input(value=self._pos, id="mon-pos", classes="mon-input", select_on_focus=False)
            yield Label("  VRR / Adaptive Sync  (Enter to choose)", classes="mon-field-label")
            yield Input(value=self._vrr, id="mon-vrr", classes="mon-input", select_on_focus=False)

            # ── Display quality ────────────────────────────────────────
            yield Label("  ─── Display quality", classes="mon-section-header")
            yield Label(
                "  Bit depth  (Enter to choose; 10-bit requires HDR-capable output)",
                classes="mon-field-label",
            )
            yield Input(
                value=self._bitdepth, id="mon-bitdepth", classes="mon-input", select_on_focus=False
            )
            yield Label("  Color management  (Enter to choose preset)", classes="mon-field-label")
            yield Input(value=self._cm, id="mon-cm", classes="mon-input", select_on_focus=False)
            yield Label(
                "  SDR brightness  (HDR mode only; Enter to adjust [0.5–3.0])",
                classes="mon-field-label",
            )
            yield Input(
                value=self._sdrbrightness,
                id="mon-sdrbrightness",
                classes="mon-input",
                select_on_focus=False,
            )
            yield Label(
                "  SDR saturation  (HDR mode only; Enter to adjust [0.0–2.0])",
                classes="mon-field-label",
            )
            yield Input(
                value=self._sdrsaturation,
                id="mon-sdrsaturation",
                classes="mon-input",
                select_on_focus=False,
            )

            # ── Advanced ───────────────────────────────────────────────
            yield Label("  ─── Advanced", classes="mon-section-header")
            yield Label("  Transform / rotation  (Enter to choose)", classes="mon-field-label")
            yield Input(
                value=self._transform,
                id="mon-transform",
                classes="mon-input",
                select_on_focus=False,
            )
            yield Label(
                "  Mirror  (optional — name of monitor to mirror, e.g. DP-1)",
                classes="mon-field-label",
            )
            yield Input(
                value=self._mirror, id="mon-mirror", classes="mon-input", select_on_focus=False
            )

            yield Label(
                "  [Enter] open picker / apply on last   [Ctrl+S] apply   [Esc] cancel",
                id="edit-hint",
            )

    def on_mount(self) -> None:
        self.query_one(f"#{self._FIELDS[0]}", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        fid = event.input.id

        if fid == "mon-res":
            if self._modes:
                mode_opts = [(m, m) for m in self._modes]
                current_res = self.query_one("#mon-res", Input).value.strip()

                def _apply_res(val: str | None) -> None:
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
                ("1.0", "1.0  — native (100 %)"),
                ("1.25", "1.25 — 125 %"),
                ("1.5", "1.5  — 150 %"),
                ("2.0", "2.0  — 200 % (HiDPI)"),
                ("auto", "auto — let Hyprland decide"),
            ]
            current_scale = self.query_one("#mon-scale", Input).value.strip()

            def _apply_scale(val: str | None) -> None:
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
                ("auto", "auto        — let Hyprland decide"),
                ("auto-right", "auto-right  — to the right of existing monitors"),
                ("auto-left", "auto-left   — to the left  of existing monitors"),
                ("auto-up", "auto-up     — above existing monitors"),
                ("auto-down", "auto-down   — below existing monitors"),
            ]

            def _apply_pos(val: str | None) -> None:
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

            def _apply_vrr(val: str | None) -> None:
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
                ("", "— auto (default 8-bit)"),
                ("8", "8  — standard 8-bit colour"),
                ("10", "10 — 10-bit wide colour (requires HDR-capable output)"),
            ]
            current_bd = self.query_one("#mon-bitdepth", Input).value.strip()

            def _apply_bd(val: str | None) -> None:
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
                ("", "— default (sRGB)"),
                ("auto", "auto    — sRGB for 8-bit, wide for 10-bit if supported"),
                ("srgb", "srgb    — sRGB primaries"),
                ("dcip3", "dcip3   — DCI-P3 primaries"),
                ("dp3", "dp3     — Apple P3 primaries"),
                ("adobe", "adobe   — Adobe RGB primaries"),
                ("wide", "wide    — BT.2020 wide gamut"),
                ("edid", "edid    — primaries from EDID (may be inaccurate)"),
                ("hdr", "hdr     — HDR PQ transfer function (experimental)"),
                ("hdredid", "hdredid — HDR PQ with EDID primaries (experimental)"),
            ]
            current_cm = self.query_one("#mon-cm", Input).value.strip()

            def _apply_cm(val: str | None) -> None:
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

            def _apply_sbr(val: str | None) -> None:
                if val is not None:
                    self.query_one("#mon-sdrbrightness", Input).value = val
                self.query_one("#mon-sdrsaturation", Input).focus()

            self.app.push_screen(
                NumericEditScreen(
                    "monitor",
                    "sdrbrightness",
                    current_sbr or "1.0",
                    "float",
                    "1.0",
                    "SDR brightness multiplier in HDR mode. Typical range 1.0–2.0.",
                    0.5,
                    3.0,
                    0.05,
                    0.01,
                ),
                _apply_sbr,
            )
            return

        if fid == "mon-sdrsaturation":
            current_ssat = self.query_one("#mon-sdrsaturation", Input).value.strip()

            def _apply_ssat(val: str | None) -> None:
                if val is not None:
                    self.query_one("#mon-sdrsaturation", Input).value = val
                self.query_one("#mon-transform", Input).focus()

            self.app.push_screen(
                NumericEditScreen(
                    "monitor",
                    "sdrsaturation",
                    current_ssat or "1.0",
                    "float",
                    "1.0",
                    "SDR colour saturation multiplier in HDR mode. [0.0-2.0]",
                    0.0,
                    2.0,
                    0.05,
                    0.01,
                ),
                _apply_ssat,
            )
            return

        if fid == "mon-transform":
            tr_opts = [
                ("", "— no transform"),
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

            def _apply_tr(val: str | None) -> None:
                if val is not None:
                    self.query_one("#mon-transform", Input).value = val
                self.query_one("#mon-mirror", Input).focus()

            self.app.push_screen(
                OptionSelectScreen("Display transform", tr_opts, current_tr),
                _apply_tr,
            )
            return

        if fid == self._FIELDS[-1]:
            self.action_submit()

    def action_submit(self) -> None:
        res = self.query_one("#mon-res", Input).value.strip()
        scale = self.query_one("#mon-scale", Input).value.strip()
        pos = self.query_one("#mon-pos", Input).value.strip()
        vrr = self.query_one("#mon-vrr", Input).value.strip()
        bd = self.query_one("#mon-bitdepth", Input).value.strip()
        cm = self.query_one("#mon-cm", Input).value.strip()
        sbr = self.query_one("#mon-sdrbrightness", Input).value.strip()
        ssat = self.query_one("#mon-sdrsaturation", Input).value.strip()
        tr = self.query_one("#mon-transform", Input).value.strip()
        mir = self.query_one("#mon-mirror", Input).value.strip()

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
        self._title = title
        self._options = options  # [(value, display_label), ...]
        self._current = current

    def compose(self) -> ComposeResult:
        initial = next((i for i, (v, _) in enumerate(self._options) if v == self._current), 0)
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
        Binding("left", "step(-1)", "◄", show=False),
        Binding("right", "step(1)", "►", show=False),
        Binding("shift+left", "fine(-1)", "◄◄", show=False),
        Binding("shift+right", "fine(1)", "►► ", show=False),
        Binding("home", "to_min", "min", show=False),
        Binding("end", "to_max", "max", show=False),
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
        self._min = min_val
        self._max = max_val
        self._step = step
        self._fine = fine_step
        self._is_int = is_int
        self._value = self._clamp(value)
        self._BAR_W = 32

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
        span = self._max - self._min or 1.0
        ratio = max(0.0, min(1.0, (self._value - self._min) / span))
        filled = int(ratio * self._BAR_W)
        bar = "█" * filled + "░" * (self._BAR_W - filled)

        val_str = self._fmt(self._value)
        min_str = self._fmt(self._min)
        max_str = self._fmt(self._max)
        step_str = self._fmt(self._step)
        fine_str = self._fmt(self._fine)

        inner_w = self._BAR_W + 2
        pad = max(inner_w - len(min_str) - len(max_str), len(val_str) + 2)
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
        self._key = key
        self._type = type_
        self._default = default
        self._desc = description
        self._is_int = type_ == "int"
        self._min = min_val
        self._max = max_val
        self._step = step
        self._fine = fine_step
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
                self._init_val,
                self._min,
                self._max,
                self._step,
                self._fine,
                self._is_int,
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

# A RowSelected on the monitors table this soon after the editor closed is the
# second Enter of a double-press, not a request to open it again.
_REOPEN_GUARD_S = 0.3

# Idle rows: row key -> (label, shell.json key, description)
_IDLE_ROWS = {
    "idle_lock": ("Lock after (s)", "lock", "Seconds idle before the screen locks"),
    "idle_screensaver": (
        "Screensaver after (s)",
        "screensaver",
        "Seconds idle before the screensaver starts",
    ),
}


class HyprconfApp(App):
    CSS = APP_CSS

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        # Enter is handled exclusively via @on(DataTable.RowSelected) to avoid
        # double-calling action_edit_option when the DataTable's own binding
        # and the app-level binding both fire on the same keypress.
        Binding("space", "toggle_bool", "Toggle", show=True, priority=False),
        Binding("d", "reset_option", " Reset", show=True),
        Binding("n", "new_entry", " New", show=True),
        Binding("D", "delete_entry", " Delete", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("s", "save", "Save", show=True),
        Binding("/", "focus_search", "Filter", show=True),
        Binding("escape", "escape_action", "Clear", show=False),
        Binding("tab", "switch_focus", "Switch pane", show=False),
        Binding("h", "focus_sidebar", "Sidebar", show=False),
        Binding("l", "focus_table", "Table", show=False),
    ]

    def __init__(self, initial_section: str | None = None, slim: bool = False) -> None:
        super().__init__()
        self._initial_section = initial_section or "general"
        self._current_section = self._initial_section
        self._slim = slim
        self._row_keys: list[str] = []
        self._search_query = ""
        self._search_visible = False
        self._theme_name = _omarchy.current_theme()
        # pending[section][key] = value_str  — changes not yet written to disk
        self._pending: dict[str, dict[str, str]] = {}
        self._monitor_refresh_started = False
        # A blocking apply (hyprctl / omarchy-*) is running in a worker; Enter
        # on a row is ignored until it lands so it cannot be double-applied.
        self._busy = False
        self._monitor_editor_closed_at = 0.0

    # ── Layout ────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        session_note = (
            "session active" if HYPRLAND_ACTIVE else "no Hyprland session — defaults shown"
        )
        theme_info = f"[theme: {self._theme_name}]"

        with Horizontal(id="brand-bar"):
            yield Static("hyprconf ░░▒▓", id="brand-left")
            yield Static(session_note, id="brand-status")
            yield Static(theme_info, id="brand-right")

        with Horizontal(id="main-pane"):
            if not self._slim:
                with Vertical(id="sidebar"):
                    yield Input(placeholder="/ filter...", id="filter-input")
                    yield Static("─" * 20, id="sidebar-sep")
                    yield ListView(*self._build_list_items(), id="section-list")

            with Vertical(id="content"):
                yield Static(
                    f"  {SECTION_LABELS.get(self._initial_section, self._initial_section)}",
                    id="section-title",
                )
                yield Static("", id="pending-bar")
                yield DataTable(id="option-table", cursor_type="row", zebra_stripes=True)

        yield Footer()

    def _build_list_items(self) -> list[ListItem]:
        items: list[ListItem] = []
        for s in SECTION_ORDER:
            if s == "":
                items.append(
                    ListItem(Label("  ─────────────"), id="sep-divider", classes="sep-item")
                )
            else:
                safe_id = "sec-" + s.replace(".", "__")
                label = SECTION_LABELS.get(s, s)
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

    # ── Background work ───────────────────────────────────────────────────────

    def _in_background(self, work: Callable[[], object], done: Callable[[object], None]) -> None:
        """Run blocking *work* (hyprctl, omarchy-*) off the UI thread, then
        *done(result)* back on it.

        The event pump keeps running meanwhile, so keypresses land on a live
        UI instead of being queued and replayed against whatever is on top
        once the freeze ends. ``_busy`` blocks a second apply until the first
        has landed.
        """
        self._busy = True

        async def _job() -> None:
            try:
                result = await asyncio.to_thread(work)
            except Exception as exc:  # surface the failure, never crash the TUI
                self._busy = False
                self.notify(f"Failed: {exc}", severity="error")
                return
            self._busy = False
            done(result)

        self.run_worker(_job(), name="hyprconf-apply")

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
            self._fill_rules(table, "Window rule")
        elif section == "workspace_rules":
            self._fill_rules(table, "Workspace rule")
        elif section == "theme":
            self._fill_theme(table)
        elif section == "background":
            self._fill_background(table)
        elif section == "idle":
            self._fill_idle(table)
        elif section in OPTION_SCHEMA:
            self._fill_options(table, section)
        else:
            table.add_column("INFO")
            table.add_row(f"'{section}' is not a configurable section.")

        self._update_pending_bar()

    def _fill_options(self, table: DataTable, section: str) -> None:
        table.add_column("KEY", width=28)
        table.add_column("VALUE", width=22)
        table.add_column("DEFAULT", width=14)
        table.add_column("DESCRIPTION", width=50)
        q = self._search_query
        for key, (_type, default, desc) in OPTION_SCHEMA[section].items():
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
        table.add_column("NAME", width=14)
        table.add_column("DESCRIPTION", width=24)
        table.add_column("RESOLUTION", width=12)
        table.add_column("REFRESH Hz", width=10)
        table.add_column("SCALE", width=7)
        table.add_column("POSITION", width=10)
        table.add_column("WORKSPACE", width=10)
        table.add_column("VRR", width=5)
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
        table.add_column("TYPE", width=8)
        table.add_column("MODS", width=14)
        table.add_column("KEY", width=12)
        table.add_column("DISPATCH", width=18)
        table.add_column("ARGUMENT", width=30)
        table.add_column("DESCRIPTION", width=32)
        entries = _lib_keybinds_with_loc(KEYBINDS_CONF)
        q = self._search_query
        if not entries:
            table.add_row("(no keybinds found)", "", "", "", "", "")
            self._row_keys.append("")
            return
        for e in entries:
            row = (e.kind, e.mods or "—", e.key, e.dispatcher, e.args, e.description)
            if q and not any(q in part.lower() for part in row):
                continue
            table.add_row(*row)
            self._row_keys.append(f"__keybind__{e.file_path}::{e.line_idx}")

    def _fill_rules(self, table: DataTable, label: str) -> None:
        table.add_column("#", width=5)
        table.add_column("RULE", width=110)
        is_workspace = "workspace" in label.lower()
        entries = _lib_wksp_rules(HYPRLAND_CONF) if is_workspace else _lib_win_rules(HYPRLAND_CONF)
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

    def _fill_theme(self, table: DataTable) -> None:
        """Omarchy's themes (omarchy-theme-list); Enter applies via omarchy-theme-set."""
        table.add_column("THEME", width=34)
        table.add_column("STATUS", width=10)
        themes = _omarchy.list_themes()
        q = self._search_query
        if not themes:
            table.add_row("(no themes found — is Omarchy installed?)", "")
            return
        for name in themes:
            if q and q not in name.lower():
                continue
            table.add_row(name, " active" if name == self._theme_name else "")
            self._row_keys.append(name)

    def _fill_background(self, table: DataTable) -> None:
        """The active theme's backgrounds (the two dirs omarchy-theme-bg-next
        scans); Enter applies via omarchy-theme-bg-set."""
        table.add_column("BACKGROUND", width=70)
        table.add_column("STATUS", width=10)
        backgrounds = _omarchy.list_backgrounds()
        q = self._search_query
        if not backgrounds:
            table.add_row("(no backgrounds found for the current theme)", "")
            return
        current = _omarchy.current_background()
        home = str(_omarchy.home_dir())
        for p in backgrounds:
            shown = str(p)
            if shown.startswith(home + "/"):
                shown = "~" + shown[len(home) :]
            if q and q not in shown.lower():
                continue
            table.add_row(shown, " active" if p == current else "")
            self._row_keys.append(f"__bg__{p}")

    def _fill_idle(self, table: DataTable) -> None:
        """Omarchy's idle timeouts (shell.json) and its stay-awake toggle."""
        table.add_column("SETTING", width=24)
        table.add_column("VALUE", width=10)
        table.add_column("DESCRIPTION", width=60)
        timeouts = _omarchy.idle_timeouts()
        q = self._search_query
        for rk, (label, key, desc) in _IDLE_ROWS.items():
            if q and q not in label.lower() and q not in desc.lower():
                continue
            table.add_row(label, str(timeouts[key]), f"{desc} (shell.json idle.{key})")
            self._row_keys.append(rk)
        label = "Stay awake"
        desc = "Suspend idle lock & screensaver (omarchy-toggle-idle); Enter toggles"
        if not q or q in label.lower() or q in desc.lower():
            table.add_row(label, "on" if _omarchy.stay_awake() else "off", desc)
            self._row_keys.append("idle_stay_awake")

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
        rk = self._row_keys[row_idx] if 0 <= row_idx < len(self._row_keys) else ""

        # ── Keybinds ─────────────────────────────────────────────────────────
        if section == "keybinds":
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
                    key=entry.key if entry else "",
                    dispatcher=entry.dispatcher if entry else "",
                    args=entry.args if entry else "",
                    description=entry.description if entry else "",
                )

                def _handle_kb_edit(result, _fp=Path(file_path), _li=line_idx):
                    if result is None:
                        return
                    kind, mods, key, disp, args, desc = result
                    ok = _lib_update_keybind(_fp, _li, kind, mods, key, disp, args, desc)
                    self.notify(
                        "Keybind updated" if ok else "Failed to update keybind",
                        severity="information" if ok else "error",
                    )
                    self._load_section(section)

                self.push_screen(scr, _handle_kb_edit)
            return

        # ── Window / workspace rules ──────────────────────────────────────────
        if section in ("window_rules", "workspace_rules"):
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
                    self.notify(
                        "Rule updated" if ok else "Failed to update rule",
                        severity="information" if ok else "error",
                    )
                    self._load_section(section)

                self.push_screen(scr, _handle_rule_edit)
            return

        # Everything below shells out to apply; one at a time.
        if self._busy:
            return

        # ── Monitors ─────────────────────────────────────────────────────────
        if section == "monitors":
            # The second Enter of a double-press arrives on this table the
            # instant the editor pops; it must not open a fresh one.
            if time.monotonic() - self._monitor_editor_closed_at < _REOPEN_GUARD_S:
                return
            if rk:
                monitor_name = rk
                monitors = get_monitors()
                mon_data = next((m for m in monitors if m.get("name") == monitor_name), None)
                if mon_data is None:
                    self.notify(
                        f"Could not retrieve data for {monitor_name}",
                        severity="warning",
                    )
                    return

                # Read persisted extras (bitdepth, cm, sdrbrightness, etc.) from monitors.lua
                file_configs = _lib_monitor_configs()
                file_mc = next((mc for mc in file_configs if mc.name == monitor_name), None)
                file_extras = file_mc.extras if file_mc else ""
                file_position = file_mc.position if file_mc else ""

                # Snapshot ALL monitors now (before the edit dialog opens) so
                # the apply can detect which neighbours need adjusting.
                monitors_snapshot = monitors

                def handle_monitor(keyword: str | None) -> None:
                    self._monitor_editor_closed_at = time.monotonic()
                    if not keyword:
                        return
                    self._in_background(
                        lambda: _apply_monitor_keyword(keyword, mon_data, monitors_snapshot),
                        self._after_monitor_apply,
                    )

                self.push_screen(
                    MonitorEditScreen(mon_data, file_extras, file_position), handle_monitor
                )
            return

        # ── Theme (omarchy-theme-set) ─────────────────────────────────────────
        if section == "theme":
            if rk:
                self._in_background(
                    lambda: (rk, _omarchy.set_theme(rk)),
                    self._after_theme_set,
                )
            return

        # ── Background (omarchy-theme-bg-set) ────────────────────────────────
        if section == "background":
            if rk.startswith("__bg__"):
                path = rk[6:]
                self._in_background(
                    lambda: (path, _omarchy.set_background(path)),
                    self._after_background_set,
                )
            return

        # ── Idle & lock (shell.json / omarchy-toggle-idle) ───────────────────
        if section == "idle":
            if rk == "idle_stay_awake":
                self._in_background(_omarchy.toggle_stay_awake, self._after_stay_awake_toggle)
            elif rk in _IDLE_ROWS:
                label, key, desc = _IDLE_ROWS[rk]
                current = str(_omarchy.idle_timeouts()[key])

                def _handle_timeout(value: str | None, _key=key) -> None:
                    if value is None or value == current:
                        return
                    self._in_background(
                        lambda: _omarchy.set_idle_timeouts(**{_key: int(value)}),
                        lambda ok, _k=_key, _v=value: self._after_idle_set(_k, _v, ok),
                    )

                self.push_screen(
                    NumericEditScreen(
                        "idle",
                        key,
                        current,
                        "int",
                        str(_omarchy.IDLE_DEFAULTS[key]),
                        desc,
                        0,
                        _omarchy.IDLE_MAX_S,
                        60,
                        1,
                    ),
                    _handle_timeout,
                )
            return

        # ── All OPTION_SCHEMA sections ────────────────────────────────────────
        self.action_edit_option()

    # ── Completion callbacks for background applies (UI thread) ──────────────

    def _after_monitor_apply(self, result: object) -> None:
        msg, severity = result  # type: ignore[misc]
        self._monitor_editor_closed_at = time.monotonic()
        self.notify(msg, severity=severity)
        self._refresh_monitors()

    def _after_theme_set(self, result: object) -> None:
        name, ok = result  # type: ignore[misc]
        if ok:
            self._theme_name = name
            self.query_one("#brand-right", Static).update(f"[theme: {name}]")
            self.notify(f"Theme applied: {name}")
        else:
            self.notify(f"omarchy-theme-set failed for {name}", severity="error")
        self._load_section("theme")

    def _after_background_set(self, result: object) -> None:
        path, ok = result  # type: ignore[misc]
        self.notify(
            f"Background set: {Path(path).name}" if ok else f"omarchy-theme-bg-set failed: {path}",
            severity="information" if ok else "error",
        )
        self._load_section("background")

    def _after_stay_awake_toggle(self, result: object) -> None:
        if result is None:
            self.notify("omarchy-toggle-idle failed", severity="error")
        else:
            self.notify("Stay awake: on" if result else "Stay awake: off")
        self._load_section("idle")

    def _after_idle_set(self, key: str, value: str, ok: object) -> None:
        self.notify(
            f"idle.{key} = {value}s" if ok else f"Failed to write shell.json (idle.{key})",
            severity="information" if ok else "error",
        )
        self._load_section("idle")

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_new_entry(self) -> None:
        """Open a modal to add a new entry for the current file-based section."""
        section = self._current_section
        if section == "keybinds":

            def _handle(result) -> None:
                if result is None:
                    return
                kind, mods, key, disp, args, desc = result
                # o.bind needs a description for Omarchy's SUPER+K menu; fall
                # back to the command itself rather than a blank entry.
                desc = desc or f"{disp} {args}".strip()
                ok = _lib_add_keybind(kind, mods, key, disp, args, KEYBINDS_CONF, desc)
                self.notify(
                    "Keybind added" if ok else "Failed to add keybind",
                    severity="information" if ok else "error",
                )
                self._load_section(section)

            self.push_screen(KeybindEditScreen(), _handle)

        elif section == "window_rules":

            def _handle(result) -> None:
                if result is None:
                    return
                rule_type, action_or_id, filters_or_opts = result
                ok = _lib_add_win_rule(action_or_id, filters_or_opts)
                self.notify(
                    "Window rule added" if ok else "Failed to add rule",
                    severity="information" if ok else "error",
                )
                self._load_section(section)

            self.push_screen(RuleEditScreen(rule_type="window"), _handle)

        elif section == "workspace_rules":

            def _handle(result) -> None:
                if result is None:
                    return
                rule_type, wksp_id, opts = result
                ok = _lib_add_wksp_rule(wksp_id, opts)
                self.notify(
                    "Workspace rule added" if ok else "Failed to add rule",
                    severity="information" if ok else "error",
                )
                self._load_section(section)

            self.push_screen(RuleEditScreen(rule_type="workspace"), _handle)

        elif section == "monitors":
            if self._busy:
                return
            # New monitor: open MonitorEditScreen with an empty/placeholder dict
            blank = {
                "name": "",
                "description": "",
                "width": 1920,
                "height": 1080,
                "refreshRate": 60.0,
                "scale": 1.0,
                "x": 0,
                "y": 0,
                "vrr": False,
                "availableModes": [],
            }
            scr = MonitorEditScreen(blank, "", "auto")

            def _handle(keyword: str | None) -> None:
                self._monitor_editor_closed_at = time.monotonic()
                if not keyword:
                    return
                self._in_background(
                    lambda: _apply_monitor_keyword(keyword, None, []),
                    self._after_monitor_apply,
                )

            self.push_screen(scr, _handle)
        else:
            self.notify(f"New entry not supported for: {section}", severity="warning")

    def action_delete_entry(self) -> None:
        """Delete the currently selected row from its config file."""
        section = self._current_section
        table = self.query_one("#option-table", DataTable)
        row_idx = table.cursor_row
        if row_idx < 0 or row_idx >= len(self._row_keys):
            return
        rk = self._row_keys[row_idx]

        def _do_delete(file_path: Path, line_idx: int, label: str) -> None:
            ok = _lib_delete_line(file_path, line_idx)
            self.notify(
                f"{label} deleted" if ok else f"Failed to delete {label}",
                severity="information" if ok else "error",
            )
            self._load_section(section)

        if rk.startswith("__keybind__"):
            payload = rk[11:]
            fp, li = payload.rsplit("::", 1)
            _do_delete(Path(fp), int(li), "Keybind")

        elif rk.startswith("__rule__"):
            payload = rk[8:]
            fp, li = payload.rsplit("::", 1)
            _do_delete(Path(fp), int(li), "Rule")

        elif section == "monitors" and rk:
            # Delete monitor from monitors.lua by name
            mon_cfg = _lib_monitor_configs(MONITORS_FILE)
            mc = next((m for m in mon_cfg if m.name == rk), None)
            if mc:
                ok = _lib_delete_monitor(mc.file_path, mc.line_idx)
                # Also turn it off live if a session is active
                _lib_disable_monitor(rk)
                self.notify(
                    f"Monitor {rk} removed" if ok else "Failed to remove monitor",
                    severity="information" if ok else "error",
                )
                self._refresh_monitors()
            else:
                self.notify(f"Monitor {rk!r} not found in monitors.lua", severity="warning")
        else:
            self.notify("Nothing to delete here.", severity="warning")

    def action_edit_option(self) -> None:
        section = self._current_section
        if section not in OPTION_SCHEMA:
            return
        table = self.query_one("#option-table", DataTable)
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

        def handle_result(new_value: str | None) -> None:
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
                NumericEditScreen(section, key, current, type_, default, desc, lo, hi, step, fine),
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
        table = self.query_one("#option-table", DataTable)
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
        table = self.query_one("#option-table", DataTable)
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
        status = "applied" if applied else "config-only"

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
        description="hyprconf TUI — Hyprland configuration for an Omarchy system",
        prog="hyprconf",
    )
    parser.add_argument(
        "--section",
        "-s",
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
                f"Unknown section: {args.section}\nValid sections: {', '.join(all_sections)}"
            )

    # --slim without --section: show slim view at default section
    slim = args.slim or (section is not None)

    HyprconfApp(initial_section=section, slim=slim).run()


if __name__ == "__main__":
    main()
