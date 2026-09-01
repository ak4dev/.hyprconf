-- Kitchen monitor preset: `hyprconf-monitor-preset kitchen` (SUPER+SHIFT+K). See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Output names verified against this desk's `hyprctl monitors all`: the
-- Odyssey G8 enumerates as DP-1, the portrait CB282K as DP-2, and the LG TV
-- (the bedroom display, off in this layout) as HDMI-A-1. The DP-N/HDMI-A-N
-- numbering follows the GPU the session drives the displays through (probe
-- order / AQ_DRM_DEVICES / cabling) — re-verify it whenever that changes.
hl.monitor({ output = "DP-1", mode = "3840x2160@240.00", position = "auto-right", scale = 2.0, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.7 })
hl.monitor({ output = "DP-2", mode = "3840x2160@60", position = "0x0", scale = 2, transform = 1 })
hl.monitor({ output = "HDMI-A-1", disabled = true })
hl.monitor({ output = "DP-3", disabled = true })

hl.workspace_rule({ workspace = "1", monitor = "DP-1" })
hl.workspace_rule({ workspace = "2", monitor = "DP-1" })
hl.workspace_rule({ workspace = "3", monitor = "DP-1" })
hl.workspace_rule({ workspace = "4", monitor = "DP-2" })
hl.workspace_rule({ workspace = "5", monitor = "DP-2" })
hl.workspace_rule({ workspace = "6", monitor = "DP-2" })
