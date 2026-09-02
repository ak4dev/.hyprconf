"""Supply-chain pins: the artifacts strangers trust before and while running
the overlay, frozen as text so a regression cannot ship green.

Verifies:
- web/ stays self-contained: no script element, no external resource — the
  page's whole job is to be trusted enough to pipe into bash
- every published install one-liner speaks https (and only https): schemeless,
  curl's first request is plaintext port 80 and an on-path attacker answers it
  before the redirect exists
- the CI workflow keeps its least-privilege shape: read-only token, no
  pull_request_target, no secrets, actions pinned by commit sha
- the .claude/settings.json guardrails AGENTS.md cites keep their entries
- the Oh My Zsh updater stays disabled beside stage_shell's commit pin — the
  channel inside the pinned code, not just the one install.sh drives

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
    } <= deny
    assert {
        "Bash(git push:*)",
        "Bash(git -C * push:*)",
        "Bash(*scripts/publish*)",
        "Bash(aws:*)",
        "Bash(*/aws *)",
    } <= ask


def test_omz_updater_is_disabled_beside_the_pin() -> None:
    """stage_shell pins Oh My Zsh to a reviewed commit, but the updater
    shipping INSIDE it would re-open the auto-update channel with one
    keypress — the zstyle disable must precede the source line."""
    block = (REPO_ROOT / "zsh" / "zshrc.block").read_text(encoding="utf-8")
    disable = block.find("zstyle ':omz:update' mode disabled")
    source = block.find("oh-my-zsh.sh")
    assert disable != -1, "the omz updater disable is gone"
    assert source != -1 and disable < source, "the disable must come before the source"
