"""The contract every shipped plugin folder keeps, across all of them.

Each bar module owns its own widget's behaviour in `modules/bar-*/test_*.py`
— the link, the enable-once, the manifest values, the real
`omarchy-plugin-validate` run on the installed folder. What lives here is the
part that is the same for every folder and pointless to write four times: the
validator's own checks ported to Python (CI has no Omarchy, so this is the
half that runs there), the publishable shape a folder needs as a repository
of its own, Omarchy's `Text.PlainText` rule, the implicit-size rule, a real
`qmllint` parse, and the one pin no single module can hold — every `bar.<x>`
a widget reads against the facades an installed third-party widget actually
gets.

HERMETIC: reads of the checkout only, plus the installed `shell/` facades
where there are any.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def plugin_folders() -> list[Path]:
    """Every plugin folder the overlay ships — one per bar module."""
    folders = sorted(REPO_ROOT.glob("modules/*/plugin"))
    assert folders, "no plugin folders found"
    return folders


def folder_id(folder: Path) -> str:
    """A test id a reader can place: the module the folder belongs to."""
    return folder.parent.name


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


def _walk(folder: Path):
    """Every path under a plugin folder, .git pruned the way the validator
    prunes it (an installed plugin is a git checkout)."""
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in dirnames + sorted(filenames):
            yield Path(dirpath) / name


def validator_problems(folder: Path) -> list[str]:
    """What omarchy-plugin-validate (4.0.2-1, unchanged in 4.0.3-1) would
    refuse in `folder`, as messages; empty means valid. Its checks, check for
    check — this is the CI half of a test whose other half runs the real
    validator, and it catches one thing the real one cannot: a symlink inside
    the folder, which the validator's own `find` would follow past.
    The one subtlety is schemaVersion: jq's `==` is type-aware, so "1" and
    `true` are refused where Python's True == 1."""
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
    problems += [f"manifest missing '{f}'" for f in REQUIRED_FIELDS if f not in manifest]

    plugin_id = manifest.get("id")
    if not isinstance(plugin_id, str) or not plugin_id:
        problems.append("manifest 'id' is empty")
    elif (
        not PLUGIN_ID_RE.match(plugin_id)
        or ".." in plugin_id
        or plugin_id.startswith("omarchy.")  # the reserved namespace
    ):
        problems.append(f"invalid plugin id '{plugin_id}'")

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
        # Non-empty, newline-free, relative, `..`-free, and a file that is there.
        if not isinstance(ep, str) or not ep:
            problems.append(f"entry point '{key}' is empty")
        elif "\n" in ep or ep.startswith("/") or ".." in ep or not (folder / ep).is_file():
            problems.append(f"entry point '{key}' is not a relative path to a file here: '{ep}'")

    problems += [
        f"kind '{kind}' requires an 'entryPoints.{ep_key}' to load"
        for kind, ep_key in KIND_ENTRY_POINTS.items()
        if kind in kinds and ep_key not in entry_points
    ]
    problems += [f"symlink inside a plugin folder: {p}" for p in _walk(folder) if p.is_symlink()]
    return problems


BARE_HYPRCONF_ARGV = re.compile(r'command:\s*\[\s*"(hyprconf-[^"]*)"')
OVERLAY_ONLY = (".local/bin", "@HYPRCONF_DIR@")


def publishable_problems(folder: Path) -> list[str]:
    """What would break the folder as a repository of its own, beyond what
    the validator checks. The two whys: Omarchy's MIT licence requires its
    NOTICE on every copy of its code, and a plugin installed by `omarchy
    plugin add` has no overlay around it — nothing of the installer's
    (~/.local/bin, @HYPRCONF_DIR@, a bare hyprconf-* argv) can work there."""
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
# Omarchy 4.0.2's Text rule
# ---------------------------------------------------------------------------
#
# A `Text` whose `text:` is a runtime string renders it as rich text under
# Qt's default AutoText: a window title, a device name or a feeder line
# carrying markup is parsed as HTML. Omarchy 4.0.2 added `textFormat:
# Text.PlainText` to its own stock widgets (shell/plugins/bar/widgets/
# ActiveWindow.qml:32, shell/Ui/WidgetButton.qml:77) and enforces it with a
# scan that lives in its git repository (test/shell.d/qml-text-format-scan.py),
# not in the package — so there is nothing on the box to call.
#
# The rule below is blunter than upstream's: every Text block declares the
# line, literal-only text included. That is stricter than it needs to be and
# has no exemptions to get wrong. One caveat if a future Omarchy clock ships a
# literal-only Text: modules/bar-clock/plugin/BarWidget.qml is byte-parity with
# the stock file (that module's parity test pins the exact deltas), so the file
# would be exempted here rather than gain a fourth delta.

TEXT_BLOCK = re.compile(r"(?:^|[:\s])(?:[A-Za-z_]\w*\.)?Text\s*\{")


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


def text_format_problems(path: Path) -> list[str]:
    """Every `Text {` block in `path` — `component X: Text {` included — that
    does not declare textFormat: Text.PlainText, brace-matched from its own
    opening brace."""
    code = "\n".join(_strip_comment(ln) for ln in path.read_text(encoding="utf-8").splitlines())
    rel = path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path
    problems = []
    for match in TEXT_BLOCK.finditer(code):
        depth, i = 1, match.end()
        while depth and i < len(code):
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        block = code[match.end() : i]
        if "textFormat: Text.PlainText" not in block:
            line = code.count("\n", 0, match.start()) + 1
            problems.append(f"{rel}:{line}: Text without textFormat: Text.PlainText")
    return problems


# Ui/PluginBarApi.qml and services/PluginShellApi.qml (Omarchy 4.0.3-1) — the
# facades an INSTALLED third-party widget gets in place of the host Bar and
# ShellRoot (plugins/bar/Bar.qml:2002-2003, shell.qml:739-743). Their public
# members are the whole contract: anything else a widget reads off `bar` is
# undefined at runtime and says nothing. Pinned here so CI (no Omarchy) still
# checks the plugins; where Omarchy is installed the real files are read, so
# an upstream narrowing turns this red on the box that can see it.
PLUGIN_BAR_API = (
    "activePopout",
    "background",
    "barForeground",
    "barSize",
    "centerHoverRevealSuppressed",
    "centerSectionRevealHeld",
    "clickTargets",
    "fontFamily",
    "foreground",
    "foregroundAnimationEnabled",
    "foreignPopoutMarker",
    "hideTooltip",
    "layoutConfig",
    "moduleName",
    "moduleWidgets",
    "pluginId",
    "position",
    "registerClickTarget",
    "releasePopout",
    "requestPopout",
    "run",
    "setCenterHoverRevealSuppressed",
    "shell",
    "showTooltip",
    "switchPanelFrom",
    "targetBelongsToWindow",
    "transparent",
    "unregisterClickTarget",
    "urgent",
    "vertical",
)
PLUGIN_SHELL_API = (
    "appLibrary",
    "bar",
    "barConfig",
    "firstPartyServiceFor",
    "hide",
    "idleConfig",
    "isPluginOpen",
    "mutateShellConfig",
    "pluginId",
    "pluginShellForBarEntry",
    "serviceFor",
    "summon",
    "toggle",
    "updateEntryInline",
)
# The installed tree, through the same seam every needs-Omarchy probe keys on
# (never a skip here: the pinned lists stand in where it is absent).
OMARCHY_SHELL = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
_DECLARES_RE = re.compile(
    r"^\s*(?:readonly\s+)?(?:required\s+)?(?:property\s+\S+|function)\s+(\w+)", re.M
)
# `bar.x`, `bar?.shell?.x`. `root.`/`this.` are stripped first so `root.bar.x`
# counts and `Style.bar.iconSlot` (a different `bar`) does not.
_OWNER_RE = re.compile(r"\b(?:root|this)\s*\??\.\s*")
_MEMBER_RE = re.compile(r"(?<![\w.])bar\s*\??\.\s*(?:shell\s*\??\.\s*)?([A-Za-z_]\w*)")


def _qml_code(qml: Path) -> str:
    """The file with its `//` comments stripped, so a scan cannot match the
    prose explaining the rule (the header names facade members it never calls)."""
    return "\n".join(_strip_comment(ln) for ln in qml.read_text().splitlines())


def _facade_members() -> tuple[set[str], set[str]]:
    """The installed facades' members, or the pinned lists where Omarchy is absent."""
    bar_api = OMARCHY_SHELL / "Ui" / "PluginBarApi.qml"
    shell_api = OMARCHY_SHELL / "services" / "PluginShellApi.qml"
    if bar_api.is_file() and shell_api.is_file():
        return (
            {m for m in _DECLARES_RE.findall(bar_api.read_text()) if not m.startswith("_")},
            {m for m in _DECLARES_RE.findall(shell_api.read_text()) if not m.startswith("_")},
        )
    return set(PLUGIN_BAR_API), set(PLUGIN_SHELL_API)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("folder", plugin_folders(), ids=folder_id)
def test_plugin_folders_satisfy_the_validator_contract(folder: Path) -> None:
    """omarchy-plugin-validate's every check, on every plugin folder, with no
    Omarchy needed — the contract `omarchy plugin add` gates a repository on,
    pinned where publishing is gated: CI. Each module also runs the real
    validator against its installed folder, which skips there."""
    assert validator_problems(folder) == []


def test_the_validator_port_refuses_what_the_validator_refuses(tmp_path: Path) -> None:
    """The port above is only worth its lines if it says no: a manifest with
    a reserved id, a missing entry point and a symlink inside the folder."""
    folder = tmp_path / "plugin"
    (folder / "sub").mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "id": "omarchy.clock",
                "name": "x",
                "version": "1.0.0",
                "kinds": ["bar-widget"],
                "entryPoints": {"barWidget": "Gone.qml"},
                "barWidget": {"defaultSection": "middle"},
            }
        )
    )
    (folder / "sub" / "link").symlink_to(folder / "manifest.json")
    problems = validator_problems(folder)
    assert any("invalid plugin id" in p for p in problems), problems
    assert any("not a relative path to a file here" in p for p in problems), problems
    assert any("defaultSection" in p for p in problems), problems
    assert any("symlink" in p for p in problems), problems


@pytest.mark.parametrize("folder", plugin_folders(), ids=folder_id)
def test_plugin_folders_are_publishable_on_their_own(folder: Path) -> None:
    """A folder split into its own repository (CONTRIBUTING › Publishing a
    plugin) carries everything it needs — manifest.json at its root, a README,
    Omarchy's NOTICE where the code is Omarchy's, the exec bit on a bundled
    feeder — and nothing of the overlay's around it."""
    assert publishable_problems(folder) == []
    manifest = json.loads((folder / "manifest.json").read_text())
    # Frozen, not a discipline: the validator checks the key's presence only
    # (bin/omarchy-plugin-validate:44-47), `omarchy plugin update` is a
    # fast-forward that never opens the manifest, and all 13 of Omarchy's own
    # plugin manifests sit at 1.0.0 (Omarchy 4.0.3-1).
    assert manifest["version"] == "1.0.0"


def test_plugin_text_never_renders_runtime_strings_as_rich_text() -> None:
    """Omarchy 4.0.2's rule over every QML the overlay ships (the why, and why
    the rule here is blunter than upstream's, sit beside the scan above)."""
    qml = sorted(p for folder in plugin_folders() for p in folder.rglob("*.qml"))
    assert qml, "no plugin QML found"
    problems = [p for path in qml for p in text_format_problems(path)]
    assert not problems, (
        "Text rendering a runtime value without textFormat: Text.PlainText:\n" + "\n".join(problems)
    )


def test_bar_widget_never_sizes_itself_off_its_parent() -> None:
    """A widget whose implicit size reads `parent` is invisible on the bar:
    Omarchy's ModuleSlot takes its height from the widget's implicit size, so
    `implicitHeight: parent.height` closes a binding loop, and QML breaks a
    loop by dropping the binding — zero height, nothing logged at any
    verbosity, only a gap in the bar."""
    qml = sorted(p for folder in plugin_folders() for p in folder.rglob("*.qml"))
    assert qml, "no plugin QML found"
    offenders = [
        f"{path.relative_to(REPO_ROOT)}: {line.strip()}"
        for path in qml
        for line in _qml_code(path).splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", line) and "parent" in line
    ]
    assert not offenders, (
        "Bar widget implicit size must not depend on `parent` (binding loop -> "
        "zero size -> invisible widget):\n" + "\n".join(offenders)
    )


def test_plugin_qml_parses() -> None:
    """A QML syntax error is an empty bar slot with nothing in any log.
    `qmllint --bare` parses without the module imports (exit 0 with import
    warnings on a good file, non-zero on a broken one)."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    for qml in sorted(p for folder in plugin_folders() for p in folder.rglob("*.qml")):
        proc = subprocess.run([qmllint, "--bare", str(qml)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{qml}: {proc.stderr}"


def test_widgets_read_only_what_the_plugin_facades_expose() -> None:
    """Every `bar.<x>` / `bar.shell.<x>` in a shipped widget is a facade member.

    An installed third-party widget never sees the host Bar or the ShellRoot
    (plugins/bar/Bar.qml:2002-2003 hands it pluginBarApiFor(...), and
    shell.qml:739-743 the scoped PluginShellApi), so a member that exists
    only on the Bar reads as undefined with nothing logged anywhere — the
    exact failure the 4.0.2 -> 4.0.3 host rewrite could have caused: the
    facades are the contract, and this is what pins the widgets to them.
    Never a skip — where Omarchy is absent the pinned lists stand in.
    """
    installed_bar, installed_shell = _facade_members()
    if (OMARCHY_SHELL / "Ui" / "PluginBarApi.qml").is_file():
        # Same test, no extra skip: where Omarchy is installed the pinned
        # lists are checked against it, so CI's fallback cannot drift.
        assert installed_bar == set(PLUGIN_BAR_API)
        assert installed_shell == set(PLUGIN_SHELL_API)
    allowed = installed_bar | installed_shell
    seen = set()
    for qml in sorted(p for folder in plugin_folders() for p in folder.glob("*.qml")):
        code = _OWNER_RE.sub("", _qml_code(qml))
        for member in _MEMBER_RE.findall(code):
            assert member in allowed, f"{qml}: bar.{member} is not on the facades"
            seen.add(member)
    # The scan is worthless if it matches nothing: these two are in the tree.
    assert {"serviceFor", "updateEntryInline"} <= seen
