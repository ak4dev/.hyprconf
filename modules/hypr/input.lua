-- hyprconf input overlay for Omarchy: ~/.config/hypr/input.lua, require'd
-- after Omarchy's defaults (config/hypr/hyprland.lua:20), so only the deltas
-- are stated. The keyboard layout logic (kb_* from /etc/vconsole.conf, compose
-- on CapsLock, a Latin fallback layout) is Omarchy's on purpose; follow_mouse
-- and sensitivity already match.

hl.config({
  input = {
    -- Natural (inverted) scrolling for the mouse and the touchpad (Omarchy: off).
    natural_scroll = true,

    touchpad = {
      natural_scroll = true,
    },
  },
})

-- Touchpad gestures. Since the 0.51 gesture rework the swipe itself must be
-- declared with hl.gesture(): Omarchy declares none (config/hypr/input.lua:53
-- carries this very line commented out), and without it the gestures.* keys
-- below apply to nothing.
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

hl.config({
  gestures = {
    -- A quick flick commits the switch (Hyprland: 30 px per timepoint).
    workspace_swipe_min_speed_to_force = 15,
    -- Keep swiping past the neighbouring workspace (Hyprland clamps to it).
    workspace_swipe_forever = true,
  },
})
