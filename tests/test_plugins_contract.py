"""The contract every shipped plugin folder keeps, the same for all four bar modules: the
omarchy-plugin-validate port (CI has no Omarchy), the shape a folder needs as a repository of
its own, the Text and implicit-size rules, a qmllint parse, and the facade-member pin."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
FOLDERS = sorted(REPO_ROOT.glob("modules/*/plugin"))
assert FOLDERS, "no plugin folders found"
per_folder = pytest.mark.parametrize("folder", FOLDERS, ids=lambda f: f.parent.name)

# bin/omarchy-plugin-validate (Omarchy 4.0.3-1): its id regex, required fields and
# kind -> entry-point table.
PLUGIN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REQUIRED = ("id", "name", "version", "kinds", "entryPoints")
KIND_ENTRY_POINTS = {
    "bar": "bar",
    "bar-widget": "barWidget",
    "menu": "menu",
    "overlay": "overlay",
    "panel": "panel",
    "service": "service",
}
BARE_ARGV = re.compile(r'command:\s*\[\s*"(hyprconf-[^"]*)"')


def walk(folder: Path):
    """Every path under a plugin folder, .git pruned the way the validator prunes it."""
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in dirnames + sorted(filenames):
            yield Path(dirpath) / name


def validator_problems(folder: Path) -> list[str]:
    """What omarchy-plugin-validate refuses, check for check, plus the one thing its own
    `find` follows past: a symlink inside the folder. jq's `==` is type-aware: `true` is not 1."""
    path = folder / "manifest.json"
    if not path.is_file():
        return ["missing manifest.json"]
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"manifest.json is not valid JSON: {exc}"]
    if not isinstance(m, dict):
        return ["manifest.json is not a JSON object"]
    out = [f"manifest missing '{f}'" for f in REQUIRED if f not in m]
    schema = m.get("schemaVersion")
    if isinstance(schema, bool) or schema != 1:
        out.append("unsupported or missing schemaVersion (expected 1)")
    pid = m.get("id")
    if not isinstance(pid, str) or not pid:
        out.append("manifest 'id' is empty")
    elif not PLUGIN_ID_RE.match(pid) or ".." in pid or pid.startswith("omarchy."):
        out.append(f"invalid plugin id '{pid}'")
    kinds = m.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        out.append("'kinds' must be a non-empty array")
        kinds = []
    eps = m.get("entryPoints")
    if not isinstance(eps, dict):
        out.append("'entryPoints' must be an object")
        eps = {}
    widget = m.get("barWidget")
    if isinstance(widget, dict) and "defaultSection" in widget:
        if widget["defaultSection"] not in ("left", "center", "right"):
            out.append("'barWidget.defaultSection' must be left, center, or right")
    for key, ep in eps.items():
        if not isinstance(ep, str) or not ep:
            out.append(f"entry point '{key}' is empty")
        elif "\n" in ep or ep.startswith("/") or ".." in ep or not (folder / ep).is_file():
            out.append(f"entry point '{key}' is not a relative path to a file here: '{ep}'")
    for kind, ep_key in KIND_ENTRY_POINTS.items():
        if kind in kinds and ep_key not in eps:
            out.append(f"kind '{kind}' requires an 'entryPoints.{ep_key}' to load")
    out += [f"symlink inside the folder: {p}" for p in walk(folder) if p.is_symlink()]
    return out


def publishable_problems(folder: Path) -> list[str]:
    """What breaks the folder as a repository of its own: no README, no MIT NOTICE on a
    clonedFrom copy, a feeder without its exec bit, anything of the overlay's around it."""
    out = [] if (folder / "README.md").is_file() else ["no README.md at the folder root"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("omarchy", {}).get("clonedFrom") and not (folder / "NOTICE").is_file():
        out.append("a clonedFrom copy of Omarchy's MIT code with no NOTICE")
    for path in (p for p in walk(folder) if p.is_file()):
        rel, text = path.relative_to(folder), path.read_text(encoding="utf-8", errors="replace")
        out += [f"{rel} mentions {n}" for n in (".local/bin", "@HYPRCONF_DIR@") if n in text]
        if path.suffix == ".qml":
            out += [f"{rel} runs a bare {m.group(1)}" for m in BARE_ARGV.finditer(text)]
        if text.startswith("#!") and not os.access(path, os.X_OK):
            out.append(f"{rel} has a shebang but is not executable")
    return out


# Omarchy 4.0.2's Text rule (shell/plugins/bar/widgets/ActiveWindow.qml:32, shell/Ui/
# WidgetButton.qml:77; its scan lives in Omarchy's git repository, not the package): a runtime
# string renders markup under Qt's AutoText. Blunter here: every Text block declares the line.
TEXT_BLOCK = re.compile(r"(?:^|[:\s])(?:[A-Za-z_]\w*\.)?Text\s*\{")
COMMENT = re.compile(r"""("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|//.*$""")


def qml_code(path: Path) -> str:
    """The file with its `//` comments off (one inside a string stays)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(COMMENT.sub(lambda m: m.group(1) or "", ln) for ln in lines)


def text_format_problems(path: Path) -> list[str]:
    code, out = qml_code(path), []
    for match in TEXT_BLOCK.finditer(code):
        depth, i = 1, match.end()
        while depth and i < len(code):
            depth += {"{": 1, "}": -1}.get(code[i], 0)
            i += 1
        if "textFormat: Text.PlainText" not in code[match.end() : i]:
            out.append(f"{path.relative_to(REPO_ROOT)}:{code.count(chr(10), 0, match.start()) + 1}")
    return out


# Ui/PluginBarApi.qml and services/PluginShellApi.qml (Omarchy 4.0.3-1): the facades an
# INSTALLED third-party widget gets in place of the host Bar and ShellRoot (plugins/bar/
# Bar.qml:2002-2003, shell.qml:739-743). Their public members are the whole contract;
# anything else a widget reads off `bar` is undefined at runtime and says nothing. Where
# Omarchy is installed the real files are read and the pins checked against them.
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
OMARCHY_SHELL = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")) / "shell"
DECLARES_RE = re.compile(
    r"^\s*(?:readonly\s+)?(?:required\s+)?(?:property\s+\S+|function)\s+(\w+)", re.M
)
# `bar.x`, `bar?.shell?.x`; `root.`/`this.` stripped first, so `Style.bar.iconSlot` is not one.
OWNER_RE = re.compile(r"\b(?:root|this)\s*\??\.\s*")
MEMBER_RE = re.compile(r"(?<![\w.])bar\s*\??\.\s*(?:shell\s*\??\.\s*)?([A-Za-z_]\w*)")


@per_folder
def test_plugin_folder_is_valid_and_publishable_alone(folder: Path) -> None:
    """The contract `omarchy plugin add` gates a repository on, pinned where publishing is
    gated: CI. Each module also runs the real validator on its installed folder."""
    assert validator_problems(folder) + publishable_problems(folder) == []
    # Frozen: the validator checks presence only (bin/omarchy-plugin-validate:44-47),
    # `plugin update` is a fast-forward that never opens it, Omarchy's own 13 sit at 1.0.0.
    assert json.loads((folder / "manifest.json").read_text())["version"] == "1.0.0"


@per_folder
def test_plugin_text_never_renders_runtime_strings_as_rich_text(folder: Path) -> None:
    problems = [p for qml in sorted(folder.rglob("*.qml")) for p in text_format_problems(qml)]
    assert not problems, "Text without textFormat: Text.PlainText:\n" + "\n".join(problems)


@per_folder
def test_bar_widget_never_sizes_itself_off_its_parent(folder: Path) -> None:
    """Omarchy's ModuleSlot takes its height from the widget's implicit size, so
    `implicitHeight: parent.height` is a binding loop QML drops: zero height, nothing logged."""
    offenders = [
        f"{qml.relative_to(REPO_ROOT)}: {ln.strip()}"
        for qml in sorted(folder.rglob("*.qml"))
        for ln in qml_code(qml).splitlines()
        if re.match(r"\s*implicit(Width|Height)\s*:", ln) and "parent" in ln
    ]
    assert not offenders, "implicit size off `parent`:\n" + "\n".join(offenders)


@per_folder
def test_plugin_qml_parses(folder: Path) -> None:
    """A QML syntax error is an empty bar slot with nothing in any log. `qmllint --bare`
    parses without the module imports."""
    qmllint = shutil.which("qmllint") or shutil.which("qmllint", path="/usr/lib/qt6/bin")
    if qmllint is None:
        pytest.skip("no qmllint (qt6-declarative) to parse the plugin QML")
    for qml in sorted(folder.rglob("*.qml")):
        proc = subprocess.run([qmllint, "--bare", str(qml)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{qml}: {proc.stderr}"


def test_widgets_read_only_what_the_plugin_facades_expose() -> None:
    """Every `bar.<x>` / `bar.shell.<x>` in a shipped widget is a facade member. Never a
    skip: where Omarchy is absent the pinned lists stand in."""
    bar_api = OMARCHY_SHELL / "Ui/PluginBarApi.qml"
    shell_api = OMARCHY_SHELL / "services/PluginShellApi.qml"
    allowed = set(PLUGIN_BAR_API) | set(PLUGIN_SHELL_API)
    if bar_api.is_file() and shell_api.is_file():
        declared = lambda f: {m for m in DECLARES_RE.findall(f.read_text()) if m[0] != "_"}  # noqa: E731
        assert declared(bar_api) == set(PLUGIN_BAR_API)
        assert declared(shell_api) == set(PLUGIN_SHELL_API)
    seen = set()
    for qml in sorted(p for folder in FOLDERS for p in folder.glob("*.qml")):
        for member in MEMBER_RE.findall(OWNER_RE.sub("", qml_code(qml))):
            assert member in allowed, f"{qml}: bar.{member} is not on the facades"
            seen.add(member)
    assert {"serviceFor", "updateEntryInline"} <= seen, "the scan matched nothing it should"
