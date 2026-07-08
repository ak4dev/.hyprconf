import QtQuick
import Quickshell

// Modern clock + month calendar (upgrade of waybar's clock tooltip):
// a large live time/date header over a month grid with weekend shading,
// today highlighted, and hover feedback. Click the month title for today.
Column {
    id: root
    spacing: 12
    width: 260

    property date shown: new Date()

    SystemClock {
        id: clock
        precision: SystemClock.Seconds
    }

    function monthShift(delta) {
        const d = new Date(shown)
        d.setDate(1)
        d.setMonth(d.getMonth() + delta)
        root.shown = d
    }

    // ---- header: big time + full date
    Column {
        width: parent.width
        spacing: 0

        BarText {
            text: Qt.formatDateTime(clock.date, "h:mm")
            font.pixelSize: 38
            color: Theme.accent

            BarText { // seconds, small
                anchors.left: parent.right
                anchors.leftMargin: 4
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 4
                text: Qt.formatDateTime(clock.date, "ss")
                font.pixelSize: 14
                color: Theme.comment
            }
        }

        BarText {
            text: Qt.formatDateTime(clock.date, "dddd, MMMM d")
            font.pixelSize: 13
            color: Theme.fg
        }
    }

    Rectangle { width: parent.width; height: 1; color: Theme.divider }

    // ---- month nav
    Item {
        width: grid.width
        height: 22

        BarText {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: "󰅁"
            color: navL.containsMouse ? Theme.cyan : Theme.comment
            MouseArea {
                id: navL
                anchors.fill: parent
                anchors.margins: -8
                hoverEnabled: true
                onClicked: root.monthShift(-1)
            }
        }

        BarText {
            anchors.centerIn: parent
            text: Qt.formatDate(root.shown, "MMMM yyyy")
            font.pixelSize: 13
            color: titleM.containsMouse ? Theme.cyan : Theme.fg
            MouseArea {
                id: titleM
                anchors.fill: parent
                hoverEnabled: true
                onClicked: root.shown = new Date()
            }
        }

        BarText {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            text: "󰅂"
            color: navR.containsMouse ? Theme.cyan : Theme.comment
            MouseArea {
                id: navR
                anchors.fill: parent
                anchors.margins: -8
                hoverEnabled: true
                onClicked: root.monthShift(1)
            }
        }
    }

    // ---- day grid
    Grid {
        id: grid
        anchors.horizontalCenter: parent.horizontalCenter
        columns: 7
        spacing: 2

        Repeater {
            model: ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
            delegate: Item {
                required property int index
                required property string modelData
                width: 34
                height: 20
                BarText {
                    anchors.centerIn: parent
                    text: parent.modelData
                    font.pixelSize: 11
                    color: (index === 0 || index === 6) ? Theme.orange : Theme.comment
                }
            }
        }

        Repeater {
            model: {
                const y = root.shown.getFullYear()
                const m = root.shown.getMonth()
                const first = new Date(y, m, 1)
                const start = new Date(y, m, 1 - first.getDay())
                const today = new Date()
                const cells = []
                for (let i = 0; i < 42; i++) {
                    const d = new Date(start)
                    d.setDate(start.getDate() + i)
                    cells.push({
                        day: d.getDate(),
                        weekend: d.getDay() === 0 || d.getDay() === 6,
                        inMonth: d.getMonth() === m,
                        today: d.getFullYear() === today.getFullYear()
                            && d.getMonth() === today.getMonth()
                            && d.getDate() === today.getDate()
                    })
                }
                return cells
            }

            delegate: Rectangle {
                id: cell
                required property var modelData
                width: 34
                height: 28
                radius: 8
                color: modelData.today ? Theme.accent
                     : cellM.containsMouse ? Theme.hover
                     : "transparent"

                BarText {
                    anchors.centerIn: parent
                    text: String(cell.modelData.day)
                    font.pixelSize: 12
                    // today's number sits on an accent fill — the theme
                    // background gives contrast on dark and light themes alike
                    color: cell.modelData.today ? Theme.bg
                         : !cell.modelData.inMonth ? Qt.rgba(Theme.comment.r, Theme.comment.g, Theme.comment.b, 0.33)
                         : cell.modelData.weekend ? Theme.orange
                         : Theme.fg
                }

                MouseArea {
                    id: cellM
                    anchors.fill: parent
                    hoverEnabled: true
                }
            }
        }
    }
}
