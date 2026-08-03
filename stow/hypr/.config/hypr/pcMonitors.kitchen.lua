-- Kitchen monitor preset (Lua). Apply manually: `switch_monitor.sh kitchen`.
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
