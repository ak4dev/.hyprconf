"""Supply-chain pins: the artifacts strangers trust before and while running
the overlay, frozen as text so a regression cannot ship green. The model they
enforce, and what to do when one of them has to move, is CONTRIBUTING ›
Security.

HERMETIC: reads only the checkout; no network, no HOME.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
ONE_LINER = "bash <(curl -fsSL --proto '=https' https://hyprconf.sh)"

# The only remote URLs the published page may carry.
WEB_ALLOWED_URLS = (
    "https://github.com/ak4dev/.hyprconf",
    "https://hyprconf.sh",  # the page's own origin, in the install one-liner
    "http://www.w3.org/2000/svg",  # the SVG namespace identifier, not a request
)


def test_web_page_is_self_contained() -> None:
    """The page's whole job is to be trusted enough to pipe into bash: no
    script element, no external resource."""
    for path in sorted((REPO_ROOT / "web").iterdir()):
        text = path.read_text(encoding="utf-8")
        assert "<script" not in text.lower(), f"{path.name}: script element"
        for url in re.findall(r"https?://[^\s\"'<>()]+", text):
            assert any(url.startswith(a) for a in WEB_ALLOWED_URLS), f"{path.name}: {url}"
        # protocol-relative fetches and inline handlers are requests/JS too
        assert not re.search(r"(?:href|src)\s*=\s*[\"']//", text), (
            f"{path.name}: protocol-relative URL"
        )
        assert "url(//" not in text, f"{path.name}: protocol-relative CSS url"
        assert not re.search(r"\son\w+\s*=", text), f"{path.name}: inline event handler"


def test_published_one_liners_are_https_only() -> None:
    """Schemeless, curl's first request is plaintext port 80 and an on-path
    attacker answers it before the redirect exists."""
    published = ("README.md", "install.sh", "docs/CONTRIBUTING.md")
    for rel in published:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for m in re.finditer(r"curl [^\n]*hyprconf\.sh", text):
            assert "https://hyprconf.sh" in m.group(0), (
                f"{rel}: schemeless bootstrap: {m.group(0)!r}"
            )
    web = (REPO_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "curl -fsSL --proto '=https' https://hyprconf.sh" in web
    assert ONE_LINER in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_bootstrap_defaults_are_pinned_https_and_stable() -> None:
    """The first bytes strangers run. Every behavioural curl-path test
    (tests/test_core.py) overrides HYPRCONF_REPO, so an http:// downgrade or
    a fork URL in the default would ship green without this literal pin."""
    text = (REPO_ROOT / "install.sh").read_text(encoding="utf-8")
    assert ': "${HYPRCONF_REPO:=https://github.com/ak4dev/.hyprconf}"' in text
    assert ': "${HYPRCONF_BRANCH:=stable}"' in text


def test_ci_workflow_is_least_privilege() -> None:
    workflows = sorted(
        p for ext in ("*.yml", "*.yaml") for p in (REPO_ROOT / ".github" / "workflows").glob(ext)
    )
    assert workflows, "no CI workflow found"
    for wf in workflows:
        text = wf.read_text(encoding="utf-8")
        assert re.search(r"^permissions:\n  contents: read$", text, re.M), f"{wf.name}: token scope"
        assert text.count("permissions:") == 1, f"{wf.name}: a second permissions block"
        assert "pull_request_target" not in text, wf.name
        assert "secrets." not in text, wf.name
        for use in re.findall(r"uses:\s*(\S+)", text):
            assert re.search(r"@[0-9a-f]{40}$", use), f"{wf.name}: mutable action pin {use!r}"


def test_claude_settings_guardrails_keep_their_entries() -> None:
    """AGENTS.md leans on these deny/ask rules as its speed bump; an entry
    silently dropped changes the enforcement AGENTS documents."""
    settings = json.loads((REPO_ROOT / ".claude" / "settings.json").read_text())
    deny = set(settings["permissions"]["deny"])
    ask = set(settings["permissions"]["ask"])
    assert {
        "Edit(//usr/share/omarchy/**)",
        "Bash(sudo pacman:*)",
        "Bash(yay:*)",
        "Bash(sudo yay:*)",
        "Bash(paru:*)",
        "Bash(makepkg:*)",
        "Bash(omarchy-pkg-aur-add:*)",
        # Omarchy ships three AUR entry points, not one: omarchy-pkg-aur-install
        # is a yay TUI (`# omarchy:requires-sudo=true`, /usr/bin/omarchy-pkg-aur-install:4,
        # `yay -Slqa | fzf` then `xargs yay -S --noconfirm`, :20,26) and
        # omarchy-update-aur-pkgs is `yay -Sua --noconfirm --cleanafter` (:8).
        # The rules match command text, so invoking either by name walked past
        # `Bash(yay:*)`. Omarchy 4.0.3-1.
        "Bash(omarchy-pkg-aur-install:*)",
        "Bash(omarchy-update-aur-pkgs:*)",
    } <= deny
    assert {
        "Bash(git push:*)",
        "Bash(git -C * push:*)",
        "Bash(*scripts/publish*)",
        "Bash(aws:*)",
        "Bash(*/aws *)",
    } <= ask


def test_every_module_clone_is_pinned_to_a_reviewed_commit() -> None:
    """Third-party code a module clones runs on the user's box — powerlevel10k
    in every interactive zsh — so it stays at a commit somebody read: every
    `git clone` a module makes names a `--revision=$<name>pin` variable, and no
    module pulls. Bumping a pin is a deliberate commit through the publish
    gates (AGENTS rule 8), never an auto-update."""
    for install in sorted((REPO_ROOT / "modules").glob("*/install")):
        # Code only: a module's own prose says what `git pull` would do to a
        # symlinked plugin folder, and a comment is not a call.
        text = "\n".join(
            ln
            for ln in install.read_text(encoding="utf-8").splitlines()
            if not ln.lstrip().startswith("#")
        )
        for clone in re.findall(r"git clone[^\n]*", text):
            assert re.search(r'--revision="?\$[a-z0-9_]*pin', clone), (
                f"{install.parent.name}: {clone}"
            )
        assert "git pull" not in text, install.parent.name
    shell = (REPO_ROOT / "modules" / "shell-zsh" / "install").read_text(encoding="utf-8")
    assert re.search(r"^p10k_url=https://", shell, re.M)
    assert re.search(r"^p10k_pin=[0-9a-f]{40}$", shell, re.M)
