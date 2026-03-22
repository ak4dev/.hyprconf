"""Tests for hyprconf.monitors — monitor line parser and writer."""
from __future__ import annotations

from pathlib import Path

import pytest

from hyprconf.monitors import (
    MonitorConfig,
    delete_monitor,
    disable_monitor,
    enable_monitor,
    read_monitor_configs,
    upsert_monitor,
)

MONITORS_CONF = """\
monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5
monitor = DP-1, 1920x1080@60, 3840x0, 1.0
"""

EXTRAS_CONF = """\
monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5, vrr, 1, bitdepth, 10, cm, hdr
"""

DISABLED_CONF = """\
monitor = eDP-1, disable
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mon_file(hypr_dir: Path, content: str) -> Path:
    p = hypr_dir / "monitors.conf"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# read_monitor_configs
# ---------------------------------------------------------------------------

def test_reads_two_monitors(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    configs = read_monitor_configs(p)
    assert len(configs) == 2


def test_parses_fields_correctly(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    m = read_monitor_configs(p)[0]
    assert m.name == "HDMI-A-1"
    assert m.resolution == "3840x2160@120"
    assert m.position == "0x0"
    assert m.scale == "1.5"


def test_parses_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, EXTRAS_CONF)
    m = read_monitor_configs(p)[0]
    assert "vrr" in m.extras
    assert "bitdepth" in m.extras
    assert "cm" in m.extras


def test_empty_file(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    assert read_monitor_configs(p) == []


def test_missing_file(hypr_dir: Path) -> None:
    assert read_monitor_configs(hypr_dir / "nonexistent.conf") == []


def test_ignores_comments(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "# monitor = DP-1, preferred, auto, 1\nmonitor = HDMI-A-1, preferred, auto, 1\n")
    configs = read_monitor_configs(p)
    assert len(configs) == 1
    assert configs[0].name == "HDMI-A-1"


def test_is_disabled_false(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    m = read_monitor_configs(p)[0]
    assert m.is_disabled is False


def test_is_disabled_true(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, DISABLED_CONF)
    m = read_monitor_configs(p)[0]
    assert m.is_disabled is True


def test_to_line_no_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    m = read_monitor_configs(p)[0]
    line = m.to_line()
    assert line == "monitor = HDMI-A-1, 3840x2160@120, 0x0, 1.5"


def test_to_line_with_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, EXTRAS_CONF)
    m = read_monitor_configs(p)[0]
    line = m.to_line()
    assert "vrr" in line
    assert "cm" in line


def test_line_idx_correct(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    configs = read_monitor_configs(p)
    assert configs[0].line_idx == 0
    assert configs[1].line_idx == 1


# ---------------------------------------------------------------------------
# upsert_monitor
# ---------------------------------------------------------------------------

def test_upsert_appends_new(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    assert upsert_monitor("HDMI-A-1", "preferred", "auto", "1", file=p) is True
    configs = read_monitor_configs(p)
    assert len(configs) == 1
    assert configs[0].name == "HDMI-A-1"


def test_upsert_updates_existing(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0", file=p)
    configs = read_monitor_configs(p)
    hdmi = next(c for c in configs if c.name == "HDMI-A-1")
    assert hdmi.resolution == "1920x1080@60"
    assert hdmi.scale == "1.0"


def test_upsert_with_extras(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    upsert_monitor("HDMI-A-1", "3840x2160@120", "0x0", "1.5",
                   "vrr, 1, bitdepth, 10", file=p)
    text = p.read_text()
    assert "vrr, 1, bitdepth, 10" in text


def test_upsert_preserves_other_monitors(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    upsert_monitor("HDMI-A-1", "preferred", "auto", "1", file=p)
    configs = read_monitor_configs(p)
    names = [c.name for c in configs]
    assert "DP-1" in names  # second monitor preserved


# ---------------------------------------------------------------------------
# delete_monitor
# ---------------------------------------------------------------------------

def test_delete_monitor(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    configs = read_monitor_configs(p)
    first = configs[0]
    assert delete_monitor(first.file_path, first.line_idx) is True
    remaining = read_monitor_configs(p)
    assert len(remaining) == 1
    assert remaining[0].name == "DP-1"


def test_delete_monitor_invalid_idx(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    assert delete_monitor(p, 999) is False


# ---------------------------------------------------------------------------
# disable_monitor / enable_monitor
# ---------------------------------------------------------------------------

def test_disable_monitor(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    assert disable_monitor("HDMI-A-1", file=p) is True
    configs = read_monitor_configs(p)
    hdmi = next(c for c in configs if c.name == "HDMI-A-1")
    assert hdmi.is_disabled is True


def test_disable_monitor_not_found_appends(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")
    disable_monitor("HDMI-A-1", file=p)
    text = p.read_text()
    assert "HDMI-A-1" in text
    assert "disable" in text


def test_enable_disabled_monitor(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, DISABLED_CONF)
    assert enable_monitor("eDP-1", file=p) is True
    configs = read_monitor_configs(p)
    edp = next(c for c in configs if c.name == "eDP-1")
    assert edp.is_disabled is False
    assert edp.resolution == "preferred"


def test_enable_already_enabled_returns_false(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, MONITORS_CONF)
    assert enable_monitor("HDMI-A-1", file=p) is False


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_full_crud_round_trip(hypr_dir: Path) -> None:
    p = _mon_file(hypr_dir, "")

    # Add
    upsert_monitor("TEST-1", "1920x1080@60", "0x0", "1.0", file=p)
    configs = read_monitor_configs(p)
    assert len(configs) == 1

    # Update
    upsert_monitor("TEST-1", "2560x1440@144", "0x0", "1.25", file=p)
    configs = read_monitor_configs(p)
    assert configs[0].resolution == "2560x1440@144"

    # Disable
    disable_monitor("TEST-1", file=p)
    configs = read_monitor_configs(p)
    assert configs[0].is_disabled is True

    # Enable
    enable_monitor("TEST-1", file=p)
    configs = read_monitor_configs(p)
    assert configs[0].is_disabled is False

    # Delete
    delete_monitor(configs[0].file_path, configs[0].line_idx)
    assert read_monitor_configs(p) == []


# ---------------------------------------------------------------------------
# Default path coverage (covers L79, L114, L136, L147)
# ---------------------------------------------------------------------------

def test_read_monitor_configs_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import read_monitor_configs, MONITORS_FILE
    MONITORS_FILE.write_text("monitor = eDP-1, 1920x1080@60, 0x0, 1\n")
    configs = read_monitor_configs()  # no file arg → MONITORS_FILE
    assert len(configs) == 1
    assert configs[0].name == "eDP-1"


def test_upsert_monitor_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import upsert_monitor, read_monitor_configs, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1")  # no file arg
    configs = read_monitor_configs(MONITORS_FILE)
    assert any(m.name == "HDMI-A-1" for m in configs)


def test_delete_monitor_uses_default_file_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import upsert_monitor, delete_monitor, read_monitor_configs, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("eDP-1", "preferred", "auto", "1", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    assert len(configs) == 1
    mc = configs[0]
    # delete_monitor uses mc.file_path which is MONITORS_FILE
    delete_monitor(mc.file_path, mc.line_idx)
    assert read_monitor_configs(MONITORS_FILE) == []


# ---------------------------------------------------------------------------
# enable_monitor / disable_monitor use default file path (covers L136, L147)
# ---------------------------------------------------------------------------

def test_enable_monitor_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import enable_monitor, upsert_monitor, read_monitor_configs, MONITORS_FILE
    MONITORS_FILE.write_text("")
    # Add a disabled monitor
    upsert_monitor("DP-1", "disable", "0x0", "1", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    assert any(m.is_disabled for m in configs)
    # enable_monitor without file arg should use MONITORS_FILE
    enable_monitor("DP-1")  # file=None → MONITORS_FILE
    configs2 = read_monitor_configs(MONITORS_FILE)
    assert not any(m.is_disabled for m in configs2 if m.name == "DP-1")


def test_disable_monitor_uses_default_path(hypr_dir: Path) -> None:
    from hyprconf.monitors import disable_monitor, upsert_monitor, read_monitor_configs, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-1", "preferred", "0x0", "1", file=MONITORS_FILE)
    # disable_monitor without file arg
    disable_monitor("HDMI-1")  # file=None → MONITORS_FILE
    configs = read_monitor_configs(MONITORS_FILE)
    assert any(m.is_disabled for m in configs if m.name == "HDMI-1")


# ---------------------------------------------------------------------------
# get_monitor_fields
# ---------------------------------------------------------------------------

def test_get_monitor_fields_all(hypr_dir: Path) -> None:
    from hyprconf.monitors import get_monitor_fields, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0",
                   extras="vrr, 1", file=MONITORS_FILE)
    upsert_monitor("DP-1", "3840x2160@120", "1920x0", "1.5", file=MONITORS_FILE)
    result = get_monitor_fields(file=MONITORS_FILE)
    assert "HDMI-A-1" in result
    assert "DP-1" in result
    assert "1920x1080@60" in result


def test_get_monitor_fields_single(hypr_dir: Path) -> None:
    from hyprconf.monitors import get_monitor_fields, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0",
                   extras="vrr, 2, bitdepth, 10", file=MONITORS_FILE)
    result = get_monitor_fields("HDMI-A-1", file=MONITORS_FILE)
    assert "HDMI-A-1" in result
    assert "1920x1080@60" in result
    assert "vrr" in result
    assert "bitdepth" in result


def test_get_monitor_fields_not_found(hypr_dir: Path) -> None:
    from hyprconf.monitors import get_monitor_fields, MONITORS_FILE
    MONITORS_FILE.write_text("")
    result = get_monitor_fields("nonexistent", file=MONITORS_FILE)
    assert "not found" in result.lower()


def test_get_monitor_fields_empty(hypr_dir: Path) -> None:
    from hyprconf.monitors import get_monitor_fields, MONITORS_FILE
    MONITORS_FILE.write_text("")
    result = get_monitor_fields(file=MONITORS_FILE)
    assert "No monitor" in result


# ---------------------------------------------------------------------------
# update_monitor_field
# ---------------------------------------------------------------------------

def test_update_monitor_field_extras(hypr_dir: Path) -> None:
    from hyprconf.monitors import update_monitor_field, read_monitor_configs, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0", file=MONITORS_FILE)
    update_monitor_field("HDMI-A-1", "vrr", "2", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    mc = next(c for c in configs if c.name == "HDMI-A-1")
    assert "vrr" in mc.extras
    assert "2" in mc.extras


def test_update_monitor_field_scale(hypr_dir: Path) -> None:
    from hyprconf.monitors import update_monitor_field, read_monitor_configs, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0", file=MONITORS_FILE)
    update_monitor_field("HDMI-A-1", "scale", "1.5", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    mc = next(c for c in configs if c.name == "HDMI-A-1")
    assert mc.scale == "1.5"


def test_update_monitor_field_res(hypr_dir: Path) -> None:
    from hyprconf.monitors import update_monitor_field, read_monitor_configs, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0", file=MONITORS_FILE)
    update_monitor_field("HDMI-A-1", "res", "2560x1440@144", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    mc = next(c for c in configs if c.name == "HDMI-A-1")
    assert mc.resolution == "2560x1440@144"


def test_update_monitor_field_preserves_other_extras(hypr_dir: Path) -> None:
    from hyprconf.monitors import update_monitor_field, read_monitor_configs, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0",
                   extras="vrr, 1, bitdepth, 10", file=MONITORS_FILE)
    update_monitor_field("HDMI-A-1", "vrr", "2", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    mc = next(c for c in configs if c.name == "HDMI-A-1")
    assert "bitdepth" in mc.extras
    assert "vrr" in mc.extras


def test_update_monitor_field_unknown_raises(hypr_dir: Path) -> None:
    from hyprconf.monitors import update_monitor_field, upsert_monitor, MONITORS_FILE
    MONITORS_FILE.write_text("")
    upsert_monitor("HDMI-A-1", "1920x1080@60", "0x0", "1.0", file=MONITORS_FILE)
    with pytest.raises(ValueError, match="Unknown monitor field"):
        update_monitor_field("HDMI-A-1", "invalid_field", "x", file=MONITORS_FILE)


def test_update_monitor_field_creates_new_entry(hypr_dir: Path) -> None:
    from hyprconf.monitors import update_monitor_field, read_monitor_configs, MONITORS_FILE
    MONITORS_FILE.write_text("")
    update_monitor_field("DP-1", "scale", "2.0", file=MONITORS_FILE)
    configs = read_monitor_configs(MONITORS_FILE)
    mc = next((c for c in configs if c.name == "DP-1"), None)
    assert mc is not None
    assert mc.scale == "2.0"
