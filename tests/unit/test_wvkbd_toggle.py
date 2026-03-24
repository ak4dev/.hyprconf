"""
Unit/integration tests for wvkbd-toggle.

wvkbd-mobintl signals (confirmed via live test on X13):
  SIGUSR1 = hide
  SIGUSR2 = show

wvkbd-toggle state machine (driven by STATE_FILE):
  - wvkbd not running           → start launcher + send SIGUSR2 + create state file
  - wvkbd running, visible      → send SIGUSR1  + remove state file
  - wvkbd running, hidden       → send SIGUSR2  + create state file

The script accepts WVKBD_STATE_FILE env-var override so tests can use a
tmpdir path instead of /tmp/wvkbd-visible.

Strategy for "wvkbd is running" cases:
  A real bash process (signal receiver) records incoming USR1/USR2 to a log
  file.  A fake `pgrep` script placed first on PATH returns that process's
  PID when queried for "wvkbd-mobintl", so the toggle's built-in `kill`
  sends signals to our controlled receiver rather than any real wvkbd.

Strategy for "wvkbd not running" cases:
  The fake pgrep exits 1 for wvkbd-mobintl, so the toggle invokes the
  launcher.  A mock launcher script records its invocation to a log file.
"""
from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
WVKBD_TOGGLE = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "wvkbd-toggle"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_env(tmp_path: Path) -> SimpleNamespace:
    home    = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    home.mkdir()
    bin_dir.mkdir()
    return SimpleNamespace(
        home=home,
        bin_dir=bin_dir,
        signal_log=tmp_path / "signals.log",
        state_file=tmp_path / "wvkbd-state",
        launcher_log=tmp_path / "launcher.log",
    )


def _write_exe(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _fake_pgrep_returning(bin_dir: Path, pid: int) -> None:
    """fake pgrep: return pid for wvkbd-mobintl queries, delegate the rest."""
    _write_exe(bin_dir / "pgrep", f"""\
#!/usr/bin/env bash
if [[ "$*" == *"wvkbd-mobintl"* ]]; then
    echo {pid}; exit 0
fi
exec /usr/bin/pgrep "$@"
""")


def _fake_pgrep_empty(bin_dir: Path) -> None:
    """fake pgrep: always report wvkbd-mobintl as not running."""
    _write_exe(bin_dir / "pgrep", """\
#!/usr/bin/env bash
if [[ "$*" == *"wvkbd-mobintl"* ]]; then exit 1; fi
exec /usr/bin/pgrep "$@"
""")


def _start_signal_receiver(env: SimpleNamespace) -> subprocess.Popen:
    """Start a bash process that logs USR1/USR2 to env.signal_log."""
    script = env.home / "_receiver.sh"
    _write_exe(script, f"""\
#!/usr/bin/env bash
trap 'echo USR1 >> {env.signal_log}' USR1
trap 'echo USR2 >> {env.signal_log}' USR2
while true; do sleep 0.05; done
""")
    return subprocess.Popen(["bash", str(script)])


def _run_toggle(env: SimpleNamespace) -> subprocess.CompletedProcess[str]:
    e = os.environ.copy()
    e["HOME"]              = str(env.home)
    e["WVKBD_STATE_FILE"]  = str(env.state_file)
    e["PATH"]              = f"{env.bin_dir}:{e.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(WVKBD_TOGGLE)],
        env=e, capture_output=True, text=True, timeout=5,
    )


def _wait_for_signal(signal_log: Path, expected: str, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if signal_log.exists() and expected in signal_log.read_text():
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# Case: wvkbd running, hidden (no state file) → SIGUSR2 + state file created
# ---------------------------------------------------------------------------

def test_toggle_shows_when_running_but_hidden(tmp_path: Path) -> None:
    env  = _make_env(tmp_path)
    proc = _start_signal_receiver(env)
    try:
        _fake_pgrep_returning(env.bin_dir, proc.pid)
        result = _run_toggle(env)
        assert result.returncode == 0, result.stderr
        assert _wait_for_signal(env.signal_log, "USR2"), "Expected SIGUSR2 (show) not received"
        assert env.state_file.exists(), "State file should be created when showing"
    finally:
        proc.kill(); proc.wait()


def test_toggle_show_does_not_send_usr1_when_hidden(tmp_path: Path) -> None:
    env  = _make_env(tmp_path)
    proc = _start_signal_receiver(env)
    try:
        _fake_pgrep_returning(env.bin_dir, proc.pid)
        _run_toggle(env)
        time.sleep(0.2)
        content = env.signal_log.read_text() if env.signal_log.exists() else ""
        assert "USR1" not in content, "SIGUSR1 (hide) must not be sent when showing"
    finally:
        proc.kill(); proc.wait()


# ---------------------------------------------------------------------------
# Case: wvkbd running, visible (state file) → SIGUSR1 + state file removed
# ---------------------------------------------------------------------------

def test_toggle_hides_when_running_and_visible(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    env.state_file.touch()            # mark as visible
    proc = _start_signal_receiver(env)
    try:
        _fake_pgrep_returning(env.bin_dir, proc.pid)
        result = _run_toggle(env)
        assert result.returncode == 0, result.stderr
        assert _wait_for_signal(env.signal_log, "USR1"), "Expected SIGUSR1 (hide) not received"
        assert not env.state_file.exists(), "State file should be removed when hiding"
    finally:
        proc.kill(); proc.wait()


def test_toggle_hide_does_not_send_usr2(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    env.state_file.touch()
    proc = _start_signal_receiver(env)
    try:
        _fake_pgrep_returning(env.bin_dir, proc.pid)
        _run_toggle(env)
        time.sleep(0.2)
        content = env.signal_log.read_text() if env.signal_log.exists() else ""
        assert "USR2" not in content, "SIGUSR2 (show) must not be sent when hiding"
    finally:
        proc.kill(); proc.wait()


# ---------------------------------------------------------------------------
# Full show → hide → show cycle
# ---------------------------------------------------------------------------

def test_toggle_full_cycle(tmp_path: Path) -> None:
    env  = _make_env(tmp_path)
    proc = _start_signal_receiver(env)
    try:
        _fake_pgrep_returning(env.bin_dir, proc.pid)

        # 1st: hidden → show (SIGUSR2)
        _run_toggle(env)
        assert _wait_for_signal(env.signal_log, "USR2")
        assert env.state_file.exists()

        # 2nd: visible → hide (SIGUSR1)
        _run_toggle(env)
        assert _wait_for_signal(env.signal_log, "USR1")
        assert not env.state_file.exists()

        # 3rd: hidden → show again (SIGUSR2)
        env.signal_log.unlink(missing_ok=True)
        _run_toggle(env)
        assert _wait_for_signal(env.signal_log, "USR2")
        assert env.state_file.exists()
    finally:
        proc.kill(); proc.wait()


# ---------------------------------------------------------------------------
# Case: wvkbd not running → launcher called, stale state file cleaned
# ---------------------------------------------------------------------------

def test_toggle_calls_launcher_when_not_running(tmp_path: Path) -> None:
    env = _make_env(tmp_path)
    _fake_pgrep_empty(env.bin_dir)

    launcher = env.home / ".local" / "bin" / "wvkbd-launcher"
    launcher.parent.mkdir(parents=True)
    _write_exe(launcher, f"#!/usr/bin/env bash\necho 'launched' >> {env.launcher_log}\n")

    _run_toggle(env)
    assert env.launcher_log.exists(), "Launcher was not invoked"
    assert "launched" in env.launcher_log.read_text()


def test_toggle_stale_state_file_cleaned_on_not_running(tmp_path: Path) -> None:
    """Stale state file is removed when entering the not-running branch."""
    env = _make_env(tmp_path)
    env.state_file.touch()            # stale — wvkbd died while marked visible
    _fake_pgrep_empty(env.bin_dir)

    launcher = env.home / ".local" / "bin" / "wvkbd-launcher"
    launcher.parent.mkdir(parents=True)
    _write_exe(launcher, "#!/usr/bin/env bash\n")

    _run_toggle(env)
    assert not env.state_file.exists(), "Stale state file was not cleaned up"


def test_toggle_error_when_launcher_missing(tmp_path: Path) -> None:
    """Script exits non-zero and emits an error when launcher is absent."""
    env = _make_env(tmp_path)
    _fake_pgrep_empty(env.bin_dir)

    result = _run_toggle(env)
    assert result.returncode != 0
    assert "wvkbd-launcher" in result.stderr


# ---------------------------------------------------------------------------
# WVKBD_STATE_FILE env override is respected
# ---------------------------------------------------------------------------

def test_state_file_env_override_used(tmp_path: Path) -> None:
    """WVKBD_STATE_FILE env var points to the custom path, not /tmp/wvkbd-visible."""
    env  = _make_env(tmp_path)
    proc = _start_signal_receiver(env)
    try:
        _fake_pgrep_returning(env.bin_dir, proc.pid)
        _run_toggle(env)
        time.sleep(0.15)
        assert env.state_file.exists(), "Custom WVKBD_STATE_FILE was not used"
        assert not Path("/tmp/wvkbd-visible").stat() if Path("/tmp/wvkbd-visible").exists() else True
    finally:
        proc.kill(); proc.wait()


# ---------------------------------------------------------------------------
# Regression: multi-PID handling — pgrep must use -o (oldest) to get one PID
# ---------------------------------------------------------------------------

def test_toggle_survives_when_multiple_wvkbd_instances_exist(tmp_path: Path) -> None:
    """pgrep -x -o ensures only ONE pid is returned even when multiple wvkbd
    processes are running.  Without -o, pgrep returns a multi-line string
    which bash passes as a single invalid argument to kill → EINVAL → the
    toggle silently fails and the keyboard never appears.
    """
    env  = _make_env(tmp_path)
    proc = _start_signal_receiver(env)
    try:
        # fake pgrep: with -o return exactly one PID; without -o return two
        # (simulating stale duplicate processes in the process table).
        pgrep_script = f"""\
#!/usr/bin/env bash
if [[ "$*" == *"wvkbd-mobintl"* ]]; then
    if [[ "$*" == *"-o"* ]]; then
        echo {proc.pid}; exit 0
    else
        echo {proc.pid}; echo 99998; exit 0
    fi
fi
exec /usr/bin/pgrep "$@"
"""
        _write_exe(env.bin_dir / "pgrep", pgrep_script)
        result = _run_toggle(env)
        assert result.returncode == 0, f"toggle failed: {result.stderr}"
        assert _wait_for_signal(env.signal_log, "USR2"), (
            "SIGUSR2 (show) not received — multi-PID pgrep fix may be missing"
        )
    finally:
        proc.kill(); proc.wait()


# ---------------------------------------------------------------------------
# Regression: touch-panel-watch must use pgrep -f (cmdline match), not -x
# ---------------------------------------------------------------------------

TOUCH_PANEL_WATCH = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "touch-panel-watch"


def test_touch_panel_watch_uses_cmdline_pgrep_not_exact_name() -> None:
    """touch-panel runs as 'python3 /path/to/touch-panel', so its comm is
    'python3', not 'touch-panel'.  pgrep -x touch-panel never matches and
    the watch spawns a new instance on every udev event.

    Fix: pgrep -f '[/]touch-panel$' matches the full command line.
    """
    content = TOUCH_PANEL_WATCH.read_text()
    assert "pgrep -x touch-panel" not in content, (
        "touch-panel-watch uses pgrep -x which never finds the Python process. "
        "Use 'pgrep -f' to match the full command line."
    )
    assert "pgrep -f" in content, (
        "touch-panel-watch must use 'pgrep -f' to match by full command line."
    )


# ---------------------------------------------------------------------------
# Regression: touch-panel-watch must use grep -E (ERE) for PHYS pattern
# ---------------------------------------------------------------------------

def test_touch_panel_watch_uses_grep_e_for_phys() -> None:
    """Regression: touch-panel-watch used 'grep -q ^PHYS=.\\+' (GNU BRE
    extension).  touch-panel-launcher was already fixed to use grep -E.
    Both scripts must use the same ERE form for consistency and portability."""
    content = TOUCH_PANEL_WATCH.read_text()
    assert r"grep -q '^PHYS=.\+'" not in content, (
        "touch-panel-watch still uses non-POSIX BRE \\+ — should use grep -E"
    )
    assert "grep -E" in content, (
        "touch-panel-watch must use grep -E for PHYS pattern"
    )


# ---------------------------------------------------------------------------
# Regression: wvkbd-toggle default state file must use XDG_RUNTIME_DIR
# ---------------------------------------------------------------------------

def test_wvkbd_toggle_default_state_uses_xdg_runtime_dir() -> None:
    """Regression: the default STATE_FILE was '/tmp/wvkbd-visible', shared
    across all users and susceptible to /tmp TOCTOU attacks.  Fix: use
    ${XDG_RUNTIME_DIR:-/tmp} so the file lives in the user's private runtime
    directory when available."""
    content = WVKBD_TOGGLE.read_text()
    assert ":-/tmp}/wvkbd-visible" in content or "${XDG_RUNTIME_DIR" in content, (
        "wvkbd-toggle default STATE_FILE should use ${XDG_RUNTIME_DIR:-/tmp}"
    )
    # Must NOT have the bare /tmp hardcode any more
    assert ":-/tmp/wvkbd-visible}" not in content, (
        "wvkbd-toggle still has bare /tmp/wvkbd-visible hardcode"
    )
