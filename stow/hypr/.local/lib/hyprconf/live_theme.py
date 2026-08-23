"""Make a theme change take effect in the *running* session.

Writing an app's config only themes its next launch. A kitty window or a btop
that was open across a theme switch keeps the old palette until it is
restarted — the difference between a switch that looks instant and one that
looks half-applied. Both apps re-read their config on a signal, so they are
told to.

Also home to the lock that keeps two switches from interleaving: applying a
theme is a long sequence of read-modify-write passes over shared config files
(kitty.conf, btop.conf, gtk settings, …), and two of them at once can leave a
session wearing halves of two themes.
"""

from __future__ import annotations

import fcntl
import os
import signal
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

# Overridable so tests can point at a fake /proc (never readonly — see AGENTS).
PROC_ROOT = Path(os.environ.get("_HYPRCONF_PROC_ROOT", "/proc"))
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))

# The signal each app documents for "re-read your config", and nothing else.
# An app that can only pick up a palette by restarting does not belong here:
# restarting someone's terminal or editor to recolor it throws away their
# session, which is worse than a stale palette until they open a new window.
RELOAD_SIGNALS: dict[str, int] = {
    "kitty": signal.SIGUSR1,
    "btop": signal.SIGUSR2,
}


def running_pids(name: str) -> list[int]:
    """PIDs whose /proc/<pid>/comm is exactly *name*.

    Reads /proc directly rather than shelling out to pgrep — a theme switch
    already spawns plenty of processes, and this runs per app.
    """
    pids: list[int] = []
    try:
        entries = sorted(PROC_ROOT.iterdir(), key=lambda p: p.name)
    except OSError:
        return pids

    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text(encoding="utf-8").strip() == name:
                pids.append(int(entry.name))
        except (OSError, ValueError):
            continue
    return pids


def reload_app(name: str) -> int:
    """Signal every running instance of *name* to re-read its config.

    Returns how many processes were signalled. Unknown app: 0, no exception —
    the caller is a theme switch, and failing to recolor a terminal must never
    take the switch down with it.
    """
    sig = RELOAD_SIGNALS.get(name)
    if sig is None:
        return 0

    signalled = 0
    for pid in running_pids(name):
        try:
            os.kill(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            # Exited between the scan and the kill, or belongs to another user.
            continue
        signalled += 1
    return signalled


def reload_themed_apps() -> dict[str, int]:
    """Reload every app that can re-read a theme in place.

    Returns {app: processes signalled}, listing only the apps that were running.
    """
    reloaded = {}
    for name in RELOAD_SIGNALS:
        count = reload_app(name)
        if count:
            reloaded[name] = count
    return reloaded


@contextmanager
def switch_lock(name: str = "hyprconf-theme-switch") -> Iterator[bool]:
    """Serialize theme switches; yields True if this process holds the lock.

    Blocking, not `try`-and-bail: a second switch queued behind the first still
    ends on the theme the user picked last, whereas dropping it would leave the
    session on the earlier one and look like the keypress was ignored.

    Yields False when the lock file cannot be created at all (a read-only or
    missing XDG_RUNTIME_DIR, e.g. inside the installer's chroot) — the caller
    proceeds unserialized rather than refusing to theme.
    """
    lock_path = RUNTIME_DIR / f"{name}.lock"
    try:
        handle = lock_path.open("w")
    except OSError:
        yield False
        return

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield True
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
