-- Kitchen monitor preset: `hyprconf-monitor-preset kitchen` (SUPER+SHIFT+K). See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Output names verified against this desk's `hyprctl monitors all`: the
-- Odyssey G8 enumerates as DP-4, the portrait CB282K as DP-5, and the LG TV
-- (the bedroom display, off in this layout) as HDMI-A-2.
hl.monitor({ output = "DP-4", mode = "3840x2160@240.00", position = "auto-right", scale = 2.0, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.7 })
hl.monitor({ output = "DP-5", mode = "3840x2160@60", position = "0x0", scale = 2, transform = 1 })
hl.monitor({ output = "HDMI-A-2", disabled = true })
hl.monitor({ output = "DP-6", disabled = true })

hl.workspace_rule({ workspace = "1", monitor = "DP-4" })
hl.workspace_rule({ workspace = "2", monitor = "DP-4" })
hl.workspace_rule({ workspace = "3", monitor = "DP-4" })
hl.workspace_rule({ workspace = "4", monitor = "DP-5" })
hl.workspace_rule({ workspace = "5", monitor = "DP-5" })
hl.workspace_rule({ workspace = "6", monitor = "DP-5" })
