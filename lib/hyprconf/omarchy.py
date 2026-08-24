"""hyprconf.omarchy — the TUI's seams into Omarchy's own theme / background /
idle machinery.

hyprconf is an overlay on Omarchy, so nothing here re-implements what Omarchy
already ships: every state change goes through an ``omarchy-*`` command from
``/usr/share/omarchy/bin`` (verified against Omarchy 4.0.0-1 — the script that
justifies each call is named beside it), and reads follow the exact paths
those scripts read. Where Omarchy demonstrably has no command (the idle
timeouts) the comment says what was checked.

Pure functions: the command runner is injectable (``run=``) and every path is
derived from the environment (``HOME``, ``OMARCHY_PATH``) at call time, so
tests fake all of it with a throwaway HOME and a fake-bins PATH. No Textual
here — the TUI is a thin consumer.
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

# ── Runner ─────────────────────────────────────────────────────────────────────

# A runner takes an argv and returns (returncode, stdout). Failing to launch
# at all (command not found, timeout) is reported as a non-zero code with no
# output, so callers treat it exactly like a command that failed.
Runner = Callable[[list[str]], tuple[int, str]]

# omarchy-theme-set fans out into a dozen app retints and hooks; the rest are
# quick, but a wedged shell IPC (omarchy-shell times out after 2s itself)
# must never hang the TUI.
_TIMEOUT_S = 120.0


def run_command(argv: list[str]) -> tuple[int, str]:
    """Default :data:`Runner` — ``subprocess.run`` with captured stdout."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return 127, ""
    return r.returncode, r.stdout


def _runner(run: Runner | None) -> Runner:
    return run if run is not None else run_command


# ── Paths (Omarchy's own, literally $HOME-anchored as its scripts spell them) ──


def home_dir() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def state_dir() -> Path:
    """``~/.local/state/omarchy`` — where Omarchy keeps ``current/``."""
    return home_dir() / ".local" / "state" / "omarchy"


def config_dir() -> Path:
    """``~/.config/omarchy`` — the user's overrides (``shell.json``, backgrounds)."""
    return home_dir() / ".config" / "omarchy"


def omarchy_path() -> Path:
    """``$OMARCHY_PATH`` — Omarchy's installed tree (defaults per its own scripts)."""
    return Path(os.environ.get("OMARCHY_PATH") or "/usr/share/omarchy")


def current_theme_dir() -> Path:
    """``~/.local/state/omarchy/current/theme`` — the rendered active theme."""
    return state_dir() / "current" / "theme"


# ── Theme ──────────────────────────────────────────────────────────────────────


def list_themes(run: Runner | None = None) -> list[str]:
    """Available themes, as ``omarchy-theme-list`` prints them (display
    names: ``tokyo-night`` → ``Tokyo Night``; user themes and Omarchy's own,
    merged and sorted by the script itself)."""
    code, out = _runner(run)(["omarchy-theme-list"])
    if code != 0:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def current_theme(run: Runner | None = None) -> str:
    """The active theme's display name (``omarchy-theme-current``; it prints
    ``Unknown`` when no theme has ever been set)."""
    code, out = _runner(run)(["omarchy-theme-current"])
    return out.strip() if code == 0 and out.strip() else "Unknown"


def set_theme(name: str, run: Runner | None = None) -> bool:
    """Apply a theme via ``omarchy-theme-set <name>`` — it accepts the display
    name (lower-cases and hyphenates it itself), stages the theme, swaps it
    in, picks a background, retints every app and fires the theme-set hook.
    """
    code, _ = _runner(run)(["omarchy-theme-set", name])
    return code == 0


# ── Background ─────────────────────────────────────────────────────────────────

# The suffixes omarchy-theme-bg-next's `find -iname` accepts.
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"})


def theme_name() -> str:
    """The active theme's directory name (``current/theme.name``) — the
    hyphenated form the backgrounds directory is keyed by."""
    try:
        return (state_dir() / "current" / "theme.name").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def background_dirs() -> list[Path]:
    """Exactly the two directories ``omarchy-theme-bg-next`` scans, in its
    order: ``~/.config/omarchy/backgrounds/<theme-name>/`` then
    ``~/.local/state/omarchy/current/theme/backgrounds/``."""
    return [
        config_dir() / "backgrounds" / theme_name(),
        current_theme_dir() / "backgrounds",
    ]


def list_backgrounds() -> list[Path]:
    """The backgrounds available to the active theme, the way
    ``omarchy-theme-bg-next`` enumerates them: regular files (symlinks
    followed) directly inside :func:`background_dirs`, image suffixes only,
    sorted by full path."""
    found: list[Path] = []
    for d in background_dirs():
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file():
                found.append(p)
    return sorted(found)


def current_background() -> Path | None:
    """The background in use: the target of the
    ``~/.local/state/omarchy/current/background`` symlink, read with a plain
    ``readlink`` so it compares equal to :func:`list_backgrounds` entries
    (what omarchy-theme-bg-next itself does to find the current index;
    ``omarchy-theme-bg-current`` prints a prettified basename, not a path).
    """
    link = state_dir() / "current" / "background"
    try:
        return Path(os.readlink(link))
    except OSError:
        return None


def set_background(path: Path | str, run: Runner | None = None) -> bool:
    """Apply a background via ``omarchy-theme-bg-set <path>`` — it re-points
    the ``current/background`` symlink and pushes the image to the running
    shell over IPC."""
    code, _ = _runner(run)(["omarchy-theme-bg-set", str(path)])
    return code == 0


# ── Idle timeouts (shell.json) ─────────────────────────────────────────────────

# Omarchy's shell drives idle from the "idle" block of shell.json:
# ``{"lock": 300, "screensaver": 150}`` (seconds since idle began), read by
# shell/plugins/services/idle/Service.qml with those same numbers as the
# fallback when a key is absent. Omarchy 4.0.0-1 ships NO command for these
# keys: `grep -rl screensaver /usr/share/omarchy/bin` finds nothing, and
# omarchy-shell-config (the helper that writes shell.json for `omarchy bar`)
# is a sourced library, marked omarchy:hidden=true, not a CLI — its own docs
# (default/agents/skills/omarchy/plugins.md) say to edit idle.lock /
# idle.screensaver in ~/.config/omarchy/shell.json directly. So this edits
# the file the way omarchy-shell-config's commit() does: read the user file
# if it is non-empty, else $OMARCHY_PATH/config/omarchy/shell.json; change
# only the keys asked for; write to a temp file and move it into place; then
# refresh_shell_config() — `omarchy-shell shell reloadConfig`, falling back
# to `omarchy-shell -q shell rescanPlugins`.
IDLE_DEFAULTS: dict[str, int] = {"lock": 300, "screensaver": 150}
IDLE_MAX_S = 86400


def shell_config_file() -> Path:
    return config_dir() / "shell.json"


def shell_defaults_file() -> Path:
    return omarchy_path() / "config" / "omarchy" / "shell.json"


def _shell_config_source() -> Path:
    """omarchy-shell-config's source_file(): the user file when non-empty, else defaults."""
    user = shell_config_file()
    try:
        if user.stat().st_size > 0:
            return user
    except OSError:
        pass
    return shell_defaults_file()


def _load_shell_config() -> dict:
    try:
        data = json.loads(_shell_config_source().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def idle_timeouts() -> dict[str, int]:
    """``{"lock": s, "screensaver": s}`` as the shell will apply them."""
    idle = _load_shell_config().get("idle")
    idle = idle if isinstance(idle, dict) else {}
    result: dict[str, int] = {}
    for key, default in IDLE_DEFAULTS.items():
        raw = idle.get(key, default)
        try:
            result[key] = int(raw)
        except (TypeError, ValueError):
            result[key] = default
    return result


def refresh_shell_config(run: Runner | None = None) -> bool:
    """Make the running shell re-read shell.json — omarchy-shell-config's
    refresh_shell_config(), verbatim."""
    r = _runner(run)
    code, _ = r(["omarchy-shell", "shell", "reloadConfig"])
    if code == 0:
        return True
    r(["omarchy-shell", "-q", "shell", "rescanPlugins"])
    return False


def set_idle_timeouts(
    lock: int | None = None,
    screensaver: int | None = None,
    run: Runner | None = None,
) -> bool:
    """Persist idle timeouts (seconds) to ``~/.config/omarchy/shell.json``,
    keeping every other key, then refresh the shell. Returns True once the
    file is written (the shell refresh is best-effort, as in Omarchy)."""
    config = _load_shell_config()
    idle = config.get("idle")
    idle = dict(idle) if isinstance(idle, dict) else {}
    for key, value in (("lock", lock), ("screensaver", screensaver)):
        if value is None:
            continue
        idle[key] = max(0, min(IDLE_MAX_S, int(value)))
    config["idle"] = idle
    target = shell_config_file()
    tmp = target.with_name(target.name + ".hyprconf-tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # jq -S: sorted keys, 2-space indent — the same shape Omarchy writes.
        tmp.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    refresh_shell_config(run)
    return True


# ── Stay awake (omarchy-toggle-idle) ───────────────────────────────────────────


def stay_awake(run: Runner | None = None) -> bool:
    """True when idle lock/screensaver are suspended — ``omarchy-toggle-idle
    --status`` prints ``{"enabled":true,…}`` while the stay-awake flag file
    exists."""
    code, out = _runner(run)(["omarchy-toggle-idle", "--status"])
    if code != 0:
        return False
    try:
        return bool(json.loads(out).get("enabled"))
    except (ValueError, AttributeError):
        return False


def toggle_stay_awake(run: Runner | None = None) -> bool | None:
    """Flip stay-awake via ``omarchy-toggle-idle`` (its ``toggle`` default).
    It prints the resulting *idle* state — ``disabled`` means stay-awake is
    now on. Returns the new stay-awake state, or None if the command failed."""
    code, out = _runner(run)(["omarchy-toggle-idle"])
    if code != 0:
        return None
    return out.strip() == "disabled"


# ── Theme palette (for the TUI's own colours) ──────────────────────────────────

# colors.toml is the machine-readable palette omarchy-theme-set renders into
# current/theme/ (generating it from alacritty.toml when a theme lacks one).
# Only the four roles the TUI paints with are mapped; "comment" is Omarchy's
# "muted".
_COLOR_ROLES = {
    "background": "background",
    "foreground": "foreground",
    "accent": "accent",
    "comment": "muted",
}


def theme_colors() -> dict[str, str]:
    """``{background, foreground, accent, comment}`` from the active theme's
    ``colors.toml`` — only the keys present and well-formed (``#rrggbb``)."""
    try:
        data = tomllib.loads((current_theme_dir() / "colors.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    result: dict[str, str] = {}
    for role, key in _COLOR_ROLES.items():
        value = data.get(key)
        if isinstance(value, str) and len(value) == 7 and value.startswith("#"):
            result[role] = value
    return result
