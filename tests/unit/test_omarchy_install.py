"""omarchy/install.sh — the overlay installer for Omarchy systems.

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
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OMARCHY_DIR = REPO_ROOT / "omarchy"
INSTALL_SH = OMARCHY_DIR / "install.sh"
HOOK = OMARCHY_DIR / "hooks" / "post-update.d" / "10-hyprconf"

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
        "omarchy-update",
        "hyprctl",
        "kitty",
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
    env: dict, *args: str, zsh: str | None = None, zsh_bin: str | None = None
) -> subprocess.CompletedProcess:
    """Run install.sh against the fake tree. Returns the completed process.

    `zsh` pins the resolved zsh path outright; `zsh_bin` instead renames the
    binary the installer looks up on PATH, which is how a test can model "zsh
    does not exist until the package stage installs it" on a host whose own
    /usr/bin/zsh would otherwise always be found.
    """
    child_env = {
        "HOME": str(env["home"]),
        "PATH": f"{env['bins']}:/usr/bin:/bin",
        "OMARCHY_PATH": str(env["omarchy_path"]),
        "_HYPRCONF_PKG_ADD": env["pkg_add"],
    }
    if zsh is not None:
        child_env["_HYPRCONF_ZSH"] = zsh
    if zsh_bin is not None:
        child_env["_HYPRCONF_ZSH_BIN"] = zsh_bin
    return subprocess.run(
        ["bash", str(INSTALL_SH), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=child_env,
    )


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
    """omarchy-default-terminal exec()s a GUI window when kitty is missing."""
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
        assert hypr.joinpath(name).resolve() == OMARCHY_DIR / "hypr" / name
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
    for lua in sorted((OMARCHY_DIR / "hypr").glob("*.lua")):
        proc = subprocess.run(
            [luac, "-p", str(lua)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr


def test_theme_is_installed_as_a_symlink(tmp_path: Path) -> None:
    """omarchy-theme-set only takes its permissive path for a symlinked theme.

    Its check is `[[ ! -L $source && -d $source/.git ]]` — a real directory
    inside a git checkout would be treated as a stranger's theme and filtered
    through INSTALLED_THEME_DENIED instead when the user picks it from the menu.
    """
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
    for script in sorted((OMARCHY_DIR / "hypr" / "scripts").iterdir()):
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
    src = (OMARCHY_DIR / "hypr" / "scripts" / "adjust-gaps").read_text()
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
        for line in (OMARCHY_DIR / "hypr" / "bindings.lua").read_text().splitlines()
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
    src = (OMARCHY_DIR / "hypr" / "bindings.lua").read_text()
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
    for script in sorted((OMARCHY_DIR / "hypr" / "scripts").iterdir()):
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
        for ln in (OMARCHY_DIR / "hypr" / "bindings.lua").read_text().splitlines()
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
    assert seeded.read_bytes() == (OMARCHY_DIR / "wallpapers" / "gruvbox.jpg").read_bytes()


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
    qml = (OMARCHY_DIR / "plugins" / "hyprconf-resources" / "Widget.qml").read_text()
    offenders = [
        line.strip()
        for line in _code_only(qml).splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]
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
        ["git", "ls-files", "omarchy"],
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


def test_overlay_never_reaches_into_the_standalone_installer() -> None:
    """setup.sh's remove_aur_packages would offer to uninstall Omarchy itself."""
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
