-- Kitchen monitor preset: `hyprconf-monitor-preset kitchen` (SUPER+SHIFT+K). See https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Outputs are named by DESCRIPTION, not connector — see the comment in
-- pcMonitors.bedroom.lua for why (recabling renumbers DP-N/HDMI-A-N; a
-- description follows the panel). Verified against this desk's
-- `hyprctl monitors all` on Hyprland 0.56.2.
-- The Odyssey only reaches 3840x2160@240.00 on the 5090's DisplayPort; it was
-- capped at 4K@60 for as long as it hung off the 3070.
hl.monitor({ output = "desc:Samsung Electric Company Odyssey G8", mode = "3840x2160@240.00", position = "auto-right", scale = 2.0, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.7 })
hl.monitor({ output = "desc:Acer Technologies CB282K", mode = "3840x2160@60.00", position = "0x0", scale = 2, transform = 1 })
hl.monitor({ output = "desc:LG Electronics LG TV SSCR2", disabled = true })

hl.workspace_rule({ workspace = "1", monitor = "desc:Samsung Electric Company Odyssey G8" })
hl.workspace_rule({ workspace = "2", monitor = "desc:Samsung Electric Company Odyssey G8" })
hl.workspace_rule({ workspace = "3", monitor = "desc:Samsung Electric Company Odyssey G8" })
hl.workspace_rule({ workspace = "4", monitor = "desc:Acer Technologies CB282K" })
hl.workspace_rule({ workspace = "5", monitor = "desc:Acer Technologies CB282K" })
hl.workspace_rule({ workspace = "6", monitor = "desc:Acer Technologies CB282K" })

-- Safety net: any panel not named above comes up at its preferred mode rather
-- than staying dark. Named rules win over the catch-all whatever the order —
-- the disable above included — so this only fires for an unknown display.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })
