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
KITTY_CONFIG_FILE = os.path.expanduser("~/.config/kitty/kitty.conf")
WOFI_STYLE_FILE = os.path.expanduser("~/.config/wofi/style.css")

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

    # Search for any 'include' lines and remove the old ones (if any) for the same theme
    lines = kitty_conf_content.splitlines()
    lines = [line for line in lines if not line.strip().startswith("include") or normalized_path not in line]

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

def apply_theme(theme_name: str):
    """Apply the selected theme to all relevant config files."""
    print(f"Switching to theme: {theme_name}")
    theme = load_theme(theme_name)

    # Apply Kitty theme if the "kitty" key is present in the JSON
    if "kitty" in theme:
        load_kitty_theme(theme["kitty"])
    
    update_waybar(theme)
    update_hyprpaper(theme)
    update_wofi(theme) 
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
