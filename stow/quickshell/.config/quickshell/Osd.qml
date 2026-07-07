import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.Pipewire

// macOS-style volume OSD: frosted pill at the bottom of the focused
// monitor, shown on volume/mute changes, auto-hides. Input-transparent.
PanelWindow {
    id: osd

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real vol: sink?.audio?.volume ?? 0
    readonly property bool muted: sink?.audio?.muted ?? false

    property bool show: false
    // Suppress the burst of change signals while pipewire syncs at startup.
    property bool armed: false

    PwObjectTracker { objects: [Pipewire.defaultAudioSink] }

    screen: Quickshell.screens.find(
                s => Hyprland.monitorFor(s) === Hyprland.focusedMonitor)
            ?? Quickshell.screens[0]

    visible: show
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: "quickshell:osd"

    // Purely visual: never intercept clicks.
    mask: Region {}

    anchors.bottom: true
    margins.bottom: 48

    implicitWidth: 280
    implicitHeight: 44

    Timer {
        id: armTimer
        interval: 2000
        running: true
        onTriggered: osd.armed = true
    }

    Timer {
        id: hideTimer
        interval: 1400
        onTriggered: osd.show = false
    }

    function ping() {
        if (!armed)
            return
        show = true
        hideTimer.restart()
    }

    Connections {
        target: osd.sink?.audio ?? null
        function onVolumeChanged() { osd.ping() }
        function onMutedChanged() { osd.ping() }
    }

    Rectangle {
        anchors.fill: parent
        radius: height / 2
        color: Theme.surface

        Row {
            anchors.centerIn: parent
            spacing: 12

            BarText {
                anchors.verticalCenter: parent.verticalCenter
                text: osd.muted ? "󰝟"
                    : osd.vol <= 0.33 ? "󰕿" : osd.vol <= 0.66 ? "󰖀" : "󰕾"
                color: osd.muted ? Theme.red : Theme.pink
            }

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 160
                height: 6
                radius: 3
                color: "#40928374"

                Rectangle {
                    width: parent.width * Math.min(1, osd.vol)
                    height: parent.height
                    radius: parent.radius
                    color: osd.muted ? Theme.comment : Theme.pink

                    Behavior on width {
                        NumberAnimation { duration: 80 }
                    }
                }
            }

            BarText {
                anchors.verticalCenter: parent.verticalCenter
                font.pixelSize: 12
                text: Math.round(osd.vol * 100) + "%"
                color: Theme.comment
            }
        }
    }
}
