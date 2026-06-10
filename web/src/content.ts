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
  'A complete configuration suite for Arch Linux and Hyprland. ' +
  `Manage ${themeCount} themes, keybinds, window rules, monitor layouts, and system settings ` +
  'through a powerful CLI, rich terminal UI, or one-command install.';

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
      `Choose from ${themeCount} themes spanning community favorites and AI-generated originals. Apply any theme with a single command — colors cascade instantly across Hyprland, Kitty, Waybar, VS Code, Firefox, and hyprlock.`,
    icon: Palette,
    route: '/themes',
  },
  {
    title: 'Keybindings',
    description:
      'Production-ready keybindings for window management, workspace navigation, app launching, media, and display controls. Fully editable through the CLI or TUI — no manual config editing required.',
    icon: Keyboard,
    route: '/keybindings',
  },
  {
    title: 'CLI & TUI',
    description:
      'A full-featured CLI and interactive terminal UI for managing every aspect of your Hyprland environment. Configure themes, keybinds, window rules, monitors, lock screen, idle behavior, and wallpapers.',
    icon: Terminal,
    route: '/cli',
  },
  {
    title: 'Installation',
    description:
      'Three install modes: complete Arch Linux from a live ISO, dotfiles-only for an existing Hyprland system, or standalone CLI. One command starts any path.',
    icon: Download,
    route: '/install',
  },
  {
    title: 'Hardware Detection',
    description:
      'Automatic detection and configuration for touchscreens, convertible laptops, accelerometers, mechanical keyboards, Nvidia GPUs, and GPU passthrough (VFIO) with mode-based sysfs binding for VM passthrough. Applied at install and kept current through sync.',
    icon: Cpu,
  },
  {
    title: 'Monitor Profiles',
    description:
      'Define and switch between multi-display presets. Configure resolution, scaling, position, and transforms per profile — switch instantly via keybind or TUI.',
    icon: Monitor,
  },
  {
    title: 'Privacy Firefox',
    description:
      'Firefox configured with enterprise-grade privacy policies, uBlock Origin, and theme-matched styling. Private by default, no manual setup.',
    icon: Shield,
  },
  {
    title: 'Lock & Idle',
    description:
      'Theme-aware lock screens via hyprlock with configurable idle timeouts, DPMS management, and automatic suspend — all managed through the CLI.',
    icon: Lock,
  },
  {
    title: 'YubiKey Login',
    description:
      'Optional FIDO2 + PIN hardware-key authentication for sudo, TTY login, display manager, SSH, and LUKS unlock at boot. One interactive script enrols the key, backs up every change, and rolls back on failure.',
    icon: Shield,
  },
  {
    title: 'Sync & Update',
    description:
      'Run hyprconf sync to apply all configuration changes in place. Hardware detection, services, and packages are patched idempotently — no reinstall required.',
    icon: RefreshCw,
  },
];

export interface CliCommand {
  name: string;
  usage: string;
  description: string;
  example?: string;
}

export interface CliGroup {
  title: string;
  commands: CliCommand[];
}

export const CLI_GROUPS: CliGroup[] = [
  {
    title: 'Theme',
    commands: [
      {
        name: 'hyprconf theme <name>',
        usage: 'hyprconf theme <name>',
        description: 'Apply a theme by name. Colors cascade across Hyprland borders, Kitty, Waybar, VS Code, Firefox, hyprlock, and wallpaper.',
        example: 'Switching to theme: dracula\n  ✔ Hyprland borders   ✔ Kitty terminal\n  ✔ Waybar             ✔ hyprlock\n  ✔ Wallpaper\nTheme applied.',
      },
      {
        name: 'hyprconf theme current',
        usage: 'hyprconf theme current',
        description: 'Print the name of the currently active theme.',
        example: 'dracula',
      },
      { name: 'hyprconf theme next', usage: 'hyprconf theme next', description: 'Cycle forward to the next theme in alphabetical order.' },
      { name: 'hyprconf theme prev', usage: 'hyprconf theme prev', description: 'Cycle backward to the previous theme.' },
      { name: 'hyprconf theme random', usage: 'hyprconf theme random', description: 'Apply a randomly selected theme.' },
      { name: 'hyprconf theme pick', usage: 'hyprconf theme pick', description: 'Open an interactive picker to browse and preview themes.' },
      { name: 'hyprconf theme filter', usage: 'hyprconf theme filter <dark|light>', description: 'Filter themes by appearance and open the picker.' },
      {
        name: 'hyprconf theme list',
        usage: 'hyprconf theme list',
        description: 'List all available themes with their appearance type.',
        example: `★ dracula            dark\n  gruvbox-dark       dark\n  nord               dark\n  tokyo-night        dark\n\n${themeCount} themes available`,
      },
      { name: 'hyprconf theme generate', usage: 'hyprconf theme generate <image>', description: 'Generate a new theme from an image file using color extraction.' },
    ],
  },
  {
    title: 'Options',
    commands: [
      {
        name: 'hyprconf get',
        usage: 'hyprconf get [section] [key]',
        description: 'Read Hyprland config variables. With no arguments, lists sections. With a section, shows all keys. With a section and key, shows the current value with type and default.',
        example: '$ hyprconf get general border_size\ngeneral:border_size  3\n  type: int  default: 1',
      },
      {
        name: 'hyprconf set',
        usage: 'hyprconf set <section> <key> <value>',
        description: 'Set a Hyprland variable. The change is applied immediately via hyprctl and persisted to disk.',
        example: '$ hyprconf set general border_size 3\nApplied: general:border_size = 3',
      },
      { name: 'hyprconf configure', usage: 'hyprconf configure', description: 'Launch an interactive REPL for browsing and editing config options.' },
      { name: 'hyprconf schema dump', usage: 'hyprconf schema dump', description: 'Dump the full configuration schema as JSON.' },
      { name: 'hyprconf schema list-sections', usage: 'hyprconf schema list-sections', description: 'List all config sections and their key counts.' },
      { name: 'hyprconf schema keys', usage: 'hyprconf schema keys <section>', description: 'List all keys in a config section with their types and defaults.' },
      { name: 'hyprconf schema validate', usage: 'hyprconf schema validate', description: 'Validate the persisted config against the schema and report errors.' },
      { name: 'hyprconf show keybind', usage: 'hyprconf show keybind', description: 'Display all keybindings in a formatted table.' },
    ],
  },
  {
    title: 'Keybinds',
    commands: [
      {
        name: 'hyprconf keybind list',
        usage: 'hyprconf keybind list',
        description: 'List all keybindings in a formatted table.',
        example: '#  KIND  MODS          KEY     DISPATCHER  ARGS\n1  bind  SUPER         Return  exec        kitty\n2  bind  SUPER         Q       killactive\n3  bind  SUPER SHIFT   F       fullscreen',
      },
      { name: 'hyprconf keybind add', usage: 'hyprconf keybind add <kind> <mods> <key> <dispatcher> [args]', description: 'Add a new keybinding.' },
      { name: 'hyprconf keybind delete', usage: 'hyprconf keybind delete <index>', description: 'Delete a keybinding by its table index.' },
      { name: 'hyprconf keybind update', usage: 'hyprconf keybind update <index> <kind> <mods> <key> <dispatcher> [args]', description: 'Update an existing keybinding by index.' },
    ],
  },
  {
    title: 'Window & Workspace Rules',
    commands: [
      {
        name: 'hyprconf rule window list',
        usage: 'hyprconf rule window list',
        description: 'List all window rules.',
        example: '#  RULE                     MATCH\n1  float                    class:pavucontrol\n2  size 800 600, float      class:blueman-manager',
      },
      { name: 'hyprconf rule window add', usage: 'hyprconf rule window add <rule> <filter>', description: 'Add a new window rule.' },
      { name: 'hyprconf rule window delete', usage: 'hyprconf rule window delete <index>', description: 'Delete a window rule by index.' },
      { name: 'hyprconf rule workspace list', usage: 'hyprconf rule workspace list', description: 'List all workspace rules.' },
      { name: 'hyprconf rule workspace add', usage: 'hyprconf rule workspace add <ws_id> <options>', description: 'Add a new workspace rule.' },
      { name: 'hyprconf rule workspace delete', usage: 'hyprconf rule workspace delete <index>', description: 'Delete a workspace rule by index.' },
      { name: 'hyprconf rule workspace update', usage: 'hyprconf rule workspace update <index> <ws_id> <options>', description: 'Update an existing workspace rule by index.' },
    ],
  },
  {
    title: 'Monitor',
    commands: [
      { name: 'hyprconf monitor', usage: 'hyprconf monitor', description: 'Open the interactive monitor configurator for layout, resolution, and scaling.' },
      { name: 'hyprconf display', usage: 'hyprconf display toggle', description: 'Toggle the built-in display on or off (laptops and handhelds).' },
    ],
  },
  {
    title: 'Lock & Idle',
    commands: [
      { name: 'hyprconf lock', usage: 'hyprconf lock', description: 'Configure hyprlock lock screen settings — backgrounds, labels, and input fields.' },
      { name: 'hyprconf idle', usage: 'hyprconf idle', description: 'Configure hypridle timeout thresholds and actions (lock, DPMS, suspend).' },
    ],
  },
  {
    title: 'Wallpaper',
    commands: [
      { name: 'hyprconf paper', usage: 'hyprconf paper', description: 'Manage wallpapers, preloads, and per-monitor assignments via hyprpaper.' },
    ],
  },
  {
    title: 'TUI',
    commands: [
      { name: 'hyprconf tui', usage: 'hyprconf tui', description: 'Launch the interactive terminal UI. Navigate themes, keybinds, options, rules, monitors, and system settings in a full-screen interface.' },
    ],
  },
  {
    title: 'System',
    commands: [
      {
        name: 'hyprconf sync',
        usage: 'hyprconf sync',
        description: 'Apply all configuration changes idempotently — packages, services, hardware detection, and dotfile symlinks.',
        example: 'Syncing configuration...\n  ✔ Packages up to date\n  ✔ Configs stowed\n  ✔ Services enabled\n  ✔ Hardware config written\nSync complete.',
      },
      { name: 'hyprconf repair', usage: 'hyprconf repair', description: 'Run self-repair checks and fix common issues automatically.' },
      {
        name: 'hyprconf hardware status',
        usage: 'hyprconf hardware status',
        description: 'Show detected hardware features and running daemon status.',
        example: 'Touchscreen     detected\nAccelerometer   not detected\nNvidia GPU      not detected\n\nwvkbd (OSK)     stopped\nautorotate      stopped',
      },
      { name: 'hyprconf hardware osk', usage: 'hyprconf hardware osk', description: 'Toggle the on-screen keyboard (wvkbd).' },
      { name: 'hyprconf hardware rotate', usage: 'hyprconf hardware rotate', description: 'Toggle auto-rotation for accelerometer-equipped devices.' },
      {
        name: 'hyprconf hardware gpu',
        usage: 'hyprconf hardware gpu [detect|setup|audit|mode|report|diagnose]',
        description: 'GPU passthrough management — mode-based sysfs binding (mode vm/host/none), hardware report.',
        example: 'GPU Passthrough Status\n══════════════════════\n\nIOMMU: enabled ✔\nConfigured: NVIDIA GeForce RTX 3070 [04:00.0]\n\nGPUs:\n  04:00.0  NVIDIA GeForce RTX 3070  🖥  host (nvidia)\n  0a:00.0  NVIDIA GeForce RTX 5090  🖥  host (nvidia)',
      },
      {
        name: 'hyprconf doctor',
        usage: 'hyprconf doctor',
        description: 'Run diagnostics on packages, services, config files, themes, and hardware.',
        example: 'Packages   ✔ All installed\nServices   ✔ NetworkManager  ✔ bluetooth  ✔ pipewire\nConfig     ✔ hyprland.conf   ✔ keybinds.conf\nTheme      ✔ dracula\nHardware   ✔ 60-hardware.conf\n\nAll checks passed.',
      },
      { name: 'hyprconf autodetect', usage: 'hyprconf autodetect', description: 'Import an existing Hyprland config into .hyprconf managed format.' },
    ],
  },
  {
    title: 'Deploy',
    commands: [
      { name: 'hyprconf deploy', usage: 'hyprconf deploy', description: 'Deploy the full stack via CDK — S3, CloudFront, ACM, Route53, and web frontend.' },
      { name: 'hyprconf deploy web', usage: 'hyprconf deploy web', description: 'Build and deploy the web frontend with CloudFront cache invalidation.' },
      { name: 'hyprconf deploy list', usage: 'hyprconf deploy list', description: 'List all configured deployments and their status.' },
      { name: 'hyprconf deploy new', usage: 'hyprconf deploy new', description: 'Add and deploy an additional domain.' },
      { name: 'hyprconf teardown', usage: 'hyprconf teardown', description: 'Destroy all AWS resources for a deployment via CDK.' },
    ],
  },
  {
    title: 'Utilities',
    commands: [
      { name: 'hyprconf screenshot', usage: 'hyprconf screenshot', description: 'Capture a screenshot — select a region, window, or full screen.' },
      { name: 'hyprconf record', usage: 'hyprconf record', description: 'Start or stop screen recording.' },
      { name: 'hyprconf clipboard', usage: 'hyprconf clipboard', description: 'Browse and paste from clipboard history.' },
      { name: 'hyprconf colorpicker', usage: 'hyprconf colorpicker', description: 'Pick a color from anywhere on screen and copy it to clipboard.' },
      { name: 'hyprconf nightlight', usage: 'hyprconf nightlight', description: 'Toggle the blue-light filter (night mode).' },
      { name: 'hyprconf gamemode', usage: 'hyprconf gamemode', description: 'Toggle gaming mode — disables animations and applies compositing tweaks.' },
      { name: 'hyprconf power', usage: 'hyprconf power', description: 'Open the power menu — shutdown, reboot, suspend, hibernate, or lock.' },
      { name: 'hyprconf power-profile', usage: 'hyprconf power-profile', description: 'Switch between power profiles (performance, balanced, power-saver).' },
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
      'A complete Arch Linux installation from a live ISO. Handles partitioning, base system, Hyprland desktop environment, and all hyprconf dotfiles in one pass.',
    steps: [
      'Boot from an Arch Linux ISO',
      'Connect to the internet (use iwctl for Wi-Fi)',
      'Run: bash <(curl -fsSL hyprconf.sh)',
      'Select option [1] Full Arch Install',
      'Follow the prompts — disk, timezone, hostname, and user account',
      'Reboot into your new system',
    ],
  },
  {
    title: 'Dotfiles Only',
    description:
      'Apply hyprconf dotfiles to an existing Arch Linux + Hyprland system. Installs all packages, symlinks configs via GNU Stow, and enables system services.',
    steps: [
      'Run: bash <(curl -fsSL hyprconf.sh)',
      'Select option [2] Dotfiles Only',
      'Packages are installed and configs are symlinked',
      'Services (iwd, bluetooth, pipewire) are enabled',
      'Log out and back in to apply',
    ],
  },
  {
    title: 'CLI Only',
    description:
      'Install just the hyprconf CLI and TUI tool without modifying your existing dotfiles or desktop.',
    steps: [
      'Run: bash <(curl -fsSL hyprconf.sh)',
      'Select option [3] CLI Only',
      'The hyprconf binary is placed in ~/.local/bin/',
      'Run hyprconf --help to get started',
    ],
  },
];
