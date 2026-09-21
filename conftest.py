"""The `box` fixture — one throwaway machine per test — and the skip budget.

Its shape, its API and what is faked: CONTRIBUTING › Writing hermetic tests.
Only here: the reason each name is faked, the Omarchy bodies transcribed below,
and the PATH a run gets — the fakes, then only `/usr/bin` and `/bin`, never the
developer's, where `/usr/share/omarchy/bin` would answer.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent
MODULE_NAMES = sorted(p.parent.name for p in (REPO_ROOT / "modules").glob("*/install"))

# The installed tree, through the one seam every probe keys on, and the word a
# suite skips with when it is absent. Pure tools are the only other skip the
# budget below allows, and only where the tool really is missing.
OMARCHY = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
NEEDS_OMARCHY = "needs the installed Omarchy"
PURE_TOOLS = ("jq", "luac", "qmllint", "shellcheck", "zsh")


def _budgeted(reason: str) -> bool:
    if "omarchy" in reason.lower():
        return not (OMARCHY / "default").is_dir()  # install.sh's own probe
    return any(t in reason and shutil.which(t) is None for t in PURE_TOOLS)


def pytest_sessionfinish(session: pytest.Session) -> None:
    """AGENTS.md › Gates and CI, mechanised: any other skip is a regression, so the run
    goes red on one. Matched on the reason — no test id is listed here — and the
    terminal reporter is the xdist controller's, which collects every worker's reports."""
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    seen = {str(r.longrepr[2]).removeprefix("Skipped: ") for r in reporter.stats.get("skipped", ())}
    outside = sorted(r for r in seen if not _budgeted(r))
    if outside:
        reporter.write_sep("=", f"skips outside the budget: {outside}", red=True)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


# A git identity for the whole session: the archlinux:latest container CI runs
# in has no ~/.gitconfig, and there a bare `git commit` in a throwaway tree
# dies "unable to auto-detect email address" — red in CI only. setdefault, so
# a developer's own exported identity is left alone.
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "testuser",
    "GIT_AUTHOR_EMAIL": "testuser@example.invalid",
    "GIT_COMMITTER_NAME": "testuser",
    "GIT_COMMITTER_EMAIL": "testuser@example.invalid",
}
for _name, _value in GIT_IDENTITY.items():
    os.environ.setdefault(_name, _value)


def git(cwd: Path, *args: str) -> str:
    """Run git in a THROWAWAY tree and return its stdout, asserting success: never
    pointed at this checkout, and the identity above spares every caller a `-c user.*`."""
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"git {' '.join(args)} failed: {result.stderr}"
    return result.stdout.strip()


# Not omarchy-*, and every one of them reaches the real machine: sudo and
# udevadm change the system, hyprctl the running desktop, git the
# network, fc-list, nvidia-smi and vulkaninfo answer for the host's fonts and
# GPUs instead of the box's, and findmnt and limine-entry-tool answer for the
# developer's own root filesystem and bootloader (modules/yubikey reads both,
# and gives them bodies of its own with box.stub()).
EXTRA_FAKES = (
    "omarchy",
    "sudo",
    "hyprctl",
    "udevadm",
    "fc-list",
    "findmnt",
    "git",
    "limine-entry-tool",
    "nvidia-smi",
    "vulkaninfo",
)

# What the scripts read out of $OMARCHY_PATH, in the shape the installed tree
# has (Omarchy 4.0.3-1) and cut to what a test needs to see. A script that
# reads another file adds it here, or writes its own with box.omarchy_write().
OMARCHY_TREE = {
    # default/firefox/policies.json — what install.sh merges ours UNDER.
    "default/firefox/policies.json": (
        '{\n  "policies": {\n    "Preferences": {\n'
        '      "media.ffmpeg.vaapi.enabled": { "Value": true, "Status": "default" }\n'
        "    }\n  }\n}\n"
    ),
    # config/kitty/kitty.conf — the 4.0.3 stub: one live line, the rest
    # commented, with Omarchy's own defaults in /etc/xdg/kitty/kitty.conf.
    "config/kitty/kitty.conf": (
        "# Remove the include below to disconnect Kitty from Omarchy's theming system.\n"
        "include ~/.local/state/omarchy/current/theme/kitty.conf\n"
        "\n# Settings below override Omarchy's defaults in /etc/xdg/kitty/kitty.conf.\n"
    ),
    # config/omarchy/shell.json — the seed for ~/.config/omarchy/shell.json,
    # cut to the two keys the overlay reads: idle.screensaver and the bar's
    # centre anchor.
    "config/omarchy/shell.json": (
        '{\n  "version": 1,\n  "idle": { "screensaver": 150, "lock": 300 },\n'
        '  "bar": { "centerAnchor": "omarchy.clock",\n'
        '    "layout": { "center": [ { "id": "omarchy.clock" } ] } }\n}\n'
    ),
}

# -- fakes with a body ------------------------------------------------------
# What a module's real path needs the box to answer, each transcribed from the
# Omarchy file:line beside it (4.0.3-1); a suite hands one to the box with
# `box.stub(name, BODY)`.

# bin/omarchy-hook-install:27-29: mkdir -p the .d dir, cp under the basename, chmod 755.
HOOK_INSTALL = (
    'd="$HOME/.config/omarchy/hooks/$1.d"; mkdir -p "$d"; cp "$2" "$d/${2##*/}"; '
    'chmod 755 "$d/${2##*/}"\n'
)
# bin/omarchy-shell-config:6-26,47-62, the helper modules/idle SOURCES: functions only,
# since the recording fake's `exit 0` would end the sourcing shell before commit() ran.
SHELL_CONFIG = """\
CONFIG_FILE="$HOME/.config/omarchy/shell.json"
DEFAULTS_FILE="$OMARCHY_PATH/config/omarchy/shell.json"
fail() { echo "omarchy-shell-config: $*" >&2; exit 1; }
source_file() { if [[ -s $CONFIG_FILE ]]; then echo "$CONFIG_FILE"; else echo "$DEFAULTS_FILE"; fi; }
commit() {
  local program="$1" tmp; shift
  mkdir -p "$(dirname "$CONFIG_FILE")"; tmp=$(mktemp)
  jq -S -e "$@" "$program" "$(source_file)" > "$tmp" || fail "could not update shell config"
  mv "$tmp" "$CONFIG_FILE"; omarchy-shell shell reloadConfig >/dev/null 2>&1 || true
}
"""
# The running shell's three shell.json writes, one template: every layout entry is a
# bare id or an object with one (bin/omarchy-bar:178); an enable swaps a clonedFrom copy
# into the slot of the id it was cloned from (shell/services/PluginRegistry.qml:529-534)
# and a disable hands the whole entry back, format included (:555 -> restoreCloneSource:441).
_EDIT = """
json="$HOME/.config/omarchy/shell.json"
[[ -f $json ]] || exit 1
%s
jq %s '
    .bar.layout |= with_entries(.value |= map(
        if (if type == "object" then .id else . end) == $a then %s
        else . end))' "$json" > "$json.t" && mv "$json.t" "$json"
"""
_CLONED_FROM = """src=$(jq -r '.omarchy.clonedFrom // empty' \
    "$HOME/.config/omarchy/plugins/$1/manifest.json" 2>/dev/null) || exit 1"""
_RENAME = '(if type == "object" then .id = $b else { id: $b } end)'
PLUGIN_ENABLE = _EDIT % (_CLONED_FROM, '--arg a "$src" --arg b "$1"', _RENAME)
PLUGIN_DISABLE = _EDIT % (_CLONED_FROM, '--arg a "$1" --arg b "$src"', _RENAME)
BAR_SET = _EDIT % (
    "[[ ${1:-} == set ]] || exit 1",
    '--arg a "$2" --arg k "$3" --arg v "$4"',
    '(if type == "object" then . else { id: . } end) + { ($k): $v }',
)
# bin/omarchy-plugin-list --json, cut to the id: with no shell it exits 1 (through
# bin/omarchy-shell:14-17), which is not the same answer as an empty list.
PLUGIN_LIST = """
cd "$HOME/.config/omarchy/plugins" 2>/dev/null || exit 1
jq -n --args '[$ARGS.positional[] | { id: rtrimstr("/") }]' -- */
"""


def bar_shell(box: Box, anchor: str = "omarchy.clock", layout: list | None = None) -> Path:
    """The box's ~/.config/omarchy/shell.json — Omarchy's own default bar, `layout` in
    place of its centre — plus the four fakes that model the running shell."""
    path = box.home / ".config/omarchy/shell.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    center = [{"id": "omarchy.clock", "format": "dddd HH:mm"}] if layout is None else layout
    left = [{"id": "omarchy.menu"}, {"id": "omarchy.workspaces"}]
    layouts = {"left": left, "center": center, "right": []}
    path.write_text(json.dumps({"bar": {"centerAnchor": anchor, "layout": layouts}}))
    box.stub("omarchy-plugin-list", PLUGIN_LIST)
    box.stub("omarchy-plugin-enable", PLUGIN_ENABLE)
    box.stub("omarchy-plugin-disable", PLUGIN_DISABLE)
    box.stub("omarchy-bar", BAR_SET)
    return path


# A sudo that runs its arguments as the box's user, past its own `--` / `-n`, so a
# root write lands in the box's /etc.
SUDO_RUNS = 'while (($#)); do case $1 in -- | -n) shift ;; *) break ;; esac; done\nexec "$@"\n'
# A git that never reaches the network: a clone of a directory is real (the curl path
# clones a throwaway checkout); a clone of a URL is modelled, the directory, a .git and
# the --revision pin as HEAD, which fetch + checkout move. Anything else does nothing.
GIT_FAKE = """\
case "${1:-}" in
  clone)
    src=${@: -2:1}; dst=${@: -1}
    if [[ -d $src ]]; then exec "$(PATH=/usr/bin:/bin command -v git)" "$@"; fi
    rev=; for a in "$@"; do case $a in --revision=*) rev=${a#--revision=} ;; esac; done
    mkdir -p "$dst/.git"; printf '%s' "$rev" > "$dst/.git/head"; exit 0 ;;
  -C)
    d=$2; shift 2
    case "${1:-}" in
      rev-parse) cat "$d/.git/head" 2>/dev/null || echo unborn ;;
      fetch)     for a in "$@"; do last=$a; done; printf '%s' "$last" > "$d/.git/fetched" ;;
      checkout)  cat "$d/.git/fetched" > "$d/.git/head" 2>/dev/null ;;
    esac
    exit 0 ;;
esac
exit 0
"""


def default_app(state: Path, unset: str) -> str:
    """omarchy-default-browser / -editor (bin/omarchy-default-browser:7-19, -editor:9-15,33-34):
    bare, it prints the pick back, `unset` before any; with an argument it records the pick."""
    return (
        f'if (($# == 0)); then cat "{state}" 2>/dev/null || echo {unset}; '
        f'else printf %s "$1" > "{state}"; fi\n'
    )


_OMARCHY_COMMAND = re.compile(r"\bomarchy(?:-[a-z0-9]+)+\b")
_NOT_SHIPPED = {".git", "tests", "docs", "__pycache__", ".pytest_cache", ".ruff_cache"}
_PAYLOAD = {".lua", ".qml", ".js"}  # what a command name can hide in besides a script


def shipped_bash() -> list[Path]:
    """Every bash script the tree ships, selected by SHEBANG — the rule `make
    shellcheck` uses. Walked on disk, not `git ls-files`, so the scans need no
    git and no ownership trust; relative parts, so an ancestor named tests or
    docs does not empty the walk."""
    out: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if path.is_file() and not _NOT_SHIPPED & set(path.relative_to(REPO_ROOT).parts):
            with path.open("rb") as fh:
                first = fh.readline()
            if first.startswith(b"#!") and b"bash" in first:
                out.append(path)
    assert out, "no bash scripts found: the scan is broken"
    return out


def code(text: str) -> str:
    """Comments off: a rule about what a script does is never met, or tripped, by a comment."""
    lines = (ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))
    return "\n".join(ln.split(" #", 1)[0] for ln in lines)


def omarchy_names(bash: Callable[[str], str] = str) -> tuple[str, ...]:
    """Every `omarchy-*` name the tree carries — the bash scripts plus the Lua,
    QML and JS payload. Comments are scanned too: a stub too many costs a file in
    a tmp dir, a stub too few lets a test reach the developer's real desktop.
    `bash=code` drops them, leaving the names that are commands and must resolve."""
    payload = (p for p in sorted((REPO_ROOT / "modules").rglob("*")) if p.suffix in _PAYLOAD)
    names: set[str] = set()
    for path in (*shipped_bash(), *payload):
        names |= set(_OMARCHY_COMMAND.findall(bash(path.read_text(errors="ignore"))))
    assert names, "no omarchy-* names found — the scan is broken"
    return tuple(sorted(names))


def _write_stub(path: Path, body: str) -> None:
    """A recording fake: it appends its own name and arguments, tab
    separated, to $FAKE_CALLS and then runs `body` (nothing but `exit 0` by
    default). Tab separated so an argument with spaces still reads back
    whole (box.calls_of)."""
    path.write_text(
        "#!/usr/bin/env bash\n"
        f"# Recording fake for {path.name}: the real command must never run from a test.\n"
        f"{{ printf '%s' '{path.name}'; (($#)) && printf '\\t%s' \"$@\"; printf '\\n'; }}"
        ' >> "${FAKE_CALLS:-/dev/null}"\n' + body
    )
    path.chmod(0o755)


@pytest.fixture(scope="session")
def _fakes(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The shared fakes, written once per session (per xdist worker): every
    stub here is stateless — it records into whichever box's $FAKE_CALLS the
    environment names."""
    shared = tmp_path_factory.mktemp("fakes")
    for name in (*omarchy_names(), *EXTRA_FAKES):
        _write_stub(shared / name, "exit 0\n")
    return shared


class Box:
    """One throwaway machine: $HOME, /etc, $OMARCHY_PATH and PATH all inside
    tmp_path, and every call to a command that could touch the real system
    recorded instead of made."""

    def __init__(self, tmp: Path, fakes: Path) -> None:
        self.tmp = tmp
        self.home = tmp / "home"
        self.etc = tmp / "etc"
        self.bins = tmp / "bins"
        self.omarchy = tmp / "omarchy"
        self.calls_file = tmp / "calls.txt"
        self._fakes = fakes
        for d in (self.home, self.etc, self.bins):
            d.mkdir(parents=True)
        for rel, text in OMARCHY_TREE.items():
            self.omarchy_write(rel, text)
        self.env: dict[str, str] = {
            "HOME": str(self.home),
            "PATH": f"{self.bins}:{fakes}:/usr/bin:/bin",
            "OMARCHY_PATH": str(self.omarchy),
            "FAKE_CALLS": str(self.calls_file),
            # The two root paths a module writes, at the box's /etc: a run must never
            # read the developer's own to decide.
            "_HYPRCONF_UDEV_RULES": str(self.etc / "udev/rules.d"),
            "_HYPRCONF_FIREFOX_POLICIES": str(self.etc / "firefox/policies"),
            **{k: os.environ[k] for k in GIT_IDENTITY},
        }

    # -- building the box ---------------------------------------------------

    def omarchy_write(self, rel: str, text: str) -> Path:
        """Put a file in the box's $OMARCHY_PATH tree."""
        path = self.omarchy / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def stub(self, name: str, body: str = "exit 0\n") -> Path:
        """A fake of this box's own, ahead of the shared ones on PATH."""
        path = self.bins / name
        _write_stub(path, body)
        return path

    @property
    def fakes(self) -> set[str]:
        """Every command a run of this box finds a fake for — what a suite's
        "every external the tool names has a fake" self-check holds it to."""
        return {p.name for p in self.bins.iterdir()} | {p.name for p in self._fakes.iterdir()}

    # -- running ------------------------------------------------------------

    def run(
        self,
        script: Path | str,
        *args: str,
        tty: bool = False,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Run a shipped script against the box. `tty` reaches the prompts
        through the _HYPRCONF_ASSUME_TTY seam; `stdin` feeds their reads —
        without it stdin is closed, so the --yes / no-terminal refusals stay
        exercised on every other run. `env` adds or overrides box.env."""
        child = {**self.env, **(env or {})}
        if tty:
            child["_HYPRCONF_ASSUME_TTY"] = "1"
        feed: dict = {"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}
        return subprocess.run(
            ["bash", str(script), *args],
            capture_output=True,
            text=True,
            env=child,
            timeout=60,
            **feed,
        )

    def core(self, *args: str, **kwargs) -> subprocess.CompletedProcess:
        """install.sh — the module loop — against the box."""
        return self.run(REPO_ROOT / "install.sh", *args, **kwargs)

    def undo(self, module: str, **kwargs) -> subprocess.CompletedProcess:
        """`modules/<name>/install undo`: the stock-restoring branch."""
        return self.run(REPO_ROOT / "modules" / module / "install", "undo", **kwargs)

    # -- what happened ------------------------------------------------------

    @property
    def _recorded(self) -> list[list[str]]:
        if not self.calls_file.exists():
            return []
        return [ln.split("\t") for ln in self.calls_file.read_text().splitlines() if ln]

    @property
    def calls(self) -> list[str]:
        """Every recorded call, in order, as `name arg arg`."""
        return [" ".join(c) for c in self._recorded]

    def calls_of(self, name: str) -> list[list[str]]:
        """One command's calls, each as its own argv — the form to match on
        when an argument can contain spaces."""
        return [c for c in self._recorded if c[0] == name]

    @property
    def commands(self) -> list[str]:
        """Just the command names, in order.

        Match on these, never on a whole call line: pytest names tmp dirs
        after the test, so a path baked into an argument can contain almost
        any word and produce a false positive."""
        return [c[0] for c in self._recorded]

    def reset(self) -> None:
        """Forget the calls so far."""
        self.calls_file.unlink(missing_ok=True)

    def files(self) -> set[Path]:
        """Every file under the box's HOME — `== set()` is "wrote nothing"."""
        return {p for p in self.home.rglob("*") if p.is_file()}

    def snapshot(self, *roots: Path) -> dict[str, tuple]:
        """Every path under the given roots, HOME and /etc by default: mode, inode, mtime
        and the bytes or link target — the inode because `ln -sfn` over a correct link
        recreates it. `before == after` is "a second run wrote nothing"."""
        out: dict[str, tuple] = {}
        for root in roots or (self.home, self.etc):
            for p in sorted(root.rglob("*")):
                st = p.lstat()
                body = os.readlink(p) if p.is_symlink() else p.read_bytes() if p.is_file() else None
                out[str(p.relative_to(self.tmp))] = (st.st_mode, st.st_ino, st.st_mtime_ns, body)
        return out


@pytest.fixture
def box(tmp_path: Path, _fakes: Path) -> Box:
    return Box(tmp_path, _fakes)
