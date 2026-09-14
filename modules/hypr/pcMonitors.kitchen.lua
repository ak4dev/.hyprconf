-- Kitchen monitor preset: `hyprconf-monitor-preset kitchen` (SUPER+SHIFT+K).
-- Outputs by desc:<make> <model>: never a connector (renumbers across GPUs),
-- never a serial (PII); the output = "" line below is the catch-all. Why and
-- syntax: README.md in this folder.
hl.monitor({ output = "desc:Samsung Electric Company Odyssey G8", mode = "3840x2160@240.00", position = "auto-right", scale = 2.0, vrr = 2, bitdepth = 10, cm = "dcip3", sdrbrightness = 1.7 })
hl.monitor({ output = "desc:Acer Technologies CB282K", mode = "3840x2160@60.00", position = "0x0", scale = 2, transform = 1 })
hl.monitor({ output = "desc:LG Electronics LG TV SSCR2", disabled = true })

hl.workspace_rule({ workspace = "1", monitor = "desc:Samsung Electric Company Odyssey G8" })
hl.workspace_rule({ workspace = "2", monitor = "desc:Samsung Electric Company Odyssey G8" })
hl.workspace_rule({ workspace = "3", monitor = "desc:Samsung Electric Company Odyssey G8" })
hl.workspace_rule({ workspace = "4", monitor = "desc:Acer Technologies CB282K" })
hl.workspace_rule({ workspace = "5", monitor = "desc:Acer Technologies CB282K" })
hl.workspace_rule({ workspace = "6", monitor = "desc:Acer Technologies CB282K" })

-- Safety net: an unknown panel comes up at its preferred mode, not dark.
hl.monitor({ output = "", mode = "preferred", position = "auto", scale = "auto" })
