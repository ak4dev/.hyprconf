"""install.sh — the overlay installer for Omarchy systems.

This installer is unusual for hyprconf in that it runs on a machine it does not
own: Omarchy owns the base system, and the overlay's whole design constraint is
to disturb it as little as possible. Most of what is asserted here is therefore
*restraint* — what the installer must NOT do:

  * never `chsh` (the login shell stays bash, so Omarchy's rc chain, aliases,
    completions, session and scripts keep working)
  * never rewrite Omarchy's ~/.config/kitty/kitty.conf beyond appending one
    `include` line (it owns the theme include, listen_on, font_family/font_size)
  * never reach `omarchy-launch-floating-terminal-with-presentation`, which
    `omarchy-default-terminal` exec()s when kitty is missing — a GUI window is
    fatal to a non-interactive run
  * never `pacman -Syu` (an Omarchy ALPM AbortOnFail hook blocks it) or
    `pacman -R` (on Omarchy the "foreign" set includes Omarchy itself)
  * never switch the active theme — hyprconf's theme is installed into the
    theme menu, and which one is active stays the user's choice

Everything runs against fake `omarchy-*` binaries in a throwaway HOME, so the
suite is hermetic in a bare archlinux container per the testing rules.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
HOOK = REPO_ROOT / "hooks" / "post-update.d" / "10-hyprconf"

# A recording stub: appends its own name + args to the calls log, then runs an
# optional body. One template covers every external the installer touches.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "${{0##*/}} $*" >> "{calls}"
{body}
"""

# Omarchy's kitty.conf as a fresh install has it (seeded from /etc/skel). The
# include, allow_remote_control/listen_on and font_family lines are exactly what
# the overlay must leave intact.
OMARCHY_KITTY_CONF = """include ~/.local/state/omarchy/current/theme/kitty.conf
allow_remote_control yes
listen_on unix:${XDG_RUNTIME_DIR}/omarchy-kitty-{kitty_pid}
font_family JetBrainsMono Nerd Font
font_size 10
"""


# Every monitor preset the overlay ships. Each carries the workspace-to-monitor
# rules for its layout, so they travel as whole files.
PRESETS = (
    "pcMonitors.bedroom.lua",
    "pcMonitors.kitchen.lua",
    "pcMonitors.K.lua",
    "pcMonitors.lua",
    "laptopMonitors.lua",
)


def _stub(path: Path, calls: Path, body: str = "exit 0") -> None:
    path.write_text(STUB.format(calls=calls, body=body))
    path.chmod(0o755)


def _setup(tmp_path: Path, *, with_omarchy: bool = True, with_zsh: bool = True) -> dict:
    """Build a throwaway HOME + fake-bins tree resembling a fresh Omarchy box."""
    home = tmp_path / "home"
    bins = tmp_path / "bins"
    omarchy_path = tmp_path / "omarchy"
    calls = tmp_path / "calls"
    for d in (home, bins, omarchy_path):
        d.mkdir(parents=True, exist_ok=True)
    calls.write_text("")

    for name in (
        "omarchy-theme-set",
        "omarchy-font-set",
        "omarchy-default-browser",
        "omarchy-default-editor",
        "omarchy-shell",
        "omarchy-plugin-enable",
        "omarchy-plugin-disable",
        "omarchy-plugin-remove",
        "omarchy-plugin-catalog",
        "omarchy-restart-shell",
        "omarchy-bar",
        "omarchy-update",
        "sudo",
        "hyprctl",
        "kitty",
        # switch_monitor.sh (run by several tests here) reports through these;
        # the real ones would put a notification and an OSD on the developer's
        # desktop every time the suite runs.
        "omarchy-notification-send",
        "omarchy-osd",
        # The theme-set hook: Code - OSS is themed through Omarchy's own
        # omarchy-theme-set-vscode functions (sourced), gated on its toggle.
        "code",
        # Asserted never to run: the GUI path out of omarchy-default-terminal.
        "omarchy-launch-floating-terminal-with-presentation",
        # Asserted never to run: switching the login shell.
        "chsh",
    ):
        _stub(bins / name, calls)
    # Named so a "no Omarchy here" run can point the installer at a command
    # that really is absent — /usr/bin/omarchy-pkg-add exists on the machines
    # this overlay is developed on, so simply not stubbing it proves nothing.
    pkg_add = "omarchy-pkg-add" if with_omarchy else "omarchy-pkg-add-absent"
    if with_omarchy:
        _stub(bins / pkg_add, calls)
    if with_zsh:
        _stub(bins / "zsh", calls)
    # No plugin is enabled yet, so the jq guard must fall through to enable.
    _stub(bins / "omarchy-plugin-list", calls, 'echo "[]"')
    _stub(bins / "jq", calls, "exit 1")
    # Toggles are off unless a test says otherwise (exit 1 = not enabled).
    _stub(bins / "omarchy-toggle-enabled", calls, "exit 1")
    # Sourced by the theme-set hook for its set_theme; the fake records
    # the arguments and the descriptor path it would have read.
    _stub(
        bins / "omarchy-theme-set-vscode",
        calls,
        'VS_CODE_THEME_DESCRIPTOR="$HOME/.local/state/omarchy/current/theme/vscode.json"\n'
        'set_theme() { printf \'%s\\n\' "set_theme $* descriptor=${VS_CODE_THEME_DESCRIPTOR##*/}" >> "'
        + str(calls)
        + '"; }',
    )
    # fc-list is how the installer discovers whether the font it wants is really
    # present; the real one on the test host would answer for the host's fonts.
    _stub(bins / "fc-list", calls, 'echo "GeistMono Nerd Font,GeistMono NF"')
    # Reports foot until something sets it, then reports what was set.
    _stub(
        bins / "omarchy-default-terminal",
        calls,
        f'if [ $# -eq 0 ]; then cat "{tmp_path}/term" 2>/dev/null || echo foot;'
        f' else printf "%s" "$1" > "{tmp_path}/term"; fi',
    )
    # `clone` must materialise a directory; everything else is a no-op.
    _stub(bins / "git", calls, 'if [ "$1" = clone ]; then mkdir -p "${@: -1}"; fi; exit 0')

    # Seed the parts of a fresh Omarchy $HOME the installer interacts with.
    (home / ".config" / "kitty").mkdir(parents=True)
    (home / ".config" / "kitty" / "kitty.conf").write_text(OMARCHY_KITTY_CONF)
    (home / ".config" / "hypr").mkdir(parents=True)
    for stock in ("bindings.lua", "input.lua", "looknfeel.lua"):
        (home / ".config" / "hypr" / stock).write_text(f"-- stock omarchy {stock}\n")
    (omarchy_path / "default" / "bash").mkdir(parents=True)

    return {
        "home": home,
        "bins": bins,
        "omarchy_path": omarchy_path,
        "calls": calls,
        "pkg_add": pkg_add,
    }


def _run(
    env: dict,
    *args: str,
    zsh: str | None = None,
    zsh_bin: str | None = None,
    extra_env: dict[str, str] | None = None,
    install_sh: Path = INSTALL_SH,
) -> subprocess.CompletedProcess:
    """Run install.sh against the fake tree. Returns the completed process.

    `zsh` pins the resolved zsh path outright; `zsh_bin` instead renames the
    binary the installer looks up on PATH, which is how a test can model "zsh
    does not exist until the package stage installs it" on a host whose own
    /usr/bin/zsh would otherwise always be found. `install_sh` runs a copy of
    the installer (see _checkout) instead of the one in this checkout.
    """
    child_env = {
        "HOME": str(env["home"]),
        "PATH": f"{env['bins']}:/usr/bin:/bin",
        "OMARCHY_PATH": str(env["omarchy_path"]),
        "_HYPRCONF_PKG_ADD": env["pkg_add"],
        # The plugin-discovery wait polls a stub that never answers.
        "_HYPRCONF_PLUGIN_WAIT": "0",
    }
    if zsh is not None:
        child_env["_HYPRCONF_ZSH"] = zsh
    if zsh_bin is not None:
        child_env["_HYPRCONF_ZSH_BIN"] = zsh_bin
    if extra_env:
        child_env.update(extra_env)
    return subprocess.run(
        ["bash", str(install_sh), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=child_env,
    )


# The payload install.sh reads at run time — enough of the repo to run every
# stage from a copy. lib/ is only reached through the theme-set hook's
# PYTHONPATH, which points at the real checkout, so it is not needed here.
PAYLOAD = (
    "install.sh",
    "packages",
    "hypr",
    "bin",
    "hooks",
    "zsh",
    "kitty",
    "fastfetch",
    "themes",
    "wallpapers",
    "plugins",
    "infra",
)

# A git that is real for everything the refresh guard needs (`checkout --`)
# and still fake for the two things a hermetic run must never do: clone Oh My
# Zsh / powerlevel10k off the network, and pull.
GIT_PASSTHROUGH = """\
if [ "$1" = clone ]; then mkdir -p "${@: -1}"; exit 0; fi
case " $* " in *" pull "*) exit 0 ;; esac
exec "$(PATH=/usr/bin:/bin command -v git)" "$@"
"""


def _checkout(tmp_path: Path) -> Path:
    """A throwaway git checkout of the overlay payload.

    The refresh-guard tests have to simulate `omarchy refresh` clobbering the
    checkout and the installer repairing it with git — which must never be
    rehearsed on the real repository the suite runs from.
    """
    repo = tmp_path / "checkout"
    repo.mkdir()
    for name in PAYLOAD:
        src = REPO_ROOT / name
        if src.is_dir():
            shutil.copytree(src, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, repo / name)
    git = ["git", "-c", "user.name=hyprconf-tests", "-c", "user.email=tests@example.invalid"]
    subprocess.run([*git, "init", "-q"], cwd=repo, check=True, timeout=30)
    subprocess.run([*git, "add", "-A"], cwd=repo, check=True, timeout=30)
    subprocess.run([*git, "commit", "-qm", "payload"], cwd=repo, check=True, timeout=30)
    return repo


def _calls(env: dict) -> list[str]:
    return env["calls"].read_text().splitlines()


def _commands(env: dict) -> list[str]:
    """Just the command names invoked.

    Match on these, never on the whole call line: pytest names tmp dirs after
    the test, so a path baked into an argument can contain almost any word and
    produce a false positive.
    """
    return [c.split()[0] for c in _calls(env) if c.strip()]


def _code_only(body: str) -> str:
    """Drop comments so a static scan can't match a comment explaining the rule.

    Naive on `#` inside strings, which is fine for the forbidden-token scans
    below — none of them look for a character that appears in one.
    """
    out = []
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split(" #", 1)[0])
    return "\n".join(out)


def _code_only_qml(body: str) -> str:
    """Drop // comment lines, so a scan cannot match the prose explaining it."""
    return "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("//"))


def _tree_hash(root: Path) -> str:
    """Hash every path and file body under root, for byte-stability checks."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(str(p.relative_to(root)).encode())
        if p.is_symlink():
            h.update(b"->" + str(os.readlink(p)).encode())
        elif p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------


def test_scripts_are_syntactically_valid() -> None:
    for script in (INSTALL_SH, HOOK):
        assert subprocess.run(["bash", "-n", str(script)]).returncode == 0, script


# ---------------------------------------------------------------------------
# Preflight — the guard that keeps this off a non-Omarchy machine
# ---------------------------------------------------------------------------


def test_refuses_without_omarchy_command(tmp_path: Path) -> None:
    env = _setup(tmp_path, with_omarchy=False)
    proc = _run(env)
    assert proc.returncode != 0
    assert "omarchy" in proc.stderr.lower()
    # Nothing may be written before the guard fires.
    assert not (env["home"] / ".zshrc").exists()


def test_refuses_without_omarchy_path(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    env["omarchy_path"] = tmp_path / "no-omarchy-here"  # never created
    proc = _run(env)
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# Idempotency — a re-run is the supported way to pick up changes
# ---------------------------------------------------------------------------


def test_full_run_succeeds_and_is_byte_stable(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    first = _run(env, "--no-update")
    assert first.returncode == 0, first.stderr

    after_first = _tree_hash(env["home"])
    assert _run(env, "--no-update").returncode == 0
    after_second = _tree_hash(env["home"])
    assert _run(env, "--no-update").returncode == 0
    after_third = _tree_hash(env["home"])

    assert after_first == after_second == after_third


def test_zshrc_block_has_exactly_one_marker_pair(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    for _ in range(3):
        _run(env, "--no-update")
    zshrc = (env["home"] / ".zshrc").read_text()
    assert zshrc.count("# >>> hyprconf >>>") == 1
    assert zshrc.count("# <<< hyprconf <<<") == 1


def test_zshrc_preserves_content_outside_the_block(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    (env["home"] / ".zshrc").write_text("export MY_OWN_THING=1\n")
    for _ in range(2):
        _run(env, "--no-update")
    assert "export MY_OWN_THING=1" in (env["home"] / ".zshrc").read_text()


# ---------------------------------------------------------------------------
# Restraint — what the installer must never do
# ---------------------------------------------------------------------------


def test_never_changes_the_login_shell(tmp_path: Path) -> None:
    """The hybrid's whole point: kitty runs zsh, the login shell stays bash."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert "chsh" not in _commands(env)
    assert "chsh" not in _code_only(INSTALL_SH.read_text())


def test_never_opens_the_floating_terminal(tmp_path: Path) -> None:
    """No stage may reach a GUI-opening Omarchy command in a non-interactive
    run (the post-update hook has no display to put a window on)."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-launch-floating") for c in _commands(env))


def test_kitty_conf_gains_only_the_include(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    for _ in range(3):
        _run(env, "--no-update")
    conf = (env["home"] / ".config" / "kitty" / "kitty.conf").read_text()

    # Every original line survives, in order, untouched.
    assert conf.startswith(OMARCHY_KITTY_CONF)
    # And the only thing added is one include.
    assert conf.count("include hyprconf.conf") == 1
    added = conf[len(OMARCHY_KITTY_CONF) :]
    assert set(added.split()) <= {"#", "hyprconf", "overlay", "include", "hyprconf.conf"}


def test_hyprconf_kitty_include_file_is_self_contained(tmp_path: Path) -> None:
    """It must not restate anything Omarchy's kitty.conf owns."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    body = _code_only((env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "background_opacity 0.85" in body
    assert "cursor_trail" in body
    for owned in ("font_family", "font_size", "listen_on", "allow_remote_control", "include "):
        assert owned not in body, owned


def test_shell_line_points_at_zsh_only_when_zsh_exists(tmp_path: Path) -> None:
    """Writing `shell /bin/zsh` without zsh present would stop kitty starting."""
    env = _setup(tmp_path)
    # _HYPRCONF_ZSH="" is the seam for "no zsh on this box" — the real lookup
    # would otherwise find the host's zsh, since /usr/bin has to stay on PATH
    # for coreutils.
    assert _run(env, "--no-update", zsh="").returncode == 0
    body = _code_only((env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "shell " not in body

    env2 = _setup(tmp_path / "with-zsh")
    _run(env2, "--no-update")
    body2 = _code_only((env2["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "shell " in body2


def test_zsh_installed_by_the_package_stage_is_used_in_the_same_run(tmp_path: Path) -> None:
    """The zsh lookup must happen AFTER packages, not when the script starts.

    On a fresh Omarchy zsh does not exist until stage_packages installs it. A
    lookup at startup pins the empty string for the whole run, and the machine
    comes out of its first install with no ~/.zshrc, no powerlevel10k and bash
    in kitty — which is exactly what happened on the first real install.
    """
    env = _setup(tmp_path, with_zsh=False)
    zsh = env["bins"] / "zsh-installed-by-pkg-add"
    # Stand in for `pacman -S zsh`: the binary appears while the run is going.
    _stub(
        env["bins"] / env["pkg_add"],
        env["calls"],
        f'printf "#!/usr/bin/env bash\\nexit 0\\n" > "{zsh}"; chmod 755 "{zsh}"',
    )

    proc = _run(env, "--no-update", zsh_bin=zsh.name)
    assert proc.returncode == 0, proc.stderr

    assert (env["home"] / ".zshrc").read_text().count("powerlevel10k") >= 1
    assert (env["home"] / ".p10k.zsh").is_symlink()
    assert (env["home"] / ".oh-my-zsh").is_dir()
    kitty_conf = (env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text()
    assert f"shell {zsh}" in kitty_conf


# ---------------------------------------------------------------------------
# The ~/.config/hypr override files
# ---------------------------------------------------------------------------


def test_hypr_overrides_are_symlinked_with_a_stock_backup(tmp_path: Path) -> None:
    """bindings/input/looknfeel are Omarchy's own post-defaults require points.

    Each stock file is Omarchy's commented template, so the backup is what
    makes the overlay reversible by hand.
    """
    env = _setup(tmp_path)
    for _ in range(2):  # the backup must not be re-taken from our own symlink
        _run(env, "--no-update")
    hypr = env["home"] / ".config" / "hypr"
    for name in ("bindings.lua", "input.lua", "looknfeel.lua"):
        assert hypr.joinpath(name).is_symlink(), name
        assert hypr.joinpath(name).resolve() == REPO_ROOT / "hypr" / name
        assert hypr.joinpath(f"{name}.stock").read_text() == f"-- stock omarchy {name}\n"


def test_monitor_presets_are_installed_without_touching_the_active_layout(
    tmp_path: Path,
) -> None:
    """Presets are inert files; monitors.lua stays whatever the machine chose.

    Omarchy writes its own auto layout there, and switch_monitor.sh only
    symlinks a preset over it when a hotkey is actually pressed.
    """
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")
    for preset in PRESETS:
        assert hypr.joinpath(preset).is_file(), preset
    assert hypr.joinpath("monitors.lua").read_text() == "-- omarchy auto layout\n"
    # Saved before a preset switch can overwrite it — the only way back.
    assert hypr.joinpath("monitors.lua.stock").read_text() == "-- omarchy auto layout\n"


def test_switch_monitor_reaches_every_preset_and_back(tmp_path: Path) -> None:
    """Each shipped preset must be selectable, and stock must restore Omarchy's.

    The presets carry hyprconf's workspace-to-monitor rules, so one that cannot
    be named is dead config.
    """
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")
    switch = hypr / "scripts" / "switch_monitor.sh"

    for name, preset in (
        ("bedroom", "pcMonitors.bedroom.lua"),
        ("kitchen", "pcMonitors.kitchen.lua"),
        ("K", "pcMonitors.K.lua"),
        ("pc", "pcMonitors.lua"),
        ("laptop", "laptopMonitors.lua"),
    ):
        proc = subprocess.run(
            ["bash", str(switch), name],
            capture_output=True,
            text=True,
            env={"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stderr
        assert hypr.joinpath("monitors.lua").resolve() == hypr.joinpath(preset).resolve()

    proc = subprocess.run(
        ["bash", str(switch), "stock"],
        capture_output=True,
        text=True,
        env={"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr
    # A real file again, as Omarchy's own tooling expects to find there.
    assert not hypr.joinpath("monitors.lua").is_symlink()
    assert hypr.joinpath("monitors.lua").read_text() == "-- omarchy auto layout\n"


def test_natural_scroll_is_the_default(tmp_path: Path) -> None:
    """Omarchy ships natural_scroll off for the touchpad and off for the mouse."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    body = (env["home"] / ".config" / "hypr" / "input.lua").read_text()
    # Once for the pointer, once inside the touchpad table.
    assert body.count("natural_scroll = true") == 2


def test_hypr_overrides_parse_as_lua(tmp_path: Path) -> None:
    """A syntax error here is a broken desktop, not a failed test run."""
    luac = shutil.which("luac") or shutil.which("luac5.4")
    if luac is None:
        pytest.skip("no luac available to parse the Hyprland Lua config")
    for lua in sorted((REPO_ROOT / "hypr").glob("*.lua")):
        proc = subprocess.run(
            [luac, "-p", str(lua)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr


def test_theme_is_installed_as_a_symlink(tmp_path: Path) -> None:
    """A symlink, so a `git pull` updates the theme in place; omarchy-theme-set
    (4.0.0-1) only tests `-d` and `cp -r`s the contents, both of which follow
    a link."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert (env["home"] / ".config" / "omarchy" / "themes" / "hyprconf").is_symlink()


def test_never_switches_the_active_theme(tmp_path: Path) -> None:
    """Installing lists hyprconf's theme; it never takes the active one away.

    The overlay re-applies itself after every Omarchy update, so a stage that
    activated the theme would keep overriding a choice the user had since made.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert "omarchy-theme-set" not in _commands(env)
    assert "omarchy-theme-set" not in _code_only(INSTALL_SH.read_text())


def test_stock_snapshot_captures_the_live_layout_not_the_install_time_one(
    tmp_path: Path,
) -> None:
    """`stock` must restore what was actually live, not a stale install snapshot.

    Omarchy keeps writing to monitors.lua after the overlay is installed —
    `omarchy-hyprland-monitor-scaling` seds the scale lines in place — so a
    snapshot taken once at install time goes stale, and switch_monitor.sh
    replaces that file with a symlink, destroying the only copy. The snapshot
    has to be re-taken at the moment of destruction.
    """
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")

    # Omarchy edits the live file after install, exactly as its scaling tool does.
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n-- DRIFTED\n")

    switch = hypr / "scripts" / "switch_monitor.sh"
    child = {"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"}
    assert (
        subprocess.run(
            ["bash", str(switch), "bedroom"], capture_output=True, text=True, env=child
        ).returncode
        == 0
    )
    assert (
        subprocess.run(
            ["bash", str(switch), "stock"], capture_output=True, text=True, env=child
        ).returncode
        == 0
    )
    assert "DRIFTED" in hypr.joinpath("monitors.lua").read_text()


def test_presets_are_seeded_once_and_never_overwritten(tmp_path: Path) -> None:
    """A preset describes one machine's desk, so the machine owns it after seeding.

    The post-update hook re-runs the installer after every Omarchy update, and
    switch_monitor.sh promises edits survive re-selecting a preset — copying the
    repo's version over the top on each run would break that silently.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    preset = env["home"] / ".config" / "hypr" / "pcMonitors.bedroom.lua"
    preset.write_text("-- my desk, my monitors\n")
    _run(env, "--no-update")
    assert preset.read_text() == "-- my desk, my monitors\n"


def test_no_shipped_script_uses_the_dead_hyprctl_keyword_path() -> None:
    """`hyprctl keyword` is a silent no-op under Hyprland's Lua parser.

    It answers "keyword can't work with non-legacy parsers. Use eval." and
    still exits 0 — so a script using it fails without failing, and the hotkey
    driving it simply does nothing. `hyprctl eval` is the replacement and does
    report errors (exit 7). Verified against Hyprland 0.56.2.
    """
    offenders = []
    for script in sorted((REPO_ROOT / "hypr" / "scripts").iterdir()):
        if not script.is_file():
            continue
        for lineno, line in enumerate(_code_only(script.read_text()).splitlines(), 1):
            if re.search(r"hyprctl\s+(--batch\s+)?[\"']?keyword\b", line):
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert not offenders, "hyprctl keyword is a silent no-op — use hyprctl eval:\n" + "\n".join(
        offenders
    )


def test_gap_reader_understands_the_current_hyprctl_shape() -> None:
    """0.56 reports four-sided gaps under "css"; older builds used "custom".

    Reading only the old name makes every keypress compute its step from 0, so
    the keys look alive (0 -> 2 -> 0) while discarding the configured gap.
    """
    src = (REPO_ROOT / "hypr" / "scripts" / "adjust-gaps").read_text()
    assert "'css'" in src or '"css"' in src


def test_osd_keys_are_left_to_omarchy(tmp_path: Path) -> None:
    """Volume and brightness keys must keep reaching Omarchy's own commands.

    hyprconf bound them to raw wpctl / hyprconf-brightness, whose extra job was
    feeding hyprconf's quickshell OSD. That OSD does not exist here, and
    Omarchy's own commands end by calling omarchy-osd — so rebinding these keys
    silently removes the on-screen indicator while still changing the level,
    which reads as "the volume popup disappeared".
    """
    # Match on bind CALLS, not on the file's prose: the comments explaining why
    # these keys are left alone necessarily name them.
    bindings = "\n".join(
        line
        for line in (REPO_ROOT / "hypr" / "bindings.lua").read_text().splitlines()
        if not line.lstrip().startswith("--")
    )
    for key in (
        "XF86AudioRaiseVolume",
        "XF86AudioLowerVolume",
        "XF86AudioMute",
        "XF86AudioMicMute",
        "XF86MonBrightnessUp",
        "XF86MonBrightnessDown",
        "XF86AudioNext",
        "XF86AudioPrev",
        "XF86AudioPlay",
        "XF86AudioPause",
    ):
        assert key not in bindings, f"{key} must be left to Omarchy (it drives the OSD)"


def test_every_binding_carries_a_description(tmp_path: Path) -> None:
    """A description is what puts a key in Omarchy's SUPER+K keybindings menu.

    hl.bind records none, so hyprconf's whole keymap was invisible there while
    the menu still listed the Omarchy defaults hyprconf had replaced — worse
    than listing nothing. o.bind (via the rebind helper) records one.
    """
    src = (REPO_ROOT / "hypr" / "bindings.lua").read_text()
    code = [ln for ln in src.splitlines() if not ln.lstrip().startswith("--")]
    assert not [ln for ln in code if re.search(r"\bhl\.bind\s*\(", ln)], (
        "use rebind()/o.bind so the key appears in the keybindings menu"
    )
    # rebind(keys, description, dispatcher[, options]) — the description is a
    # literal string, so a two-argument call is a dropped description.
    for ln in code:
        if ln.lstrip().startswith("local function rebind"):
            continue  # the helper's own signature, not a call
        m = re.search(r"\brebind\((.*)\)\s*$", ln)
        if m:
            assert '"' in m.group(1).split(",", 1)[-1], f"missing description: {ln.strip()}"


def test_no_shipped_script_uses_the_dead_two_token_dispatch() -> None:
    """`hyprctl dispatch dpms on` is a 0.55-ism that no longer parses.

    Under Hyprland's Lua parser the two-token form is a syntax error and exits
    non-zero into a discarded stream, so the dark-output recovery in
    switch_monitor.sh never ran once. The working form is the one Omarchy uses:
    hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'.
    """
    offenders = []
    for script in sorted((REPO_ROOT / "hypr" / "scripts").iterdir()):
        if not script.is_file():
            continue
        for lineno, line in enumerate(_code_only(script.read_text()).splitlines(), 1):
            if re.search(r"hyprctl\s+dispatch\s+[a-z_]+\s+[a-z_]+", line):
                offenders.append(f"{script.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "two-token `hyprctl dispatch` does not parse under the Lua config — "
        "use hyprctl dispatch 'hl.dsp.…':\n" + "\n".join(offenders)
    )


def test_app_keys_go_through_omarchy_launchers(tmp_path: Path) -> None:
    """The keymap must not name app binaries — Omarchy's defaults own that.

    A binding that execs `firefox` pins the choice in a file the user cannot
    reach from Omarchy's own menu, and skips uwsm-app scoping and the
    cwd-inheriting terminal launch that come with the native launchers.
    """
    code = "\n".join(
        ln
        for ln in (REPO_ROOT / "hypr" / "bindings.lua").read_text().splitlines()
        if not ln.lstrip().startswith("--")
    )
    # The quoted form is the point: `exec_cmd("nautilus")` pins the app, while
    # `exec_cmd("omarchy-launch-nautilus")` resolves the user's default.
    for binary in ('"firefox"', '"nautilus"', '"code"', '"kitty"', '"dolphin"'):
        assert binary not in code, f"{binary} is an Omarchy default, not a keymap constant"


def test_default_apps_are_seeded_once(tmp_path: Path) -> None:
    """Seeded to hyprconf's picks on first install, then the user's to change."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    calls = _calls(env)
    assert any(c.startswith("omarchy-default-browser firefox") for c in calls)
    assert any(c.startswith("omarchy-default-editor code") for c in calls)

    env["calls"].write_text("")
    _run(env, "--no-update")
    # Not `omarchy-default-*`: stage_terminal calls omarchy-default-terminal on
    # every run by design, to check what the default already is.
    again = _calls(env)
    assert not any(c.startswith("omarchy-default-browser") for c in again)
    assert not any(c.startswith("omarchy-default-editor") for c in again)


# ---------------------------------------------------------------------------
# Wallpapers
# ---------------------------------------------------------------------------


def test_wallpapers_land_where_omarchy_looks_for_them(tmp_path: Path) -> None:
    """Omarchy only ever scans two directories, both keyed to the ACTIVE theme.

    omarchy-theme-bg-next and omarchy-theme-bg-switcher both read the active
    theme's own backgrounds/ plus ~/.config/omarchy/backgrounds/<theme>/. A
    wallpaper filed anywhere else simply never appears in the switcher, with no
    error to explain why — which is what happened when hyprconf's gruvbox shot
    lived in hyprconf's own theme directory.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    seeded = env["home"] / ".config" / "omarchy" / "backgrounds" / "gruvbox" / "gruvbox.jpg"
    assert seeded.is_file()
    assert seeded.read_bytes() == (REPO_ROOT / "wallpapers" / "gruvbox.jpg").read_bytes()


def test_a_replaced_wallpaper_is_left_alone(tmp_path: Path) -> None:
    """Backgrounds are seeded, not synced — the folder is the user's to curate."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    seeded = env["home"] / ".config" / "omarchy" / "backgrounds" / "gruvbox" / "gruvbox.jpg"
    seeded.write_bytes(b"my own wallpaper")
    _run(env, "--no-update")
    assert seeded.read_bytes() == b"my own wallpaper"


# ---------------------------------------------------------------------------
# The system font
# ---------------------------------------------------------------------------


def test_font_is_set_once_and_then_left_alone(tmp_path: Path) -> None:
    """Which font is running is the user's call after the first install.

    The post-update hook re-runs this installer after every Omarchy update, so
    a stage that re-asserted the font would quietly undo `omarchy font set` —
    the same way stage_theme used to take the theme back.
    """
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert any(c.startswith("omarchy-font-set") for c in _calls(env))

    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-font-set") for c in _calls(env))


def test_font_stage_is_skipped_when_the_font_is_not_installed(tmp_path: Path) -> None:
    """A cosmetic stage must not take the whole install down.

    omarchy-font-set exits 1 on a family fc-list does not know, which under
    `set -e` would abort the run — so the family is resolved from fc-list first
    and the stage bows out if it is missing.
    """
    env = _setup(tmp_path)
    _stub(env["bins"] / "fc-list", env["calls"], 'echo "DejaVu Sans Mono"')
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not any(c.startswith("omarchy-font-set") for c in _calls(env))
    # No marker written, so it will apply once the package really is there.
    assert not (env["home"] / ".local" / "state" / "hyprconf" / "font-applied").exists()


# ---------------------------------------------------------------------------
# The bar widget
# ---------------------------------------------------------------------------


def test_bar_widget_never_sizes_itself_off_its_parent() -> None:
    """A widget whose implicit size reads `parent` is invisible on the bar.

    Omarchy's ModuleSlot takes its height from the widget's implicit size, so
    `implicitHeight: parent.height` closes a binding loop. QML breaks a loop by
    dropping the binding, which leaves the widget zero-height — it still loads,
    logs nothing at any verbosity, and paints nothing. That silence is what
    makes this worth a test rather than a comment: there is no error to grep
    for, only a gap in the bar.
    """
    offenders = [
        f"{qml.relative_to(REPO_ROOT)}: {line.strip()}"
        for qml in sorted((REPO_ROOT / "plugins").glob("*/*.qml"))
        for line in _code_only_qml(qml.read_text()).splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]
    assert list((REPO_ROOT / "plugins").glob("*/*.qml")), "no plugin QML found"
    assert not offenders, (
        "Bar widget implicit size must not depend on `parent` (binding loop -> "
        "zero size -> invisible widget):\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_no_update_never_runs_omarchy_update(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-update") for c in _calls(env))


def test_sync_runs_omarchy_update_and_never_pacman(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--sync")
    calls = _calls(env)
    assert any(c.startswith("omarchy-update") for c in calls)
    assert not any(c.startswith("pacman") for c in calls)


def test_no_packages_skips_the_only_privileged_stage(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--no-packages", "--no-update")
    assert not any(c.startswith("omarchy-pkg-add") for c in _calls(env))

    env2 = _setup(tmp_path / "default-run")
    _run(env2, "--no-update")
    assert any(c.startswith("omarchy-pkg-add") for c in _calls(env2))


def test_unknown_flag_is_rejected(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    proc = _run(env, "--definitely-not-a-flag")
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# The post-update hook
# ---------------------------------------------------------------------------


def test_hook_is_installed_with_a_resolved_path(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--no-update")
    installed = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    body = installed.read_text()
    assert "@HYPRCONF_DIR@" not in body, "placeholder was not substituted"
    assert str(REPO_ROOT) in body
    assert os.access(installed, os.X_OK)


def _theme_state(env: dict, *, extension: str = "pub.lumon") -> Path:
    """An active Omarchy theme as omarchy-theme-set leaves it: theme.name plus
    the rendered colors.toml and the VS Code descriptor."""
    theme = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme.parent / "theme.name").write_text("lumon\n")
    (theme / "colors.toml").write_text(
        'mode = "dark"\nbackground = "#16242d"\nforeground = "#d6e2ee"\naccent = "#8bc9eb"\n'
        'dark_background = "#101b21"\nlighter_background = "#1b2d40"\n'
    )
    (theme / "vscode.json").write_text(json.dumps({"name": "Lumon", "extension": extension}))
    return theme


def _firefox_profile(env: dict) -> Path:
    ff = env["home"] / ".config" / "mozilla" / "firefox"
    profile = ff / "abc.default-release"
    profile.mkdir(parents=True, exist_ok=True)
    (ff / "profiles.ini").write_text(
        "[Profile0]\nName=default-release\nIsRelative=1\nPath=abc.default-release\n"
        "[Install4F96]\nDefault=abc.default-release\n"
    )
    return profile


def test_theme_set_hook_is_installed_beside_the_post_update_one(tmp_path: Path) -> None:
    """omarchy-theme-set ends with `omarchy-hook theme-set <name>`, which runs
    ~/.config/omarchy/hooks/theme-set.d/*. The hook must carry the resolved
    checkout path (it puts lib/ on PYTHONPATH), be executable, and never
    abort a theme switch (no set -e) or escalate."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    installed = env["home"] / ".config" / "omarchy" / "hooks" / "theme-set.d" / "10-hyprconf"
    body = installed.read_text()
    assert "@HYPRCONF_DIR@" not in body and str(REPO_ROOT) in body
    assert os.access(installed, os.X_OK)
    code = _code_only(body)
    assert "set -e" not in code and "sudo" not in code and "omarchy-update" not in code
    assert "omarchy-theme-set-vscode" in code and "hyprconf.firefox_theme" in code


def test_theme_set_hook_extends_the_theme_to_code_oss_and_firefox(tmp_path: Path) -> None:
    """Omarchy themes VS Code by the Microsoft build's paths; Arch's `code` is
    Code - OSS (~/.config/Code - OSS, ~/.vscode-oss). The hook reuses
    Omarchy's own set_theme with those paths, falls back to the generated
    theme when the descriptor's extension is not installed (Open VSX may
    lack it), and writes Firefox's userChrome.css + user.js from the
    rendered colors.toml. install.sh runs the hook once for the active
    theme, so nothing waits for the next switch."""
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq for the descriptor read")
    env = _setup(tmp_path)
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')
    _theme_state(env)
    profile = _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr

    home = env["home"]
    calls = _calls(env)
    settings = f"{home}/.config/Code - OSS/User/settings.json"
    assert (
        f"set_theme code {settings} {home}/.vscode-oss/extensions descriptor=vscode.json" in calls
    )
    # `code --list-extensions` (stub) lists nothing -> the generated-theme fallback.
    assert (
        f"set_theme code {settings} {home}/.vscode-oss/extensions descriptor=.no-descriptor"
        in calls
    )
    assert "Open VSX" in proc.stderr

    css = (profile / "chrome" / "userChrome.css").read_text()
    assert "--toolbar-bgcolor: #16242d !important;" in css
    js = (profile / "user.js").read_text()
    assert 'user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);' in js
    assert 'user_pref("ui.systemUsesDarkTheme", 1);' in js

    # Idempotent: a second run (the post-update hook's) changes nothing.
    before = _tree_hash(profile)
    _run(env, "--no-update")
    assert _tree_hash(profile) == before


def test_theme_set_hook_honours_omarchys_vscode_toggle(tmp_path: Path) -> None:
    """`omarchy toggle skip-vscode-theme-changes` is how Omarchy's own script
    is told to leave VS Code alone; the Code - OSS bridge must obey it too."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-toggle-enabled", env["calls"], "exit 0")
    _theme_state(env)
    _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not any(c.startswith("set_theme") for c in _calls(env))
    # Firefox is independent of that toggle.
    assert (
        env["home"] / ".config" / "mozilla" / "firefox" / "abc.default-release" / "user.js"
    ).exists()


def test_theme_stage_is_a_noop_without_an_active_theme(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (
        env["home"] / ".config" / "mozilla" / "firefox" / "abc.default-release" / "user.js"
    ).exists()
    assert not any(c.startswith("set_theme") for c in _calls(env))


def test_hook_cannot_recurse_or_escalate() -> None:
    """It runs *inside* omarchy-update, so it must not update or use sudo."""
    code = _code_only(HOOK.read_text())
    assert "--no-update" in code and "--no-packages" in code
    # It must not re-enter the thing that invoked it, nor the wrapper for it.
    assert "omarchy-update" not in code
    assert "hyprsync" not in code
    assert "HYPRCONF_SYNC_RUNNING" in code, "missing the hyprsync recursion guard"
    assert "sudo" not in code
    # No `set -e`: omarchy-hook must never let a hook abort an update.
    assert "set -e" not in code


# ---------------------------------------------------------------------------
# Static scans over the whole overlay tree
# ---------------------------------------------------------------------------


def _overlay_scripts() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "install.sh", "hypr", "bin", "hooks", "zsh", "kitty", "plugins"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [REPO_ROOT / line for line in out.stdout.split()]
    return [p for p in paths if p.suffix in {".sh", ""} and p.is_file() and p.suffix != ".png"]


def test_overlay_never_uses_forbidden_pacman_forms() -> None:
    """`-Syu` is blocked by Omarchy's ALPM guard; `-R` would dismantle Omarchy."""
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        assert "pacman -Syu" not in code, script
        assert "pacman -Syyu" not in code, script
        assert "pacman -R" not in code, script


def test_overlay_never_reaches_into_the_retired_standalone_installer() -> None:
    """setup.sh is gone with the standalone desktop; a reference to it is dead code
    (and its remove_aur_packages would have offered to uninstall Omarchy itself)."""
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        assert "setup.sh" not in code, script
        assert "remove_aur_packages" not in code, script


def test_overlay_installs_no_aur_packages() -> None:
    """Per AGENTS.md: official repos only, and AUR never without asking first."""
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        assert "yay " not in code, script
        assert "makepkg" not in code, script
        assert "omarchy-pkg-aur-add" not in code, script


# ---------------------------------------------------------------------------
# The Firefox policy — the overlay's one write outside $HOME
# ---------------------------------------------------------------------------


def test_firefox_policy_is_installed_via_sudo_when_interactive(tmp_path: Path) -> None:
    """setup.sh's setup_firefox, ported: Firefox reads enterprise policies only
    from root-owned paths, so the file goes through sudo to (an overridden)
    /etc/firefox/policies. A matching file is left alone, so a re-run — and
    every hyprsync after it — never re-prompts for a password."""
    env = _setup(tmp_path)
    # A sudo that actually runs its command, so the install lands in the tree.
    _stub(env["bins"] / "sudo", env["calls"], '"$@"')
    policies = tmp_path / "etc" / "firefox" / "policies"
    extra = {"_HYPRCONF_ASSUME_TTY": "1", "_HYPRCONF_FIREFOX_POLICIES": str(policies)}
    proc = _run(env, "--no-update", extra_env=extra)
    assert proc.returncode == 0, proc.stderr
    src = REPO_ROOT / "infra" / "firefox" / "policies.json"
    assert (policies / "policies.json").read_text() == src.read_text()

    env["calls"].write_text("")
    _run(env, "--no-update", extra_env=extra)
    assert not any(c.startswith("sudo") for c in _calls(env))


def test_firefox_policy_is_skipped_without_a_terminal(tmp_path: Path) -> None:
    """The post-update hook runs non-interactively inside omarchy-update; a
    sudo password prompt there would stall the whole update, so no tty means
    no attempt (and no half-configured warning-free failure)."""
    env = _setup(tmp_path)
    policies = tmp_path / "etc" / "firefox" / "policies"
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_FIREFOX_POLICIES": str(policies)})
    assert proc.returncode == 0, proc.stderr
    assert not (policies / "policies.json").exists()
    assert not any(c.startswith("sudo") for c in _calls(env))


def test_firefox_policy_sits_behind_the_no_packages_gate(tmp_path: Path) -> None:
    """--no-packages means "no sudo" — the hook passes it for that reason, so
    the only other privileged stage must honor it too."""
    env = _setup(tmp_path)
    policies = tmp_path / "etc" / "firefox" / "policies"
    _run(
        env,
        "--no-update",
        "--no-packages",
        extra_env={"_HYPRCONF_ASSUME_TTY": "1", "_HYPRCONF_FIREFOX_POLICIES": str(policies)},
    )
    assert not any(c.startswith("sudo") for c in _calls(env))
    assert not (policies / "policies.json").exists()


# ---------------------------------------------------------------------------
# The retired TUI
# ---------------------------------------------------------------------------


def test_retired_tui_is_swept_up(tmp_path: Path) -> None:
    """Earlier overlay versions installed the hyprconf TUI: a launcher, two
    symlinks into the checkout, a desktop entry and a managed block at the
    tail of hyprland.lua loading conf.d/*.lua. The TUI is gone; a re-run
    must leave an upgraded machine looking like a fresh one, while the user's
    own conf.d files and everything else in hyprland.lua survive."""
    env = _setup(tmp_path)
    home = env["home"]
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "hyprconf").write_text("#!/bin/bash\n")
    (home / ".local" / "lib").mkdir(parents=True)
    (home / ".local" / "lib" / "hyprconf").symlink_to(REPO_ROOT / "lib" / "hyprconf")
    (home / ".config" / "hypr" / "scripts").mkdir(parents=True)
    (home / ".config" / "hypr" / "scripts" / "hyprconf-tui").symlink_to(
        tmp_path / "old-checkout" / "tui"
    )
    (home / ".local" / "share" / "applications").mkdir(parents=True)
    (home / ".local" / "share" / "applications" / "hyprconf.desktop").write_text(
        "[Desktop Entry]\n"
    )
    hyprland = home / ".config" / "hypr" / "hyprland.lua"
    hyprland.write_text(
        'require("default.hypr.omarchy")\n\n-- >>> hyprconf >>>\nloadfile("conf.d")\n-- <<< hyprconf <<<\n'
    )
    conf_d = home / ".config" / "hypr" / "conf.d"
    conf_d.mkdir()
    (conf_d / "local.lua").write_text("hl.config({})\n")

    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (home / ".local" / "bin" / "hyprconf").exists()
    assert not (home / ".local" / "lib" / "hyprconf").is_symlink()
    assert not (home / ".config" / "hypr" / "scripts" / "hyprconf-tui").is_symlink()
    assert not (home / ".local" / "share" / "applications" / "hyprconf.desktop").exists()
    assert hyprland.read_text() == 'require("default.hypr.omarchy")\n'
    assert (conf_d / "local.lua").exists()
    assert "conf.d" in proc.stderr  # told, not deleted

    # A fresh box has none of it; the sweep must be a silent no-op there.
    env2 = _setup(tmp_path / "fresh")
    proc2 = _run(env2, "--no-update")
    assert proc2.returncode == 0, proc2.stderr
    assert "conf.d" not in proc2.stderr
    assert not any(
        "python-textual" in ln for ln in (REPO_ROOT / "packages").read_text().splitlines()
    )


def test_stale_username_clones_are_retired(tmp_path: Path) -> None:
    """The first overlay versions cloned the clock with omarchy-plugin-clone,
    which names the copy <user>.clock. Once hyprconf.clock exists that copy
    is a second clock on the bar (seen after an upgrade). The stage retires
    every clonedFrom copy of the built-in that is not ours, through Omarchy's
    own plugin commands, and does so on every run."""
    env = _setup(tmp_path)
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq for the plugin list")
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')
    listing = json.dumps(
        [
            {"id": "omarchy.clock", "enabled": False, "clonedFrom": ""},
            {"id": "testuser.clock", "enabled": True, "clonedFrom": "omarchy.clock"},
            {"id": "hyprconf.clock", "enabled": True, "clonedFrom": "omarchy.clock"},
            {"id": "testuser.workspaces", "enabled": True, "clonedFrom": "omarchy.workspaces"},
            {"id": "hyprconf.workspaces", "enabled": True, "clonedFrom": "omarchy.workspaces"},
        ]
    )
    _stub(env["bins"] / "omarchy-plugin-list", env["calls"], f"cat <<'EOF'\n{listing}\nEOF")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-disable testuser.clock" in calls
    assert "omarchy-plugin-remove testuser.clock --yes" in calls
    assert "omarchy-plugin-disable testuser.workspaces" in calls
    assert "omarchy-plugin-remove testuser.workspaces --yes" in calls
    for keep in ("hyprconf.clock", "hyprconf.workspaces", "omarchy.clock", "omarchy.workspaces"):
        assert f"omarchy-plugin-disable {keep}" not in calls
        assert f"omarchy-plugin-remove {keep} --yes" not in calls
    assert any(c.startswith("omarchy-restart-shell") for c in calls)


def test_stock_widget_left_beside_our_copy_is_healed_by_reseating(tmp_path: Path) -> None:
    """After an upgrade from the first overlay versions both omarchy.clock and
    hyprconf.clock can sit on the bar (their <user>.clock clone had taken the
    stock slot, so ours was appended; retiring the clone restored the stock
    entry). The registry swaps a copy into the stock slot only at enable
    time, so the stage takes ours off and puts it back — every run, before
    the set-once marker — and re-applies the format and anchor that travel
    with the layout entry."""
    env = _setup(tmp_path)
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq for the layout read")
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')
    state = env["home"] / ".local" / "state" / "hyprconf"
    state.mkdir(parents=True)
    (state / "clock-applied").write_text("")  # set-once path already done
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    shell_json.parent.mkdir(parents=True, exist_ok=True)
    shell_json.write_text(
        json.dumps(
            {
                "bar": {
                    "centerAnchor": "omarchy.clock",
                    "layout": {
                        "left": ["omarchy.menu", {"id": "hyprconf.workspaces"}],
                        "center": [
                            {"id": "omarchy.clock"},
                            {"id": "hyprconf.clock", "format": "x"},
                        ],
                        "right": [],
                    },
                }
            }
        )
    )
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-disable hyprconf.clock" in calls
    assert "omarchy-plugin-enable hyprconf.clock" in calls
    assert "omarchy-bar set hyprconf.clock format hh:mm:ss AP" in calls
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "hyprconf.clock"
    assert any(c.startswith("omarchy-restart-shell") for c in calls)
    # The workspaces slot was fine (only ours on the bar): left alone.
    assert "omarchy-plugin-disable hyprconf.workspaces" not in calls

    # Only the copy on the bar: nothing to heal, nothing re-applied.
    shell_json.write_text(
        json.dumps(
            {"bar": {"layout": {"left": [], "center": [{"id": "hyprconf.clock"}], "right": []}}}
        )
    )
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any("hyprconf.clock" in c for c in _calls(env) if c.startswith("omarchy-plugin"))


def test_clones_found_by_manifest_on_disk_are_retired_too(tmp_path: Path) -> None:
    """A <user>.clock copy the running shell has not scanned (or a run with
    no shell to ask) still has its manifest on disk; it is retired from that."""
    env = _setup(tmp_path)
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq for the manifest read")
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')
    stale = env["home"] / ".config" / "omarchy" / "plugins" / "testuser.clock"
    stale.mkdir(parents=True)
    (stale / "manifest.json").write_text(
        json.dumps({"id": "testuser.clock", "omarchy": {"clonedFrom": "omarchy.clock"}})
    )
    (stale / "BarWidget.qml").write_text("")
    proc = _run(env, "--no-update")  # omarchy-plugin-list still answers []
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-disable testuser.clock" in calls
    assert "omarchy-plugin-remove testuser.clock --yes" in calls
    assert not stale.exists()


def test_defaults_marker_waits_for_a_successful_seed(tmp_path: Path) -> None:
    """A first run with --no-packages (firefox/code not installed yet) must not
    record the defaults as applied, or they would never be seeded."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-default-browser", env["calls"], "exit 1")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (env["home"] / ".local" / "state" / "hyprconf" / "defaults-applied").exists()
    _stub(env["bins"] / "omarchy-default-browser", env["calls"], "exit 0")
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert any(c.startswith("omarchy-default-browser firefox") for c in _calls(env))
    assert (env["home"] / ".local" / "state" / "hyprconf" / "defaults-applied").exists()


def test_every_shipped_tool_lands_on_path(tmp_path: Path) -> None:
    """bin/hyprconf-* is the whole tool set: the two bar-widget feeders and
    hyprconf-yubikey. Installed by glob, so a new tool is one file."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    shipped = sorted(p.name for p in (REPO_ROOT / "bin").glob("hyprconf-*"))
    assert {"hyprconf-stats", "hyprconf-gpu-info", "hyprconf-yubikey"} <= set(shipped)
    for name in shipped:
        installed = env["home"] / ".local" / "bin" / name
        assert os.access(installed, os.X_OK), name
        assert installed.read_bytes() == (REPO_ROOT / "bin" / name).read_bytes()
    assert not (env["home"] / ".local" / "bin" / "hyprconf").exists()


# ---------------------------------------------------------------------------
# The bar clock
# ---------------------------------------------------------------------------


def _plugin_fixtures(env: dict, tmp_path: Path) -> Path:
    """Real jq + a fake omarchy.clock plugin source behind a catalog stub.

    The stage resolves the plugin source from omarchy-plugin-catalog at
    runtime and rewrites its manifest with jq, so these tests need the real
    jq (the default stub plays "broken") and a catalog pointing at a source
    tree under tmp_path."""
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq available for the clock stage")
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')
    src = tmp_path / "clock-src"
    src.mkdir(exist_ok=True)
    (src / "manifest.json").write_text(
        json.dumps(
            {
                "id": "omarchy.clock",
                "name": "Clock",
                "barWidget": {"displayName": "Clock"},
                "omarchy": {"clonePaths": [{"source": "x", "target": "x"}]},
            }
        )
    )
    (src / "BarWidget.qml").write_text("precision: SystemClock.Minutes\n")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            [
                {
                    "id": "omarchy.clock",
                    "firstParty": True,
                    "sourceDir": str(src),
                    "manifestPath": str(src / "manifest.json"),
                    "name": "Clock",
                },
            ]
        )
    )
    _stub(env["bins"] / "omarchy-plugin-catalog", env["calls"], f'cat "{catalog}"')
    return src


def test_clock_is_copied_patched_and_set_once(tmp_path: Path) -> None:
    """The stock widget samples SystemClock at Minutes precision (shell/
    plugins/panels/clock/BarWidget.qml), so a seconds format freezes. The
    stage copies the widget to the project's own hyprconf.clock — source
    resolved from omarchy-plugin-catalog at runtime, manifest rewritten the
    way omarchy-plugin-clone's update_manifest does — and patches the copy.
    Set-once: the marker is what keeps the post-update hook from reverting a
    format the user later picked."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-enable hyprconf.clock" in calls
    assert "omarchy-bar set hyprconf.clock format hh:mm:ss AP" in calls
    # The shell loaded/drew the stock widget before the patch; without a
    # restart the seconds sit frozen.
    assert any(c.startswith("omarchy-restart-shell") for c in calls)

    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.clock"
    widget = (plug / "BarWidget.qml").read_text()
    assert "SystemClock.Seconds" in widget
    assert "SystemClock.Minutes" not in widget
    manifest = json.loads((plug / "manifest.json").read_text())
    assert manifest["id"] == "hyprconf.clock"
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.clock"
    assert "clonePaths" not in manifest["omarchy"]
    assert manifest["barWidget"]["displayName"] == "hyprconf Clock"

    env["calls"].write_text("")
    _run(env, "--no-update")
    again = _calls(env)
    assert not any(c.startswith("omarchy-plugin-catalog") for c in again)
    assert not any(c.startswith("omarchy-bar") for c in again)


def test_clock_widget_id_carries_no_username(tmp_path: Path) -> None:
    """omarchy-plugin-clone names clones <username>.<id> with no way to
    choose otherwise — a username must never leak into shipped
    configuration. The stage builds the copy itself under the project's own
    namespace, beside hyprconf.resources."""
    code = _code_only(INSTALL_SH.read_text())
    assert "hyprconf.clock" in code
    assert "omarchy-plugin-clone" not in code
    assert "id -un" not in code
    assert "$USER" not in code and "${USER" not in code

    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    _run(env, "--no-update")
    user = subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()
    plugins = env["home"] / ".config" / "omarchy" / "plugins"
    assert not (plugins / f"{user}.clock").exists()
    assert (plugins / "hyprconf.clock").is_dir()


def test_clock_stage_retries_until_the_shell_can_answer(tmp_path: Path) -> None:
    """omarchy-plugin-enable talks to the live shell; a TTY or SSH run has
    none to talk to. The failure must not abort the install, and the marker
    must stay unwritten so the next in-session run tries again."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    _stub(env["bins"] / "omarchy-plugin-enable", env["calls"], "exit 1")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (env["home"] / ".local" / "state" / "hyprconf" / "clock-applied").exists()
    assert not any(c.startswith("omarchy-bar") for c in _calls(env))


def test_workspaces_widget_is_the_overlays_own_plugin(tmp_path: Path) -> None:
    """The stock widget hardcodes pills 1-5, caps ids at 10 and reads no
    settings, so the overlay ships its own widget (plugins/hyprconf-workspaces)
    as a clonedFrom copy: the shell swaps it into the stock widget's slot and
    `omarchy plugin disable hyprconf.workspaces` restores stock. Synced on
    every run — a git pull updates it — and enabled once."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-plugin-enable hyprconf.workspaces" in _calls(env)

    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.workspaces"
    src = REPO_ROOT / "plugins" / "hyprconf-workspaces"
    for f in src.iterdir():
        assert (plug / f.name).read_bytes() == f.read_bytes(), f.name
    manifest = json.loads((plug / "manifest.json").read_text())
    assert manifest["id"] == "hyprconf.workspaces"
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.workspaces"
    assert manifest["entryPoints"]["barWidget"] == "Workspaces.qml"
    assert manifest["kinds"] == ["bar-widget"]

    # Synced, not seeded: a stale installed copy comes back to the repo's, and
    # the running shell is reloaded so it draws the new one.
    (plug / "Workspaces.qml").write_text("// stale\n")
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert (plug / "Workspaces.qml").read_bytes() == (src / "Workspaces.qml").read_bytes()
    assert any(c.startswith("omarchy-restart-shell") for c in _calls(env))
    # …but enabled once only, so a later `omarchy plugin disable` sticks.
    assert "omarchy-plugin-enable hyprconf.workspaces" not in _calls(env)


def test_workspaces_widget_shows_only_active_workspaces_on_two_lines() -> None:
    """What the widget promises, pinned statically: no fixed pill set and no
    id cap (only workspaces Hyprland has), two rows, hyprconf's Pac-Man on the
    focused workspace, and the stock IPC id kept as moduleName."""
    qml = _code_only_qml(
        (REPO_ROOT / "plugins" / "hyprconf-workspaces" / "Workspaces.qml").read_text()
    )
    assert "var ids = []" in qml
    assert "[1, 2, 3, 4, 5]" not in qml and "id <= 10" not in qml
    assert "\\u{F0BAF}" in qml  # nf-md-pac_man, hyprconf's focused marker
    assert "\\uDB85\\uDCFB" not in qml  # the stock dot
    assert re.search(r"columns:.*Math\.ceil\(root\.ids\.length / 2\)", qml)
    assert 'moduleName: "omarchy.workspaces"' in qml


def test_window_title_is_a_two_line_clone_enabled_once_after_the_workspaces(
    tmp_path: Path,
) -> None:
    """hyprconf's bar drew the focused window's title beside the workspaces.
    Omarchy's stock omarchy.active-window does that on one line; the overlay
    ships a clonedFrom copy that lays the same character budget out on two
    lines. Synced every run, enabled once, placed right after the workspaces
    widget; a later `omarchy plugin disable` survives the hook's re-runs."""
    env = _setup(tmp_path)
    # A machine from the version that enabled the stock widget under the old marker.
    old_marker = env["home"] / ".local" / "state" / "hyprconf" / "window-title-applied"
    old_marker.parent.mkdir(parents=True)
    old_marker.write_text("")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert (
        "omarchy-plugin-enable hyprconf.active-window --section left --after hyprconf.workspaces"
        in calls
    )
    assert not any("omarchy-plugin-enable omarchy.active-window" in c for c in calls)
    assert (env["home"] / ".local" / "state" / "hyprconf" / "active-window-applied").exists()
    assert not old_marker.exists()

    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.active-window"
    src = REPO_ROOT / "plugins" / "hyprconf-active-window"
    for f in src.iterdir():
        assert (plug / f.name).read_bytes() == f.read_bytes(), f.name
    manifest = json.loads((plug / "manifest.json").read_text())
    assert manifest["id"] == "hyprconf.active-window"
    assert manifest["omarchy"]["clonedFrom"] == "omarchy.active-window"
    assert manifest["entryPoints"]["barWidget"] == "ActiveWindow.qml"

    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(
        "active-window" in c for c in _calls(env) if c.startswith("omarchy-plugin-enable")
    )


def test_window_title_widget_lays_the_same_budget_out_on_two_lines() -> None:
    """Pinned statically: the stock maxWidth budget (body-size, one line) is
    rendered as two caption-size lines of half the width, word-wrapped and
    elided on the second line; stock behaviours (tooltip, click focus,
    middle-click close, hidden when nothing is focused / vertical bar) and
    the stock IPC id are kept."""
    qml = _code_only_qml(
        (REPO_ROOT / "plugins" / "hyprconf-active-window" / "ActiveWindow.qml").read_text()
    )
    assert 'moduleName: "omarchy.active-window"' in qml
    assert 'setting("maxWidth", 280)' in qml
    assert "Style.font.caption / Style.font.body / 2" in qml
    assert "maximumLineCount: 2" in qml and "wrapMode: Text.Wrap" in qml
    assert "elide: Text.ElideRight" in qml and "font.pixelSize: Style.font.caption" in qml
    assert "lineHeightMode: Text.ProportionalHeight" in qml
    assert 'visible: title !== "" && !vertical' in qml
    assert "root.toplevel.close()" in qml and "root.toplevel.activate()" in qml
    assert "showTooltip(root, root.title)" in qml


def test_window_title_falls_back_when_the_workspaces_copy_is_off_the_bar(tmp_path: Path) -> None:
    """omarchy-plugin-enable refuses a --after target the bar does not carry.
    A user who disabled hyprconf.workspaces is back on the stock widget, so
    the title lands after that instead; with neither, the left section."""
    env = _setup(tmp_path)
    _stub(
        env["bins"] / "omarchy-plugin-enable",
        env["calls"],
        'case " $* " in *" --after hyprconf.workspaces "*) exit 1 ;; esac; exit 0',
    )
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert (
        "omarchy-plugin-enable hyprconf.active-window --section left --after omarchy.workspaces"
        in calls
    )
    assert (env["home"] / ".local" / "state" / "hyprconf" / "active-window-applied").exists()

    env2 = _setup(tmp_path / "no-anchor")
    _stub(
        env2["bins"] / "omarchy-plugin-enable",
        env2["calls"],
        'case " $* " in *" --after "*) exit 1 ;; esac; exit 0',
    )
    assert _run(env2, "--no-update").returncode == 0
    assert "omarchy-plugin-enable hyprconf.active-window --section left" in _calls(env2)


def test_window_title_retries_until_the_shell_can_answer(tmp_path: Path) -> None:
    """No live shell (TTY/SSH): no marker, so the next in-session run tries again."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-plugin-enable", env["calls"], "exit 1")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not (env["home"] / ".local" / "state" / "hyprconf" / "active-window-applied").exists()
    assert "hyprconf.active-window" in proc.stderr


def test_resources_widget_layout_is_fixed_width_and_ordered() -> None:
    """Two aligned lines — CPU temp/util · RAM · upload over GPU temp/util ·
    VRAM · download — with every column sized by TextMetrics from its widest
    value, so nothing moves as the numbers change; the thermometer is the
    solid Material Design glyph (U+F050F), not the Weather-Icons outline
    (U+E350) that rendered as a hairline; the GPU cells read the structured
    fields the feeder emits (no pre-rendered "text")."""
    qml = _code_only_qml((REPO_ROOT / "plugins" / "hyprconf-resources" / "Widget.qml").read_text())
    assert "\\u{F050F}" in qml and "\\ue350" not in qml.lower()
    assert qml.count("TextMetrics {") == 3
    for col in ("loadCol", "memCol", "netCol"):
        assert qml.count(f"width: {col}.width") == 2, col  # one cell per line
    # Row-major order: the upload cell precedes every GPU cell, the download cell is last.
    up = qml.index('"↑ " + root.netUp')
    down = qml.index('"↓ " + root.netDown')
    gpu = qml.index('root.glyphGpu + " " + root.tempText')
    assert up < gpu < down
    for field in ("j.util", "j.temp", "j.vram_used", "j.vram_total", "j.tooltip"):
        assert field in qml, field
    assert "j.text" not in qml
    assert "columns: root.vertical ? 1 : 3" in qml


def test_bar_plugins_are_enabled_once_so_disable_sticks(tmp_path: Path) -> None:
    """The post-update hook re-runs the installer after every Omarchy update;
    an unconditional enable would undo `omarchy plugin disable <id>` each
    time. The first run enables, later runs leave the choice alone."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    calls = _calls(env)
    assert "omarchy-plugin-enable hyprconf.resources --section right" in calls
    assert "omarchy-plugin-enable hyprconf.workspaces" in calls
    assert any(c.startswith("omarchy-plugin-enable hyprconf.active-window") for c in calls)
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-plugin-enable") for c in _calls(env))


# ---------------------------------------------------------------------------
# Workspace placement on a preset switch
# ---------------------------------------------------------------------------


def test_switch_monitor_moves_existing_workspaces(tmp_path: Path) -> None:
    """Workspace rules only place FUTURE workspaces; a switch must move
    today's. On reload Hyprland leaves existing workspaces on whatever monitor
    they already occupy, so without an explicit move the kitchen hotkey
    enabled the right outputs while workspaces 1-6 stayed on the bedroom TV.
    The move uses the Lua dispatch form — hl.dsp.workspace.move, verified on
    Hyprland 0.56.2 — for the same reason the dpms recovery does (the
    two-token dispatch is a parse error there, per its own scan below)."""
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")

    env["calls"].write_text("")
    proc = subprocess.run(
        ["bash", str(hypr / "scripts" / "switch_monitor.sh"), "kitchen"],
        capture_output=True,
        text=True,
        env={"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"},
    )
    assert proc.returncode == 0, proc.stderr

    rules = re.findall(
        r'hl\.workspace_rule\(\{ workspace = "(\d+)", monitor = "([^"]+)" \}\)',
        (REPO_ROOT / "hypr" / "pcMonitors.kitchen.lua").read_text(),
    )
    assert rules, "kitchen preset carries no workspace rules"
    calls = _calls(env)
    for ws, mon in rules:
        expected = (
            f'hyprctl dispatch hl.dsp.workspace.move({{ workspace = {ws}, monitor = "{mon}" }})'
        )
        assert expected in calls, expected


def test_clock_copy_takes_the_center_anchor_with_it(tmp_path: Path) -> None:
    """canonicalWidgetId does no clone resolution (shell/Commons/Util.qml — a
    plain string cast), so a centerAnchor left at omarchy.clock matches
    nothing once the bar swaps to hyprconf.clock, and the clock drifts
    off-center. The stage follows the anchor — but only while it still
    points at the stock id, so a user's own anchor choice is never
    overridden."""
    env = _setup(tmp_path)
    _plugin_fixtures(env, tmp_path)
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    shell_json.parent.mkdir(parents=True, exist_ok=True)
    shell_json.write_text('{"bar": {"centerAnchor": "omarchy.clock"}}')
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "hyprconf.clock"

    # An anchor the user re-pointed later is left alone (marker aside, the
    # guard itself only matches the stock id).
    shell_json.write_text('{"bar": {"centerAnchor": "omarchy.weather"}}')
    _run(env, "--no-update")
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "omarchy.weather"


# ---------------------------------------------------------------------------
# The `omarchy refresh` guard
# ---------------------------------------------------------------------------


STOCK_BINDINGS = "-- Keep only your personal keybinding overrides here.\n"


def _stock_templates(env: dict) -> Path:
    """Omarchy's config/ templates — what omarchy-refresh-config copies from."""
    templates = env["omarchy_path"] / "config" / "hypr"
    templates.mkdir(parents=True, exist_ok=True)
    (templates / "bindings.lua").write_text(STOCK_BINDINGS)
    (templates / "monitors.lua").write_text('hl.monitor({ output = "", mode = "preferred" })\n')
    return templates


def _refresh_config(env: dict, templates: Path, name: str) -> None:
    """What omarchy-refresh-config does to ~/.config/hypr/<name>: cp -f from the
    template. cp -f follows a symlink, so with the overlay installed this
    writes THROUGH the link into the checkout. Reproduced with the real cp."""
    subprocess.run(
        ["cp", "-f", str(templates / name), str(env["home"] / ".config" / "hypr" / name)],
        check=True,
        timeout=30,
    )


def test_refresh_through_the_symlink_is_undone_from_git(tmp_path: Path) -> None:
    """`omarchy refresh hyprland` replaces every ~/.config/hypr/*.lua with the
    stock template via cp -f, which follows the overlay's symlinks straight
    into the checkout — hypr/bindings.lua became Omarchy's commented template
    and every hyprconf hotkey vanished (observed on Omarchy 4.0.0-1). A
    re-run must notice the checkout holds a byte-identical stock template and
    put the committed file back."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    templates = _stock_templates(env)
    committed = (repo / "hypr" / "bindings.lua").read_text()
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0

    _refresh_config(env, templates, "bindings.lua")
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS  # the damage

    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == committed
    assert "stock template" in proc.stderr and "restored" in proc.stderr
    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert live.is_symlink() and live.read_text() == committed


def test_a_real_edit_in_the_checkout_is_never_reverted(tmp_path: Path) -> None:
    """The guard keys on byte-identity with the stock template and nothing
    else: an edit made through the symlink is the user editing their own
    dotfiles, exactly what the links are for."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    _stock_templates(env)
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0

    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    edited = live.read_text() + '\no.bind("SUPER + SHIFT + R", "SSH", "kitty -e ssh box")\n'
    live.write_text(edited)  # through the symlink, like an editor would

    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == edited
    assert "stock template" not in proc.stderr


def test_guard_reports_when_git_cannot_repair(tmp_path: Path) -> None:
    """No git to restore from (a tarball, or the stub in every other test):
    the clobber is still reported, and the run still completes."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    templates = _stock_templates(env)
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0
    _refresh_config(env, templates, "bindings.lua")

    proc = _run(env, "--no-update", install_sh=repo / "install.sh")  # git is the no-op stub
    assert proc.returncode == 0, proc.stderr
    assert "could not be" in proc.stderr and "git" in proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS


def test_a_preset_reset_to_the_stock_template_is_reported_not_rewritten(tmp_path: Path) -> None:
    """monitors.lua points at the chosen preset after a hotkey switch, so
    `omarchy refresh config hypr/monitors.lua` lands on the preset. The
    installer must say so — naming Omarchy's own .bak.<epoch> backup — and
    must NOT re-seed on its own: a preset is machine-local, and re-enabling
    outputs that are not plugged in right now would black out the desk."""
    env = _setup(tmp_path)
    templates = _stock_templates(env)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    assert _run(env, "--no-update").returncode == 0
    switch = hypr / "scripts" / "switch_monitor.sh"
    child = {"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"}
    assert subprocess.run(["bash", str(switch), "bedroom"], env=child, timeout=30).returncode == 0
    assert hypr.joinpath("monitors.lua").is_symlink()

    _refresh_config(env, templates, "monitors.lua")  # lands on pcMonitors.bedroom.lua
    stock = (templates / "monitors.lua").read_text()
    assert hypr.joinpath("pcMonitors.bedroom.lua").read_text() == stock

    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "pcMonitors.bedroom.lua" in proc.stderr and "monitors.lua.bak" in proc.stderr
    assert hypr.joinpath("pcMonitors.bedroom.lua").read_text() == stock  # left for the user
