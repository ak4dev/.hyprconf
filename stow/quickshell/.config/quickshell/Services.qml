pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// One instance of every bar data source, shared by all screens. Bar{} is
// instantiated per monitor (Variants in shell.qml); before this singleton
// each screen ran its own stats.sh, GPU stream, battery poll and VPN poll —
// two monitors meant two of everything. Sample once, bind everywhere.
Singleton {
    id: root

    readonly property string home: Quickshell.env("HOME")

    // ---- streaming cpu/mem/net/temp (stats.sh: long-lived pure-bash
    // sampler, one JSON line per second, hwmon temp resolved at startup)
    property int cpuPct: 0
    property string memText: ""
    property string netKind: "off"
    property string netDown: "0B/s"
    property string netUp: "0B/s"
    property string cpuTemp: ""

    Process {
        running: true
        command: ["bash", root.home + "/.config/quickshell/stats.sh"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    const j = JSON.parse(data)
                    root.cpuPct = j.cpu
                    root.memText = j.mem
                    root.netKind = j.net
                    root.netDown = j.down
                    root.netUp = j.up
                    root.cpuTemp = j.temp ?? ""
                } catch (e) {}
            }
        }
    }

    // ---- streaming gpu (gpu_info.sh: one nvidia-smi --loop piped through
    // one awk, or a pure-bash AMD sysfs loop). A stream that produced output
    // and then died is restarted (driver hiccup); one that exits without
    // ever producing output means "no such hardware" — stays hidden.
    property string gpuText: ""
    property bool _gpuProduced: false

    Process {
        id: gpuProc
        running: true
        command: ["bash", root.home + "/.config/quickshell/scripts/gpu_info.sh"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    root._gpuProduced = true
                    root.gpuText = String(JSON.parse(data).text ?? "")
                } catch (e) {}
            }
        }
        onExited: {
            if (root._gpuProduced)
                gpuRespawn.start()
        }
    }
    Timer {
        id: gpuRespawn
        interval: 3000
        onTriggered: gpuProc.running = true
    }

    // ---- polled battery (1s). The script answers with `"once": true` on
    // battery-less desktops — the result can never change, so the poll stops
    // after the first sample instead of spawning a shell every second.
    property string batText: ""
    property string batClass: ""
    property bool _batDone: false

    Process {
        id: batProc
        command: ["bash", root.home + "/.config/quickshell/scripts/battery_power_status.sh"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    const j = JSON.parse(data)
                    root.batText = j.text !== undefined ? String(j.text) : ""
                    root.batClass = j["class"] !== undefined ? String(j["class"]) : ""
                    if (j.once === true)
                        root._batDone = true
                } catch (e) {}
            }
        }
    }
    Timer {
        interval: 1000
        running: !root._batDone
        repeat: true
        triggeredOnStart: true
        onTriggered: batProc.running = true
    }

    // ---- polled vpn (5s; state changes are rare and user-driven)
    property string vpnText: ""
    property string vpnClass: ""

    Process {
        id: vpnProc
        command: [root.home + "/.local/bin/hyprconf", "vpn", "status", "--json"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    const j = JSON.parse(data)
                    root.vpnText = j.text !== undefined ? String(j.text) : ""
                    root.vpnClass = j["class"] !== undefined ? String(j["class"]) : ""
                } catch (e) {}
            }
        }
    }
    Timer {
        interval: 5000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: vpnProc.running = true
    }
}
