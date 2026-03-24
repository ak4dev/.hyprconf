"""Unit / functional tests for wvkbd-launcher.

Strategy:
  - Source inspection tests verify key patterns in the script text.
  - Functional tests create stub binaries and run the script in a
    controlled environment (fake $PATH, tmp HOME) to verify behaviour.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
WVKBD_LAUNCHER = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "wvkbd-launcher"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_exe(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run_launcher(tmp_path: Path, *, colors: str = "", extra_env: dict | None = None):
    """Run wvkbd-launcher in a controlled environment.

    A fake wvkbd-mobintl in bin_dir captures arguments and exits 0.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)

    arg_log = tmp_path / "wvkbd_args.txt"
    # Fake wvkbd-mobintl: capture args and exit 0
    _write_exe(bin_dir / "wvkbd-mobintl", f"""\
#!/usr/bin/env bash
echo "$@" > {arg_log}
# Simulate --help output (no color support) when called with --help
if [[ "$1" == "--help" ]]; then
    echo "Usage: wvkbd-mobintl [OPTIONS]"
    echo "  --hidden   start hidden"
    exit 0
fi
exit 0
""")

    # Write colors file if provided
    xdg_cfg = home / ".config"
    if colors:
        wvkbd_dir = xdg_cfg / "wvkbd"
        wvkbd_dir.mkdir(parents=True, exist_ok=True)
        (wvkbd_dir / "colors").write_text(colors)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(xdg_cfg)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        ["bash", str(WVKBD_LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result, arg_log


def _run_launcher_no_wvkbd(tmp_path: Path):
    """Run launcher without wvkbd-mobintl on PATH — expects failure."""
    # Use an isolated bin_dir that contains nothing — wvkbd-mobintl absent
    bin_dir = tmp_path / "empty_bin"
    bin_dir.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)

    env = os.environ.copy()
    env["HOME"] = str(home)
    # Only expose the empty bin_dir — wvkbd-mobintl not present
    env["PATH"] = str(bin_dir)

    return subprocess.run(
        ["/usr/bin/bash", str(WVKBD_LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


# ---------------------------------------------------------------------------
# Source-inspection tests
# ---------------------------------------------------------------------------

def test_wvkbd_launcher_has_shebang():
    content = WVKBD_LAUNCHER.read_text()
    assert content.startswith("#!/usr/bin/env bash")


def test_wvkbd_launcher_has_set_euo():
    content = WVKBD_LAUNCHER.read_text()
    assert "set -euo pipefail" in content


def test_wvkbd_launcher_checks_for_wvkbd_mobintl():
    content = WVKBD_LAUNCHER.read_text()
    assert "wvkbd-mobintl" in content


def test_wvkbd_launcher_always_passes_hidden_flag():
    content = WVKBD_LAUNCHER.read_text()
    assert "--hidden" in content


def test_wvkbd_launcher_reads_xdg_config_home():
    """Colors file path must use $XDG_CONFIG_HOME or HOME/.config fallback."""
    content = WVKBD_LAUNCHER.read_text()
    assert "XDG_CONFIG_HOME" in content or "wvkbd/colors" in content


def test_wvkbd_launcher_uses_pgrep_to_kill_existing():
    """Must use pgrep to find existing wvkbd-mobintl PIDs (no pkill/killall)."""
    content = WVKBD_LAUNCHER.read_text()
    assert "pgrep" in content
    assert "pkill" not in content
    assert "killall" not in content


def test_wvkbd_launcher_uses_kill_not_pkill():
    """Must use `kill` with explicit PID, not pkill/killall."""
    content = WVKBD_LAUNCHER.read_text()
    assert "kill " in content
    assert "pkill" not in content


# ---------------------------------------------------------------------------
# Functional tests
# ---------------------------------------------------------------------------

def test_wvkbd_launcher_exits_nonzero_without_wvkbd(tmp_path):
    result = _run_launcher_no_wvkbd(tmp_path)
    assert result.returncode != 0
    assert "wvkbd-mobintl" in result.stderr or "not found" in result.stderr.lower()


def test_wvkbd_launcher_passes_hidden_to_wvkbd(tmp_path):
    result, arg_log = _run_launcher(tmp_path)
    assert result.returncode == 0, f"Launcher failed: {result.stderr}"
    args = arg_log.read_text().strip()
    assert "--hidden" in args


def test_wvkbd_launcher_passes_color_flags_when_available(tmp_path):
    """When colors file has valid hex values and wvkbd supports --bg, pass them."""
    # Provide a fake wvkbd that reports --bg support in --help
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    arg_log = tmp_path / "wvkbd_args.txt"

    _write_exe(bin_dir / "wvkbd-mobintl", f"""\
#!/usr/bin/env bash
if [[ "$1" == "--help" ]]; then
    echo "  --bg COLOR  background"
    echo "  --fg COLOR  foreground"
    echo "  --press COLOR  press color"
    exit 0
fi
echo "$@" > {arg_log}
exit 0
""")

    xdg_cfg = home / ".config"
    wvkbd_dir = xdg_cfg / "wvkbd"
    wvkbd_dir.mkdir(parents=True)
    (wvkbd_dir / "colors").write_text(
        'bg="#282a36"\nfg="#f8f8f2"\naccent="#8be9fd"\n'
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(xdg_cfg)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    result = subprocess.run(
        ["bash", str(WVKBD_LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    args = arg_log.read_text().strip() if arg_log.exists() else ""
    assert "--bg" in args
    assert "#282a36" in args
    assert "--fg" in args
    assert "#f8f8f2" in args
    assert "--press" in args
    assert "#8be9fd" in args


def test_wvkbd_launcher_no_color_flags_without_support(tmp_path):
    """When wvkbd --help does NOT advertise --bg, no color flags are passed."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    arg_log = tmp_path / "wvkbd_args.txt"

    _write_exe(bin_dir / "wvkbd-mobintl", f"""\
#!/usr/bin/env bash
if [[ "$1" == "--help" ]]; then
    echo "Usage: wvkbd-mobintl [OPTIONS]"
    echo "  --hidden   start hidden"
    exit 0
fi
echo "$@" > {arg_log}
exit 0
""")

    xdg_cfg = home / ".config"
    wvkbd_dir = xdg_cfg / "wvkbd"
    wvkbd_dir.mkdir(parents=True)
    (wvkbd_dir / "colors").write_text(
        'bg="#282a36"\nfg="#f8f8f2"\naccent="#8be9fd"\n'
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(xdg_cfg)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    result = subprocess.run(
        ["bash", str(WVKBD_LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    args = arg_log.read_text().strip() if arg_log.exists() else ""
    assert "--bg" not in args
    assert "--fg" not in args


def test_wvkbd_launcher_works_without_colors_file(tmp_path):
    """Launcher must succeed even when no colors file exists."""
    result, arg_log = _run_launcher(tmp_path, colors="")
    assert result.returncode == 0, result.stderr
    args = arg_log.read_text().strip()
    assert "--hidden" in args
    # No color flags should be passed since colors file is absent
    assert "--bg" not in args


def test_wvkbd_launcher_ignores_invalid_hex_colors(tmp_path):
    """Colors with invalid hex values must not be passed to wvkbd."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    arg_log = tmp_path / "wvkbd_args.txt"

    _write_exe(bin_dir / "wvkbd-mobintl", f"""\
#!/usr/bin/env bash
if [[ "$1" == "--help" ]]; then
    echo "  --bg COLOR"
    exit 0
fi
echo "$@" > {arg_log}
exit 0
""")

    xdg_cfg = home / ".config"
    wvkbd_dir = xdg_cfg / "wvkbd"
    wvkbd_dir.mkdir(parents=True)
    (wvkbd_dir / "colors").write_text(
        'bg="notacolor"\nfg="alsonotvalid"\n'
    )

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(xdg_cfg)
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"

    result = subprocess.run(
        ["bash", str(WVKBD_LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    args = arg_log.read_text().strip() if arg_log.exists() else ""
    assert "--bg" not in args
