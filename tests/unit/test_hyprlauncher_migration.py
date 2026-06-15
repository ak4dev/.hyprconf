"""
Tests for the wofi → hyprlauncher migration.

Covers:
- packages file: hyperlauncher present, wofi absent
- hyprland.conf: $menu uses hyprlauncher, not wofi
- keybinds.conf: clipboard bind uses hyprlauncher --dmenu
- hyprlauncher.conf: config file exists and has required keys
- switch_theme.py: update_wofi removed, launcher_select present,
  --pick flag present, --wofi absent, launcher_select uses hyprlauncher
- hyprconf bin: theme pick subcommand invokes --pick
- stow/wofi: package removed
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
PACKAGES_FILE = REPO_ROOT / "packages"
HYPRLAND_CONF = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "hyprland.conf"
KEYBINDS_CONF = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "keybinds.conf"
HYPRLAUNCHER_CONF = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "hyprlauncher.conf"
SWITCH_THEME = (
    REPO_ROOT
    / "stow"
    / "hypr"
    / ".config"
    / "hypr"
    / "scripts"
    / "theme-switcher"
    / "switch_theme.py"
)
HYPRCONF_BIN = REPO_ROOT / "stow" / "hypr" / ".local" / "bin" / "hyprconf"
WOFI_STOW_DIR = REPO_ROOT / "stow" / "wofi"


# ---------------------------------------------------------------------------
# packages
# ---------------------------------------------------------------------------


def test_packages_contains_hyprlauncher() -> None:
    """hyperlauncher must be listed in packages."""
    text = PACKAGES_FILE.read_text()
    non_comment_lines = [
        l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")
    ]
    assert "hyprlauncher" in non_comment_lines, "hyprlauncher must be in the packages file"


def test_packages_does_not_contain_wofi() -> None:
    """wofi must not appear as an active (non-commented) package."""
    non_comment_lines = [
        l.strip()
        for l in PACKAGES_FILE.read_text().splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    assert "wofi" not in non_comment_lines, (
        "wofi must be removed from packages; hyprlauncher is the launcher now"
    )


# ---------------------------------------------------------------------------
# hyprland.conf — $menu variable
# ---------------------------------------------------------------------------


def test_hyprland_conf_menu_uses_hyprlauncher() -> None:
    """$menu in hyprland.conf must invoke hyprlauncher."""
    text = HYPRLAND_CONF.read_text()
    match = re.search(r"^\$menu\s*=\s*(.+)$", text, re.MULTILINE)
    assert match, "$menu variable not found in hyprland.conf"
    value = match.group(1).strip()
    assert "hyprlauncher" in value, f"$menu must use hyprlauncher, got: {value!r}"


def test_hyprland_conf_menu_does_not_use_wofi() -> None:
    """$menu in hyprland.conf must not invoke wofi."""
    text = HYPRLAND_CONF.read_text()
    match = re.search(r"^\$menu\s*=\s*(.+)$", text, re.MULTILINE)
    assert match, "$menu variable not found in hyprland.conf"
    value = match.group(1).strip()
    assert "wofi" not in value, f"$menu must not contain wofi, got: {value!r}"


# ---------------------------------------------------------------------------
# keybinds.conf — clipboard history
# ---------------------------------------------------------------------------


def test_keybinds_clipboard_uses_hyprlauncher() -> None:
    """Clipboard history bind must pipe through hyprlauncher --dmenu."""
    text = KEYBINDS_CONF.read_text()
    clipboard_lines = [l for l in text.splitlines() if "cliphist" in l and "dmenu" in l.lower()]
    assert clipboard_lines, "No cliphist dmenu bind found in keybinds.conf"
    for line in clipboard_lines:
        assert "hyprlauncher" in line, (
            f"Clipboard bind must use hyprlauncher --dmenu, got: {line!r}"
        )
        assert "wofi" not in line, f"Clipboard bind must not reference wofi, got: {line!r}"


def test_keybinds_clipboard_uses_dmenu_flag() -> None:
    """hyperlauncher must be called with --dmenu in the clipboard bind."""
    text = KEYBINDS_CONF.read_text()
    clipboard_lines = [l for l in text.splitlines() if "cliphist" in l and "hyprlauncher" in l]
    assert clipboard_lines, "No cliphist + hyprlauncher bind found in keybinds.conf"
    for line in clipboard_lines:
        assert "--dmenu" in line, (
            f"hyprlauncher must be called with --dmenu in clipboard bind, got: {line!r}"
        )


# ---------------------------------------------------------------------------
# hyprlauncher.conf
# ---------------------------------------------------------------------------


def test_hyprlauncher_conf_exists() -> None:
    """hyprlauncher.conf must exist in stow/hypr/.config/hypr/."""
    assert HYPRLAUNCHER_CONF.exists(), (
        f"hyprlauncher.conf not found at {HYPRLAUNCHER_CONF}; "
        "it must be tracked in stow/hypr/ so it is deployed on install"
    )


def test_hyprlauncher_conf_has_general_section() -> None:
    """hyprlauncher.conf must have a general {{ ... }} section."""
    text = HYPRLAUNCHER_CONF.read_text()
    assert re.search(r"^general\s*\{", text, re.MULTILINE), (
        "hyprlauncher.conf must contain a general { } section"
    )


def test_hyprlauncher_conf_has_cache_section() -> None:
    """hyprlauncher.conf must have a cache {{ ... }} section."""
    text = HYPRLAUNCHER_CONF.read_text()
    assert re.search(r"^cache\s*\{", text, re.MULTILINE), (
        "hyprlauncher.conf must contain a cache { } section"
    )


def test_hyprlauncher_conf_has_finders_section() -> None:
    """hyprlauncher.conf must have a finders {{ ... }} section."""
    text = HYPRLAUNCHER_CONF.read_text()
    assert re.search(r"^finders\s*\{", text, re.MULTILINE), (
        "hyprlauncher.conf must contain a finders { } section"
    )


def test_hyprlauncher_conf_has_ui_section() -> None:
    """hyprlauncher.conf must have a ui {{ ... }} section."""
    text = HYPRLAUNCHER_CONF.read_text()
    assert re.search(r"^ui\s*\{", text, re.MULTILINE), (
        "hyprlauncher.conf must contain a ui { } section"
    )


def test_hyprlauncher_conf_grab_focus_enabled() -> None:
    """grab_focus must be set to true for reliable keyboard behaviour."""
    text = HYPRLAUNCHER_CONF.read_text()
    match = re.search(r"grab_focus\s*=\s*(\S+)", text)
    assert match, "grab_focus not set in hyprlauncher.conf"
    assert match.group(1).lower() == "true", (
        f"grab_focus should be true for reliable keyboard focus, got: {match.group(1)!r}"
    )


def test_hyprlauncher_conf_cache_enabled() -> None:
    """cache.enabled must be true so launch frequency is remembered."""
    text = HYPRLAUNCHER_CONF.read_text()
    match = re.search(r"enabled\s*=\s*(\S+)", text)
    assert match, "cache enabled not set in hyprlauncher.conf"
    assert match.group(1).lower() == "true", (
        f"cache.enabled should be true, got: {match.group(1)!r}"
    )


def test_hyprlauncher_conf_desktop_icons_enabled() -> None:
    """desktop_icons must be enabled for a rich app-picker experience."""
    text = HYPRLAUNCHER_CONF.read_text()
    match = re.search(r"desktop_icons\s*=\s*(\S+)", text)
    assert match, "desktop_icons not set in hyprlauncher.conf"
    assert match.group(1).lower() == "true", (
        f"desktop_icons should be true, got: {match.group(1)!r}"
    )


def test_hyprlauncher_conf_window_size_specified() -> None:
    """window_size must be explicitly set in the ui section."""
    text = HYPRLAUNCHER_CONF.read_text()
    assert re.search(r"window_size\s*=\s*\d+\s+\d+", text), (
        "window_size must be set in the ui section of hyprlauncher.conf (e.g. 560 380)"
    )


# ---------------------------------------------------------------------------
# stow/wofi removal
# ---------------------------------------------------------------------------


def test_wofi_stow_package_removed() -> None:
    """stow/wofi directory must not exist — wofi has been replaced by hyprlauncher."""
    assert not WOFI_STOW_DIR.exists(), (
        "stow/wofi/ still exists; it must be removed as part of the hyprlauncher migration"
    )


# ---------------------------------------------------------------------------
# switch_theme.py — update_wofi removed, launcher_select present
# ---------------------------------------------------------------------------


def test_switch_theme_has_no_update_wofi() -> None:
    """update_wofi() must be removed from switch_theme.py — hyprlauncher uses hyprtoolkit theming."""
    text = SWITCH_THEME.read_text()
    assert not re.search(r"^def update_wofi\b", text, re.MULTILINE), (
        "update_wofi() must be removed; hyprlauncher handles its own theming via hyprtoolkit"
    )


def test_switch_theme_has_launcher_select() -> None:
    """launcher_select() must exist in switch_theme.py."""
    text = SWITCH_THEME.read_text()
    assert re.search(r"^def launcher_select\b", text, re.MULTILINE), (
        "launcher_select() function not found in switch_theme.py"
    )


def test_switch_theme_launcher_select_uses_hyprlauncher() -> None:
    """launcher_select() must call hyprlauncher --dmenu, not wofi."""
    text = SWITCH_THEME.read_text()
    # Extract launcher_select function body
    match = re.search(
        r"def launcher_select\(.*?\n(.*?)^(?:def |\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert match, "launcher_select() not found"
    body = match.group(1)
    assert "hyprlauncher" in body, "launcher_select must invoke hyprlauncher"
    assert "--dmenu" in body, "launcher_select must use --dmenu flag"
    assert "wofi" not in body, "launcher_select must not reference wofi"


def test_switch_theme_no_wofi_in_apply_theme() -> None:
    """apply_theme() must not call update_wofi()."""
    text = SWITCH_THEME.read_text()
    apply_match = re.search(
        r"def apply_theme\(.*?\n(.*?)^(?:def |\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert apply_match, "apply_theme() not found in switch_theme.py"
    body = apply_match.group(1)
    assert "update_wofi" not in body, (
        "apply_theme() must not call update_wofi(); it has been removed"
    )


def test_switch_theme_has_pick_flag() -> None:
    """switch_theme.py must have a --pick argument (not --wofi)."""
    text = SWITCH_THEME.read_text()
    assert re.search(r'"--pick"', text), "--pick argument not found in switch_theme.py argparse"


def test_switch_theme_has_no_wofi_flag() -> None:
    """switch_theme.py must not have a --wofi argument (replaced by --pick)."""
    text = SWITCH_THEME.read_text()
    # Ignore comments
    non_comment = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    assert '"--wofi"' not in non_comment, (
        "--wofi argument must be removed from switch_theme.py; use --pick instead"
    )


# ---------------------------------------------------------------------------
# hyprconf bin — theme pick
# ---------------------------------------------------------------------------


def test_hyprconf_bin_theme_pick_uses_pick_flag() -> None:
    """hyprconf theme pick must invoke switch_theme.py --pick."""
    text = HYPRCONF_BIN.read_text()
    match = re.search(r"pick\)\s+.*?--(\w+)", text)
    assert match, "pick) case not found in hyprconf bin"
    flag = match.group(1)
    assert flag == "pick", f"hyprconf theme pick should call switch_theme.py --pick, got --{flag}"


def test_hyprconf_bin_theme_pick_help_mentions_hyprlauncher() -> None:
    """hyprconf help text for 'theme pick' must reference hyprlauncher."""
    text = HYPRCONF_BIN.read_text()
    pick_help_lines = [l for l in text.splitlines() if "theme pick" in l]
    assert pick_help_lines, "'theme pick' help line not found in hyprconf bin"
    for line in pick_help_lines:
        assert "hyprlauncher" in line.lower() or "launcher" in line.lower(), (
            f"'theme pick' help must mention hyprlauncher, got: {line!r}"
        )


def test_hyprconf_bin_no_wofi_reference() -> None:
    """hyprconf bin must not reference wofi anywhere (active code or help text)."""
    text = HYPRCONF_BIN.read_text()
    non_comment = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
    assert "wofi" not in non_comment, (
        "hyprconf bin must not reference wofi; hyprlauncher is the launcher"
    )


# ---------------------------------------------------------------------------
# launcher_select() functional: mock subprocess
# ---------------------------------------------------------------------------

_THEME_SCRIPT_DIR = SWITCH_THEME.parent
sys.path.insert(0, str(_THEME_SCRIPT_DIR))


def _import_switch_theme():
    """Import switch_theme dynamically (it's not a proper package)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("switch_theme", SWITCH_THEME)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def st():
    """Lazily imported switch_theme module."""
    return _import_switch_theme()


def test_launcher_select_returns_theme_on_valid_selection(st, tmp_path) -> None:
    """launcher_select returns the chosen theme name when hyprlauncher exits 0."""
    with (
        patch.object(st.subprocess, "run") as mock_run,
        patch.object(st, "get_all_themes", return_value=["dracula", "gruvbox"]),
        patch.object(st, "read_state", return_value="dracula"),
    ):
        mock_run.return_value = MagicMock(stdout="   gruvbox\n", returncode=0)
        result = st.launcher_select()
    assert result == "gruvbox"


def test_launcher_select_marks_current_theme_with_star(st) -> None:
    """launcher_select passes the current theme marked with ★ to hyprlauncher."""
    captured_input = {}

    def fake_run(cmd, **kwargs):
        captured_input["input"] = kwargs.get("input", "")
        return MagicMock(stdout="", returncode=0)

    with (
        patch.object(st.subprocess, "run", side_effect=fake_run),
        patch.object(st, "get_all_themes", return_value=["dracula", "gruvbox"]),
        patch.object(st, "read_state", return_value="dracula"),
    ):
        st.launcher_select()

    lines = captured_input["input"].splitlines()
    assert any("★" in l and "dracula" in l for l in lines), (
        "Current theme must be marked with ★ in the dmenu input"
    )


def test_launcher_select_returns_none_when_no_selection(st) -> None:
    """launcher_select returns None when hyprlauncher dmenu produces no output."""
    with (
        patch.object(st.subprocess, "run") as mock_run,
        patch.object(st, "get_all_themes", return_value=["dracula", "gruvbox"]),
        patch.object(st, "read_state", return_value="dracula"),
    ):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        result = st.launcher_select()
    assert result is None


def test_launcher_select_filters_themes(st) -> None:
    """launcher_select respects initial_filter to narrow the theme list."""
    captured_input = {}

    def fake_run(cmd, **kwargs):
        captured_input["input"] = kwargs.get("input", "")
        return MagicMock(stdout="", returncode=0)

    with (
        patch.object(st.subprocess, "run", side_effect=fake_run),
        patch.object(st, "get_all_themes", return_value=["dracula", "gruvbox", "ai:void"]),
        patch.object(st, "read_state", return_value=None),
    ):
        st.launcher_select(initial_filter="ai:")

    themes_shown = [
        l.strip().lstrip("★").strip().lstrip("☀☾").strip()
        for l in captured_input["input"].splitlines()
    ]
    assert themes_shown == ["ai:void"], (
        f"Only ai: themes should be shown with filter 'ai:', got: {themes_shown}"
    )


def test_launcher_select_falls_back_to_tui_when_not_found(st) -> None:
    """launcher_select falls back to interactive_select when hyprlauncher is not installed."""
    with (
        patch.object(st.subprocess, "run", side_effect=FileNotFoundError),
        patch.object(st, "get_all_themes", return_value=["dracula"]),
        patch.object(st, "read_state", return_value=None),
        patch.object(st, "interactive_select", return_value="dracula") as mock_interactive,
    ):
        result = st.launcher_select()

    mock_interactive.assert_called_once()
    assert result == "dracula"


def test_launcher_select_calls_hyprlauncher_dmenu(st) -> None:
    """launcher_select must invoke hyprlauncher with --dmenu."""
    called_with = {}

    def fake_run(cmd, **kwargs):
        called_with["cmd"] = cmd
        return MagicMock(stdout="", returncode=0)

    with (
        patch.object(st.subprocess, "run", side_effect=fake_run),
        patch.object(st, "get_all_themes", return_value=["dracula"]),
        patch.object(st, "read_state", return_value=None),
    ):
        st.launcher_select()

    assert called_with.get("cmd"), "subprocess.run was not called"
    assert "hyprlauncher" in called_with["cmd"][0], (
        f"launcher_select must call hyprlauncher, got: {called_with['cmd']}"
    )
    assert "--dmenu" in called_with["cmd"], (
        f"launcher_select must use --dmenu, got: {called_with['cmd']}"
    )


# ---------------------------------------------------------------------------
# update_hyprtoolkit() — functional tests
# ---------------------------------------------------------------------------

SWITCH_THEME_HYPRTOOLKIT = (
    REPO_ROOT
    / "stow"
    / "hypr"
    / ".config"
    / "hypr"
    / "scripts"
    / "theme-switcher"
    / "switch_theme.py"
)


def test_switch_theme_has_update_hyprtoolkit() -> None:
    """update_hyprtoolkit() must exist in switch_theme.py."""
    text = SWITCH_THEME_HYPRTOOLKIT.read_text()
    assert re.search(r"^def update_hyprtoolkit\b", text, re.MULTILINE), (
        "update_hyprtoolkit() not found in switch_theme.py"
    )


def test_update_hyprtoolkit_called_in_apply_theme() -> None:
    """apply_theme() must call update_hyprtoolkit()."""
    text = SWITCH_THEME_HYPRTOOLKIT.read_text()
    match = re.search(
        r"def apply_theme\(.*?\n(.*?)^(?:def |\Z)",
        text,
        re.DOTALL | re.MULTILINE,
    )
    assert match, "apply_theme() not found"
    assert "update_hyprtoolkit" in match.group(1), "apply_theme() must call update_hyprtoolkit()"


def test_update_hyprtoolkit_writes_correct_keys(st, tmp_path) -> None:
    """update_hyprtoolkit() writes background, accent, icon_theme etc."""
    out = tmp_path / "hyprtoolkit.conf"
    with patch.object(st, "HYPRTOOLKIT_CONF_FILE", str(out)):
        st.update_hyprtoolkit(
            {
                "background": "#1e1e2e",
                "foreground": "#cdd6f4",
                "accent": "#89b4fa",
                "comment": "#6c7086",
            }
        )
    content = out.read_text()
    assert "background" in content
    assert "accent" in content
    assert "icon_theme" in content
    assert "font_family" in content


def test_update_hyprtoolkit_dark_theme_uses_papirus_dark(st, tmp_path) -> None:
    """Dark background → icon_theme = Papirus-Dark."""
    out = tmp_path / "hyprtoolkit.conf"
    with patch.object(st, "HYPRTOOLKIT_CONF_FILE", str(out)):
        st.update_hyprtoolkit({"background": "#1e1e2e", "foreground": "#fff", "accent": "#89b4fa"})
    assert "Papirus-Dark" in out.read_text()


def test_update_hyprtoolkit_light_theme_uses_papirus_light(st, tmp_path) -> None:
    """Light background → icon_theme = Papirus-Light."""
    out = tmp_path / "hyprtoolkit.conf"
    with patch.object(st, "HYPRTOOLKIT_CONF_FILE", str(out)):
        st.update_hyprtoolkit({"background": "#ffffff", "foreground": "#000", "accent": "#0066cc"})
    assert "Papirus-Light" in out.read_text()


def test_update_hyprtoolkit_argb_format(st, tmp_path) -> None:
    """Colors must be written in 0xAARRGGBB format."""
    out = tmp_path / "hyprtoolkit.conf"
    with patch.object(st, "HYPRTOOLKIT_CONF_FILE", str(out)):
        st.update_hyprtoolkit(
            {"background": "#282a36", "foreground": "#f8f8f2", "accent": "#bd93f9"}
        )
    content = out.read_text()
    assert re.search(r"0x[0-9A-F]{8}", content), "Colors must use 0xAARRGGBB ARGB hex notation"


def test_hyprtoolkit_conf_not_in_stow() -> None:
    """hyprtoolkit.conf must NOT be tracked in stow — it's generated by switch_theme.py."""
    stow_path = REPO_ROOT / "stow" / "hypr" / ".config" / "hypr" / "hyprtoolkit.conf"
    assert not stow_path.exists(), (
        "stow/hypr/.config/hypr/hyprtoolkit.conf must not exist — "
        "it is generated at runtime by update_hyprtoolkit() and must not be a stow symlink"
    )


# ── seed_hicolor_index ──────────────────────────────────────────────────────


class TestSeedHicolorIndex:
    """Tests for the seed_hicolor_index() function in setup.sh."""

    SETUP_SH = REPO_ROOT / "setup.sh"

    def test_seed_hicolor_index_function_exists(self) -> None:
        """setup.sh must define seed_hicolor_index()."""
        src = self.SETUP_SH.read_text()
        assert "seed_hicolor_index()" in src

    def _run_seed(self, tmp_path: Path) -> subprocess.CompletedProcess[str]:
        """Extract seed_hicolor_index from setup.sh and run it in isolation."""
        import os
        import subprocess
        import tempfile

        # Extract just the function body + a stub for log_ok so no full source is needed
        fn_script = tempfile.NamedTemporaryFile(
            mode="w", suffix=".sh", delete=False, dir=str(tmp_path)
        )
        fn_script.write("#!/usr/bin/env bash\nset -euo pipefail\n")
        fn_script.write("log_ok() { :; }\n")
        # awk: print lines from seed_hicolor_index() definition through its closing `}`
        import subprocess as _sp

        extract = _sp.run(
            ["awk", "/^seed_hicolor_index\\(\\)/,/^\\}$/", str(self.SETUP_SH)],
            capture_output=True,
            text=True,
        )
        fn_script.write(extract.stdout)
        fn_script.write("\nseed_hicolor_index\n")
        fn_script.flush()
        env = {**os.environ, "HOME": str(tmp_path)}
        return subprocess.run(["bash", fn_script.name], capture_output=True, text=True, env=env)

    def test_seed_hicolor_index_creates_index_theme(self, tmp_path: Path) -> None:
        """seed_hicolor_index() creates index.theme when missing."""
        result = self._run_seed(tmp_path)
        index = tmp_path / ".local" / "share" / "icons" / "hicolor" / "index.theme"
        assert index.exists(), f"index.theme not created; stderr={result.stderr[:500]}"

    def test_seed_hicolor_index_theme_has_required_sections(self, tmp_path: Path) -> None:
        """The generated index.theme must list all required app-icon directories."""
        self._run_seed(tmp_path)
        content = (tmp_path / ".local" / "share" / "icons" / "hicolor" / "index.theme").read_text()
        for size in ("16x16/apps", "32x32/apps", "48x48/apps", "256x256/apps"):
            assert size in content, f"{size} missing from generated index.theme"
        assert "[Icon Theme]" in content

    def test_seed_hicolor_index_idempotent(self, tmp_path: Path) -> None:
        """Running seed_hicolor_index() twice must not overwrite an existing index.theme."""
        self._run_seed(tmp_path)
        index = tmp_path / ".local" / "share" / "icons" / "hicolor" / "index.theme"
        first_content = index.read_text()
        index.write_text(first_content + "\n# sentinel")
        self._run_seed(tmp_path)
        assert "# sentinel" in index.read_text(), (
            "seed_hicolor_index() must not overwrite an existing index.theme"
        )

    def test_seed_hicolor_index_called_in_main_flow(self) -> None:
        """seed_hicolor_index must be called in the main setup flow."""
        src = self.SETUP_SH.read_text()
        # Find the main() function body and check the call is present
        main_idx = src.index("main()")
        assert "seed_hicolor_index" in src[main_idx:], (
            "seed_hicolor_index() not called in main() setup flow"
        )

    def test_seed_hicolor_index_called_in_sync_flow(self) -> None:
        """seed_hicolor_index must be called in the --sync code path."""
        src = self.SETUP_SH.read_text()
        sync_idx = src.index('"--sync"')
        # Next occurrence of seed_hicolor_index after the --sync block opening
        assert "seed_hicolor_index" in src[sync_idx : sync_idx + 1500], (
            "seed_hicolor_index() not called in --sync flow"
        )

    def test_seed_hicolor_index_called_in_repair_flow(self) -> None:
        """seed_hicolor_index must be called in the --repair / repair_install() path."""
        src = self.SETUP_SH.read_text()
        repair_idx = src.index("repair_install()")
        assert "seed_hicolor_index" in src[repair_idx : repair_idx + 3000], (
            "seed_hicolor_index() not called in repair_install() flow"
        )
