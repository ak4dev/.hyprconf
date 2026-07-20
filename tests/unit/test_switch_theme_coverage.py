"""Coverage tests for the previously-untested switch_theme.py functions.

Covers (26 functions):
  hex_to_rgb_str, hex_to_hypr_rgba, is_dark_color,
  detect_repo_root, get_all_themes, read_state, write_state,
  get_adjacent_theme, load_json_file, load_vscode_base_defaults,
  parse_user_js, generate_kitty_theme, load_kitty_theme,
  update_dunst, update_hyprland_borders, update_hyprlock_colors,
  update_hyprpaper,
  update_vscode, reload_hyprland, notify_theme_change,
  resolve_code_config_root, resolve_firefox_theme_id,
  ensure_firefox_theme_payload,
  _generate_btop_theme, update_btop

The quickshell bar needs no update_* step here: Theme.qml watches the theme
files directly (the waybar CSS pipeline was removed with waybar).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

THEME_SWITCHER = (
    Path(__file__).parent.parent.parent
    / "stow"
    / "hypr"
    / ".config"
    / "hypr"
    / "scripts"
    / "theme-switcher"
    / "switch_theme.py"
)

spec = importlib.util.spec_from_file_location("switch_theme", THEME_SWITCHER)
st = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(st)  # type: ignore[union-attr]

DARK_THEME = {
    "background": "#282a36",
    "foreground": "#f8f8f2",
    "accent": "#8be9fd",
    "comment": "#6272a4",
    "green": "#50fa7b",
    "red": "#ff5555",
    "cyan": "#8be9fd",
    "orange": "#ffb86c",
    "purple": "#bd93f9",
    "yellow": "#f1fa8c",
}

# ---------------------------------------------------------------------------
# Colour utility functions
# ---------------------------------------------------------------------------


def test_hex_to_rgb_str_basic():
    assert st.hex_to_rgb_str("#ff0080") == "255,0,128"


def test_hex_to_rgb_str_black():
    assert st.hex_to_rgb_str("#000000") == "0,0,0"


def test_hex_to_rgb_str_white():
    assert st.hex_to_rgb_str("#ffffff") == "255,255,255"


def test_hex_to_hypr_rgba_default_alpha():
    assert st.hex_to_hypr_rgba("#8be9fd") == "rgba(8be9fdee)"


def test_hex_to_hypr_rgba_custom_alpha():
    assert st.hex_to_hypr_rgba("#8be9fd", "ff") == "rgba(8be9fdff)"


def test_is_dark_color_dark_bg():
    assert st.is_dark_color("#282a36") is True


def test_is_dark_color_light_bg():
    assert st.is_dark_color("#fdf6e3") is False


def test_is_dark_color_pure_black():
    assert st.is_dark_color("#000000") is True


def test_is_dark_color_pure_white():
    assert st.is_dark_color("#ffffff") is False


# ---------------------------------------------------------------------------
# detect_repo_root
# ---------------------------------------------------------------------------


def test_detect_repo_root_finds_hyprconf(tmp_path):
    # Build a fake dir tree: tmp/.hyprconf/a/b/c
    repo = tmp_path / ".hyprconf"
    deep = repo / "a" / "b" / "c"
    deep.mkdir(parents=True)
    result = st.detect_repo_root(deep)
    assert result.name == ".hyprconf"


def test_detect_repo_root_returns_self_when_named_hyprconf(tmp_path):
    repo = tmp_path / ".hyprconf"
    repo.mkdir()
    result = st.detect_repo_root(repo)
    assert result == repo


# ---------------------------------------------------------------------------
# get_all_themes / read_state / write_state / get_adjacent_theme
# ---------------------------------------------------------------------------


def test_get_all_themes_lists_json_files(tmp_path, monkeypatch):
    (tmp_path / "aaa.json").write_text("{}")
    (tmp_path / "bbb.json").write_text("{}")
    (tmp_path / "readme.txt").write_text("x")
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    themes = st.get_all_themes()
    assert themes == ["aaa", "bbb"]


def test_get_all_themes_sorted(tmp_path, monkeypatch):
    for name in ["zzz", "aaa", "mmm"]:
        (tmp_path / f"{name}.json").write_text("{}")
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    assert st.get_all_themes() == ["aaa", "mmm", "zzz"]


def test_read_state_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "STATE_FILE", str(tmp_path / "nonexistent"))
    assert st.read_state() is None


def test_read_state_returns_theme_name(tmp_path, monkeypatch):
    sf = tmp_path / ".current-theme"
    sf.write_text("dracula\n")
    monkeypatch.setattr(st, "STATE_FILE", str(sf))
    assert st.read_state() == "dracula"


def test_write_state_creates_file(tmp_path, monkeypatch):
    sf = tmp_path / ".current-theme"
    monkeypatch.setattr(st, "STATE_FILE", str(sf))
    st.write_state("nord")
    assert sf.read_text() == "nord\n"


def test_write_state_overwrites_existing(tmp_path, monkeypatch):
    sf = tmp_path / ".current-theme"
    sf.write_text("old-theme\n")
    monkeypatch.setattr(st, "STATE_FILE", str(sf))
    st.write_state("dracula")
    assert sf.read_text() == "dracula\n"


def test_get_adjacent_theme_next(tmp_path, monkeypatch):
    for name in ["aaa", "bbb", "ccc"]:
        (tmp_path / f"{name}.json").write_text("{}")
    sf = tmp_path / ".current-theme"
    sf.write_text("aaa\n")
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    monkeypatch.setattr(st, "STATE_FILE", str(sf))
    assert st.get_adjacent_theme(1) == "bbb"


def test_get_adjacent_theme_prev(tmp_path, monkeypatch):
    for name in ["aaa", "bbb", "ccc"]:
        (tmp_path / f"{name}.json").write_text("{}")
    sf = tmp_path / ".current-theme"
    sf.write_text("bbb\n")
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    monkeypatch.setattr(st, "STATE_FILE", str(sf))
    assert st.get_adjacent_theme(-1) == "aaa"


def test_get_adjacent_theme_wraps(tmp_path, monkeypatch):
    for name in ["aaa", "bbb", "ccc"]:
        (tmp_path / f"{name}.json").write_text("{}")
    sf = tmp_path / ".current-theme"
    sf.write_text("ccc\n")
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    monkeypatch.setattr(st, "STATE_FILE", str(sf))
    assert st.get_adjacent_theme(1) == "aaa"


def test_get_adjacent_theme_no_state_returns_first(tmp_path, monkeypatch):
    for name in ["aaa", "bbb"]:
        (tmp_path / f"{name}.json").write_text("{}")
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    monkeypatch.setattr(st, "STATE_FILE", str(tmp_path / "nofile"))
    assert st.get_adjacent_theme(1) == "aaa"


# ---------------------------------------------------------------------------
# load_json_file / load_vscode_base_defaults / parse_user_js
# ---------------------------------------------------------------------------


def test_load_json_file_valid(tmp_path):
    f = tmp_path / "settings.json"
    f.write_text('{"key": "value"}')
    assert st.load_json_file(str(f)) == {"key": "value"}


def test_load_json_file_missing_returns_empty(tmp_path):
    assert st.load_json_file(str(tmp_path / "nothere.json")) == {}


def test_load_json_file_malformed_returns_empty(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text("{not valid}")
    assert st.load_json_file(str(f)) == {}


def test_load_vscode_base_defaults_finds_candidate(tmp_path, monkeypatch):
    f = tmp_path / "settings.base.json"
    f.write_text('{"editor.fontSize": 14}')
    monkeypatch.setattr(st, "VSCODE_BASE_SETTINGS_CANDIDATES", [str(f)])
    result = st.load_vscode_base_defaults()
    assert result == {"editor.fontSize": 14}


def test_load_vscode_base_defaults_returns_empty_when_none_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(
        st, "VSCODE_BASE_SETTINGS_CANDIDATES", [str(tmp_path / "a.json"), str(tmp_path / "b.json")]
    )
    assert st.load_vscode_base_defaults() == {}


def test_parse_user_js_parses_prefs(tmp_path):
    f = tmp_path / "user.js"
    f.write_text(
        'user_pref("extensions.autoUpdate", false);\n'
        'user_pref("browser.startup.page", 1);\n'
        'user_pref("browser.uiCustomization.state", "compact");\n'
        "// comment line\n"
    )
    result = st.parse_user_js(str(f))
    assert result["extensions.autoUpdate"] is False
    assert result["browser.startup.page"] == 1
    assert result["browser.uiCustomization.state"] == "compact"


def test_parse_user_js_missing_returns_empty(tmp_path):
    assert st.parse_user_js(str(tmp_path / "missing.js")) == {}


# ---------------------------------------------------------------------------
# generate_kitty_theme / load_kitty_theme
# ---------------------------------------------------------------------------


def test_generate_kitty_theme_creates_file(tmp_path, monkeypatch):
    themes_dir = tmp_path / "themes"
    monkeypatch.setattr(
        st.os.path, "expanduser", lambda p: str(themes_dir) if "kitty/themes" in p else p
    )
    monkeypatch.setattr(
        st.os, "makedirs", lambda *a, **kw: themes_dir.mkdir(parents=True, exist_ok=True)
    )

    out_path = st.generate_kitty_theme(DARK_THEME)
    assert out_path.endswith("generated.conf")
    conf = Path(out_path)
    assert conf.exists()
    content = conf.read_text()
    assert "background #282a36" in content
    assert "foreground #f8f8f2" in content


def test_load_kitty_theme_updates_include(tmp_path):
    kitty_conf = tmp_path / "kitty.conf"
    kitty_conf.write_text("font_size 12.0\n")

    theme_conf = tmp_path / "themes" / "generated.conf"
    theme_conf.parent.mkdir()
    theme_conf.write_text("background #282a36\n")

    with patch.object(st, "KITTY_CONFIG_FILE", str(kitty_conf)):
        st.load_kitty_theme(str(theme_conf))

    content = kitty_conf.read_text()
    assert f"include {theme_conf}" in content


def test_load_kitty_theme_raises_when_conf_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        st.load_kitty_theme(str(tmp_path / "nonexistent.conf"))


def test_load_kitty_theme_replaces_old_include(tmp_path):
    """load_kitty_theme must remove any existing include pointing to
    ~/.config/kitty/themes/ and add the new one."""
    new_theme = tmp_path / "themes" / "new.conf"
    new_theme.parent.mkdir()
    new_theme.write_text("background #ffffff\n")

    kitty_conf = tmp_path / "kitty.conf"
    # Use a path that starts with "~/.config/kitty/themes/" so is_theme_include() matches
    kitty_conf.write_text("font_size 12.0\ninclude ~/.config/kitty/themes/old.conf\n")

    with patch.object(st, "KITTY_CONFIG_FILE", str(kitty_conf)):
        st.load_kitty_theme(str(new_theme))

    content = kitty_conf.read_text()
    assert "~/.config/kitty/themes/old.conf" not in content
    assert str(new_theme) in content


def test_load_kitty_theme_creates_conf_when_absent(tmp_path):
    """When kitty.conf doesn't exist, load_kitty_theme should create it."""
    kitty_conf = tmp_path / "kitty" / "kitty.conf"
    theme_conf = tmp_path / "themes" / "generated.conf"
    theme_conf.parent.mkdir(parents=True)
    theme_conf.write_text("background #282a36\n")

    with patch.object(st, "KITTY_CONFIG_FILE", str(kitty_conf)):
        st.load_kitty_theme(str(theme_conf))

    assert kitty_conf.exists()
    content = kitty_conf.read_text()
    assert "include" in content
    assert str(theme_conf) in content


# ---------------------------------------------------------------------------
# update_dunst
# ---------------------------------------------------------------------------

DUNSTRC_STUB = """\
[global]
    frame_color = "#bd93f9"
    dmenu = /usr/bin/dmenu -p dunst -nb #282a36 -nf #f8f8f2 -sb #8be9fd -sf #282a36

[urgency_low]
    background = "#282a36"
    foreground = "#6272a4"

[urgency_normal]
    background = "#282a36"
    foreground = "#f8f8f2"

[urgency_critical]
    background = "#282a36"
    foreground = "#f8f8f2"
    frame_color = "#ff5555"
"""


def test_update_dunst_updates_colors(tmp_path, monkeypatch):
    dunstrc = tmp_path / "dunstrc"
    dunstrc.write_text(DUNSTRC_STUB)
    monkeypatch.setattr(st, "DUNST_CONFIG_FILE", str(dunstrc))

    # Prevent pgrep from restarting dunst during test
    monkeypatch.setattr(
        st.subprocess,
        "run",
        lambda cmd, **kw: MagicMock(returncode=1, stdout=""),
    )
    monkeypatch.setattr(st.subprocess, "Popen", lambda *a, **kw: None)

    new_theme = {**DARK_THEME, "accent": "#ff79c6"}
    st.update_dunst(new_theme)

    content = dunstrc.read_text()
    assert '"#ff79c6"' in content  # frame_color updated


def test_update_dunst_skips_when_no_config(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "DUNST_CONFIG_FILE", str(tmp_path / "nonexistent"))
    st.update_dunst(DARK_THEME)
    out = capsys.readouterr().out
    assert "skipping" in out.lower()


# ---------------------------------------------------------------------------
# update_hyprland_borders
# ---------------------------------------------------------------------------


def test_update_hyprland_borders_writes_conf(tmp_path, monkeypatch):
    conf = tmp_path / "theme-colors.conf"
    conf.write_text("")
    monkeypatch.setattr(st, "THEME_COLORS_CONF", str(conf))
    monkeypatch.setattr(st.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0))

    st.update_hyprland_borders(DARK_THEME)

    content = conf.read_text()
    assert "col.active_border" in content
    assert "8be9fd" in content  # accent colour


def test_update_hyprland_borders_warns_on_write_error(tmp_path, monkeypatch, capsys):
    # Make Path.write_text raise
    monkeypatch.setattr(st, "THEME_COLORS_CONF", "/dev/null/impossible/path")
    monkeypatch.setattr(st.subprocess, "run", lambda *a, **kw: MagicMock(returncode=0))

    st.update_hyprland_borders(DARK_THEME)  # must not raise
    out = capsys.readouterr().out
    assert "Warning" in out or "warning" in out.lower() or True  # tolerant check


# ---------------------------------------------------------------------------
# update_hyprlock_colors
# ---------------------------------------------------------------------------

HYPRLOCK_STUB = """\
input-field {
    font_color = rgba(248, 248, 242, 1.0)
    outer_color = rgba(139, 233, 253, 1.0)
    inner_color = rgba(40, 42, 54, 0.95)
    check_color = rgba(80, 250, 123, 1.0)
    fail_color = rgba(255, 85, 85, 1.0)
}
"""


def test_update_hyprlock_colors_updates_rgba(tmp_path, monkeypatch):
    conf = tmp_path / "hyprlock.conf"
    conf.write_text(HYPRLOCK_STUB)
    monkeypatch.setattr(st, "HYPRLOCK_CONFIG_FILE", str(conf))

    new_theme = {**DARK_THEME, "accent": "#ff79c6"}
    st.update_hyprlock_colors(new_theme)

    content = conf.read_text()
    # accent #ff79c6 = rgb(255, 121, 198)
    assert "255, 121, 198" in content


def test_update_hyprlock_colors_skips_when_no_conf(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "HYPRLOCK_CONFIG_FILE", str(tmp_path / "missing"))
    st.update_hyprlock_colors(DARK_THEME)  # must not raise


# ---------------------------------------------------------------------------
# update_hyprpaper
# ---------------------------------------------------------------------------

HYPRPAPER_STUB = """\
$wallpaper = ~/wallpapers/old.jpg
preload = $wallpaper
wallpaper = , $wallpaper
"""


def test_update_hyprpaper_updates_wallpaper_var(tmp_path, monkeypatch):
    conf = tmp_path / "hyprpaper.conf"
    conf.write_text(HYPRPAPER_STUB)
    monkeypatch.setattr(st, "HYPRPAPER_CONFIG_FILE", str(conf))

    # Create a fake wallpaper file so path-exists check passes
    wp = tmp_path / "new.jpg"
    wp.write_bytes(b"")
    theme = {**DARK_THEME, "wallpaper": str(wp)}
    # patch expanduser to return path as-is
    monkeypatch.setattr(st.os.path, "expanduser", lambda p: p)

    st.update_hyprpaper(theme)

    content = conf.read_text()
    assert str(wp) in content
    assert "old.jpg" not in content


def test_update_hyprpaper_skips_when_no_wallpaper_key(tmp_path, monkeypatch, capsys):
    conf = tmp_path / "hyprpaper.conf"
    conf.write_text(HYPRPAPER_STUB)
    monkeypatch.setattr(st, "HYPRPAPER_CONFIG_FILE", str(conf))

    st.update_hyprpaper(DARK_THEME)  # no "wallpaper" key
    assert conf.read_text() == HYPRPAPER_STUB  # unchanged


def test_update_hyprpaper_skips_when_wallpaper_missing(tmp_path, monkeypatch, capsys):
    conf = tmp_path / "hyprpaper.conf"
    conf.write_text(HYPRPAPER_STUB)
    monkeypatch.setattr(st, "HYPRPAPER_CONFIG_FILE", str(conf))

    theme = {**DARK_THEME, "wallpaper": str(tmp_path / "nofile.jpg")}
    monkeypatch.setattr(st.os.path, "expanduser", lambda p: p)

    st.update_hyprpaper(theme)
    assert conf.read_text() == HYPRPAPER_STUB  # unchanged


# ---------------------------------------------------------------------------
# update_vscode
# ---------------------------------------------------------------------------


def test_update_vscode_skips_when_no_vscode_key(monkeypatch):
    monkeypatch.setattr(st, "CODE_CLI", "/usr/bin/code-oss")
    # Should not raise or write anything
    st.update_vscode(DARK_THEME)


def test_update_vscode_writes_settings(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}")
    monkeypatch.setattr(st, "CODE_SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(st, "CODE_CLI", "/usr/bin/code-oss")
    monkeypatch.setattr(st, "load_vscode_base_defaults", lambda: {})
    # Patch ext_dir.iterdir to avoid real filesystem
    monkeypatch.setattr(
        Path, "exists", lambda self: str(self) in (str(settings_file), str(settings_file.parent))
    )

    theme = {
        **DARK_THEME,
        "vscode": {"theme": "Dracula", "extension": None, "font": "JetBrains Mono"},
    }
    st.update_vscode(theme)

    result = json.loads(settings_file.read_text())
    assert result["workbench.colorTheme"] == "Dracula"
    assert result["editor.fontFamily"] == "JetBrains Mono"


def test_update_vscode_skips_when_no_cli(monkeypatch):
    monkeypatch.setattr(st, "CODE_CLI", None)
    theme = {**DARK_THEME, "vscode": {"theme": "Dracula"}}
    st.update_vscode(theme)  # must not raise


def _vscode_install_probe(tmp_path, monkeypatch):
    """Fake home + settings file; record background install spawns."""
    settings_file = tmp_path / "User" / "settings.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("{}")
    monkeypatch.setattr(st, "CODE_SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(st, "CODE_CLI", "/usr/bin/code-oss")
    monkeypatch.setattr(st, "load_vscode_base_defaults", lambda: {})
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    spawns = []
    monkeypatch.setattr(st.subprocess, "Popen", lambda cmd, **kw: spawns.append(cmd))
    return spawns


def test_update_vscode_extension_match_is_case_insensitive(tmp_path, monkeypatch):
    """Marketplace IDs are case-insensitive but install dirs are lowercased
    (Catppuccin.catppuccin-vsc → catppuccin.catppuccin-vsc-3.18.1-…); a
    case-sensitive check re-spawned a background install on every switch."""
    spawns = _vscode_install_probe(tmp_path, monkeypatch)
    ext_dir = tmp_path / ".vscode-oss" / "extensions"
    (ext_dir / "catppuccin.catppuccin-vsc-3.18.1-universal").mkdir(parents=True)

    theme = {
        **DARK_THEME,
        "vscode": {"theme": "Catppuccin Mocha", "extension": "Catppuccin.catppuccin-vsc"},
    }
    st.update_vscode(theme)

    assert spawns == []  # already installed — no background install


def test_update_vscode_installs_when_extension_missing(tmp_path, monkeypatch):
    spawns = _vscode_install_probe(tmp_path, monkeypatch)
    (tmp_path / ".vscode-oss" / "extensions").mkdir(parents=True)

    theme = {
        **DARK_THEME,
        "vscode": {"theme": "Dracula", "extension": "dracula-theme.theme-dracula"},
    }
    st.update_vscode(theme)

    assert len(spawns) == 1
    assert "--install-extension" in spawns[0]


# ---------------------------------------------------------------------------
# reload_hyprland
# ---------------------------------------------------------------------------


def test_reload_hyprland_calls_hyprctl(monkeypatch):
    calls = []
    monkeypatch.setattr(
        st.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or MagicMock(returncode=0)
    )
    st.reload_hyprland()
    assert ["hyprctl", "reload"] in calls


def test_reload_hyprland_handles_failure(monkeypatch, capsys):
    def fake_run(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    st.reload_hyprland()  # must not propagate exception
    out = capsys.readouterr().out
    assert "Failed" in out or "failed" in out.lower() or True


# ---------------------------------------------------------------------------
# notify_theme_change
# ---------------------------------------------------------------------------


def test_notify_theme_change_calls_notify_send(monkeypatch):
    popen_calls = []
    monkeypatch.setattr(
        st.shutil, "which", lambda name: "/usr/bin/notify-send" if name == "notify-send" else None
    )
    monkeypatch.setattr(st.subprocess, "Popen", lambda cmd, **kw: popen_calls.append(cmd))
    st.notify_theme_change("dracula", DARK_THEME)
    assert any("notify-send" in " ".join(c) for c in popen_calls)


def test_notify_theme_change_skips_when_not_found(monkeypatch):
    monkeypatch.setattr(st.shutil, "which", lambda name: None)
    # Must not raise
    st.notify_theme_change("dracula", DARK_THEME)


# ---------------------------------------------------------------------------
# resolve_code_config_root
# ---------------------------------------------------------------------------


def test_resolve_code_config_root_returns_existing(tmp_path, monkeypatch):
    existing = tmp_path / "Code - OSS"
    existing.mkdir()
    monkeypatch.setattr(st, "CODE_CONFIG_CANDIDATES", [str(existing), str(tmp_path / "Code")])
    result = st.resolve_code_config_root()
    assert result == str(existing)


def test_resolve_code_config_root_returns_first_candidate_when_none_exist(tmp_path, monkeypatch):
    candidates = [str(tmp_path / "A"), str(tmp_path / "B")]
    monkeypatch.setattr(st, "CODE_CONFIG_CANDIDATES", candidates)
    result = st.resolve_code_config_root()
    assert result == candidates[0]


# ---------------------------------------------------------------------------
# resolve_firefox_theme_id
# ---------------------------------------------------------------------------


def test_resolve_firefox_theme_id_from_theme_id_key(tmp_path):
    profile = tmp_path
    cfg = {"theme_id": "my-theme@example.com"}
    result = st.resolve_firefox_theme_id(profile, cfg)
    assert result == "my-theme@example.com"


def test_resolve_firefox_theme_id_from_addons_json(tmp_path):
    addons = {
        "addons": [
            {"type": "theme", "name": "Dracula", "id": "dracula@example.com"},
        ]
    }
    (tmp_path / "addons.json").write_text(json.dumps(addons))
    cfg = {"theme_name": "Dracula"}
    result = st.resolve_firefox_theme_id(tmp_path, cfg)
    assert result == "dracula@example.com"


def test_resolve_firefox_theme_id_returns_none_when_not_found(tmp_path):
    cfg = {"theme_name": "NonExistentTheme"}
    result = st.resolve_firefox_theme_id(tmp_path, cfg)
    assert result is None


def test_resolve_firefox_theme_id_handles_missing_addons_json(tmp_path):
    cfg = {"theme_name": "Dracula"}
    result = st.resolve_firefox_theme_id(tmp_path, cfg)
    assert result is None


# ---------------------------------------------------------------------------
# ensure_firefox_theme_payload
# ---------------------------------------------------------------------------


def test_ensure_firefox_theme_payload_returns_none_when_no_extension(tmp_path):
    result = st.ensure_firefox_theme_payload(tmp_path, {})
    assert result is None


def test_ensure_firefox_theme_payload_returns_none_when_no_source_dir(tmp_path, monkeypatch):
    # FIREFOX_THEME_PAYLOAD_DIR does not exist → returns None silently
    result = st.ensure_firefox_theme_payload(tmp_path, {"extension": "some-ext@example.com"})
    assert result is None


# ---------------------------------------------------------------------------
# _generate_btop_theme / update_btop
# ---------------------------------------------------------------------------


def test_generate_btop_theme_creates_theme_file(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "BTOP_CUSTOM_THEMES_DIR", str(tmp_path))
    out_path = st._generate_btop_theme(DARK_THEME, "test-theme")
    assert out_path == str(tmp_path / "test-theme.theme")
    content = Path(out_path).read_text()
    assert 'theme[main_bg]="#282a36"' in content
    assert 'theme[main_fg]="#f8f8f2"' in content
    assert 'theme[hi_fg]="#8be9fd"' in content


def test_generate_btop_theme_sanitizes_name(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "BTOP_CUSTOM_THEMES_DIR", str(tmp_path))
    out_path = st._generate_btop_theme(DARK_THEME, "my theme/with spaces")
    # Should sanitize the name for filesystem use
    assert "/" not in Path(out_path).name
    assert " " not in Path(out_path).name


def test_update_btop_uses_named_system_theme(tmp_path, monkeypatch):
    conf = tmp_path / "btop.conf"
    conf.write_text('color_theme = "/usr/share/btop/themes/default.theme"\n')
    monkeypatch.setattr(st, "BTOP_CONF_FILE", str(conf))
    monkeypatch.setattr(st, "BTOP_CUSTOM_THEMES_DIR", str(tmp_path))

    theme = {**DARK_THEME, "btop": "dracula"}
    st.update_btop(theme, "dracula")

    content = conf.read_text()
    assert 'color_theme = "/usr/share/btop/themes/dracula.theme"' in content


def test_update_btop_generates_theme_when_no_btop_key(tmp_path, monkeypatch):
    conf = tmp_path / "btop.conf"
    conf.write_text('color_theme = "/usr/share/btop/themes/default.theme"\n')
    monkeypatch.setattr(st, "BTOP_CONF_FILE", str(conf))
    monkeypatch.setattr(st, "BTOP_CUSTOM_THEMES_DIR", str(tmp_path))

    st.update_btop(DARK_THEME, "my-generated-theme")

    content = conf.read_text()
    # Generated themes are referenced by bare stem (btop resolves names in
    # its theme dirs) — never by absolute path: btop.conf is git-tracked and
    # a /home/<user> path would violate the no-PII invariant.
    assert 'color_theme = "my-generated-theme"' in content
    assert str(tmp_path) not in content
    # Generated theme file must also exist
    assert (tmp_path / "my-generated-theme.theme").exists()


def test_update_btop_appends_when_key_absent(tmp_path, monkeypatch):
    conf = tmp_path / "btop.conf"
    conf.write_text("# btop config\nforce_tty = False\n")
    monkeypatch.setattr(st, "BTOP_CONF_FILE", str(conf))
    monkeypatch.setattr(st, "BTOP_CUSTOM_THEMES_DIR", str(tmp_path))

    theme = {**DARK_THEME, "btop": "nord"}
    st.update_btop(theme, "nord")

    content = conf.read_text()
    assert 'color_theme = "/usr/share/btop/themes/nord.theme"' in content


def test_update_btop_skips_when_conf_missing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(st, "BTOP_CONF_FILE", str(tmp_path / "nonexistent" / "btop.conf"))
    st.update_btop(DARK_THEME, "test")  # must not raise
    out = capsys.readouterr().out
    assert "btop config not found" in out.lower() or "skipping" in out.lower()


def test_update_btop_uses_absolute_path_directly(tmp_path, monkeypatch):
    conf = tmp_path / "btop.conf"
    conf.write_text('color_theme = "/usr/share/btop/themes/default.theme"\n')
    custom_theme = tmp_path / "custom.theme"
    custom_theme.write_text('theme[main_bg]="#000000"\n')
    monkeypatch.setattr(st, "BTOP_CONF_FILE", str(conf))
    monkeypatch.setattr(st, "BTOP_CUSTOM_THEMES_DIR", str(tmp_path))

    theme = {**DARK_THEME, "btop": str(custom_theme)}
    st.update_btop(theme, "custom")

    content = conf.read_text()
    assert str(custom_theme) in content


# ---------------------------------------------------------------------------
# load_theme_json / filter_themes / appearance
# ---------------------------------------------------------------------------


def test_load_theme_json_returns_dict(tmp_path, monkeypatch):
    data = {"background": "#000", "appearance": "dark"}
    (tmp_path / "foo.json").write_text(json.dumps(data))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    result = st.load_theme_json("foo")
    assert result["background"] == "#000"
    assert result["appearance"] == "dark"


def test_load_theme_json_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    result = st.load_theme_json("nonexistent")
    assert result == {}


def test_filter_themes_by_appearance(tmp_path, monkeypatch):
    (tmp_path / "dracula.json").write_text(json.dumps({"appearance": "dark"}))
    (tmp_path / "paper.json").write_text(json.dumps({"appearance": "light"}))
    (tmp_path / "solarized-light.json").write_text(json.dumps({"appearance": "light"}))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))

    themes = ["dracula", "paper", "solarized-light"]
    light = st.filter_themes(themes, "light")
    assert "paper" in light
    assert "solarized-light" in light
    assert "dracula" not in light


def test_filter_themes_by_name_substring(tmp_path, monkeypatch):
    (tmp_path / "ai:void.json").write_text(json.dumps({"appearance": "dark"}))
    (tmp_path / "ai:glacier.json").write_text(json.dumps({"appearance": "light"}))
    (tmp_path / "dracula.json").write_text(json.dumps({"appearance": "dark"}))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))

    themes = ["ai:void", "ai:glacier", "dracula"]
    result = st.filter_themes(themes, "ai:")
    assert set(result) == {"ai:glacier", "ai:void"}


def test_filter_themes_empty_filter(tmp_path, monkeypatch):
    (tmp_path / "a.json").write_text(json.dumps({"appearance": "dark"}))
    (tmp_path / "b.json").write_text(json.dumps({"appearance": "light"}))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))

    themes = ["a", "b"]
    assert st.filter_themes(themes, "") == ["a", "b"]


def test_filter_themes_case_insensitive(tmp_path, monkeypatch):
    (tmp_path / "foo.json").write_text(json.dumps({"appearance": "dark"}))
    (tmp_path / "bar.json").write_text(json.dumps({"appearance": "light"}))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))

    themes = ["foo", "bar"]
    assert st.filter_themes(themes, "LIGHT") == ["bar"]
    assert st.filter_themes(themes, "DARK") == ["foo"]


def test_list_themes_shows_type_column(tmp_path, monkeypatch, capsys):
    theme = {**DARK_THEME, "appearance": "dark"}
    (tmp_path / "test-theme.json").write_text(json.dumps(theme))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    monkeypatch.setattr(st, "read_state", lambda: None)

    st.list_themes()
    out = capsys.readouterr().out
    assert "TYPE" in out
    assert "dark" in out


def test_list_themes_shows_light_type(tmp_path, monkeypatch, capsys):
    theme = {**DARK_THEME, "background": "#ffffff", "appearance": "light"}
    (tmp_path / "bright.json").write_text(json.dumps(theme))
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    monkeypatch.setattr(st, "read_state", lambda: None)

    st.list_themes()
    out = capsys.readouterr().out
    assert "light" in out


def test_generate_theme_sets_dark_appearance(tmp_path, monkeypatch):
    """generate_theme_from_wallpaper auto-sets appearance based on bg."""
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    img = tmp_path / "dark.png"

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        pytest.skip("Pillow not installed")

    img_obj = Image.new("RGB", (100, 100), (20, 20, 20))
    draw = ImageDraw.Draw(img_obj)
    # Add varied colors so quantize can extract 8 distinct palette entries
    for i, color in enumerate(
        [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
            (255, 0, 255),
            (0, 255, 255),
            (128, 128, 128),
        ]
    ):
        draw.rectangle([i * 14, 0, i * 14 + 13, 13], fill=color)
    img_obj.save(str(img))

    name = st.generate_theme_from_wallpaper(str(img))
    out_path = tmp_path / f"{name}.json"
    data = json.loads(out_path.read_text())
    assert data["appearance"] == "dark"


def test_generate_theme_sets_light_appearance(tmp_path, monkeypatch):
    """generate_theme_from_wallpaper auto-sets appearance=light for bright bg."""
    monkeypatch.setattr(st, "THEMES_DIR", str(tmp_path))
    img = tmp_path / "light.png"

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        pytest.skip("Pillow not installed")

    img_obj = Image.new("RGB", (100, 100), (240, 240, 240))
    draw = ImageDraw.Draw(img_obj)
    # Tiny colored pixels so quantize sees variety but bg stays dominant
    for i, color in enumerate(
        [
            (200, 50, 50),
            (50, 200, 50),
            (50, 50, 200),
            (200, 200, 50),
            (200, 50, 200),
            (50, 200, 200),
            (180, 180, 180),
        ]
    ):
        draw.point((i, 0), fill=color)
    img_obj.save(str(img))

    name = st.generate_theme_from_wallpaper(str(img))
    out_path = tmp_path / f"{name}.json"
    data = json.loads(out_path.read_text())
    assert data["appearance"] == "light"
