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

export const GITHUB_REPO = 'https://github.com/ak4dev/.hyprconf';

export const PROJECT_TAGLINE = 'Hyprland Configuration Suite';

export const PROJECT_DESCRIPTION =
  'A standalone CLI/TUI tool and curated dotfile collection for Arch Linux + Hyprland. ' +
  '68 themes, hardware auto-detection, keybind management, and one-command install.';

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
      '68 themes — community favourites and AI-originals. Switch instantly via CLI, TUI, or keybind. Themes cascade across Hyprland, Kitty, Waybar, VS Code, Firefox, and hyprlock.',
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
      { name: 'hyprconf theme', usage: 'hyprconf theme [name]', description: 'Apply a theme by name' },
      { name: 'hyprconf theme --current', usage: 'hyprconf theme --current', description: 'Show current theme' },
      { name: 'hyprconf theme --next', usage: 'hyprconf theme --next', description: 'Cycle to next theme' },
      { name: 'hyprconf theme --prev', usage: 'hyprconf theme --prev', description: 'Cycle to previous theme' },
      { name: 'hyprconf theme --random', usage: 'hyprconf theme --random', description: 'Apply a random theme' },
      { name: 'hyprconf theme --pick', usage: 'hyprconf theme --pick', description: 'Interactive theme picker (fzf)' },
      { name: 'hyprconf theme --filter', usage: 'hyprconf theme --filter <dark|light>', description: 'Filter by appearance' },
    ],
  },
  {
    title: 'Options',
    commands: [
      { name: 'hyprconf options', usage: 'hyprconf options', description: 'Show/edit Hyprland variables (gaps, borders, animations, etc.)' },
    ],
  },
  {
    title: 'Keybinds',
    commands: [
      { name: 'hyprconf keybinds', usage: 'hyprconf keybinds', description: 'List, add, edit, or remove keybindings' },
    ],
  },
  {
    title: 'Window Rules',
    commands: [
      { name: 'hyprconf rules', usage: 'hyprconf rules', description: 'Manage window rules (float, size, workspace, opacity, etc.)' },
    ],
  },
  {
    title: 'Monitor',
    commands: [
      { name: 'hyprconf monitor', usage: 'hyprconf monitor', description: 'Configure monitor layout, resolution, and scaling' },
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
    title: 'Sync & Deploy',
    commands: [
      { name: 'hyprconf sync', usage: 'hyprconf sync', description: 'Re-apply all configs, packages, services, and hardware detection' },
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
