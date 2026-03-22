"""Tests for new theme-switcher behaviours added in this session:
  - _kill_process_if_running() helper
  - hyperlauncher restart after update_hyprtoolkit()
  - Dolphin ColorScheme write in update_kde_colors()
  - Firefox running-state guard in update_firefox()
  - update_touch_panel() (see also test_hardware_features.py)
"""
from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

THEME_SWITCHER = (
    Path(__file__).parent.parent.parent
    / "stow" / "hypr" / ".config" / "hypr"
    / "scripts" / "theme-switcher" / "switch_theme.py"
)

import importlib.util

spec = importlib.util.spec_from_file_location("switch_theme", THEME_SWITCHER)
st = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(st)  # type: ignore[union-attr]

DARK_THEME = {
    "background": "#1e1e2e",
    "foreground": "#cdd6f4",
    "accent":     "#89b4fa",
}


# ---------------------------------------------------------------------------
# _kill_process_if_running()
# ---------------------------------------------------------------------------

def test_kill_process_sends_sigterm(monkeypatch):
    kill_calls: list = []

    def fake_run(cmd, **_kw):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "1234\n5678\n"
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    result = st._kill_process_if_running("fakeprog")
    assert result is True
    assert (1234, signal.SIGTERM) in kill_calls
    assert (5678, signal.SIGTERM) in kill_calls


def test_kill_process_returns_false_when_not_running(monkeypatch):
    def fake_run(cmd, **_kw):
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    kill_calls: list = []
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: kill_calls.append((pid, sig)))

    result = st._kill_process_if_running("notrunning")
    assert result is False
    assert kill_calls == []


def test_kill_process_ignores_stale_pids(monkeypatch):
    """ProcessLookupError (stale PID) must not raise."""
    def fake_run(cmd, **_kw):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "9999\n"
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))

    # Must not raise
    st._kill_process_if_running("ghost")


# ---------------------------------------------------------------------------
# update_hyprtoolkit() — kills hyperlauncher if running
# ---------------------------------------------------------------------------

def test_update_hyprtoolkit_kills_hyperlauncher(tmp_path, monkeypatch):
    """After writing hyprtoolkit.conf, hyperlauncher should be sent SIGTERM."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(st.os, "makedirs", lambda *a, **kw: None)
    monkeypatch.setattr(st, "HYPRTOOLKIT_CONF_FILE", str(tmp_path / "hyprtoolkit.conf"))

    killed: list = []

    def fake_kill_process(name: str) -> bool:
        killed.append(name)
        return True

    monkeypatch.setattr(st, "_kill_process_if_running", fake_kill_process)

    # patch open so we don't need actual filesystem
    with patch("builtins.open", unittest_mock_open()):
        st.update_hyprtoolkit(DARK_THEME)

    assert "hyprlauncher" in killed


def test_update_hyprtoolkit_does_not_raise_when_hyprlauncher_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(st.os, "makedirs", lambda *a, **kw: None)
    monkeypatch.setattr(st, "HYPRTOOLKIT_CONF_FILE", str(tmp_path / "hyprtoolkit.conf"))

    def fake_kill_process(name: str) -> bool:
        return False  # process not running

    monkeypatch.setattr(st, "_kill_process_if_running", fake_kill_process)

    with patch("builtins.open", unittest_mock_open()):
        st.update_hyprtoolkit(DARK_THEME)  # must not raise


# ---------------------------------------------------------------------------
# update_kde_colors() — writes ColorScheme to dolphinrc
# ---------------------------------------------------------------------------

def test_update_kde_colors_writes_dolphin_colorscheme(monkeypatch, tmp_path):
    """kwriteconfig6 should be called to write ColorScheme=SwitchThemeGenerated."""
    kwrite_calls: list = []

    def fake_which(name: str):
        return "/usr/bin/kwriteconfig6" if name == "kwriteconfig6" else None

    def fake_run(cmd, **_kw):
        kwrite_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.shutil, "which", fake_which)
    monkeypatch.setattr(st.subprocess, "run", fake_run)

    # Patch file writes so we don't touch the real filesystem
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    st.update_kde_colors(DARK_THEME)

    dolphin_calls = [c for c in kwrite_calls if "dolphinrc" in c]
    assert len(dolphin_calls) == 1
    cmd = dolphin_calls[0]
    assert "SwitchThemeGenerated" in cmd
    assert "--key" in cmd
    assert "ColorScheme" in cmd


def test_update_kde_colors_falls_back_to_kwriteconfig5(monkeypatch, tmp_path):
    """If kwriteconfig6 is absent, kwriteconfig5 should be tried."""
    kwrite_calls: list = []

    def fake_which(name: str):
        if name == "kwriteconfig5":
            return "/usr/bin/kwriteconfig5"
        return None  # kwriteconfig6 absent

    def fake_run(cmd, **_kw):
        kwrite_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.shutil, "which", fake_which)
    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    st.update_kde_colors(DARK_THEME)

    dolphin_calls = [c for c in kwrite_calls if "dolphinrc" in c]
    assert len(dolphin_calls) == 1
    assert dolphin_calls[0][0] in ("kwriteconfig5", "/usr/bin/kwriteconfig5")


def test_update_kde_colors_skips_dolphin_when_kwriteconfig_absent(monkeypatch, tmp_path):
    """No dolphin write if neither kwriteconfig6 nor kwriteconfig5 is present."""
    subprocess_calls: list = []

    def fake_which(name: str):
        if name in ("kwriteconfig6", "kwriteconfig5"):
            return None
        return f"/usr/bin/{name}"  # other tools present

    def fake_run(cmd, **_kw):
        subprocess_calls.append(cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.shutil, "which", fake_which)
    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    st.update_kde_colors(DARK_THEME)

    dolphin_calls = [c for c in subprocess_calls if any("dolphinrc" in str(a) for a in c)]
    assert dolphin_calls == []


# ---------------------------------------------------------------------------
# update_firefox() — running-state guard
# ---------------------------------------------------------------------------

def test_firefox_skips_extensions_json_when_running(tmp_path, monkeypatch):
    """When Firefox is running, set_firefox_theme_activation must not be called."""
    activation_calls: list = []

    monkeypatch.setattr(st, "_is_process_running", lambda name: True)  # Firefox is running
    monkeypatch.setattr(st.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0))
    monkeypatch.setattr(st, "get_default_firefox_profile", lambda: tmp_path)
    monkeypatch.setattr(st, "parse_user_js", lambda *_: {})
    monkeypatch.setattr(st, "ensure_firefox_theme_payload", lambda *_: None)
    monkeypatch.setattr(st, "set_firefox_theme_activation",
                        lambda p, tid: activation_calls.append(tid) or True)
    monkeypatch.setattr(st, "write_firefox_userchrome", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userjs", lambda *_: None)

    st.update_firefox(DARK_THEME)

    assert activation_calls == [], "extensions.json must not be written while Firefox is running"


def test_firefox_updates_extensions_json_when_not_running(tmp_path, monkeypatch):
    """When Firefox is not running, theme activation should proceed normally."""
    activation_calls: list = []

    monkeypatch.setattr(st, "_is_process_running", lambda name: False)  # Firefox NOT running
    monkeypatch.setattr(st, "get_default_firefox_profile", lambda: tmp_path)
    monkeypatch.setattr(st, "parse_user_js", lambda *_: {})
    monkeypatch.setattr(st, "ensure_firefox_theme_payload", lambda *_: None)
    monkeypatch.setattr(st, "resolve_firefox_theme_id", lambda *_: None)
    monkeypatch.setattr(st, "get_firefox_builtin_theme_id", lambda _: "firefox-compact-dark@mozilla.org")
    monkeypatch.setattr(st, "set_firefox_theme_activation",
                        lambda p, tid: activation_calls.append(tid) or True)
    monkeypatch.setattr(st, "write_firefox_userchrome", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userjs", lambda *_: None)

    st.update_firefox(DARK_THEME)

    assert len(activation_calls) == 1
    assert "compact-dark" in activation_calls[0]


def test_firefox_sends_notify_when_running(tmp_path, monkeypatch, capsys):
    """notify-send should be called when Firefox is running."""
    notify_calls: list = []

    monkeypatch.setattr(st, "_is_process_running", lambda name: True)  # Firefox is running

    def fake_run(cmd, **_kw):
        m = MagicMock()
        if cmd[0] == "notify-send":
            notify_calls.append(cmd)
        m.returncode = 0
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    monkeypatch.setattr(st, "get_default_firefox_profile", lambda: tmp_path)
    monkeypatch.setattr(st, "parse_user_js", lambda *_: {})
    monkeypatch.setattr(st, "ensure_firefox_theme_payload", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userchrome", lambda *_: None)
    monkeypatch.setattr(st, "write_firefox_userjs", lambda *_: None)

    st.update_firefox(DARK_THEME)

    assert notify_calls, "notify-send should have been called"
    assert any("restart" in " ".join(c).lower() for c in notify_calls)


# ---------------------------------------------------------------------------
# update_kde_colors() — alternating-row contrast (Dolphin dark-theme stripes)
# ---------------------------------------------------------------------------

DRACULA_THEME = {
    "background": "#282a36",
    "foreground": "#f8f8f2",
    "accent":     "#8be9fd",
    "comment":    "#6272a4",
    "red":        "#ff5555",
    "green":      "#50fa7b",
    "yellow":     "#f1fa8c",
    "cyan":       "#8be9fd",
}


def _capture_kdeglobals(monkeypatch, tmp_path, theme: dict) -> str:
    """Run update_kde_colors() and return the text written to kdeglobals."""
    written: list[str] = []

    def fake_write_text(self, content, encoding="utf-8"):
        written.append(content)

    monkeypatch.setattr(Path, "write_text", fake_write_text)
    monkeypatch.setattr(Path, "mkdir", lambda *a, **kw: None)
    monkeypatch.setattr(st.shutil, "which", lambda name: None)  # no external tools
    monkeypatch.setattr(st.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0))

    st.update_kde_colors(theme)
    # The first write_text call is kdeglobals, the second is the .colors file
    assert written, "update_kde_colors() must write at least one file"
    return written[0]


def _parse_rgb_key(section_text: str, key: str) -> tuple[int, int, int]:
    """Extract R,G,B integers for 'key=R,G,B' from a kdeglobals section block."""
    import re
    m = re.search(rf"^{re.escape(key)}=(\d+),(\d+),(\d+)", section_text, re.MULTILINE)
    assert m, f"Key '{key}' not found in section text"
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _luminance(r: int, g: int, b: int) -> float:
    """Approximate perceived brightness (0–255 scale)."""
    return 0.299 * r + 0.587 * g + 0.114 * b


def test_kde_view_alternate_is_lighter_than_normal_for_dark_theme(monkeypatch, tmp_path):
    """[Colors:View] BackgroundAlternate must be noticeably lighter than BackgroundNormal
    for dark themes so that KDE's contrast enforcement does not override it with a
    completely different computed shade."""
    content = _capture_kdeglobals(monkeypatch, tmp_path, DRACULA_THEME)

    # Extract the [Colors:View] block
    assert "[Colors:View]" in content
    view_start = content.index("[Colors:View]")
    view_end = content.find("\n[", view_start + 1)
    view_block = content[view_start:view_end]

    normal_rgb = _parse_rgb_key(view_block, "BackgroundNormal")
    alt_rgb    = _parse_rgb_key(view_block, "BackgroundAlternate")

    lum_normal = _luminance(*normal_rgb)
    lum_alt    = _luminance(*alt_rgb)

    # Alternate must be perceptibly lighter: at least 10 luma units difference
    assert lum_alt > lum_normal, (
        f"BackgroundAlternate ({alt_rgb}) must be lighter than "
        f"BackgroundNormal ({normal_rgb}) in [Colors:View]"
    )
    assert (lum_alt - lum_normal) >= 10, (
        f"Contrast too low ({lum_alt - lum_normal:.1f} luma units) — "
        "KDE will override with its own derived shade, causing clearly-light rows"
    )


def test_kde_button_alternate_is_lighter_than_button_normal(monkeypatch, tmp_path):
    """[Colors:Button] BackgroundAlternate must be lighter than BackgroundNormal.
    Previously alt_bg (5% blend from bg) was darker than btn_bg (10% blend),
    inverting the visual striping in button-style surfaces."""
    content = _capture_kdeglobals(monkeypatch, tmp_path, DRACULA_THEME)

    assert "[Colors:Button]" in content
    btn_start = content.index("[Colors:Button]")
    btn_end   = content.find("\n[", btn_start + 1)
    btn_block = content[btn_start:btn_end]

    normal_rgb = _parse_rgb_key(btn_block, "BackgroundNormal")
    alt_rgb    = _parse_rgb_key(btn_block, "BackgroundAlternate")

    lum_normal = _luminance(*normal_rgb)
    lum_alt    = _luminance(*alt_rgb)

    assert lum_alt > lum_normal, (
        f"[Colors:Button] BackgroundAlternate ({alt_rgb}) must be lighter than "
        f"BackgroundNormal ({normal_rgb}); previously the order was inverted"
    )


def test_kde_view_alternate_consistent_with_window_alternate(monkeypatch, tmp_path):
    """[Colors:View] and [Colors:Window] BackgroundAlternate must use the same
    alt_bg value so window chrome and file-list rows stripe consistently."""
    content = _capture_kdeglobals(monkeypatch, tmp_path, DRACULA_THEME)

    view_start  = content.index("[Colors:View]")
    view_end    = content.find("\n[", view_start + 1)
    view_block  = content[view_start:view_end]

    win_start   = content.index("[Colors:Window]")
    win_end     = content.find("\n[", win_start + 1)
    win_block   = content[win_start:win_end]

    view_alt = _parse_rgb_key(view_block, "BackgroundAlternate")
    win_alt  = _parse_rgb_key(win_block,  "BackgroundAlternate")

    assert view_alt == win_alt, (
        f"[Colors:View] alternate {view_alt} != [Colors:Window] alternate {win_alt}; "
        "both should use the same alt_bg"
    )


# ---------------------------------------------------------------------------
# update_gtk() — blueman GTK_THEME env and relaunch delay
# ---------------------------------------------------------------------------

def _run_update_gtk_with_blueman(monkeypatch, gtk_theme_override: str | None = None):
    """
    Run update_gtk() with blueman-applet appearing to be running.
    Returns (popen_calls, sleep_calls) where each entry in popen_calls is the
    kwargs dict passed to subprocess.Popen.
    """
    popen_calls: list[dict] = []
    sleep_calls: list[float] = []

    def fake_pgrep(cmd, **_kw):
        m = MagicMock()
        if cmd[0] == "pgrep":
            m.returncode = 0
            m.stdout = "4321\n"
        else:
            m.returncode = 1
            m.stdout = ""
        return m

    monkeypatch.setattr(st.subprocess, "run", fake_pgrep)
    monkeypatch.setattr(st.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(st.time, "sleep", lambda secs: sleep_calls.append(secs))

    def fake_popen(cmd, **kw):
        popen_calls.append({"cmd": cmd, **kw})
        return MagicMock()

    monkeypatch.setattr(st.subprocess, "Popen", fake_popen)

    # Stub out every file / external tool used by update_gtk()
    monkeypatch.setattr(st.shutil, "which", lambda name: f"/usr/bin/{name}")

    def fake_run_noop(cmd, **_kw):
        return MagicMock(returncode=0)

    monkeypatch.setattr(st.subprocess, "run", fake_pgrep)

    import builtins
    original_open = builtins.open

    def fake_open(path, *a, **kw):
        from io import StringIO
        return StringIO("[Settings]\ngtk-theme-name=old-theme\ngtk-application-prefer-dark-theme=0\n")

    monkeypatch.setattr(builtins, "open", fake_open)

    theme = dict(DRACULA_THEME)
    if gtk_theme_override:
        theme["gtk_theme"] = gtk_theme_override

    monkeypatch.setattr(st.subprocess, "run", fake_pgrep)
    monkeypatch.setattr(st.subprocess, "Popen", fake_popen)

    st.update_gtk(theme)
    return popen_calls, sleep_calls


def test_blueman_relaunch_passes_gtk_theme_in_env(monkeypatch, tmp_path):
    """The relaunched blueman-applet must receive GTK_THEME in its explicit env.
    Previously subprocess.Popen had no env= argument, so it inherited the script's
    stale os.environ — hyprctl setenv does not update os.environ."""
    popen_calls, _ = _run_update_gtk_with_blueman(monkeypatch)

    blueman_launches = [c for c in popen_calls if c["cmd"] == ["blueman-applet"]]
    assert blueman_launches, "blueman-applet should have been relaunched"

    launch = blueman_launches[0]
    assert "env" in launch, "subprocess.Popen must receive an explicit env= dict"
    assert "GTK_THEME" in launch["env"], "env must contain GTK_THEME"
    # GTK_THEME must be a non-empty string (the resolved theme name)
    assert launch["env"]["GTK_THEME"], "GTK_THEME must not be empty"


def test_blueman_relaunch_sleeps_after_sigterm(monkeypatch, tmp_path):
    """A brief sleep must occur between SIGTERM and relaunch to prevent the race
    condition where both old and new processes coexist and the old one wins."""
    _, sleep_calls = _run_update_gtk_with_blueman(monkeypatch)

    assert sleep_calls, "time.sleep() must be called between kill and relaunch"
    assert any(s >= 0.1 for s in sleep_calls), (
        f"Sleep must be at least 0.1 s to allow the old process to exit; got {sleep_calls}"
    )


# ---------------------------------------------------------------------------
# Helper: unittest mock_open compatible with write_text
# ---------------------------------------------------------------------------

def unittest_mock_open():
    """Return a mock open() that accepts positional and keyword args."""
    from unittest.mock import mock_open
    m = mock_open()
    m.return_value.__enter__ = lambda s: s
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m
