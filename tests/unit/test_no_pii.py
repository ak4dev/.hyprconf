"""
PII guard tests.

No tracked file may carry personal information about the person who authored it
— a real username, an absolute /home/<user>/ path, or a personal email address.
Two separate reasons: the overlay's configs (hypr/, kitty/, zsh/, plugins/ …)
are installed into any user's $HOME, so a hardcoded path is broken on every
other machine; and the repo is published, so a name in it is published too.

Scope is deliberately the WHOLE repository. An earlier version of this file
scanned only the shipped config trees, and only for path-shaped leaks — so a
bare username sitting in a test fixture under tests/ went unseen. A guard that
covers part of the tree teaches you to trust it everywhere.

The identities being searched for are derived from the environment at runtime
and never written down here: hard-coding the name would commit the very thing
the test exists to keep out.
"""

from __future__ import annotations

import getpass
import os
import re
import socket
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# /home/<name>/ — a real per-user absolute path. Generic placeholders
# (/home/$USER, /home/user, /home/username, /home/<user>) are allowed.
#
# The leading lookbehind requires the match to begin at a path boundary, so a
# substring like ".../not/home/directory/" in prose is not mistaken for an
# absolute home path. Both exclusions exist to keep the check precise: a rule
# that cries wolf on vendored upstream comments gets muted, and then it stops
# catching the real thing.
HOME_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9._/-])/home/(?!\$|user\b|username\b|<|USER\b)[A-Za-z0-9._-]+/"
)

# Shared, machine-provided or placeholder accounts. A match on one of these is
# not a leak, and CI runs the suite as root — without this the check would
# either flag every "root" in the tree or, worse, be quietly meaningless there.
GENERIC_ACCOUNTS = frozenset(
    {
        "root",
        "user",
        "users",
        "username",
        "test",
        "tester",
        "testuser",
        "someone",
        "nobody",
        "admin",
        "arch",
        "archlinux",
        "build",
        "builder",
        "runner",
        "ubuntu",
        "github",
        "docker",
        "vagrant",
    }
)

# Binary or vendored payloads: scanning them proves nothing and decoding them
# is noise.
SKIP_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".ttf", ".otf", ".woff", ".woff2", ".pyc"}
)


def _tracked_files() -> list[Path]:
    """Every file git tracks, as absolute paths.

    git is the source of truth rather than a directory walk: it skips the
    scratch files, build output and local experiments that are not part of what
    gets published, which is what this guard is actually about.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if out.returncode != 0:  # not a checkout (release tarball, vendored copy)
        pytest.skip("not a git checkout — nothing to enumerate")
    return [REPO_ROOT / name for name in out.stdout.split("\0") if name]


def _text_lines(path: Path) -> list[str]:
    if path.suffix.lower() in SKIP_SUFFIXES or path.is_symlink() or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []  # binary / unreadable — not a file we author


def _identities() -> set[str]:
    """Names and addresses that must not appear in tracked files.

    Derived from whoever is running the suite — their login name, their home
    directory's name, this machine's hostname and their configured git email.
    Nothing is hard-coded, so this file never becomes the leak. Anything
    generic or too short to match precisely is dropped: a two-character login
    would match half the prose in the repo.
    """
    names = {
        os.environ.get("USER", ""),
        os.environ.get("SUDO_USER", ""),
        os.environ.get("LOGNAME", ""),
        Path.home().name,
        socket.gethostname().split(".")[0],
    }
    try:
        names.add(getpass.getuser())
    except (KeyError, OSError):  # no passwd entry for this uid
        pass

    identities = {n for n in names if len(n) >= 3 and n.lower() not in GENERIC_ACCOUNTS}

    email = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "config", "--get", "user.email"],
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if "@" in email:
        identities.add(email)

    return identities


def test_no_hardcoded_home_paths_anywhere() -> None:
    offenders: list[str] = []
    for f in _tracked_files():
        for lineno, line in enumerate(_text_lines(f), 1):
            if HOME_PATH_RE.search(line):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Hardcoded /home/<user>/ paths found in tracked files (use ~ or $HOME):\n"
        + "\n".join(offenders)
    )


def test_no_personal_identities_anywhere() -> None:
    """No tracked file may name the person running the suite.

    Reported without echoing the identity itself, so a failure in CI logs (or
    in a pasted terminal) does not republish what it just caught.
    """
    identities = _identities()
    if not identities:
        pytest.skip("no non-generic identity to search for (shared or CI account)")

    patterns = [
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(i)}(?![A-Za-z0-9])", re.I) for i in identities
    ]
    offenders: list[str] = []
    for f in _tracked_files():
        if f == Path(__file__):
            continue  # this file names none of them, but keep the scan honest
        for lineno, line in enumerate(_text_lines(f), 1):
            if any(p.search(line) for p in patterns):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{lineno}")
    assert not offenders, (
        "Personal identity (username or git email) found in tracked files.\n"
        "Replace it with a placeholder such as 'testuser', ~ or $HOME:\n" + "\n".join(offenders)
    )
