"""The `box` fixture: one throwaway machine per test.

A box is a tmp `$HOME`, a tmp `/etc`, a tmp `$OMARCHY_PATH` tree and a fakes
directory FIRST on PATH carrying a recording stub for every command the tree
can run: every `omarchy-*` name the shipped scripts and payload carry
(derived from them, so a call the fakes do not cover cannot slip past), plus
the handful that are just as able to touch the real machine — `omarchy`
itself, `sudo`, `hyprctl`, `udevadm`, `fc-list`, `git`, `nvidia-smi`,
`vulkaninfo`. PATH is those fakes, then only `/usr/bin` and `/bin` — never
the host's, where `/usr/share/omarchy/bin` would answer — and the whole
environment is built from scratch, so nothing of the developer's session
(HOME, a live `VK_LOADER_*`, `OMARCHY_UPDATE_LOGGED`) reaches a run.

A test that needs a fake to DO something — a `sudo` that execs its arguments,
a `vulkaninfo` that answers — overrides it with `box.stub(name, body)`, which lands
in the box's own dir ahead of the shared one. Everything a script reads
outside `$HOME` reaches the box through that script's own `_HYPRCONF_*` seam,
which the suite adds to `box.env` (AGENTS.md › Scripts, CONTRIBUTING ›
Writing hermetic tests).
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent

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

# Not omarchy-*, and every one of them reaches the real machine: sudo and
# udevadm change the system, hyprctl the running desktop, git the
# network, and fc-list, nvidia-smi and vulkaninfo answer for the host's
# fonts and GPUs instead of the box's.
EXTRA_FAKES = (
    "omarchy",
    "sudo",
    "hyprctl",
    "udevadm",
    "fc-list",
    "git",
    "nvidia-smi",
    "vulkaninfo",
)

# What the scripts read out of $OMARCHY_PATH, in the shape the installed tree
# has (Omarchy 4.0.3-1) and cut to what a test needs to see. A script that
# reads another file adds it here, or writes its own with box.omarchy_write().
OMARCHY_TREE = {
    # default/bash/env-bootstrap:10-16,37-41 — OMARCHY_PATH exported, and
    # ~/.local/bin appended to PATH; envs and aliases are the other two
    # files zsh/zshrc.block sources.
    "default/bash/env-bootstrap": ': "${OMARCHY_PATH:=/usr/share/omarchy}"\nexport OMARCHY_PATH\n',
    "default/bash/envs": 'export EDITOR="${EDITOR:-omarchy-launch-editor --inline}"\n',
    "default/bash/aliases": "alias ff=fastfetch\n",
    # default/firefox/policies.json — what install.sh merges ours UNDER.
    "default/firefox/policies.json": (
        '{\n  "policies": {\n    "Preferences": {\n'
        '      "media.ffmpeg.vaapi.enabled": { "Value": true, "Status": "default" }\n'
        "    }\n  }\n}\n"
    ),
    # config/kitty/kitty.conf — the 4.0.3 stub: two live lines, the rest
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

_OMARCHY_COMMAND = re.compile(r"\bomarchy(?:-[a-z0-9]+)+\b")


def _shipped_text_files() -> list[Path]:
    """Every shipped file a command name can hide in: the bash scripts (a
    bash shebang on line 1 — what the Makefile's shellcheck target selects
    by) plus the Lua, QML and JS payload. Walked on disk, not `git
    ls-files`, so the scan needs no git and no ownership trust."""
    out: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        parts = set(path.parts)
        if not path.is_file() or ".git" in parts or "tests" in parts or "docs" in parts:
            continue
        if path.suffix in {".lua", ".qml", ".js"}:
            out.append(path)
            continue
        with path.open("rb") as fh:
            first = fh.read(80).split(b"\n", 1)[0]
        if first.startswith(b"#!") and b"bash" in first:
            out.append(path)
    return out


@functools.cache
def omarchy_fakes() -> tuple[str, ...]:
    """Every `omarchy-*` name the tree carries. Comments are scanned too: a
    stub too many costs a file in a tmp dir, a stub too few lets a test reach
    the developer's real desktop."""
    names: set[str] = set()
    for path in _shipped_text_files():
        names |= set(_OMARCHY_COMMAND.findall(path.read_text(errors="ignore")))
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
    for name in (*omarchy_fakes(), *EXTRA_FAKES):
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
        timeout: int = 60,
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
            timeout=timeout,
            **feed,
        )

    def core(self, *args: str, **kwargs) -> subprocess.CompletedProcess:
        """install.sh — the module loop — against the box."""
        return self.run(REPO_ROOT / "install.sh", *args, **kwargs)

    def undo(self, module: str, **kwargs) -> subprocess.CompletedProcess:
        """`modules/<name>/install undo`: the stage-restoring branch."""
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


@pytest.fixture
def box(tmp_path: Path, _fakes: Path) -> Box:
    return Box(tmp_path, _fakes)
