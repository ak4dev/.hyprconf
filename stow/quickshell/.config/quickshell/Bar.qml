import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import Quickshell.Services.SystemTray
import Quickshell.Services.Pipewire
import Quickshell.Widgets

// One bar per monitor; layout and styling mirror waybar.jsonc + waybar.css.
PanelWindow {
    id: bar

    required property var modelData
    screen: modelData

    anchors {
        top: true
        left: true
        right: true
    }
    implicitHeight: 24
    color: "transparent"

    readonly property string home: Quickshell.env("HOME")

    // ---- clock (waybar: format + format-alt toggled on click)
    SystemClock {
        id: clock
        precision: SystemClock.Seconds
    }
    property bool clockAlt: false

    function fmtClock(): string {
        const d = clock.date
        if (bar.clockAlt)
            return "󰥔 " + Qt.formatDateTime(d, "ddd, MMM dd HH:mm")
        let h = d.getHours() % 12
        if (h === 0)
            h = 12
        const p = n => String(n).padStart(2, "0")
        return "󰥔 " + p(h) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds())
    }

    // Hyprland.activeToplevel only populates from focus events, so seed the
    // initial title via IPC; events take over after the first focus change.
    property string seedTitle: ""
    property int seedTries: 0

    Process {
        id: seedProc
        running: true
        command: ["hyprctl", "-j", "activewindow"]
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    bar.seedTitle = JSON.parse(text).title ?? ""
                } catch (e) {}
            }
        }
    }

    // The one-shot seed can race a Hyprland config reload (empty IPC reply
    // when the bar is relaunched by the exec line), so retry a few times.
    Timer {
        interval: 700
        repeat: true
        running: bar.seedTries < 5 && bar.seedTitle === "" && Hyprland.activeToplevel === null
        onTriggered: {
            bar.seedTries++
            seedProc.running = true
        }
    }

    Connections {
        target: Hyprland
        function onRawEvent(event) {
            if (event.name === "activewindow")
                bar.seedTitle = ""
        }
    }

    // ---- pipewire default sink (replaces waybar's pulseaudio module)
    PwObjectTracker {
        objects: [Pipewire.defaultAudioSink]
    }
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real vol: sink?.audio?.volume ?? 0
    readonly property bool muted: sink?.audio?.muted ?? false

    // ---- streaming cpu/mem/net stats (single long-lived sampler)
    property int cpuPct: 0
    property string memText: ""
    property string netKind: "off"
    property string netDown: "0B/s"
    property string netUp: "0B/s"

    Process {
        running: true
        command: ["bash", bar.home + "/.config/quickshell/stats.sh"]
        stdout: SplitParser {
            onRead: data => {
                try {
                    const j = JSON.parse(data)
                    bar.cpuPct = j.cpu
                    bar.memText = j.mem
                    bar.netKind = j.net
                    bar.netDown = j.down
                    bar.netUp = j.up
                } catch (e) {}
            }
        }
    }

    component BarText: Text {
        font.family: Theme.font
        font.pixelSize: Theme.fontSize
        color: Theme.fg
        textFormat: Text.PlainText
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.bgAlpha

        // ================= left: workspaces island + window title
        Row {
            anchors.left: parent.left
            height: parent.height

            Item { width: 8; height: 1 } // island margin-left

            Rectangle {
                id: island
                anchors.verticalCenter: parent.verticalCenter
                width: wsRow.width + 16 // island padding 0 8
                height: 24
                radius: 12
                color: Theme.bgAlpha

                Row {
                    id: wsRow
                    anchors.centerIn: parent

                    Repeater {
                        model: Hyprland.workspaces

                        delegate: Item {
                            id: wsButton
                            required property var modelData
                            visible: modelData.id > 0 // hide special workspaces
                            width: visible ? pill.width + 8 : 0 // button margin 0 4
                            height: 20

                            Rectangle {
                                id: pill
                                x: 4
                                width: wsLabel.implicitWidth + 16 // button padding 0 8
                                height: 20
                                radius: 8
                                color: wsButton.modelData.focused ? Theme.purpleAlpha
                                     : wsMouse.containsMouse ? Theme.cyanAlpha
                                     : "transparent"

                                BarText {
                                    id: wsLabel
                                    anchors.centerIn: parent
                                    text: wsButton.modelData.focused ? "󰮯" : String(wsButton.modelData.id)
                                    color: wsButton.modelData.focused ? Theme.accent
                                         : wsMouse.containsMouse ? Theme.cyan
                                         : Theme.comment
                                }

                                MouseArea {
                                    id: wsMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: wsButton.modelData.activate()
                                }
                            }
                        }
                    }
                }
            }

            Item { width: 8; height: 1 } // island margin-right

            Item { // hyprland/window, max-length 50
                id: titleItem
                width: titleText.text === "" ? 0 : titleText.width + 20
                height: parent.height

                BarText {
                    id: titleText
                    x: 10
                    anchors.verticalCenter: parent.verticalCenter
                    // Cap the width so the title elides instead of running
                    // into the clock (waybar overlaps on narrow portrait
                    // monitors). implicitWidth is the natural text width, so
                    // this binding is not circular with titleItem.width.
                    width: Math.min(implicitWidth, Math.max(0, clockItem.x - titleItem.x - 24))
                    elide: Text.ElideRight
                    text: {
                        const t = Hyprland.activeToplevel?.title || bar.seedTitle
                        return t.length > 50 ? t.substring(0, 50) + "…" : t
                    }
                }
            }
        }

        // ================= center: clock
        Item {
            id: clockItem
            width: clockText.implicitWidth
            height: parent.height
            // Centered, but slides left instead of colliding with the right
            // block on narrow (portrait) monitors.
            x: Math.min((parent.width - width) / 2,
                        parent.width - rightRow.width - width - 8)

            BarText {
                id: clockText
                anchors.centerIn: parent
                text: bar.fmtClock()
                color: Theme.accent
            }

            MouseArea {
                anchors.fill: parent
                onClicked: bar.clockAlt = !bar.clockAlt
            }
        }

        // ================= right
        Row {
            id: rightRow
            anchors.right: parent.right
            height: parent.height

            Item { // tray: padding 0 8, icon 16, spacing 8
                visible: SystemTray.items.values.length > 0
                width: visible ? trayRow.width + 16 : 0
                height: parent.height

                Row {
                    id: trayRow
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Repeater {
                        model: SystemTray.items

                        delegate: Item {
                            id: trayItem
                            required property var modelData
                            width: 16
                            height: 16

                            IconImage {
                                anchors.fill: parent
                                source: trayItem.modelData.icon
                            }

                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
                                onClicked: mouse => {
                                    if (mouse.button === Qt.LeftButton && !trayItem.modelData.onlyMenu) {
                                        trayItem.modelData.activate()
                                    } else if (mouse.button === Qt.MiddleButton) {
                                        trayItem.modelData.secondaryActivate()
                                    } else {
                                        const p = trayItem.mapToItem(null, 0, trayItem.height)
                                        trayItem.modelData.display(bar, p.x, p.y)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item { // cpu (fused with cpu_temp: padding-right 2)
                width: cpuText.implicitWidth + 8 + 2
                height: parent.height

                BarText {
                    id: cpuText
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: "󰻠 " + bar.cpuPct + "%"
                    color: Theme.green
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: Quickshell.execDetached(["kitty", "-e", "htop"])
                }
            }

            ScriptModule { // custom/cpu_temp (padding-left 2)
                height: parent.height
                command: ["bash", bar.home + "/.config/waybar/cpu_temp.sh"]
                intervalMs: 2000
                prefix: ""
                textColor: Theme.green
                padL: 2
            }

            Item { // memory
                width: memText_.implicitWidth + 16
                height: parent.height

                BarText {
                    id: memText_
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    text: bar.memText === "" ? "" : "󰘚 " + bar.memText
                    color: Theme.yellow
                }
            }

            ScriptModule { // custom/gpu
                height: parent.height
                command: ["bash", bar.home + "/.config/waybar/gpu_info.sh"]
                intervalMs: 2000
                prefix: "󰾲 "
                textColor: Theme.purple
            }

            ScriptModule { // custom/vpn
                height: parent.height
                command: [bar.home + "/.local/bin/hyprconf", "vpn", "status", "--json"]
                intervalMs: 5000
                textColor: Theme.comment
                classColors: ({
                    "connected": Theme.green,
                    "connected-killswitch": Theme.cyan,
                    "disconnected": Theme.comment
                })
                onModuleClicked: Quickshell.execDetached([bar.home + "/.local/bin/hyprconf", "vpn", "toggle"])
            }

            Item { // network (min-width 180 like waybar.css)
                width: Math.max(netText.implicitWidth + 16, 180)
                height: parent.height

                BarText {
                    id: netText
                    anchors.centerIn: parent
                    color: Theme.cyan
                    text: bar.netKind === "off" ? "󰖪 Disconnected"
                        : (bar.netKind === "wifi" ? "󰖩" : "󰈀")
                          + " ↓" + bar.netDown + " ↑" + bar.netUp
                }
            }

            Item { // pulseaudio
                width: volText.implicitWidth + 16
                height: parent.height

                BarText {
                    id: volText
                    x: 8
                    anchors.verticalCenter: parent.verticalCenter
                    color: bar.muted ? Theme.red : Theme.pink
                    text: bar.muted ? "󰝟 Muted"
                        : (bar.vol <= 0.33 ? "󰕿" : bar.vol <= 0.66 ? "󰖀" : "󰕾")
                          + " " + Math.round(bar.vol * 100) + "%"
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: Quickshell.execDetached(["pavucontrol"])
                }
            }

            ScriptModule { // custom/power_status
                height: parent.height
                command: ["bash", bar.home + "/.config/waybar/battery_power_status.sh"]
                intervalMs: 1000
                textColor: Theme.fg
                classColors: ({
                    "normal": "#ffffff",
                    "warning": "#fab005",
                    "critical": "#f03e3e",
                    "charging": "#37b24d"
                })
            }
        }
    }
}
