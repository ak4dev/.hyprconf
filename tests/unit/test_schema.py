"""Tests for hyprconf.schema — option schema, validation, and serialisation."""

from __future__ import annotations

import pytest
from hyprconf.schema import (
    OPTION_SCHEMA,
    SECTION_ORDER,
    format_type_short,
    get_all_sections,
    get_option_meta,
    get_section_keys,
    schema_to_dict,
    validate_value,
)

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
# get_section_keys
# ---------------------------------------------------------------------------


def test_get_section_keys_general() -> None:
    keys = get_section_keys("general")
    assert "gaps_in" in keys
    assert "border_size" in keys


def test_get_section_keys_unknown_section() -> None:
    assert get_section_keys("nonexistent_section") == []


def test_get_section_keys_returns_list() -> None:
    result = get_section_keys("general")
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# get_option_meta
# ---------------------------------------------------------------------------


def test_get_option_meta_known_key() -> None:
    meta = get_option_meta("general", "gaps_in")
    assert meta is not None
    type_str, default, desc = meta
    assert type_str == "int"
    assert default == "5"
    assert "gap" in desc.lower()


def test_get_option_meta_unknown_section() -> None:
    assert get_option_meta("nonexistent", "key") is None


def test_get_option_meta_unknown_key() -> None:
    assert get_option_meta("general", "nonexistent_key") is None


def test_get_option_meta_subsection() -> None:
    meta = get_option_meta("decoration.blur", "enabled")
    assert meta is not None
    assert meta[0] == "bool"


# ---------------------------------------------------------------------------
# get_all_sections
# ---------------------------------------------------------------------------


def test_get_all_sections_returns_list() -> None:
    sections = get_all_sections()
    assert isinstance(sections, list)
    assert len(sections) > 0


def test_get_all_sections_matches_schema() -> None:
    assert set(get_all_sections()) == set(OPTION_SCHEMA.keys())


# ---------------------------------------------------------------------------
# validate_value — int
# ---------------------------------------------------------------------------


def test_validate_int_valid() -> None:
    ok, msg = validate_value("int", "42")
    assert ok is True
    assert msg == ""


def test_validate_int_negative() -> None:
    ok, _ = validate_value("int", "-5")
    assert ok is True


def test_validate_int_invalid() -> None:
    ok, msg = validate_value("int", "hello")
    assert ok is False
    assert msg != ""


def test_validate_int_float_string() -> None:
    ok, _ = validate_value("int", "3.14")
    assert ok is False


# ---------------------------------------------------------------------------
# validate_value — float
# ---------------------------------------------------------------------------


def test_validate_float_valid() -> None:
    ok, _ = validate_value("float", "1.5")
    assert ok is True


def test_validate_float_integer_string() -> None:
    ok, _ = validate_value("float", "2")
    assert ok is True


def test_validate_float_invalid() -> None:
    ok, msg = validate_value("float", "not_a_number")
    assert ok is False
    assert msg != ""


# ---------------------------------------------------------------------------
# validate_value — bool
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "v", ["true", "false", "yes", "no", "on", "off", "0", "1", "True", "FALSE"]
)
def test_validate_bool_valid_values(v: str) -> None:
    ok, _ = validate_value("bool", v)
    assert ok is True


def test_validate_bool_invalid() -> None:
    ok, msg = validate_value("bool", "maybe")
    assert ok is False
    assert msg != ""


# ---------------------------------------------------------------------------
# validate_value — enum
# ---------------------------------------------------------------------------


def test_validate_enum_valid() -> None:
    ok, _ = validate_value("enum:dwindle,master,scrolling", "dwindle")
    assert ok is True


def test_validate_enum_invalid() -> None:
    ok, msg = validate_value("enum:dwindle,master", "unknown")
    assert ok is False
    assert "dwindle" in msg


def test_validate_enum_case_sensitive() -> None:
    ok, _ = validate_value("enum:dwindle,master", "Dwindle")
    assert ok is False


# ---------------------------------------------------------------------------
# validate_value — color
# ---------------------------------------------------------------------------


def test_validate_color_hex_format() -> None:
    ok, _ = validate_value("color", "0xffaabbcc")
    assert ok is True


def test_validate_color_hash_format() -> None:
    ok, _ = validate_value("color", "#aabbcc")
    assert ok is True


def test_validate_color_invalid() -> None:
    ok, _ = validate_value("color", "red")
    assert ok is False


def test_validate_color_rgb_format() -> None:
    ok, _ = validate_value("color", "rgb(255, 128, 0)")
    assert ok is True


def test_validate_color_rgba_format() -> None:
    ok, _ = validate_value("color", "rgba(255, 128, 0, 0.5)")
    assert ok is True


def test_validate_color_unset() -> None:
    ok, _ = validate_value("color", "unset")
    assert ok is True


# ---------------------------------------------------------------------------
# validate_value — gradient / vec2 / str (permissive)
# ---------------------------------------------------------------------------


def test_validate_gradient_accepts_anything() -> None:
    ok, _ = validate_value("gradient", "0xff000000 0xffffffff 45deg")
    assert ok is True


def test_validate_vec2_accepts_anything() -> None:
    ok, _ = validate_value("vec2", "0 0")
    assert ok is True


def test_validate_str_accepts_anything() -> None:
    ok, _ = validate_value("str", "any string at all")
    assert ok is True


# ---------------------------------------------------------------------------
# format_type_short
# ---------------------------------------------------------------------------


def test_format_type_short_enum() -> None:
    assert format_type_short("enum:a,b,c") == "enum"


def test_format_type_short_int() -> None:
    assert format_type_short("int") == "int"


def test_format_type_short_passthrough() -> None:
    assert format_type_short("color") == "color"


# ---------------------------------------------------------------------------
# schema_to_dict
# ---------------------------------------------------------------------------


def test_schema_to_dict_has_sections() -> None:
    d = schema_to_dict()
    assert "sections" in d
    assert "section_order" in d


def test_schema_to_dict_sections_structure() -> None:
    d = schema_to_dict()
    for _section, data in d["sections"].items():
        assert "keys" in data
        for _key, meta in data["keys"].items():
            assert "type" in meta
            assert "default" in meta
            assert "description" in meta


def test_schema_to_dict_json_serialisable() -> None:
    import json

    d = schema_to_dict()
    result = json.dumps(d)
    assert isinstance(result, str) and len(result) > 0


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
