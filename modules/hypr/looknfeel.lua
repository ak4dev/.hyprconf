-- hyprconf look'n'feel overlay for Omarchy: ~/.config/hypr/looknfeel.lua,
-- require'd after Omarchy's defaults (config/hypr/hyprland.lua:22), so this
-- states only where hyprconf differs. Left to Omarchy on purpose: the border
-- colours (the active theme owns them) and xwayland.force_zero_scaling
-- (default/hypr/envs.lua).

hl.config({
  general = {
    -- Tighter than Omarchy's 5 / 10; hyprconf-gaps moves both at runtime, so
    -- this is only the value each session starts at.
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

    -- Both off in Omarchy's defaults. The shadow is only switched ON: its
    -- range, falloff and colour belong to the active theme, which Omarchy
    -- loads before this file (default/hypr/omarchy.lua,
    -- `omarchy.current.theme.hyprland`) — lumon ships its own shadow, which a
    -- value here would clobber.
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

-- Omarchy floats every "steam" window (default/hypr/apps/steam.lua); this
-- file loads after it and a later rule wins, so Steam tiles like everything
-- else. The Friends List stays floating — Omarchy sizes it as a 460x800 panel.
o.window("steam", { tile = true })
o.window({ class = "steam", title = "Friends List" }, { float = true })
