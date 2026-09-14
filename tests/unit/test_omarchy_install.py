"""install.sh — the overlay installer for Omarchy systems.

Mostly *restraint* (AGENTS.md › Hard rules, 6): what the installer must NOT
do to a machine Omarchy owns. Hermetic — fake `omarchy-*` binaries in a
throwaway HOME, so it runs in a bare archlinux container (AGENTS.md › Tests).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
HOOK = REPO_ROOT / "hooks" / "post-update.d" / "10-hyprconf"

# Where hyprconf-monitor-preset puts the chosen preset: Omarchy's Hyprland
# toggles directory, loaded after ~/.config/hypr/monitors.lua.
TOGGLE = Path(".local") / "state" / "omarchy" / "toggles" / "hypr" / "hyprconf-monitor-preset.lua"

# A recording stub: appends its own name + args to the calls log, then runs an
# optional body. One template covers every external the installer touches.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "${{0##*/}} $*" >> "{calls}"
{body}
"""

# ~/.config/kitty/kitty.conf on an UPGRADED Omarchy 4.0.3-1 box, which is the
# one a hyprconf box is in: 4.0.3 moved the defaults to /etc/xdg, but its
# migration 1788745941.sh only refreshes a user file whose sha still matches
# the old stock one — and a hyprconf box's carries `include hyprconf.conf`.
# These are the lines the overlay must leave intact.
OMARCHY_KITTY_CONF = """include ~/.local/state/omarchy/current/theme/kitty.conf
# allow_remote_control yes
listen_on unix:${XDG_RUNTIME_DIR}/omarchy-kitty-{kitty_pid}
font_family JetBrainsMono Nerd Font
font_size 10
"""


# Omarchy's default/firefox/policies.json as omarchy-install-browser copies
# it (4.0.0-1: Preferences only) — its five prefs verbatim, plus one synthetic
# pref hyprconf's policy also sets, so the merge test can show Omarchy's
# prefs surviving and ours winning on a shared key.
SHARED_PREF = "browser.compactmode.show"
OMARCHY_FIREFOX_POLICY = {
    "policies": {
        "Preferences": {
            "apz.overscroll.enabled": {"Value": True, "Status": "default"},
            "media.ffmpeg.vaapi.enabled": {"Value": True, "Status": "default"},
            "media.hardware-video-decoding.force-enabled": {"Value": True, "Status": "default"},
            "widget.disable-swipe-tracker": {"Value": False, "Status": "default"},
            "widget.wayland.fractional-scale.enabled": {"Value": True, "Status": "default"},
            SHARED_PREF: {"Value": False, "Status": "default"},
        }
    }
}
# What omarchy-install-browser copies to /usr/lib/firefox/distribution/.
OMARCHY_POLICY = Path("/usr/share/omarchy/default/firefox/policies.json")

# omarchy-hook-install <type> <file> (4.0.0-1): mkdir -p the .d dir, cp under
# the file's basename, chmod 755 — reproduced so later stages find the hook.
HOOK_INSTALL = (
    'd="$HOME/.config/omarchy/hooks/$1.d"; mkdir -p "$d"; cp "$2" "$d/${2##*/}"; '
    'chmod 755 "$d/${2##*/}"'
)

# omarchy-theme-refresh re-sets the current theme, which renders every user
# template (~/.config/omarchy/themed/*.tpl) into the current theme dir from
# its colors.toml (omarchy-theme-set-templates); the fake does that part.
THEME_REFRESH = """\
t="$HOME/.local/state/omarchy/current/theme"; [ -f "$t/colors.toml" ] || exit 0
s=""
while IFS= read -r l; do k="${l%% *}"; v="${l#*\\"}"; v="${v%\\"*}"; s="$s;s|{{ $k }}|$v|g"; done \\
  < <(grep -E '^[a-z_]+ = "' "$t/colors.toml")
for f in "$HOME"/.config/omarchy/themed/*.tpl; do
  [ -f "$f" ] || continue; n="${f##*/}"; sed "${s#;}" "$f" > "$t/${n%.tpl}"
done"""

# Every monitor preset the overlay ships, by the name hyprconf-monitor-preset
# answers to. Each carries the workspace-to-monitor rules for its layout, so
# they travel as whole files; stage_monitors seeds them all.
PRESETS = (
    ("bedroom", "pcMonitors.bedroom.lua"),
    ("kitchen", "pcMonitors.kitchen.lua"),
    ("laptop", "laptopMonitors.lua"),
)


def _stub(path: Path, calls: Path, body: str = "exit 0") -> None:
    path.write_text(STUB.format(calls=calls, body=body))
    path.chmod(0o755)


def _terminal_stub(tmp_path: Path, set_status: int = 0) -> str:
    """omarchy-default-terminal: reports foot until something sets it, then
    what was set. The set form writes first and exits `set_status` — the real
    one's status is its closing notification's (no set -e, 4.0.0-1)."""
    return (
        f'if [ $# -eq 0 ]; then cat "{tmp_path}/term" 2>/dev/null || echo foot;'
        f' else printf "%s" "$1" > "{tmp_path}/term"; exit {set_status}; fi'
    )


# /usr/bin/omarchy-shell-config (Omarchy 4.0.3-1), transcribed: the hidden
# helper modules/idle SOURCES to edit ~/.config/omarchy/shell.json — which a
# full install.sh run reaches, and stage_clock then reads. Written out instead
# of stubbed for two reasons — the recording stub's closing `exit 0` would end
# the module's subshell before commit() ever ran, and $0 inside a sourced file
# names the caller, not this file, so the recording line has to name itself.
# Only the three functions that path reaches are here; NORMALIZE (the helper's
# other half, for bar writers) is not.
SHELL_CONFIG_FAKE = """#!/usr/bin/env bash
printf '%s\\n' "omarchy-shell-config (sourced)" >> "__CALLS__"
CONFIG_FILE="$HOME/.config/omarchy/shell.json"
DEFAULTS_FILE="$OMARCHY_PATH/config/omarchy/shell.json"

fail() {
  echo "omarchy-shell-config: $*" >&2
  exit 1
}

refresh_shell_config() {
  if ! omarchy-shell shell reloadConfig >/dev/null 2>&1; then
    omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
  fi
}

source_file() {
  if [[ -s $CONFIG_FILE ]]; then
    printf '%s\\n' "$CONFIG_FILE"
  else
    printf '%s\\n' "$DEFAULTS_FILE"
  fi
}

_SHELL_CONFIG_TMP=""
cleanup_shell_config_tmp() {
  if [[ -n $_SHELL_CONFIG_TMP ]]; then rm -f "$_SHELL_CONFIG_TMP"; fi
}
trap cleanup_shell_config_tmp EXIT

commit() {
  local program="$1"
  shift
  mkdir -p "$(dirname "$CONFIG_FILE")"
  _SHELL_CONFIG_TMP=$(mktemp)
  jq -S -e "$@" "$program" "$(source_file)" >"$_SHELL_CONFIG_TMP" || fail "could not update shell config"
  mv "$_SHELL_CONFIG_TMP" "$CONFIG_FILE"
  _SHELL_CONFIG_TMP=""
  refresh_shell_config
}
"""


def _default_app_stub(
    tmp_path: Path, key: str, unset: str, *, writes: bool = True, set_status: int = 0
) -> str:
    """omarchy-default-browser / -editor: reports `unset` until something sets it,
    then what was set — the read-back stage_defaults decides on. The set form
    writes FIRST and exits `set_status` (no set -e, 4.0.3-1: the real ones
    notify last and inherit that status); `writes=False` is a setter that
    recorded the call and changed nothing."""
    write = f'printf "%s" "$1" > "{tmp_path}/{key}"; ' if writes else ""
    return (
        f'if [ $# -eq 0 ]; then cat "{tmp_path}/{key}" 2>/dev/null || echo {unset};'
        f" else {write}exit {set_status}; fi"
    )


# The externals _setup fakes with the bare recording stub. The conditional
# and bodied ones are written individually in _setup below;
# test_every_omarchy_command_install_sh_calls_has_a_fake holds install.sh to
# the union, which it reads off the fake directory rather than this list.
OMARCHY_STUBS = (
    "omarchy-theme-set",
    "omarchy-cmd-present",
    "omarchy-font-set",
    "omarchy-shell",
    "omarchy-plugin-enable",
    "omarchy-restart-shell",
    "omarchy-bar",
    "omarchy-update",
    # Firefox and VS Code go in through Omarchy's own installers.
    "omarchy-install-browser",
    "omarchy-install-editor-vscode",
    "sudo",
    "hyprctl",
    # hyprconf-monitor-preset (run by several tests here) reports through these;
    # the real ones would put a notification and an OSD on the developer's
    # desktop every time the suite runs. Its `stock` hands over to
    # omarchy-hyprland-toggle, which would reload the developer's Hyprland.
    "omarchy-notification-send",
    "omarchy-osd",
    "omarchy-hyprland-toggle",
    # Asserted never to run: pacman directly (the container has a real
    # one; a call must be seen, not reach it).
    "pacman",
    # modules/keychron reloads and retriggers udev; the real one would
    # re-apply rules on the developer's own machine.
    "udevadm",
)


def _setup(tmp_path: Path, *, with_zsh: bool = True) -> dict:
    """Build a throwaway HOME + fake-bins tree resembling a fresh Omarchy box."""
    home = tmp_path / "home"
    bins = tmp_path / "bins"
    omarchy_path = tmp_path / "omarchy"
    calls = tmp_path / "calls"
    for d in (home, bins, omarchy_path):
        d.mkdir(parents=True, exist_ok=True)
    calls.write_text("")

    for name in OMARCHY_STUBS:
        _stub(bins / name, calls)
    _stub(bins / "omarchy-pkg-add", calls)
    if with_zsh:
        _stub(bins / "zsh", calls)
    # omarchy-plugin-list answers empty and jq is "broken" (exit 1) until a
    # test puts the real one in (_real_jq): the discovery wait finds nothing
    # and the enable is still attempted.
    _stub(bins / "omarchy-plugin-list", calls, 'echo "[]"')
    _stub(bins / "jq", calls, "exit 1")
    # Omarchy's package probe (pacman -Q per name): everything present unless
    # a test says otherwise, so the steady-state box is the default and each
    # install flow is opted into.
    _stub(bins / "omarchy-pkg-present", calls)
    _stub(bins / "omarchy-hook-install", calls, HOOK_INSTALL)
    # Sourced, not run (see SHELL_CONFIG_FAKE) — hence the direct write.
    shell_config = bins / "omarchy-shell-config"
    shell_config.write_text(SHELL_CONFIG_FAKE.replace("__CALLS__", str(calls)))
    shell_config.chmod(0o755)
    _stub(bins / "omarchy-theme-refresh", calls, THEME_REFRESH)
    _stub(bins / "omarchy-default-terminal", calls, _terminal_stub(tmp_path))
    # Read back by stage_defaults; the unset answers are Omarchy's own (editor
    # falls back to "nvim", bin/omarchy-default-editor:14, and the browser
    # reports whatever xdg-settings says — stock Omarchy's chromium).
    _stub(
        bins / "omarchy-default-browser", calls, _default_app_stub(tmp_path, "browser", "chromium")
    )
    _stub(bins / "omarchy-default-editor", calls, _default_app_stub(tmp_path, "editor", "nvim"))
    # `clone` must materialise a directory; everything else is a no-op.
    _stub(bins / "git", calls, 'if [ "$1" = clone ]; then mkdir -p "${@: -1}"; fi; exit 0')

    # Seed the parts of a fresh Omarchy $HOME the installer interacts with.
    (home / ".config" / "kitty").mkdir(parents=True)
    (home / ".config" / "kitty" / "kitty.conf").write_text(OMARCHY_KITTY_CONF)
    (home / ".config" / "hypr").mkdir(parents=True)
    for stock in ("bindings.lua", "input.lua", "looknfeel.lua"):
        (home / ".config" / "hypr" / stock).write_text(f"-- stock omarchy {stock}\n")
    # Omarchy's shipped shell.json defaults — what omarchy-shell-config's
    # source_file() starts from when the user has no shell.json yet.
    (omarchy_path / "config" / "omarchy").mkdir(parents=True)
    (omarchy_path / "config" / "omarchy" / "shell.json").write_text(
        json.dumps({"version": 1, "idle": {"lock": 300, "screensaver": 150}})
    )
    # Omarchy's Firefox prefs — what stage_firefox merges under hyprconf's.
    (omarchy_path / "default" / "firefox").mkdir(parents=True)
    (omarchy_path / "default" / "firefox" / "policies.json").write_text(
        json.dumps(OMARCHY_FIREFOX_POLICY, indent=2) + "\n"
    )

    env = {
        "home": home,
        "bins": bins,
        "omarchy_path": omarchy_path,
        "calls": calls,
        "udev_rules": tmp_path / "etc" / "udev" / "rules.d",
    }
    return env


def _install_env(env: dict, *, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """The environment install.sh runs in against the fake tree: _child_env
    plus every seam pinned at a fake. What _run passes — and what the
    installed post-update hook, which execs install.sh, is run under."""
    child_env = {
        **_child_env(env),
        "OMARCHY_PATH": str(env["omarchy_path"]),
        # The plugin-discovery and shell.json waits poll stubs that never
        # answer (a test modelling the shell's writes raises it again).
        "_HYPRCONF_PLUGIN_WAIT": "0",
        # modules/keychron's own seam, pinned on every run because main()
        # calls that module: a test that makes sudo real (_policy_env) would
        # otherwise install the rule into the CI container's /etc/udev/rules.d.
        "_HYPRCONF_UDEV_RULES": str(env["udev_rules"]),
    }
    if extra_env:
        child_env.update(extra_env)
    return child_env


def _run(
    env: dict,
    *args: str,
    extra_env: dict[str, str] | None = None,
    install_sh: Path = INSTALL_SH,
) -> subprocess.CompletedProcess:
    """Run install.sh against the fake tree (_install_env). Returns the
    completed process. `install_sh` runs a copy of the installer (see
    _checkout) instead of the one in this checkout."""
    return subprocess.run(
        ["bash", str(install_sh), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env=_install_env(env, extra_env=extra_env),
    )


# The payload install.sh reads at run time — enough of the repo to run every
# stage from a copy, lib/ included: the theme-set hook's PYTHONPATH points
# into the checkout that installed it.
PAYLOAD = (
    "install.sh",
    "packages",
    "modules",
    "hypr",
    "bin",
    "hooks",
    "lib",
    "zsh",
    "kitty",
    "plugins",
    "infra",
    "themed",
)

# What a hermetic run must never do is touch the network for Oh My Zsh or
# powerlevel10k, so the pin dance against those two dirs (fetch <sha> /
# checkout FETCH_HEAD / rev-parse HEAD) is faked through marker files:
# clone_pinned sees a repo that lands at — and stays at — whatever sha it
# fetched. `.fail-fetch` in a dir models a pin the box cannot reach.
GIT_PIN_PROTOCOL = """\
if [ "$1" = -C ]; then case "$2" in *oh-my-zsh*|*powerlevel10k*)
  dir=$2; shift 2
  case "$1" in
    fetch)     if [ -e "$dir/.fail-fetch" ]; then exit 1; fi
               printf %s "$4" > "$dir/.fake-fetch-head"; exit 0 ;;
    checkout)  cat "$dir/.fake-fetch-head" > "$dir/.fake-head" 2>/dev/null; exit 0 ;;
    rev-parse) cat "$dir/.fake-head" 2>/dev/null || echo unborn; exit 0 ;;
    *)         exit 0 ;;
  esac ;;
esac; fi
"""

# Real git for everything the refresh guard needs (`checkout --`) and for a
# clone of a LOCAL directory (the throwaway checkout under tmp_path, which is
# how the curl path is exercised); a clone of a URL only makes the directory,
# and a pull is a no-op.
GIT_PASSTHROUGH = (
    """\
if [ "$1" = clone ]; then
  src="${@: -2:1}"
  if [ -d "$src" ]; then exec "$(PATH=/usr/bin:/bin command -v git)" "$@"; fi
  mkdir -p "${@: -1}"; exit 0
fi
"""
    + GIT_PIN_PROTOCOL
    + """\
case " $* " in *" pull "*) exit 0 ;; esac
exec "$(PATH=/usr/bin:/bin command -v git)" "$@"
"""
)

# The pin dance with no real git behind it at all — its consumer runs
# install.sh from the real checkout, where a passthrough stub would run git
# against the developer's own working tree.
GIT_PIN_DANCE = (
    'if [ "$1" = clone ]; then mkdir -p "${@: -1}"; fi\n' + GIT_PIN_PROTOCOL + "exit 0\n"
)


def _checkout(tmp_path: Path) -> Path:
    """A throwaway git checkout of the overlay payload — the refresh-guard tests
    rehearse `omarchy refresh` clobbering a checkout and git repairing it,
    which must never happen to the repository the suite runs from."""
    repo = tmp_path / "checkout"
    repo.mkdir()
    for name in PAYLOAD:
        src = REPO_ROOT / name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, repo / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(src, repo / name)
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "payload"]):
        subprocess.run(["git", *args], cwd=repo, check=True, timeout=30)
    return repo


# "zsh is on this box, here": install.sh keys on ${_HYPRCONF_ZSH+set}, so a
# set-but-empty value is "no zsh" and the PATH lookup is skipped either way.
ZSH_AT = {"_HYPRCONF_ZSH": "/usr/bin/zsh"}


def _child_env(env: dict) -> dict[str, str]:
    """The pinned environment of everything run against the fake tree: the
    fakes first, then only /usr/bin and /bin (never the host's PATH)."""
    return {"HOME": str(env["home"]), "PATH": f"{env['bins']}:/usr/bin:/bin"}


def _real_jq(env: dict) -> None:
    """The real jq behind the recording stub — the default stub plays
    "broken" — for the stages that read or rewrite JSON; skips without one."""
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq available")
    _stub(env["bins"] / "jq", env["calls"], f'exec {jq} "$@"')


def _switch(env: dict, *args: str) -> subprocess.CompletedProcess:
    """hyprconf-monitor-preset as stage_bin installed it, against the fakes."""
    tool = env["home"] / ".local" / "bin" / "hyprconf-monitor-preset"
    return subprocess.run(
        ["bash", str(tool), *args],
        capture_output=True,
        text=True,
        env=_child_env(env),
        timeout=30,
    )


def _calls(env: dict) -> list[str]:
    return env["calls"].read_text().splitlines()


def _commands(env: dict) -> list[str]:
    """Just the command names invoked. Match on these, never on a whole call line:
    pytest names tmp dirs after the test, so a path baked into an argument can
    contain almost any word."""
    return [c.split()[0] for c in _calls(env) if c.strip()]


def _code_only(body: str) -> str:
    """Drop comments so a static scan can't match a comment explaining the rule.
    Naive on `#` inside strings, which none of the scans below look for."""
    out = []
    for line in body.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        out.append(line.split(" #", 1)[0])
    return "\n".join(out)


def _stage_body(name: str) -> str:
    """One install.sh stage function's code, comments stripped — so a claim
    about what a stage *does* cannot be satisfied by the comment above it."""
    src = INSTALL_SH.read_text()
    start = src.index(f"\n{name}() {{\n")
    end = src.index("\n}\n", start)
    return _code_only(src[start:end])


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
# Preflight — the guard that keeps this off a non-Omarchy machine
# ---------------------------------------------------------------------------


def test_the_omarchy_firefox_policy_fixture_names_no_pref_omarchy_dropped() -> None:
    """OMARCHY_FIREFOX_POLICY stands in for Omarchy's own file where there is
    no Omarchy (CI); with one installed it must name no pref Omarchy stopped
    shipping. SHARED_PREF is synthetic and is not one of Omarchy's."""
    if not OMARCHY_POLICY.is_file():
        return
    theirs = json.loads(OMARCHY_POLICY.read_text())["policies"]["Preferences"]
    ours = set(OMARCHY_FIREFOX_POLICY["policies"]["Preferences"]) - {SHARED_PREF}
    assert ours <= set(theirs), ours - set(theirs)


def test_refuses_without_omarchy_command(tmp_path: Path) -> None:
    # A name that really is absent: /usr/bin/omarchy-pkg-add exists on the
    # machines this overlay is developed on, so not stubbing it proves nothing.
    env = _setup(tmp_path)
    proc = _run(env, extra_env={"_HYPRCONF_PKG_ADD": "omarchy-pkg-add-absent"})
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


# What the second run of a settled box may still invoke: probes and writes
# that are idempotent by construction. This is the set-once/no-sudo gate for
# EVERY stage at once — a stage that re-asserted a user choice (the font, the
# default apps, an enable, the clock format, the idle timeout) or reached for
# sudo on a re-run shows up here as a name outside the set, which is why the
# per-stage tests below do not each pay a second install.sh run for it.
SETTLED_RERUN_COMMANDS = {
    "git",  # the two third-party dirs: rev-parse, already at their pins
    "hyprctl",
    "jq",
    "omarchy-cmd-present",  # is kitty installed
    "omarchy-default-terminal",  # read back: what is the default now
    "omarchy-hook-install",  # Omarchy's own idempotent mkdir/cp/chmod
    "omarchy-pkg-add",  # the package list, a no-op once installed
    "omarchy-pkg-present",  # is firefox / VS Code installed
}


def test_full_run_succeeds_and_is_byte_stable(tmp_path: Path) -> None:
    """Every stage on its real path, with the whole HOME in the hash: the real jq
    behind the JSON stages, a sudo that runs its command and a terminal to ask
    on, and ~/.local/bin on PATH the way default/bash/envs:32-33 (4.0.3-1)
    puts it there. The second run is byte-identical, warning-free, and calls
    nothing outside SETTLED_RERUN_COMMANDS."""
    env = _setup(tmp_path)
    _real_jq(env)
    _, extra = _policy_env(tmp_path, env)
    extra["PATH"] = f"{env['bins']}:{env['home']}/.local/bin:/usr/bin:/bin"
    first = _run(env, "--no-update", extra_env=extra)
    assert first.returncode == 0, first.stderr

    after_first = _tree_hash(env["home"])
    env["calls"].write_text("")
    second = _run(env, "--no-update", extra_env=extra)
    assert second.returncode == 0, second.stderr

    assert _tree_hash(env["home"]) == after_first
    assert "WARNING:" not in second.stderr, second.stderr
    assert set(_commands(env)) <= SETTLED_RERUN_COMMANDS, set(_commands(env))


def _zshrc_block(checkout: Path = REPO_ROOT) -> list[str]:
    """zsh/zshrc.block as stage_shell writes it: the @HYPRCONF_DIR@ of the
    hyprsync alias rendered to the checkout that installed it, the same `sed`
    pass stage_bin and stage_hooks run on their own payloads."""
    text = (REPO_ROOT / "zsh" / "zshrc.block").read_text()
    return text.replace("@HYPRCONF_DIR@", str(checkout)).splitlines()


def test_zshrc_preserves_content_outside_the_block_in_place(tmp_path: Path) -> None:
    """Everything outside the markers survives WHERE IT WAS, and a stale block is
    replaced at its own position. The strip-then-append this replaces moved a
    trailing line above the block, silently changing zsh's evaluation order —
    the block sources zsh-syntax-highlighting last for a reason."""
    env = _setup(tmp_path)
    zshrc = env["home"] / ".zshrc"
    zshrc.write_text("export MY_OWN_THING=1\n")
    _run(env, "--no-update")
    text = zshrc.read_text()
    assert text.startswith("export MY_OWN_THING=1\n\n# >>> hyprconf >>>\n")
    assert text.endswith("# <<< hyprconf <<<\n")

    zshrc.write_text(text + "source ~/.zshrc.local\n")
    _run(env, "--no-update")
    lines = zshrc.read_text().splitlines()
    assert lines[0] == "export MY_OWN_THING=1"
    assert lines.count("# >>> hyprconf >>>") == 1 and lines.count("# <<< hyprconf <<<") == 1
    assert lines[-1] == "source ~/.zshrc.local"
    assert lines.index("source ~/.zshrc.local") > lines.index("# <<< hyprconf <<<")

    block = _zshrc_block()
    stale = zshrc.read_text().replace("alias hyprsync=", "alias hyprsync_old=")
    assert stale != zshrc.read_text()
    zshrc.write_text(stale)
    _run(env, "--no-update")
    lines = zshrc.read_text().splitlines()
    begin, end = lines.index("# >>> hyprconf >>>"), lines.index("# <<< hyprconf <<<")
    assert lines[begin : end + 1] == block
    assert lines[:begin] == ["export MY_OWN_THING=1", ""]
    assert lines[end + 1 :] == ["source ~/.zshrc.local"]


def test_a_backslash_in_the_checkout_path_keeps_the_zshrc_block(tmp_path: Path) -> None:
    """HYPRCONF_DIR is the user's to choose, and `awk -v blk=...` runs the value
    through POSIX escape processing — so a checkout path carrying a backslash
    made `getline < blk` open nothing, and run 2 ate both marker lines and the
    block at exit 0. Same class as HERE_SED."""
    env = _setup(tmp_path)
    odd = tmp_path / "my\\stuff"
    _checkout(tmp_path).rename(odd)
    assert "\\" in str(odd)
    block = _zshrc_block(odd)
    zshrc = env["home"] / ".zshrc"

    for run in range(1, 3):
        proc = _run(env, "--no-update", install_sh=odd / "install.sh")
        assert proc.returncode == 0, proc.stderr
        lines = zshrc.read_text().splitlines()
        assert lines.count("# >>> hyprconf >>>") == 1, f"run {run}: {proc.stderr}"
        begin, end = lines.index("# >>> hyprconf >>>"), lines.index("# <<< hyprconf <<<")
        assert lines[begin : end + 1] == block, f"run {run}"


def _unpaired_markers(text: str, begin: str, end: str) -> dict[str, str]:
    """The three ways a marker pair stops bounding a block: either line gone,
    or the two of them in the wrong order. All three leave the rewrite's
    skip=1 latch with nothing to clear it."""
    lines = text.splitlines(keepends=True)
    b = next(i for i, ln in enumerate(lines) if ln.rstrip() == begin)
    e = next(i for i, ln in enumerate(lines) if ln.rstrip() == end)
    swapped = list(lines)
    swapped[b], swapped[e] = swapped[e], swapped[b]
    return {
        "no end marker": "".join(ln for ln in lines if ln.rstrip() != end),
        "no begin marker": "".join(ln for ln in lines if ln.rstrip() != begin),
        "markers swapped": "".join(swapped),
    }


def test_marker_lines_that_are_not_an_ordered_pair_leave_zshrc_alone(tmp_path: Path) -> None:
    """One marker line gone — or an end marker ABOVE the begin marker, which the
    warning's own advice can produce — leaves the rewrite's skip=1 latch with
    nothing to clear it, and used to cost everything from the marker to EOF at
    exit 0. None of the three is a file the installer understands."""
    env = _setup(tmp_path)
    zshrc = env["home"] / ".zshrc"
    zshrc.write_text("export MY_OWN_THING=1\n")
    assert _run(env, "--no-update").returncode == 0
    full = zshrc.read_text() + "source ~/.zshrc.local\nexport SECOND_OWN_THING=2\n"

    for shape, maimed in _unpaired_markers(
        full, "# >>> hyprconf >>>", "# <<< hyprconf <<<"
    ).items():
        assert maimed != full
        zshrc.write_text(maimed)
        proc = _run(env, "--no-update")
        assert proc.returncode == 0, proc.stderr
        assert zshrc.read_text() == maimed, shape
        assert "marker" in proc.stderr and ".zshrc" in proc.stderr, shape

    # The pair back: the block is rewritten in place and the tail survives.
    zshrc.write_text(full)
    assert _run(env, "--no-update").returncode == 0
    assert zshrc.read_text() == full


def test_a_failed_shell_clone_warns_and_the_stages_after_it_still_run(tmp_path: Path) -> None:
    """A dead network must not abort the apply — or the post-update hook's run.
    The clones run under `set -e`; unguarded, a DNS failure killed the whole
    run before stage_hooks, so a first install on a flaky network never got
    the post-update hook."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "git", env["calls"], 'if [ "$1" = clone ]; then exit 1; fi; exit 0')
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "could not clone Oh My Zsh" in proc.stderr
    assert not (env["home"] / ".oh-my-zsh").is_dir()
    assert not (env["home"] / ".zshrc").exists()
    assert "omarchy-hook-install" in _commands(env)


# ---------------------------------------------------------------------------
# Restraint — what the installer must never do
# ---------------------------------------------------------------------------


def test_default_terminal_is_never_set_to_an_absent_kitty(tmp_path: Path) -> None:
    """omarchy-default-terminal (4.0.3-1) checks nothing — it writes the desktop
    id and notifies — so pointing it at an absent kitty would leave
    SUPER+RETURN with no terminal. It warns and skips rather than dying: this
    is the first stage after the package gate, re-run on every update."""
    env = _setup(tmp_path)
    # kitty alone absent: a later omarchy-cmd-present for another command
    # still answers, and /usr/bin stays on PATH for coreutils.
    _stub(
        env["bins"] / "omarchy-cmd-present",
        env["calls"],
        'case "$1" in kitty) exit 1 ;; esac; exit 0',
    )
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "kitty" in proc.stderr
    assert not any(c.startswith("omarchy-default-terminal ") for c in _calls(env)), (
        "omarchy-default-terminal was called with an argument"
    )
    # And the run went on: a stage well after the terminal one still landed.
    assert (env["home"] / ".zshrc").exists()


def test_a_failed_terminal_setter_does_not_take_the_install_down(tmp_path: Path) -> None:
    """omarchy-default-terminal has no set -e and exits with its closing
    omarchy-notification-send's status (4.0.3-1), which fails on a TTY first
    run — after the list file is written. Every later stage must still run."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-default-terminal", env["calls"], _terminal_stub(tmp_path, 1))
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-default-terminal kitty" in _calls(env)
    assert (env["home"] / ".zshrc").exists()  # a stage well after the terminal one
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert "omarchy-default-terminal kitty" not in _calls(env)


def test_kitty_conf_gains_only_the_include(tmp_path: Path) -> None:
    """Every original line survives, in order, and the only thing added is one
    include — Omarchy's file stays authoritative."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    conf = (env["home"] / ".config" / "kitty" / "kitty.conf").read_text()
    assert conf == OMARCHY_KITTY_CONF + "\n# hyprconf overlay\ninclude hyprconf.conf\n"


def test_hyprconf_kitty_include_file_is_self_contained(tmp_path: Path) -> None:
    """It must not restate anything Omarchy sets, in either of its two homes: on
    4.0.3-1 `listen_on` and `allow_remote_control socket-only` live in
    /etc/xdg/kitty/kitty.conf and `font_family` is appended to the user file
    by omarchy-font-set. The include goes LAST, so a restatement would win."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    body = _code_only((env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    for owned in ("font_family", "font_size", "listen_on", "allow_remote_control", "include "):
        assert owned not in body, owned


def test_the_shell_line_is_written_once_however_often_the_stage_runs(tmp_path: Path) -> None:
    """hyprconf.conf is re-installed from the checkout on every run (`install -m
    644`, which also puts the mode back), so the appended `shell` line is the
    only thing the stage adds — one copy, never a growing stack."""
    env = _setup(tmp_path)
    for _ in range(3):
        assert _run(env, "--no-update", extra_env=ZSH_AT).returncode == 0
    conf = env["home"] / ".config" / "kitty" / "hyprconf.conf"
    body = conf.read_text()
    assert body.count("shell /usr/bin/zsh") == 1
    assert "shell " not in _code_only((REPO_ROOT / "kitty" / "hyprconf.conf").read_text())
    # Only the shell line, and never a second copy of what the header says.
    added = body[len((REPO_ROOT / "kitty" / "hyprconf.conf").read_text()) :]
    assert added == "\nshell /usr/bin/zsh\n", added
    assert conf.stat().st_mode & 0o777 == 0o644


def test_the_include_is_written_even_with_no_user_kitty_conf(tmp_path: Path) -> None:
    """From Omarchy 4.0.3 ~/.config/kitty/kitty.conf is optional (the defaults
    moved to /etc/xdg/kitty/kitty.conf, merged BELOW any user file —
    /usr/lib/kitty/kitty/cli.py:712), and a box without one ended up with
    hyprconf.conf installed and nothing including it."""
    env = _setup(tmp_path)
    conf = env["home"] / ".config" / "kitty" / "kitty.conf"
    conf.unlink()
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert conf.read_text() == "\n# hyprconf overlay\ninclude hyprconf.conf\n"
    assert "nothing includes it" not in proc.stderr
    # And a second run does not append it twice.
    _run(env, "--no-update")
    assert conf.read_text().count("include hyprconf.conf") == 1


def test_shell_line_points_at_zsh_only_when_zsh_exists(tmp_path: Path) -> None:
    """Writing `shell /bin/zsh` without zsh present would stop kitty starting."""
    env = _setup(tmp_path)
    # _HYPRCONF_ZSH="" is the seam for "no zsh on this box" — the real lookup
    # would otherwise find the host's zsh, since /usr/bin has to stay on PATH
    # for coreutils.
    assert _run(env, "--no-update", extra_env={"_HYPRCONF_ZSH": ""}).returncode == 0
    body = _code_only((env["home"] / ".config" / "kitty" / "hyprconf.conf").read_text())
    assert "shell " not in body


def test_zsh_installed_by_the_package_stage_is_used_in_the_same_run(tmp_path: Path) -> None:
    """The zsh lookup must happen AFTER packages: on a fresh Omarchy zsh does not
    exist until stage_packages installs it, and a lookup at startup pins the
    empty string for the whole run — first install, no ~/.zshrc, bash in
    kitty."""
    env = _setup(tmp_path, with_zsh=False)
    zsh = env["bins"] / "zsh-installed-by-pkg-add"
    # Stand in for `pacman -S zsh`: the binary appears while the run is going.
    _stub(
        env["bins"] / "omarchy-pkg-add",
        env["calls"],
        f'printf "#!/usr/bin/env bash\\nexit 0\\n" > "{zsh}"; chmod 755 "{zsh}"',
    )

    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_ZSH_BIN": zsh.name})
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
    """bindings/input/looknfeel are Omarchy's own post-defaults require points,
    and each stock file is its commented template — so the backup is what
    makes the overlay reversible by hand."""
    env = _setup(tmp_path)
    for _ in range(2):  # the backup must not be re-taken from our own symlink
        _run(env, "--no-update")
    hypr = env["home"] / ".config" / "hypr"
    for name in ("bindings.lua", "input.lua", "looknfeel.lua"):
        assert hypr.joinpath(name).is_symlink(), name
        assert hypr.joinpath(name).resolve() == REPO_ROOT / "hypr" / name
        assert hypr.joinpath(f"{name}.stock").read_text() == f"-- stock omarchy {name}\n"


def test_a_dotfiles_link_at_an_override_path_is_backed_up_as_a_link(
    tmp_path: Path,
) -> None:
    """A stow-style link at one of these paths is somebody's own arrangement. The
    guard used to skip every link, so `ln -sfn` overwrote it with no backup
    and no message; `cp -P` keeps it a link, so the README's `mv …stock` hands
    it back pointing where it pointed."""
    env = _setup(tmp_path)
    theirs = tmp_path / "dotfiles"
    theirs.mkdir()
    (theirs / "bindings.lua").write_text("-- their own bindings\n")
    (theirs / "p10k.zsh").write_text("# their own prompt\n")
    links = {
        env["home"] / ".config" / "hypr" / "bindings.lua": theirs / "bindings.lua",
        env["home"] / ".p10k.zsh": theirs / "p10k.zsh",
    }
    for link, src in links.items():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.unlink(missing_ok=True)
        link.symlink_to(src)

    for _ in range(2):  # a re-run must not overwrite the backup with our link
        assert _run(env, "--no-update").returncode == 0

    for link, src in links.items():
        backup = link.with_name(link.name + ".stock")
        assert backup.is_symlink(), f"{backup} is not a link"
        assert Path(os.readlink(backup)) == src
        assert link.is_symlink() and link.resolve() != src
    # And the revert line puts each one back unchanged.
    for link, src in links.items():
        backup = link.with_name(link.name + ".stock")
        link.unlink()
        backup.rename(link)
        assert Path(os.readlink(link)) == src


def test_a_backup_a_user_re_created_their_link_over_is_never_overwritten(
    tmp_path: Path,
) -> None:
    """The first .stock is the one that matters: a user who puts their own link
    back after an install, then re-runs, must not have the first backup
    replaced by the second (or, later, by ours)."""
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    _run(env, "--no-update")
    assert hypr.joinpath("bindings.lua.stock").read_text() == "-- stock omarchy bindings.lua\n"

    theirs = tmp_path / "their-bindings.lua"
    theirs.write_text("-- their own bindings\n")
    hypr.joinpath("bindings.lua").unlink()
    hypr.joinpath("bindings.lua").symlink_to(theirs)
    _run(env, "--no-update")
    assert hypr.joinpath("bindings.lua.stock").read_text() == "-- stock omarchy bindings.lua\n"


def test_monitor_presets_are_installed_without_touching_the_active_layout(
    tmp_path: Path,
) -> None:
    """Presets are inert files; monitors.lua stays whatever the machine chose. A
    chosen preset goes to Omarchy's Hyprland toggles directory, which
    hyprland.lua requires AFTER monitors.lua (config/hypr/hyprland.lua:19,26,
    4.0.3-1), so no backup of monitors.lua is needed or taken."""
    env = _setup(tmp_path)
    hypr = env["home"] / ".config" / "hypr"
    hypr.joinpath("monitors.lua").write_text("-- omarchy auto layout\n")
    _run(env, "--no-update")
    for _, preset in PRESETS:
        assert hypr.joinpath(preset).is_file(), preset
    assert hypr.joinpath("monitors.lua").read_text() == "-- omarchy auto layout\n"
    assert not hypr.joinpath("monitors.lua.stock").exists()
    assert not (env["home"] / TOGGLE).exists()


def test_monitor_preset_reaches_every_preset(tmp_path: Path) -> None:
    """What couples stage_monitors' seed list to the names the tool answers
    to: a preset that cannot be named is dead config. `stock` and the toggle
    mechanics are test_monitor_preset.py's, against a faithful fake."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    hypr = env["home"] / ".config" / "hypr"
    toggle = env["home"] / TOGGLE
    for name, preset in PRESETS:
        proc = _switch(env, name)
        assert proc.returncode == 0, proc.stderr
        assert toggle.read_bytes() == hypr.joinpath(preset).read_bytes(), name


def test_never_switches_the_active_theme() -> None:
    """install.sh never takes the active theme away — the overlay re-applies
    itself after every Omarchy update, and the theme it ships is installed
    from modules/themes, never activated (that module's own copy of this
    assertion is test_installing_never_activates_a_theme). Scanned rather than
    run, which covers every branch instead of the one a run takes."""
    code = _code_only(INSTALL_SH.read_text())
    assert "omarchy-theme-set" not in re.findall(r"\bomarchy-[a-z0-9-]+\b", code)


def test_presets_are_seeded_once_and_never_overwritten(tmp_path: Path) -> None:
    """A preset describes one machine's desk, so the machine owns it after
    seeding: hyprconf-monitor-preset's header promises edits survive
    re-selecting a preset, and the post-update hook re-runs this installer
    after every Omarchy update."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    preset = env["home"] / ".config" / "hypr" / "pcMonitors.bedroom.lua"
    preset.write_text("-- my desk, my monitors\n")
    _run(env, "--no-update")
    assert preset.read_text() == "-- my desk, my monitors\n"


def test_the_default_browser_is_seeded_once_and_the_marker_waits_for_the_seed(
    tmp_path: Path,
) -> None:
    """Seeded to hyprconf's pick on first install, then the user's — but only
    once the seed took, which is the value READ BACK, not the setter's exit
    status. The editor half of this stage is modules/vscode's now; the marker
    is already the name modules/firefox will use."""
    env = _setup(tmp_path)
    marker = env["home"] / ".local" / "state" / "hyprconf" / "browser-applied"
    # The setter that records the call and leaves the default where it was.
    _stub(
        env["bins"] / "omarchy-default-browser",
        env["calls"],
        _default_app_stub(tmp_path, "browser", "chromium", writes=False),
    )
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "default browser" in proc.stderr
    assert not marker.exists()

    _stub(
        env["bins"] / "omarchy-default-browser",
        env["calls"],
        _default_app_stub(tmp_path, "browser", "chromium"),
    )
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert any(c.startswith("omarchy-default-browser firefox") for c in _calls(env))
    assert marker.exists()


def test_the_pre_split_defaults_marker_still_counts_as_applied(tmp_path: Path) -> None:
    """A machine that ran an install.sh from before the module split carries
    ~/.local/state/hyprconf/defaults-applied. The browser must not be
    re-asserted over a pick made since, and the file is left in place —
    modules/vscode honours it too, for one release."""
    env = _setup(tmp_path)
    state = env["home"] / ".local" / "state" / "hyprconf"
    state.mkdir(parents=True)
    (state / "defaults-applied").touch()
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert not any(c.startswith("omarchy-default-browser firefox") for c in _calls(env))
    assert (state / "defaults-applied").exists()


# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------


def test_sync_runs_omarchy_update_and_never_pacman(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    _run(env, "--sync")
    calls = _calls(env)
    assert any(c.startswith("omarchy-update") for c in calls)
    assert not any(c.startswith("pacman") for c in calls)


def test_no_update_beats_sync_in_either_order(tmp_path: Path) -> None:
    """--no-update documents "never invoke omarchy-update": --sync sets the
    update flag, so a last-wins option loop would let `--no-update --sync`
    update anyway. The latch must win regardless of order."""
    for order in (("--no-update", "--sync"), ("--sync", "--no-update")):
        env = _setup(tmp_path / order[0].strip("-"))
        _run(env, *order)
        assert not any(c.startswith("omarchy-update") for c in _calls(env)), order


def test_a_failed_pull_stops_the_sync_before_anything_is_applied(tmp_path: Path) -> None:
    """--sync is pull, apply, omarchy-update, each gated on the last: a pull that
    fails is a stop with git's own error above it, never a stale checkout
    applied and an Omarchy update run on top of it."""
    env = _setup(tmp_path)
    # `pull.rebase = true` is a common global setting, and under it a bare
    # `git pull --ff-only` refuses whenever the checkout has unstaged edits —
    # and the overlay's checkout is where the overlay is edited (install.sh's
    # own comment carries the why).
    assert "-c pull.rebase=false" in _stage_body("stage_pull")
    _stub(env["bins"] / "git", env["calls"], 'case " $* " in *" pull "*) exit 1 ;; esac; exit 0')
    proc = _run(env, "--sync")
    assert proc.returncode != 0
    assert "git pull failed" in proc.stderr
    assert any(" pull " in f" {c} " for c in _calls(env))
    assert "omarchy-update" not in _commands(env)
    assert "omarchy-pkg-add" not in _commands(env)  # the first stage after the pull
    assert "omarchy-default-terminal" not in _commands(env)  # and a later one
    assert not (env["home"] / ".zshrc").exists()


def test_package_install_failure_stops_the_run(tmp_path: Path) -> None:
    """The packages stage has no terminal guard of its own (AGENTS › Hard
    rules, 6): with no terminal for sudo, omarchy-pkg-add fails on a missing
    package, and the run must die there instead of carrying on."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-pkg-add", env["calls"], "exit 1")
    proc = _run(env, "--no-update")
    assert proc.returncode != 0
    assert "package install failed" in proc.stderr
    assert not (env["home"] / ".zshrc").exists()


def test_unknown_flag_is_rejected(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    proc = _run(env, "--definitely-not-a-flag")
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# The hooks
# ---------------------------------------------------------------------------


def _theme_state(env: dict) -> Path:
    """An active Omarchy theme as omarchy-theme-set leaves it: theme.name plus
    colors.toml (what the omarchy-theme-refresh fake renders templates from)."""
    theme = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme"
    theme.mkdir(parents=True, exist_ok=True)
    (theme.parent / "theme.name").write_text("lumon\n")
    (theme / "colors.toml").write_text(
        'mode = "dark"\nbackground = "#16242d"\nforeground = "#d6e2ee"\naccent = "#8bc9eb"\n'
        'dark_background = "#101b21"\nlighter_background = "#1b2d40"\n'
    )
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


def test_hooks_are_installed_through_omarchy_hook_install(tmp_path: Path) -> None:
    """omarchy-update runs post-update.d/* and omarchy-theme-set ends with
    `omarchy-hook theme-set <name>`. Each hook is rendered — the checkout path
    resolved — under its final basename and handed to Omarchy's own
    `omarchy-hook-install <type> <file>` (4.0.3-1: mkdir -p, cp, chmod 755)."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    hooks = env["home"] / ".config" / "omarchy" / "hooks"
    installs = [c for c in _calls(env) if c.startswith("omarchy-hook-install ")]
    assert sorted(c.split()[1] for c in installs) == ["post-update", "theme-set"]
    for name in ("post-update", "theme-set"):
        call = next(c for c in installs if c.split()[1] == name)
        assert call.split()[2].endswith("/10-hyprconf"), call  # installed under its basename
        installed = hooks / f"{name}.d" / "10-hyprconf"
        body = installed.read_text()
        assert "@HYPRCONF_DIR@" not in body and str(REPO_ROOT) in body, name
        assert os.access(installed, os.X_OK), name


def _run_hook(env: dict, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """The installed post-update hook run the way omarchy-hook runs it — `bash
    <hook>` (bin/omarchy-hook:26, 4.0.3-1) — under install.sh's own pinned
    environment, with a terminal: the hook's flags, not a missing tty, must be
    what keeps the sudo stages out."""
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    return subprocess.run(
        ["bash", str(hook)],
        capture_output=True,
        text=True,
        timeout=60,
        env=_install_env(env, extra_env={"_HYPRCONF_ASSUME_TTY": "1", **(extra_env or {})}),
    )


def test_post_update_hook_reapplies_the_overlay_without_update_or_sudo(tmp_path: Path) -> None:
    """omarchy-update runs the migrations and THEN this hook (bin/omarchy-update:
    48-49), which execs the checkout's install.sh with `--no-update
    --no-packages` — the only recursion guard there is, and the production
    path for both flags."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "omarchy-pkg-present", env["calls"], "exit 1")
    assert _run(env, "--no-update").returncode == 0
    bindings = env["home"] / ".config" / "hypr" / "bindings.lua"
    bindings.unlink()  # never write through the link: it points into the real checkout
    bindings.write_text("-- a migration put the stock file back\n")
    env["calls"].write_text("")
    proc = _run_hook(env)
    assert proc.returncode == 0, proc.stderr
    assert bindings.is_symlink()  # the overlay was re-applied
    commands = _commands(env)
    assert "omarchy-default-terminal" in commands
    for forbidden in (
        "omarchy-update",
        "sudo",
        "omarchy-pkg-add",
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
        "udevadm",
    ):
        assert forbidden not in commands, forbidden

    # omarchy-hook must never let a hook abort an update, and the hook must
    # re-apply on hyprsync's update too: omarchy-update runs the migrations
    # and THEN the hook, so under --sync this run is the one that undoes them.
    # The environment guard that once skipped exactly that run may not return.
    code = _code_only(HOOK.read_text())
    assert "set -e" not in code
    assert "HYPRCONF_SYNC_RUNNING" not in code
    assert "HYPRCONF_SYNC_RUNNING" not in _code_only(INSTALL_SH.read_text())


def test_post_update_hook_bows_out_when_the_checkout_is_gone(tmp_path: Path) -> None:
    """A deleted or moved checkout: the hook says so on stderr and exits 0 —
    omarchy-hook reports a failing hook, and an Omarchy update must never
    look failed over a missing overlay. Nothing runs."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    assert _run(env, "--no-update", install_sh=repo / "install.sh").returncode == 0
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    assert f'HYPRCONF_DIR="{repo}"' in hook.read_text()
    (repo / "install.sh").rename(tmp_path / "install.sh.moved")
    env["calls"].write_text("")
    proc = _run_hook(env)
    assert proc.returncode == 0, proc.stderr
    assert "is gone" in proc.stderr
    assert _calls(env) == []


def test_theme_set_hook_extends_the_theme_to_firefox(tmp_path: Path) -> None:
    """Omarchy renders hyprconf's user template into the current theme dir; the
    hook copies it into the Firefox profile and merges user.js, and install.sh
    runs it once for the active theme so nothing waits for the next switch.
    (VS Code is themed by Omarchy's own omarchy-theme-set-vscode.)"""
    env = _setup(tmp_path)
    _real_jq(env)
    _theme_state(env)
    profile = _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr

    rendered = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme" / "userChrome.css"
    assert rendered.is_file(), "stage_themed did not get the template rendered"
    assert (profile / "chrome" / "userChrome.css").read_bytes() == rendered.read_bytes()
    assert "user_pref(" in (profile / "user.js").read_text()

    # Idempotent: a second run (the post-update hook's) changes nothing.
    before = _tree_hash(profile)
    _run(env, "--no-update")
    assert _tree_hash(profile) == before


def test_theme_stage_is_a_noop_without_an_active_theme(tmp_path: Path) -> None:
    """The templates are installed either way; with no theme.name there is
    nothing to render them from, so nothing is refreshed and no profile is
    touched — the next `omarchy theme set` renders them."""
    env = _setup(tmp_path)
    profile = _firefox_profile(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert (env["home"] / ".config" / "omarchy" / "themed" / "userChrome.css.tpl").is_file()
    assert not (profile / "user.js").exists()
    assert "omarchy-theme-refresh" not in _commands(env)


# ---------------------------------------------------------------------------
# Theme templates — Omarchy's user template seam
# ---------------------------------------------------------------------------


def _themed_checkout(tmp_path: Path) -> tuple[Path, str]:
    """A throwaway checkout with one extra user template beside the shipped
    themed/userChrome.css.tpl — a one-variable file the re-render step can
    rewrite and assert literally. Returns (checkout, template name)."""
    repo = _checkout(tmp_path)
    (repo / "themed").mkdir(exist_ok=True)
    name = "hyprconf-test.css.tpl"
    (repo / "themed" / name).write_text("body { color: {{ foreground }}; }\n")
    return repo, name


def test_templates_are_installed_and_rendered_through_omarchy_theme_refresh(
    tmp_path: Path,
) -> None:
    """Every repo themed/*.tpl lands in Omarchy's user template dir, and the
    render for the theme active right now is Omarchy's own
    omarchy-theme-refresh — run only when a template changed or its render is
    missing, so the hook's re-runs cost nothing; never omarchy-theme-set."""
    env = _setup(tmp_path)
    repo, name = _themed_checkout(tmp_path)
    _theme_state(env)
    proc = _run(env, "--no-update", install_sh=repo / "install.sh")
    assert proc.returncode == 0, proc.stderr
    assert "Firefox theming failed" not in proc.stderr  # the hook found the copy's lib/
    installed = env["home"] / ".config" / "omarchy" / "themed" / name
    assert installed.read_bytes() == (repo / "themed" / name).read_bytes()
    assert _commands(env).count("omarchy-theme-refresh") == 1
    assert "omarchy-theme-set" not in _commands(env)
    rendered = env["home"] / ".local" / "state" / "omarchy" / "current" / "theme" / name[:-4]
    assert rendered.read_text() == "body { color: #d6e2ee; }\n"

    env["calls"].write_text("")
    _run(env, "--no-update", install_sh=repo / "install.sh")
    assert "omarchy-theme-refresh" not in _commands(env)

    (repo / "themed" / name).write_text("body { color: {{ accent }}; }\n")
    env["calls"].write_text("")
    _run(env, "--no-update", install_sh=repo / "install.sh")
    assert installed.read_text() == "body { color: {{ accent }}; }\n"
    assert _commands(env).count("omarchy-theme-refresh") == 1
    assert rendered.read_text() == "body { color: #8bc9eb; }\n"


# ---------------------------------------------------------------------------
# Static scans over the whole overlay tree
# ---------------------------------------------------------------------------


def _overlay_scripts() -> list[Path]:
    """Every shell script the overlay ships: the PAYLOAD trees filtered by a bash
    shebang, the rule `make shellcheck` selects by. Walked on disk, not `git
    ls-files`, so the scan needs no git and no ownership trust; scripts/publish
    is outside PAYLOAD and covered by the Makefile's whole-tree pass. modules/
    is skipped: each module carries its own script-shape and forbidden-forms
    tests (modules/<name>/test_<name>.py), and the tree-wide scan lands in
    tests/test_scans.py with the core rewrite."""
    paths: list[Path] = []
    for name in PAYLOAD:
        if name == "modules":
            continue
        top = REPO_ROOT / name
        if not top.exists():
            continue
        paths.extend([top] if top.is_file() else sorted(top.rglob("*")))
    scripts = []
    for p in paths:
        if not p.is_file() or p.suffix not in {".sh", ""}:
            continue
        with p.open("rb") as fh:
            first = fh.readline()
        if first.startswith(b"#!") and b"bash" in first:
            scripts.append(p)
    return scripts


# AGENTS.md › Scripts: `#!/usr/bin/env bash` and `set -euo pipefail`, with the
# deviations named there — the two hooks and hyprconf-yubikey drop -e (they
# handle their own failures), hyprconf-stats is `set -u`. The map IS that
# list, so a script that quietly drops a guard fails here.
SET_LINE = {
    "hyprconf-yubikey": "set -uo pipefail",
    "10-hyprconf": "set -uo pipefail",
    "hyprconf-stats": "set -u",
}


@pytest.mark.parametrize("script", _overlay_scripts(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_every_overlay_script_carries_the_documented_header(script: Path) -> None:
    """One header check for the whole tree. `make shellcheck` selects scripts BY
    the shebang, so a missing one means no lint at all rather than a failure:
    this is what catches that."""
    text = script.read_text()
    assert text.startswith("#!/usr/bin/env bash\n"), script
    want = SET_LINE.get(script.name, "set -euo pipefail")
    assert re.search(rf"^{re.escape(want)}$", text, re.M), f"{script}: no `{want}` line"
    # The hooks are installed by `omarchy hook install`, which copies and
    # chmods 755 (/usr/bin/omarchy-hook-install:27-29, Omarchy 4.0.3-1);
    # everything else is run from where it lands, so it carries the bit.
    if "hooks" not in script.parts:
        assert script.stat().st_mode & stat.S_IXUSR, f"{script}: not executable"
    # A seam has to stay overridable, or the suite cannot point it at a fake
    # (AGENTS.md › Scripts). Constants of the script's own may be readonly.
    frozen = re.findall(r"^\s*readonly\s+(_HYPRCONF_\w+|HYPRCONF_(?:STATS|GPU)_\w+)", text, re.M)
    assert not frozen, f"{script}: readonly seam {frozen}"


def test_every_omarchy_command_install_sh_calls_has_a_fake(tmp_path: Path) -> None:
    """The hermetic contract (AGENTS.md › Tests): /usr/bin carries every omarchy-*
    command on a dev box, so an unstubbed call reaches the real desktop from a
    test — silently where it is guarded with `|| true`, as several are."""
    env = _setup(tmp_path)
    fakes = {p.name for p in env["bins"].iterdir()}
    assert set(OMARCHY_STUBS) <= fakes
    called = set(re.findall(r"\bomarchy-[a-z0-9-]+\b", _code_only(INSTALL_SH.read_text())))
    assert called, "no omarchy-* calls found — the scan regex is broken"
    unstubbed = called - fakes
    assert not unstubbed, f"omarchy-* commands install.sh can run with no fake: {sorted(unstubbed)}"


# Packages go through Omarchy's front-end and nothing else: `pacman` on any
# path, the AUR wrappers, and `chsh` — the login shell stays bash, which is
# the hybrid's whole point (AGENTS.md › Hard rules, 3 and 6). Whole words, so
# the scan says what the rules say rather than three pacman spellings.
FORBIDDEN_PATTERNS = (
    r"\bpacman\b",
    r"\byay\b",
    r"\bparu\b",
    r"\bmakepkg\b",
    r"\bchsh\b",
    # Every AUR wrapper Omarchy ships in one token: -add, -install and
    # -accessible (/usr/bin/omarchy-pkg-aur-*), plus the AUR half of its updater.
    r"omarchy-pkg-aur-",
    r"omarchy-update-aur-pkgs",
)


def test_overlay_never_uses_forbidden_pacman_aur_or_chsh_forms() -> None:
    for script in _overlay_scripts():
        code = _code_only(script.read_text(errors="ignore"))
        for pattern in FORBIDDEN_PATTERNS:
            assert not re.search(pattern, code), f"{script}: {pattern}"


# The overlay's network trust is clone-only over https: fetching content and
# executing it would add a network trust root the model never had (AGENTS ›
# Security). Every exception is written down here, in full, or does not land.
# Whole-word curl/wget on purpose: URL-first invocations and `sh -c "$(curl
# …)"` all carry the word; the pipe net catches any *sh interpreter.
FETCH_EXEC_PATTERNS = (
    r"\bcurl\b",
    r"\bwget\b",
    r"\|&?\s*\w*sh\b",
    r"bash\s*<\(",
    r"source\s*<\(",
    r"base64\s+(?:-d|--decode)",
    r"(?<!hyprctl )\beval\b",
)
FETCH_EXEC_ALLOWED = (
    # zoxide's documented init: output of a pacman-installed binary
    'command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init zsh)"',
)
# install.sh's usage() heredoc: prose that documents the curl one-liner, not a
# call. Dropped for this scan only — _code_only must keep every other heredoc
# (bin/hyprconf-vulkan-gpu, bin/hyprconf-yubikey) inside it.
USAGE_HEREDOC = re.compile(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$")


def _fetch_exec_surface() -> list[Path]:
    """_overlay_scripts() plus the shipped shell payload its suffix filter
    misses — the zsh block and p10k config every interactive zsh executes,
    and the kitty conf. The scan must reach everything that runs."""
    return _overlay_scripts() + [
        REPO_ROOT / "zsh" / "zshrc.block",
        REPO_ROOT / "zsh" / ".p10k.zsh",
        REPO_ROOT / "kitty" / "hyprconf.conf",
    ]


def test_overlay_never_fetches_and_executes() -> None:
    for script in _fetch_exec_surface():
        code = USAGE_HEREDOC.sub("", _code_only(script.read_text(errors="ignore")))
        for allowed in FETCH_EXEC_ALLOWED:
            code = code.replace(allowed, "")
        for pat in FETCH_EXEC_PATTERNS:
            assert not re.search(pat, code), f"{script}: fetch-and-execute shape {pat!r}"


def test_bootstrap_defaults_are_pinned_https_and_stable() -> None:
    """The first bytes strangers run. Every behavioral curl-path test
    overrides HYPRCONF_REPO, so an http:// downgrade or fork URL in the
    default would ship green without this literal pin."""
    text = INSTALL_SH.read_text()
    assert ': "${HYPRCONF_REPO:=https://github.com/ak4dev/.hyprconf}"' in text
    assert ': "${HYPRCONF_BRANCH:=stable}"' in text


def test_packages_file_lines_are_plain_package_names() -> None:
    """A line starting with '-' would reach the sudo package stage as an
    option, not a package. Each module's own `packages` file is pinned the
    same way by its own suite (modules/font/test_font.py)."""
    for ln in (REPO_ROOT / "packages").read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        assert re.fullmatch(r"[a-z0-9][a-z0-9@._+-]*", ln), f"packages: {ln!r}"


def test_overlay_never_uses_the_dead_hyprctl_forms() -> None:
    """`hyprctl keyword` and a two-token `hyprctl dispatch dpms on` are both
    dead under Hyprland 0.56's Lua parser; the working forms are `hyprctl eval`
    and `hyprctl dispatch 'hl.dsp.…'` (AGENTS.md › Known quirks)."""
    dead = re.compile(
        r"hyprctl\s+(--batch\s+)?[\"']?keyword\b|hyprctl\s+dispatch\s+[a-z_]+\s+[a-z_]+"
    )
    offenders = [
        f"{script.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
        for script in _overlay_scripts()
        for lineno, line in enumerate(_code_only(script.read_text(errors="ignore")).splitlines(), 1)
        if dead.search(line)
    ]
    assert not offenders, "use hyprctl eval / hyprctl dispatch 'hl.dsp.…':\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# The Firefox policy — one of the overlay's two writes outside $HOME
# ---------------------------------------------------------------------------


def _policy_env(tmp_path: Path, env: dict) -> tuple[Path, dict[str, str]]:
    """A sudo that actually runs its command (so the policy lands in the
    tree), the real jq (the merge), and the policy path under tmp_path."""
    _real_jq(env)
    _stub(env["bins"] / "sudo", env["calls"], '"$@"')
    policies = tmp_path / "etc" / "firefox" / "policies"
    return policies, {"_HYPRCONF_ASSUME_TTY": "1", "_HYPRCONF_FIREFOX_POLICIES": str(policies)}


def test_firefox_policy_is_omarchys_merged_under_ours_via_sudo_when_interactive(
    tmp_path: Path,
) -> None:
    """Firefox reads enterprise policies only from root-owned paths, and
    /etc/firefox/policies takes precedence over the distribution/ file
    omarchy-install-browser writes — so what lands is Omarchy's policy merged
    UNDER ours. A matching file is left alone: no re-prompt on a re-run."""
    env = _setup(tmp_path)
    policies, extra = _policy_env(tmp_path, env)
    proc = _run(env, "--no-update", extra_env=extra)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-browser" not in _commands(env)  # firefox is present

    installed = json.loads((policies / "policies.json").read_text())["policies"]
    ours = json.loads((REPO_ROOT / "infra" / "firefox" / "policies.json").read_text())["policies"]
    for key, value in ours.items():
        if key != "Preferences":
            assert installed[key] == value, key
    for pref, value in ours["Preferences"].items():  # SHARED_PREF included: ours wins
        assert installed["Preferences"][pref] == value, pref
    for pref, value in OMARCHY_FIREFOX_POLICY["policies"]["Preferences"].items():
        if pref != SHARED_PREF:
            assert installed["Preferences"][pref] == value, pref

    env["calls"].write_text("")
    _run(env, "--no-update", extra_env=extra)
    assert "sudo" not in _commands(env)


def test_every_sudo_stage_bows_out_without_a_terminal(tmp_path: Path) -> None:
    """The post-update hook runs non-interactively inside omarchy-update, where a
    sudo password prompt would stall the whole update. One gate, the same line
    in stage_packages and stage_firefox: no tty, no attempt. The modules carry
    their own (modules/keychron/test_keychron.py, modules/vscode)."""
    env = _setup(tmp_path)
    _real_jq(env)  # else stage_firefox bows out on the merge, before its gate
    _packages(env, ())
    policies = tmp_path / "etc" / "firefox" / "policies"
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_FIREFOX_POLICIES": str(policies)})
    assert proc.returncode == 0, proc.stderr
    for forbidden in (
        "sudo",
        "udevadm",
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
    ):
        assert forbidden not in _commands(env), forbidden
    assert not (policies / "policies.json").exists()


def test_firefox_is_installed_through_omarchys_installer_when_absent(tmp_path: Path) -> None:
    """`omarchy-install-browser firefox` — Omarchy's own flow: omarchy-pkg-add,
    its prefs under /usr/lib/firefox/distribution, MOZ_ENABLE_WAYLAND — runs
    before the policy lands; never a bare omarchy-pkg-add firefox."""
    env = _setup(tmp_path)
    policies, extra = _policy_env(tmp_path, env)
    _stub(env["bins"] / "omarchy-pkg-present", env["calls"], '[ "$1" != firefox ]')
    proc = _run(env, "--no-update", extra_env=extra)
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-install-browser firefox" in calls
    assert calls.index("omarchy-install-browser firefox") < next(
        i for i, c in enumerate(calls) if c.startswith("sudo install")
    )
    assert (policies / "policies.json").is_file()
    pkg_add = [c for c in calls if c.startswith("omarchy-pkg-add")]
    assert pkg_add and not any("firefox" in c.split() for c in pkg_add)


def test_a_failed_firefox_install_leaves_no_policy_behind(tmp_path: Path) -> None:
    """A failed install is a warning with Omarchy's retry command, and the stage
    stops there: no policy for a Firefox that is not installed (it would
    shadow nothing), so no sudo at all, and the run goes on."""
    env = _setup(tmp_path)
    policies, extra = _policy_env(tmp_path, env)
    _stub(env["bins"] / "omarchy-pkg-present", env["calls"], '[ "$1" != firefox ]')
    _stub(env["bins"] / "omarchy-install-browser", env["calls"], "exit 1")
    proc = _run(env, "--no-update", extra_env=extra)
    assert proc.returncode == 0, proc.stderr
    assert "omarchy-install-browser firefox" in _calls(env)
    assert "retry with: omarchy install browser firefox" in proc.stderr
    assert not policies.exists()
    # No `sudo install` of a policy — the run's other root write is
    # modules/keychron's, which has its own gate and its own tests.
    assert not [c for c in _calls(env) if c.startswith("sudo") and "policies" in c]
    assert (env["home"] / ".zshrc").exists()  # a stage well after the Firefox one


# ---------------------------------------------------------------------------
# Package presence — the helper the Firefox and sudo-gate tests share
# ---------------------------------------------------------------------------


def _packages(env: dict, present: tuple[str, ...]) -> None:
    """omarchy-pkg-present answering for exactly these package names. The
    VS Code installer stub then makes visual-studio-code-bin present, the way
    the real one does (omarchy-pkg-add inside) — modules/vscode runs inside a
    full install.sh run and reads the result back."""
    marker = env["home"].parent / "vscode-installed"
    names = " ".join(present)
    _stub(
        env["bins"] / "omarchy-pkg-present",
        env["calls"],
        f'case " {names} " in *" $1 "*) exit 0;; esac; '
        f'[ "$1" = visual-studio-code-bin ] && [ -e "{marker}" ]',
    )
    _stub(env["bins"] / "omarchy-install-editor-vscode", env["calls"], f'touch "{marker}"')


# omarchy-plugin-enable and omarchy-bar mutate the config the shell holds in
# memory and persist it to shell.json LATER — shell.qml writes through a
# FileView (PluginRegistry.qml, Omarchy 4.0.3-1). The enable's swap is
# modelled synchronously, so wait_for_swap has a cause to return on; the
# `omarchy bar set` that follows snapshots the file AT CALL TIME and writes
# the snapshot back after a delay, which is the stale-read hazard itself:
# anything the installer writes to shell.json before that lands is lost.
SHELL_ENABLE_SWAP = """\
[ "$1" = hyprconf.clock ] || exit 0
jq '.bar.layout |= with_entries(.value |= map(if .id == "omarchy.clock" then .id = "hyprconf.clock" else . end))' \
  "$SHELL_JSON" > "$SHELL_JSON.new" && mv "$SHELL_JSON.new" "$SHELL_JSON"
"""
SHELL_LATE_PERSIST = """\
[ "$1" = set ] || exit 0
snap=$(jq --arg id "$2" --arg k "$3" --arg v "$4" \
  '.bar.layout |= with_entries(.value |= map(if .id == $id then . + {($k): $v} else . end))' \
  "$SHELL_JSON")
( sleep 0.2; printf '%s' "$snap" > "$SHELL_JSON" ) &
exit 0
"""


def _late_persisting_shell(env: dict) -> Path:
    """The two shell commands stage_clock talks to, backed by the real jq."""
    _real_jq(env)
    shell_json = env["home"] / ".config" / "omarchy" / "shell.json"
    shell_json.parent.mkdir(parents=True, exist_ok=True)
    for name, body in (
        ("omarchy-plugin-enable", SHELL_ENABLE_SWAP),
        ("omarchy-bar", SHELL_LATE_PERSIST),
    ):
        _stub(env["bins"] / name, env["calls"], f'SHELL_JSON="{shell_json}"\n{body}')
    return shell_json


def test_shell_json_edits_wait_for_the_shells_asynchronous_writes(tmp_path: Path) -> None:
    """The shell answers an enable or a set at once but persists shell.json some
    time later. The anchor edit is a read-modify-write on that file, so
    without wait_for_shell_json it lands on a stale copy and the pending write
    takes it straight back."""
    env = _setup(tmp_path)
    shell_json = _late_persisting_shell(env)
    # Discovered at once, so the enable's own discovery wait does not eat the budget.
    _installed_plugins(
        env, "hyprconf.clock", "hyprconf.workspaces", "hyprconf.active-window", "hyprconf.resources"
    )
    shell_json.write_text(
        json.dumps(
            {
                "bar": {
                    "centerAnchor": "omarchy.clock",
                    "layout": {"left": [], "center": [{"id": "omarchy.clock"}], "right": []},
                }
            }
        )
    )
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_PLUGIN_WAIT": "40"})
    assert proc.returncode == 0, proc.stderr
    data = json.loads(shell_json.read_text())
    assert data["bar"]["centerAnchor"] == "hyprconf.clock"
    assert {"id": "hyprconf.clock", "format": "hh:mm:ss AP"} in data["bar"]["layout"]["center"]
    assert "omarchy.clock" not in [e["id"] for e in data["bar"]["layout"]["center"]]


def test_browser_marker_survives_the_setters_failing_notification(tmp_path: Path) -> None:
    """The setter writes the value and THEN notifies, and its exit status is the
    notification's (no set -e, 4.0.3-1) — so trusting it left the marker
    unwritten on exactly the runs that had succeeded, and the next in-session
    run re-asserted firefox over a browser chosen in between."""
    env = _setup(tmp_path)
    _stub(
        env["bins"] / "omarchy-default-browser",
        env["calls"],
        _default_app_stub(tmp_path, "browser", "chromium", set_status=1),
    )
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "default browser" not in proc.stderr
    assert (env["home"] / ".local" / "state" / "hyprconf" / "browser-applied").exists()

    # The user's later pick, which the re-run must not take back.
    (tmp_path / "browser").write_text("zen")
    env["calls"].write_text("")
    _run(env, "--no-update")
    assert not any(c.startswith("omarchy-default-browser ") for c in _calls(env))
    assert (tmp_path / "browser").read_text() == "zen"


def test_every_shipped_tool_lands_on_path(tmp_path: Path) -> None:
    """Every bin/hyprconf-* file, installed by glob with @HYPRCONF_DIR@
    substituted for the checkout path — byte for byte, and executable."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    shipped = sorted(p.name for p in (REPO_ROOT / "bin").glob("hyprconf-*"))
    assert shipped, "no tools in bin/"
    for name in shipped:
        installed = env["home"] / ".local" / "bin" / name
        assert os.access(installed, os.X_OK), name
        expected = (REPO_ROOT / "bin" / name).read_text().replace("@HYPRCONF_DIR@", str(REPO_ROOT))
        assert installed.read_text() == expected, name


# ---------------------------------------------------------------------------
# The bar clock
# ---------------------------------------------------------------------------


def _plugin_state(root: Path) -> dict[str, tuple[bytes, int]]:
    """Every file under a plugin folder with its bytes and permission bits —
    what `cp -aL` has to reproduce, mode included."""
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_every_shipped_plugin_is_synced_from_the_checkout_and_enabled_once(
    tmp_path: Path,
) -> None:
    """One run, every plugins/* folder: the installed copy is the checkout's bytes
    AND modes under the manifest's own id, enabled exactly once, no staging
    dir left behind. Then the two repaired drifts — a stale file and a lost
    exec bit — and a re-run that enables nothing, so a disable sticks."""
    env = _setup(tmp_path)
    _real_jq(env)
    assert _run(env, "--no-update").returncode == 0
    installed = env["home"] / ".config" / "omarchy" / "plugins"
    folders = sorted((REPO_ROOT / "plugins").iterdir())
    assert folders, "no plugin folders in the checkout"

    enables = [c for c in _calls(env) if c.startswith("omarchy-plugin-enable ")]
    assert len(enables) == len(folders)
    for src in folders:
        plug = installed / json.loads((src / "manifest.json").read_text())["id"]
        assert _plugin_state(plug) == _plugin_state(src), plug.name
        assert f"omarchy-plugin-enable {plug.name}" in enables, plug.name
    assert "omarchy-shell shell rescanPlugins" in _calls(env)
    assert "omarchy-restart-shell" not in _commands(env)
    assert not list(installed.glob(".hyprconf.*"))

    (installed / "hyprconf.workspaces" / "Workspaces.qml").write_text("// stale\n")
    (installed / "hyprconf.resources" / "bin" / "hyprconf-stats").chmod(0o644)
    env["calls"].write_text("")
    assert _run(env, "--no-update").returncode == 0
    for src in folders:
        plug = installed / json.loads((src / "manifest.json").read_text())["id"]
        assert _plugin_state(plug) == _plugin_state(src), plug.name
    assert "omarchy-shell shell rescanPlugins" in _calls(env)
    assert not any(c.startswith("omarchy-plugin-enable") for c in _calls(env))
    assert not list(installed.glob(".hyprconf.*"))


def test_the_clock_copy_is_enabled_and_formatted_once(tmp_path: Path) -> None:
    """The stock widget samples SystemClock at Minutes precision (shell/plugins/
    panels/clock/BarWidget.qml), so a seconds format would sit frozen 59 s of
    every minute — hence a copy of Omarchy's own widget carrying that delta.
    The enable and the format are set once: a reformatted clock stays theirs."""
    env = _setup(tmp_path)
    _real_jq(env)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-enable hyprconf.clock" in calls
    assert "omarchy-bar set hyprconf.clock format hh:mm:ss AP" in calls
    assert "omarchy-plugin-catalog" not in _commands(env)
    # The three deltas the copy exists for, on the installed copy — the only
    # place they are pinned where there is no Omarchy to diff against
    # (test_plugins.py's parity test is the authority on a box that has one).
    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.clock"
    widget = (plug / "BarWidget.qml").read_text()
    assert "SystemClock.Seconds" in widget and "SystemClock.Minutes" not in widget
    # The calendar panel comes from the running Omarchy, never a stale copy…
    assert 'Quickshell.env("OMARCHY_PATH")' in widget
    assert not (plug / "Panel.qml").exists()
    # …and is told which module id it is mounted as, or persistSettings()
    # writes through an id no live bar entry carries and the calendar's own
    # settings (a week start, a birth year) are never saved.
    assert 'if ("moduleName" in target) target.moduleName = root.moduleName' in widget
    assert "onModuleNameChanged: injectPanel()" in widget


def test_the_documented_clock_revert_undoes_what_the_stage_applied() -> None:
    """`omarchy plugin disable hyprconf.clock` alone is not stock: restoreCloneSource
    copies the clone's whole bar entry onto omarchy.clock and rewrites only its
    id (PluginRegistry.qml, 4.0.3-1), and bar.centerAnchor gets no clone
    resolution — so README's revert block has to carry both extra steps."""
    applied = re.search(
        r'set_clock_format\(\) \{\n\s*local id="\$1" format="([^"]+)"', INSTALL_SH.read_text()
    )
    assert applied, "set_clock_format no longer states the format it applies"
    widget = (REPO_ROOT / "plugins" / "hyprconf-clock" / "BarWidget.qml").read_text()
    stock = re.search(r'setting\("format", "([^"]+)"\)', widget)
    assert stock, "BarWidget.qml no longer carries Omarchy's format fallback"
    assert applied.group(1) != stock.group(1), "nothing to undo if they match"

    revert = (REPO_ROOT / "README.md").read_text().split("## Reverting to stock", 1)[1]
    revert = revert.split("\n## ", 1)[0]
    assert f"omarchy bar set omarchy.clock format '{stock.group(1)}'" in revert
    assert ".bar.centerAnchor" in revert


def test_plugin_sync_leaves_an_omarchy_plugin_add_checkout_alone(tmp_path: Path) -> None:
    """`omarchy plugin add <url>` lands the same id as a git checkout, which is
    Omarchy's to update (bin/omarchy-plugin-update fast-forwards it and
    refuses a non-git folder) — so the sync must not read its .git as stale
    and replace it, edits and all."""
    env = _setup(tmp_path)
    plug = env["home"] / ".config" / "omarchy" / "plugins" / "hyprconf.resources"
    (plug / ".git").mkdir(parents=True)
    (plug / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (plug / "Widget.qml").write_text("// the user's checkout\n")
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert (plug / ".git" / "HEAD").read_text() == "ref: refs/heads/main\n"
    assert (plug / "Widget.qml").read_text() == "// the user's checkout\n"
    assert not (plug / "manifest.json").exists()
    assert not list(plug.parent.glob(".hyprconf.*"))
    assert "omarchy plugin update hyprconf.resources" in proc.stdout
    assert "omarchy-plugin-enable hyprconf.resources" in _calls(env)
    # The other plugins are synced as before.
    assert (plug.parent / "hyprconf.workspaces" / "manifest.json").is_file()


def test_bar_widget_enables_retry_until_the_shell_can_answer(tmp_path: Path) -> None:
    """A TTY or SSH run has no live shell to enable against, and omarchy-plugin-list
    (set -e) exits 1 identically on every poll. So: no abort, no set-once
    marker, nothing set on a clock that never landed, and one list call per
    enable rather than the whole discovery wait per widget."""
    env = _setup(tmp_path)
    _real_jq(env)
    _stub(env["bins"] / "omarchy-plugin-list", env["calls"], "exit 1")
    _stub(env["bins"] / "omarchy-plugin-enable", env["calls"], "exit 1")
    proc = _run(env, "--no-update", extra_env={"_HYPRCONF_PLUGIN_WAIT": "40"})
    assert proc.returncode == 0, proc.stderr
    state = env["home"] / ".local" / "state" / "hyprconf"
    for widget in ("resources", "clock", "workspaces", "active-window"):
        assert not (state / f"{widget}-applied").exists(), widget
        assert f"hyprconf.{widget}" in proc.stderr, widget
    commands = _commands(env)
    assert "omarchy-bar" not in commands
    assert commands.count("omarchy-plugin-enable") == 4
    assert commands.count("omarchy-plugin-list") == 4


def test_a_changed_plugin_restarts_the_shell_when_no_rescan_answers(tmp_path: Path) -> None:
    """`omarchy-shell shell rescanPlugins` hot-reloads plugin code (what
    omarchy-plugin-update runs after a fast-forward) and exits 1 when no shell
    answers — only then is the shell restarted, which is how one comes back."""
    env = _setup(tmp_path)
    assert _run(env, "--no-update").returncode == 0
    plugins = env["home"] / ".config" / "omarchy" / "plugins"

    _stub(env["bins"] / "omarchy-shell", env["calls"], "exit 1")
    (plugins / "hyprconf.resources" / "Widget.qml").write_text("// stale\n")
    env["calls"].write_text("")
    assert _run(env, "--no-update").returncode == 0
    assert "omarchy-shell shell rescanPlugins" in _calls(env)
    assert "omarchy-restart-shell" in _commands(env)
    assert not list(plugins.glob(".hyprconf.*"))


def test_the_window_title_clone_is_enabled_never_the_stock_widget(tmp_path: Path) -> None:
    """Enabled with no placement of its own: the manifest's defaultSection is
    left, where the shell anchors a new widget right after omarchy.workspaces
    — clone-resolved while our copy holds that slot (PluginRegistry.qml
    barTarget / findRelativeBarLocation, 4.0.3-1)."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    calls = _calls(env)
    assert "omarchy-plugin-enable hyprconf.active-window" in calls
    assert not any("omarchy-plugin-enable omarchy.active-window" in c for c in calls)
    assert (env["home"] / ".local" / "state" / "hyprconf" / "active-window-applied").exists()


# ---------------------------------------------------------------------------
# The bar clock's centre anchor
# ---------------------------------------------------------------------------


def _shell_json(env: dict, anchor: str, center: list[str]) -> Path:
    """~/.config/omarchy/shell.json with one centre anchor and one centre
    section — the two things follow_center_anchor reads."""
    path = env["home"] / ".config" / "omarchy" / "shell.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bar": {"centerAnchor": anchor, "layout": {"center": center}}}))
    return path


def _installed_plugins(env: dict, *ids: str) -> None:
    """omarchy-plugin-list --json answering for a live shell that knows `ids`."""
    _stub(
        env["bins"] / "omarchy-plugin-list",
        env["calls"],
        "echo '[" + ",".join(f'{{"id":"{i}"}}' for i in ids) + "]'",
    )


def test_a_dangling_center_anchor_is_repaired_on_a_later_run(tmp_path: Path) -> None:
    """`omarchy plugin clone` then `remove` leaves bar.centerAnchor naming an id
    that exists nowhere: hasAnchor goes false and the centre section centres
    the whole group (BarModel.js entryIndex). The follow runs on every run,
    not once behind the clock marker, because that is years too early."""
    env = _setup(tmp_path)
    _real_jq(env)
    _installed_plugins(env, "hyprconf.clock", "omarchy.weather")
    # A box that finished its first install long ago: marker present, so the
    # enable and the format are the user's now.
    marker = env["home"] / ".local" / "state" / "hyprconf" / "clock-applied"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    shell_json = _shell_json(env, "someone.clock", ["hyprconf.clock"])
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "hyprconf.clock"


def test_an_anchor_on_a_widget_the_user_disabled_is_left_alone(tmp_path: Path) -> None:
    """The dangling test is "no bar entry AND no such plugin", never the bare
    "not on the bar": a widget the user disabled is off the bar and still
    installed, and its anchor is their choice to re-point — or to restore by
    enabling it again."""
    env = _setup(tmp_path)
    _real_jq(env)
    _installed_plugins(env, "hyprconf.clock", "omarchy.weather")
    shell_json = _shell_json(env, "omarchy.weather", ["hyprconf.clock"])
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "omarchy.weather"


def test_the_anchor_is_not_moved_onto_a_clock_the_bar_does_not_carry(tmp_path: Path) -> None:
    """`omarchy plugin disable hyprconf.clock` puts the stock widget back, and
    the repair must not then point the anchor at a widget that is gone —
    which is the same failure it exists to fix, pointing the other way."""
    env = _setup(tmp_path)
    _real_jq(env)
    _installed_plugins(env, "hyprconf.clock")
    marker = env["home"] / ".local" / "state" / "hyprconf" / "clock-applied"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    shell_json = _shell_json(env, "omarchy.clock", ["omarchy.clock"])
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "omarchy.clock"


def test_a_failed_anchor_edit_warns_and_leaves_no_temp_file(tmp_path: Path) -> None:
    """The `jq … > tmp && mv` tail this replaces printed success whichever way jq
    went — a failing jq is the non-final command of an && list, so set -e
    never fired — while a failing mv, being final, took the whole install down
    over a cosmetic step."""
    env = _setup(tmp_path)
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq available")
    # A jq that reads fine but refuses the one program that writes the anchor.
    _stub(
        env["bins"] / "jq",
        env["calls"],
        f'for a in "$@"; do case "$a" in *".bar.centerAnchor = "*) exit 3 ;; esac; done;'
        f' exec {jq} "$@"',
    )
    shell_json = _shell_json(env, "omarchy.clock", ["hyprconf.clock"])
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert "could not move bar.centerAnchor" in proc.stderr
    assert "centerAnchor follows" not in proc.stdout
    assert json.loads(shell_json.read_text())["bar"]["centerAnchor"] == "omarchy.clock"
    assert not shell_json.with_suffix(".json.tmp").exists()


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


def _guard_env(tmp_path: Path, *, git: str | None = None) -> tuple[dict, Path, Path]:
    """The refresh guard's fixture: a throwaway checkout to install from (never
    the repository the suite runs in), Omarchy's config/hypr templates to
    refresh from, and by default a git real enough to `checkout --`;
    `git=None` leaves the no-op stub, which is a checkout with no git at all."""
    env = _setup(tmp_path)
    repo = _checkout(tmp_path)
    if git:
        _stub(env["bins"] / "git", env["calls"], git)
    return env, repo, _stock_templates(env)


def _apply(env: dict, repo: Path, *args: str) -> subprocess.CompletedProcess:
    """install.sh run out of the throwaway checkout."""
    return _run(env, *(args or ("--no-update",)), install_sh=repo / "install.sh")


def test_refresh_through_the_symlink_is_undone_from_git(tmp_path: Path) -> None:
    """`omarchy refresh hyprland` cp -f's the stock template over every
    ~/.config/hypr/*.lua, following the overlay's symlinks straight into the
    checkout — every hyprconf hotkey gone (observed on 4.0.0-1). A re-run
    notices the byte-identical stock template and puts the commit back."""
    env, repo, templates = _guard_env(tmp_path, git=GIT_PASSTHROUGH)
    committed = (repo / "hypr" / "bindings.lua").read_text()
    assert _apply(env, repo).returncode == 0

    _refresh_config(env, templates, "bindings.lua")
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS  # the damage

    proc = _apply(env, repo)
    assert proc.returncode == 0, proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == committed
    assert "stock template" in proc.stderr
    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert live.is_symlink() and live.read_text() == committed


def test_a_clobber_is_still_repaired_after_omarchy_ships_a_new_template(tmp_path: Path) -> None:
    """`cmp` against the INSTALLED template alone stops recognising a clobber the
    moment Omarchy ships that file's next version — and omarchy-update
    upgrades the package BEFORE running the hook (4.0.3-1) — so the installer
    caches the last template it saw and accepts that one too."""
    env, repo, templates = _guard_env(tmp_path, git=GIT_PASSTHROUGH)
    committed = (repo / "hypr" / "bindings.lua").read_text()
    assert _apply(env, repo).returncode == 0

    _refresh_config(env, templates, "bindings.lua")  # the damage, at template A
    bumped = STOCK_BINDINGS + "-- Omarchy 4.1 says something new here.\n"
    (templates / "bindings.lua").write_text(bumped)  # the package upgrade

    proc = _apply(env, repo)
    assert proc.returncode == 0, proc.stderr
    assert "stock template" in proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == committed
    # And the cache moved on with Omarchy, so the next bump is covered too.
    cached = env["home"] / ".local" / "state" / "hyprconf" / "stock" / "bindings.lua"
    assert cached.read_text() == bumped


def test_a_cache_the_installer_cannot_write_warns_and_the_run_goes_on(tmp_path: Path) -> None:
    """The stock cache is an optimisation for the NEXT template bump, so it warns
    and carries on like every other state write. Unguarded under `set -e` its
    `mkdir -p` failure killed the whole run at the first hypr override — no
    hooks, no plugins, no clock, on every post-update run from then on."""
    env, repo, templates = _guard_env(tmp_path, git=GIT_PASSTHROUGH)
    committed = (repo / "hypr" / "bindings.lua").read_text()
    stock_dir = env["home"] / ".local" / "state" / "hyprconf" / "stock"
    stock_dir.parent.mkdir(parents=True, exist_ok=True)
    stock_dir.write_text("not a directory\n")  # mkdir -p fails here for root too
    assert _apply(env, repo).returncode == 0

    _refresh_config(env, templates, "bindings.lua")
    proc = _apply(env, repo)
    assert proc.returncode == 0, proc.stderr
    assert "WARNING:" in proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == committed
    assert stock_dir.read_text() == "not a directory\n"
    assert "omarchy-hook-install" in _commands(env)  # the stages after it still ran


def test_a_clobber_git_cannot_undo_is_reported_as_unrepaired_after_a_bump(
    tmp_path: Path,
) -> None:
    """The guard's two messages must stay honest: it says it restored the file
    only when the file changed. A clobber the user committed is one git
    checkout cannot undo, and the cached template still recognises it."""
    env, repo, templates = _guard_env(tmp_path, git=GIT_PASSTHROUGH)
    assert _apply(env, repo).returncode == 0

    _refresh_config(env, templates, "bindings.lua")  # the damage, at template A
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "oops"], check=True, timeout=30)
    (templates / "bindings.lua").write_text(STOCK_BINDINGS + "-- 4.1\n")  # the package upgrade

    proc = _apply(env, repo)
    assert proc.returncode == 0, proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS  # still clobbered
    assert "could not be" in proc.stderr and "restored it from git" not in proc.stderr


def test_a_real_edit_survives_a_template_bump(tmp_path: Path) -> None:
    """The guard keys on byte-identity with a stock template and nothing else, and
    the cache only ever ADDS a set of Omarchy bytes to recognise: an edit made
    through the symlink is the user editing their own dotfiles."""
    env, repo, templates = _guard_env(tmp_path, git=GIT_PASSTHROUGH)
    assert _apply(env, repo).returncode == 0

    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    edited = live.read_text() + '\no.bind("SUPER + SHIFT + R", "SSH", "kitty -e ssh box")\n'
    live.write_text(edited)  # through the symlink, like an editor would
    (templates / "bindings.lua").write_text(STOCK_BINDINGS + "-- 4.1\n")

    proc = _apply(env, repo)
    assert proc.returncode == 0, proc.stderr
    assert "stock template" not in proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == edited


def test_guard_reports_when_git_cannot_repair(tmp_path: Path) -> None:
    """No git to restore from (a checkout without .git — a zip download): the
    clobber is still reported, and the run still completes."""
    env, repo, templates = _guard_env(tmp_path)  # git is the no-op stub
    assert _apply(env, repo).returncode == 0
    _refresh_config(env, templates, "bindings.lua")

    proc = _apply(env, repo)
    assert proc.returncode == 0, proc.stderr
    assert "could not be restored" in proc.stderr
    assert (repo / "hypr" / "bindings.lua").read_text() == STOCK_BINDINGS


# The overrides install.sh links into ~/.config/hypr, read from its own
# link_hypr_override call sites — the set stage_pull has to repair before it
# pulls, and the whole point of deriving that set rather than re-listing it.
LINKED_OVERRIDES = tuple(
    sorted(
        set(re.findall(r"^\s*link_hypr_override\s+(\S+\.lua)\s*$", INSTALL_SH.read_text(), re.M))
    )
)


def test_every_linked_hypr_override_ships_in_the_checkout() -> None:
    """`ln -sfn` on a source the checkout does not ship makes a DANGLING link and
    stage_pull then skips it silently, so every file link_hypr_override points
    at has to be one of hypr/*.lua."""
    assert LINKED_OVERRIDES, "the link_hypr_override scan found nothing"
    for name in LINKED_OVERRIDES:
        assert (REPO_ROOT / "hypr" / name).is_file(), name


def test_sync_repairs_any_clobbered_override_before_it_pulls(tmp_path: Path) -> None:
    """A clobbered override is a dirty tracked file, and `git pull --ff-only`
    refuses to merge over one upstream also changed — so hyprsync after a
    refresh died on the pull until stage_pull ran the guard first, over a set
    derived from "$HERE"/hypr/*.lua. An UNTRACKED look-alike stays a no-op."""
    env = _setup(tmp_path)
    up = _checkout(tmp_path)
    (up / "hypr" / "autostart.lua").write_text('hl.exec_once("waybar")\n')
    subprocess.run(["git", "-C", str(up), "add", "-A"], check=True, timeout=30)
    subprocess.run(["git", "-C", str(up), "commit", "-qm", "four"], check=True, timeout=30)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(up), str(clone)], check=True, timeout=30)
    git_with_pull = GIT_PASSTHROUGH.replace('case " $* " in *" pull "*) exit 0 ;; esac\n', "")
    assert git_with_pull != GIT_PASSTHROUGH, "the pull short-circuit moved"
    _stub(env["bins"] / "git", env["calls"], git_with_pull)
    templates = _stock_templates(env)
    stock = "-- Omarchy's own autostart.lua\n"
    (templates / "autostart.lua").write_text(stock)
    assert _apply(env, clone).returncode == 0

    # What `omarchy refresh` leaves behind: the checkout's copy IS Omarchy's
    # template — for a linked override, through the symlink; for autostart.lua,
    # which nothing links yet, written straight into the clone.
    _refresh_config(env, templates, "bindings.lua")
    (clone / "hypr" / "autostart.lua").write_text(stock)
    # And an untracked look-alike beside it, which must stay a silent no-op.
    (templates / "spare.lua").write_text(stock)
    (clone / "hypr" / "spare.lua").write_text(stock)

    moved = {
        "bindings.lua": (up / "hypr" / "bindings.lua").read_text() + "\n-- upstream moved\n",
        "autostart.lua": 'hl.exec_once("waybar")\n-- upstream moved\n',
    }
    for name, body in moved.items():
        (up / "hypr" / name).write_text(body)
    subprocess.run(["git", "-C", str(up), "commit", "-qam", "five"], check=True, timeout=30)

    proc = _apply(env, clone, "--sync")
    assert proc.returncode == 0, proc.stderr
    assert "restored it from git" in proc.stderr and "hypr/autostart.lua" in proc.stderr
    for name, body in moved.items():
        assert (clone / "hypr" / name).read_text() == body, name
    # The repaired link is re-pointed at the restored file, not left dangling.
    live = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert live.is_symlink() and live.read_text() == moved["bindings.lua"]
    assert "omarchy-update" in _commands(env)  # the pull did not stop the sync
    assert "spare.lua" not in proc.stderr
    assert (clone / "hypr" / "spare.lua").read_text() == stock


# ---------------------------------------------------------------------------
# The curl path — `bash <(curl -fsSL --proto '=https' https://hyprconf.sh)` serves install.sh alone
# ---------------------------------------------------------------------------


def _served_copy(tmp_path: Path) -> Path:
    """install.sh alone, the way hyprconf.sh serves it to curl: no payload beside it."""
    served = tmp_path / "served"
    served.mkdir()
    shutil.copy2(INSTALL_SH, served / "install.sh")
    return served / "install.sh"


def _stable_checkout(tmp_path: Path) -> Path:
    """_checkout on `stable`, the branch the curl path clones by default."""
    repo = _checkout(tmp_path)
    subprocess.run(["git", "branch", "-M", "stable"], cwd=repo, check=True, timeout=30)
    return repo


def test_curl_path_clones_the_checkout_and_hands_over_to_it(tmp_path: Path) -> None:
    """Run with nothing beside it, install.sh clones HYPRCONF_REPO (branch stable,
    single-branch) into HYPRCONF_DIR and execs that checkout's own copy with
    the same arguments — which then applies every stage from the checkout."""
    env = _setup(tmp_path)
    repo = _stable_checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    target = tmp_path / "hyprconf-dir"
    proc = _run(
        env,
        "--no-update",
        extra_env={"HYPRCONF_REPO": str(repo), "HYPRCONF_DIR": str(target)},
        install_sh=_served_copy(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert f"git clone --branch stable --single-branch {repo} {target}" in _calls(env)
    assert (target / ".git").is_dir()
    for name in PAYLOAD:
        assert (target / name).exists(), name
    # The stages ran, from the checkout: the tools and hooks resolve to it and
    # the override links point into it.
    assert "omarchy-default-terminal kitty" in _calls(env)
    assert "omarchy-pkg-add" in _commands(env)
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    assert f'HYPRCONF_DIR="{target}"' in hook.read_text()
    bindings = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert Path(os.readlink(bindings)) == target / "hypr" / "bindings.lua"
    assert (env["home"] / ".zshrc").exists()
    assert "omarchy-update" not in _commands(env)


def test_curl_path_refuses_a_box_without_omarchy_before_cloning(tmp_path: Path) -> None:
    """Preflight runs BEFORE the clone: a machine that is not Omarchy gets the
    refusal and nothing else — no checkout lands on it."""
    env = _setup(tmp_path)
    repo = _stable_checkout(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    target = tmp_path / "hyprconf-dir"
    proc = _run(
        env,
        extra_env={
            "HYPRCONF_REPO": str(repo),
            "HYPRCONF_DIR": str(target),
            "_HYPRCONF_PKG_ADD": "omarchy-pkg-add-absent",
        },
        install_sh=_served_copy(tmp_path),
    )
    assert proc.returncode != 0
    assert "omarchy" in proc.stderr.lower()
    assert not target.exists()
    assert not any(c.startswith("git clone") for c in _calls(env))
    assert not (env["home"] / ".zshrc").exists()


def test_curl_path_reuses_an_existing_checkout_without_pulling(tmp_path: Path) -> None:
    """A checkout already at HYPRCONF_DIR is used as it is: no clone over it,
    and no pull either — updating it is --sync's job, not the bootstrap's."""
    env = _setup(tmp_path)
    repo = _stable_checkout(tmp_path)
    git = ["git", "-C", str(repo)]
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    proc = _run(
        env,
        "--no-update",
        extra_env={"HYPRCONF_REPO": str(tmp_path / "never-cloned"), "HYPRCONF_DIR": str(repo)},
        install_sh=_served_copy(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr
    assert not any(c.startswith("git clone") and c.endswith(f" {repo}") for c in _calls(env))
    assert not any(" pull " in f" {c} " for c in _calls(env))
    assert not (tmp_path / "never-cloned").exists()
    after = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    assert after.stdout == head.stdout
    status = subprocess.run([*git, "status", "--porcelain"], capture_output=True, text=True)
    assert status.stdout == ""
    # …and the stages ran from that checkout.
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    assert f'HYPRCONF_DIR="{repo}"' in hook.read_text()


def test_curl_path_help_and_bad_options_never_clone(tmp_path: Path) -> None:
    """The option loop runs before the hand-over, so --help (and a typo) answer
    from the served copy without touching the machine."""
    env = _setup(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PASSTHROUGH)
    target = tmp_path / "hyprconf-dir"
    served = _served_copy(tmp_path)
    proc = _run(env, "--help", extra_env={"HYPRCONF_DIR": str(target)}, install_sh=served)
    assert proc.returncode == 0
    assert "bash <(curl -fsSL --proto '=https' https://hyprconf.sh)" in proc.stdout
    assert "HYPRCONF_REPO" in proc.stdout
    proc = _run(env, "--bogus", extra_env={"HYPRCONF_DIR": str(target)}, install_sh=served)
    assert proc.returncode != 0
    assert not target.exists()
    assert _calls(env) == []


def test_shell_third_party_repos_are_pinned_and_never_pulled(tmp_path: Path) -> None:
    """Oh My Zsh and powerlevel10k execute in every interactive zsh, so they stay
    at the reviewed pins: the per-apply `git pull` this replaces was a silent
    auto-update channel from two upstream HEADs into every box on every
    omarchy-update. A dir at another commit is moved to the pin."""
    pins = dict(re.findall(r"local (omz_pin|p10k_pin)=([0-9a-f]{40})", INSTALL_SH.read_text()))
    assert set(pins) == {"omz_pin", "p10k_pin"}, "stage_shell must name both pins"
    env = _setup(tmp_path)
    _stub(env["bins"] / "git", env["calls"], GIT_PIN_DANCE)
    _run(env, "--no-update")
    omz = env["home"] / ".oh-my-zsh"
    p10k = omz / "custom" / "themes" / "powerlevel10k"
    assert (omz / ".fake-head").read_text() == pins["omz_pin"]
    assert (p10k / ".fake-head").read_text() == pins["p10k_pin"]
    assert not any(" pull " in f" {c} " for c in _calls(env))
    # the migration: a checkout left at any other commit moves to the pin
    (p10k / ".fake-head").write_text("0" * 40)
    _run(env, "--no-update")
    assert (p10k / ".fake-head").read_text() == pins["p10k_pin"]
    # an offline box mid-migration keeps the usable checkout AND the stage
    # tail: .zshrc must not be held hostage by an unreachable pin
    (p10k / ".fake-head").write_text("1" * 40)
    (p10k / ".fail-fetch").write_text("")
    (env["home"] / ".zshrc").unlink()
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    assert (p10k / ".fake-head").read_text() == "1" * 40  # unpinned, but in use
    assert "WARNING:" in proc.stderr
    assert (env["home"] / ".zshrc").exists()  # the tail still ran


def test_refuses_to_run_as_root() -> None:
    """curl|bash users reflexively prefix sudo; under env_reset that
    half-installs the overlay into /root. Pinned as text, not run: the suite
    is unprivileged everywhere now (CI included), and there is no seam left
    to make the branch reachable — which is the point, since the seam was
    itself a way past the guard."""
    code = _code_only(INSTALL_SH.read_text())
    assert re.search(r"if \(\(EUID == 0\)\); then", code)
    assert "run as your regular user" in code
