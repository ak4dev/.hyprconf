"""Tests for hyprconf.schema — option-schema data integrity and currency."""

from __future__ import annotations

import re

from hyprconf.schema import OPTION_SCHEMA, SECTION_LABELS, SECTION_ORDER

_HEX_COLOR_RE = re.compile(r"^0x[0-9a-fA-F]{6,8}$")
_HASH_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6,8}$")


def validate_value(type_str: str, value: str) -> tuple[bool, str]:
    """Test oracle for the schema type contract (see the module docstring of
    hyprconf.schema): each declared default must satisfy its declared type."""
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
        if _HEX_COLOR_RE.match(v) or _HASH_COLOR_RE.match(v):
            return True, ""
        if v.startswith(("rgb(", "rgba(")) or v.lower() == "unset":
            return True, ""
        return False, f"expected color (hex, rgb(), rgba(), or 'unset'), got: {v!r}"
    return True, ""  # gradient, vec2, str — accept anything


# ---------------------------------------------------------------------------
# OPTION_SCHEMA structure
# ---------------------------------------------------------------------------


def test_schema_not_empty() -> None:
    assert len(OPTION_SCHEMA) > 0


def test_schema_has_required_sections() -> None:
    required = {"general", "decoration", "animations", "input", "misc"}
    assert required.issubset(OPTION_SCHEMA.keys())


def test_schema_entry_is_triple() -> None:
    """Every entry must be a 3-tuple: (type, default, description)."""
    for section, keys in OPTION_SCHEMA.items():
        for key, meta in keys.items():
            assert isinstance(meta, tuple) and len(meta) == 3, (
                f"Bad schema entry: {section}.{key} = {meta!r}"
            )


def test_schema_types_are_valid_strings() -> None:
    valid_base_types = {"int", "float", "bool", "str", "color", "gradient", "vec2"}
    for section, keys in OPTION_SCHEMA.items():
        for key, (type_str, _default, _desc) in keys.items():
            is_valid = type_str in valid_base_types or type_str.startswith("enum:")
            assert is_valid, f"Unknown type {type_str!r} in {section}.{key}"


def test_schema_subsection_dot_notation() -> None:
    """Subsections use dot notation (e.g. decoration.blur)."""
    dot_sections = [s for s in OPTION_SCHEMA if "." in s]
    assert len(dot_sections) > 0
    assert "decoration.blur" in OPTION_SCHEMA


# ---------------------------------------------------------------------------
# SECTION_ORDER
# ---------------------------------------------------------------------------


def test_section_order_is_list() -> None:
    assert isinstance(SECTION_ORDER, list)


def test_section_order_not_empty() -> None:
    assert len(SECTION_ORDER) > 0


def test_section_order_monitors_is_first_entry() -> None:
    """Monitors should be the very first (non-separator) item in SECTION_ORDER."""
    non_empty = [s for s in SECTION_ORDER if s]
    assert non_empty[0] == "monitors"


def test_section_order_management_sections_before_separator() -> None:
    """Management sections (monitors, keybinds, …) must all appear before the '' separator."""
    separator_idx = SECTION_ORDER.index("")
    before_sep = SECTION_ORDER[:separator_idx]
    for section in (
        "monitors",
        "keybinds",
        "window_rules",
        "workspace_rules",
        "hyprlock",
        "hypridle",
        "hyprpaper",
        "theme",
        "hardware",
    ):
        assert section in before_sep, f"'{section}' should be before the separator"


def test_section_order_general_after_separator() -> None:
    separator_idx = SECTION_ORDER.index("")
    after_sep = SECTION_ORDER[separator_idx + 1 :]
    assert "general" in after_sep


# ---------------------------------------------------------------------------
# Hyprland 0.55 currency — new sections, removals, renames, drift-fixes
# (lockstep: these pin the schema to the live wiki.hypr.land reference)
# ---------------------------------------------------------------------------


def test_new_055_sections_present() -> None:
    for section in (
        "decoration.glow",
        "decoration.motion_blur",
        "input.touchdevice",
        "input.virtualkeyboard",
        "input.tablet",
        "input.tablettool",
        "layout",
        "scrolling",
        "gestures.scrolling",
        "ecosystem",
        "experimental",
        "quirks",
        "debug",
    ):
        assert section in OPTION_SCHEMA, f"missing 0.55 section {section!r}"


def test_qtutils_check_renamed_to_guiutils() -> None:
    """0.55 renamed hyprland-qtutils -> hyprland-guiutils (and the misc option)."""
    misc = OPTION_SCHEMA["misc"]
    assert "disable_hyprland_guiutils_check" in misc
    assert "disable_hyprland_qtutils_check" not in misc


def test_scrolling_layout_is_configurable() -> None:
    """general:layout offers `scrolling`, so its options must be in the schema."""
    assert "scrolling" in OPTION_SCHEMA
    sc = OPTION_SCHEMA["scrolling"]
    assert sc["direction"][0] == "enum:left,right,down,up"
    assert sc["column_width"][0] == "float"


def test_shadow_and_glow_colors_are_gradients() -> None:
    """0.55 types shadow/glow colors as gradients (a plain color is a valid subset)."""
    assert OPTION_SCHEMA["decoration.shadow"]["color"][0] == "gradient"
    assert OPTION_SCHEMA["decoration.glow"]["color"][0] == "gradient"


def test_removed_options_absent() -> None:
    """Options Hyprland dropped must not linger in the schema."""
    assert "ignore_window" not in OPTION_SCHEMA["decoration.shadow"]
    assert "pseudotile" not in OPTION_SCHEMA["dwindle"]  # now the window.pseudo dispatcher
    assert "new_client_position" not in OPTION_SCHEMA["master"]  # superseded by new_status
    assert "inherit_fullscreen" not in OPTION_SCHEMA["master"]
    assert "vfr" not in OPTION_SCHEMA["misc"]  # relocated to debug:vfr


def test_touchpad_tap_options_use_hyphens() -> None:
    # Hyprland 0.56.0 accepts only the hyphenated names (`Hyprland
    # --verify-config` rejects the underscore variants; the wiki's underscores
    # track unreleased git). Re-check on the next compositor upgrade.
    tp = OPTION_SCHEMA["input.touchpad"]
    assert "tap-to-click" in tp and "tap_to_click" not in tp
    assert "tap-and-drag" in tp and "tap_and_drag" not in tp


def test_vfr_relocated_to_debug() -> None:
    assert "vfr" in OPTION_SCHEMA["debug"]


def test_drift_fixed_defaults_and_types() -> None:
    assert OPTION_SCHEMA["input"]["accel_profile"][1] == ""  # libinput device default
    assert OPTION_SCHEMA["master"]["special_scale_factor"][1] == "1.0"
    cm_type, cm_default, _ = OPTION_SCHEMA["render"]["cm_auto_hdr"]
    assert cm_type == "enum:0,1,2" and cm_default == "1"  # was mistyped bool/true
    new_status_type = OPTION_SCHEMA["master"]["new_status"][0]
    assert "inherit" in new_status_type
    assert "inherit_fullscreen" not in new_status_type


def test_new_option_spot_checks() -> None:
    assert OPTION_SCHEMA["ecosystem"]["no_update_news"][0] == "bool"
    assert OPTION_SCHEMA["layout"]["single_window_aspect_ratio"][0] == "vec2"
    assert OPTION_SCHEMA["decoration.glow"]["enabled"][0] == "bool"
    assert OPTION_SCHEMA["input.touchpad"]["tap_button_map"][0] == "enum:lrm,lmr"
    assert OPTION_SCHEMA["master"]["orientation"][0] == "enum:left,right,top,bottom,center"


def test_every_default_validates_against_its_type() -> None:
    """Currency invariant: a non-empty default must satisfy its own declared type."""
    for section, keys in OPTION_SCHEMA.items():
        for key, (type_str, default, _desc) in keys.items():
            if default == "":
                continue  # empty = unset / inherit device default
            ok, msg = validate_value(type_str, default)
            assert ok, f"{section}.{key} default {default!r} invalid for {type_str}: {msg}"


def test_every_schema_section_has_label_and_order_entry() -> None:
    """No schema section may be unreachable from the TUI sidebar."""
    for section in OPTION_SCHEMA:
        assert section in SECTION_LABELS, f"{section} missing a SECTION_LABELS entry"
        assert section in SECTION_ORDER, f"{section} missing from SECTION_ORDER"


def test_descriptions_present_and_bounded() -> None:
    for section, keys in OPTION_SCHEMA.items():
        for key, (_t, _d, desc) in keys.items():
            assert 0 < len(desc) <= 110, f"{section}.{key} description length {len(desc)}"
