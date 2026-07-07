import QtQuick
import Quickshell
import Quickshell.Services.Pipewire
import Quickshell.Bluetooth
import Quickshell.Networking
import Quickshell.Widgets

// macOS-style Control Center: Wi-Fi (with in-panel network list + connect),
// Bluetooth, and full audio (volume + output/input device pickers). Only
// Bluetooth *pairing* still delegates to an app (blueman); everything else
// is handled inline. Wi-Fi uses Quickshell.Networking (NetworkManager over
// D-Bus): radio toggles, scans, and connects — including the PSK — never
// touch a shell, argv, or the process list, and nothing is polled; state is
// pushed by NetworkManager.
Column {
    id: root
    width: 340
    spacing: 12

    // ---------------- Wi-Fi (Quickshell.Networking) ----------------
    readonly property var wifiDev:
        Networking.devices.values.find(d => d.type === DeviceType.Wifi) ?? null
    readonly property bool wifiEnabled: Networking.wifiEnabled
    readonly property string wifiSsid:
        wifiDev?.networks.values.find(n => n.connected)?.name ?? ""
    property string pwSsid: ""          // ssid whose password box is open

    // Scan only while the panel is open (the Loader destroys it on close).
    // Networking.devices populates asynchronously over D-Bus, so wifiDev is
    // usually still null at onCompleted — enable the scanner whenever the
    // device (re)appears as well.
    onWifiDevChanged: if (wifiDev) wifiDev.scannerEnabled = true
    Component.onCompleted: if (wifiDev) wifiDev.scannerEnabled = true
    Component.onDestruction: if (wifiDev) wifiDev.scannerEnabled = false

    // Strongest-first, deduped by SSID, capped like the nmcli list was.
    readonly property var networks: {
        if (!wifiDev)
            return []
        const seen = ({})
        const out = []
        for (const n of wifiDev.networks.values) {
            if (!n.name || seen[n.name])
                continue
            seen[n.name] = true
            out.push(n)
        }
        out.sort((a, b) => b.signalStrength - a.signalStrength)
        return out.slice(0, 6)
    }

    function toggleWifi() {
        Networking.wifiEnabled = !Networking.wifiEnabled
    }

    function isOpenNet(net) {
        return net.security === WifiSecurityType.Open
            || net.security === WifiSecurityType.Owe
    }

    // Saved/open networks connect directly; secured unknown ones get the
    // inline password box. A wrong PSK re-opens it via connectionFailed.
    function connectTo(net) {
        if (net.connected)
            return
        if (net.known || isOpenNet(net))
            net.connect()
        else
            root.pwSsid = net.name
    }

    function submitPw(net, pw) {
        if (pw.length === 0)
            return
        net.connectWithPsk(pw)
        root.pwSsid = ""
    }

    function wifiGlyph(sig) {
        return sig >= 0.75 ? "󰤨" : sig >= 0.5 ? "󰤥" : sig >= 0.25 ? "󰤢" : sig > 0 ? "󰤟" : "󰤯"
    }

    // ---------------- Bluetooth ----------------
    readonly property var btAdapter: Bluetooth.defaultAdapter
    readonly property bool btOn: btAdapter?.enabled ?? false

    // ---------------- Audio (Pipewire) ----------------
    PwObjectTracker { objects: [Pipewire.defaultAudioSink, Pipewire.defaultAudioSource] }
    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var source: Pipewire.defaultAudioSource
    readonly property var sinks: Pipewire.nodes.values.filter(n => n.isSink && !n.isStream && n.audio)
    readonly property var sources: Pipewire.nodes.values.filter(n => n.audio && !n.isStream && !n.isSink)
    PwObjectTracker { objects: root.sinks }
    PwObjectTracker { objects: root.sources }

    // ================= toggle tiles =================
    component Tile: Rectangle {
        id: tile
        property string icon
        property string label
        property string sublabel
        property bool active
        signal clicked()
        width: (root.width - 12) / 2
        height: 62
        radius: 16
        color: active ? Theme.accent : Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.08)
        Behavior on color { ColorAnimation { duration: Theme.animFast } }

        Row {
            anchors.left: parent.left; anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            Rectangle {
                width: 34; height: 34; radius: 17
                anchors.verticalCenter: parent.verticalCenter
                color: tile.active ? Qt.rgba(1, 1, 1, 0.25) : Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.12)
                BarText {
                    anchors.centerIn: parent; text: tile.icon; font.pixelSize: 16
                    color: tile.active ? "#ffffff" : Theme.fg
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: 1
                BarText { text: tile.label; font.pixelSize: 13; color: tile.active ? "#ffffff" : Theme.fg }
                BarText {
                    width: tile.width - 68; elide: Text.ElideRight; text: tile.sublabel
                    font.pixelSize: 11; color: tile.active ? Qt.rgba(1, 1, 1, 0.8) : Theme.comment
                }
            }
        }
        MouseArea { anchors.fill: parent; onClicked: tile.clicked() }
    }

    Row {
        spacing: 12
        Tile {
            icon: root.wifiEnabled ? "󰤨" : "󰤭"
            label: "Wi-Fi"
            sublabel: !root.wifiEnabled ? "Off" : (root.wifiSsid || "On")
            active: root.wifiEnabled
            onClicked: root.toggleWifi()
        }
        Tile {
            icon: root.btOn ? "󰂯" : "󰂲"
            label: "Bluetooth"
            sublabel: {
                if (!root.btOn) return "Off"
                const c = Bluetooth.devices.values.filter(d => d.connected)
                // `?? "On"`: a device can be mid-teardown with no name — a
                // QString property must never be assigned undefined.
                return c.length > 0 ? (c[0].name ?? "On") : "On"
            }
            active: root.btOn
            onClicked: if (root.btAdapter) root.btAdapter.enabled = !root.btAdapter.enabled
        }
    }

    // ================= Wi-Fi networks =================
    Column {
        width: parent.width
        spacing: 2
        visible: root.wifiEnabled && root.networks.length > 0

        BarText { text: "Networks"; font.pixelSize: 11; color: Theme.comment }

        Repeater {
            model: root.networks
            delegate: Column {
                id: netEntry
                required property var modelData
                width: root.width
                spacing: 2

                // Wrong PSK → NetworkManager reports NoSecrets → re-open the
                // password box for this network.
                // `?.` / `?? null` guards throughout: scan results churn the
                // model, so a delegate can briefly outlive its modelData.
                Connections {
                    target: netEntry.modelData ?? null
                    function onConnectionFailed(reason) {
                        if (reason === ConnectionFailReason.NoSecrets)
                            root.pwSsid = netEntry.modelData.name
                    }
                }

                Rectangle {
                    width: parent.width; height: 30; radius: 8
                    color: nm.containsMouse ? Theme.hover : "transparent"

                    BarText {
                        x: 8; anchors.verticalCenter: parent.verticalCenter
                        text: root.wifiGlyph(netEntry.modelData?.signalStrength ?? 0)
                        font.pixelSize: 14
                        color: netEntry.modelData?.connected ? Theme.accent : Theme.fg
                    }
                    BarText {
                        x: 34; width: parent.width - 120
                        anchors.verticalCenter: parent.verticalCenter
                        elide: Text.ElideRight; font.pixelSize: 12
                        text: netEntry.modelData?.name ?? ""
                        color: netEntry.modelData?.connected ? Theme.fg : Theme.comment
                    }
                    BarText {
                        anchors.right: parent.right; anchors.rightMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        font.pixelSize: 11
                        text: !netEntry.modelData ? ""
                            : netEntry.modelData.stateChanging ? "…"
                            : netEntry.modelData.connected ? "connected"
                            : !root.isOpenNet(netEntry.modelData) ? "󰤪" : ""
                        color: netEntry.modelData?.connected ? Theme.green : Theme.comment
                    }
                    MouseArea {
                        id: nm; anchors.fill: parent; hoverEnabled: true
                        onClicked: {
                            if (!netEntry.modelData || netEntry.modelData.connected) return
                            if (root.pwSsid === netEntry.modelData.name) root.pwSsid = ""
                            else root.connectTo(netEntry.modelData)
                        }
                    }
                }

                // inline password box (opens when a secured connect needs one)
                Rectangle {
                    width: parent.width; height: 32; radius: 8
                    visible: netEntry.modelData != null && root.pwSsid === netEntry.modelData.name
                    color: Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.08)

                    Row {
                        anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 6
                        spacing: 6
                        BarText {
                            anchors.verticalCenter: parent.verticalCenter
                            text: "󰌾"; font.pixelSize: 13; color: Theme.comment
                        }
                        TextInput {
                            id: pwInput
                            width: parent.width - 90
                            anchors.verticalCenter: parent.verticalCenter
                            font.family: Theme.font; font.pixelSize: 12
                            color: Theme.fg
                            echoMode: TextInput.Password
                            clip: true
                            focus: visible
                            onVisibleChanged: if (visible) forceActiveFocus()
                            onAccepted: { if (netEntry.modelData) root.submitPw(netEntry.modelData, text); text = "" }
                            BarText {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: pwInput.text.length === 0
                                text: "Password"; font.pixelSize: 12; color: Theme.comment
                            }
                        }
                        Rectangle {
                            width: 60; height: 24; radius: 6
                            anchors.verticalCenter: parent.verticalCenter
                            color: joinM.containsMouse ? Theme.accent : Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.6)
                            BarText {
                                anchors.centerIn: parent; text: "Join"; font.pixelSize: 12; color: "#ffffff"
                            }
                            MouseArea {
                                id: joinM; anchors.fill: parent; hoverEnabled: true
                                onClicked: { if (netEntry.modelData) root.submitPw(netEntry.modelData, pwInput.text); pwInput.text = "" }
                            }
                        }
                    }
                }
            }
        }
    }

    // ================= volume + output =================
    Column {
        width: parent.width
        spacing: 6

        Row {
            width: parent.width; spacing: 8
            BarText {
                id: volIcon
                anchors.verticalCenter: parent.verticalCenter
                text: root.sink?.audio?.muted ? "󰝟" : (root.sink?.audio?.volume ?? 0) <= 0.5 ? "󰖀" : "󰕾"
                color: root.sink?.audio?.muted ? Theme.red : Theme.fg
                MouseArea {
                    anchors.fill: parent; anchors.margins: -6
                    onClicked: if (root.sink?.audio) root.sink.audio.muted = !root.sink.audio.muted
                }
            }
            Item {
                width: parent.width - volIcon.width - opct.width - 16; height: 18
                anchors.verticalCenter: parent.verticalCenter
                Rectangle {
                    id: otrack; anchors.verticalCenter: parent.verticalCenter
                    width: parent.width; height: 6; radius: 3
                    color: Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.15)
                }
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: otrack.width * Math.min(1, root.sink?.audio?.volume ?? 0)
                    height: 6; radius: 3; color: Theme.accent
                }
                Rectangle {
                    x: otrack.width * Math.min(1, root.sink?.audio?.volume ?? 0) - 7
                    anchors.verticalCenter: parent.verticalCenter
                    width: 14; height: 14; radius: 7; color: "#ffffff"
                }
                MouseArea {
                    anchors.fill: parent
                    onPressed: mouse => set(mouse.x)
                    onPositionChanged: mouse => { if (pressed) set(mouse.x) }
                    function set(mx) { if (root.sink?.audio) root.sink.audio.volume = Math.max(0, Math.min(1, mx / width)) }
                }
            }
            BarText { id: opct; anchors.verticalCenter: parent.verticalCenter; text: Math.round((root.sink?.audio?.volume ?? 0) * 100) + "%"; font.pixelSize: 12; color: Theme.comment }
        }

        // output devices
        Column {
            width: parent.width; spacing: 2
            visible: root.sinks.length > 1
            BarText { text: "Output"; font.pixelSize: 11; color: Theme.comment }
            Repeater {
                model: root.sinks
                delegate: DeviceRow {
                    required property var modelData
                    label: modelData?.description || modelData?.name || ""
                    current: modelData === Pipewire.defaultAudioSink
                    onPicked: if (modelData) Pipewire.preferredDefaultAudioSink = modelData
                }
            }
        }

        // input (microphone) devices
        Column {
            width: parent.width; spacing: 2
            visible: root.sources.length >= 1
            Row {
                width: parent.width; spacing: 6
                BarText { text: "Input"; font.pixelSize: 11; color: Theme.comment }
                BarText {
                    text: root.source?.audio?.muted ? "󰍭 muted" : "󰍬"
                    font.pixelSize: 11
                    color: root.source?.audio?.muted ? Theme.red : Theme.comment
                    MouseArea {
                        anchors.fill: parent; anchors.margins: -4
                        onClicked: if (root.source?.audio) root.source.audio.muted = !root.source.audio.muted
                    }
                }
            }
            Repeater {
                model: root.sources
                delegate: DeviceRow {
                    required property var modelData
                    label: modelData?.description || modelData?.name || ""
                    current: modelData === Pipewire.defaultAudioSource
                    onPicked: if (modelData) Pipewire.preferredDefaultAudioSource = modelData
                }
            }
        }
    }

    component DeviceRow: Rectangle {
        property string label
        property bool current
        signal picked()
        width: root.width; height: 28; radius: 8
        color: drm.containsMouse ? Theme.hover : "transparent"
        BarText {
            x: 8; anchors.verticalCenter: parent.verticalCenter
            text: parent.current ? "󰄬" : ""; font.pixelSize: 12; color: Theme.green; width: 16
        }
        BarText {
            x: 28; width: parent.width - 36
            anchors.verticalCenter: parent.verticalCenter
            elide: Text.ElideRight; font.pixelSize: 12
            text: parent.label; color: parent.current ? Theme.fg : Theme.comment
        }
        MouseArea { id: drm; anchors.fill: parent; hoverEnabled: true; onClicked: parent.picked() }
    }

    // ================= bluetooth devices =================
    Column {
        width: parent.width; spacing: 2
        visible: root.btOn && Bluetooth.devices.values.length > 0
        BarText { text: "Devices"; font.pixelSize: 11; color: Theme.comment }
        Repeater {
            model: Bluetooth.devices
            delegate: Rectangle {
                id: btRow
                required property var modelData
                visible: modelData != null
                    && (modelData.bonded || modelData.paired || modelData.connected)
                width: parent.width; height: visible ? 30 : 0; radius: 8
                color: btM.containsMouse ? Theme.hover : "transparent"
                BarText {
                    x: 8; anchors.verticalCenter: parent.verticalCenter
                    text: "󰂱"; font.pixelSize: 13
                    color: btRow.modelData?.connected ? Theme.accent : Theme.comment
                }
                BarText {
                    x: 32; width: parent.width - 120
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight; font.pixelSize: 12
                    text: btRow.modelData?.name ?? ""
                    color: btRow.modelData?.connected ? Theme.fg : Theme.comment
                }
                BarText {
                    anchors.right: parent.right; anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    font.pixelSize: 11
                    text: !btRow.modelData ? ""
                        : btRow.modelData.connected
                        ? (btRow.modelData.batteryAvailable ? Math.round(btRow.modelData.battery * 100) + "%  connected" : "connected")
                        : "connect"
                    color: btRow.modelData?.connected ? Theme.green : Theme.comment
                }
                MouseArea {
                    id: btM; anchors.fill: parent; hoverEnabled: true
                    onClicked: if (btRow.modelData) btRow.modelData.connected = !btRow.modelData.connected
                }
            }
        }
    }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    // Only pairing NEW Bluetooth devices still needs the full app.
    Rectangle {
        width: parent.width; height: 28; radius: 8
        color: btSetM.containsMouse ? Theme.hover : "transparent"
        Row {
            anchors.left: parent.left; anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter; spacing: 10
            BarText { text: "󰂯"; font.pixelSize: 13; color: Theme.cyan }
            BarText { text: "Pair a Bluetooth device…"; font.pixelSize: 12; color: Theme.cyan }
        }
        MouseArea { id: btSetM; anchors.fill: parent; hoverEnabled: true; onClicked: Quickshell.execDetached(["blueman-manager"]) }
    }
}
