import type { LucideIcon } from 'lucide-react';
import {
  Palette,
  Keyboard,
  Terminal,
  Monitor,
  Shield,
  Lock,
  RefreshCw,
  Cpu,
  Download,
} from 'lucide-react';
import { themeCount } from './generated/themes';

export const GITHUB_REPO = 'https://github.com/ak4dev/.hyprconf';

export const PROJECT_TAGLINE = 'Hyprland Configuration Suite';

export const PROJECT_DESCRIPTION =
  'A standalone CLI/TUI tool and curated dotfile collection for Arch Linux + Hyprland. ' +
  `${themeCount} themes, hardware auto-detection, keybind management, and one-command install.`;

export const INSTALL_COMMAND = 'bash <(curl -fsSL hyprconf.sh)';

export const VERSION = '2.1.1';

export interface Feature {
  title: string;
  description: string;
  icon: LucideIcon;
  route?: string;
}

export const FEATURES: Feature[] = [
  {
    title: 'Theme Engine',
    description:
      `${themeCount} themes — community favourites and AI-originals. Switch instantly via CLI, TUI, or keybind. Themes cascade across Hyprland, Kitty, Waybar, VS Code, Firefox, and hyprlock.`,
    icon: Palette,
    route: '/themes',
  },
  {
    title: 'Keybindings',
    description:
      'Pre-configured keybindings for window management, workspace navigation, application launching, media controls, and brightness. Fully customisable via hyprconf keybinds.',
    icon: Keyboard,
    route: '/keybindings',
  },
  {
    title: 'CLI & TUI',
    description:
      'Full-featured command-line interface with a rich terminal UI. Manage themes, keybinds, window rules, monitor layouts, lock screen, idle behaviour, and wallpapers.',
    icon: Terminal,
    route: '/cli',
  },
  {
    title: 'Installation',
    description:
      'Three install modes: full Arch setup from ISO, dotfiles-only onto an existing Arch+Hyprland system, or CLI-only for just the hyprconf tool.',
    icon: Download,
    route: '/install',
  },
  {
    title: 'Hardware Detection',
    description:
      'Automatic detection and configuration for touchscreens, convertible laptops, accelerometers, Keychron/Lemokey keyboards, and Nvidia GPUs.',
    icon: Cpu,
  },
  {
    title: 'Monitor Profiles',
    description:
      'Hot-switchable monitor presets for multi-display setups. Configure via TUI or keybind.',
    icon: Monitor,
  },
  {
    title: 'Privacy Firefox',
    description:
      'Pre-configured Firefox with enterprise policies, uBlock Origin, and theme-matched extensions. Privacy-first browsing out of the box.',
    icon: Shield,
  },
  {
    title: 'Lock & Idle',
    description:
      'hyprlock and hypridle configured with theme-aware lock screens, DPMS management, and automatic suspend timers.',
    icon: Lock,
  },
  {
    title: 'Sync & Update',
    description:
      'hyprconf sync applies all configuration changes idempotently. Hardware config, services, and packages are patched in-place — no reinstall needed.',
    icon: RefreshCw,
  },
];

export interface CliCommand {
  name: string;
  usage: string;
  description: string;
}

export interface CliGroup {
  title: string;
  commands: CliCommand[];
}

export const CLI_GROUPS: CliGroup[] = [
  {
    title: 'Theme',
    commands: [
      { name: 'hyprconf theme <name>', usage: 'hyprconf theme <name>', description: 'Apply a theme by name' },
      { name: 'hyprconf theme current', usage: 'hyprconf theme current', description: 'Show current theme' },
      { name: 'hyprconf theme next', usage: 'hyprconf theme next', description: 'Cycle to next theme' },
      { name: 'hyprconf theme prev', usage: 'hyprconf theme prev', description: 'Cycle to previous theme' },
      { name: 'hyprconf theme random', usage: 'hyprconf theme random', description: 'Apply a random theme' },
      { name: 'hyprconf theme pick', usage: 'hyprconf theme pick', description: 'Interactive theme picker (hyprlauncher)' },
      { name: 'hyprconf theme filter', usage: 'hyprconf theme filter <dark|light>', description: 'Filter by appearance' },
      { name: 'hyprconf theme list', usage: 'hyprconf theme list', description: 'List all available themes' },
      { name: 'hyprconf theme generate', usage: 'hyprconf theme generate <image>', description: 'Generate a theme from an image' },
    ],
  },
  {
    title: 'Options',
    commands: [
      { name: 'hyprconf get', usage: 'hyprconf get [section] [key]', description: 'Show current value of Hyprland variables (no args lists sections)' },
      { name: 'hyprconf set', usage: 'hyprconf set <section> <key> <value>', description: 'Set a Hyprland variable (applied live + persisted)' },
      { name: 'hyprconf configure', usage: 'hyprconf configure', description: 'Interactive IOS-style REPL for editing options' },
      { name: 'hyprconf schema dump', usage: 'hyprconf schema dump', description: 'Dump the full schema as JSON' },
      { name: 'hyprconf schema list-sections', usage: 'hyprconf schema list-sections', description: 'List all config sections and key counts' },
      { name: 'hyprconf schema keys', usage: 'hyprconf schema keys <section>', description: 'List all keys in a config section with types and defaults' },
      { name: 'hyprconf schema validate', usage: 'hyprconf schema validate', description: 'Validate persisted config against the schema' },
      { name: 'hyprconf show keybind', usage: 'hyprconf show keybind', description: 'Display all keybindings in a formatted table' },
    ],
  },
  {
    title: 'Keybinds',
    commands: [
      { name: 'hyprconf keybind list', usage: 'hyprconf keybind list', description: 'List all keybindings' },
      { name: 'hyprconf keybind add', usage: 'hyprconf keybind add <kind> <mods> <key> <dispatcher> [args]', description: 'Add a keybinding' },
      { name: 'hyprconf keybind delete', usage: 'hyprconf keybind delete <index>', description: 'Delete a keybinding by index' },
      { name: 'hyprconf keybind update', usage: 'hyprconf keybind update <index> <kind> <mods> <key> <dispatcher> [args]', description: 'Update a keybinding by index' },
    ],
  },
  {
    title: 'Window & Workspace Rules',
    commands: [
      { name: 'hyprconf rule window list', usage: 'hyprconf rule window list', description: 'List all window rules' },
      { name: 'hyprconf rule window add', usage: 'hyprconf rule window add <rule> <filter>', description: 'Add a window rule' },
      { name: 'hyprconf rule window delete', usage: 'hyprconf rule window delete <index>', description: 'Delete a window rule by index' },
      { name: 'hyprconf rule workspace list', usage: 'hyprconf rule workspace list', description: 'List all workspace rules' },
      { name: 'hyprconf rule workspace add', usage: 'hyprconf rule workspace add <ws_id> <options>', description: 'Add a workspace rule' },
      { name: 'hyprconf rule workspace delete', usage: 'hyprconf rule workspace delete <index>', description: 'Delete a workspace rule by index' },
    ],
  },
  {
    title: 'Monitor',
    commands: [
      { name: 'hyprconf monitor', usage: 'hyprconf monitor', description: 'Configure monitor layout, resolution, and scaling' },
      { name: 'hyprconf display', usage: 'hyprconf display toggle', description: 'Toggle built-in display (laptops/handhelds)' },
    ],
  },
  {
    title: 'Lock & Idle',
    commands: [
      { name: 'hyprconf lock', usage: 'hyprconf lock', description: 'Configure hyprlock settings' },
      { name: 'hyprconf idle', usage: 'hyprconf idle', description: 'Configure hypridle timeouts and actions' },
    ],
  },
  {
    title: 'Wallpaper',
    commands: [
      { name: 'hyprconf paper', usage: 'hyprconf paper', description: 'Manage wallpapers via hyprpaper' },
    ],
  },
  {
    title: 'TUI',
    commands: [
      { name: 'hyprconf tui', usage: 'hyprconf tui', description: 'Launch the terminal UI for graphical management' },
    ],
  },
  {
    title: 'System',
    commands: [
      { name: 'hyprconf sync', usage: 'hyprconf sync', description: 'Re-apply all configs, packages, services, and hardware detection' },
      { name: 'hyprconf repair', usage: 'hyprconf repair', description: 'Run self-repair checks and fix common issues' },
      { name: 'hyprconf hardware status', usage: 'hyprconf hardware status', description: 'Show detected hardware features and daemon status' },
      { name: 'hyprconf hardware osk', usage: 'hyprconf hardware osk', description: 'Toggle on-screen keyboard (wvkbd)' },
      { name: 'hyprconf hardware rotate', usage: 'hyprconf hardware rotate', description: 'Toggle auto-rotation (accelerometer)' },
      { name: 'hyprconf doctor', usage: 'hyprconf doctor', description: 'Diagnose and report system health' },
      { name: 'hyprconf autodetect', usage: 'hyprconf autodetect', description: 'Import existing Hyprland config into .hyprconf format' },
    ],
  },
  {
    title: 'Deploy',
    commands: [
      { name: 'hyprconf deploy', usage: 'hyprconf deploy', description: 'Deploy/refresh the default domain (S3, CloudFront, DNS, web frontend)' },
      { name: 'hyprconf deploy web', usage: 'hyprconf deploy web', description: 'Quick web frontend deploy (build + S3 sync + cache invalidation)' },
      { name: 'hyprconf deploy list', usage: 'hyprconf deploy list', description: 'List all configured deployments and their status' },
      { name: 'hyprconf deploy new', usage: 'hyprconf deploy new', description: 'Add and deploy an additional domain' },
      { name: 'hyprconf teardown', usage: 'hyprconf teardown', description: 'Destroy all AWS resources for a deployment' },
    ],
  },
  {
    title: 'Utilities',
    commands: [
      { name: 'hyprconf screenshot', usage: 'hyprconf screenshot', description: 'Capture screenshots (region, window, or full screen)' },
      { name: 'hyprconf record', usage: 'hyprconf record', description: 'Screen recording controls' },
      { name: 'hyprconf clipboard', usage: 'hyprconf clipboard', description: 'Clipboard history management' },
      { name: 'hyprconf colorpicker', usage: 'hyprconf colorpicker', description: 'Pick a colour from anywhere on screen' },
      { name: 'hyprconf nightlight', usage: 'hyprconf nightlight', description: 'Toggle blue-light filter (night mode)' },
      { name: 'hyprconf gamemode', usage: 'hyprconf gamemode', description: 'Toggle gaming mode (disable animations, compositing tweaks)' },
      { name: 'hyprconf power', usage: 'hyprconf power', description: 'Power management (shutdown, reboot, suspend, lock)' },
      { name: 'hyprconf power-profile', usage: 'hyprconf power-profile', description: 'Switch power profiles (performance, balanced, power-saver)' },
    ],
  },
];

export interface KeybindCategory {
  title: string;
  id: string;
  bindings: { keys: string[]; action: string }[];
}

export const KEYBINDINGS: KeybindCategory[] = [
  {
    title: 'Applications',
    id: 'apps',
    bindings: [
      { keys: ['Super', 'T'], action: 'Open terminal (Kitty)' },
      { keys: ['Super', 'F'], action: 'Open browser (Firefox)' },
      { keys: ['Super', 'E'], action: 'Open file manager (Dolphin)' },
      { keys: ['Super', 'D'], action: 'Application launcher (hyprlauncher)' },
      { keys: ['Super', 'C'], action: 'Open VS Code' },
      { keys: ['Super', 'Shift', 'V'], action: 'Clipboard history (cliphist + hyprlauncher)' },
    ],
  },
  {
    title: 'Window Management',
    id: 'windows',
    bindings: [
      { keys: ['Super', 'Q'], action: 'Close active window' },
      { keys: ['Super', 'Shift', 'Q'], action: 'Exit Hyprland session' },
      { keys: ['Super', 'V'], action: 'Toggle floating' },
      { keys: ['Super', 'Shift', 'Space'], action: 'Toggle floating (alternate)' },
      { keys: ['Super', 'Shift', 'F'], action: 'Toggle fullscreen' },
      { keys: ['Super', 'P'], action: 'Toggle pseudo-tile' },
      { keys: ['Super', 'J'], action: 'Toggle split direction' },
      { keys: ['Super', '←/→/↑/↓'], action: 'Move focus' },
      { keys: ['Super', 'Shift', '←/→/↑/↓'], action: 'Resize window' },
      { keys: ['Super', 'Shift', 'A/D/W/S'], action: 'Swap window position (L/R/U/D)' },
      { keys: ['Super', 'Shift', '+/−'], action: 'Adjust window gaps' },
      { keys: ['Super', 'LMB drag'], action: 'Move window' },
      { keys: ['Super', 'RMB drag'], action: 'Resize window' },
    ],
  },
  {
    title: 'Workspaces',
    id: 'workspaces',
    bindings: [
      { keys: ['Super', '1–2'], action: 'Switch to workspace 1–2' },
      { keys: ['Super', 'F1/F2'], action: 'Switch to workspace 3/4' },
      { keys: ['Super', '5–0'], action: 'Switch to workspace 5–10' },
      { keys: ['Super', 'Shift', '1–0/F1/F2'], action: 'Move window to workspace' },
      { keys: ['Super', 'Scroll'], action: 'Cycle workspaces' },
      { keys: ['Super', 'M'], action: 'Toggle special workspace (scratchpad)' },
      { keys: ['Super', 'Shift', 'M'], action: 'Move window to special workspace' },
    ],
  },
  {
    title: 'Media & Volume',
    id: 'media',
    bindings: [
      { keys: ['XF86AudioPlay'], action: 'Play/pause media' },
      { keys: ['XF86AudioNext'], action: 'Next track' },
      { keys: ['XF86AudioPrev'], action: 'Previous track' },
      { keys: ['XF86AudioRaiseVolume'], action: 'Volume up' },
      { keys: ['XF86AudioLowerVolume'], action: 'Volume down' },
      { keys: ['XF86AudioMute'], action: 'Toggle mute' },
      { keys: ['XF86AudioMicMute'], action: 'Toggle mic mute' },
    ],
  },
  {
    title: 'Brightness',
    id: 'brightness',
    bindings: [
      { keys: ['XF86MonBrightnessUp'], action: 'Brightness up' },
      { keys: ['XF86MonBrightnessDown'], action: 'Brightness down' },
    ],
  },
  {
    title: 'Screenshots & Screen Lock',
    id: 'screenshots',
    bindings: [
      { keys: ['Super', 'Shift', '4'], action: 'Screenshot region (hyprshot)' },
      { keys: ['Super', 'L'], action: 'Lock screen (hyprlock)' },
      { keys: ['Super', 'Shift', 'Escape'], action: 'Lock screen (alternate)' },
    ],
  },
  {
    title: 'Monitor',
    id: 'monitor',
    bindings: [
      { keys: ['Super', 'Shift', 'B'], action: 'Switch to bedroom monitor preset' },
      { keys: ['Super', 'Shift', 'K'], action: 'Switch to kitchen monitor preset' },
      { keys: ['Super', 'Shift', 'Backspace'], action: 'Toggle native laptop display' },
    ],
  },
];

export interface InstallMode {
  title: string;
  description: string;
  steps: string[];
}

export const INSTALL_MODES: InstallMode[] = [
  {
    title: 'Full Arch Install',
    description:
      'Complete Arch Linux installation from a live ISO — partitioning, base system, Hyprland desktop, and all hyprconf dotfiles.',
    steps: [
      'Boot from Arch ISO',
      'Connect to internet (iwctl for Wi-Fi)',
      'Run: bash <(curl -fsSL hyprconf.sh)',
      'Select option [1] Full Arch Install',
      'Follow the interactive prompts (disk, timezone, hostname, user)',
      'Reboot into your new system',
    ],
  },
  {
    title: 'Dotfiles Only',
    description:
      'Apply hyprconf dotfiles to an existing Arch + Hyprland system. Installs packages, stows configs, enables services.',
    steps: [
      'Run: bash <(curl -fsSL hyprconf.sh)',
      'Select option [2] Dotfiles Only',
      'Packages are installed and configs are symlinked via GNU Stow',
      'Services (iwd, bluetooth, pipewire) are enabled',
      'Log out and back in to apply',
    ],
  },
  {
    title: 'CLI Only',
    description:
      'Install just the hyprconf CLI/TUI tool without changing your existing dotfiles.',
    steps: [
      'Run: bash <(curl -fsSL hyprconf.sh)',
      'Select option [3] CLI Only',
      'The hyprconf binary is installed to ~/.local/bin/',
      'Run hyprconf --help to get started',
    ],
  },
];
