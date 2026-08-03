-- Hyprland compositor config (Lua, Hyprland 0.55+). hyprlang `.conf` was
-- deprecated in 0.56 and is slated for removal ~0.57 — see
-- docs/hyprland-reference.md for the full syntax reference and the
-- deprecation timeline. hypridle/hyprlock/hyprpaper/hyprlauncher are
-- separate programs and still use their own hyprlang `.conf` files.

------------------
---- MONITORS ----
------------------

-- monitors.lua is a symlink to the active preset (pcMonitors.lua /
-- laptopMonitors.lua / pcMonitors.<name>.lua), swapped by switch_monitor.sh
-- and setup.sh's chassis-detection.
require("monitors")

-------------------------------
---- ENVIRONMENT VARIABLES ----
-------------------------------

-- Cursor
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

-- QT
hl.env("QT_QPA_PLATFORM", "wayland")
hl.env("QT_QPA_PLATFORMTHEME", "kde")

-- GTK — theme is managed by the theme switcher (switch_theme.py sets GTK_THEME
-- at runtime via hyprctl setenv + writes gtk-3.0/settings.ini + reloads
-- xsettingsd). Do NOT set GTK_THEME here; it would override the theme
-- switcher for every app.
hl.env("GTK_ICON_THEME", "Papirus-Dark")
hl.env("GTK_CURSOR_THEME", "Bibata-Modern-Ice")
hl.env("GTK_CURSOR_SIZE", "24")

-- Firefox — force native Wayland rendering
hl.env("MOZ_ENABLE_WAYLAND", "1")

-------------------
---- AUTOSTART ----
-------------------

-- Re-run every reload (plain top-level calls — a Lua config file re-executes
-- top-to-bottom on every `hyprctl reload`, matching classic `exec = …`
-- semantics). Both guards below are idempotent so a theme-switch reload does
-- not restart these.
hl.exec_cmd(
    "pgrep -x hyprpaper >/dev/null && pgrep -x hyprpaper | xargs -r kill; "
        .. "hyprpaper --config ~/.config/hypr/hyprpaper.conf"
)
-- Quickshell bar. The leading waybar kill is a migration shim: it stops a
-- stray waybar left running by a pre-quickshell install picking up this
-- config via `setup.sh --sync` (no-op once waybar is gone).
-- Idempotent: only launch if not already running, so `hyprctl reload` (e.g.
-- on a theme switch) does NOT restart quickshell — restarting tears down the
-- StatusNotifierWatcher it hosts and leaves the tray unresponsive. Quickshell
-- hot-reloads its own QML, and Theme.qml repaints live on theme change.
-- The guard matches BOTH `qs` and `quickshell`: launch.sh execs `qs` (a
-- symlink to quickshell) when the system package is present, so the running
-- process's comm is `qs`, not `quickshell`. Matching only `quickshell` made
-- the guard always miss, spawning a new instance on every reload.
hl.exec_cmd("pgrep -x waybar | xargs -r kill; pgrep -x 'qs|quickshell' >/dev/null || ~/.config/quickshell/launch.sh")

-- Fire once at startup only — the Lua equivalent of `exec-once =` (plain
-- top-level hl.exec_cmd() calls above re-run on every reload instead, the
-- equivalent of classic `exec =`).
hl.on("hyprland.start", function()
    hl.exec_cmd("/usr/lib/pam_kwallet_init")
    hl.exec_cmd("kwalletd6")
    hl.exec_cmd("systemctl --user start hyprpolkitagent")
    hl.exec_cmd("xsettingsd")
    hl.exec_cmd("hypridle")
    hl.exec_cmd("wl-paste --type text --watch cliphist store")
    hl.exec_cmd("wl-paste --type image --watch cliphist store")
    hl.exec_cmd("nm-applet --indicator")
    hl.exec_cmd("blueman-applet")
end)

-----------------------
----- PERMISSIONS -----
-----------------------

-- See https://wiki.hypr.land/Configuring/Advanced-and-Cool/Permissions/
-- Please note permission changes here require a Hyprland restart and are not
-- applied on-the-fly for security reasons

-- hl.config({
--   ecosystem = {
--     enforce_permissions = true,
--   },
-- })

-- hl.permission("/usr/(bin|local/bin)/grim", "screencopy", "allow")
-- hl.permission("/usr/(lib|libexec|lib64)/xdg-desktop-portal-hyprland", "screencopy", "allow")
-- hl.permission("/usr/(bin|local/bin)/hyprpm", "plugin", "allow")

-----------------------
---- LOOK AND FEEL ----
-----------------------

-- https://wiki.hypr.land/Configuring/Basics/Variables/#general
-- https://wiki.hypr.land/Configuring/Basics/Variables/#decoration
-- https://wiki.hypr.land/Configuring/Basics/Variables/#animations
hl.config({
    general = {
        gaps_in  = 3,
        gaps_out = 3,

        border_size = 2,

        col = {
            active_border   = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 },
            inactive_border = "rgba(595959aa)",
        },

        resize_on_border = false,
        allow_tearing    = false,

        layout = "dwindle",
    },

    decoration = {
        rounding       = 1,
        rounding_power = 3,

        -- Change transparency of focused and unfocused windows
        active_opacity   = 1,
        inactive_opacity = 0.8,

        shadow = {
            enabled      = true,
            range        = 4,
            render_power = 3,
            color        = "rgba(1a1a1aee)",
        },

        -- https://wiki.hypr.land/Configuring/Basics/Variables/#blur
        blur = {
            enabled  = true,
            size     = 3,
            passes   = 4,
            vibrancy = 0.1696,
        },
    },

    animations = {
        enabled = true,
    },
})

-- Default animations, see https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/ for more
hl.curve("easeOutQuint",   { type = "bezier", points = { { 0.23, 1 },    { 0.32, 1 } } })
hl.curve("easeInOutCubic", { type = "bezier", points = { { 0.65, 0.05 }, { 0.36, 1 } } })
hl.curve("linear",         { type = "bezier", points = { { 0, 0 },       { 1, 1 } } })
hl.curve("almostLinear",   { type = "bezier", points = { { 0.5, 0.5 },   { 0.75, 1 } } })
hl.curve("quick",          { type = "bezier", points = { { 0.15, 0 },    { 0.1, 1 } } })

hl.animation({ leaf = "global",        enabled = true, speed = 10,   bezier = "default" })
hl.animation({ leaf = "border",        enabled = true, speed = 5.39, bezier = "easeOutQuint" })
hl.animation({ leaf = "windows",       enabled = true, speed = 4.79, bezier = "easeOutQuint" })
hl.animation({ leaf = "windowsIn",     enabled = true, speed = 4.1,  bezier = "easeOutQuint", style = "popin 87%" })
hl.animation({ leaf = "windowsOut",    enabled = true, speed = 1.49, bezier = "linear",       style = "popin 87%" })
hl.animation({ leaf = "fadeIn",        enabled = true, speed = 1.73, bezier = "almostLinear" })
hl.animation({ leaf = "fadeOut",       enabled = true, speed = 1.46, bezier = "almostLinear" })
hl.animation({ leaf = "fade",          enabled = true, speed = 3.03, bezier = "quick" })
hl.animation({ leaf = "layers",        enabled = true, speed = 3.81, bezier = "easeOutQuint" })
hl.animation({ leaf = "layersIn",      enabled = true, speed = 4,    bezier = "easeOutQuint", style = "fade" })
hl.animation({ leaf = "layersOut",     enabled = true, speed = 1.5,  bezier = "linear",       style = "fade" })
hl.animation({ leaf = "fadeLayersIn",  enabled = true, speed = 1.79, bezier = "almostLinear" })
hl.animation({ leaf = "fadeLayersOut", enabled = true, speed = 1.39, bezier = "almostLinear" })
hl.animation({ leaf = "workspaces",    enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesIn",  enabled = true, speed = 1.21, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })

-- Ref https://wiki.hypr.land/Configuring/Basics/Workspace-Rules/
-- "Smart gaps" / "No gaps when only" — uncomment all if you wish to use that.
-- hl.workspace_rule({ workspace = "w[tv1]", gaps_out = 0, gaps_in = 0 })
-- hl.workspace_rule({ workspace = "f[1]",   gaps_out = 0, gaps_in = 0 })
-- hl.window_rule({ name = "no-gaps-wtv1", match = { float = false, workspace = "w[tv1]" }, border_size = 0, rounding = 0 })
-- hl.window_rule({ name = "no-gaps-f1",   match = { float = false, workspace = "f[1]" },   border_size = 0, rounding = 0 })

-- See https://wiki.hypr.land/Configuring/Layouts/Dwindle-Layout/ for more
hl.config({
    dwindle = {
        preserve_split = true,
        force_split    = 0,
        -- mouse drops choose the split by drop position (quadrant of the target window)
        precise_mouse_move = true,
    },
})

-- See https://wiki.hypr.land/Configuring/Layouts/Master-Layout/ for more
hl.config({
    master = {
        new_status = "master",
    },
})

-- https://wiki.hypr.land/Configuring/Basics/Variables/#misc
hl.config({
    misc = {
        force_default_wallpaper = 0,
        disable_hyprland_logo   = true,
        -- Let a fresh hyprlock take over after a crashed one. hyprlock dies
        -- at nearly every suspend exit; systemd (hyprlock.service,
        -- Restart=on-failure) relaunches it, and without this Hyprland
        -- refuses the new locker and sits on the "lockdead" screen.
        allow_session_lock_restore = true,
    },
})

-- Quickshell surfaces: frosted bar/popouts/OSD.
-- Blur is rendered by Hyprland (decoration.blur above); the shell only draws
-- translucent surfaces. Corners overlay is cosmetic and input-transparent.
hl.layer_rule({ name = "quickshell-bar-blur",       match = { namespace = "^(quickshell:bar)$" },      blur = true, ignore_alpha = 0.05 })
hl.layer_rule({ name = "quickshell-popouts-blur",   match = { namespace = "^(quickshell:popouts)$" },  blur = true, ignore_alpha = 0.05, no_anim = true })
hl.layer_rule({ name = "quickshell-osd-blur",       match = { namespace = "^(quickshell:osd)$" },      blur = true, ignore_alpha = 0.05, no_anim = true })
hl.layer_rule({ name = "quickshell-corners-noanim", match = { namespace = "^(quickshell:corners)$" },  no_anim = true })

---------------
---- INPUT ----
---------------

-- https://wiki.hypr.land/Configuring/Basics/Variables/#input
hl.config({
    input = {
        kb_layout  = "us",
        kb_variant = "",
        kb_model   = "",
        kb_options = "",
        kb_rules   = "",

        follow_mouse   = 1,
        sensitivity    = 0,
        natural_scroll = true,

        touchpad = {
            natural_scroll = true,
        },
    },
})

-- https://wiki.hypr.land/Configuring/Basics/Variables/#gestures
require("gestures")

hl.device({
    name        = "epic-mouse-v1",
    sensitivity = -0.5,
})

---------------------
---- KEYBINDINGS ----
---------------------

require("keybinds")

--------------------------------
---- WINDOWS AND WORKSPACES ----
--------------------------------

-- See https://wiki.hypr.land/Configuring/Basics/Window-Rules/
-- See https://wiki.hypr.land/Configuring/Basics/Workspace-Rules/ for workspace rules

-- Theme switcher — float and center the kitty window launched from hyprlauncher
hl.window_rule({ name = "theme-switcher-float", match = { class = "theme-switcher" }, float = true, center = true, size = "820 440" })

hl.config({
    xwayland = {
        force_zero_scaling = true,
    },
})

-- Theme-specific border/color overrides — updated by switch_theme.py
require("theme-colors")

-- Machine-local overrides (managed by hyprconf TUI/CLI — gitignored). Each is
-- optional, so a missing file is silently skipped (Lua's `require` has no
-- equivalent of hyprlang's "glob must match >=1 file" restriction).
--
-- `require()` converts every "." in a module name to a path separator, so a
-- dotted name like "conf.d.local" would resolve to conf/d/local.lua (two
-- nested dirs) rather than conf.d/local.lua (our one directory, named with a
-- literal dot, following the common /etc/foo.d/ convention). Extending
-- package.path with an explicit conf.d/?.lua template lets the plain names
-- below resolve correctly instead. Wrapped in pcall so a sandboxed/missing
-- `debug` library degrades to "no conf.d overrides" rather than a hard error.
pcall(function()
    local this_dir = debug.getinfo(1, "S").source:sub(2):match("(.*/)") or "./"
    package.path = package.path .. ";" .. this_dir .. "conf.d/?.lua"
end)

local function try_require(name)
    pcall(require, name)
end
try_require("local")
try_require("windowrules")
try_require("workspacerules")
try_require("hardware")
