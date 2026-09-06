-- hyprconf look'n'feel overlay for Omarchy: loaded after Omarchy's defaults
-- (/usr/share/omarchy/default/hypr/looknfeel.lua), so this states only where
-- hyprconf differs — restating a value Omarchy already sets would drift the
-- moment it retunes the default. Left to Omarchy on purpose: the border
-- colours (the active theme owns them) and xwayland.force_zero_scaling
-- (default/hypr/envs.lua).

hl.config({
  general = {
    -- hyprconf runs tighter than Omarchy's 5 / 10. SUPER+SHIFT+= / SUPER+SHIFT+-
    -- (hyprconf-gaps) move both at runtime via hyprctl, so this is only
    -- the value each session starts at.
    gaps_in = 3,
    gaps_out = 3,
  },

  decoration = {
    -- Omarchy squares its corners (rounding 0); hyprconf keeps a hairline
    -- radius with a sharper falloff curve.
    rounding = 1,
    rounding_power = 3,

    -- Unfocused windows are translucent (Omarchy: opaque).
    inactive_opacity = 0.8,

    -- Both off in Omarchy's defaults (default/hypr/looknfeel.lua sets only
    -- `enabled = false` for each). The shadow is only switched on: its range,
    -- falloff and colour stay at Hyprland's own, and the colour is a theme's
    -- to set — Omarchy loads the active theme's hyprland.lua
    -- (default/hypr/omarchy.lua, `omarchy.current.theme.hyprland`) before
    -- this file, and lumon ships its own shadow, which a value here would
    -- have clobbered. The blur keeps its size / passes: Hyprland's are 8 / 1.
    shadow = {
      enabled = true,
    },

    blur = {
      enabled = true,
      size = 3,
      passes = 4,
    },
  },
})

-- Animation deltas only — the curves and every other leaf already match
-- Omarchy's defaults.
hl.animation({ leaf = "windows",       enabled = true, speed = 4.79, bezier = "easeOutQuint" })
-- Omarchy disables the workspace animation outright; hyprconf cross-fades.
hl.animation({ leaf = "workspaces",    enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesIn",  enabled = true, speed = 1.21, bezier = "almostLinear", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 1.94, bezier = "almostLinear", style = "fade" })

hl.config({
  dwindle = {
    -- Omarchy forces every split to the same side (force_split = 2); hyprconf
    -- splits by where the cursor is, and lets a mouse drop pick the split from
    -- the quadrant of the window it lands on.
    force_split = 0,
    precise_mouse_move = true,

    -- Cursor position decides the split DIRECTION, not just which side the new
    -- window takes. Without this, Hyprland picks the orientation automatically
    -- from the container's aspect — it splits along the longer axis — so the
    -- same gesture tiles side-by-side on a wide container and stacked on a tall
    -- one, which is why the layout felt inconsistent between machines even
    -- though every dwindle setting matched. Neither hyprconf nor Omarchy set
    -- this; it is a deliberate divergence, chosen for predictability.
    smart_split = true,
  },
})

-- Window rules --------------------------------------------------------------
--
-- Steam tiles like everything else. Omarchy floats every window of class
-- "steam" (/usr/share/omarchy/default/hypr/apps/steam.lua: `o.window("steam",
-- { float = true, idle_inhibit = "fullscreen" })` plus a centred 1100x700 for
-- the main window). This file is required AFTER default.hypr.omarchy, and
-- Hyprland applies window rules in order, so a later `tile = true` wins —
-- the same way Omarchy's own apps/browser.lua un-floats Chromium windows.
-- Shipped unconditionally: a rule for an app that is not installed costs
-- nothing, and Steam installed later is tiled from its first window.
--
-- The Friends List keeps floating: Omarchy sizes it as a 460x800 panel
-- (same file), which only makes sense floating, and a tiled friends list is
-- a column of nothing. Omarchy's other two rules in that file — the
-- `idle_inhibit = "fullscreen"` on class "steam" and the opaque
-- `opacity = "1 1"` on "steam.*" — are untouched: a rule sets only the
-- effects it names. (Omarchy has no rule for the `steam_app_*` classes
-- games run under; that shape appears only in apps/battlenet.lua.)
o.window("steam", { tile = true })
o.window({ class = "steam", title = "Friends List" }, { float = true })
