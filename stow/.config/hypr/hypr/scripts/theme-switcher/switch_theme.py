import configparser
import json
import os
import re
import shutil
import subprocess
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
WOFI_STYLE_FILE = os.path.expanduser("~/.config/wofi/style.css")
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
    os.path.join(REPO_ROOT, "stow", ".config", "Code - OSS", "User", "settings.base.json"),
    os.path.join(REPO_ROOT, "stow", ".config", "Code", "User", "settings.base.json"),
]
CODE_CLI = shutil.which("code-oss") or shutil.which("code")
FIREFOX_PROFILES_INI = os.path.expanduser("~/.mozilla/firefox/profiles.ini")
FIREFOX_DIR = os.path.dirname(FIREFOX_PROFILES_INI)
FIREFOX_BASE_PREFS_FILE = os.path.expanduser("~/.mozilla/firefox/user.js")
FIREFOX_THEME_PAYLOAD_DIR = REPO_ROOT / "theme" / "firefox" / "extensions"

FIREFOX_ENFORCED_PREFS = {
    "browser.tabs.verticalTabs": True,
    "browser.tabs.verticalTabs.showPinnedTabs": True,
    "browser.tabs.drawInTitlebar": True,
    "toolkit.telemetry.enabled": False,
    "toolkit.telemetry.unified": False,
    "toolkit.telemetry.archive.enabled": False,
    "toolkit.coverage.opt-out": True,
    "toolkit.telemetry.server": "data:,",
    "datareporting.healthreport.uploadEnabled": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "app.shield.optoutstudies.enabled": False,
    "app.normandy.enabled": False,
    "browser.discovery.enabled": False,
    "browser.newtabpage.activity-stream.showSponsored": False,
    "browser.newtabpage.activity-stream.showSponsoredTopSites": False,
    "browser.newtabpage.activity-stream.feeds.section.topstories": False,
    "browser.newtabpage.activity-stream.showWeather": False,
    "browser.newtabpage.activity-stream.feeds.telemetry": False,
    "browser.newtabpage.activity-stream.asrouter.userprefs.cfr.addons": False,
    "browser.newtabpage.activity-stream.asrouter.userprefs.cfr.features": False,
}

def update_wofi(theme: Dict[str, str]):
    """Generate or replace Wofi style.css using colors from the theme JSON."""
    os.makedirs(os.path.dirname(WOFI_STYLE_FILE), exist_ok=True)

    # Extract colors from the theme
    bg = theme.get("background", "#1e1e2e")
    fg = theme.get("foreground", "#ffffff")
    border = theme.get("purple", theme.get("orange", "#89b4fa"))
    input_bg = theme.get("comment", theme.get("background", "#44475a"))
    accent = theme.get("purple", theme.get("orange", "#89b4fa"))     # selection border
    selected_bg = theme.get("purple", "#89b4fa")                     # highlight background
    selected_text = theme.get("background", "#1e1e2e")               # highlight text
    hover_text = theme.get("pink", theme.get("cyan", fg))            # active/hover text

    # Build a complete Dracula/Gruvbox-compatible style.css
    wofi_css = f"""window {{
    margin: 0px;
    border: 1px solid {border};
    background-color: {bg};
    color: {fg};
}}

#input {{
    margin: 5px;
    border: none;
    color: {fg};
    background-color: {input_bg};
}}

#inner-box, #outer-box {{
    margin: 5px;
    border: none;
    background-color: {bg};
}}

#scroll {{
    margin: 0px;
    border: none;
}}

#text {{
    margin: 5px;
    border: none;
    color: {fg};
}}

#entry.activatable #text {{
    color: {fg};
}}

#entry > * {{
    color: {fg};
}}

#entry:selected {{
    background-color: {selected_bg};
    color: {selected_text};
}}

#entry:selected #text {{
    color: {hover_text};
    font-weight: bold;
}}
"""

    with open(WOFI_STYLE_FILE, "w") as f:
        f.write(wofi_css.strip() + "\n")

    print("Wofi theme updated using current theme colors.")


def hex_to_rgba(hex_color: str, alpha: float = 0.8) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha})"

def reload_hyprland():
    """Reload Hyprland via hyprctl."""
    try:
        subprocess.run(["hyprctl", "reload"], check=True)
        print("Hyprland reloaded.")
    except subprocess.CalledProcessError as e:
        print(f"Failed to reload Hyprland: {e}")

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
        return (
            include_target.startswith("~/.config/kitty/themes/")
            or include_target.startswith(themes_dir)
            or expanded_target.startswith(themes_dir)
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
    """Update Hyprpaper wallpaper."""
    if "wallpaper" not in theme:
        print("No wallpaper defined in theme, skipping Hyprpaper.")
        return

    wallpaper_path = os.path.expanduser(theme["wallpaper"])
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
        if line.startswith("preload="):
            updated_lines.append(f"preload={wallpaper_path}\n")
        elif line.startswith("wallpaper="):
            match = re.match(r"wallpaper=([^,]+),", line)
            if match:
                monitor = match.group(1)
                updated_lines.append(f"wallpaper={monitor},{wallpaper_path}\n")
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
        try:
            subprocess.run(
                [CODE_CLI, "--install-extension", extension, "--force"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"Ensured VS Code extension {extension} is installed.")
        except subprocess.CalledProcessError as exc:
            print(f"Failed to install VS Code extension {extension}: {exc}")

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
                return _profile_path_from_entry(rel_path, "1")

    # Fall back to profile sections that declare Default=1
    for section in parser.sections():
        if parser.has_option(section, "Default") and parser.get(section, "Default") == "1":
            rel_path = parser.get(section, "Path", fallback=None)
            if not rel_path:
                continue
            is_relative = parser.get(section, "IsRelative", fallback="1")
            return _profile_path_from_entry(rel_path, is_relative)

    # As a last resort, use the first profile entry with a Path
    for section in parser.sections():
        if parser.has_option(section, "Path"):
            rel_path = parser.get(section, "Path")
            is_relative = parser.get(section, "IsRelative", fallback="1")
            return _profile_path_from_entry(rel_path, is_relative)

    return None


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


def set_firefox_theme_activation(profile_path: Path, theme_id: str) -> None:
    """Update extensions.json so the requested theme is the only active profile theme."""
    extensions_json = profile_path / "extensions.json"
    if not extensions_json.exists():
        print("Firefox extensions.json not found; cannot activate theme.")
        return

    try:
        data = json.loads(extensions_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("Firefox extensions.json is not valid JSON; cannot activate theme.")
        return

    addons = data.get("addons", [])
    found = False
    changed = False

    for addon in addons:
        if addon.get("type") != "theme":
            continue
        if addon.get("location") not in {"app-profile", "profile", "app-system-profile"}:
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
        return

    if changed:
        extensions_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print("Firefox extensions.json updated with new active theme.")


def update_firefox(theme: Dict[str, Any]) -> None:
    firefox_cfg = theme.get("firefox")
    if not firefox_cfg:
        return

    profile_path = get_default_firefox_profile()
    if not profile_path:
        print("Firefox profile not found; skipping Firefox theme.")
        return

    prefs: Dict[str, Any] = parse_user_js(FIREFOX_BASE_PREFS_FILE)
    prefs.update(FIREFOX_ENFORCED_PREFS)
    prefs.update(firefox_cfg.get("prefs", {}))

    ensure_firefox_theme_payload(profile_path, firefox_cfg)
    theme_id = resolve_firefox_theme_id(profile_path, firefox_cfg)
    if theme_id:
        prefs["extensions.activeThemeID"] = theme_id
        set_firefox_theme_activation(profile_path, theme_id)
    else:
        if firefox_cfg.get("theme_name"):
            print(
                f'Firefox theme "{firefox_cfg["theme_name"]}" not found. '
                "Install it and rerun the theme switcher."
            )
        elif firefox_cfg.get("theme_id"):
            print(
                f'Firefox theme id "{firefox_cfg["theme_id"]}" is not available in this profile.'
            )

    write_firefox_userjs(profile_path, prefs)
    print(f"Firefox user.js updated at {profile_path}.")

def apply_theme(theme_name: str):
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

    # Apply Kitty theme if the "kitty" key is present in the JSON
    if "kitty" in theme:
        load_kitty_theme(theme["kitty"])
    
    update_waybar(theme)
    update_hyprpaper(theme)
    update_wofi(theme) 
    if "vscode" in theme:
        ensure_vscode_extension_payload(theme["vscode"].get("extension"))
    update_vscode(theme)
    update_firefox(theme)
    reload_hyprland()
    print("Theme applied successfully.")

# === Entry Point ===
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Switch between desktop themes.")
    parser.add_argument(
        "theme", help="Name of the theme to apply (e.g., dracula, nord, gruvbox)"
    )
    args = parser.parse_args()

    try:
        apply_theme(args.theme.lower())
    except Exception as e:
        print(f"Error: {e}")
