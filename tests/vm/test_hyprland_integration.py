"""
VM integration tests — run against a QEMU/KVM VM via SSH.

All tests in this file are marked @pytest.mark.vm and are SKIPPED unless
pytest is invoked with --run-vm.  A running QEMU VM with SSH on port 2222
is expected.  Tests do NOT require a live Hyprland session inside the VM.

Start the VM first:
    bash tests/vm/run_vm.sh

Then run:
    pytest tests/vm/ --run-vm
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Generator

import pytest


# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------

class VMClient:
    """Thin wrapper around SSH commands to the test VM."""

    def __init__(self, host: str = "127.0.0.1", port: int = 2222,
                 user: str = "hyprtest", key: Path | None = None) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.key  = key or Path.home() / ".ssh" / "hyprconf_vm_key"

    def run(self, cmd: str, *, check: bool = True) -> subprocess.CompletedProcess:
        ssh_args = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-i", str(self.key),
            "-p", str(self.port),
            f"{self.user}@{self.host}",
            cmd,
        ]
        return subprocess.run(ssh_args, capture_output=True, text=True,
                              check=check)

    def read_file(self, remote_path: str) -> str:
        result = self.run(f"cat {remote_path}")
        return result.stdout

    def write_file(self, remote_path: str, content: str) -> None:
        # Write via echo + tee to avoid quoting issues for short content
        escaped = content.replace("'", "'\\''")
        self.run(f"printf '%s' '{escaped}' > {remote_path}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def vm() -> Generator[VMClient, None, None]:
    """Session-scoped VM client.  Checks connectivity before yielding."""
    client = VMClient()
    try:
        result = client.run("echo ok", check=True)
        assert result.stdout.strip() == "ok", "VM SSH not responding"
    except Exception as e:
        pytest.skip(f"VM not reachable: {e}")
    yield client


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_vm_ssh_reachable(vm: VMClient) -> None:
    result = vm.run("echo pong")
    assert "pong" in result.stdout


@pytest.mark.vm
def test_hyprconf_on_path(vm: VMClient) -> None:
    result = vm.run("which hyprconf")
    assert result.returncode == 0
    assert "hyprconf" in result.stdout


# ---------------------------------------------------------------------------
# hyprconf sync
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_sync_completes_successfully(vm: VMClient) -> None:
    result = vm.run("hyprconf sync --no-reload 2>&1", check=False)
    assert result.returncode == 0
    assert "Sync complete" in result.stdout


# ---------------------------------------------------------------------------
# Live get/set via hyprctl
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_set_gaps_in_reflected_by_get(vm: VMClient) -> None:
    """hyprconf set persists the value so hyprconf get reads it back."""
    vm.run("hyprconf set general gaps_in 12")
    result = vm.run("hyprconf get general gaps_in 2>&1")
    assert "12" in result.stdout


@pytest.mark.vm
def test_set_gaps_in_persists_to_file(vm: VMClient) -> None:
    vm.run("hyprconf set general gaps_in 8")
    conf = vm.read_file("~/.config/hypr/conf.d/99-hyprconf-local.conf")
    assert "general:gaps_in = 8" in conf


# ---------------------------------------------------------------------------
# Monitor config
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_monitor_list_returns_output(vm: VMClient) -> None:
    result = vm.run("hyprconf monitor list 2>&1", check=False)
    # Should not crash; output may be empty if no presets exist
    assert result.returncode == 0


@pytest.mark.vm
def test_set_monitor_writes_monitors_conf(vm: VMClient) -> None:
    """hyprconf monitor config set writes an entry to monitors.conf."""
    monitor_name = "VIRTUAL-1"
    vm.run(f"hyprconf monitor config set {monitor_name} 1920x1080 auto 1")
    conf = vm.read_file("~/.config/hypr/monitors.conf")
    assert monitor_name in conf


# ---------------------------------------------------------------------------
# Hyprland health check
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_hyprland_config_has_no_errors(vm: VMClient) -> None:
    """Hyprland --verify-config passes without errors on the installed config."""
    result = vm.run("Hyprland --verify-config 2>&1", check=False)
    assert result.returncode == 0, f"Hyprland config has errors:\n{result.stdout}"
    assert "config ok" in result.stdout.lower()


# ---------------------------------------------------------------------------
# hyprconf get
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_get_section_table(vm: VMClient) -> None:
    """hyprconf get <section> prints a table of keys."""
    result = vm.run("hyprconf get general 2>&1", check=False)
    assert result.returncode == 0
    assert "gaps_in" in result.stdout


@pytest.mark.vm
def test_get_section_key_returns_value(vm: VMClient) -> None:
    """hyprconf get <section> <key> prints the current value."""
    result = vm.run("hyprconf get general gaps_in 2>&1", check=False)
    assert result.returncode == 0
    assert "general:gaps_in" in result.stdout


@pytest.mark.vm
def test_get_unknown_section_exits_nonzero(vm: VMClient) -> None:
    """hyprconf get <bad_section> exits non-zero."""
    result = vm.run("hyprconf get __nonexistent_section__ 2>&1", check=False)
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# hyprconf set
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_set_writes_overrides_file(vm: VMClient) -> None:
    """hyprconf set <section> <key> <value> writes to the overrides conf."""
    vm.run("hyprconf set general gaps_out 15 2>&1")
    conf = vm.read_file("~/.config/hypr/conf.d/99-hyprconf-local.conf")
    assert "general:gaps_out = 15" in conf
    # Reset to default
    vm.run("hyprconf set general gaps_out 10 2>&1", check=False)


@pytest.mark.vm
def test_set_invalid_section_exits_nonzero(vm: VMClient) -> None:
    """hyprconf set <bad_section> exits non-zero."""
    result = vm.run("hyprconf set __bad__ gaps_in 0 2>&1", check=False)
    assert result.returncode != 0


# ---------------------------------------------------------------------------
# hyprconf schema
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_schema_dump_outputs_valid_json(vm: VMClient) -> None:
    """hyprconf schema dump returns valid, non-empty JSON."""
    result = vm.run("hyprconf schema dump 2>&1", check=False)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    assert len(data) > 0


@pytest.mark.vm
def test_schema_list_sections(vm: VMClient) -> None:
    """hyprconf schema list-sections includes the 'general' section."""
    result = vm.run("hyprconf schema list-sections 2>&1", check=False)
    assert result.returncode == 0
    assert "general" in result.stdout


@pytest.mark.vm
def test_schema_keys_section(vm: VMClient) -> None:
    """hyprconf schema keys <section> lists keys for that section."""
    result = vm.run("hyprconf schema keys general 2>&1", check=False)
    assert result.returncode == 0
    assert "gaps_in" in result.stdout


# ---------------------------------------------------------------------------
# hyprconf autodetect
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_autodetect_runs_without_error(vm: VMClient) -> None:
    """hyprconf autodetect completes without crashing."""
    result = vm.run("hyprconf autodetect 2>&1", check=False)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# hyprconf keybind
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_keybind_list_returns_output(vm: VMClient) -> None:
    """hyprconf keybind list produces a table without crashing."""
    result = vm.run("hyprconf keybind list 2>&1", check=False)
    assert result.returncode == 0


@pytest.mark.vm
def test_keybind_add_creates_entry(vm: VMClient) -> None:
    """hyprconf keybind add appends a new keybind line."""
    before = vm.run("hyprconf keybind list 2>&1", check=False)
    before_count = sum(
        1 for l in before.stdout.splitlines()
        if l.strip() and l.strip()[0].isdigit()
    )

    add = vm.run(
        "hyprconf keybind add bind SUPER F12 exec hyprconf-test-sentinel 2>&1",
        check=False,
    )
    assert add.returncode == 0
    assert "Added" in add.stdout

    after = vm.run("hyprconf keybind list 2>&1", check=False)
    after_count = sum(
        1 for l in after.stdout.splitlines()
        if l.strip() and l.strip()[0].isdigit()
    )
    assert after_count == before_count + 1


@pytest.mark.vm
def test_keybind_delete_removes_entry(vm: VMClient) -> None:
    """hyprconf keybind delete removes the entry at a given 1-based index."""
    # Ensure the sentinel keybind exists (add if missing)
    listing = vm.run("hyprconf keybind list 2>&1", check=False)
    if "hyprconf-test-sentinel" not in listing.stdout:
        vm.run(
            "hyprconf keybind add bind SUPER F12 exec hyprconf-test-sentinel 2>&1"
        )
        listing = vm.run("hyprconf keybind list 2>&1", check=False)

    # Find its 1-based index
    idx = None
    for line in listing.stdout.splitlines():
        if "hyprconf-test-sentinel" in line and line.strip() and line.strip()[0].isdigit():
            idx = line.split()[0].strip()
            break
    assert idx is not None, "Sentinel keybind not found in list"

    del_result = vm.run(f"hyprconf keybind delete {idx} 2>&1", check=False)
    assert del_result.returncode == 0
    assert "Deleted" in del_result.stdout

    final = vm.run("hyprconf keybind list 2>&1", check=False)
    assert "hyprconf-test-sentinel" not in final.stdout


# ---------------------------------------------------------------------------
# hyprconf rule
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_rule_window_list_runs_without_error(vm: VMClient) -> None:
    """hyprconf rule window list does not crash."""
    result = vm.run("hyprconf rule window list 2>&1", check=False)
    assert result.returncode == 0


@pytest.mark.vm
def test_rule_window_add_creates_entry(vm: VMClient) -> None:
    """hyprconf rule window add appends a new window rule."""
    add = vm.run(
        "hyprconf rule window add float 'class:hyprconf-test-window' 2>&1",
        check=False,
    )
    assert add.returncode == 0
    assert "Added" in add.stdout

    listing = vm.run("hyprconf rule window list 2>&1", check=False)
    assert "hyprconf-test-window" in listing.stdout


@pytest.mark.vm
def test_rule_window_delete_removes_entry(vm: VMClient) -> None:
    """hyprconf rule window delete removes the rule at the given index."""
    # Ensure test rule exists
    listing = vm.run("hyprconf rule window list 2>&1", check=False)
    if "hyprconf-test-window" not in listing.stdout:
        vm.run(
            "hyprconf rule window add float 'class:hyprconf-test-window' 2>&1"
        )
        listing = vm.run("hyprconf rule window list 2>&1", check=False)

    idx = None
    for line in listing.stdout.splitlines():
        if "hyprconf-test-window" in line and line.strip() and line.strip()[0].isdigit():
            idx = line.split()[0].strip()
            break
    assert idx is not None, "Test rule not found in list"

    del_result = vm.run(f"hyprconf rule window delete {idx} 2>&1", check=False)
    assert del_result.returncode == 0
    assert "Deleted" in del_result.stdout

    final = vm.run("hyprconf rule window list 2>&1", check=False)
    assert "hyprconf-test-window" not in final.stdout


# ---------------------------------------------------------------------------
# hyprconf monitor (set / delete — list already covered above)
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_monitor_set_writes_config(vm: VMClient) -> None:
    """hyprconf monitor config set creates a monitor entry in monitors.conf."""
    monitor_name = "HYPRCONF-TEST-MON"
    set_result = vm.run(
        f"hyprconf monitor config set {monitor_name} 1920x1080 0x0 1 2>&1",
        check=False,
    )
    assert set_result.returncode == 0
    assert "Set" in set_result.stdout

    conf = vm.read_file("~/.config/hypr/monitors.conf")
    assert monitor_name in conf


@pytest.mark.vm
def test_monitor_delete_removes_entry(vm: VMClient) -> None:
    """hyprconf monitor config delete removes the named monitor entry."""
    monitor_name = "HYPRCONF-TEST-MON"
    # Ensure it exists
    vm.run(
        f"hyprconf monitor config set {monitor_name} 1920x1080 0x0 1 2>&1",
        check=False,
    )

    del_result = vm.run(
        f"hyprconf monitor config delete {monitor_name} 2>&1",
        check=False,
    )
    assert del_result.returncode == 0
    assert "Deleted" in del_result.stdout

    listing = vm.run("hyprconf monitor list 2>&1", check=False)
    assert monitor_name not in listing.stdout


# ---------------------------------------------------------------------------
# hyprconf lock
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_lock_list_runs_without_error(vm: VMClient) -> None:
    """hyprconf lock list does not crash."""
    result = vm.run("hyprconf lock list 2>&1", check=False)
    assert result.returncode == 0


@pytest.mark.vm
def test_lock_add_set_delete(vm: VMClient) -> None:
    """hyprconf lock add creates a block; set updates a field; delete removes it."""
    before = vm.run("hyprconf lock list 2>&1", check=False)
    before_count = sum(
        1 for l in before.stdout.splitlines()
        if l.strip() and l.strip()[0].isdigit()
    )

    add = vm.run("hyprconf lock add background 2>&1", check=False)
    assert add.returncode == 0
    assert "Added" in add.stdout

    new_idx = before_count + 1
    set_result = vm.run(
        f"hyprconf lock set {new_idx} blur_passes 3 2>&1",
        check=False,
    )
    assert set_result.returncode == 0
    assert "Set" in set_result.stdout

    del_result = vm.run(
        f"hyprconf lock delete {new_idx} 2>&1",
        check=False,
    )
    assert del_result.returncode == 0
    assert "Deleted" in del_result.stdout


# ---------------------------------------------------------------------------
# hyprconf idle
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_idle_list_runs_without_error(vm: VMClient) -> None:
    """hyprconf idle list does not crash."""
    result = vm.run("hyprconf idle list 2>&1", check=False)
    assert result.returncode == 0


@pytest.mark.vm
def test_idle_add_set_delete(vm: VMClient) -> None:
    """hyprconf idle add listener creates a block; set updates timeout; delete removes it."""
    before = vm.run("hyprconf idle list 2>&1", check=False)
    before_count = sum(
        1 for l in before.stdout.splitlines()
        if l.strip() and l.strip()[0].isdigit()
    )

    add = vm.run("hyprconf idle add listener 2>&1", check=False)
    assert add.returncode == 0
    assert "Added" in add.stdout

    new_idx = before_count + 1
    set_result = vm.run(
        f"hyprconf idle set {new_idx} timeout 600 2>&1",
        check=False,
    )
    assert set_result.returncode == 0
    assert "Set" in set_result.stdout

    del_result = vm.run(
        f"hyprconf idle delete {new_idx} 2>&1",
        check=False,
    )
    assert del_result.returncode == 0
    assert "Deleted" in del_result.stdout


# ---------------------------------------------------------------------------
# hyprconf sync (idempotency)
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_sync_is_idempotent(vm: VMClient) -> None:
    """Running hyprconf sync twice both succeed."""
    first  = vm.run("hyprconf sync --no-reload 2>&1", check=False)
    second = vm.run("hyprconf sync --no-reload 2>&1", check=False)
    assert first.returncode  == 0, f"First sync failed:\n{first.stdout}"
    assert second.returncode == 0, f"Second sync failed:\n{second.stdout}"


# ---------------------------------------------------------------------------
# hyprconf tui
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_tui_launches_cleanly(vm: VMClient) -> None:
    """hyprconf tui starts without crashing (3-second headless smoke test)."""
    dep = vm.run("python3 -c 'import textual' 2>&1", check=False)
    if dep.returncode != 0:
        pytest.skip("python-textual not installed in VM")

    # Run with a 3-second timeout; 0=clean exit, 124=timeout-killed — both fine.
    result = vm.run(
        "timeout 3 hyprconf tui 2>/dev/null; "
        "rc=$?; [[ $rc -eq 0 || $rc -eq 124 ]] && echo PASS || echo FAIL:$rc",
        check=False,
    )
    assert "PASS" in result.stdout, (
        f"TUI did not launch cleanly: stdout={result.stdout!r}"
    )


# ---------------------------------------------------------------------------
# hyprconf theme
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_theme_list_shows_themes(vm: VMClient) -> None:
    """hyprconf theme list outputs a table containing theme names."""
    result = vm.run("hyprconf theme list 2>&1", check=False)
    assert result.returncode == 0
    assert "dracula" in result.stdout.lower()


@pytest.mark.vm
def test_theme_current_returns_name(vm: VMClient) -> None:
    """hyprconf theme current prints the active theme name."""
    result = vm.run("hyprconf theme current 2>&1", check=False)
    assert result.returncode == 0
    assert result.stdout.strip() != ""


@pytest.mark.vm
def test_theme_set_switches_theme(vm: VMClient) -> None:
    """hyprconf theme set <name> exits 0 and reports the switch."""
    result = vm.run("hyprconf theme set dracula 2>&1", check=False)
    assert result.returncode == 0
    assert "dracula" in result.stdout.lower()


# ---------------------------------------------------------------------------
# hyprconf repair
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_repair_runs_successfully(vm: VMClient) -> None:
    """hyprconf repair exits 0 and reports no issues."""
    result = vm.run("hyprconf repair 2>&1", check=False)
    assert result.returncode == 0
    assert "healthy" in result.stdout.lower() or "stowed" in result.stdout.lower()


# ---------------------------------------------------------------------------
# hyprconf show
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_show_keybinds_outputs_table(vm: VMClient) -> None:
    """hyprconf show keybinds prints a formatted keybinds table."""
    result = vm.run("hyprconf show keybinds 2>&1", check=False)
    assert result.returncode == 0
    assert "SUPER" in result.stdout or "mainMod" in result.stdout.lower()


# ---------------------------------------------------------------------------
# hyprconf set mainMod
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_set_mainmod_writes_overrides_file(vm: VMClient) -> None:
    """hyprconf set mainMod SUPER persists $mainMod in the overrides file."""
    result = vm.run("hyprconf set mainMod SUPER 2>&1", check=False)
    assert result.returncode == 0
    conf = vm.read_file("~/.config/hypr/conf.d/99-hyprconf-local.conf")
    assert "$mainMod = SUPER" in conf


# ---------------------------------------------------------------------------
# hyprconf paper
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_paper_list_runs_without_error(vm: VMClient) -> None:
    """hyprconf paper list does not crash."""
    result = vm.run("hyprconf paper list 2>&1", check=False)
    assert result.returncode == 0


@pytest.mark.vm
def test_paper_set_wallpaper_writes_config(vm: VMClient) -> None:
    """hyprconf paper set-wallpaper writes the entry to hyprpaper.conf."""
    wallpaper_path = "~/wallpaper/dracula.png"
    result = vm.run(
        f"hyprconf paper set-wallpaper VIRTUAL-1 {wallpaper_path} 2>&1",
        check=False,
    )
    assert result.returncode == 0
    conf = vm.read_file("~/.config/hypr/hyprpaper.conf")
    assert "VIRTUAL-1" in conf


# ---------------------------------------------------------------------------
# hyprconf deploy
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_deploy_list_runs_without_error(vm: VMClient) -> None:
    """hyprconf deploy list exits 0 (empty list is valid)."""
    result = vm.run("hyprconf deploy list 2>&1", check=False)
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# hyprconf configure
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_configure_requires_interactive_tty(vm: VMClient) -> None:
    """hyprconf configure exits non-zero with a clear message over SSH."""
    result = vm.run("hyprconf configure 2>&1", check=False)
    assert result.returncode != 0
    assert "tty" in result.stdout.lower() or "interactive" in result.stdout.lower()


# ---------------------------------------------------------------------------
# hyprconf display
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_display_unknown_subcommand_exits_nonzero(vm: VMClient) -> None:
    """hyprconf display <unknown> exits non-zero with an error message."""
    result = vm.run("hyprconf display unknown-sub 2>&1", check=False)
    assert result.returncode != 0
    assert "unknown" in result.stdout.lower() or "unknown" in result.stderr.lower()
