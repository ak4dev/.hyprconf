-- hyprconf look'n'feel overlay for Omarchy: loaded after Omarchy's defaults
-- (/usr/share/omarchy/default/hypr/looknfeel.lua), so this states only where
-- hyprconf differs — restating a value Omarchy already sets would drift the
-- moment it retunes the default. Left to Omarchy on purpose: the border
-- colours (the active theme owns them) and xwayland.force_zero_scaling
-- (default/hypr/envs.lua).

hl.config({
  general = {
    -- hyprconf runs tighter than Omarchy's 5 / 10. SUPER+SHIFT+= / SUPER+SHIFT+-
    -- (scripts/adjust-gaps) move both at runtime via hyprctl, so this is only
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

    -- Both off in Omarchy's defaults.
    shadow = {
      enabled = true,
      range = 4,
      render_power = 3,
      color = "rgba(1a1a1aee)",
    },

    blur = {
      enabled = true,
      size = 3,
      passes = 4,
      vibrancy = 0.1696,
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

  misc = {
    -- Never draw Hyprland's own wallpaper; Omarchy's background is set by
    -- omarchy-theme-bg-next / the active theme.
    force_default_wallpaper = 0,
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
-- a column of nothing. Omarchy's idle_inhibit and opacity rules for Steam
-- games (steam_app_*) are untouched.
o.window("steam", { tile = true })
o.window({ class = "steam", title = "Friends List" }, { float = true })
