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
-- without it.
hl.gesture({ fingers = 3, direction = "horizontal", action = "workspace" })

hl.config({
  gestures = {
    workspace_swipe_invert = true,                  -- Matches macOS natural swipe direction (touchpad)
    workspace_swipe_distance = 300,                 -- Distance for swipe gesture (adjust for sensitivity)
    workspace_swipe_min_speed_to_force = 15,        -- Minimum speed to force a swipe
    workspace_swipe_cancel_ratio = 0.5,             -- Prevents accidental swipes
    workspace_swipe_create_new = true,              -- Create new workspaces on swipe
    workspace_swipe_direction_lock = true,          -- Locks swipe direction after threshold
    workspace_swipe_direction_lock_threshold = 10,  -- Distance before locking direction
    workspace_swipe_forever = true,                 -- Allows swiping through all workspaces
  },
})
