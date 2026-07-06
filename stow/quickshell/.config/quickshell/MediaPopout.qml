import QtQuick
import Quickshell.Widgets

// MPRIS media controls with album art and track progress.
Column {
    id: root
    spacing: 10
    width: 300

    required property var player

    // Poll the position while visible; MPRIS position does not update
    // reactively (emitting positionChanged forces a re-read).
    Timer {
        interval: 1000
        running: root.visible && (root.player?.isPlaying ?? false)
        repeat: true
        onTriggered: root.player.positionChanged()
    }

    function fmtTime(s) {
        if (!isFinite(s) || s < 0)
            return "--:--"
        const m = Math.floor(s / 60)
        const sec = Math.floor(s % 60)
        return m + ":" + String(sec).padStart(2, "0")
    }

    Row {
        spacing: 10
        width: parent.width

        // Album art: local files only — the shell performs no network I/O.
        Rectangle {
            id: artBox
            width: 64
            height: 64
            radius: 8
            color: "#40928374"
            clip: true

            readonly property string artUrl: root.player?.trackArtUrl ?? ""

            Image {
                id: artImg
                anchors.fill: parent
                visible: status === Image.Ready
                asynchronous: true
                fillMode: Image.PreserveAspectCrop
                source: artBox.artUrl.startsWith("file://") ? artBox.artUrl : ""
            }

            BarText {
                anchors.centerIn: parent
                visible: artImg.status !== Image.Ready
                text: "󰎈"
                font.pixelSize: 24
                color: Theme.comment
            }
        }

        Column {
            width: parent.width - artBox.width - 10
            anchors.verticalCenter: artBox.verticalCenter
            spacing: 2

            BarText {
                width: parent.width
                elide: Text.ElideRight
                text: root.player?.trackTitle || "Nothing playing"
            }
            BarText {
                width: parent.width
                elide: Text.ElideRight
                font.pixelSize: 12
                text: root.player?.trackArtist ?? ""
                color: Theme.comment
            }
            BarText {
                width: parent.width
                elide: Text.ElideRight
                font.pixelSize: 11
                text: root.player?.identity ?? ""
                color: "#66928374"
            }
        }
    }

    // progress
    Column {
        width: parent.width
        spacing: 4

        Rectangle {
            width: parent.width
            height: 5
            radius: 2.5
            color: "#40928374"

            Rectangle {
                readonly property real frac:
                    (root.player?.positionSupported && root.player?.lengthSupported
                        && root.player?.length > 0)
                        ? Math.min(1, (root.player?.position ?? 0) / root.player.length)
                        : 0
                width: parent.width * frac
                height: parent.height
                radius: parent.radius
                color: Theme.orange
            }
        }

        Item {
            width: parent.width
            height: 14

            BarText {
                anchors.left: parent.left
                font.pixelSize: 11
                color: Theme.comment
                text: root.fmtTime(root.player?.position ?? -1)
            }
            BarText {
                anchors.right: parent.right
                font.pixelSize: 11
                color: Theme.comment
                text: root.fmtTime(root.player?.length ?? -1)
            }
        }
    }

    // controls
    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 28

        component CtlButton: BarText {
            property bool allowed: true
            signal pressed()
            font.pixelSize: 20
            color: allowed ? (m.containsMouse ? Theme.cyan : Theme.fg) : "#66928374"
            MouseArea {
                id: m
                anchors.fill: parent
                anchors.margins: -6
                hoverEnabled: true
                enabled: parent.allowed
                onClicked: parent.pressed()
            }
        }

        CtlButton {
            text: "󰒮"
            allowed: root.player?.canGoPrevious ?? false
            onPressed: root.player.previous()
        }
        CtlButton {
            text: (root.player?.isPlaying ?? false) ? "󰏤" : "󰐊"
            allowed: root.player?.canTogglePlaying ?? false
            onPressed: root.player.togglePlaying()
        }
        CtlButton {
            text: "󰒭"
            allowed: root.player?.canGoNext ?? false
            onPressed: root.player.next()
        }
    }
}
