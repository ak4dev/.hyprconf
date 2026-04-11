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
      'Automatic detection and configuration for touchscreens, convertible laptops, accelerometers, Keychron keyboards, and Nvidia GPUs.',
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
      'Pre-configured Firefox with arkenfox user.js, uBlock Origin, and theme-matched extensions. Privacy-first browsing out of the box.',
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
      { name: 'hyprconf theme set', usage: 'hyprconf theme set <name>', description: 'Apply a theme by name' },
      { name: 'hyprconf theme current', usage: 'hyprconf theme current', description: 'Show current theme' },
      { name: 'hyprconf theme next', usage: 'hyprconf theme next', description: 'Cycle to next theme' },
      { name: 'hyprconf theme prev', usage: 'hyprconf theme prev', description: 'Cycle to previous theme' },
      { name: 'hyprconf theme random', usage: 'hyprconf theme random', description: 'Apply a random theme' },
      { name: 'hyprconf theme pick', usage: 'hyprconf theme pick', description: 'Interactive theme picker (fzf)' },
      { name: 'hyprconf theme filter', usage: 'hyprconf theme filter <dark|light>', description: 'Filter by appearance' },
      { name: 'hyprconf theme list', usage: 'hyprconf theme list', description: 'List all available themes' },
      { name: 'hyprconf theme generate', usage: 'hyprconf theme generate <image>', description: 'Generate a theme from an image' },
    ],
  },
  {
    title: 'Options',
    commands: [
      { name: 'hyprconf get', usage: 'hyprconf get <section> [key]', description: 'Show current value of Hyprland variables' },
      { name: 'hyprconf set', usage: 'hyprconf set <section> <key> <value>', description: 'Set a Hyprland variable (applied live + persisted)' },
      { name: 'hyprconf configure', usage: 'hyprconf configure', description: 'Interactive IOS-style REPL for editing options' },
      { name: 'hyprconf schema', usage: 'hyprconf schema [section]', description: 'Dump the schema for Hyprland config sections' },
      { name: 'hyprconf show', usage: 'hyprconf show <section>', description: 'Display all values for a config section' },
    ],
  },
  {
    title: 'Keybinds',
    commands: [
      { name: 'hyprconf keybind list', usage: 'hyprconf keybind list', description: 'List all keybindings' },
      { name: 'hyprconf keybind set', usage: 'hyprconf keybind set <mods> <key> <action>', description: 'Add or update a keybinding' },
      { name: 'hyprconf keybind config', usage: 'hyprconf keybind config', description: 'Interactive keybind editor' },
    ],
  },
  {
    title: 'Window Rules',
    commands: [
      { name: 'hyprconf rule list', usage: 'hyprconf rule list', description: 'List all window rules' },
      { name: 'hyprconf rule new', usage: 'hyprconf rule new', description: 'Create a new window rule interactively' },
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
      { name: 'hyprconf hardware', usage: 'hyprconf hardware', description: 'Show detected hardware features and capabilities' },
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
      { keys: ['Super', 'Return'], action: 'Open terminal (Kitty)' },
      { keys: ['Super', 'B'], action: 'Open browser (Firefox)' },
      { keys: ['Super', 'E'], action: 'Open file manager (Thunar)' },
      { keys: ['Super', 'Space'], action: 'Application launcher (Rofi)' },
      { keys: ['Super', 'V'], action: 'Clipboard manager (cliphist)' },
      { keys: ['Super', 'Period'], action: 'Emoji picker' },
      { keys: ['Super', 'Escape'], action: 'Power menu (wlogout)' },
    ],
  },
  {
    title: 'Window Management',
    id: 'windows',
    bindings: [
      { keys: ['Super', 'Q'], action: 'Close active window' },
      { keys: ['Super', 'F'], action: 'Toggle fullscreen' },
      { keys: ['Super', 'T'], action: 'Toggle floating' },
      { keys: ['Super', 'P'], action: 'Toggle pseudo-tile' },
      { keys: ['Super', 'J'], action: 'Toggle split direction' },
      { keys: ['Super', '←/→/↑/↓'], action: 'Move focus' },
      { keys: ['Super', 'Shift', '←/→/↑/↓'], action: 'Move window' },
      { keys: ['Super', 'Ctrl', '←/→/↑/↓'], action: 'Resize window' },
    ],
  },
  {
    title: 'Workspaces',
    id: 'workspaces',
    bindings: [
      { keys: ['Super', '1–2'], action: 'Switch to workspace 1–2' },
      { keys: ['F1', '/', 'F2'], action: 'Switch to workspace 3/4' },
      { keys: ['Super', '5–0'], action: 'Switch to workspace 5–10' },
      { keys: ['Super', 'Shift', '1–0'], action: 'Move window to workspace 1–10' },
      { keys: ['Super', 'Scroll'], action: 'Cycle workspaces' },
      { keys: ['Super', 'S'], action: 'Toggle special workspace' },
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
    ],
  },
  {
    title: 'Screenshots',
    id: 'screenshots',
    bindings: [
      { keys: ['Print'], action: 'Screenshot region (clipboard)' },
      { keys: ['Super', 'Print'], action: 'Screenshot active window' },
      { keys: ['Super', 'Shift', 'Print'], action: 'Screenshot full screen' },
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
