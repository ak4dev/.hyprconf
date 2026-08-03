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

import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest

SWITCH_THEME = "python3 ~/.config/hypr/scripts/theme-switcher/switch_theme.py"

# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------


class VMClient:
    """Thin wrapper around SSH commands to the test VM."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2222,
        user: str = "hyprtest",
        key: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.key = key or Path.home() / ".ssh" / "hyprconf_vm_key"

    def run(self, cmd: str, *, check: bool = True) -> subprocess.CompletedProcess:
        ssh_args = [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ConnectTimeout=10",
            "-i",
            str(self.key),
            "-p",
            str(self.port),
            f"{self.user}@{self.host}",
            cmd,
        ]
        return subprocess.run(ssh_args, capture_output=True, text=True, check=check)

    def read_file(self, remote_path: str) -> str:
        result = self.run(f"cat {remote_path}")
        return result.stdout


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
# setup.sh --sync
# ---------------------------------------------------------------------------


@pytest.mark.vm
def test_sync_completes_successfully(vm: VMClient) -> None:
    result = vm.run("bash ~/.hyprconf/setup.sh --sync 2>&1", check=False)
    assert result.returncode == 0
    assert "Sync complete" in result.stdout


@pytest.mark.vm
def test_sync_is_idempotent(vm: VMClient) -> None:
    """Running setup.sh --sync twice both succeed."""
    first = vm.run("bash ~/.hyprconf/setup.sh --sync 2>&1", check=False)
    second = vm.run("bash ~/.hyprconf/setup.sh --sync 2>&1", check=False)
    assert first.returncode == 0
    assert second.returncode == 0
    assert "Sync complete" in second.stdout


# ---------------------------------------------------------------------------
# Hyprland health check
# ---------------------------------------------------------------------------


@pytest.mark.vm
def test_hyprland_config_has_no_errors(vm: VMClient) -> None:
    """Hyprland --verify-config passes without errors on the installed config.

    Hyprland auto-discovers hyprland.lua over hyprland.conf when both are
    present (0.55+; see docs/hyprland-reference.md), so this exercises the
    Lua config now shipped — no path is hardcoded here. If --verify-config's
    output wording changes for a Lua entrypoint on the VM's installed
    Hyprland version, update the assertion below to match.
    """
    result = vm.run("Hyprland --verify-config 2>&1", check=False)
    assert result.returncode == 0, f"Hyprland config has errors:\n{result.stdout}"
    assert "config ok" in result.stdout.lower()


# ---------------------------------------------------------------------------
# hyprconf (TUI launcher)
# ---------------------------------------------------------------------------


@pytest.mark.vm
def test_tui_launches_cleanly(vm: VMClient) -> None:
    """hyprconf starts the TUI without crashing (3-second headless smoke test)."""
    dep = vm.run("python3 -c 'import textual' 2>&1", check=False)
    if dep.returncode != 0:
        pytest.skip("python-textual not installed in VM")

    # Run with a 3-second timeout; 0=clean exit, 124=timeout-killed — both fine.
    result = vm.run(
        "timeout 3 hyprconf 2>/dev/null; "
        "rc=$?; [[ $rc -eq 0 || $rc -eq 124 ]] && echo PASS || echo FAIL:$rc",
        check=False,
    )
    assert "PASS" in result.stdout, f"TUI did not launch cleanly: stdout={result.stdout!r}"


# ---------------------------------------------------------------------------
# theme switcher
# ---------------------------------------------------------------------------


@pytest.mark.vm
def test_theme_list_shows_themes(vm: VMClient) -> None:
    """switch_theme.py --list outputs a table containing theme names."""
    result = vm.run(f"{SWITCH_THEME} --list 2>&1", check=False)
    assert result.returncode == 0
    assert "dracula" in result.stdout.lower()


@pytest.mark.vm
def test_theme_current_returns_name(vm: VMClient) -> None:
    """switch_theme.py --current prints the active theme name."""
    result = vm.run(f"{SWITCH_THEME} --current 2>&1", check=False)
    assert result.returncode == 0
    assert result.stdout.strip() != ""


@pytest.mark.vm
def test_theme_set_switches_theme(vm: VMClient) -> None:
    """switch_theme.py <name> exits 0 and reports the switch."""
    result = vm.run(f"{SWITCH_THEME} dracula --no-reload 2>&1", check=False)
    assert result.returncode == 0, f"theme apply failed:\n{result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# Branch model — dev → stable release model
# ---------------------------------------------------------------------------


@pytest.mark.vm
def test_repo_has_stable_remote_ref(vm: VMClient) -> None:
    """VM bundle includes origin/stable.

    If this test fails, rebuild the VM with: bash tests/vm/run_vm.sh --wait
    """
    result = vm.run(
        "git -C ~/.hyprconf show-ref --verify refs/remotes/origin/stable 2>&1",
        check=False,
    )
    assert result.returncode == 0, (
        "origin/stable not found in VM repo. "
        "Re-run: bash tests/vm/run_vm.sh --wait  (updated to bundle stable)"
    )
