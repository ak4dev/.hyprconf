import QtQuick

// Waybar-style bar module chrome for a Services-fed data source: fixed
// padding, class→color mapping, hide-when-empty, critical blink, click
// signal. Bind `text`/`klass` from the Services singleton — bars are pure
// views, and Services runs each sampler exactly once for all screens
// (this component used to own a Process + poll Timer per bar instance,
// which duplicated every sampler per monitor).
Item {
    id: root

    property string text: ""
    property string klass: ""
    property string prefix: ""
    property color textColor: Theme.fg
    // class name -> color; unknown classes fall back to textColor
    property var classColors: ({})
    property int padL: 5
    property int padR: 5

    signal moduleClicked()

    visible: text !== ""
    width: visible ? label.implicitWidth + padL + padR : 0

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
