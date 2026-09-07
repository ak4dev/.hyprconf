"""plugins/**: the contract every plugin folder keeps so it can be published
on its own — `omarchy plugin add <url>` clones a repository with
manifest.json at its root and refuses what omarchy-plugin-validate refuses
(bin/omarchy-plugin-add, Omarchy 4.0.2-1) — while install.sh keeps syncing
the same folders out of the checkout.

- omarchy-plugin-validate's checks, re-implemented in Python so that CI (an
  archlinux container with no Omarchy) pins them; on a box with Omarchy the
  real validator runs too (test_omarchy_install.py).
- The publishable shape: README.md and manifest.json at the folder root, a
  NOTICE where the code is Omarchy's (a clonedFrom copy of MIT code),
  nothing that only works with the overlay installed (no ~/.local/bin, no
  @HYPRCONF_DIR@, no bare hyprconf-* argv in a Process), every bundled
  script executable.
- Omarchy 4.0.2's rule for QML Text: a `text:` bound to anything but string
  literals declares `textFormat: Text.PlainText` (Qt's default AutoText would
  parse a window title or a device name as rich text; upstream's
  test/shell.d/qml-text-format-scan.py — the block rule is ported here,
  small, with a self-check so the port cannot pass in silence).
- The clock plugin's parity with the installed Omarchy's own clock (skips
  without one — with test_installed_plugins_pass_omarchy_plugin_validate,
  the two skips CI shows).
- The resources plugin's feeder restart policy, which is a source shape
  because a behavioural check would need a running shell: a capped backoff,
  never a flat retry, with the latched produced-output flags left alone.

HERMETIC: reads of the checkout only. The exec-bit check reads the on-disk
mode — what a git checkout gives a 100755 blob and what install.sh's
`cp -aL` and `omarchy plugin add`'s clone both carry — never `git ls-files`,
which would need the checkout's git (CI's root-run git refuses the
runner-owned workspace).
"""

from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS = REPO_ROOT / "plugins"
# The stock plugin plugins/hyprconf-clock is a copy of; the parity test
# reads it and changes nothing.
OMARCHY_CLOCK = Path("/usr/share/omarchy/shell/plugins/panels/clock")

# bin/omarchy-plugin-validate (Omarchy 4.0.2-1) — its regex, its required
# fields, its kind → entry-point table and its section domain, verbatim.
PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REQUIRED_FIELDS = ("id", "name", "version", "kinds", "entryPoints")
KIND_ENTRY_POINTS = {
    "bar": "bar",
    "bar-widget": "barWidget",
    "menu": "menu",
    "overlay": "overlay",
    "panel": "panel",
    "service": "service",
}
SECTIONS = ("left", "center", "right")


def plugin_folders() -> list[Path]:
    folders = sorted(p for p in PLUGINS.iterdir() if p.is_dir())
    assert folders, f"no plugin folders under {PLUGINS}"
    return folders


def _walk(folder: Path):
    """Every path under a plugin folder, .git pruned the way the validator
    prunes it (an installed plugin is a git checkout)."""
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in dirnames + sorted(filenames):
            yield Path(dirpath) / name


def validator_problems(folder: Path) -> list[str]:
    """What omarchy-plugin-validate would refuse in `folder`, as messages;
    empty means valid. Check for check the script's (4.0.2-1): manifest.json
    present and JSON; schemaVersion the JSON number 1 — jq's `==` is
    type-aware, so "1" and `true` are refused, hence the bool exclusion
    (Python's True == 1); the five required fields; the id's regex, no `..`,
    not the reserved omarchy.* namespace; kinds a non-empty array;
    entryPoints an object whose values are non-empty, newline-free,
    relative, `..`-free paths to files that exist; barWidget.defaultSection
    in its domain when given; an entry point for every kind that needs one;
    no symlink anywhere in the folder (.git pruned)."""
    problems: list[str] = []
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        return [f"missing manifest.json in {folder}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"manifest.json is not valid JSON: {exc}"]
    if not isinstance(manifest, dict):
        return ["manifest.json is not a JSON object"]

    schema = manifest.get("schemaVersion")
    if isinstance(schema, bool) or schema != 1:
        problems.append("unsupported or missing schemaVersion (expected 1)")
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            problems.append(f"manifest missing required field '{field}'")

    plugin_id = manifest.get("id")
    if not isinstance(plugin_id, str) or not plugin_id:
        problems.append("manifest 'id' is empty")
    else:
        if not PLUGIN_ID_RE.match(plugin_id) or ".." in plugin_id:
            problems.append(f"invalid plugin id '{plugin_id}'")
        if plugin_id.startswith("omarchy."):
            problems.append(f"plugin id '{plugin_id}' uses the reserved omarchy.* namespace")

    kinds = manifest.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        problems.append("'kinds' must be a non-empty array")
        kinds = []
    entry_points = manifest.get("entryPoints")
    if not isinstance(entry_points, dict):
        problems.append("'entryPoints' must be an object")
        entry_points = {}

    bar_widget = manifest.get("barWidget")
    if isinstance(bar_widget, dict) and "defaultSection" in bar_widget:
        section = bar_widget["defaultSection"]
        if not isinstance(section, str) or section not in SECTIONS:
            problems.append("'barWidget.defaultSection' must be left, center, or right")

    for key, ep in entry_points.items():
        if not isinstance(ep, str) or not ep:
            problems.append(f"entry point '{key}' is empty")
            continue
        if "\n" in ep:
            problems.append(f"entry point '{key}' may not contain a newline")
        if ep.startswith("/"):
            problems.append(f"entry point must be a relative path: '{ep}'")
        if ".." in ep:
            problems.append(f"entry point may not contain '..': '{ep}'")
        if not (folder / ep).is_file():
            problems.append(f"entry point file not found: '{ep}'")

    for kind, ep_key in KIND_ENTRY_POINTS.items():
        if kind in kinds and ep_key not in entry_points:
            problems.append(f"kind '{kind}' requires an 'entryPoints.{ep_key}' to load")

    for path in _walk(folder):
        if path.is_symlink():
            problems.append(f"symlinks are not allowed inside a plugin folder: {path}")
    return problems


BARE_HYPRCONF_ARGV = re.compile(r'command:\s*\[\s*"(hyprconf-[^"]*)"')
OVERLAY_ONLY = (".local/bin", "@HYPRCONF_DIR@")


def publishable_problems(folder: Path) -> list[str]:
    """What would break the folder as a repository of its own: no README.md
    at the root; a clonedFrom copy of Omarchy's MIT code with no NOTICE
    (the license requires its notice on every copy); a file that names
    something only the overlay's install.sh provides — ~/.local/bin, the
    @HYPRCONF_DIR@ token — or a Process running a bare hyprconf-* command
    instead of one resolved from the plugin's own directory; a script with
    a shebang that is not executable."""
    problems: list[str] = []
    if not (folder / "README.md").is_file():
        problems.append("no README.md at the folder root")
    manifest_path = folder / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        omarchy = manifest.get("omarchy") if isinstance(manifest, dict) else None
        if (
            isinstance(omarchy, dict)
            and omarchy.get("clonedFrom")
            and not (folder / "NOTICE").is_file()
        ):
            problems.append("a clonedFrom copy of Omarchy's MIT code with no NOTICE")
    for path in _walk(folder):
        if not path.is_file():
            continue
        rel = path.relative_to(folder)
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in OVERLAY_ONLY:
            if needle in text:
                problems.append(f"{rel} mentions {needle} — the overlay's, not the plugin's")
        if path.suffix == ".qml":
            for match in BARE_HYPRCONF_ARGV.finditer(text):
                problems.append(
                    f"{rel} runs a bare {match.group(1)} — resolve it from the plugin's own dir"
                )
        with path.open("rb") as fh:
            first = fh.readline()
        if first.startswith(b"#!") and not os.access(path, os.X_OK):
            problems.append(f"{rel} has a shebang but is not executable")
    return problems


# ---------------------------------------------------------------------------
# Omarchy 4.0.2's Text rule — the block form of upstream's scanner
# ---------------------------------------------------------------------------

TEXT_NAME = r"(?:[A-Za-z_][A-Za-z0-9_]*\.)?Text"
OPEN_ELEMENT = re.compile(r"(?:^|[:\s])([A-Z][A-Za-z0-9_.]*)\s*\{\s*$")
COMPONENT_TEXT = re.compile(r"^\s*component\s+[A-Za-z_]\w*\s*:\s*" + TEXT_NAME + r"\s*\{\s*$")
INLINE_TEXT = re.compile(r"(?:^|[:\s])" + TEXT_NAME + r"\s*\{([^{}]*)\}")
UNSCANNABLE_TEXT = re.compile(r"(?:^|[:\s])" + TEXT_NAME + r"\s*\{\s*\S")
PROP = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*:")
PROPERTY_DECL = re.compile(r"^\s*(?:readonly\s+)?property\b")
STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
TRAILING_OPERATOR = re.compile(r"(?:&&|\|\||[?:+\-*/,(\[=&|])$")
LEADING_OPERATOR = re.compile(r"^\s*(?:&&|\|\||[?:+\-*/,)\]&|.])")


def _strip_comment(line: str) -> str:
    """The line without a trailing // comment (one inside a string stays)."""
    out: list[str] = []
    quote = None
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            out.append(c)
            if c == "\\":
                out.append(line[i + 1 : i + 2])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
            out.append(c)
        elif line.startswith("//", i):
            break
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _binding_expression(lines: list[str], start: int) -> str:
    """The whole right-hand side of the binding on `lines[start]`, following
    a wrapped expression to its end (a line ending on an operator, or the
    next non-blank line starting with one)."""
    parts = []
    i = start
    while i < len(lines):
        parts.append(lines[i])
        following = next((ln for ln in lines[i + 1 :] if ln.strip()), "")
        if not (TRAILING_OPERATOR.search(lines[i].rstrip()) or LEADING_OPERATOR.match(following)):
            break
        i += 1
    chunk = " ".join(parts)
    return chunk.split(":", 1)[1] if ":" in chunk else chunk


def _is_pure_literal(expr: str) -> bool:
    residue = re.sub(r"[\s+]", "", STRING_LITERAL.sub("", expr))
    return residue == "" and STRING_LITERAL.search(expr) is not None


def text_format_problems(path: Path) -> list[str]:
    """Every Text in `path` that renders a non-literal value without
    `textFormat: Text.PlainText`, one line each: a block whose own `text:`
    is not string literals only; an inline component root Text (its text
    comes from every caller, so it needs the default whatever this file
    binds); a one-line `Text { text: x }`. A `Text {` whose block carries on
    after the brace on the same line is a form this line scanner cannot
    read and is reported as such, as upstream does. Like upstream, text
    assigned from elsewhere (a Binding, PropertyChanges, an alias) is out
    of reach."""
    lines = [_strip_comment(ln) for ln in path.read_text(encoding="utf-8").splitlines()]
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    problems: list[str] = []

    for idx, code in enumerate(lines):
        for match in INLINE_TEXT.finditer(code):
            body = match.group(1)
            binding = re.search(r"\btext\s*:\s*(.*?)\s*(?:;|$)", body)
            if "textFormat" in body or not binding or _is_pure_literal(binding.group(1)):
                continue
            problems.append(f"{rel}:{idx + 1}: inline Text block without textFormat")
        for match in UNSCANNABLE_TEXT.finditer(code):
            # From the block's first body character: does its own brace close
            # on this line, with no nested block? Then it is the one-line
            # form judged above (upstream's walk, not a brace count — an
            # enclosing element's `}` after it would miscount).
            rest = code[match.end() - 1 :]
            depth, closed = 1, False
            for char in rest:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        closed = True
                        break
            if closed and "{" not in rest:
                continue
            problems.append(f"{rel}:{idx + 1}: Text block in a form this scanner cannot read")

    stack: list[dict] = []
    depth = 0
    for idx, code in enumerate(lines):
        opened = OPEN_ELEMENT.search(code)
        prop = PROP.match(code)
        if (
            prop
            and stack
            and stack[-1]["depth"] == depth
            and not opened
            and not PROPERTY_DECL.match(code)
        ):
            stack[-1]["props"].setdefault(prop.group(1), idx)
        depth += code.count("{") - code.count("}")
        if opened and "{" in code:
            stack.append(
                {
                    "name": opened.group(1),
                    "depth": depth,
                    "props": {},
                    "start": idx,
                    "component": bool(COMPONENT_TEXT.match(code)),
                }
            )
        while stack and depth < stack[-1]["depth"]:
            block = stack.pop()
            if block["name"].split(".")[-1] != "Text" or "textFormat" in block["props"]:
                continue
            if block["component"]:
                problems.append(
                    f"{rel}:{block['start'] + 1}: inline component root Text declares no textFormat"
                )
            elif "text" in block["props"]:
                tline = block["props"]["text"]
                if not _is_pure_literal(_binding_expression(lines, tline)):
                    problems.append(f"{rel}:{tline + 1}: text binding without textFormat")
    return sorted(problems)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("folder", plugin_folders(), ids=lambda p: p.name)
def test_plugin_folders_satisfy_the_validator_contract(folder: Path) -> None:
    """omarchy-plugin-validate's every check, on every plugin folder, with
    no Omarchy needed — the contract `omarchy plugin add` gates a
    repository on, pinned where publishing is gated: CI."""
    assert validator_problems(folder) == []


@pytest.mark.parametrize("folder", plugin_folders(), ids=lambda p: p.name)
def test_plugin_folders_are_publishable_on_their_own(folder: Path) -> None:
    """A folder split into its own repository (CONTRIBUTING › Publishing a
    plugin) carries everything it needs and nothing of the overlay's."""
    assert publishable_problems(folder) == []
    manifest = json.loads((folder / "manifest.json").read_text())
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"]), "SemVer, bumped per change"


def test_plugin_text_never_renders_runtime_strings_as_rich_text() -> None:
    """Omarchy 4.0.2's rule over every QML the overlay ships (upstream's
    stock ActiveWindow.qml and WidgetButton.qml gained the line in that
    release): a window title, a device name or a feeder string is data, and
    Text's default AutoText would parse it as HTML."""
    qml = sorted(PLUGINS.rglob("*.qml"))
    assert qml, "no plugin QML found"
    problems = [p for path in qml for p in text_format_problems(path)]
    assert not problems, (
        "Text rendering a runtime value without textFormat: Text.PlainText:\n" + "\n".join(problems)
    )


def test_the_text_format_scan_catches_what_it_should(tmp_path: Path) -> None:
    """The port, held to fixtures — a guard nothing can fail is a guard
    nobody should trust (upstream's own words for its scanner)."""
    fixtures = {
        "clean.qml": 'Item {\n  Text {\n    text: root.title\n    textFormat: Text.PlainText\n  }\n  Text {\n    text: "literal" +\n      "only"\n  }\n}\n',
        "bound.qml": "Item {\n  Text {\n    text: root.title\n  }\n}\n",
        "wrapped.qml": 'Item {\n  Text {\n    text: "prefix" +\n      root.title\n  }\n}\n',
        "component.qml": "Item {\n  component Cell: Text {\n    color: root.fg\n  }\n}\n",
        "inline.qml": "Item {\n  Row { Text { text: root.title } }\n}\n",
        "unscannable.qml": "Item {\n  Text { text: root.title\n    color: root.fg\n  }\n}\n",
    }
    root = tmp_path / "plugins"
    root.mkdir()
    for name, body in fixtures.items():
        (root / name).write_text(body)
    # Report paths are relative to REPO_ROOT; the fixtures live elsewhere.
    caught = {
        name: [p.split(": ", 1)[1] for p in text_format_problems(root / name)] for name in fixtures
    }
    assert caught["clean.qml"] == []
    assert caught["bound.qml"] == ["text binding without textFormat"]
    assert caught["wrapped.qml"] == ["text binding without textFormat"]
    assert caught["component.qml"] == ["inline component root Text declares no textFormat"]
    assert caught["inline.qml"] == ["inline Text block without textFormat"]
    assert caught["unscannable.qml"] == ["Text block in a form this scanner cannot read"]


def test_resources_feeders_restart_on_a_capped_backoff() -> None:
    """A feeder that produced output once and then dies is restarted, but the
    flag that says it produced output is latched — it also decides what the
    GPU cells paint, so it can never be cleared — and a flat 1 s retry behind
    a latched flag never gives up: an NVIDIA box whose driver stops answering
    makes `nvidia-smi --loop` exit at once, and the respawn is then ~78,000
    execs a day, each paying a failing NVML init. So the
    ladder (1 s, 2 s, 4 s, 8 s, 16 s, 32 s, then parked) and its refill on a
    line that parses are pinned here. Verified running under quickshell
    0.3.1 against a feeder that exits at once: 7 execs in 63 s, then nothing;
    and against one that emits a line every time: a steady 1 s."""
    qml = sorted((PLUGINS / "hyprconf-resources").glob("*.qml"))
    assert qml, "no resources plugin QML found"
    code = "\n".join(_strip_comment(ln) for path in qml for ln in path.read_text().splitlines())
    assert "component Restarter: Timer" in code
    assert "readonly property int maxAttempts: 6" in code
    assert "if (restarter.attempt >= restarter.maxAttempts) return" in code
    assert "restarter.interval = 1000 * (1 << restarter.attempt)" in code
    assert "function produced() { restarter.attempt = 0 }" in code
    # Both feeders go through it, and neither restarts a Process any other way.
    assert code.count("RestartTimer.died()") == 2
    assert code.count("RestartTimer.produced()") == 2
    assert "RestartTimer.start()" not in code
    # The latched flags stay latched: clearing one would blank the cells.
    assert not re.search(r"root\.(?:gpu|stats)Produced\s*=\s*false", code)


def test_clock_plugin_ticks_seconds_and_loads_omarchys_own_panel() -> None:
    """The three deltas the clock plugin exists for, pinned without Omarchy:
    SystemClock at Seconds (the stock Minutes would freeze a seconds format
    59 s of every minute), the calendar panel loaded from the running
    Omarchy's own Panel.qml through OMARCHY_PATH — the way Omarchy's plugins
    find their tree (Clipboard.qml's omarchyPath) — so the panel is never a
    stale copy, and the panel told which module id it is mounted as, so what
    the calendar writes reaches shell.json. Model.js sits beside
    BarWidget.qml because its static `import "Model.js"` needs it there."""
    folder = PLUGINS / "hyprconf-clock"
    widget = folder / "BarWidget.qml"
    code = "\n".join(
        ln for ln in widget.read_text().splitlines() if not ln.lstrip().startswith("//")
    )
    assert "precision: SystemClock.Seconds" in code
    assert "SystemClock.Minutes" not in code
    assert (
        'source: "file://" + Quickshell.env("OMARCHY_PATH") + "/shell/plugins/panels/clock/Panel.qml"'
        in code
    )
    assert 'Qt.resolvedUrl("Panel.qml")' not in code
    # Delta 3: without the forward the panel keeps Panel.qml's literal
    # "omarchy.clock", and its persistSettings() then writes through
    # shell.qml's updateEntryInline() against an id no live entry carries —
    # a week start or a birth year redraws and is never saved. The trigger
    # covers a moduleName that arrives after the panel has loaded.
    assert 'if ("moduleName" in target) target.moduleName = root.moduleName' in code
    assert "onModuleNameChanged: injectPanel()" in code
    assert 'import "Model.js" as Model' in code and (folder / "Model.js").is_file()
    assert not (folder / "Panel.qml").exists()
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["omarchy"] == {"clonedFrom": "omarchy.clock"}
    assert manifest["entryPoints"] == {"barWidget": "BarWidget.qml"}


def test_clock_plugin_tracks_omarchys_stock_clock() -> None:
    """plugins/hyprconf-clock is Omarchy's own clock (shell/plugins/panels/
    clock, 4.0.2-1): Model.js byte-identical, BarWidget.qml the stock file
    plus a header comment and exactly the three deltas above, nothing else.
    An Omarchy release that changes its clock turns this red on a box with
    that release, and the header carries the refresh recipe. Skips without
    an installed Omarchy — one of the two skips CI shows."""
    if not OMARCHY_CLOCK.is_dir():
        pytest.skip("no installed Omarchy clock plugin to compare with")
    folder = PLUGINS / "hyprconf-clock"
    assert (folder / "Model.js").read_bytes() == (OMARCHY_CLOCK / "Model.js").read_bytes()

    ours = (folder / "BarWidget.qml").read_text().splitlines()
    while ours and (ours[0].startswith("//") or not ours[0].strip()):
        ours.pop(0)  # the header comment is the one addition
    stock = (OMARCHY_CLOCK / "BarWidget.qml").read_text().splitlines()
    diff = list(difflib.unified_diff(stock, ours, n=0, lineterm=""))[2:]
    assert [ln[1:] for ln in diff if ln.startswith("-")] == [
        "    precision: SystemClock.Minutes",
        '    source: Qt.resolvedUrl("Panel.qml")',
    ], "\n".join(diff)
    assert [ln[1:] for ln in diff if ln.startswith("+")] == [
        '    if ("moduleName" in target) target.moduleName = root.moduleName',
        "  onModuleNameChanged: injectPanel()",
        "    precision: SystemClock.Seconds",
        '    source: "file://" + Quickshell.env("OMARCHY_PATH") + "/shell/plugins/panels/clock/Panel.qml"',
    ], "\n".join(diff)
