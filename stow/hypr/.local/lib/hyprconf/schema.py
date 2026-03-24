"""
hyprconf.schema — Canonical option schema for all Hyprland configuration keys.

This module is the SINGLE SOURCE OF TRUTH for every configurable option that
hyprconf exposes.  Both the CLI (get/set/configure) and the TUI import from
here; neither may define its own schema.

──────────────────────────────────────────────────────────────────────────────
AI-CHANGELOG INTERFACE
──────────────────────────────────────────────────────────────────────────────
When a new Hyprland release ships with changed configuration keys:

1.  Obtain the changelog / diff from https://github.com/hyprwm/Hyprland/releases
2.  Run:  hyprconf schema dump > schema_before.json
3.  Identify affected entries in OPTION_SCHEMA below (each entry is a tuple:
    (type_str, default_str, description)).
4.  Add / rename / remove entries as required.
5.  Run:  hyprconf schema dump > schema_after.json
        diff schema_before.json schema_after.json
6.  If a section or key is renamed, also update SECTION_ORDER and SECTION_LABELS.
7.  Run:  hyprconf schema validate   to catch type/format issues.

Option types understood by hyprconf:
    int        — integer (may be negative)
    float      — floating-point number
    bool       — true/false (also accepts yes/no/on/off/0/1)
    str        — arbitrary string (no validation)
    color      — 0xAARRGGBB hex color
    gradient   — space-separated colors + optional angle  e.g. "0xff... 0xff... 45deg"
    vec2       — two space-separated numbers  e.g. "0 0"
    enum:a,b,c — one of the listed comma-separated values
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from typing import Optional

_HEX_COLOR_RE  = re.compile(r"^0x[0-9a-fA-F]{6,8}$")
_HASH_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6,8}$")

# ── Type alias ────────────────────────────────────────────────────────────────
# (type_str, default_str, description)
OptionMeta = tuple[str, str, str]

# ── Main schema ───────────────────────────────────────────────────────────────
# Layout:  section_name -> { key: (type, default, description) }
# Subsections use dot-notation:  "decoration.blur", "input.touchpad", etc.
# hyprctl keyword path uses colon-notation:  decoration:blur:enabled

OPTION_SCHEMA: dict[str, dict[str, OptionMeta]] = {

    # ── general ──────────────────────────────────────────────────────────────
    "general": {
        "border_size":               ("int",     "1",        "Border width around windows (px)"),
        "gaps_in":                   ("int",     "5",        "Gap between tiled windows"),
        "gaps_out":                  ("int",     "20",       "Gap between windows and monitor edges"),
        "float_gaps":                ("int",     "0",        "Gap for floating windows (-1 = use gaps_out)"),
        "gaps_workspaces":           ("int",     "0",        "Extra gap between workspaces (stacks with gaps_out)"),
        "col.inactive_border":       ("gradient","0xff444444","Inactive window border color"),
        "col.active_border":         ("gradient","0xffffffff","Active window border color"),
        "col.nogroup_border":        ("gradient","0xffffaaff","Ungroupable window inactive border"),
        "col.nogroup_border_active": ("gradient","0xffff00ff","Ungroupable window active border"),
        "layout":                    ("enum:dwindle,master,scrolling,monocle",
                                               "dwindle",  "Active layout algorithm"),
        "no_focus_fallback":         ("bool",    "false",    "Do not fall back focus to next window on loss"),
        "resize_on_border":          ("bool",    "false",    "Allow resizing by dragging borders/gaps"),
        "extend_border_grab_area":   ("int",     "15",       "Extra grab area around border (requires resize_on_border)"),
        "hover_icon_on_border":      ("bool",    "true",     "Show resize cursor when hovering border"),
        "allow_tearing":             ("bool",    "false",    "Master switch for allowing screen tearing"),
        "resize_corner":             ("int",     "0",        "Force resize from a corner: 1-4 clockwise, 0=off"),
        "modal_parent_blocking":     ("bool",    "true",     "Modal parents are interactive while child is open"),
    },

    # ── general.snap ─────────────────────────────────────────────────────────
    "general.snap": {
        "enabled":        ("bool", "false", "Enable snapping for floating windows"),
        "window_gap":     ("int",  "10",    "Min gap (px) between windows before snapping"),
        "monitor_gap":    ("int",  "10",    "Min gap (px) between window and monitor edge"),
        "border_overlap": ("bool", "false", "Snap allowing only one border-width of space"),
        "respect_gaps":   ("bool", "false", "Snapping respects gaps_in value"),
    },

    # ── decoration ───────────────────────────────────────────────────────────
    "decoration": {
        "rounding":              ("int",   "0",    "Corner rounding radius (px)"),
        "rounding_power":        ("float", "2.0",  "Rounding curve: 2.0=circle, 4.0=squircle [1.0-10.0]"),
        "active_opacity":        ("float", "1.0",  "Active window opacity [0.0-1.0]"),
        "inactive_opacity":      ("float", "1.0",  "Inactive window opacity [0.0-1.0]"),
        "fullscreen_opacity":    ("float", "1.0",  "Fullscreen window opacity [0.0-1.0]"),
        "dim_modal":             ("bool",  "true", "Dim parents of modal windows"),
        "dim_inactive":          ("bool",  "false","Dim inactive windows"),
        "dim_strength":          ("float", "0.5",  "Inactive dim amount [0.0-1.0]"),
        "dim_special":           ("float", "0.2",  "Dim when special workspace is open [0.0-1.0]"),
        "dim_around":            ("float", "0.4",  "Dim amount for dim_around window rule [0.0-1.0]"),
        "screen_shader":         ("str",   "",     "Path to custom GLSL screen shader (empty=none)"),
        "border_part_of_window": ("bool",  "true", "Whether window border is part of the window geometry"),
    },

    # ── decoration.blur ───────────────────────────────────────────────────────
    "decoration.blur": {
        "enabled":            ("bool",  "true",   "Enable kawase window background blur"),
        "size":               ("int",   "8",      "Blur distance (kernel radius)"),
        "passes":             ("int",   "1",      "Blur passes — more = better quality at GPU cost"),
        "ignore_opacity":     ("bool",  "true",   "Blur ignores window opacity setting"),
        "new_optimizations":  ("bool",  "true",   "Enable blur optimizations (recommended)"),
        "xray":               ("bool",  "false",  "Floating windows ignore tiled in blur"),
        "noise":              ("float", "0.0117", "Blur noise amount [0.0-1.0]"),
        "contrast":           ("float", "0.8916", "Blur contrast modulation [0.0-2.0]"),
        "brightness":         ("float", "0.8172", "Blur brightness modulation [0.0-2.0]"),
        "vibrancy":           ("float", "0.1696", "Blur color saturation increase [0.0-1.0]"),
        "vibrancy_darkness":  ("float", "0.0",    "Vibrancy effect on dark areas [0.0-1.0]"),
        "special":            ("bool",  "false",  "Blur behind special workspace (expensive)"),
        "popups":             ("bool",  "false",  "Blur popups (e.g. right-click menus)"),
        "popups_ignorealpha": ("float", "0.2",    "Blur popups below this opacity threshold"),
    },

    # ── decoration.shadow ─────────────────────────────────────────────────────
    "decoration.shadow": {
        "enabled":       ("bool",  "true",       "Enable drop shadows"),
        "range":         ("int",   "4",          "Shadow range/size (px)"),
        "render_power":  ("int",   "3",          "Shadow falloff power [1-4]"),
        "sharp":         ("bool",  "false",      "Sharp shadows (equivalent to infinite render_power)"),
        "ignore_window": ("bool",  "true",       "Do not render shadow behind window itself"),
        "color":         ("color", "0xee1a1a1a", "Shadow color (alpha controls opacity)"),
        "color_inactive":("color", "unset",      "Inactive shadow color (falls back to color)"),
        "offset":        ("vec2",  "0 0",        "Shadow rendering offset (x y)"),
        "scale":         ("float", "1.0",        "Shadow scale [0.0-1.0]"),
    },

    # ── animations ────────────────────────────────────────────────────────────
    "animations": {
        "enabled":              ("bool", "true",  "Enable animations globally"),
        "workspace_wraparound": ("bool", "false", "Enable workspace wraparound animation"),
    },

    # ── input ─────────────────────────────────────────────────────────────────
    "input": {
        "kb_layout":                   ("str",            "us",       "XKB keyboard layout (e.g. us, gb, de)"),
        "kb_variant":                  ("str",            "",         "XKB keyboard variant"),
        "kb_model":                    ("str",            "",         "XKB keyboard model"),
        "kb_options":                  ("str",            "",         "XKB keyboard options (e.g. caps:escape)"),
        "kb_rules":                    ("str",            "",         "XKB keyboard rules"),
        "numlock_by_default":          ("bool",           "false",    "Enable numlock by default"),
        "resolve_binds_by_sym":        ("bool",           "false",    "Keybinds act on symbol vs first layout"),
        "repeat_rate":                 ("int",            "25",       "Key repeat rate (repeats/second)"),
        "repeat_delay":                ("int",            "600",      "Key repeat delay (ms)"),
        "sensitivity":                 ("float",          "0.0",      "Mouse sensitivity [-1.0 to 1.0]"),
        "accel_profile":               ("enum:adaptive,flat,custom,",
                                                          "adaptive", "Cursor acceleration profile"),
        "force_no_accel":              ("bool",           "false",    "Force raw mouse input (no acceleration)"),
        "left_handed":                 ("bool",           "false",    "Swap left and right mouse buttons"),
        "scroll_method":               ("enum:2fg,edge,on_button_down,no_scroll,",
                                                          "",         "Scroll method"),
        "scroll_factor":               ("float",          "1.0",      "External mouse scroll multiplier"),
        "scroll_button":               ("int",            "0",        "Scroll button ID (0=default)"),
        "scroll_button_lock":          ("bool",           "false",    "Lock scroll button (toggle instead of hold)"),
        "natural_scroll":              ("bool",           "false",    "Invert scroll direction"),
        "follow_mouse":                ("enum:0,1,2,3",   "1",        "Focus follows cursor [0=disabled,1=full,2=loose,3=fullOnRelease]"),
        "focus_on_close":              ("enum:0,1",       "0",        "Focus on close: 0=next candidate, 1=under cursor"),
        "mouse_refocus":               ("bool",           "true",     "Mouse focus crosses window boundaries"),
        "float_switch_override_focus": ("enum:0,1,2",     "1",        "Focus follows tiled/float switch [0-2]"),
        "special_fallthrough":         ("bool",           "false",    "Float-only special workspace won't block regular"),
        "off_window_axis_events":      ("enum:0,1,2,3",   "1",        "Off-window axis events [0=ignore,1=send,2=force,3=noblur]"),
        "emulate_discrete_scroll":     ("enum:0,1,2",     "1",        "Emulate discrete scroll [0=off,1=always,2=auto]"),
    },

    # ── input.touchpad ────────────────────────────────────────────────────────
    "input.touchpad": {
        "disable_while_typing":    ("bool",       "true",  "Disable touchpad while typing"),
        "natural_scroll":          ("bool",       "false", "Touchpad natural scroll"),
        "scroll_factor":           ("float",      "1.0",   "Touchpad scroll multiplier"),
        "middle_button_emulation": ("bool",       "false", "LMB+RMB simultaneously = middle click"),
        "clickfinger_behavior":    ("bool",       "false", "1/2/3-finger tap = LMB/RMB/MMB"),
        "tap-to-click":            ("bool",       "true",  "Tapping = click"),
        "drag_lock":               ("enum:0,1,2", "0",     "Drag lock: 0=off, 1=timeout, 2=sticky"),
        "tap-and-drag":            ("bool",       "true",  "Tap and drag enabled"),
        "flip_x":                  ("bool",       "false", "Invert touchpad horizontal movement"),
        "flip_y":                  ("bool",       "false", "Invert touchpad vertical movement"),
    },

    # ── gestures ──────────────────────────────────────────────────────────────
    "gestures": {
        "workspace_swipe_distance":                 ("int",   "300",  "Swipe distance (px)"),
        "workspace_swipe_touch":                    ("bool",  "false","Enable touchscreen edge swipe"),
        "workspace_swipe_invert":                   ("bool",  "true", "Invert touchpad swipe direction"),
        "workspace_swipe_touch_invert":             ("bool",  "false","Invert touchscreen swipe direction"),
        "workspace_swipe_min_speed_to_force":       ("int",   "30",   "Min speed to force workspace switch (px/timepoint)"),
        "workspace_swipe_cancel_ratio":             ("float", "0.5",  "Swipe threshold ratio to commit [0.0-1.0]"),
        "workspace_swipe_create_new":               ("bool",  "true", "Swipe right on last workspace creates new"),
        "workspace_swipe_direction_lock":           ("bool",  "true", "Lock swipe direction after threshold"),
        "workspace_swipe_direction_lock_threshold": ("int",   "10",   "Distance before direction lock (px)"),
        "workspace_swipe_forever":                  ("bool",  "false","Swipe continues past neighboring workspace"),
        "workspace_swipe_use_r":                    ("bool",  "false","Use r prefix instead of m for workspace target"),
        "close_max_timeout":                        ("int",   "1000", "Max close gesture timeout (ms)"),
    },

    # ── group ─────────────────────────────────────────────────────────────────
    "group": {
        "auto_group":                ("bool",       "true",       "Auto-group new windows into focused unlocked group"),
        "insert_after_current":      ("bool",       "true",       "New group windows spawn after current (vs at end)"),
        "focus_removed_window":      ("bool",       "true",       "Focus window moved out of a group"),
        "drag_into_group":           ("enum:0,1,2", "1",          "Allow dragging window into group [0=off,1=on,2=groupbar]"),
        "col.border_active":         ("gradient",   "0x66ffff00", "Active group border color"),
        "col.border_inactive":       ("gradient",   "0x66777700", "Inactive group border color"),
        "col.border_locked_active":  ("gradient",   "0x66ff5500", "Active locked group border color"),
        "col.border_locked_inactive":("gradient",   "0x66775500", "Inactive locked group border color"),
    },

    # ── group.groupbar ────────────────────────────────────────────────────────
    "group.groupbar": {
        "enabled":              ("bool",     "true",       "Enable groupbars"),
        "font_size":            ("int",      "8",          "Groupbar font size"),
        "gradients":            ("bool",     "false",      "Enable groupbar gradients"),
        "height":               ("int",      "14",         "Groupbar height (px)"),
        "stacked":              ("bool",     "false",      "Render groupbar as vertical stack"),
        "render_titles":        ("bool",     "true",       "Render titles in groupbar"),
        "scrolling":            ("bool",     "true",       "Scroll in groupbar changes active window"),
        "rounding":             ("int",      "1",          "Groupbar indicator rounding"),
        "rounding_power":       ("float",    "2.0",        "Groupbar rounding curve [1.0-10.0]"),
        "text_color":           ("color",    "0xffffffff", "Groupbar title text color"),
        "col.active":           ("gradient", "0x66ffff00", "Active groupbar background"),
        "col.inactive":         ("gradient", "0x66777700", "Inactive groupbar background"),
        "col.locked_active":    ("gradient", "0x66ff5500", "Active locked groupbar background"),
        "col.locked_inactive":  ("gradient", "0x66775500", "Inactive locked groupbar background"),
    },

    # ── misc ──────────────────────────────────────────────────────────────────
    "misc": {
        "disable_hyprland_logo":        ("bool",          "false",   "Disable random Hyprland logo background"),
        "disable_splash_rendering":     ("bool",          "false",   "Disable splash rendering (requires monitor reload)"),
        "force_default_wallpaper":      ("enum:-1,0,1,2", "-1",      "Force default wallpaper: -1=auto, 0/1=off, 2=on"),
        "vfr":                          ("bool",          "true",    "Variable frame rate — highly recommended"),
        "vrr":                          ("enum:0,1,2,3",  "0",       "Adaptive Sync: 0=off, 1=on, 2=fullscreen, 3=fs+video"),
        "mouse_move_enables_dpms":      ("bool",          "false",   "Mouse movement wakes displays from DPMS off"),
        "key_press_enables_dpms":       ("bool",          "false",   "Key press wakes displays from DPMS off"),
        "animate_manual_resizes":       ("bool",          "false",   "Animate manual window resize/move"),
        "animate_mouse_windowdragging": ("bool",          "false",   "Animate windows being dragged by mouse"),
        "disable_autoreload":           ("bool",          "false",   "Disable auto-reload on config file save"),
        "enable_swallow":               ("bool",          "false",   "Enable window swallowing"),
        "swallow_regex":                ("str",           "",        "Class regex for windows that swallow (usually terminal)"),
        "swallow_exception_regex":      ("str",           "",        "Title regex for windows that should NOT be swallowed"),
        "focus_on_activate":            ("bool",          "false",   "Focus app on activate request"),
        "mouse_move_focuses_monitor":   ("bool",          "true",    "Mouse into different monitor focuses it"),
        "allow_session_lock_restore":   ("bool",          "false",   "Allow restarting crashed lockscreen app"),
        "background_color":             ("color",         "0x111111","Background color (requires disable_hyprland_logo)"),
        "close_special_on_empty":       ("bool",          "true",    "Close special workspace when last window removed"),
        "initial_workspace_tracking":   ("enum:0,1,2",    "1",       "Open windows on invocation workspace [0=off,1=once,2=persistent]"),
        "middle_click_paste":           ("bool",          "true",    "Enable middle-click paste (primary selection)"),
        "render_unfocused_fps":         ("int",           "15",      "FPS limit for unfocused background windows"),
        "disable_xdg_env_checks":       ("bool",          "false",   "Suppress XDG environment warning on startup"),
        "lockdead_screen_delay":        ("int",           "1000",    "Delay (ms) before lockdead screen appears"),
    },

    # ── binds ─────────────────────────────────────────────────────────────────
    "binds": {
        "pass_mouse_when_bound":             ("bool",     "false","Pass mouse events when a keybind is triggered"),
        "scroll_event_delay":                ("int",      "300",  "Delay (ms) between scroll events for binds"),
        "workspace_back_and_forth":          ("bool",     "false","Re-activating current workspace switches to previous"),
        "hide_special_on_workspace_change":  ("bool",     "false","Hide special workspace on workspace change"),
        "allow_workspace_cycles":            ("bool",     "false","Enable workspace cycling via previous workspace"),
        "workspace_center_on":               ("enum:0,1", "0",    "Workspace switch centers on: 0=workspace, 1=last window"),
        "focus_preferred_method":            ("enum:0,1", "0",    "Focus method: 0=history, 1=shared edge length"),
        "ignore_group_lock":                 ("bool",     "false","moveintogroup/out dispatchers ignore group locks"),
        "movefocus_cycles_fullscreen":       ("bool",     "false","movefocus on fullscreen cycles fullscreen state"),
        "movefocus_cycles_groupfirst":       ("bool",     "false","movefocus cycles group windows before leaving group"),
        "window_direction_monitor_fallback": ("bool",     "true", "Moving window/focus over edge jumps to next monitor"),
        "disable_keybind_grabbing":          ("bool",     "false","Apps cannot disable keybinds (e.g. for VMs)"),
        "allow_pin_fullscreen":              ("bool",     "false","Allow pinning fullscreen windows"),
        "drag_threshold":                    ("int",      "0",    "Mouse movement threshold for drag (0=mousedown)"),
    },

    # ── cursor ────────────────────────────────────────────────────────────────
    "cursor": {
        "no_hardware_cursors":      ("enum:0,1,2", "2",    "HW cursors: 0=use, 1=never, 2=auto"),
        "min_refresh_rate":         ("int",         "24",   "Min refresh rate for cursor animations"),
        "hotspot_padding":          ("int",         "1",    "Padding (px) between screen edges and cursor"),
        "inactive_timeout":         ("float",       "0",    "Hide cursor after N seconds idle (0=never)"),
        "no_warps":                 ("bool",        "false","Disable cursor warps on focus/keybinds"),
        "persistent_warps":         ("bool",        "false","Cursor returns to last position in refocused window"),
        "warp_on_change_workspace": ("enum:0,1,2",  "0",    "Warp cursor on workspace change [0=off,1=on,2=force]"),
        "default_monitor":          ("str",         "",     "Monitor to place cursor on startup"),
        "zoom_factor":              ("float",       "1.0",  "Zoom magnification factor (1.0=none)"),
        "zoom_rigid":               ("bool",        "false","Zoom follows cursor rigidly vs loosely"),
        "enable_hyprcursor":        ("bool",        "true", "Enable hyprcursor support"),
        "hide_on_key_press":        ("bool",        "false","Hide cursor until mouse moves after keypress"),
        "hide_on_touch":            ("bool",        "true", "Hide cursor until mouse input after touch"),
    },

    # ── render ────────────────────────────────────────────────────────────────
    "render": {
        "direct_scanout":             ("enum:0,1,2","0",   "Direct scanout: 0=off, 1=on, 2=auto (game content)"),
        "expand_undersized_textures": ("bool",       "true","Expand undersized textures along edge vs stretch"),
        "cm_fs_passthrough":          ("enum:0,1,2", "2",   "HDR passthrough for fullscreen: 0=off, 1=always, 2=hdr"),
        "cm_enabled":                 ("bool",       "true","Enable color management pipeline"),
    },

    # ── opengl ────────────────────────────────────────────────────────────────
    "opengl": {
        "nvidia_anti_flicker": ("bool","true","Reduce Nvidia flickering (may drop FPS on weak GPUs)"),
    },

    # ── xwayland ──────────────────────────────────────────────────────────────
    "xwayland": {
        "enabled":              ("bool","true",  "Allow X11 / XWayland applications"),
        "use_nearest_neighbor": ("bool","true",  "Pixelated (vs blurry) scaling for XWayland apps"),
        "force_zero_scaling":   ("bool","false", "Force 1x scale for all XWayland apps"),
    },

    # ── dwindle ───────────────────────────────────────────────────────────────
    "dwindle": {
        "pseudotile":                    ("bool",      "false","Maintain size ratios in tiled mode"),
        "force_split":                   ("enum:0,1,2","0",   "Force split direction: 0=auto, 1=left/top, 2=right/bottom"),
        "preserve_split":                ("bool",      "false","Preserve split direction when swapping"),
        "smart_split":                   ("bool",      "false","Smart split based on cursor position"),
        "smart_resizing":                ("bool",      "true", "Smart resize selects the correct split"),
        "permanent_direction_override":  ("bool",      "false","Do not reset direction override on window focus"),
        "use_active_for_splits":         ("bool",      "true", "Use active window as basis for splits"),
        "default_split_ratio":           ("float",     "1.0",  "Default split ratio (1.0 = equal)"),
    },

    # ── master ────────────────────────────────────────────────────────────────
    "master": {
        "allow_small_split":    ("bool",      "false",        "Allow master to be split further"),
        "special_scale_factor": ("float",     "0.8",          "Scale for master in special workspaces [0.0-1.0]"),
        "mfact":                ("float",     "0.55",         "Master area size factor [0.0-1.0]"),
        "new_client_position":  ("enum:before_current,after_current,beginning,end,inherit_fullscreen",
                                              "after_current","Where new slave windows open"),
        "new_status":           ("enum:master,slave,inherit_fullscreen",
                                              "slave",         "New window default status"),
        "inherit_fullscreen":   ("bool",      "true",         "New windows inherit fullscreen state of focused"),
        "smart_resizing":       ("bool",      "true",         "Smart resize selects correct split"),
        "drop_at_cursor":       ("bool",      "true",         "Dragged window drops at cursor position"),
    },
}

# ── Section display order (sidebar) ──────────────────────────────────────────
# Empty string = visual separator
SECTION_ORDER: list[str] = [
    "monitors", "keybinds",
    "window_rules", "workspace_rules",
    "hyprlock", "hypridle", "hyprpaper",
    "theme",
    "hardware",
    "",
    "general", "general.snap",
    "decoration", "decoration.blur", "decoration.shadow",
    "animations",
    "input", "input.touchpad",
    "gestures",
    "group", "group.groupbar",
    "misc", "binds", "cursor",
    "render", "opengl", "xwayland",
    "dwindle", "master",
]

# ── Section display labels ────────────────────────────────────────────────────
SECTION_LABELS: dict[str, str] = {
    "general":          "General",
    "general.snap":     "  Snap",
    "decoration":       "Decoration",
    "decoration.blur":  "  Blur",
    "decoration.shadow":"  Shadow",
    "animations":       "Animations",
    "input":            "Input",
    "input.touchpad":   "  Touchpad",
    "gestures":         "Gestures",
    "group":            "Group",
    "group.groupbar":   "  Groupbar",
    "misc":             "Misc",
    "binds":            "Binds",
    "cursor":           "Cursor",
    "render":           "Render",
    "opengl":           "OpenGL",
    "xwayland":         "XWayland",
    "dwindle":          "Dwindle",
    "master":           "Master",
    "monitors":         "Monitors",
    "keybinds":         "Keybinds",
    "window_rules":     "Win. Rules",
    "workspace_rules":  "Wksp. Rules",
    "hyprlock":         "hyprlock",
    "hypridle":         "hypridle",
    "hyprpaper":        "hyprpaper",
    "theme":            "Theme",
    "hardware":         "Hardware",
}

# ── Helper functions ──────────────────────────────────────────────────────────

def get_section_keys(section: str) -> list[str]:
    """Return ordered list of option keys for a section, or [] if unknown."""
    return list(OPTION_SCHEMA.get(section, {}).keys())


def get_option_meta(section: str, key: str) -> Optional[OptionMeta]:
    """Return (type, default, description) for section:key, or None if unknown."""
    return OPTION_SCHEMA.get(section, {}).get(key)


def get_all_sections() -> list[str]:
    """Return all configurable sections (no separators, no special sections)."""
    return list(OPTION_SCHEMA.keys())


def validate_value(type_str: str, value: str) -> tuple[bool, str]:
    """Validate a value against its type string.

    Returns (ok, error_message).  error_message is empty when ok is True.
    """
    v = value.strip()
    if type_str == "int":
        try:
            int(v)
            return True, ""
        except ValueError:
            return False, f"expected integer, got: {v!r}"

    if type_str == "float":
        try:
            float(v)
            return True, ""
        except ValueError:
            return False, f"expected number, got: {v!r}"

    if type_str == "bool":
        if v.lower() in ("true", "false", "yes", "no", "on", "off", "0", "1"):
            return True, ""
        return False, f"expected true/false, got: {v!r}"

    if type_str.startswith("enum:"):
        choices = [c for c in type_str[5:].split(",") if c]
        if v in choices:
            return True, ""
        return False, f"expected one of [{', '.join(choices)}], got: {v!r}"

    if type_str == "color":
        # Accept 0xAARRGGBB or #rrggbb
        if _HEX_COLOR_RE.match(v) or _HASH_COLOR_RE.match(v):
            return True, ""
        return False, f"expected 0xAARRGGBB or #rrggbb color, got: {v!r}"

    # gradient, vec2, str — accept anything
    return True, ""


def format_type_short(type_str: str) -> str:
    """Return a short display label for a type string."""
    if type_str.startswith("enum:"):
        return "enum"
    return type_str


def schema_to_dict() -> dict:
    """Serialize OPTION_SCHEMA to a plain dict suitable for JSON export.

    Used by `hyprconf schema dump` for machine-readable output.
    Schema shape::

        {
            "sections": {
                "general": {
                    "keys": {
                        "gaps_in": {
                            "type": "int",
                            "default": "5",
                            "description": "Gap between tiled windows"
                        },
                        ...
                    }
                },
                ...
            },
            "section_order": [...],
            "section_labels": {...}
        }
    """
    sections: dict = {}
    for section, keys in OPTION_SCHEMA.items():
        sections[section] = {
            "keys": {
                k: {"type": t, "default": d, "description": desc}
                for k, (t, d, desc) in keys.items()
            }
        }
    return {
        "sections": sections,
        "section_order": SECTION_ORDER,
        "section_labels": SECTION_LABELS,
    }
