import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.Pipewire

// macOS-style OSD: frosted pill at the bottom of the focused monitor,
// auto-hides, input-transparent. Shows volume (pushed by pipewire) and
// backlight level (pushed by hyprconf-brightness over IPC — sysfs backlight
// files do not emit inotify events, so there is nothing to watch here).
PanelWindow {
    id: osd

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property real vol: sink?.audio?.volume ?? 0
    readonly property bool muted: sink?.audio?.muted ?? false

    // "volume" | "brightness" — which reading the pill is currently showing.
    property string mode: "volume"
    property int brightnessPct: 0

    readonly property real level: mode === "brightness"
        ? brightnessPct / 100
        : Math.min(1, vol)
    // Muting is a volume state; a dimmed backlight is not "off".
    readonly property bool dimmed: mode === "volume" && muted

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
        mode = "volume"
        show = true
        hideTimer.restart()
    }

    // Called over IPC by hyprconf-brightness with the level it just set. The
    // value is clamped and only ever drawn — never executed — and it skips the
    // `armed` gate: a keypress is not the startup burst pipewire produces.
    function showBrightness(percent) {
        brightnessPct = Math.max(0, Math.min(100, Math.round(percent)))
        mode = "brightness"
        show = true
        hideTimer.restart()
        return "ok"
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
                text: osd.mode === "brightness"
                    ? (osd.level <= 0.33 ? "󰃞" : osd.level <= 0.66 ? "󰃟" : "󰃠")
                    : osd.dimmed ? "󰝟"
                    : osd.level <= 0.33 ? "󰕿" : osd.level <= 0.66 ? "󰖀" : "󰕾"
                color: osd.dimmed ? Theme.red : Theme.accent
            }

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 160
                height: 6
                radius: 3
                color: Qt.rgba(Theme.fg.r, Theme.fg.g, Theme.fg.b, 0.15)

                Rectangle {
                    width: parent.width * osd.level
                    height: parent.height
                    radius: parent.radius
                    color: osd.dimmed ? Theme.comment : Theme.accent

                    Behavior on width {
                        NumberAnimation { duration: 80 }
                    }
                }
            }

            BarText {
                anchors.verticalCenter: parent.verticalCenter
                font.pixelSize: 12
                text: Math.round(osd.level * 100) + "%"
                color: Theme.comment
            }
        }
    }
}
