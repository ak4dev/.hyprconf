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

from conftest import OMARCHY_TREE

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO_ROOT / "install.sh"
HOOK = REPO_ROOT / "hooks" / "post-update.d" / "10-hyprconf"

# A recording stub: appends its own name + args to the calls log, then runs an
# optional body. One template covers every external the installer touches.
STUB = """#!/usr/bin/env bash
printf '%s\\n' "${{0##*/}} $*" >> "{calls}"
{body}
"""


# omarchy-hook-install <type> <file> (4.0.0-1): mkdir -p the .d dir, cp under
# the file's basename, chmod 755 — reproduced so later stages find the hook.
HOOK_INSTALL = (
    'd="$HOME/.config/omarchy/hooks/$1.d"; mkdir -p "$d"; cp "$2" "$d/${2##*/}"; '
    'chmod 755 "$d/${2##*/}"'
)


def _stub(path: Path, calls: Path, body: str = "exit 0") -> None:
    path.write_text(STUB.format(calls=calls, body=body))
    path.chmod(0o755)


# /usr/bin/omarchy-shell-config (Omarchy 4.0.3-1), transcribed: the hidden
# helper modules/idle SOURCES to edit ~/.config/omarchy/shell.json — which a
# full install.sh run reaches, and modules/bar-clock then reads. Written out
# instead of stubbed for two reasons — the recording stub's closing `exit 0` would end
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


def _default_app_stub(tmp_path: Path, key: str, unset: str) -> str:
    """omarchy-default-browser / -editor: reports `unset` until something sets
    it, then what was set — the value modules/firefox and modules/vscode read
    back instead of trusting the setter's exit status. Those two modules own
    the set-once contract and its failure modes; this is the working setter a
    full install.sh run needs."""
    return (
        f'if [ $# -eq 0 ]; then cat "{tmp_path}/{key}" 2>/dev/null || echo {unset};'
        f' else printf "%s" "$1" > "{tmp_path}/{key}"; fi'
    )


# The externals _setup fakes with the bare recording stub. The conditional
# and bodied ones are written individually in _setup below;
# test_every_omarchy_command_install_sh_calls_has_a_fake holds install.sh to
# the union, which it reads off the fake directory rather than this list.
OMARCHY_STUBS = (
    "omarchy-theme-set",
    # modules/firefox-theme re-renders the current theme through it; the real
    # one would re-set the developer's own theme from a test run.
    "omarchy-theme-refresh",
    "omarchy-cmd-present",
    "omarchy-default-terminal",
    "omarchy-font-set",
    "omarchy-shell",
    "omarchy-plugin-enable",
    "omarchy-bar",
    "omarchy-update",
    # Firefox and VS Code go in through Omarchy's own installers.
    "omarchy-install-browser",
    "omarchy-install-editor-vscode",
    "sudo",
    # modules/hypr reloads Hyprland once its copies land; the real one would
    # reload the developer's own compositor from a test run.
    "hyprctl",
    # Asserted never to run: pacman directly (the container has a real
    # one; a call must be seen, not reach it).
    "pacman",
    # modules/keychron reloads and retriggers udev; the real one would
    # re-apply rules on the developer's own machine.
    "udevadm",
)


# The two shell writes the box models rather than records — what
# modules/bar-clock polls shell.json for after asking for them. An enable
# swaps a clonedFrom copy into the stock widget's slot
# (shell/services/PluginRegistry.qml:529-534, Omarchy 4.0.3-1) and
# `omarchy bar set` writes one key onto a layout entry (bin/omarchy-bar:178
# is the id rule: a bare string or an object with an id).
ENTRY_ID = 'if type == "object" then .id else . end'
SHELL_ENABLE_SWAP = f"""\
json="$HOME/.config/omarchy/shell.json"
[ -f "$json" ] || exit 0
src=$(jq -r '.omarchy.clonedFrom // empty' \
  "$HOME/.config/omarchy/plugins/$1/manifest.json" 2>/dev/null) || exit 0
[ -n "$src" ] || exit 0
jq --arg from "$src" --arg to "$1" '
  .bar.layout |= with_entries(.value |= map(
    if ({ENTRY_ID}) == $from
    then (if type == "object" then .id = $to else {{ id: $to }} end)
    else . end))' "$json" > "$json.n" && mv "$json.n" "$json"
"""
SHELL_BAR_SET = f"""\
[ "$1" = set ] || exit 0
json="$HOME/.config/omarchy/shell.json"
[ -f "$json" ] || exit 1
jq --arg id "$2" --arg k "$3" --arg v "$4" '
  .bar.layout |= with_entries(.value |= map(
    if ({ENTRY_ID}) == $id
    then (if type == "object" then . else {{ id: . }} end) + {{ ($k): $v }}
    else . end))' "$json" > "$json.n" && mv "$json.n" "$json"
"""


def _setup(tmp_path: Path) -> dict:
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
    # No shell answering the plugin list is what a TTY or SSH run really finds
    # (omarchy-plugin-list is `set -e` over an IPC call that exits 1 the moment
    # omarchy-shell reports "is not running"), so a discovery wait has nothing
    # to wait for; the enable itself is modelled as answering, below.
    _stub(bins / "omarchy-plugin-list", calls, "exit 1")
    # jq is a hard dependency of the JSON stages and of modules/bar-clock's
    # own polls — the box gets the real one behind the recording stub, and a
    # machine without it skips instead of pretending.
    jq = shutil.which("jq")
    if jq is None:
        pytest.skip("no jq available")
    _stub(bins / "jq", calls, f'exec {jq} "$@"')
    # The live shell's two writes modules/bar-clock waits for: an enable swaps
    # the clone into the slot of the id its manifest was cloned from, and
    # `omarchy-bar set` writes the key onto that entry.
    _stub(bins / "omarchy-plugin-enable", calls, SHELL_ENABLE_SWAP)
    _stub(bins / "omarchy-bar", calls, SHELL_BAR_SET)
    # Omarchy's package probe (pacman -Q per name): everything present unless
    # a test says otherwise, so the steady-state box is the default and each
    # install flow is opted into.
    _stub(bins / "omarchy-pkg-present", calls)
    _stub(bins / "omarchy-hook-install", calls, HOOK_INSTALL)
    # Sourced, not run (see SHELL_CONFIG_FAKE) — hence the direct write.
    shell_config = bins / "omarchy-shell-config"
    shell_config.write_text(SHELL_CONFIG_FAKE.replace("__CALLS__", str(calls)))
    shell_config.chmod(0o755)
    # Read back by modules/firefox and modules/vscode; the unset answers are
    # Omarchy's own (editor falls back to "nvim", bin/omarchy-default-editor:14,
    # and the browser reports whatever xdg-settings says — Omarchy's chromium).
    _stub(
        bins / "omarchy-default-browser", calls, _default_app_stub(tmp_path, "browser", "chromium")
    )
    _stub(bins / "omarchy-default-editor", calls, _default_app_stub(tmp_path, "editor", "nvim"))
    # `clone` must materialise a directory; everything else is a no-op.
    _stub(bins / "git", calls, 'if [ "$1" = clone ]; then mkdir -p "${@: -1}"; fi; exit 0')

    # Seed the parts of a fresh Omarchy $HOME the installer interacts with:
    # Omarchy's three stock override files, which modules/hypr copies over.
    (home / ".config" / "hypr").mkdir(parents=True)
    for stock in ("bindings.lua", "input.lua", "looknfeel.lua"):
        (home / ".config" / "hypr" / stock).write_text(f"-- stock omarchy {stock}\n")
    # A live box's own ~/.config/omarchy/shell.json: the bar layout and the
    # centre anchor modules/bar-clock reads and the shell rewrites.
    (home / ".config" / "omarchy").mkdir(parents=True, exist_ok=True)
    (home / ".config" / "omarchy" / "shell.json").write_text(
        json.dumps(
            {
                "version": 1,
                "bar": {
                    "centerAnchor": "omarchy.clock",
                    "layout": {"left": [], "center": [{"id": "omarchy.clock"}], "right": []},
                },
            }
        )
    )
    # Omarchy's shipped shell.json defaults — what omarchy-shell-config's
    # source_file() starts from when the user has no shell.json yet.
    (omarchy_path / "config" / "omarchy").mkdir(parents=True)
    (omarchy_path / "config" / "omarchy" / "shell.json").write_text(
        json.dumps({"version": 1, "idle": {"lock": 300, "screensaver": 150}})
    )
    # Omarchy's kitty stub: the file modules/{shell-zsh,terminal-kitty} seed
    # an absent ~/.config/kitty/kitty.conf from, since the theme include lives
    # only there (config/kitty/kitty.conf:1-2, 4.0.3-1). Without it a full run
    # takes the degraded branch and the box stops modelling a real Omarchy.
    (omarchy_path / "config" / "kitty").mkdir(parents=True)
    (omarchy_path / "config" / "kitty" / "kitty.conf").write_text(
        OMARCHY_TREE["config/kitty/kitty.conf"]
    )
    # Omarchy's Firefox prefs — what modules/firefox merges under its own.
    # The stand-in is conftest's, the one the module's own suite drift-checks
    # against the installed file.
    (omarchy_path / "default" / "firefox").mkdir(parents=True)
    (omarchy_path / "default" / "firefox" / "policies.json").write_text(
        OMARCHY_TREE["default/firefox/policies.json"]
    )

    env = {
        "home": home,
        "bins": bins,
        "omarchy_path": omarchy_path,
        "calls": calls,
        "udev_rules": tmp_path / "etc" / "udev" / "rules.d",
        "firefox_policies": tmp_path / "etc" / "firefox" / "policies",
    }
    return env


def _install_env(env: dict, *, extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """The environment install.sh runs in against the fake tree: _child_env
    plus every seam pinned at a fake. What _run passes — and what the
    installed post-update hook, which execs install.sh, is run under."""
    child_env = {
        **_child_env(env),
        "OMARCHY_PATH": str(env["omarchy_path"]),
        # The two module seams that name a root-owned path, pinned on every
        # run because main() calls both modules: a test that makes sudo real
        # would otherwise write into the CI container's own /etc, and a plain
        # run would read the developer's /etc/firefox to decide.
        "_HYPRCONF_UDEV_RULES": str(env["udev_rules"]),
        "_HYPRCONF_FIREFOX_POLICIES": str(env["firefox_policies"]),
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
# module and the hook from a throwaway copy of the checkout.
PAYLOAD = (
    "install.sh",
    "modules",
    "hooks",
)

# Real git for a clone of a LOCAL directory (the throwaway checkout under
# tmp_path, which is how the curl path is exercised); a clone of a URL only
# makes the directory, and a pull is a no-op.
GIT_PASSTHROUGH = """\
if [ "$1" = clone ]; then
  src="${@: -2:1}"
  if [ -d "$src" ]; then exec "$(PATH=/usr/bin:/bin command -v git)" "$@"; fi
  mkdir -p "${@: -1}"; exit 0
fi
case " $* " in *" pull "*) exit 0 ;; esac
exec "$(PATH=/usr/bin:/bin command -v git)" "$@"
"""


def _checkout(tmp_path: Path) -> Path:
    """A throwaway git checkout of the overlay payload — what the curl-path
    tests clone and run from, never the repository the suite runs in."""
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


MODULES = REPO_ROOT / "modules"


@pytest.mark.parametrize(
    "order",
    [("shell-zsh", "terminal-kitty"), ("terminal-kitty", "shell-zsh")],
    ids=["loop-order", "reversed"],
)
def test_the_two_kitty_includes_are_order_free(box, order) -> None:
    """main()'s module loop is alphabetical, so shell-zsh runs BEFORE
    terminal-kitty — and both write ~/.config/kitty/kitty.conf. Neither may
    depend on that: both seed an absent file from Omarchy's own stub (the theme
    include lives only there, config/kitty/kitty.conf:1-2) and both guard only
    their own line, so either order ends with the stub plus exactly one of each
    include — and undoing both puts Omarchy's stub back byte for byte."""
    conf = box.home / ".config" / "kitty" / "kitty.conf"
    stub = (box.omarchy / "config" / "kitty" / "kitty.conf").read_text()

    for _ in range(2):  # and a re-run of either adds nothing
        for name in order:
            proc = box.run(MODULES / name / "install")
            assert proc.returncode == 0, f"{name}: {proc.stderr}"

    text = conf.read_text()
    assert text.startswith(stub), text
    assert text.count("include hyprconf.conf\n") == 1, text
    assert text.count("include hyprconf-zsh.conf\n") == 1, text
    assert sorted(text[len(stub) :].splitlines()) == [
        "# hyprconf overlay",
        "include hyprconf-zsh.conf",
        "include hyprconf.conf",
    ], text

    for name in reversed(order):
        assert box.undo(name).returncode == 0
    assert conf.read_text() == stub


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
    "jq",
    "omarchy-hook-install",  # Omarchy's own idempotent mkdir/cp/chmod
    "omarchy-pkg-present",  # every module's own `pacman -Q` probe
    # modules/bar-* install their plugin folder as a SYMLINK, and the shell's
    # inotifywait -r never descends one (PluginRegistry.qml:663-667), so the
    # rescan is what picks a `git pull` up and repeats on every run by design.
    # Pure IPC: it changes nothing on disk.
    "omarchy-shell",
}


def test_full_run_succeeds_and_is_byte_stable(tmp_path: Path) -> None:
    """Every stage on its real path, with the whole HOME in the hash: the real jq
    behind the JSON stages, a sudo that runs its command and a terminal to ask
    on, and ~/.local/bin on PATH the way default/bash/envs:32-33 (4.0.3-1)
    puts it there. The second run is byte-identical, warning-free, and calls
    nothing outside SETTLED_RERUN_COMMANDS."""
    env = _setup(tmp_path)
    _real_jq(env)
    # A sudo that really runs its argument list, so every module's root write
    # lands in the box's own /etc (the two seams _install_env pins) instead of
    # being merely recorded — the byte-stability of those files is theirs.
    _stub(env["bins"] / "sudo", env["calls"], '"$@"')
    extra = {
        "_HYPRCONF_ASSUME_TTY": "1",
        "PATH": f"{env['bins']}:{env['home']}/.local/bin:/usr/bin:/bin",
    }
    first = _run(env, "--no-update", extra_env=extra)
    assert first.returncode == 0, first.stderr

    after_first = _tree_hash(env["home"])
    env["calls"].write_text("")
    second = _run(env, "--no-update", extra_env=extra)
    assert second.returncode == 0, second.stderr

    assert _tree_hash(env["home"]) == after_first
    assert "WARNING:" not in second.stderr, second.stderr
    assert set(_commands(env)) <= SETTLED_RERUN_COMMANDS, set(_commands(env))


# ---------------------------------------------------------------------------
# Restraint — what the installer must never do
# ---------------------------------------------------------------------------


def test_never_switches_the_active_theme() -> None:
    """install.sh never takes the active theme away — the overlay re-applies
    itself after every Omarchy update, and the theme it ships is installed
    from modules/themes, never activated (that module's own copy of this
    assertion is test_installing_never_activates_a_theme). Scanned rather than
    run, which covers every branch instead of the one a run takes."""
    code = _code_only(INSTALL_SH.read_text())
    assert "omarchy-theme-set" not in re.findall(r"\bomarchy-[a-z0-9-]+\b", code)


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
    assert "omarchy-shell" not in _commands(env)  # the module loop never started
    assert "omarchy-hook-install" not in _commands(env)  # nor the stages after it
    assert not (env["home"] / ".zshrc").exists()


def test_unknown_flag_is_rejected(tmp_path: Path) -> None:
    env = _setup(tmp_path)
    proc = _run(env, "--definitely-not-a-flag")
    assert proc.returncode != 0
    assert not (env["home"] / ".zshrc").exists()


# ---------------------------------------------------------------------------
# The hooks
# ---------------------------------------------------------------------------


def test_hooks_are_installed_through_omarchy_hook_install(tmp_path: Path) -> None:
    """omarchy-update runs post-update.d/* and omarchy-theme-set ends with
    `omarchy-hook theme-set <name>`. A full run installs one of each, through
    Omarchy's own `omarchy-hook-install <type> <file>` (4.0.3-1: mkdir -p, cp,
    chmod 755) and under the file's final basename, which is the name it is
    installed as. Only install.sh's own hook is RENDERED — @HYPRCONF_DIR@
    resolved to the checkout; modules/firefox-theme's theme-set hook carries
    no checkout path at all, which is what lets it run from a copy."""
    env = _setup(tmp_path)
    _run(env, "--no-update")
    hooks = env["home"] / ".config" / "omarchy" / "hooks"
    installs = [c for c in _calls(env) if c.startswith("omarchy-hook-install ")]
    assert sorted(c.split()[1] for c in installs) == ["post-update", "theme-set"]
    for name in ("post-update", "theme-set"):
        call = next(c for c in installs if c.split()[1] == name)
        assert call.split()[2].endswith("/10-hyprconf"), call  # installed under its basename
        installed = hooks / f"{name}.d" / "10-hyprconf"
        assert "@HYPRCONF_DIR@" not in installed.read_text(), name
        assert os.access(installed, os.X_OK), name
    post_update = (hooks / "post-update.d" / "10-hyprconf").read_text()
    assert str(REPO_ROOT) in post_update


def _run_hook(env: dict, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """The installed post-update hook run the way omarchy-hook runs it — `bash
    <hook>` (bin/omarchy-hook:26, 4.0.3-1) — under install.sh's own pinned
    environment, with a terminal: the hook's flags, not a missing tty, must be
    what keeps the modules' sudo work out."""
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
    bindings.write_text("-- a migration put the stock file back\n")
    env["calls"].write_text("")
    proc = _run_hook(env)
    assert proc.returncode == 0, proc.stderr
    # The overlay was re-applied: modules/hypr's copy is back, as a file.
    assert not bindings.is_symlink()
    assert bindings.read_bytes() == (MODULES / "hypr" / "bindings.lua").read_bytes()
    commands = _commands(env)
    # …and so was the module loop: every bar-* module asks the shell for a
    # rescan on every run, since inotify never descends their symlinked folder.
    assert "omarchy-shell" in commands
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


# ---------------------------------------------------------------------------
# Static scans over the whole overlay tree
# ---------------------------------------------------------------------------


def _overlay_scripts() -> list[Path]:
    """Every shell script the overlay ships: the PAYLOAD trees filtered by a bash
    shebang, the rule `make shellcheck` selects by. Walked on disk, not `git
    ls-files`, so the scan needs no git and no ownership trust; scripts/publish
    is outside PAYLOAD and covered by the Makefile's whole-tree pass. modules/
    is walked by _module_scripts() instead, so the header rule below covers it
    while the forbidden-forms scans stay off it: those read strings as well as
    code, and a module's own prose ("see pacman's error above") is not a call.
    The whole set moves to tests/test_scans.py with the core rewrite — a few
    modules pin their own half meanwhile (modules/idle the script shape,
    modules/vscode the pacman ban, modules/keychron the root-write `--`)."""
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


def _module_scripts() -> list[Path]:
    """Every bash script under modules/: each `install`, the `bin/` tools a
    module links onto PATH, and the hook one hands to `omarchy hook install`.
    A per-module suite cannot pin a tree-wide rule — one module cannot know
    what the others do — so the header check below is their one home too
    (vulkan.0#19)."""
    scripts = []
    for p in sorted((REPO_ROOT / "modules").rglob("*")):
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
    "hook": "set -uo pipefail",  # modules/firefox-theme's theme-set hook
    "hyprconf-stats": "set -u",
}


@pytest.mark.parametrize(
    "script",
    _overlay_scripts() + _module_scripts(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
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
# call. Dropped for this scan only.
USAGE_HEREDOC = re.compile(r"(?ms)^\s*cat <<'USAGE'\n.*?^USAGE$")


def _fetch_exec_surface() -> list[Path]:
    """_overlay_scripts() plus the shipped shell payload its suffix filter
    misses — the rc file and p10k config every interactive zsh executes, which
    modules/shell-zsh ships. The scan must reach everything that runs."""
    zsh = REPO_ROOT / "modules" / "shell-zsh"
    return _overlay_scripts() + [zsh / "zshrc", zsh / ".p10k.zsh"]


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
    """A line starting with '-' would reach a module's sudo `omarchy-pkg-add`
    as an option, not a package. One rule over every module's own file — the
    root `packages` list is gone with stage_packages — and each line may carry
    a trailing `# why`, which comes off the way each `install` takes it off."""
    files = sorted((REPO_ROOT / "modules").glob("*/packages"))
    assert files, "no module packages file found — the scan is broken"
    for path in files:
        for ln in path.read_text().splitlines():
            ln = ln.split("#", 1)[0].strip()
            if not ln:
                continue
            assert re.fullmatch(r"[a-z0-9][a-z0-9@._+-]*", ln), f"{path.parent.name}: {ln!r}"


def test_overlay_never_uses_the_dead_hyprctl_forms() -> None:
    """`hyprctl keyword` and a two-token `hyprctl dispatch dpms on` are both
    dead under Hyprland 0.56's Lua parser; the working forms are `hyprctl eval`
    and `hyprctl dispatch 'hl.dsp.…'` (AGENTS.md › Known quirks). Over the
    modules too — the two hotkey tools that make these calls ship in
    modules/hypr/bin — since this scan reads code only and its patterns match
    no prose."""
    dead = re.compile(
        r"hyprctl\s+(--batch\s+)?[\"']?keyword\b|hyprctl\s+dispatch\s+[a-z_]+\s+[a-z_]+"
    )
    offenders = [
        f"{script.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}"
        for script in _overlay_scripts() + _module_scripts()
        for lineno, line in enumerate(_code_only(script.read_text(errors="ignore")).splitlines(), 1)
        if dead.search(line)
    ]
    assert not offenders, "use hyprctl eval / hyprctl dispatch 'hl.dsp.…':\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# The sudo gate, across the whole run
# ---------------------------------------------------------------------------


def test_every_sudo_stage_bows_out_without_a_terminal(tmp_path: Path) -> None:
    """The post-update hook runs non-interactively inside omarchy-update, where
    a sudo password prompt would stall the whole update. install.sh itself asks
    for no sudo at all now; every module carries its own gate, and this is the
    one place all of them are held to it in a single real run. The per-module
    contracts are modules/{firefox,keychron,vscode,font,terminal-kitty,
    shell-zsh}/test_*.py."""
    env = _setup(tmp_path)
    _real_jq(env)  # else modules/firefox bows out on the merge, before its gate
    _packages(env, ())
    proc = _run(env, "--no-update")
    assert proc.returncode == 0, proc.stderr
    for forbidden in (
        "sudo",
        "udevadm",
        "omarchy-install-browser",
        "omarchy-install-editor-vscode",
    ):
        assert forbidden not in _commands(env), forbidden
    assert not (env["firefox_policies"] / "policies.json").exists()


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


def test_the_installer_itself_lands_on_path_as_hyprconf(tmp_path: Path) -> None:
    """`hyprconf --sync` is what modules/shell-zsh's `hyprsync` alias runs,
    `hyprconf <module>` the re-apply after an edit, and what the post-update
    hook will exec once the core rewrite lands. A SYMLINK, so a `git pull` in
    the checkout is the update and no checkout path is baked into the alias —
    the alias names the link, which is what lets the checkout move."""
    env = _setup(tmp_path)
    for _ in range(2):  # re-pointed in place, never stacked
        assert _run(env, "--no-update").returncode == 0
    link = env["home"] / ".local" / "bin" / "hyprconf"
    assert link.is_symlink()
    assert Path(os.readlink(link)) == INSTALL_SH


def test_a_module_named_on_the_command_line_runs_alone(tmp_path: Path) -> None:
    """`hyprconf hypr` is the re-apply after an edit to that module's files:
    only the modules named run (plus the link and the hook, both idempotent),
    and a name that is not a module dies before anything runs."""
    env = _setup(tmp_path)
    proc = _run(env, "--no-update", "hypr")
    assert proc.returncode == 0, proc.stderr
    bindings = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert bindings.read_bytes() == (MODULES / "hypr" / "bindings.lua").read_bytes()
    assert set(_commands(env)) == {"hyprctl", "omarchy-hook-install"}, _commands(env)
    assert not (env["home"] / ".zshrc").exists()  # modules/shell-zsh did not run

    env = _setup(tmp_path / "unknown")
    proc = _run(env, "--no-update", "hypr", "no-such-module")
    assert proc.returncode != 0
    assert "no module named no-such-module" in proc.stderr
    assert _calls(env) == []
    assert not (env["home"] / ".config" / "omarchy" / "hooks").exists()


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
    # The modules ran, from the checkout: the hook and the tool links resolve
    # to it, and the hypr copies carry its bytes.
    assert "omarchy-default-terminal kitty" in _calls(env)
    assert "omarchy-shell" in _commands(env)  # the module loop, from the clone
    hook = env["home"] / ".config" / "omarchy" / "hooks" / "post-update.d" / "10-hyprconf"
    assert f'HYPRCONF_DIR="{target}"' in hook.read_text()
    bindings = env["home"] / ".config" / "hypr" / "bindings.lua"
    assert not bindings.is_symlink()
    assert bindings.read_bytes() == (target / "modules" / "hypr" / "bindings.lua").read_bytes()
    gaps = env["home"] / ".local" / "bin" / "hyprconf-gaps"
    assert Path(os.readlink(gaps)) == target / "modules" / "hypr" / "bin" / "hyprconf-gaps"
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


def test_refuses_to_run_as_root() -> None:
    """curl|bash users reflexively prefix sudo; under env_reset that
    half-installs the overlay into /root. Pinned as text, not run: the suite
    is unprivileged everywhere now (CI included), and there is no seam left
    to make the branch reachable — which is the point, since the seam was
    itself a way past the guard."""
    code = _code_only(INSTALL_SH.read_text())
    assert re.search(r"if \(\(EUID == 0\)\); then", code)
    assert "run as your regular user" in code
