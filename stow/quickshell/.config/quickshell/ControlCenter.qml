import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire
import Quickshell.Bluetooth
import Quickshell.Widgets

// macOS-style Control Center: Wi-Fi / Bluetooth toggle tiles, a volume
// slider, the audio-output picker, and the Bluetooth device list, plus
// launch actions for the full apps. Radio toggles use argv (no shell, no
// secrets); network/BT credential flows are delegated to nmtui / blueman.
Column {
    id: root
    width: 340
    spacing: 12

    // ---------------- Wi-Fi (NetworkManager via nmcli) ----------------
    property bool wifiEnabled: false
    property string wifiSsid: ""

    Process {
        id: wifiStatus
        command: ["bash", "-c",
            "nmcli -t radio wifi; nmcli -t -f active,ssid dev wifi | awk -F: '$1==\"yes\"{print $2; exit}'"]
        stdout: StdioCollector {
            onStreamFinished: {
                const lines = text.split("\n")
                root.wifiEnabled = (lines[0] ?? "").trim() === "enabled"
                root.wifiSsid = (lines[1] ?? "").trim()
            }
        }
    }
    Timer {
        interval: 4000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: wifiStatus.running = true
    }

    function toggleWifi() {
        Quickshell.execDetached(["nmcli", "radio", "wifi", root.wifiEnabled ? "off" : "on"])
        wifiRefresh.restart()
    }
    Timer { id: wifiRefresh; interval: 600; onTriggered: wifiStatus.running = true }

    // ---------------- Bluetooth (Quickshell.Bluetooth) ----------------
    readonly property var btAdapter: Bluetooth.defaultAdapter
    readonly property bool btOn: btAdapter?.enabled ?? false

    // ---------------- Audio (Pipewire) ----------------
    PwObjectTracker { objects: [Pipewire.defaultAudioSink] }
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var sinks: Pipewire.nodes.values.filter(n => n.isSink && !n.isStream && n.audio)
    PwObjectTracker { objects: root.sinks }

    // ================= toggle tiles =================
    component Tile: Rectangle {
        id: tile
        property string icon
        property string label
        property string sublabel
        property bool active
        signal clicked()
        signal secondary()

        width: (root.width - 12) / 2
        height: 62
        radius: 16
        color: active ? Theme.accent : Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.08)

        Behavior on color { ColorAnimation { duration: Theme.animFast } }

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10

            Rectangle {
                width: 34; height: 34; radius: 17
                anchors.verticalCenter: parent.verticalCenter
                color: tile.active ? Qt.rgba(1, 1, 1, 0.25)
                     : Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.12)
                BarText {
                    anchors.centerIn: parent
                    text: tile.icon
                    font.pixelSize: 16
                    color: tile.active ? "#ffffff" : Theme.fg
                }
            }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                BarText {
                    text: tile.label
                    font.pixelSize: 13
                    color: tile.active ? "#ffffff" : Theme.fg
                }
                BarText {
                    width: tile.width - 68
                    elide: Text.ElideRight
                    text: tile.sublabel
                    font.pixelSize: 11
                    color: tile.active ? Qt.rgba(1, 1, 1, 0.8) : Theme.comment
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.LeftButton | Qt.RightButton
            onClicked: mouse => mouse.button === Qt.RightButton ? tile.secondary() : tile.clicked()
        }
    }

    Row {
        spacing: 12
        Tile {
            icon: root.wifiEnabled ? "󰤨" : "󰤭"
            label: "Wi-Fi"
            sublabel: !root.wifiEnabled ? "Off" : (root.wifiSsid || "On")
            active: root.wifiEnabled
            onClicked: root.toggleWifi()
            onSecondary: Quickshell.execDetached(["kitty", "--class", "nm-float", "-e", "nmtui", "connect"])
        }
        Tile {
            icon: root.btOn ? "󰂯" : "󰂲"
            label: "Bluetooth"
            sublabel: {
                if (!root.btOn) return "Off"
                const c = Bluetooth.devices.values.filter(d => d.connected)
                return c.length > 0 ? c[0].name : "On"
            }
            active: root.btOn
            onClicked: if (root.btAdapter) root.btAdapter.enabled = !root.btAdapter.enabled
            onSecondary: Quickshell.execDetached(["blueman-manager"])
        }
    }

    // ================= volume =================
    Column {
        width: parent.width
        spacing: 6

        Row {
            width: parent.width
            spacing: 8
            BarText {
                id: volIcon
                text: root.sink?.audio?.muted ? "󰝟"
                    : (root.sink?.audio?.volume ?? 0) <= 0.5 ? "󰖀" : "󰕾"
                color: root.sink?.audio?.muted ? Theme.red : Theme.fg
                MouseArea {
                    anchors.fill: parent; anchors.margins: -6
                    onClicked: if (root.sink?.audio) root.sink.audio.muted = !root.sink.audio.muted
                }
            }
            Item {
                width: parent.width - volIcon.width - pct.width - 16
                height: 18
                anchors.verticalCenter: parent.verticalCenter

                Rectangle {
                    id: vtrack
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width; height: 6; radius: 3
                    color: Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.15)
                }
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: vtrack.width * Math.min(1, root.sink?.audio?.volume ?? 0)
                    height: 6; radius: 3
                    color: Theme.accent
                }
                Rectangle {
                    x: vtrack.width * Math.min(1, root.sink?.audio?.volume ?? 0) - 7
                    anchors.verticalCenter: parent.verticalCenter
                    width: 14; height: 14; radius: 7; color: "#ffffff"
                }
                MouseArea {
                    anchors.fill: parent
                    onPressed: mouse => set(mouse.x)
                    onPositionChanged: mouse => { if (pressed) set(mouse.x) }
                    function set(mx) {
                        if (root.sink?.audio)
                            root.sink.audio.volume = Math.max(0, Math.min(1, mx / width))
                    }
                }
            }
            BarText {
                id: pct
                text: Math.round((root.sink?.audio?.volume ?? 0) * 100) + "%"
                font.pixelSize: 12
                color: Theme.comment
            }
        }
    }

    // ================= output devices =================
    Column {
        width: parent.width
        spacing: 2
        visible: root.sinks.length > 1

        BarText { text: "Output"; font.pixelSize: 11; color: Theme.comment }

        Repeater {
            model: root.sinks
            delegate: Rectangle {
                id: outRow
                required property var modelData
                readonly property bool current: modelData === Pipewire.defaultAudioSink
                width: parent.width; height: 28; radius: 8
                color: outM.containsMouse ? Theme.hover : "transparent"
                BarText {
                    x: 8; anchors.verticalCenter: parent.verticalCenter
                    text: outRow.current ? "󰄬" : ""
                    font.pixelSize: 12; color: Theme.green; width: 16
                }
                BarText {
                    x: 28; width: parent.width - 36
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight; font.pixelSize: 12
                    text: outRow.modelData.description || outRow.modelData.name
                    color: outRow.current ? Theme.fg : Theme.comment
                }
                MouseArea {
                    id: outM; anchors.fill: parent; hoverEnabled: true
                    onClicked: Pipewire.preferredDefaultAudioSink = outRow.modelData
                }
            }
        }
    }

    // ================= bluetooth devices =================
    Column {
        width: parent.width
        spacing: 2
        visible: root.btOn && Bluetooth.devices.values.length > 0

        BarText { text: "Devices"; font.pixelSize: 11; color: Theme.comment }

        Repeater {
            model: Bluetooth.devices
            delegate: Rectangle {
                id: btRow
                required property var modelData
                // paired/known devices first; hide random unpaired noise
                visible: modelData.bonded || modelData.paired || modelData.connected
                width: parent.width
                height: visible ? 30 : 0
                radius: 8
                color: btM.containsMouse ? Theme.hover : "transparent"

                BarText {
                    x: 8; anchors.verticalCenter: parent.verticalCenter
                    text: "󰂱"; font.pixelSize: 13
                    color: btRow.modelData.connected ? Theme.accent : Theme.comment
                }
                BarText {
                    x: 32; width: parent.width - 120
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight; font.pixelSize: 12
                    text: btRow.modelData.name
                    color: btRow.modelData.connected ? Theme.fg : Theme.comment
                }
                BarText {
                    anchors.right: parent.right; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    font.pixelSize: 11
                    text: btRow.modelData.connected
                        ? (btRow.modelData.batteryAvailable
                            ? Math.round(btRow.modelData.battery * 100) + "%  connected"
                            : "connected")
                        : "connect"
                    color: btRow.modelData.connected ? Theme.green : Theme.comment
                }
                MouseArea {
                    id: btM; anchors.fill: parent; hoverEnabled: true
                    onClicked: btRow.modelData.connected = !btRow.modelData.connected
                }
            }
        }
    }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    // ================= action links =================
    component Action: Rectangle {
        id: actionRow
        property string icon
        property string label
        signal act()
        width: root.width; height: 28; radius: 8
        color: am.containsMouse ? Theme.hover : "transparent"
        Row {
            anchors.left: parent.left; anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            BarText { text: actionRow.icon; font.pixelSize: 13; color: Theme.cyan }
            BarText { text: actionRow.label; font.pixelSize: 12; color: Theme.cyan }
        }
        MouseArea { id: am; anchors.fill: parent; hoverEnabled: true; onClicked: actionRow.act() }
    }

    Action {
        icon: "󰤨"; label: "Wi-Fi networks…"
        onAct: Quickshell.execDetached(["kitty", "--class", "nm-float", "-e", "nmtui", "connect"])
    }
    Action {
        icon: "󰂯"; label: "Bluetooth settings…"
        onAct: Quickshell.execDetached(["blueman-manager"])
    }
    Action {
        icon: "󰕾"; label: "Sound settings…"
        onAct: Quickshell.execDetached(["pavucontrol"])
    }
}
