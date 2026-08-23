"""Tests for stow/hypr/.local/bin/hc — a pure argv-forwarding alias table.

hc has no logic beyond dispatch (see AGENTS.md — it must never grow argument
parsing/validation of its own), so these tests only need to verify each
subcommand forwards to the correct real tool with the remaining args passed
through untouched.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent.parent / "stow" / "hypr" / ".local" / "bin" / "hc"


def _make_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _stub(name: str) -> str:
    return f'#!/usr/bin/env bash\nprintf "CALLED:{name}:%s\\n" "$*"\n'


def _run(args: list[str], bin_dir: Path, home_dir: Path):
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["HOME"] = str(home_dir)
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, timeout=10
    )


class TestHcForwarding:
    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        bin_dir = tmp_path / "bin"
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        bin_dir.mkdir()

        scripts_dir = home_dir / ".config" / "hypr" / "scripts"
        _make_executable(scripts_dir / "gpu-passthrough.sh", _stub("gpu-passthrough.sh"))
        _make_executable(
            scripts_dir / "theme-switcher" / "switch_theme.py", _stub("switch_theme.py")
        )
        _make_executable(home_dir / ".hyprconf" / "setup.sh", _stub("setup.sh"))

        for name in ("hyprconf-secureboot", "hyprconf-vpn", "yubikey-fido2-setup"):
            _make_executable(bin_dir / name, _stub(name))

        return bin_dir, home_dir

    def test_vm_forwards_to_gpu_passthrough_vm_subtree(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["vm", "arch", "launch", "--force"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:gpu-passthrough.sh:vm arch launch --force"

    def test_gpu_forwards_to_gpu_passthrough_directly(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["gpu", "audit"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:gpu-passthrough.sh:audit"

    def test_secureboot_forwards_with_args_intact(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["secureboot", "verify"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:hyprconf-secureboot:verify"

    def test_vpn_forwards(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["vpn", "status"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:hyprconf-vpn:status"

    def test_yubikey_forwards(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["yubikey"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:yubikey-fido2-setup:"

    def test_theme_forwards(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["theme", "--random"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:switch_theme.py:--random"

    def test_sync_forwards(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["sync"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:setup.sh:--sync"

    def test_sync_passes_through_extra_flags(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["sync", "--force"], bin_dir, home_dir)
        assert r.returncode == 0, f"stderr: {r.stderr}"
        assert r.stdout.strip() == "CALLED:setup.sh:--sync --force"

    def test_unknown_tool_exits_nonzero_with_usage(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run(["bogus"], bin_dir, home_dir)
        assert r.returncode != 0
        assert "Usage: hc" in r.stderr

    def test_no_args_exits_nonzero_with_usage(self, tmp_path):
        bin_dir, home_dir = self._setup(tmp_path)
        r = _run([], bin_dir, home_dir)
        assert r.returncode != 0
        assert "Usage: hc" in r.stderr
