-- hyprconf input overlay for Omarchy.
--
-- Ported from the hyprland.lua of hyprconf's retired standalone desktop (its INPUT
-- section) and gestures.lua, into Omarchy's ~/.config/hypr/input.lua override
-- point — loaded after Omarchy's defaults, so only the deltas are stated here.
--
-- Deliberately NOT ported, each one checked against Omarchy's own input.lua:
--   * kb_layout / kb_variant / kb_model / kb_options / kb_rules. hyprconf hard
--     codes a bare "us" with no options; Omarchy derives the layout from
--     /etc/vconsole.conf, binds compose to CapsLock, and prepends a Latin
--     layout when the chosen one cannot type Latin keysyms (without which its
--     own SUPER bindings stop firing). Replacing that with "us" is a downgrade.
--   * follow_mouse = 1 and sensitivity = 0 — already Omarchy's values.
--   * hl.device({ name = "epic-mouse-v1", sensitivity = -0.5 }): the device
--     out of Hyprland's sample config, present on no machine here.

hl.config({
  input = {
    -- Natural (inverted) scrolling, and the mouse wheel counts — this is the
    -- default hyprconf has always shipped. Omarchy sets the touchpad to false
    -- and leaves the mouse on Hyprland's own default, which is false too.
    natural_scroll = true,

    touchpad = {
      natural_scroll = true,
    },
  },
})

-- Touchpad gestures, from hyprconf's gestures.lua.
--
-- Since the 0.51 gesture rework the old gestures:workspace_swipe toggle is
-- gone: without this hl.gesture() the tuning below would apply to nothing and
-- swiping would do nothing.
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
