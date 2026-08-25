-- Alternate desktop preset: `hyprconf-monitor-preset K`. See https://wiki.hypr.land/Configuring/Basics/Monitors/
hl.monitor({ output = "DP-2", mode = "3840x2160@75", position = "0x0", scale = 2, transform = 3, supports_hdr = true })
hl.monitor({ output = "DP-1", mode = "3840x2160@240", position = "auto-left", scale = 2, supports_hdr = true })
hl.monitor({ output = "HDMI-A-1", mode = "3840x2160@120", position = "auto-left", scale = 2, supports_hdr = true })

hl.workspace_rule({ workspace = "1", monitor = "DP-1" })
hl.workspace_rule({ workspace = "2", monitor = "DP-1" })
hl.workspace_rule({ workspace = "3", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "4", monitor = "HDMI-A-1" })
hl.workspace_rule({ workspace = "5", monitor = "DP-2" })
hl.workspace_rule({ workspace = "6", monitor = "DP-2" })
