import configparser
import json
import os
import random
import re
import signal
import shutil
import subprocess
import sys
import time
import filecmp
from pathlib import Path
from typing import Any, Dict, Optional

# === Configuration ===
SCRIPT_DIR = Path(__file__).resolve().parent


def detect_repo_root(start: Path) -> Path:
    current = start
    while current.name != ".hyprconf" and current.parent != current:
        current = current.parent
    return current


REPO_ROOT = detect_repo_root(SCRIPT_DIR)
THEMES_DIR = os.path.join(SCRIPT_DIR, "themes")
WAYBAR_CONFIG_FILE = os.path.expanduser("~/.config/waybar/waybar.css")
HYPRPAPER_CONFIG_FILE = os.path.expanduser("~/.config/hypr/hyprpaper.conf")
KITTY_CONFIG_FILE = os.path.expanduser("~/.config/kitty/kitty.conf")
WOFI_STYLE_FILE = os.path.expanduser("~/.config/wofi/style.css")  # legacy; kept for migration cleanup only
CODE_CONFIG_CANDIDATES = [
    os.path.expanduser("~/.config/Code - OSS"),
    os.path.expanduser("~/.config/Code"),
]


def resolve_code_config_root() -> str:
    for candidate in CODE_CONFIG_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return CODE_CONFIG_CANDIDATES[0]


CODE_CONFIG_ROOT = resolve_code_config_root()
CODE_SETTINGS_FILE = os.path.join(CODE_CONFIG_ROOT, "User", "settings.json")
VSCODE_BASE_SETTINGS_CANDIDATES = [
    os.path.join(CODE_CONFIG_ROOT, "User", "settings.base.json"),
    os.path.join(REPO_ROOT, "stow", "code-oss", ".config", "Code - OSS", "User", "settings.base.json"),
    os.path.join(REPO_ROOT, "stow", "code-oss", ".config", "Code", "User", "settings.base.json"),
]
CODE_CLI = shutil.which("code-oss") or shutil.which("code")
DUNST_CONFIG_FILE = os.path.expanduser("~/.config/dunst/dunstrc")
FIREFOX_PROFILES_INI = os.path.expanduser("~/.mozilla/firefox/profiles.ini")
FIREFOX_DIR = os.path.dirname(FIREFOX_PROFILES_INI)
FIREFOX_BASE_PREFS_FILE = os.path.expanduser("~/.mozilla/firefox/user.js")
FIREFOX_THEME_PAYLOAD_DIR = REPO_ROOT / "theme" / "firefox" / "extensions"
FIREFOX_COMPACT_DARK_ID   = "firefox-compact-dark@mozilla.org"
FIREFOX_COMPACT_LIGHT_ID  = "firefox-compact-light@mozilla.org"
GTK3_SETTINGS_FILE = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
GTK4_SETTINGS_FILE = os.path.expanduser("~/.config/gtk-4.0/settings.ini")
XSETTINGSD_CONFIG_FILE = os.path.expanduser("~/.config/xsettingsd/xsettingsd.conf")
KDEGLOBALS_FILE        = os.path.expanduser("~/.config/kdeglobals")
KDE_COLOR_SCHEMES_DIR  = os.path.expanduser("~/.local/share/color-schemes")
QT6CT_CONF_FILE        = os.path.expanduser("~/.config/qt6ct/qt6ct.conf")
HYPRTOOLKIT_CONF_FILE  = os.path.expanduser("~/.config/hypr/hyprtoolkit.conf")
QT6CT_COLORS_FILE      = os.path.expanduser("~/.config/qt6ct/colors/hyprconf.conf")
QT5CT_CONF_FILE        = os.path.expanduser("~/.config/qt5ct/qt5ct.conf")
QT5CT_COLORS_FILE      = os.path.expanduser("~/.config/qt5ct/colors/hyprconf.conf")
THEME_COLORS_CONF      = os.path.expanduser("~/.config/hypr/theme-colors.conf")
HYPRLOCK_CONFIG_FILE   = os.path.expanduser("~/.config/hypr/hyprlock.conf")
DOLPHIN_RC_FILE        = os.path.expanduser("~/.config/dolphinrc")
TOUCH_PANEL_COLORS_FILE = os.path.expanduser("~/.config/touch-panel/colors")
STATE_FILE             = os.path.expanduser("~/.config/hypr/.current-theme")

FIREFOX_ENFORCED_PREFS = {
    # --- UI ---
    "browser.tabs.verticalTabs": True,
    "browser.tabs.verticalTabs.showPinnedTabs": True,
    "browser.tabs.drawInTitlebar": True,
    # --- Core telemetry ---
    "toolkit.telemetry.enabled": False,
    "toolkit.telemetry.unified": False,
    "toolkit.telemetry.archive.enabled": False,
    "toolkit.coverage.opt-out": True,
    "toolkit.telemetry.server": "data:,",
    "datareporting.healthreport.uploadEnabled": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    # --- Studies / experiments ---
    "app.shield.optoutstudies.enabled": False,
    "app.normandy.enabled": False,
    # --- Sponsored / discovery content ---
    "browser.discovery.enabled": False,
    "browser.newtabpage.activity-stream.showSponsored": False,
    "browser.newtabpage.activity-stream.showSponsoredTopSites": False,
    "browser.newtabpage.activity-stream.feeds.section.topstories": False,
    "browser.newtabpage.activity-stream.showWeather": False,
    "browser.newtabpage.activity-stream.feeds.telemetry": False,
    "browser.newtabpage.activity-stream.asrouter.userprefs.cfr.addons": False,
    "browser.newtabpage.activity-stream.asrouter.userprefs.cfr.features": False,
    # --- Crash reporting ---
    "browser.tabs.crashReporting.sendReport": False,
    "browser.crashReports.unsubmittedCheck.enabled": False,
    "browser.crashReports.unsubmittedCheck.autoSubmit2": False,
    # --- Pocket ---
    "extensions.pocket.enabled": False,
    # --- Geolocation ---
    "geo.enabled": False,
    # --- Network probing ---
    "network.captive-portal-detection.enabled": False,
    "network.connectivity-service.enabled": False,
    # --- Prefetching / speculative connections ---
    "network.prefetch-next": False,
    "network.dns.disablePrefetch": True,
    "browser.urlbar.speculativeConnect.enabled": False,
    # --- Hyperlink pings and beacons ---
    "browser.send_pings": False,
    "beacon.enabled": False,
    # --- Safe browsing remote lookups ---
    "browser.safebrowsing.malware.enabled": False,
    "browser.safebrowsing.phishing.enabled": False,
    "browser.safebrowsing.downloads.enabled": False,
    "browser.safebrowsing.downloads.remote.enabled": False,
    # --- Tracking protection ---
    "privacy.trackingprotection.enabled": True,
    "privacy.trackingprotection.socialtracking.enabled": True,
    # --- userChrome.css / compact mode ---
    "toolkit.legacyUserProfileCustomizations.stylesheets": True,
    "browser.compactmode.show": True,
}

def is_dark_color(hex_color: str) -> bool:
    """Return True if the color has low perceived brightness (dark background)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 128


def launcher_select(initial_filter: str = "") -> Optional[str]:
    """Select a theme via hyprlauncher --dmenu (no terminal window required)."""
    themes = get_all_themes()
    if initial_filter:
        themes = [t for t in themes if initial_filter.lower() in t.lower()]
    current = read_state()
    display = [f"★  {t}" if t == current else f"   {t}" for t in themes]
    try:
        # Brief pause so any calling launcher (e.g. hyprlauncher itself) has
        # fully released its window before we open a new dmenu instance.
        time.sleep(0.15)
        proc = subprocess.run(
            ["hyprlauncher", "--dmenu"],
            input="\n".join(display),
            capture_output=True,
            text=True,
        )
        result = proc.stdout.strip().lstrip("★").strip()
        return result if result in themes else None
    except FileNotFoundError:
        print("hyprlauncher not found; falling back to interactive TUI.")
        return interactive_select(initial_filter)


def _css_to_argb(hex_color: str, alpha: int = 0xFF) -> str:
    """Convert a CSS #RRGGBB hex color to hyprtoolkit's 0xAARRGGBB notation."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return f"0x{alpha:02X}{h.upper()}"


def _lighten_hex(hex_color: str, amount: int = 16) -> str:
    """Return a slightly lighter version of a #RRGGBB color (clipped at 0xFF)."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r = min(255, r + amount)
    g = min(255, g + amount)
    b = min(255, b + amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def update_hyprtoolkit(theme: Dict[str, str]) -> None:
    """Write ~/.config/hypr/hyprtoolkit.conf from the active theme palette.

    hyprlauncher (and any other hyprtoolkit app) reads this file for its UI
    colors and icon theme.  Without it the launcher renders with default grey
    colors and may fail to find a suitable icon theme.
    """
    bg      = theme.get("background", "#1e1e2e")
    fg      = theme.get("foreground", "#cdd6f4")
    accent  = theme.get("accent", "#89b4fa")
    comment = theme.get("comment", bg)

    # base / alternate_base: slightly lighter than the background so the
    # launcher surface stands out from the wallpaper.
    base     = _lighten_hex(bg, 12)
    alt_base = _lighten_hex(bg, 24)

    # accent_secondary: prefer a distinct palette color; fall back to comment.
    acc2 = theme.get("purple", theme.get("blue", theme.get("cyan", comment)))

    # Icon theme: Papirus-Dark for dark backgrounds, Papirus-Light for light.
    icon_theme = "Papirus-Dark" if is_dark_color(bg) else "Papirus-Light"

    lines = [
        "# hyprtoolkit configuration — managed by switch_theme.py, do not edit by hand.",
        "# https://wiki.hypr.land/Hypr-Ecosystem/hyprtoolkit/",
        "",
        f"background       = {_css_to_argb(bg)}",
        f"base             = {_css_to_argb(base)}",
        f"alternate_base   = {_css_to_argb(alt_base)}",
        f"text             = {_css_to_argb(fg)}",
        f"bright_text      = {_css_to_argb(fg)}",
        f"accent           = {_css_to_argb(accent)}",
        f"accent_secondary = {_css_to_argb(acc2)}",
        "",
        "font_family            = JetBrainsMono Nerd Font",
        "font_family_monospace  = JetBrainsMono Nerd Font",
        "font_size              = 12",
        "h1_size                = 18",
        "h2_size                = 15",
        "h3_size                = 13",
        "small_font_size        = 10",
        "",
        "rounding_large  = 10",
        "rounding_small  = 5",
        "",
        f"icon_theme = {icon_theme}",
        "",
    ]

    os.makedirs(os.path.dirname(HYPRTOOLKIT_CONF_FILE), exist_ok=True)
    with open(HYPRTOOLKIT_CONF_FILE, "w") as f:
        f.write("\n".join(lines))

    print(f"hyprtoolkit theme updated ({icon_theme}).")

    # hyprlauncher reads hyprtoolkit.conf only at startup. If it is currently
    # running, kill it so the next launch picks up the new theme immediately.
    _kill_process_if_running("hyprlauncher")


def update_dunst(theme: Dict[str, str]) -> None:
    """Update Dunst notification colors and dmenu colors from the current theme."""
    if not os.path.exists(DUNST_CONFIG_FILE):
        print("Dunst config not found; skipping Dunst theme.")
        return

    accent = theme.get("accent", theme.get("purple", theme.get("cyan", "#bd93f9")))
    bg = theme.get("background", "#282a36")
    fg = theme.get("foreground", "#f8f8f2")
    # For dmenu selected text: dark bg on accent → use bg; light bg on accent → use fg
    selected_fg = bg if is_dark_color(bg) else fg

    section_colors: Dict[str, Dict[str, str]] = {
        "global": {
            "frame_color": accent,
        },
        "urgency_low": {
            "background": bg,
            "foreground": theme.get("comment", "#6272a4"),
        },
        "urgency_normal": {
            "background": bg,
            "foreground": fg,
        },
        "urgency_critical": {
            "background": bg,
            "foreground": fg,
            "frame_color": theme.get("red", "#ff5555"),
        },
    }

    # dmenu color flags — no quotes; dunst passes these directly, not via shell
    dmenu_color_args = f' -nb {bg} -nf {fg} -sb {accent} -sf {selected_fg}'

    with open(DUNST_CONFIG_FILE, "r") as f:
        lines = f.readlines()

    current_section: Optional[str] = None
    result = []
    for line in lines:
        stripped = line.strip()
        section_match = re.match(r"^\[(\w+)\]", stripped)
        if section_match:
            current_section = section_match.group(1).lower()
            result.append(line)
            continue

        if current_section == "global" and stripped.startswith("dmenu"):
            # Strip any existing color flags (quoted or unquoted) and append fresh themed ones
            base_cmd = re.sub(r'\s+-(?:nb|nf|sb|sf)\s+"?#[0-9a-fA-F]{6}"?', '', line.rstrip())
            result.append(base_cmd + dmenu_color_args + "\n")
            continue

        if current_section and current_section in section_colors:
            color_match = re.match(r'^(\s*)(\w+)\s*=\s*"#[0-9a-fA-F]{6}"', line)
            if color_match:
                key = color_match.group(2)
                if key in section_colors[current_section]:
                    indent = color_match.group(1)
                    new_color = section_colors[current_section][key]
                    line = f'{indent}{key} = "{new_color}"\n'

        result.append(line)

    with open(DUNST_CONFIG_FILE, "w") as f:
        f.writelines(result)
    print("Dunst theme updated.")

    proc = subprocess.run(["pgrep", "dunst"], capture_output=True, text=True)
    if proc.returncode == 0:
        for pid in proc.stdout.split():
            try:
                os.kill(int(pid), 15)  # SIGTERM
            except (ProcessLookupError, ValueError):
                pass
        subprocess.Popen(
            ["dunst"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print("Dunst restarted.")


def hex_to_rgb_str(hex_color: str) -> str:
    """Convert #RRGGBB to 'R,G,B' string for kdeglobals / KDE color schemes."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b}"


def blend_colors(hex1: str, hex2: str, ratio: float = 0.15) -> str:
    """Blend hex1 toward hex2 by ratio (0.0 = hex1, 1.0 = hex2). Returns #RRGGBB."""
    h1, h2 = hex1.lstrip("#"), hex2.lstrip("#")
    r1, g1, b1 = int(h1[0:2], 16), int(h1[2:4], 16), int(h1[4:6], 16)
    r2, g2, b2 = int(h2[0:2], 16), int(h2[2:4], 16), int(h2[4:6], 16)
    r = max(0, min(255, int(r1 + (r2 - r1) * ratio)))
    g = max(0, min(255, int(g1 + (g2 - g1) * ratio)))
    b = max(0, min(255, int(b1 + (b2 - b1) * ratio)))
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgba(hex_color: str, alpha: float = 0.8) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"


def hex_to_hypr_rgba(hex_color: str, alpha_hex: str = "ee") -> str:
    """Convert a hex color to Hyprland's rgba(RRGGBBaa) format."""
    return f"rgba({hex_color.lstrip('#')}{alpha_hex})"


def get_all_themes() -> list:
    """Return a sorted list of all available theme names."""
    return sorted(
        fname[:-5]
        for fname in os.listdir(THEMES_DIR)
        if fname.endswith(".json")
    )


def read_state() -> Optional[str]:
    """Return the name of the last applied theme, or None."""
    try:
        return Path(STATE_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def write_state(theme_name: str) -> None:
    """Persist the current theme name to the state file."""
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(STATE_FILE).write_text(theme_name + "\n", encoding="utf-8")


def get_adjacent_theme(direction: int) -> Optional[str]:
    """Return the next (+1) or previous (-1) theme from the sorted list."""
    themes = get_all_themes()
    if not themes:
        return None
    current = read_state()
    if not current or current not in themes:
        return themes[0]
    return themes[(themes.index(current) + direction) % len(themes)]


def update_hyprland_borders(theme: Dict[str, str]) -> None:
    """Write theme-colors.conf and update Hyprland border colors live via hyprctl."""
    accent    = theme.get("accent",  theme.get("purple", "#bd93f9"))
    secondary = theme.get("cyan",    theme.get("pink",   accent))
    inactive  = theme.get("comment", "#595959")

    active_border   = f"{hex_to_hypr_rgba(accent)} {hex_to_hypr_rgba(secondary)} 45deg"
    inactive_border = hex_to_hypr_rgba(inactive, "aa")

    # Write sourced conf for persistence across reloads and restarts
    content = (
        "# Generated by switch_theme.py — do not edit manually\n\n"
        "general {\n"
        f"    col.active_border   = {active_border}\n"
        f"    col.inactive_border = {inactive_border}\n"
        "}\n"
    )
    try:
        Path(THEME_COLORS_CONF).write_text(content, encoding="utf-8")
    except OSError as e:
        print(f"Warning: could not write theme-colors.conf: {e}")

    # Also apply live via hyprctl for instant visual feedback (before reload)
    for kw, val in [
        ("general:col.active_border",   active_border),
        ("general:col.inactive_border", inactive_border),
    ]:
        subprocess.run(["hyprctl", "keyword", kw, val], check=False, capture_output=True)
    print("Hyprland border colors updated.")


def update_hyprlock_colors(theme: Dict[str, str]) -> None:
    """Sync hyprlock.conf input-field and label colors with the current theme."""
    if not os.path.exists(HYPRLOCK_CONFIG_FILE):
        return

    def rgb_str(hex_c: str) -> str:
        h = hex_c.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r}, {g}, {b}"

    accent = theme.get("accent",     theme.get("purple", "#bd93f9"))
    green  = theme.get("green",  "#50fa7b")
    red    = theme.get("red",    "#ff5555")
    fg     = theme.get("foreground", "#f8f8f2")
    bg     = theme.get("background", "#282a36")

    replacements = {
        "font_color":  rgb_str(fg),
        "outer_color": rgb_str(accent),
        "inner_color": rgb_str(bg),
        "check_color": rgb_str(green),
        "fail_color":  rgb_str(red),
    }

    with open(HYPRLOCK_CONFIG_FILE, "r") as f:
        content = f.read()

    # Replace the RGB portion of rgba(R, G, B, alpha) while preserving existing alpha
    for key, new_rgb in replacements.items():
        content = re.sub(
            rf'({re.escape(key)}\s*=\s*rgba\()[\d,\s]+(,\s*[\d.]+\))',
            lambda m, rgb=new_rgb: m.group(1) + rgb + m.group(2),
            content,
        )

    with open(HYPRLOCK_CONFIG_FILE, "w") as f:
        f.write(content)
    print("Hyprlock colors updated.")


def generate_kitty_theme(theme: Dict[str, str]) -> str:
    """Generate a kitty theme .conf from theme colors; return the file path."""
    colors = {
        "background":           theme.get("background", "#1e1e2e"),
        "foreground":           theme.get("foreground", "#cdd6f4"),
        "selection_background": theme.get("accent",     "#89b4fa"),
        "selection_foreground": theme.get("background", "#1e1e2e"),
        "cursor":               theme.get("accent",     "#f5e0dc"),
        "cursor_text_color":    theme.get("background", "#1e1e2e"),
        "color0":  theme.get("comment",    "#45475a"),
        "color1":  theme.get("red",        "#f38ba8"),
        "color2":  theme.get("green",      "#a6e3a1"),
        "color3":  theme.get("yellow",     "#f9e2af"),
        "color4":  theme.get("purple",     theme.get("cyan",  "#89b4fa")),
        "color5":  theme.get("pink",       "#f5c2e7"),
        "color6":  theme.get("cyan",       "#94e2d5"),
        "color7":  theme.get("foreground", "#bac2de"),
        # Bright variants — lighten by using accent/foreground
        "color8":  theme.get("comment",    "#585b70"),
        "color9":  theme.get("red",        "#f38ba8"),
        "color10": theme.get("green",      "#a6e3a1"),
        "color11": theme.get("yellow",     "#f9e2af"),
        "color12": theme.get("accent",     "#89b4fa"),
        "color13": theme.get("pink",       "#f5c2e7"),
        "color14": theme.get("cyan",       "#94e2d5"),
        "color15": theme.get("foreground", "#a6adc8"),
    }
    out_dir  = os.path.expanduser("~/.config/kitty/themes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "generated.conf")
    with open(out_path, "w") as f:
        f.write("# Auto-generated by switch_theme.py\n")
        for k, v in colors.items():
            f.write(f"{k} {v}\n")
    return out_path


def notify_theme_change(theme_name: str, theme: Dict[str, str]) -> None:
    """Send a desktop notification confirming the theme change."""
    notify = shutil.which("notify-send")
    if not notify:
        return
    accent = theme.get("accent", "")
    body   = f"bg {theme.get('background', '')}  accent {accent}" if accent else ""
    try:
        subprocess.Popen(
            [notify, "--urgency=low", "--expire-time=3000",
             "--icon=preferences-desktop-theme-symbolic",
             f"Theme: {theme_name}", body],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def reload_hyprland() -> None:
    """Reload Hyprland via hyprctl."""
    try:
        subprocess.run(["hyprctl", "reload"], check=True)
        print("Hyprland reloaded.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to reload Hyprland: {e}")


def _kill_process_if_running(process_name: str) -> bool:
    """Send SIGTERM to any running process whose name matches exactly.

    Uses pgrep to find PIDs and os.kill to terminate — no pkill/killall.
    Returns True if at least one process was signalled.
    """
    result = subprocess.run(
        ["pgrep", "-x", process_name], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return False
    for pid_str in result.stdout.strip().splitlines():
        try:
            os.kill(int(pid_str), signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
    print(f"Sent SIGTERM to running {process_name}; theme applies on next launch.")
    return True

def _proc_name_pids(name: str) -> list:
    """Return list of PIDs whose /proc/<pid>/comm matches `name` exactly.
    Uses /proc directly — no subprocess, no hanging.
    """
    pids = []
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if (entry / "comm").read_text().strip() == name:
                    pids.append(int(entry.name))
            except (PermissionError, FileNotFoundError, OSError):
                continue
    except (PermissionError, FileNotFoundError, OSError):
        pass
    return pids


def _is_process_running(name: str) -> bool:
    """Return True if any process with the given exact name is running."""
    return bool(_proc_name_pids(name))


def load_theme(theme_name: str) -> Dict[str, str]:
    """Load a theme JSON file into a dictionary."""
    path = os.path.join(THEMES_DIR, f"{theme_name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Theme file not found: {path}")
    
    with open(path, "r") as file:
        theme = json.load(file)

    # Check for Kitty config file key
    if "kitty" in theme:
        theme["kitty"] = os.path.expanduser(theme["kitty"])

    return theme

def load_kitty_theme(kitty_config_path: str):
    """Apply Kitty theme from a .conf file in an idempotent way."""
    if not os.path.exists(kitty_config_path):
        raise FileNotFoundError(f"Kitty theme file not found: {kitty_config_path}")

    # Expand user (~) to full path in case the path is relative
    kitty_config_path = os.path.expanduser(kitty_config_path)
    
    # Normalize to make sure all paths are absolute
    normalized_path = os.path.abspath(kitty_config_path)

    # Read the current kitty.conf
    with open(KITTY_CONFIG_FILE, "r") as kitty_config:
        kitty_conf_content = kitty_config.read()

    # Search for include lines pointing to ~/.config/kitty/themes and drop them
    themes_dir = os.path.expanduser("~/.config/kitty/themes/")

    def is_theme_include(line: str) -> bool:
        stripped = line.strip()
        if not stripped.startswith("include "):
            return False
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            return False
        include_target = parts[1]
        expanded_target = os.path.expanduser(include_target)
        abs_target = os.path.abspath(os.path.join(os.path.dirname(KITTY_CONFIG_FILE), expanded_target))
        return (
            include_target.startswith("~/.config/kitty/themes/")
            or include_target.startswith(themes_dir)
            or expanded_target.startswith(themes_dir)
            or abs_target.startswith(themes_dir)
            or include_target.startswith("themes/")
        )

    lines = [line for line in kitty_conf_content.splitlines() if not is_theme_include(line)]

    # Add the new include line from the theme JSON (this will be absolute)
    new_include_line = f"include {normalized_path}"

    # Ensure the new include line is added (if not already there)
    if new_include_line not in lines:
        lines.append(new_include_line)
        print(f"Kitty theme applied from {normalized_path}.")
    else:
        print(f"Kitty theme already applied: {normalized_path}")

    # Write the updated lines back to kitty.conf
    with open(KITTY_CONFIG_FILE, "w") as kitty_config:
        kitty_config.write("\n".join(lines) + "\n")

def update_waybar_colors(config_text: str, theme_colors: dict) -> str:
    def replacer(match):
        color_name = match.group(1)
        if color_name in theme_colors:
            return f"@define-color {color_name} {theme_colors[color_name]};"
        else:
            return match.group(0)

    updated_text = re.sub(
        r"@define-color\s+(\w+)\s+[^;]+;",
        replacer,
        config_text,
    )

    rgba_bg = hex_to_rgba(theme_colors["background"], 0.8)
    if "@define-color background-alpha" in updated_text:
        updated_text = re.sub(
            r"@define-color background-alpha\s+[^;]+;",
            f"@define-color background-alpha {rgba_bg};",
            updated_text,
        )
    else:
        updated_text = re.sub(
            r"(@define-color background\s+[^;]+;)",
            r"\1\n@define-color background-alpha " + rgba_bg + ";",
            updated_text,
            count=1,
        )

    updated_text = re.sub(
        r"background:\s*rgba\(40,\s*42,\s*54,\s*0\.\d+\);",
        "background: @background-alpha;",
        updated_text,
    )

    return updated_text

def update_waybar(theme_colors: Dict[str, str]):
    """Update Waybar CSS theme."""
    if not os.path.exists(WAYBAR_CONFIG_FILE):
        raise FileNotFoundError(f"Waybar config not found: {WAYBAR_CONFIG_FILE}")
    with open(WAYBAR_CONFIG_FILE, "r") as f:
        css = f.read()
    updated_css = update_waybar_colors(css, theme_colors)
    with open(WAYBAR_CONFIG_FILE, "w") as f:
        f.write(updated_css)
    print("Waybar theme updated.")

def update_hyprpaper(theme: Dict[str, str]):
    """Update Hyprpaper wallpaper by rewriting the $wallpaper variable declaration."""
    if "wallpaper" not in theme:
        print("No wallpaper defined in theme, skipping Hyprpaper.")
        return

    wallpaper_entry = theme["wallpaper"]  # raw value, e.g. "~/wallpaper/gruvbox.jpg"
    wallpaper_path = os.path.expanduser(wallpaper_entry)
    if not os.path.exists(wallpaper_path):
        print(f"Wallpaper image not found: {wallpaper_path}")
        return

    if not os.path.exists(HYPRPAPER_CONFIG_FILE):
        print("Hyprpaper config file not found, skipping.")
        return

    with open(HYPRPAPER_CONFIG_FILE, "r") as f:
        lines = f.readlines()

    updated_lines = []
    for line in lines:
        # Update the $wallpaper variable declaration used by all wallpaper blocks
        if re.match(r'^\$wallpaper\s*=', line):
            updated_lines.append(f"$wallpaper = {wallpaper_entry}\n")
        else:
            updated_lines.append(line)

    with open(HYPRPAPER_CONFIG_FILE, "w") as f:
        f.writelines(updated_lines)

    print("Hyprpaper wallpaper updated.")


def load_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON file at {path}.")
        return {}


def load_vscode_base_defaults() -> Dict[str, Any]:
    for candidate in VSCODE_BASE_SETTINGS_CANDIDATES:
        data = load_json_file(candidate)
        if data:
            return data
    return {}


def parse_user_js(path: str) -> Dict[str, Any]:
    """Parse user.js style key/value pairs into a dictionary."""
    if not os.path.exists(path):
        return {}

    prefs: Dict[str, Any] = {}
    pattern = re.compile(r'user_pref\("([^"]+)",\s*(.+)\);\s*$')

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            match = pattern.match(line)
            if not match:
                continue
            key, value_str = match.groups()
            value_str = value_str.strip()
            try:
                if value_str.lower() in {"true", "false"}:
                    prefs[key] = value_str.lower() == "true"
                elif value_str.startswith('"') and value_str.endswith('"'):
                    prefs[key] = json.loads(value_str)
                else:
                    if "." in value_str:
                        prefs[key] = float(value_str)
                    else:
                        prefs[key] = int(value_str)
            except Exception:
                prefs[key] = value_str.strip('"')

    return prefs


def update_vscode(theme: Dict[str, Any]) -> None:
    """Set VS Code theme, font, and extension based on the theme payload."""
    vscode_cfg = theme.get("vscode")
    if not vscode_cfg:
        return

    if CODE_CLI is None:
        print("VS Code CLI not found; skipping VS Code theme.")
        return

    extension = vscode_cfg.get("extension")
    if extension:
        ext_dir = Path.home() / ".vscode-oss" / "extensions"
        already_installed = any(
            p.is_dir() and (p.name == extension or p.name.startswith(f"{extension}-"))
            for p in ext_dir.iterdir()
        ) if ext_dir.exists() else False

        if not already_installed:
            # Fire-and-forget: fully detach so Electron children never block the terminal.
            subprocess.Popen(
                [CODE_CLI, "--install-extension", extension, "--force"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"VS Code extension install started in background ({extension}).")

    settings_path = Path(CODE_SETTINGS_FILE)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: Dict[str, Any] = {}

    # Start from current settings.json so un-managed keys persist
    if settings_path.exists():
        try:
            existing_settings = json.loads(settings_path.read_text(encoding="utf-8") or "{}")
            settings.update(existing_settings)
        except json.JSONDecodeError:
            print("VS Code settings.json is not valid JSON. Recreating minimal file.")

    # Overlay repo-managed defaults so they always win
    base_defaults = load_vscode_base_defaults()
    if base_defaults:
        settings.update(base_defaults)

    theme_name = vscode_cfg.get("theme")
    if theme_name:
        settings["workbench.colorTheme"] = theme_name
        settings.setdefault("window.autoDetectColorScheme", False)

    icon_theme = vscode_cfg.get("iconTheme")
    if icon_theme:
        settings["workbench.iconTheme"] = icon_theme

    font = vscode_cfg.get("font")
    if font:
        settings["editor.fontFamily"] = font
        settings["terminal.integrated.fontFamily"] = font

    if theme_name or icon_theme or font:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
        print("VS Code settings updated.")


def _profile_path_from_entry(path_value: str, is_relative: Optional[str] = "1") -> Path:
    if path_value.startswith("/") or (is_relative and is_relative == "0"):
        return Path(path_value).expanduser()
    return Path(FIREFOX_DIR, path_value)


def get_default_firefox_profile() -> Optional[Path]:
    if not os.path.exists(FIREFOX_PROFILES_INI):
        return None

    parser = configparser.RawConfigParser()
    parser.read(FIREFOX_PROFILES_INI)

    # Prefer install-specific Default entries (common on Arch builds)
    for section in parser.sections():
        if section.lower().startswith("install") and parser.has_option(section, "Default"):
            rel_path = parser.get(section, "Default")
            if rel_path:
                candidate = _profile_path_from_entry(rel_path, "1")
                if candidate.is_dir():
                    return candidate

    # Fall back to profile sections that declare Default=1
    for section in parser.sections():
        if parser.has_option(section, "Default") and parser.get(section, "Default") == "1":
            rel_path = parser.get(section, "Path", fallback=None)
            if not rel_path:
                continue
            is_relative = parser.get(section, "IsRelative", fallback="1")
            candidate = _profile_path_from_entry(rel_path, is_relative)
            if candidate.is_dir():
                return candidate

    # As a last resort, use the first profile entry with a Path that exists
    for section in parser.sections():
        if parser.has_option(section, "Path"):
            rel_path = parser.get(section, "Path")
            is_relative = parser.get(section, "IsRelative", fallback="1")
            candidate = _profile_path_from_entry(rel_path, is_relative)
            if candidate.is_dir():
                return candidate

    return None


def get_firefox_builtin_theme_id(theme: Dict[str, Any]) -> str:
    """Return the built-in Firefox compact theme ID matching the theme's lightness."""
    bg = theme.get("background", "#000000")
    return FIREFOX_COMPACT_DARK_ID if is_dark_color(bg) else FIREFOX_COMPACT_LIGHT_ID


def write_firefox_userchrome(profile_path: Path, theme: Dict[str, Any]) -> None:
    """Write a palette-matched userChrome.css to the Firefox profile chrome/ dir.

    Uses the stable ``--lwt-*`` and ``--toolbar-*`` CSS variable API that Firefox
    exposes for lightweight-theme customisation.  Requires
    ``toolkit.legacyUserProfileCustomizations.stylesheets = true`` (set in
    FIREFOX_ENFORCED_PREFS) to take effect.
    """
    chrome_dir = profile_path / "chrome"
    chrome_dir.mkdir(parents=True, exist_ok=True)

    bg      = theme.get("background", "#1e1e2e")
    fg      = theme.get("foreground", "#cdd6f4")
    comment = theme.get("comment",    "#6c7086")
    accent  = theme.get("accent", theme.get("cyan", theme.get("purple", fg)))

    css = (
        "/* Generated by hyprconf theme-switcher — do not edit manually */\n"
        ":root {\n"
        f"  --lwt-accent-color: {bg} !important;\n"
        f"  --lwt-text-color: {fg} !important;\n"
        f"  --toolbar-bgcolor: {bg} !important;\n"
        f"  --toolbar-color: {fg} !important;\n"
        f"  --tab-selected-bgcolor: {comment} !important;\n"
        f"  --toolbar-field-background-color: {comment} !important;\n"
        f"  --toolbar-field-color: {fg} !important;\n"
        f"  --toolbar-field-focus-background-color: {comment} !important;\n"
        f"  --toolbar-field-focus-color: {fg} !important;\n"
        f"  --focus-outline-color: {accent} !important;\n"
        "}\n"
    )
    (chrome_dir / "userChrome.css").write_text(css, encoding="utf-8")
    print(f"Firefox userChrome.css written to {chrome_dir}.")


def resolve_firefox_theme_id(profile_path: Path, firefox_cfg: Dict[str, Any]) -> Optional[str]:
    if firefox_cfg.get("theme_id"):
        return firefox_cfg["theme_id"]

    theme_name = firefox_cfg.get("theme_name")
    if not theme_name:
        return None

    addons_path = profile_path / "addons.json"
    if not addons_path.exists():
        return None

    try:
        data = json.loads(addons_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    for addon in data.get("addons", []):
        if addon.get("type") != "theme":
            continue
        localized_name = addon.get("name") or addon.get("defaultLocale", {}).get("name")
        if localized_name and localized_name.lower() == theme_name.lower():
            return addon.get("id")

    return None


def format_firefox_pref(key: str, value: Any) -> str:
    if isinstance(value, bool):
        literal = "true" if value else "false"
    elif isinstance(value, (int, float)):
        literal = str(value)
    else:
        literal = json.dumps(value)
    return f'user_pref("{key}", {literal});'


def write_firefox_userjs(profile_path: Path, prefs: Dict[str, Any]) -> None:
    user_js_path = profile_path / "user.js"
    existing_lines: list[str] = []

    if user_js_path.exists():
        for raw_line in user_js_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("user_pref("):
                pref_key = stripped.split(",", 1)[0].split("(", 1)[1].strip().strip('"')
                if pref_key in prefs:
                    continue
            existing_lines.append(raw_line)

    for key, value in prefs.items():
        existing_lines.append(format_firefox_pref(key, value))

    user_js_path.write_text("\n".join(existing_lines) + "\n", encoding="utf-8")


def ensure_firefox_theme_payload(profile_path: Path, firefox_cfg: Dict[str, Any]) -> Optional[Path]:
    """Copy Firefox theme XPI payloads from the repo into the active profile."""
    theme_id = firefox_cfg.get("theme_id")
    xpi_hint = firefox_cfg.get("xpi")

    source_path: Optional[Path] = None
    if xpi_hint:
        source_path = Path(xpi_hint).expanduser()
    elif theme_id:
        source_path = FIREFOX_THEME_PAYLOAD_DIR / f"{theme_id}.xpi"

    if not source_path or not source_path.exists():
        if source_path:
            print(f"Firefox theme payload not found at {source_path}.")
        return None

    extensions_dir = profile_path / "extensions"
    extensions_dir.mkdir(parents=True, exist_ok=True)
    dest_path = extensions_dir / source_path.name

    try:
        if dest_path.exists() and filecmp.cmp(source_path, dest_path, shallow=False):
            return dest_path
    except OSError:
        # Fall back to copying if filecmp fails (e.g., permissions)
        pass

    try:
        shutil.copy2(source_path, dest_path)
        print(f"Synced Firefox theme payload: {source_path.name}")
    except OSError as exc:
        print(f"Failed to sync Firefox theme payload {source_path}: {exc}")
        return None

    return dest_path


def set_firefox_theme_activation(profile_path: Path, theme_id: str) -> bool:
    """Update extensions.json so the requested theme is the only active profile theme.

    Returns True if the theme was found (and activated), False otherwise.
    """
    extensions_json = profile_path / "extensions.json"
    if not extensions_json.exists():
        print("Firefox extensions.json not found; cannot activate theme.")
        return False

    try:
        data = json.loads(extensions_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Firefox extensions.json is not valid JSON; cannot activate theme.")
        return False

    addons = data.get("addons", [])
    found = False
    changed = False

    for addon in addons:
        if addon.get("type") != "theme":
            continue
        if addon.get("location") not in {"app-profile", "profile", "app-system-profile", "app-builtin"}:
            continue

        is_target = addon.get("id") == theme_id
        if is_target:
            found = True

        desired_active = is_target
        desired_user_disabled = not is_target

        if addon.get("active") != desired_active:
            addon["active"] = desired_active
            changed = True
        if addon.get("userDisabled") != desired_user_disabled:
            addon["userDisabled"] = desired_user_disabled
            changed = True

    if not found:
        print(f"Firefox theme {theme_id} is not installed; cannot activate theme.")
        return False

    if changed:
        extensions_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("Firefox extensions.json updated with new active theme.")
    return True


def update_firefox(theme: Dict[str, Any]) -> None:
    profile_path = get_default_firefox_profile()
    if not profile_path:
        print("Firefox profile not found; skipping Firefox theme.")
        return

    # Check if Firefox is running. If so, extensions.json is owned by the
    # running process and any changes will be overwritten on exit.
    # user.js and userChrome.css are safe to write; they take effect on restart.
    firefox_running = _is_process_running("firefox") or _is_process_running("firefox-bin")

    prefs: Dict[str, Any] = parse_user_js(FIREFOX_BASE_PREFS_FILE)
    prefs.update(FIREFOX_ENFORCED_PREFS)

    # Mirror the theme's dark/light preference to Firefox content pages.
    is_dark = is_dark_color(theme.get("background", "#000000"))
    prefs["ui.systemUsesDarkTheme"] = 1 if is_dark else 0

    firefox_cfg = theme.get("firefox")
    active_theme_id: Optional[str] = None

    if firefox_cfg:
        prefs.update(firefox_cfg.get("prefs", {}))
        ensure_firefox_theme_payload(profile_path, firefox_cfg)
        if not firefox_running:
            candidate_id = resolve_firefox_theme_id(profile_path, firefox_cfg)
            if candidate_id and set_firefox_theme_activation(profile_path, candidate_id):
                active_theme_id = candidate_id
            elif firefox_cfg.get("theme_name") or firefox_cfg.get("theme_id"):
                print(
                    "Firefox theme payload not found or not installed — "
                    "falling back to built-in compact theme."
                )

    if not active_theme_id and not firefox_running:
        # Use built-in compact dark/light — always present, no install needed.
        builtin_id = get_firefox_builtin_theme_id(theme)
        if set_firefox_theme_activation(profile_path, builtin_id):
            active_theme_id = builtin_id

    if active_theme_id:
        prefs["extensions.activeThemeID"] = active_theme_id

    write_firefox_userchrome(profile_path, theme)
    write_firefox_userjs(profile_path, prefs)

    if firefox_running:
        print("Firefox is running — userChrome.css and user.js updated.")
        try:
            subprocess.run(
                ["notify-send", "--app-name=hyprconf",
                 "Firefox restart needed",
                 "Restart Firefox for theme changes to take full effect."],
                check=False, capture_output=True, timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    else:
        label = active_theme_id or "(no theme activated)"
        print(f"Firefox updated: theme={label}, userChrome.css written at {profile_path}.")


def _resolve_gtk_theme(theme: Dict[str, str]) -> str:
    """Pick a GTK theme name: use the theme JSON's 'gtk_theme' key if set,
    otherwise choose adw-gtk3-dark/-light based on background luminance,
    falling back to Breeze-Dark/Breeze if adw-gtk3 is not installed."""
    if "gtk_theme" in theme:
        return theme["gtk_theme"]

    is_dark = is_dark_color(theme.get("background", "#1e1e2e"))
    candidates = (
        ("adw-gtk3-dark", "adw-gtk3") if is_dark else ("adw-gtk3", "adw-gtk3-dark")
    )
    fallbacks = ("Breeze-Dark", "Breeze") if is_dark else ("Breeze", "Breeze-Dark")
    theme_dirs = ["/usr/share/themes", os.path.expanduser("~/.local/share/themes")]

    def installed(name: str) -> bool:
        return any(os.path.isdir(os.path.join(d, name)) for d in theme_dirs)

    for name in candidates:
        if installed(name):
            return name
    for name in fallbacks:
        if installed(name):
            return name
    return candidates[0]


def update_gtk(theme: Dict[str, str]) -> None:
    """Apply the theme to GTK 3/4 settings, xsettingsd, and gsettings."""
    is_dark      = is_dark_color(theme.get("background", "#1e1e2e"))
    gtk_theme    = _resolve_gtk_theme(theme)
    icon_theme   = "Papirus-Dark" if is_dark else "Papirus-Light"
    color_scheme = "prefer-dark" if is_dark else "prefer-light"
    dark_val     = "true" if is_dark else "false"

    def patch_ini(path: str) -> None:
        with open(path) as f:
            content = f.read()
        content = re.sub(
            r"^(gtk-theme-name\s*=).*$", f"gtk-theme-name={gtk_theme}",
            content, flags=re.MULTILINE,
        )
        content = re.sub(
            r"^(gtk-icon-theme-name\s*=).*$", f"gtk-icon-theme-name={icon_theme}",
            content, flags=re.MULTILINE,
        )
        content = re.sub(
            r"^(gtk-application-prefer-dark-theme\s*=).*$",
            f"gtk-application-prefer-dark-theme={dark_val}",
            content, flags=re.MULTILINE,
        )
        with open(path, "w") as f:
            f.write(content)

    for ini_path in (GTK3_SETTINGS_FILE, GTK4_SETTINGS_FILE):
        os.makedirs(os.path.dirname(ini_path), exist_ok=True)
        if not os.path.exists(ini_path):
            try:
                with open(ini_path, "w") as f:
                    f.write("[Settings]\n")
                    f.write(f"gtk-theme-name={gtk_theme}\n")
                    f.write(f"gtk-icon-theme-name={icon_theme}\n")
                    f.write(f"gtk-application-prefer-dark-theme={dark_val}\n")
            except Exception as e:
                print(f"Warning: could not create {ini_path}: {e}")
                continue
        try:
            patch_ini(ini_path)
            print(f"Updated {ini_path}")
        except Exception as e:
            print(f"Warning: could not update {ini_path}: {e}")

    # xsettingsd — signals running GTK apps to reload the theme immediately.
    # Create the config if it doesn't exist (xsettingsd must be in autostart).
    try:
        os.makedirs(os.path.dirname(XSETTINGSD_CONFIG_FILE), exist_ok=True)
        if os.path.exists(XSETTINGSD_CONFIG_FILE):
            with open(XSETTINGSD_CONFIG_FILE) as f:
                lines = f.readlines()
            patched = False
            new_lines = []
            for line in lines:
                if line.startswith("Net/ThemeName"):
                    new_lines.append(f'Net/ThemeName "{gtk_theme}"\n')
                    patched = True
                elif line.startswith("Net/IconThemeName"):
                    new_lines.append(f'Net/IconThemeName "{icon_theme}"\n')
                else:
                    new_lines.append(line)
            if not patched:
                new_lines.append(f'Net/ThemeName "{gtk_theme}"\n')
            if not any(l.startswith("Net/IconThemeName") for l in lines):
                new_lines.append(f'Net/IconThemeName "{icon_theme}"\n')
            with open(XSETTINGSD_CONFIG_FILE, "w") as f:
                f.writelines(new_lines)
        else:
            with open(XSETTINGSD_CONFIG_FILE, "w") as f:
                f.write(f'Net/ThemeName "{gtk_theme}"\n')
                f.write(f'Net/IconThemeName "{icon_theme}"\n')
        pid_result = subprocess.run(["pgrep", "-x", "xsettingsd"], capture_output=True, text=True)
        if pid_result.returncode == 0:
            for pid in pid_result.stdout.strip().splitlines():
                subprocess.run(["kill", "-HUP", pid.strip()], check=False)
            print("Reloaded xsettingsd.")
    except Exception as e:
        print(f"Warning: could not update xsettingsd: {e}")

    # gsettings — affects GTK apps and Qt apps using the GNOME platform plugin
    gsettings = shutil.which("gsettings")
    if gsettings:
        cmds = [
            [gsettings, "set", "org.gnome.desktop.interface", "gtk-theme", gtk_theme],
            [gsettings, "set", "org.gnome.desktop.interface", "icon-theme", icon_theme],
            [gsettings, "set", "org.gnome.desktop.interface", "color-scheme", color_scheme],
        ]
        for cmd in cmds:
            try:
                subprocess.run(cmd, check=False)
            except Exception as e:
                print(f"Warning: gsettings failed ({' '.join(cmd[3:])}): {e}")

    # hyprctl setenv — updates GTK_THEME for all apps launched after this point.
    # Running apps receive the theme via xsettingsd (above) or a restart below.
    hyprctl = shutil.which("hyprctl")
    if hyprctl:
        try:
            subprocess.run([hyprctl, "setenv", "GTK_THEME", gtk_theme], check=False, capture_output=True)
            subprocess.run([hyprctl, "setenv", "GTK_ICON_THEME", icon_theme], check=False, capture_output=True)
        except Exception:
            pass

    # systemctl --user set-environment — persists GTK_THEME in the systemd user manager
    # so that D-Bus-activated user services (e.g. blueman-manager, which is a SEPARATE
    # process launched on demand via D-Bus, not a child of blueman-applet) also inherit
    # the correct theme.  hyprctl setenv does not affect the systemd user environment.
    systemctl = shutil.which("systemctl")
    if systemctl:
        try:
            subprocess.run(
                [systemctl, "--user", "set-environment", f"GTK_THEME={gtk_theme}",
                 f"GTK_ICON_THEME={icon_theme}"],
                check=False, capture_output=True,
            )
        except Exception:
            pass

    # Restart blueman-applet (and kill any running blueman-manager) so both processes
    # pick up the new GTK theme on next launch.
    #
    # GTK3 apps read GTK_THEME at launch only; we must therefore:
    #  1. Kill blueman-applet → relaunch with explicit GTK_THEME in env.
    #  2. Kill blueman-manager — it is D-Bus-activated as a SEPARATE systemd user service
    #     (blueman-manager.service / org.blueman.Manager).  The manager window will re-
    #     activate on the user's next click and inherit GTK_THEME from the systemd env
    #     set above.
    # A brief sleep after SIGTERM prevents a race where both old and new applet processes
    # coexist and the old one reclaims the tray slot.
    proc = subprocess.run(["pgrep", "-x", "blueman-applet"], capture_output=True, text=True)
    if proc.returncode == 0:
        for pid in proc.stdout.split():
            try:
                os.kill(int(pid), 15)  # SIGTERM
            except (ProcessLookupError, ValueError):
                pass

        mgr_proc = subprocess.run(["pgrep", "-x", "blueman-manager"], capture_output=True, text=True)
        if mgr_proc.returncode == 0:
            for pid in mgr_proc.stdout.split():
                try:
                    os.kill(int(pid), 15)  # SIGTERM
                except (ProcessLookupError, ValueError):
                    pass

        time.sleep(0.3)
        bt_env = dict(os.environ, GTK_THEME=gtk_theme, GTK_ICON_THEME=icon_theme)
        subprocess.Popen(
            ["blueman-applet"],
            env=bt_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print("Blueman applet restarted.")

    print(f"GTK theme set to '{gtk_theme}' ({color_scheme}).")


def update_kde_colors(theme: Dict[str, str]) -> None:
    """Generate ~/.config/kdeglobals KDE color scheme and Trolltech.conf from the theme palette.

    kdeglobals is read directly by KConfig (used by Dolphin, Ark, Gwenview, etc.) regardless
    of whether a full KDE Plasma session is running.  Trolltech.conf sets the fallback Qt style
    for apps that don't use a platform theme plugin.
    """
    bg      = theme.get("background", "#1e1e2e")
    fg      = theme.get("foreground", "#cdd6f4")
    accent  = theme.get("accent",     theme.get("purple", "#bd93f9"))
    comment = theme.get("comment",    "#6272a4")
    red     = theme.get("red",        "#f38ba8")
    green   = theme.get("green",      "#a6e3a1")
    yellow  = theme.get("yellow",     "#f9e2af")
    cyan    = theme.get("cyan",       "#89dceb")

    btn_bg  = blend_colors(bg, fg, 0.10)   # slightly raised surface for buttons
    # 10% blend gives ~1.25:1 contrast against the base — perceptible to the eye
    # without triggering KDE's contrast-enforcement (contrast=4) which would
    # overshoot a 5% blend to a clearly-light shade in dark themes like Dracula.
    alt_bg  = blend_colors(bg, fg, 0.10)   # alternate row background
    sel_fg  = bg if is_dark_color(bg) else fg  # legible text on accent selection

    def rgb(h: str) -> str:
        return hex_to_rgb_str(h)

    def color_section(bg_n: str, bg_a: str, fg_n: str) -> str:
        return (
            f"BackgroundAlternate={rgb(bg_a)}\n"
            f"BackgroundNormal={rgb(bg_n)}\n"
            f"DecorationFocus={rgb(accent)}\n"
            f"DecorationHover={rgb(blend_colors(accent, bg, 0.6))}\n"
            f"ForegroundActive={rgb(accent)}\n"
            f"ForegroundInactive={rgb(comment)}\n"
            f"ForegroundLink={rgb(cyan)}\n"
            f"ForegroundNegative={rgb(red)}\n"
            f"ForegroundNeutral={rgb(yellow)}\n"
            f"ForegroundNormal={rgb(fg_n)}\n"
            f"ForegroundPositive={rgb(green)}\n"
            f"ForegroundVisited={rgb(comment)}\n"
        )

    content = (
        "# Generated by switch_theme.py — do not edit manually\n"
        "\n"
        "[ColorEffects:Disabled]\n"
        "ChangeSelectionColor=true\n"
        "Color=112,111,110\n"
        "ColorAmount=0\n"
        "ColorEffect=0\n"
        "ContrastAmount=0.65\n"
        "ContrastEffect=1\n"
        "Enable=false\n"
        "IntensityAmount=0.1\n"
        "IntensityEffect=2\n"
        "\n"
        "[ColorEffects:Inactive]\n"
        "ChangeSelectionColor=true\n"
        "Color=112,111,110\n"
        "ColorAmount=0.025\n"
        "ColorEffect=2\n"
        "ContrastAmount=0.1\n"
        "ContrastEffect=2\n"
        "Enable=false\n"
        "IntensityAmount=0\n"
        "IntensityEffect=0\n"
        "\n"
        "[Colors:Button]\n"
        + color_section(btn_bg, blend_colors(bg, fg, 0.15), fg)
        + "\n"
        "[Colors:Complementary]\n"
        + color_section(blend_colors(bg, fg, 0.08), blend_colors(bg, fg, 0.12), fg)
        + "\n"
        "[Colors:Header]\n"
        + color_section(blend_colors(bg, fg, 0.03), blend_colors(bg, fg, 0.06), fg)
        + "\n"
        "[Colors:Selection]\n"
        f"BackgroundAlternate={rgb(blend_colors(accent, bg, 0.3))}\n"
        f"BackgroundNormal={rgb(accent)}\n"
        f"DecorationFocus={rgb(accent)}\n"
        f"DecorationHover={rgb(accent)}\n"
        f"ForegroundActive={rgb(sel_fg)}\n"
        f"ForegroundInactive={rgb(sel_fg)}\n"
        f"ForegroundLink={rgb(sel_fg)}\n"
        f"ForegroundNegative={rgb(red)}\n"
        f"ForegroundNeutral={rgb(yellow)}\n"
        f"ForegroundNormal={rgb(sel_fg)}\n"
        f"ForegroundPositive={rgb(green)}\n"
        f"ForegroundVisited={rgb(sel_fg)}\n"
        "\n"
        "[Colors:Tooltip]\n"
        + color_section(btn_bg, blend_colors(bg, fg, 0.15), fg)
        + "\n"
        "[Colors:View]\n"
        + color_section(bg, alt_bg, fg)
        + "\n"
        "[Colors:Window]\n"
        + color_section(bg, alt_bg, fg)
        + "\n"
        "[General]\n"
        "ColorScheme=SwitchThemeGenerated\n"
        "Name=SwitchTheme Generated\n"
        "shadeSortColumn=true\n"
        "\n"
        "[KDE]\n"
        "contrast=4\n"
        "widgetStyle=breeze\n"
        "\n"
        "[WM]\n"
        f"activeBackground={rgb(blend_colors(bg, fg, 0.10))}\n"
        f"activeBlend={rgb(fg)}\n"
        f"activeForeground={rgb(fg)}\n"
        f"inactiveBackground={rgb(bg)}\n"
        f"inactiveBlend={rgb(comment)}\n"
        f"inactiveForeground={rgb(comment)}\n"
    )

    kdeglobals_path = Path(KDEGLOBALS_FILE)
    kdeglobals_path.parent.mkdir(parents=True, exist_ok=True)
    kdeglobals_path.write_text(content, encoding="utf-8")
    print("KDE color scheme (kdeglobals) updated.")

    # Also write a standalone .colors file so plasma-apply-colorscheme can find it.
    # plasma-apply-colorscheme forces a live reload in all running KDE apps (Dolphin, etc.).
    colors_dir = Path(KDE_COLOR_SCHEMES_DIR)
    colors_dir.mkdir(parents=True, exist_ok=True)
    colors_file = colors_dir / "SwitchThemeGenerated.colors"
    colors_file.write_text(content, encoding="utf-8")

    # plasma-apply-colorscheme is the most reliable way to reload colours in running
    # KDE apps (Dolphin, Ark, Gwenview …).  Fall back to the legacy DBus signal.
    applied = False
    if shutil.which("plasma-apply-colorscheme"):
        result = subprocess.run(
            ["plasma-apply-colorscheme", "SwitchThemeGenerated"],
            check=False, capture_output=True,
        )
        applied = result.returncode == 0

    if not applied and shutil.which("dbus-send"):
        # notifyChange(uint id, uint flags): id=1 is PaletteChanged — the signal that
        # tells running KDE/Qt apps (Dolphin, etc.) to reload their QPalette from the
        # updated kdeglobals.  id=0 (StyleChanged) does NOT trigger a palette refresh,
        # so alternate row colours in Dolphin stay stale until the app is restarted.
        subprocess.run(
            [
                "dbus-send", "--session", "--type=signal",
                "/KGlobalSettings",
                "org.kde.KGlobalSettings.notifyChange",
                "int32:1", "int32:0",
            ],
            check=False, capture_output=True,
        )
    print("Qt/KDE theme updated.")

    # Write ColorScheme=SwitchThemeGenerated to dolphinrc so Dolphin uses the
    # new palette without requiring a manual Settings → Configure step.
    # kwriteconfig6 is the canonical tool; fall back to kwriteconfig5.
    for kwrite in ("kwriteconfig6", "kwriteconfig5"):
        if shutil.which(kwrite):
            subprocess.run(
                [kwrite, "--file", "dolphinrc",
                 "--group", "General",
                 "--key", "ColorScheme", "SwitchThemeGenerated"],
                check=False, capture_output=True,
            )
            break


def update_qt_platform_theme(theme: Dict[str, str]) -> None:
    """Configure qt6ct (and qt5ct if installed) with a QPalette derived from the theme.

    When qt6ct/qt5ct are installed and QT_QPA_PLATFORMTHEME is set to qt5ct/qt6ct,
    this ensures those tools have the correct palette.  On systems using
    QT_QPA_PLATFORMTHEME=kde (KDEPlasmaPlatformTheme6), colours come from kdeglobals
    instead — handled by update_kde_colors().  Writing these files is harmless
    either way and keeps both paths working.
    """
    bg       = theme.get("background", "#1e1e2e")
    fg       = theme.get("foreground", "#cdd6f4")
    accent   = theme.get("accent",     theme.get("purple", "#bd93f9"))
    cyan     = theme.get("cyan",       "#89dceb")
    dark     = is_dark_color(bg)

    btn_bg   = blend_colors(bg, fg, 0.10)
    light_bg = blend_colors(bg, fg, 0.22)
    midlight = blend_colors(bg, fg, 0.16)
    dark_bg  = blend_colors(bg, "#000000", 0.22)
    mid_bg   = blend_colors(bg, fg, 0.08)
    alt_bg   = blend_colors(bg, fg, 0.10)   # alternate row — matches kdeglobals alt_bg
    shadow   = blend_colors(bg, "#000000", 0.45)
    tooltip  = blend_colors(bg, fg, 0.08)
    sel_fg   = bg if dark else fg
    link_vis = theme.get("purple", accent)
    bright   = "#ffffff" if dark else "#000000"
    ph_fg    = blend_colors(fg, bg, 0.50)

    # QPalette roles 0-20 in declaration order:
    # WindowText, Button, Light, Midlight, Dark, Mid, Text, BrightText, ButtonText,
    # Base, Window, Shadow, Highlight, HighlightedText, Link, LinkVisited,
    # AlternateBase, NoRole, ToolTipBase, ToolTipText, PlaceholderText
    active = [
        fg,       btn_bg,   light_bg, midlight, dark_bg, mid_bg,
        fg,       bright,   fg,
        bg,       bg,       shadow,
        accent,   sel_fg,
        cyan,     link_vis,
        alt_bg,   bg,
        tooltip,  fg,
        ph_fg,
    ]
    inactive = list(active)

    def dim(c: str) -> str:
        return blend_colors(c, bg, 0.50)

    disabled = [
        dim(fg),  btn_bg,   light_bg, midlight, dark_bg, mid_bg,
        dim(fg),  dim(bright), dim(fg),
        bg,       bg,       shadow,
        mid_bg,   dim(fg),
        dim(cyan), dim(link_vis),
        alt_bg,   bg,
        tooltip,  dim(fg),
        dim(ph_fg),
    ]

    scheme = (
        "# Generated by switch_theme.py — do not edit manually\n"
        "[ColorScheme]\n"
        f"active_colors={', '.join(active)}\n"
        f"disabled_colors={', '.join(disabled)}\n"
        f"inactive_colors={', '.join(inactive)}\n"
    )

    def _patch_qt_conf(conf_path: str, colors_path: str) -> None:
        """Enable custom_palette and point color_scheme_path in a qt5ct/qt6ct .conf."""
        p = Path(conf_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""

        if "[Appearance]" not in text:
            text = "[Appearance]\n" + text

        def set_key(content: str, key: str, value: str) -> str:
            pattern = rf"^{re.escape(key)}\s*=.*$"
            replacement = f"{key}={value}"
            if re.search(pattern, content, re.MULTILINE):
                return re.sub(pattern, replacement, content, flags=re.MULTILINE)
            return re.sub(r"(\[Appearance\]\n)", rf"\1{key}={value}\n", content, count=1)

        text = set_key(text, "color_scheme_path", colors_path)
        text = set_key(text, "custom_palette", "true")
        p.write_text(text, encoding="utf-8")

    for conf_path, colors_path in (
        (QT6CT_CONF_FILE, QT6CT_COLORS_FILE),
        (QT5CT_CONF_FILE, QT5CT_COLORS_FILE),
    ):
        try:
            colors_p = Path(colors_path)
            colors_p.parent.mkdir(parents=True, exist_ok=True)
            colors_p.write_text(scheme, encoding="utf-8")
            _patch_qt_conf(conf_path, colors_path)
            suite = Path(conf_path).parent.name  # "qt6ct" or "qt5ct"
            print(f"{suite} colour scheme written.")
        except Exception as e:
            print(f"Warning: could not update {conf_path}: {e}")


def update_wvkbd(theme: Dict[str, str]) -> None:
    """Write ~/.config/wvkbd/colors and restart wvkbd-launcher if running."""
    wvkbd_config_dir = Path.home() / ".config" / "wvkbd"
    colors_file = wvkbd_config_dir / "colors"

    bg     = theme.get("background", "")
    fg     = theme.get("foreground", "")
    accent = theme.get("accent", "")

    if not bg:
        return

    try:
        wvkbd_config_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f'bg="{bg}"\n',
            f'fg="{fg}"\n',
            f'accent="{accent}"\n',
        ]
        colors_file.write_text("".join(lines), encoding="utf-8")
        print("wvkbd colors written.")
    except Exception as e:
        print(f"Warning: could not write wvkbd colors: {e}")
        return

    # Restart the launcher only if wvkbd is currently running — the new
    # launcher process will pick up the updated colors file.
    try:
        result = subprocess.run(
            ["pgrep", "-x", "wvkbd-mobintl"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            launcher = shutil.which("wvkbd-launcher")
            if launcher:
                subprocess.Popen([launcher])
                print("wvkbd restarted with new theme.")
    except Exception as e:
        print(f"Warning: could not restart wvkbd: {e}")


def update_touch_panel(theme: Dict[str, str]) -> None:
    """Write ~/.config/touch-panel/colors and signal the panel to reload.

    The touch-panel script reloads colors on SIGUSR1 without restarting, so
    the panel remains open and the theme change is instant.
    """
    bg     = theme.get("background", "")
    fg     = theme.get("foreground", "")
    accent = theme.get("accent", "")

    if not bg:
        return

    try:
        config_dir = Path(TOUCH_PANEL_COLORS_FILE).parent
        config_dir.mkdir(parents=True, exist_ok=True)
        Path(TOUCH_PANEL_COLORS_FILE).write_text(
            f'bg="{bg}"\nfg="{fg}"\naccent="{accent}"\n',
            encoding="utf-8",
        )
        print("touch-panel colors written.")
    except OSError as exc:
        print(f"Warning: could not write touch-panel colors: {exc}")
        return

    # touch-panel is a Python script; the kernel exec's python3 so the process
    # comm is "python3", not "touch-panel".  Use -f to match against the full
    # command line instead.  The $ anchor avoids matching "touch-panel-launcher".
    result = subprocess.run(
        ["pgrep", "-f", "touch-panel$"], capture_output=True, text=True
    )
    if result.returncode == 0:
        for pid_str in result.stdout.strip().splitlines():
            try:
                os.kill(int(pid_str), signal.SIGUSR1)
            except (ProcessLookupError, ValueError):
                pass
        print("touch-panel signalled to reload colors.")


def apply_theme(theme_name: str, reload: bool = True) -> None:
    """Apply the selected theme to all relevant config files."""
    print(f"Switching to theme: {theme_name}")
    theme = load_theme(theme_name)

    def ensure_vscode_extension_payload(extension_id: Optional[str]) -> None:
        """Copy VS Code theme extension payloads locally so CLI installs are optional."""
        if not extension_id:
            return

        source_root = REPO_ROOT / "theme" / ".vscode-oss" / "extensions"
        if not source_root.exists():
            return

        matches = [
            candidate
            for candidate in source_root.iterdir()
            if candidate.is_dir()
            and (candidate.name == extension_id or candidate.name.startswith(f"{extension_id}-"))
        ]

        if not matches:
            return

        # Prefer the lexicographically last match (usually the latest version)
        ext_source = sorted(matches, key=lambda path: path.name)[-1]
        dest_root = Path.home() / ".vscode-oss" / "extensions"
        dest_root.mkdir(parents=True, exist_ok=True)
        ext_dest = dest_root / ext_source.name

        if ext_dest.exists():
            if ext_dest.is_symlink():
                ext_dest.unlink()
            else:
                return

        shutil.copytree(ext_source, ext_dest)
        print(f"Synced VS Code extension payload: {ext_source.name}")

    # Apply Kitty theme: use declared conf file, or generate one from palette
    if "kitty" in theme:
        load_kitty_theme(theme["kitty"])
    else:
        generated = generate_kitty_theme(theme)
        load_kitty_theme(generated)

    update_waybar(theme)
    update_hyprpaper(theme)
    update_hyprtoolkit(theme)
    update_dunst(theme)
    update_gtk(theme)
    update_kde_colors(theme)
    update_qt_platform_theme(theme)
    if "vscode" in theme:
        ensure_vscode_extension_payload(theme["vscode"].get("extension"))
    update_vscode(theme)
    update_firefox(theme)
    update_hyprland_borders(theme)
    update_hyprlock_colors(theme)
    if shutil.which("wvkbd-mobintl"):
        update_wvkbd(theme)
    if shutil.which("touch-panel"):
        update_touch_panel(theme)
    if reload:
        reload_hyprland()
    write_state(theme_name)
    notify_theme_change(theme_name, theme)
    print("Theme applied successfully.")

# === Entry Point ===
def list_themes() -> None:
    """Print a pretty table of all available themes and their accent colors."""
    current = read_state()
    themes = []
    for fname in sorted(os.listdir(THEMES_DIR)):
        if not fname.endswith(".json"):
            continue
        name = fname[:-5]
        try:
            with open(os.path.join(THEMES_DIR, fname)) as _fh:
                d = json.load(_fh)
        except Exception:
            continue
        bg      = d.get("background", "")
        fg      = d.get("foreground", "")
        accent  = d.get("accent", d.get("purple", ""))
        themes.append((name, bg, fg, accent))

    col_name   = max(len("THEME"),      max(len(t[0]) for t in themes))
    col_bg     = max(len("BACKGROUND"), max(len(t[1]) for t in themes))
    col_fg     = max(len("FOREGROUND"), max(len(t[2]) for t in themes))
    col_accent = max(len("ACCENT"),     max(len(t[3]) for t in themes))

    # ANSI helpers
    def ansi_swatch(hex_color: str, text: str) -> str:
        h = hex_color.lstrip("#")
        if len(h) != 6:
            return text
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"\033[38;2;{r};{g};{b}m{text}\033[0m"

    def bold(text: str) -> str:
        return f"\033[1m{text}\033[0m"

    sep = f"  {'─' * col_name}  {'─' * col_bg}  {'─' * col_fg}  {'─' * col_accent}"
    header = (
        f"  {bold(f'{'THEME':<{col_name}}')}  "
        f"{bold(f'{'BACKGROUND':<{col_bg}}')}  "
        f"{bold(f'{'FOREGROUND':<{col_fg}}')}  "
        f"{bold(f'{'ACCENT':<{col_accent}}')}"
    )
    print(sep)
    print(header)
    print(sep)
    for name, bg, fg, accent in themes:
        marker = "★ " if name == current else "  "
        row = (
            f"  {marker}{name:<{col_name}}  "
            f"{ansi_swatch(bg,  f'{bg:<{col_bg}}')}  "
            f"{ansi_swatch(fg,  f'{fg:<{col_fg}}')}  "
            f"{ansi_swatch(accent, f'{accent:<{col_accent}}')}"
        )
        print(row)
    print(sep)
    active_note = f"  · active: {current}" if current else ""
    print(f"  {len(themes)} themes available{active_note}")


def interactive_select(initial_filter: str = "") -> Optional[str]:
    """Arrow-key + type-to-filter theme selector with ANSI colour swatches."""
    import curses

    all_themes = get_all_themes()
    current    = read_state()

    theme_data: Dict[str, Dict] = {}
    for name in all_themes:
        try:
            with open(os.path.join(THEMES_DIR, f"{name}.json")) as _fh:
                theme_data[name] = json.load(_fh)
        except Exception:
            theme_data[name] = {}

    selected: list[Optional[str]] = [None]

    def _swatch(hex_c: str, width: int = 2) -> str:
        """Truecolor ANSI background block — renders in kitty and modern terminals."""
        h = (hex_c or "").lstrip("#")
        if len(h) != 6:
            return " " * width
        r2, g2, b2 = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"\033[48;2;{r2};{g2};{b2}m{' ' * width}\033[0m"

    def _menu(stdscr: "curses._CursesWindow") -> None:  # type: ignore[name-defined]
        curses.curs_set(0)
        curses.use_default_colors()
        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # highlighted
        curses.init_pair(2, curses.COLOR_WHITE, -1)                   # normal
        curses.init_pair(3, curses.COLOR_YELLOW, -1)                  # active theme

        search = initial_filter
        idx    = 0

        while True:
            themes = [t for t in all_themes if search.lower() in t.lower()] if search else all_themes
            idx    = min(idx, max(0, len(themes) - 1))

            max_h, max_w = stdscr.getmaxyx()
            visible      = max_h - 8

            stdscr.erase()

            # ── Header ─────────────────────────────────────────────────────────
            header = "Theme Switcher  (↑↓/jk · Enter apply · type to filter · Esc clear · q quit)"
            stdscr.addstr(0, 0, header[:max_w - 1], curses.A_BOLD)
            stdscr.addstr(1, 0, "─" * min(max_w - 1, 78))

            # ── Search bar ─────────────────────────────────────────────────────
            prompt = f"  / {search}▌" if search else "  / (type to filter)"
            stdscr.addstr(2, 0, prompt[:max_w - 1])
            stdscr.addstr(3, 0, "─" * min(max_w - 1, 78))

            # ── Theme list ─────────────────────────────────────────────────────
            start = max(0, idx - visible + 1)
            for row_i, t_idx in enumerate(range(start, min(start + visible, len(themes)))):
                name       = themes[t_idx]
                d          = theme_data.get(name, {})
                bg_col     = d.get("background", "")
                accent_col = d.get("accent", d.get("purple", ""))
                cyan_col   = d.get("cyan",   "")
                green_col  = d.get("green",  "")
                red_col    = d.get("red",    "")
                is_current = name == current
                marker     = "★ " if is_current else "  "

                swatches = (
                    _swatch(bg_col)     + " " +
                    _swatch(accent_col) + " " +
                    _swatch(cyan_col)   + " " +
                    _swatch(green_col)  + " " +
                    _swatch(red_col)
                )
                text_part = f"{marker}{name:<34}  {bg_col:<8}"

                y = row_i + 4
                if y >= max_h - 2:
                    break

                if t_idx == idx:
                    attr = curses.color_pair(1) | curses.A_BOLD
                elif is_current:
                    attr = curses.color_pair(3) | curses.A_BOLD
                else:
                    attr = curses.color_pair(2)

                stdscr.addstr(y, 0, ("  " + text_part)[:max_w - 1], attr)
                # Append ANSI colour swatches at fixed column (truecolor, bypasses curses accounting)
                swatch_col = 2 + 2 + 34 + 2 + 9
                if swatch_col < max_w - 16:
                    try:
                        stdscr.addstr(y, swatch_col, swatches)
                    except curses.error:
                        pass

            # ── Footer ─────────────────────────────────────────────────────────
            match_info = f"  {len(themes)}/{len(all_themes)} themes"
            if current:
                match_info += f"  · active: {current}"
            stdscr.addstr(min(start + visible + 4, max_h - 1), 0, match_info[:max_w - 1])
            stdscr.refresh()

            # ── Input ──────────────────────────────────────────────────────────
            key = stdscr.getch()

            if key == curses.KEY_UP or (key == ord("k") and not search):
                idx = (idx - 1) % len(themes) if themes else 0
            elif key == curses.KEY_DOWN or (key == ord("j") and not search):
                idx = (idx + 1) % len(themes) if themes else 0
            elif key == curses.KEY_PPAGE:
                idx = max(0, idx - visible)
            elif key == curses.KEY_NPAGE:
                idx = min(len(themes) - 1, idx + visible) if themes else 0
            elif key == curses.KEY_HOME or (key == ord("g") and not search):
                idx = 0
            elif key == curses.KEY_END or (key == ord("G") and not search):
                idx = len(themes) - 1 if themes else 0
            elif key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                if themes:
                    selected[0] = themes[idx]
                break
            elif key == 27:  # Escape — clear search first, then quit
                if search:
                    search = ""
                    idx = 0
                else:
                    break
            elif key == ord("q") and not search:
                break
            elif key in (curses.KEY_BACKSPACE, 127):
                search = search[:-1]
                idx = 0
            elif 32 <= key <= 126:
                search += chr(key)
                idx = 0

    curses.wrapper(_menu)
    return selected[0]


def wofi_select(initial_filter: str = "") -> Optional[str]:
    """Select a theme via wofi --dmenu (no terminal window required)."""
    themes = get_all_themes()
    if initial_filter:
        themes = [t for t in themes if initial_filter.lower() in t.lower()]
    current = read_state()
    display = [f"★  {t}" if t == current else f"   {t}" for t in themes]
    try:
        # When launched from wofi's drun, starting a second wofi immediately can race/fail.
        time.sleep(0.15)
        proc = subprocess.run(
            ["wofi", "--dmenu", "--prompt", "Theme:", "--insensitive"],
            input="\n".join(display),
            capture_output=True,
            text=True,
        )
        result = proc.stdout.strip().lstrip("★").strip()
        return result if result in themes else None
    except FileNotFoundError:
        print("wofi not found; falling back to interactive TUI.")
        return interactive_select(initial_filter)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Switch between desktop themes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  switch_theme.py dracula         Apply the dracula theme\n"
            "  switch_theme.py --next          Next theme (alphabetical order)\n"
            "  switch_theme.py --prev          Previous theme\n"
            "  switch_theme.py --random        Apply a random theme\n"
            "  switch_theme.py --current       Print currently active theme\n"
            "  switch_theme.py --pick          Pick via hyprlauncher (no terminal needed)\n"
            "  switch_theme.py --list          List all themes with colour table\n"
            "  switch_theme.py --filter ai:    Filter to ai: themes in TUI\n"
        ),
    )
    parser.add_argument(
        "theme",
        nargs="?",
        help="Theme name to apply directly (e.g. dracula, ai:void).",
    )
    parser.add_argument("--list",      "-l", action="store_true", help="List all available themes.")
    parser.add_argument("--current",   "-c", action="store_true", help="Print the currently active theme.")
    parser.add_argument("--random",    "-r", action="store_true", help="Apply a randomly chosen theme.")
    parser.add_argument("--next",      "-n", action="store_true", help="Apply the next theme (sorted order).")
    parser.add_argument("--prev",      "-p", action="store_true", help="Apply the previous theme (sorted order).")
    parser.add_argument("--pick",      "-w", action="store_true", help="Select theme via hyprlauncher --dmenu.")
    parser.add_argument("--no-reload",       action="store_true", help="Skip hyprctl reload after applying.")
    parser.add_argument("--filter",    "-f", default="", metavar="STR",
                        help="Pre-filter themes by substring (used with TUI, --pick, --random).")

    args      = parser.parse_args()
    do_reload = not args.no_reload

    try:
        if args.current:
            state = read_state()
            print(state if state else "(no theme applied yet)")
        elif args.list:
            list_themes()
        elif args.random:
            pool = get_all_themes()
            if args.filter:
                pool = [t for t in pool if args.filter.lower() in t.lower()]
            if pool:
                choice = random.choice(pool)
                print(f"Random theme: {choice}")
                apply_theme(choice, reload=do_reload)
            else:
                print("No themes match the filter.")
        elif args.next:
            choice = get_adjacent_theme(1)
            if choice:
                print(f"Next theme: {choice}")
                apply_theme(choice, reload=do_reload)
        elif args.prev:
            choice = get_adjacent_theme(-1)
            if choice:
                print(f"Previous theme: {choice}")
                apply_theme(choice, reload=do_reload)
        elif args.pick:
            choice = launcher_select(initial_filter=args.filter)
            if choice:
                print(f"Applying theme: {choice}")
                apply_theme(choice, reload=do_reload)
            else:
                print("No theme selected.")
        elif args.theme:
            apply_theme(args.theme.lower(), reload=do_reload)
        else:
            choice = interactive_select(initial_filter=args.filter)
            if choice:
                print(f"\nApplying theme: {choice}")
                apply_theme(choice, reload=do_reload)
            else:
                print("No theme selected.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
