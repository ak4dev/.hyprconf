import QtQuick
import Quickshell.Io

// Generic waybar-style "custom" module: runs `command` every `intervalMs`,
// expects a single JSON line {"text": ..., "class": ...} on stdout, hides
// itself when the script prints nothing.
Item {
    id: root

    property list<string> command: []
    property int intervalMs: 2000
    property string prefix: ""
    property color textColor: Theme.fg
    // class name -> color; unknown classes fall back to textColor
    property var classColors: ({})
    property int padL: 8
    property int padR: 8

    property string text: ""
    property string klass: ""

    signal moduleClicked()

    visible: text !== ""
    width: visible ? label.implicitWidth + padL + padR : 0

    Process {
        id: proc
        command: root.command
        stdout: SplitParser {
            onRead: data => {
                try {
                    const j = JSON.parse(data)
                    root.text = j.text !== undefined ? String(j.text) : ""
                    root.klass = j["class"] !== undefined ? String(j["class"]) : ""
                } catch (e) {
                    // non-JSON line — ignore
                }
            }
        }
    }

    Timer {
        interval: root.intervalMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: proc.running = true
    }

    Text {
        id: label
        x: root.padL
        anchors.verticalCenter: parent.verticalCenter
        text: root.prefix + root.text
        color: root.classColors[root.klass] ?? root.textColor
        font.family: Theme.font
        font.pixelSize: Theme.fontSize
        textFormat: Text.PlainText
    }

    // waybar's `@keyframes blink` on battery-critical
    SequentialAnimation on opacity {
        running: root.klass === "critical"
        loops: Animation.Infinite
        NumberAnimation { from: 1; to: 0.5; duration: 500 }
        NumberAnimation { from: 0.5; to: 1; duration: 500 }
        onRunningChanged: if (!running) root.opacity = 1
    }

    MouseArea {
        anchors.fill: parent
        onClicked: root.moduleClicked()
    }
}
