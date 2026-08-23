"""Applying a theme to the session that is already running.

Writing config files themes the *next* launch; these are the two pieces that
make a switch land on the current one — signalling apps that can re-read their
config, and keeping two switches from interleaving over the same files.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from hyprconf import live_theme


def _fake_proc(root: Path, processes: dict[int, str]) -> Path:
    """Build a /proc-shaped tree: {pid: comm}."""
    for pid, comm in processes.items():
        entry = root / str(pid)
        entry.mkdir(parents=True)
        (entry / "comm").write_text(f"{comm}\n", encoding="utf-8")
    # Non-numeric entries (/proc/self, /proc/meminfo …) must be skipped, not read.
    (root / "self").mkdir()
    (root / "meminfo").write_text("MemTotal: 1 kB\n", encoding="utf-8")
    return root


@pytest.fixture()
def fake_proc(tmp_path, monkeypatch):
    def _make(processes: dict[int, str]) -> Path:
        root = _fake_proc(tmp_path / "proc", processes)
        monkeypatch.setattr(live_theme, "PROC_ROOT", root)
        return root

    return _make


class TestRunningPids:
    def test_finds_every_instance_by_exact_comm(self, fake_proc):
        fake_proc({10: "kitty", 11: "kitty", 12: "btop"})
        assert live_theme.running_pids("kitty") == [10, 11]

    def test_does_not_match_on_a_prefix(self, fake_proc):
        """`kitty` must not match `kitty-wrapper`; comm is compared whole."""
        fake_proc({10: "kitty-wrapper"})
        assert live_theme.running_pids("kitty") == []

    def test_missing_proc_is_not_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(live_theme, "PROC_ROOT", tmp_path / "nope")
        assert live_theme.running_pids("kitty") == []


class TestReloadApp:
    def test_sends_each_app_the_signal_it_documents(self, fake_proc, monkeypatch):
        fake_proc({10: "kitty", 12: "btop"})
        sent: list[tuple[int, int]] = []
        monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)))

        assert live_theme.reload_app("kitty") == 1
        assert live_theme.reload_app("btop") == 1
        assert sent == [(10, signal.SIGUSR1), (12, signal.SIGUSR2)]

    def test_unknown_app_is_a_no_op(self, fake_proc, monkeypatch):
        fake_proc({10: "firefox"})
        monkeypatch.setattr(os, "kill", lambda pid, sig: pytest.fail("must not signal"))
        assert live_theme.reload_app("firefox") == 0

    @pytest.mark.parametrize("error", [ProcessLookupError, PermissionError, OSError])
    def test_a_process_that_cannot_be_signalled_is_skipped(self, fake_proc, monkeypatch, error):
        """It exited between the scan and the kill, or belongs to another user —
        a theme switch must not die on either."""
        fake_proc({10: "kitty", 11: "kitty"})

        def flaky(pid, sig):
            if pid == 10:
                raise error()

        monkeypatch.setattr(os, "kill", flaky)
        assert live_theme.reload_app("kitty") == 1

    def test_reports_only_the_apps_that_were_running(self, fake_proc, monkeypatch):
        fake_proc({12: "btop"})
        monkeypatch.setattr(os, "kill", lambda pid, sig: None)
        assert live_theme.reload_themed_apps() == {"btop": 1}

    def test_nothing_running_reports_nothing(self, fake_proc, monkeypatch):
        fake_proc({10: "firefox"})
        monkeypatch.setattr(os, "kill", lambda pid, sig: pytest.fail("must not signal"))
        assert live_theme.reload_themed_apps() == {}

    def test_only_reloadable_apps_are_listed(self):
        """Restarting an app to recolor it loses the user's session, so an app
        that cannot re-read its config in place must not be added here."""
        assert set(live_theme.RELOAD_SIGNALS) == {"kitty", "btop"}


class TestSwitchLock:
    def test_holds_the_lock_against_another_process(self, tmp_path, monkeypatch):
        monkeypatch.setattr(live_theme, "RUNTIME_DIR", tmp_path)
        lock_path = tmp_path / "hyprconf-theme-switch.lock"

        probe = textwrap.dedent(f"""
            import fcntl
            handle = open({str(lock_path)!r}, "w")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                print("free")
            except BlockingIOError:
                print("busy")
        """)

        with live_theme.switch_lock() as held:
            assert held is True
            busy = subprocess.run(
                [sys.executable, "-c", probe], capture_output=True, text=True, timeout=10
            )
        free = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=10
        )

        assert busy.stdout.strip() == "busy", "a second switch was allowed to run concurrently"
        assert free.stdout.strip() == "free", "the lock outlived the context manager"

    def test_unusable_runtime_dir_still_applies_the_theme(self, tmp_path, monkeypatch):
        """No XDG_RUNTIME_DIR (the installer's chroot) means unserialized, not
        unthemed. A missing directory fails to open for root as well, so this
        holds in the root CI container too."""
        monkeypatch.setattr(live_theme, "RUNTIME_DIR", tmp_path / "missing")
        with live_theme.switch_lock() as held:
            assert held is False

    def test_lock_is_released_even_when_the_switch_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(live_theme, "RUNTIME_DIR", tmp_path)
        with pytest.raises(RuntimeError):
            with live_theme.switch_lock():
                raise RuntimeError("theme apply blew up")

        handle = (tmp_path / "hyprconf-theme-switch.lock").open("w")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


class TestThemeSwitcherUsesIt:
    """The switcher is the only caller; a refactor that drops the call would
    leave every already-open window on the previous palette."""

    SWITCHER = (
        Path(__file__).resolve().parents[2]
        / "stow/hypr/.config/hypr/scripts/theme-switcher/switch_theme.py"
    )

    def test_switcher_reloads_running_apps_and_takes_the_lock(self):
        source = self.SWITCHER.read_text(encoding="utf-8")
        assert "reload_themed_apps()" in source
        assert "switch_lock()" in source
