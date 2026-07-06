import QtQuick
import Quickshell
import Quickshell.Services.Pipewire

// Volume panel: slider + mute for the default sink, plus an output-device
// switcher (sets pipewire's preferred default sink).
Column {
    id: root
    spacing: 10
    width: 300

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property var sinks: Pipewire.nodes.values.filter(
        n => n.isSink && !n.isStream && n.audio)

    // Bind every listed node so descriptions/volumes are populated.
    PwObjectTracker { objects: root.sinks }

    // current output + mute
    Row {
        spacing: 8
        width: parent.width

        BarText {
            id: muteBtn
            text: root.sink?.audio?.muted ? "󰝟" : "󰕾"
            color: root.sink?.audio?.muted ? Theme.red : Theme.pink
            MouseArea {
                anchors.fill: parent
                anchors.margins: -4
                onClicked: if (root.sink?.audio) root.sink.audio.muted = !root.sink.audio.muted
            }
        }

        BarText {
            width: parent.width - muteBtn.width - pct.width - 16
            elide: Text.ElideRight
            text: root.sink?.description ?? "No output device"
            color: Theme.fg
        }

        BarText {
            id: pct
            text: Math.round((root.sink?.audio?.volume ?? 0) * 100) + "%"
            color: Theme.comment
        }
    }

    // slider
    Item {
        width: parent.width
        height: 20

        Rectangle {
            id: track
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width
            height: 6
            radius: 3
            color: "#40928374"
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: track.width * Math.min(1, root.sink?.audio?.volume ?? 0)
            height: 6
            radius: 3
            color: Theme.pink

            Behavior on width {
                NumberAnimation { duration: 60 }
            }
        }

        Rectangle {
            x: track.width * Math.min(1, root.sink?.audio?.volume ?? 0) - width / 2
            anchors.verticalCenter: parent.verticalCenter
            width: 14
            height: 14
            radius: 7
            color: Theme.fg
        }

        MouseArea {
            anchors.fill: parent
            onPressed: mouse => setVol(mouse.x)
            onPositionChanged: mouse => { if (pressed) setVol(mouse.x) }
            function setVol(mx) {
                if (root.sink?.audio)
                    root.sink.audio.volume = Math.max(0, Math.min(1, mx / width))
            }
        }
    }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    BarText {
        text: "Outputs"
        font.pixelSize: 12
        color: Theme.comment
    }

    Column {
        width: parent.width
        spacing: 2

        Repeater {
            model: root.sinks

            delegate: Rectangle {
                id: row
                required property var modelData
                width: parent.width
                height: 26
                radius: 6
                color: rowM.containsMouse ? Theme.hover : "transparent"

                readonly property bool current: row.modelData === Pipewire.defaultAudioSink

                BarText {
                    x: 6
                    anchors.verticalCenter: parent.verticalCenter
                    text: row.current ? "󰄬" : " "
                    font.pixelSize: 12
                    color: Theme.green
                }

                BarText {
                    x: 26
                    width: parent.width - 32
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideRight
                    font.pixelSize: 12
                    text: row.modelData.description || row.modelData.name
                    color: row.current ? Theme.fg : Theme.comment
                }

                MouseArea {
                    id: rowM
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: Pipewire.preferredDefaultAudioSink = row.modelData
                }
            }
        }
    }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    Rectangle {
        width: parent.width
        height: 26
        radius: 6
        color: pavuM.containsMouse ? Theme.hover : "transparent"

        BarText {
            anchors.centerIn: parent
            font.pixelSize: 12
            text: "󰕮  Sound settings (pavucontrol)"
            color: Theme.cyan
        }

        MouseArea {
            id: pavuM
            anchors.fill: parent
            hoverEnabled: true
            onClicked: Quickshell.execDetached(["pavucontrol"])
        }
    }
}
