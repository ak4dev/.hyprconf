pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Live palette sourced from hyprconf's theme switcher, the same source of
// truth waybar/kitty/dunst use: the active theme name in
// ~/.config/hypr/.current-theme selects a themes/<name>.json whose keys
// (background, foreground, comment, accent, cyan, green, red, orange,
// purple) drive the bar. Colors not present in the theme schema (yellow,
// pink) keep static fallbacks — matching waybar, which leaves them fixed.
// Switching themes updates the files on disk and this repaints live.
Singleton {
    id: theme

    readonly property string home: Quickshell.env("HOME")

    FileView {
        id: nameFile
        path: theme.home + "/.config/hypr/.current-theme"
        watchChanges: true
        blockLoading: true
        onFileChanged: reload()
    }

    readonly property string themeName: nameFile.text().trim()

    FileView {
        id: paletteFile
        path: theme.themeName === ""
            ? ""
            : theme.home + "/.config/hypr/scripts/theme-switcher/themes/" + theme.themeName + ".json"
        watchChanges: true
        blockLoading: true
        onFileChanged: reload()
    }

    readonly property var pal: {
        const t = paletteFile.text()
        if (!t)
            return ({})
        try {
            return JSON.parse(t)
        } catch (e) {
            return ({})
        }
    }

    // themed from the JSON (gruvbox-material-dark values as fallback)
    readonly property color bg: pal.background ?? "#282828"
    readonly property color fg: pal.foreground ?? "#d4be98"
    readonly property color comment: pal.comment ?? "#928374"
    readonly property color accent: pal.accent ?? "#ea6962"
    readonly property color cyan: pal.cyan ?? "#89b482"
    readonly property color green: pal.green ?? "#a9b665"
    readonly property color orange: pal.orange ?? "#e78a4e"
    readonly property color red: pal.red ?? "#ea6962"
    readonly property color purple: pal.purple ?? "#d3869b"
    // not in the theme schema — static, like waybar
    readonly property color yellow: pal.yellow ?? "#ffd700"
    readonly property color pink: pal.pink ?? "#ff69b4"

    // derived translucent tokens (waybar uses background @ 0.8)
    readonly property color bgAlpha: Qt.rgba(bg.r, bg.g, bg.b, 0.8)
    readonly property color surface: Qt.rgba(bg.r, bg.g, bg.b, 0.78)
    readonly property color divider: Qt.rgba(fg.r, fg.g, fg.b, 0.10)
    readonly property color hover: Qt.rgba(cyan.r, cyan.g, cyan.b, 0.20)
    readonly property color purpleAlpha: Qt.rgba(purple.r, purple.g, purple.b, 0.22)
    readonly property color cyanAlpha: Qt.rgba(cyan.r, cyan.g, cyan.b, 0.20)
    readonly property color shadow: "#66000000"

    readonly property string font: "JetBrainsMono Nerd Font"
    readonly property int fontSize: 14

    readonly property int radius: 12
    readonly property int animFast: 140
    readonly property int animSlow: 220
}
