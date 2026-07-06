pragma Singleton
import QtQuick

// Mirror of waybar.css @define-color palette.
QtObject {
    readonly property color bgAlpha: "#cc282828"      // rgba(40,40,40,0.8)
    readonly property color fg: "#d4be98"
    readonly property color comment: "#928374"
    readonly property color accent: "#ea6962"
    readonly property color cyan: "#89b482"
    readonly property color green: "#a9b665"
    readonly property color orange: "#e78a4e"
    readonly property color pink: "#ff69b4"
    readonly property color purple: "#d3869b"
    readonly property color purpleAlpha: "#33c4a7e7"  // rgba(196,167,231,0.2)
    readonly property color cyanAlpha: "#339ccfd8"    // rgba(156,207,216,0.2)
    readonly property color red: "#ea6962"
    readonly property color yellow: "#ffd700"

    readonly property string font: "JetBrainsMono Nerd Font"
    readonly property int fontSize: 14
}
