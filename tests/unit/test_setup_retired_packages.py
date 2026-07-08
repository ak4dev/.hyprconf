"""Tests for remove_retired_packages() — the waybar → quickshell migration.

Retiring a stow package from the repo strands existing installs: `packages`
is additive, stow cannot unstow a package whose source dir is gone, and
nothing else prunes the pacman package. remove_retired_packages() closes the
gap on sync: it drops the now-empty ~/.config/waybar dir (its dangling links
are pruned by purge_broken_symlinks, which runs first in both flows) and
offers — never forces — removal of the retired package(s).

Covers:
- structure: defined, prompt gated on `[[ -t 0 ]]`, wired into install AND
  sync paths, and always ordered after purge_broken_symlinks.
- behaviour (real function body, fake pacman/sudo): silent no-op when nothing
  is installed, non-interactive default = keep, interactive y/n, and the
  config-dir cleanup that must never touch user files.
"""

from __future__ import annotations

import os
import pty
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
SETUP_SH = REPO_ROOT / "setup.sh"


# ---------------------------------------------------------------------------
# Harness (same shape as test_no_aur_policy.py)
# ---------------------------------------------------------------------------


def _setup_text() -> str:
    return SETUP_SH.read_text()


def _extract_function(name: str) -> str:
    """Return the body of a bash function from setup.sh via awk."""
    result = subprocess.run(
        ["awk", f"/^{name}\\(\\)/,/^\\}}$/", str(SETUP_SH)],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _make_fakes(tmp_path: Path) -> tuple[Path, Path]:
    """Fake `pacman` (-Q honours FAKE_INSTALLED, -Rns logs) and `sudo`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    rns_log = tmp_path / "rns.log"

    pacman = bindir / "pacman"
    pacman.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "${1:-}" == "-Q" ]]; then\n'
        "  for p in ${FAKE_INSTALLED:-}; do\n"
        '    [[ "$p" == "${2:-}" ]] && exit 0\n'
        "  done\n"
        "  exit 1\n"
        "fi\n"
        'if [[ "${1:-}" == "-Rns" ]]; then\n'
        "  shift\n"
        '  [[ "${1:-}" == "--noconfirm" ]] && shift\n'
        '  printf \'RNS %s\\n\' "$*" >> "$RNS_LOG"\n'
        "  exit 0\n"
        "fi\n"
        "exit 0\n"
    )
    pacman.chmod(0o755)

    sudo = bindir / "sudo"
    sudo.write_text('#!/usr/bin/env bash\nexec "$@"\n')
    sudo.chmod(0o755)

    return bindir, rns_log


def _fragment() -> str:
    """Runnable bash program: stubbed logging + the real function body."""
    return "\n".join(
        [
            "set -euo pipefail",
            "WH=''; RS=''",
            "log_step(){ printf '%s\\n' \"$*\"; }",
            "log_ok(){ printf '%s\\n' \"$*\"; }",
            "log_warn(){ printf '%s\\n' \"$*\"; }",
            _extract_function("remove_retired_packages"),
            "remove_retired_packages",
        ]
    )


def _env(bindir: Path, rns_log: Path, home: Path, installed: str) -> dict[str, str]:
    return {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "RNS_LOG": str(rns_log),
        "FAKE_INSTALLED": installed,
        "HOME": str(home),
    }


def _run(bindir: Path, rns_log: Path, home: Path, installed: str) -> subprocess.CompletedProcess:
    """Non-interactive run (stdin = /dev/null → `[[ -t 0 ]]` is false)."""
    return subprocess.run(
        ["bash", "-c", _fragment()],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=_env(bindir, rns_log, home, installed),
    )


def _run_tty(bindir: Path, rns_log: Path, home: Path, installed: str, answer: str) -> str:
    """Run with a pty on stdin and feed `answer`; returns combined output."""
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        ["bash", "-c", _fragment()],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=_env(bindir, rns_log, home, installed),
    )
    os.close(slave)
    os.write(master, answer.encode())
    out, _ = proc.communicate(timeout=30)
    os.close(master)
    return out


# ---------------------------------------------------------------------------
# 1. Structure and wiring
# ---------------------------------------------------------------------------


class TestRetiredStructure:
    def test_function_defined_and_covers_waybar(self) -> None:
        func = _extract_function("remove_retired_packages")
        assert func, "remove_retired_packages() must exist in setup.sh"
        assert "waybar" in func, "waybar must be on the retired list"
        assert "pacman -Rns" in func, "must remove via pacman -Rns"

    def test_prompt_gated_on_interactive_stdin(self) -> None:
        func = _extract_function("remove_retired_packages")
        assert "-t 0" in func, "must gate the removal prompt on an interactive stdin"

    def test_wired_into_install_and_sync(self) -> None:
        call_lines = [
            line for line in _setup_text().splitlines() if line.strip() == "remove_retired_packages"
        ]
        assert len(call_lines) >= 2, (
            "remove_retired_packages must run in both install and sync paths"
        )

    def test_runs_after_symlink_purge_in_both_paths(self) -> None:
        """The rmdir cleanup relies on purge_broken_symlinks having already
        pruned the dangling waybar links, in every flow that calls it."""
        lines = [ln.strip() for ln in _setup_text().splitlines()]
        purge_calls = [i for i, ln in enumerate(lines) if ln == "purge_broken_symlinks"]
        retired_calls = [i for i, ln in enumerate(lines) if ln == "remove_retired_packages"]
        assert purge_calls and retired_calls
        for r in retired_calls:
            assert any(p < r for p in purge_calls), (
                "remove_retired_packages must come after a purge_broken_symlinks call"
            )


# ---------------------------------------------------------------------------
# 2. Behaviour
# ---------------------------------------------------------------------------


class TestRetiredBehaviour:
    def test_silent_noop_when_nothing_installed(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        res = _run(bindir, rns_log, tmp_path, installed="")
        assert res.returncode == 0
        assert "waybar" not in res.stdout, "must stay quiet on clean systems"
        assert not rns_log.exists()

    def test_noninteractive_defaults_to_keep(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        res = _run(bindir, rns_log, tmp_path, installed="waybar")
        assert res.returncode == 0
        assert "waybar" in res.stdout, "must tell the user what is retired"
        assert not rns_log.exists(), "non-interactive run must default to NOT removing"

    def test_interactive_yes_removes(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        _run_tty(bindir, rns_log, tmp_path, installed="waybar", answer="y\n")
        assert rns_log.exists(), "confirming should invoke pacman -Rns"
        assert "waybar" in rns_log.read_text()

    def test_interactive_no_keeps(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        out = _run_tty(bindir, rns_log, tmp_path, installed="waybar", answer="n\n")
        assert not rns_log.exists(), "declining must not remove anything"
        assert "pacman -Rns" in out, "must print the manual removal command"

    def test_removes_empty_waybar_config_dir(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        waybar_dir = tmp_path / ".config" / "waybar"
        waybar_dir.mkdir(parents=True)
        res = _run(bindir, rns_log, tmp_path, installed="")
        assert res.returncode == 0
        assert not waybar_dir.exists(), "empty retired config dir must be cleaned up"

    def test_keeps_waybar_config_dir_with_user_files(self, tmp_path: Path) -> None:
        bindir, rns_log = _make_fakes(tmp_path)
        waybar_dir = tmp_path / ".config" / "waybar"
        waybar_dir.mkdir(parents=True)
        user_file = waybar_dir / "my-own-config.jsonc"
        user_file.write_text("{}\n")
        res = _run(bindir, rns_log, tmp_path, installed="")
        assert res.returncode == 0
        assert user_file.exists(), "a dir holding real user files must never be touched"
