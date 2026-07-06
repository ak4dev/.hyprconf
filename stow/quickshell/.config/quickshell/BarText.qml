import QtQuick

// Shared text style. PlainText is a hard requirement: window titles, MPRIS
// metadata, and tray menu labels are externally controlled strings and must
// never be parsed as rich text.
Text {
    font.family: Theme.font
    font.pixelSize: Theme.fontSize
    color: Theme.fg
    textFormat: Text.PlainText
}
