"""
VM integration tests — require a live Hyprland session inside QEMU/KVM.

All tests in this file are marked @pytest.mark.vm and are SKIPPED unless
pytest is invoked with --run-vm.  A running QEMU VM with SSH on port 2222
is expected.

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
                 user: str = "user", key: Path | None = None) -> None:
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
def test_set_gaps_in_updates_hyprctl(vm: VMClient) -> None:
    vm.run("hyprconf set general gaps_in 12")
    result = vm.run("hyprctl getoption general:gaps_in -j")
    data = json.loads(result.stdout)
    assert data["int"] == 12


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
    # List available monitors from hyprctl
    result = vm.run("hyprctl monitors -j")
    monitors = json.loads(result.stdout)
    if not monitors:
        pytest.skip("No monitors in VM")
    monitor_name = monitors[0]["name"]

    vm.run(f"hyprconf monitor config set {monitor_name} preferred auto 1")
    conf = vm.read_file("~/.config/hypr/monitors.conf")
    assert monitor_name in conf


# ---------------------------------------------------------------------------
# Hyprland health check
# ---------------------------------------------------------------------------

@pytest.mark.vm
def test_hyprland_reports_no_errors(vm: VMClient) -> None:
    result = vm.run("hyprctl rollinglog 2>&1", check=False)
    if result.returncode != 0:
        pytest.skip("hyprctl not available or Hyprland not running")
    log = result.stdout
    assert "[error]" not in log.lower(), f"Hyprland logged errors:\n{log}"
