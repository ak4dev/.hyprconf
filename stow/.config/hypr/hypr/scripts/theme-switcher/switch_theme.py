import os
import re
import json
import subprocess
from typing import Dict

# === Configuration ===
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(SCRIPT_DIR, "themes")
WAYBAR_CONFIG_FILE = os.path.expanduser("~/.config/waybar/waybar.css")
HYPRPAPER_CONFIG_FILE = os.path.expanduser("~/.config/hypr/hyprpaper.conf")


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
        return json.load(file)


import re

def update_waybar_colors(config_text: str, theme_colors: dict) -> str:
    # Replace all @define-color lines with theme colors
    def replacer(match):
        color_name = match.group(1)
        if color_name in theme_colors:
            return f"@define-color {color_name} {theme_colors[color_name]};"
        else:
            return match.group(0)

    # Replace @define-color lines
    updated_text = re.sub(
        r"@define-color\s+(\w+)\s+[^;]+;",
        replacer,
        config_text,
    )

    # Insert or replace @define-color background-alpha
    rgba_bg = hex_to_rgba(theme_colors["background"], 0.8)
    if "@define-color background-alpha" in updated_text:
        updated_text = re.sub(
            r"@define-color background-alpha\s+[^;]+;",
            f"@define-color background-alpha {rgba_bg};",
            updated_text,
        )
    else:
        # Insert after background color definitions (assumes @define-color background is there)
        updated_text = re.sub(
            r"(@define-color background\s+[^;]+;)",
            r"\1\n@define-color background-alpha " + rgba_bg + ";",
            updated_text,
            count=1,
        )

    # Replace all hardcoded rgba(40, 42, 54, ...) in backgrounds with @background-alpha
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
            # Extract monitor name and rebuild line
            match = re.match(r"wallpaper=([^,]+),", line)
            if match:
                monitor = match.group(1)
                updated_lines.append(f"wallpaper={monitor},{wallpaper_path}\n")
        else:
            updated_lines.append(line)

    with open(HYPRPAPER_CONFIG_FILE, "w") as f:
        f.writelines(updated_lines)

    print("Hyprpaper wallpaper updated.")


def apply_theme(theme_name: str):
    """Apply the selected theme to all relevant config files."""
    print(f"Switching to theme: {theme_name}")
    theme = load_theme(theme_name)
    update_waybar(theme)
    update_hyprpaper(theme)
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
