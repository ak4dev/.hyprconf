"""modules/bar-resources: the install (link, rescan, enable once, undo) and the
pins on the plugin it installs that no other file can carry — the feeders run
once for the session, not once per bar surface, and the widget paints what they
emit."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import Box

MODULE = Path(__file__).parent
PLUGIN = MODULE / "plugin"
ID = "hyprconf.resources"
# Omarchy's own validator, the one real omarchy-* command the suite runs
# (AGENTS.md › Tests). Absent in CI, which carries no Omarchy.
PLUGIN_VALIDATE = Path("/usr/share/omarchy/bin/omarchy-plugin-validate")
# omarchy-plugin-list answering with this plugin: what the discovery loop waits
# for before the enable (bin/omarchy-plugin-add:164-171 does the same).
LISTED = f'printf \'[{{"id":"{ID}"}}]\\n\'\n'


def _link(box: Box) -> Path:
    return box.home / ".config" / "omarchy" / "plugins" / ID


def _marker(box: Box) -> Path:
    return box.home / ".local" / "state" / "hyprconf" / "resources-applied"


def _install(box: Box, *args: str, listed: bool = True):
    if listed:
        box.stub("omarchy-plugin-list", LISTED)
    return box.run(MODULE / "install", *args)


def _snapshot(box: Box) -> dict[str, tuple]:
    """Everything under $HOME — files with their content and mtime, symlinks
    with their target and their own mtime, directories by name. `==` across two
    runs is "the second run touched nothing", a re-made link included."""
    out: dict[str, tuple] = {}
    for p in sorted(box.home.rglob("*")):
        rel = str(p.relative_to(box.home))
        if p.is_symlink():
            out[rel] = ("link", os.readlink(p), p.lstat().st_mtime_ns)
        elif p.is_dir():
            out[rel] = ("dir",)
        else:
            out[rel] = ("file", p.read_bytes(), p.stat().st_mtime_ns)
    return out


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def test_links_the_plugin_and_enables_it_once(box: Box) -> None:
    r = _install(box)
    assert r.returncode == 0, r.stderr
    assert os.readlink(_link(box)) == str(PLUGIN)
    assert _marker(box).exists()
    assert box.calls_of("omarchy-plugin-enable") == [["omarchy-plugin-enable", ID]]
    # No --section: placement comes from the manifest's barWidget.defaultSection
    # (shell/services/PluginRegistry.qml:194-196).
    assert "omarchy-shell" in box.commands


def test_a_second_run_writes_nothing_and_re_enables_nothing(box: Box) -> None:
    _install(box)
    before = _snapshot(box)
    box.reset()
    r = _install(box)
    assert r.returncode == 0, r.stderr
    assert _snapshot(box) == before
    assert "omarchy-plugin-enable" not in box.commands


def test_a_link_pointing_somewhere_else_is_repaired(box: Box) -> None:
    stale = box.tmp / "somewhere-else"
    stale.mkdir()
    _link(box).parent.mkdir(parents=True)
    _link(box).symlink_to(stale)
    _install(box)
    assert os.readlink(_link(box)) == str(PLUGIN)


def test_no_shell_leaves_the_marker_unwritten_and_retries(box: Box) -> None:
    """The enable needs the running shell (bin/omarchy-plugin-enable:85-87
    fails "not known"); a TTY or SSH run must not burn the marker."""
    box.stub("omarchy-plugin-enable", "exit 1\n")
    r = _install(box, listed=False)
    assert r.returncode == 0
    assert not _marker(box).exists()
    assert os.readlink(_link(box)) == str(PLUGIN)  # the link lands either way
    box.stub("omarchy-plugin-enable", "exit 0\n")
    _install(box)
    assert _marker(box).exists()


def test_an_omarchy_plugin_add_checkout_is_left_alone(box: Box) -> None:
    """A same-id git checkout is Omarchy's to manage (omarchy plugin update),
    and replacing it would take the user's clone with it."""
    checkout = _link(box)
    (checkout / ".git").mkdir(parents=True)
    r = _install(box)
    assert r.returncode == 0
    assert checkout.is_dir() and not checkout.is_symlink()
    assert not _marker(box).exists()
    assert "omarchy-plugin-enable" not in box.commands


def test_a_real_folder_is_moved_aside_before_linking(box: Box) -> None:
    """The pre-module synced copy (or a hand-dropped folder): moved aside under
    omarchy-plugin-remove's own backup name (bin/omarchy-plugin-remove:106),
    never deleted."""
    old = _link(box)
    old.mkdir(parents=True)
    (old / "manifest.json").write_text("{}\n")
    _install(box)
    assert os.readlink(_link(box)) == str(PLUGIN)
    backups = list(_link(box).parent.glob(f".{ID}.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "manifest.json").read_text() == "{}\n"


def test_undo_disables_unlinks_and_forgets_the_marker(box: Box) -> None:
    _install(box)
    box.reset()
    r = box.undo("bar-resources")
    assert r.returncode == 0, r.stderr
    assert box.calls_of("omarchy-plugin-disable") == [["omarchy-plugin-disable", ID]]
    assert not _link(box).exists() and not _link(box).is_symlink()
    assert not _marker(box).exists()
    assert "omarchy-shell" in box.commands  # the shell is told to re-scan


def test_the_installed_folder_passes_omarchy_plugin_validate(box: Box) -> None:
    """Omarchy's own validator over the plugin as this module installs it. It
    refuses a symlink anywhere inside a plugin folder — `find "$PLUGIN_DIR"
    -name .git -prune -o -type l -print -quit` (bin/omarchy-plugin-validate:115,
    4.0.3-1) — and what lands in ~/.config/omarchy/plugins/ IS a link, so the
    path has to carry the trailing slash that makes find descend it. That is the
    line both READMEs give a by-hand user, and this is what holds it true."""
    if not PLUGIN_VALIDATE.is_file():
        pytest.skip("no installed omarchy-plugin-validate")
    _install(box)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(box.home)}

    def validate(path: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(PLUGIN_VALIDATE), path],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

    passed = validate(f"{_link(box)}/")
    assert passed.returncode == 0, passed.stderr
    assert validate(str(_link(box))).returncode != 0, "the trailing slash is no longer load-bearing"


def test_undo_touches_nothing_it_did_not_install(box: Box) -> None:
    """Nothing installed: exit 0, no files. A real folder of that name is
    someone else's — the pre-module copy, or a hand-dropped plugin — and only
    the module's own link is ever removed."""
    assert box.undo("bar-resources").returncode == 0
    assert box.files() == set()
    foreign = _link(box)
    foreign.mkdir(parents=True)
    (foreign / "manifest.json").write_text("{}\n")
    assert box.undo("bar-resources").returncode == 0
    assert (foreign / "manifest.json").read_text() == "{}\n"


# ---------------------------------------------------------------------------
# the plugin it installs
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    """The line without a trailing // comment (one inside a string stays)."""
    out: list[str] = []
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            out.append(c)
            if c == "\\":
                out.append(line[i + 1 : i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            out.append(c)
        elif line.startswith("//", i):
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _code(name: str) -> str:
    """One QML file with its comments stripped, so a pin matches the code and
    never the prose explaining it."""
    return "\n".join(_strip_comment(ln) for ln in (PLUGIN / name).read_text().splitlines())


def test_the_feeders_run_once_for_the_session_not_once_per_monitor() -> None:
    """Bar.qml is `Variants { model: Quickshell.screens }`, so a Process the
    WIDGET owns runs once per bar surface — two permanent streams and an NVML
    session per monitor, all reporting the same numbers. The seam is the service
    kind: shell.qml's _syncServices()/ensureService() load entryPoints.service
    of an enabled plugin exactly once, and the widget reads the values back
    through bar.shell.serviceFor(<own id>) (4.0.3-1: PluginShellApi.qml:30 →
    shell.qml:385-394 answers only for ids the plugin owns). Verified under
    quickshell 0.3.1: three surfaces, one feeder pair."""
    widget, service = _code("Widget.qml"), _code("Service.qml")
    assert "Process {" not in widget, "a Process in the widget runs once per bar surface"
    for feeder in ("bin/hyprconf-stats", "bin/hyprconf-gpu-info"):
        assert f'command: [root.pluginDir + "{feeder}"]' in service
    assert f'root.bar?.shell?.serviceFor("{ID}")' in widget
    # Every value the widget paints comes off the service, with a fallback for
    # the window before it is loaded (and for a bar that carries no `shell`).
    for prop in ("cpuPct", "cpuTemp", "memText", "netUp", "netDown", "gpuProduced", "gpuTooltip"):
        assert f"root.feed ? root.feed.{prop} :" in widget, prop


def test_the_widget_owns_the_units_and_the_glyphs() -> None:
    """The feeders emit numbers; every glyph and unit is the widget's. The
    thermometer is the solid Material Design glyph (U+F050F), not the
    Weather-Icons outline (U+E350) — a hairline at caption size — and the
    service assigns the feeder's own fields rather than a pre-rendered "text"."""
    widget, service = _code("Widget.qml"), _code("Service.qml")
    assert "\\u{F050F}" in widget and "\\ue350" not in widget.lower()
    assert '"°"' in widget or '+ "° "' in widget, "the degree sign is the widget's"
    for field in ("j.util", "j.temp", "j.vram_used", "j.vram_total", "j.tooltip"):
        assert f"= {field}\n" in service, field
    assert "j.text" not in service
    # No re-formatting on the way through: the service assigns, it does not
    # String()/Number()/?? the feeder's contract back into shape.
    assert "Number(j." not in service and "String(j." not in service


def test_the_feeders_restart_on_a_capped_backoff() -> None:
    """A dead feeder is restarted on a capped backoff, never a flat retry (why:
    Service.qml's own header). The shape is pinned rather than the behaviour,
    which would need a running shell; it was verified under quickshell 0.3.1
    against a feeder that exits at once — 7 execs in 63 s, then nothing —
    and against one that emits a line every time: a steady 1 s."""
    code = _code("Service.qml")
    assert "component Restarter: Timer" in code
    # Both feeders go through it, and neither restarts a Process any other way.
    assert code.count("RestartTimer.died()") == 2
    assert code.count("RestartTimer.produced()") == 2
    assert "RestartTimer.start()" not in code
    # The latched flags stay latched: clearing one would blank the cells.
    assert not re.search(r"root\.(?:gpu|stats)Produced\s*=\s*false", code)


def test_the_feeders_ship_executable() -> None:
    """The install links the folder instead of copying it, so the mode in the
    checkout is the mode the shell execs — nothing re-asserts it at install
    time. A feeder without its exec bit fails with EACCES and the widget
    freezes at 0%."""
    for feeder in ("hyprconf-stats", "hyprconf-gpu-info"):
        path = PLUGIN / "bin" / feeder
        assert os.access(path, os.X_OK), path
