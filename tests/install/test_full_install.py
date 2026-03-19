"""
Full install smoke tests — require a Packer-built Arch+hyprconf VM image.

All tests are marked ``@pytest.mark.install`` and are SKIPPED unless pytest
is invoked with ``--run-install``.

Prerequisites:

1. Build the image (only needed once, or when re-testing install.sh)::

       bash tests/install/build_image.sh

2. Start the install VM on port 2223::

       bash tests/install/run_install_vm.sh

3. Run::

       pytest tests/install/ --run-install -v

``scripts/publish`` handles steps 1–3 automatically, including an interactive
prompt to reuse an existing image or rebuild from scratch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Re-use VMClient from the vm test module
# ---------------------------------------------------------------------------

_VM_TEST_DIR = Path(__file__).parent.parent / "vm"
if str(_VM_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_VM_TEST_DIR))

from test_hyprland_integration import VMClient  # noqa: E402

# ---------------------------------------------------------------------------
# Install-VM connection constants
# ---------------------------------------------------------------------------

_INSTALL_VM_HOST = "127.0.0.1"
_INSTALL_VM_PORT = 2223
_INSTALL_VM_USER = "hyprtest"


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def install_vm() -> Generator[VMClient, None, None]:
    """Session-scoped client for the freshly-installed Arch+hyprconf VM."""
    client = VMClient(
        host=_INSTALL_VM_HOST,
        port=_INSTALL_VM_PORT,
        user=_INSTALL_VM_USER,
    )
    try:
        result = client.run("echo ok", check=True)
        assert result.stdout.strip() == "ok", "Install VM SSH not responding"
    except Exception as exc:
        pytest.skip(f"Install VM not reachable on port {_INSTALL_VM_PORT}: {exc}")
    yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.install
def test_hyprconf_binary_on_path(install_vm: VMClient) -> None:
    """hyprconf binary is on PATH after install."""
    result = install_vm.run("which hyprconf", check=False)
    assert result.returncode == 0
    assert "hyprconf" in result.stdout


@pytest.mark.install
def test_config_dir_exists(install_vm: VMClient) -> None:
    """~/.config/hypr/ exists and contains hyprland.conf."""
    result = install_vm.run(
        "test -f ~/.config/hypr/hyprland.conf && echo OK",
        check=False,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


@pytest.mark.install
def test_stow_packages_deployed(install_vm: VMClient) -> None:
    """Key stow-managed files are present under ~/.config/hypr/."""
    required_files = [
        "~/.config/hypr/hyprland.conf",
        "~/.config/hypr/keybinds.conf",
        "~/.config/hypr/monitors.conf",
        "~/.config/hypr/hyprlock.conf",
        "~/.config/hypr/hypridle.conf",
    ]
    for path in required_files:
        result = install_vm.run(f"test -e {path} && echo OK", check=False)
        assert result.returncode == 0 and "OK" in result.stdout, (
            f"Expected stowed file missing: {path}"
        )


@pytest.mark.install
def test_packages_installed(install_vm: VMClient) -> None:
    """All non-comment, non-optional packages in the packages file are installed."""
    # Read package names from the cloned repo on the VM
    pkg_result = install_vm.run(
        "grep -v '^\\s*#' ~/.hyprconf/packages | grep -v '^\\s*$'",
        check=False,
    )
    if pkg_result.returncode != 0:
        pytest.skip("packages file not found on install VM")

    packages = [p.strip() for p in pkg_result.stdout.splitlines() if p.strip()]
    if not packages:
        pytest.skip("packages file is empty")

    # Check all in a single pacman query
    pkg_list = " ".join(packages)
    check = install_vm.run(
        f"pacman -Q {pkg_list} 2>&1",
        check=False,
    )
    assert check.returncode == 0, (
        f"One or more packages not installed:\n{check.stdout}"
    )


@pytest.mark.install
def test_hyprconf_schema_works(install_vm: VMClient) -> None:
    """hyprconf schema dump outputs valid JSON after install."""
    result = install_vm.run("hyprconf schema dump 2>&1", check=False)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, dict) and len(data) > 0


@pytest.mark.install
def test_hyprconf_get_works(install_vm: VMClient) -> None:
    """hyprconf get general gaps_in returns a value."""
    result = install_vm.run("hyprconf get general gaps_in 2>&1", check=False)
    assert result.returncode == 0
    assert "general:gaps_in" in result.stdout


@pytest.mark.install
def test_hyprconf_set_persists(install_vm: VMClient) -> None:
    """hyprconf set <section> <key> <value> persists across a re-get."""
    install_vm.run("hyprconf set general gaps_in 99 2>&1")
    result = install_vm.run("hyprconf get general gaps_in 2>&1", check=False)
    assert result.returncode == 0
    assert "99" in result.stdout
    # Reset to default
    install_vm.run("hyprconf set general gaps_in 5 2>&1", check=False)


@pytest.mark.install
def test_no_broken_symlinks(install_vm: VMClient) -> None:
    """There are no broken symlinks under ~/.config/hypr/."""
    result = install_vm.run(
        "find ~/.config/hypr -xtype l 2>/dev/null",
        check=False,
    )
    broken = [l for l in result.stdout.splitlines() if l.strip()]
    assert not broken, f"Broken symlinks found:\n" + "\n".join(broken)


@pytest.mark.install
def test_hyprconf_sync_idempotent(install_vm: VMClient) -> None:
    """Running hyprconf sync twice both succeed without error."""
    first  = install_vm.run("hyprconf sync --no-reload 2>&1", check=False)
    second = install_vm.run("hyprconf sync --no-reload 2>&1", check=False)
    assert first.returncode  == 0, f"First sync failed:\n{first.stdout}"
    assert second.returncode == 0, f"Second sync failed:\n{second.stdout}"
