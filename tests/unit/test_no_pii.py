"""
PII guard tests.

No file in the tree may carry personal information about the person who authored it
— a real username, an absolute /home/<user>/ path, or a personal email address.
Two separate reasons: the overlay's configs (hypr/, kitty/, zsh/, plugins/ …)
are installed into any user's $HOME, so a hardcoded path is broken on every
other machine; and the repo is published, so a name in it is published too.

Scope is deliberately the WHOLE repository — a bare username in a test
fixture is as published as one in a config, and a guard that covers part of
the tree teaches you to trust it everywhere.

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
# "home": GitHub's container jobs set HOME=/github/home, whose basename is a
# directory name, not a person — and it would match every $HOME in the tree.
GENERIC_ACCOUNTS = frozenset(
    {
        "root",
        "home",
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


# Directories that are never part of what gets published: git's own store and
# tool caches. Everything else in the tree is scanned — including a stray
# scratch file, which is the moment to catch it, before it is ever added.
SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".vscode"})


def _repo_files() -> list[Path]:
    """Every regular file in the checkout, skipping SKIP_DIRS.

    A directory walk rather than `git ls-files`: the scan then needs no git
    and no ownership trust — in CI the workspace belongs to another uid and a
    root-run git refuses it.
    """
    out: list[Path] = []
    for path in sorted(REPO_ROOT.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(REPO_ROOT).parts):
            continue
        if path.is_file() and not path.is_symlink():
            out.append(path)
    return out


def _text_lines(path: Path) -> list[str]:
    if path.suffix.lower() in SKIP_SUFFIXES or path.is_symlink() or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []  # binary / unreadable — not a file we author


def _identities() -> set[str]:
    """Names and addresses that must not appear anywhere in the tree.

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
    for f in _repo_files():
        for lineno, line in enumerate(_text_lines(f), 1):
            if HOME_PATH_RE.search(line):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, "Hardcoded /home/<user>/ paths found (use ~ or $HOME):\n" + "\n".join(
        offenders
    )


def test_no_personal_identities_anywhere() -> None:
    """No file in the tree may name the person running the suite.

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
    for f in _repo_files():
        if f == Path(__file__):
            continue  # this file names none of them, but keep the scan honest
        for lineno, line in enumerate(_text_lines(f), 1):
            if any(p.search(line) for p in patterns):
                offenders.append(f"{f.relative_to(REPO_ROOT)}:{lineno}")
    assert not offenders, (
        "Personal identity (username or git email) found in the tree.\n"
        "Replace it with a placeholder such as 'testuser', ~ or $HOME:\n" + "\n".join(offenders)
    )
