"""Tests for hyprconf.config — the overrides file reader and writer."""

from __future__ import annotations

from pathlib import Path

from hyprconf.config import (
    MANAGED_MARKER,
    migrate_legacy,
    read_persisted,
    save_pending,
    section_key_to_hyprctl,
)

# ---------------------------------------------------------------------------
# section_key_to_hyprctl
# ---------------------------------------------------------------------------


def test_simple_section_key(hypr_dir: Path) -> None:
    assert section_key_to_hyprctl("general", "gaps_in") == "general:gaps_in"


def test_dotted_section_key(hypr_dir: Path) -> None:
    assert section_key_to_hyprctl("decoration.blur", "enabled") == "decoration:blur:enabled"


def test_deeply_nested_key(hypr_dir: Path) -> None:
    assert (
        section_key_to_hyprctl("input.touchpad", "natural_scroll")
        == "input:touchpad:natural_scroll"
    )


# ---------------------------------------------------------------------------
# read_persisted — file absent
# ---------------------------------------------------------------------------


def test_read_persisted_missing_file(hypr_dir: Path) -> None:
    assert read_persisted("general", "gaps_in") is None


# ---------------------------------------------------------------------------
# save_pending
# ---------------------------------------------------------------------------


def test_save_pending_writes_marker(hypr_dir: Path) -> None:
    ok, count = save_pending({"general": {"gaps_in": "8"}})
    assert ok is True
    assert count >= 1
    import hyprconf.config as cfg

    text = cfg.OVERRIDES_FILE.read_text()
    assert MANAGED_MARKER in text


def test_save_pending_multiple_sections(hypr_dir: Path) -> None:
    ok, _ = save_pending(
        {
            "general": {"gaps_in": "8", "border_size": "2"},
            "decoration.blur": {"enabled": "true"},
        }
    )
    assert ok is True
    assert read_persisted("general", "gaps_in") == "8"
    assert read_persisted("decoration.blur", "enabled") == "true"


def test_save_pending_preserves_user_zone(hypr_dir: Path) -> None:
    import hyprconf.config as cfg

    cfg.OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.OVERRIDES_FILE.write_text('-- My custom config\nhl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))\n')
    save_pending({"general": {"gaps_in": "5"}})
    text = cfg.OVERRIDES_FILE.read_text()
    assert "-- My custom config" in text
    assert 'hl.bind("SUPER + T", hl.dsp.exec_cmd("kitty"))' in text
    assert "gaps_in = 5" in text


def test_save_pending_sorted_keys(hypr_dir: Path) -> None:
    save_pending({"z_section": {"z_key": "1"}, "a_section": {"a_key": "2"}})
    import hyprconf.config as cfg

    # The managed block is a single nested hl.config({...}) call; sections
    # (top-level table keys) are written in sorted order.
    keys = list(cfg._flatten_config_call(cfg.OVERRIDES_FILE.read_text()))
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Legacy migration
# ---------------------------------------------------------------------------


def test_migrate_legacy_copies_file(hypr_dir: Path) -> None:
    """A pre-Lua-migration overrides file (flat `section:key = value`, ``#``
    marker) is converted to the current nested hl.config({...}) form."""
    import hyprconf.config as cfg

    legacy = cfg.LEGACY_OVERRIDES_FILE
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("# hyprconf-managed\ngeneral:gaps_in = 5\n")
    assert migrate_legacy() is True
    assert cfg.OVERRIDES_FILE.exists()
    text = cfg.OVERRIDES_FILE.read_text()
    assert MANAGED_MARKER in text
    assert "gaps_in = 5" in text
    assert read_persisted("general", "gaps_in") == "5"


def test_migrate_legacy_no_op_if_new_exists(hypr_dir: Path) -> None:
    import hyprconf.config as cfg

    cfg.LEGACY_OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.LEGACY_OVERRIDES_FILE.write_text("old content\n")
    cfg.OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.OVERRIDES_FILE.write_text("new content\n")
    assert migrate_legacy() is False
    assert cfg.OVERRIDES_FILE.read_text() == "new content\n"


# ---------------------------------------------------------------------------
# save_pending — legacy marker stripping (covers L116)
# ---------------------------------------------------------------------------


def test_save_pending_strips_legacy_marker(hypr_dir: Path) -> None:
    from hyprconf.config import MANAGED_MARKER, OVERRIDES_FILE, save_pending

    OVERRIDES_FILE.write_text("# hyprconf-tui managed\ngeneral:gaps_in = 3\n")
    ok, n = save_pending({"general": {"border_size": "2"}})
    assert ok is True
    text = OVERRIDES_FILE.read_text()
    assert MANAGED_MARKER in text
    assert "# hyprconf-tui managed" not in text


# ---------------------------------------------------------------------------
# save_pending — OSError path (covers L137-138)
# ---------------------------------------------------------------------------


def test_save_pending_returns_false_on_oserror(hypr_dir: Path) -> None:
    import unittest.mock as _mock

    from hyprconf.config import save_pending

    with _mock.patch("hyprconf.config.atomic_write_text", side_effect=OSError("disk full")):
        ok, n = save_pending({"general": {"gaps_in": "5"}})
    assert ok is False
    assert n == 0
