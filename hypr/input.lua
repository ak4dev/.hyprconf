-- hyprconf input overlay for Omarchy: loaded after Omarchy's defaults
-- (/usr/share/omarchy/default/hypr/input.lua), so only the deltas are stated.
-- The keyboard layout logic (kb_* from /etc/vconsole.conf, compose on
-- CapsLock, a Latin fallback layout) is Omarchy's on purpose; follow_mouse
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
-- declared with hl.gesture(); the gestures.* tuning below applies to nothing
-- without it. Omarchy declares no gesture and sets no gestures.* key (its
-- config/hypr/input.lua carries this line commented out), so the baseline
-- here is Hyprland's own — inverted direction, 300 px distance, 0.5 cancel
-- ratio, a new workspace past the last, direction lock at 10 px — and only
-- the two values that differ from it are stated.
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

hl.config({
  gestures = {
    -- A quick flick commits the switch (Hyprland: 30 px per timepoint).
    workspace_swipe_min_speed_to_force = 15,
    -- Keep swiping past the neighbouring workspace (Hyprland clamps to it).
    workspace_swipe_forever = true,
  },
})
