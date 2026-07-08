"""Static theme-consistency checks for the quickshell QML tree.

Every color in the bar must come from the Theme singleton (or be derived
from it via Qt.rgba) so all 68 themes render correctly. Hardcoded palette
hex regressed repeatedly during the waybar migration: a #ffffff battery
"normal" class was invisible on light themes, and gruvbox literals were
pinned into the calendar, tray menu, and volume slider. The only permitted
literal is "#ffffff", used deliberately for text sitting on accent-colored
fills (Control Center tiles / Join button), where white is the design
regardless of theme.

Theme.qml itself is exempt: it defines the palette, including the static
hex fallbacks used when a theme JSON omits a key.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
QML_DIR = REPO_ROOT / "stow" / "quickshell" / ".config" / "quickshell"

_HEX_LITERAL = re.compile(r'"#[0-9a-fA-F]{3,8}"')
_ALLOWED = {"#ffffff"}


def test_qml_tree_exists() -> None:
    assert QML_DIR.is_dir()
    assert (QML_DIR / "Theme.qml").is_file()


def test_no_hardcoded_palette_hex_outside_theme() -> None:
    offenders: list[str] = []
    for qml in sorted(QML_DIR.glob("*.qml")):
        if qml.name == "Theme.qml":
            continue
        for lineno, line in enumerate(qml.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//", 1)[0]  # ignore comments
            for match in _HEX_LITERAL.findall(code):
                if match.strip('"').lower() not in _ALLOWED:
                    offenders.append(f"{qml.name}:{lineno}: {match}")
    assert not offenders, (
        "Hardcoded palette colors in QML (use Theme tokens or Qt.rgba(Theme.*) "
        "so every theme renders correctly):\n  " + "\n  ".join(offenders)
    )
