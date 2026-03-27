"""
Tests for untested dispatcher commands: addon, deploy, display, repair, teardown.

Validates that each command function exists in the hyprconf binary,
has correct dispatcher entries, and appears in help text.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"


def _bin_text() -> str:
    return HYPRCONF_BIN.read_text()


# ---------------------------------------------------------------------------
# 1. cmd_addon
# ---------------------------------------------------------------------------

class TestCmdAddon:
    """Verify hyprconf addon command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_addon()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "addon)" in l and "cmd_addon" in l]
        assert lines, "addon must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf addon" in _bin_text()

    def test_addon_list(self) -> None:
        text = _bin_text()
        assert "_addon_list" in text

    def test_addon_install(self) -> None:
        text = _bin_text()
        assert "_addon_install" in text

    def test_addon_names(self) -> None:
        text = _bin_text()
        assert "_ADDON_NAMES" in text


# ---------------------------------------------------------------------------
# 2. cmd_deploy
# ---------------------------------------------------------------------------

class TestCmdDeploy:
    """Verify hyprconf deploy command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_deploy()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "deploy)" in l and "cmd_deploy" in l]
        assert lines, "deploy must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf deploy" in _bin_text()

    def test_deploy_list_subcommand(self) -> None:
        text = _bin_text()
        assert "cmd_deploy_list" in text

    def test_deploy_new_subcommand(self) -> None:
        text = _bin_text()
        assert "cmd_deploy_new" in text

    def test_deploy_domain_subcommand(self) -> None:
        text = _bin_text()
        assert "cmd_deploy_domain" in text

    def test_uses_deploy_script(self) -> None:
        text = _bin_text()
        assert "DEPLOY_SCRIPT" in text


# ---------------------------------------------------------------------------
# 3. cmd_display
# ---------------------------------------------------------------------------

class TestCmdDisplay:
    """Verify hyprconf display command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_display()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "display)" in l and "cmd_display" in l]
        assert lines, "display must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf display" in _bin_text()

    def test_toggle_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_display()")
        body = text[idx:idx + 300]
        assert "toggle" in body

    def test_uses_display_script(self) -> None:
        text = _bin_text()
        assert "DISPLAY_SCRIPT" in text


# ---------------------------------------------------------------------------
# 4. cmd_repair
# ---------------------------------------------------------------------------

class TestCmdRepair:
    """Verify hyprconf repair command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_repair()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "repair)" in l and "cmd_repair" in l]
        assert lines, "repair must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf repair" in _bin_text()

    def test_uses_setup_script(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_repair()")
        body = text[idx:idx + 200]
        assert "SETUP_SCRIPT" in body

    def test_passes_repair_flag(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_repair()")
        body = text[idx:idx + 200]
        assert "--repair" in body


# ---------------------------------------------------------------------------
# 5. cmd_teardown
# ---------------------------------------------------------------------------

class TestCmdTeardown:
    """Verify hyprconf teardown command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_teardown()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "teardown)" in l and "cmd_teardown" in l]
        assert lines, "teardown must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf teardown" in _bin_text()

    def test_uses_teardown_script(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_teardown()")
        body = text[idx:idx + 200]
        assert "TEARDOWN_SCRIPT" in body


# ---------------------------------------------------------------------------
# 6. cmd_hardware
# ---------------------------------------------------------------------------

class TestCmdHardware:
    """Verify hyprconf hardware command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_hardware()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "hardware)" in l and "cmd_hardware" in l]
        assert lines, "hardware must have a dispatcher entry in main()"

    def test_help_text(self) -> None:
        assert "hyprconf hardware" in _bin_text()

    def test_status_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_hardware()")
        body = text[idx:idx + 600]
        assert "status)" in body

    def test_osk_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_hardware()")
        body = text[idx:idx + 1500]
        assert "osk)" in body

    def test_rotate_subcommand(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_hardware()")
        body = text[idx:idx + 3000]
        assert "rotate)" in body


# ---------------------------------------------------------------------------
# 7. cmd_set_keyword
# ---------------------------------------------------------------------------

class TestCmdSetKeyword:
    """Verify hyprconf set <section> <key> <value> routing."""

    def test_function_exists(self) -> None:
        assert "cmd_set_keyword()" in _bin_text()

    def test_three_arg_validation(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_set_keyword()")
        body = text[idx:idx + 300]
        assert "section" in body and "key" in body and "value" in body

    def test_monitors_special_case(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_set_keyword()")
        body = text[idx:idx + 500]
        assert '"monitors"' in body

    def test_type_validation(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_set_keyword()")
        body = text[idx:idx + 1000]
        assert "_option_meta" in body


# ---------------------------------------------------------------------------
# 8. cmd_set_mainmod
# ---------------------------------------------------------------------------

class TestCmdSetMainmod:
    """Verify hyprconf set mainMod command."""

    def test_function_exists(self) -> None:
        assert "cmd_set_mainmod()" in _bin_text()

    def test_routed_from_cmd_set(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_set()")
        body = text[idx:idx + 300]
        assert "mainMod|mainmod)" in body
        assert "cmd_set_mainmod" in body

    def test_validates_modifier_tokens(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_set_mainmod()")
        body = text[idx:idx + 500]
        assert "SUPER" in body and "ALT" in body and "CTRL" in body and "SHIFT" in body

    def test_writes_to_local_overrides(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_set_mainmod()")
        body = text[idx:idx + 1000]
        assert "HYPR_LOCAL_OVERRIDES" in body


# ---------------------------------------------------------------------------
# 9. cmd_show
# ---------------------------------------------------------------------------

class TestCmdShow:
    """Verify hyprconf show command structure."""

    def test_function_exists(self) -> None:
        assert "cmd_show()" in _bin_text()

    def test_dispatcher_entry(self) -> None:
        text = _bin_text()
        lines = [l.strip() for l in text.splitlines()
                 if "show)" in l and "cmd_show" in l]
        assert lines, "show must have a dispatcher entry in main()"

    def test_routes_keybind(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_show()")
        body = text[idx:idx + 300]
        assert "keybind" in body
        assert "cmd_show_keybinds" in body

    def test_help_text(self) -> None:
        assert "hyprconf show" in _bin_text()


# ---------------------------------------------------------------------------
# 10. cmd_show_keybinds
# ---------------------------------------------------------------------------

class TestCmdShowKeybinds:
    """Verify hyprconf show keybind command."""

    def test_function_exists(self) -> None:
        assert "cmd_show_keybinds()" in _bin_text()

    def test_finds_keybinds_conf(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_show_keybinds()")
        body = text[idx:idx + 300]
        assert "_find_keybinds_conf" in body

    def test_recursive_read(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_show_keybinds()")
        body = text[idx:idx + 1000]
        assert "_read_conf_recursive" in body

    def test_column_output(self) -> None:
        text = _bin_text()
        idx = text.index("cmd_show_keybinds()")
        body = text[idx:idx + 2000]
        assert "printf" in body
