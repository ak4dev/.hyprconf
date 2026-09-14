// The focused window's title on TWO lines, a clonedFrom copy of Omarchy's own
// omarchy.active-window widget (README.md beside this file has the behaviour
// and the setting; NOTICE carries Omarchy's MIT notice, which every copy of
// its code must). Deltas from the stock widget, and all of them
// (shell/plugins/bar/widgets/ActiveWindow.qml, Omarchy 4.0.3-1):
//   1. the stock character budget laid out on two caption-size lines
//      (lineWidth, wrapMode, maximumLineCount, lineHeight 1.0 — two caption
//      lines fit a 26 px bar only with the line box at the glyph box);
//   2. implicitWidth off contentWidth, the widest painted line, so a short
//      title takes only the room it needs (stock: Math.min of maxLabelWidth
//      and implicitWidth, one line);
//   3. the stock widget's two identical close branches (:53-57) merged into
//      one `||` — source only, same behaviour; re-apply it deliberately.
// moduleName stays "omarchy.active-window": built-in ids inside plugin code
// are stable IPC targets, and the manifest's clonedFrom is what maps this
// copy onto them — the rule omarchy-plugin-clone follows.
//
// Refresh, when an Omarchy release changes the widget (nothing here is
// parity-tested — the clock's test is the clock's): diff the stock file
// against this one, re-apply the three deltas above, bump manifest.json.
import QtQuick
import Quickshell.Wayland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.active-window"

  readonly property var toplevel: ToplevelManager.activeToplevel
  readonly property string title: toplevel ? (toplevel.title || toplevel.appId || "") : ""

  // The stock budget is `maxWidth` px of body-size text on one line (README ›
  // Settings). The same number of characters at caption size over two lines
  // needs maxWidth × caption/body ÷ 2 px per line.
  readonly property int maxLabelWidth: Number(setting("maxWidth", 280))
  readonly property real lineWidth: Math.max(
    24, Math.round(maxLabelWidth * Style.font.caption / Style.font.body / 2))
  readonly property real lineHeightScale: 1.0

  visible: title !== "" && !vertical
  // contentWidth is the widest painted line, so a short title takes only the
  // room it needs while a long one stops at lineWidth (and elides).
  implicitWidth: visible ? Math.ceil(labelText.contentWidth) + Style.spacing.controlPaddingX * 2 : 0
  implicitHeight: barSize

  Behavior on implicitWidth {
    NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
  }

  Item {
    anchors.fill: parent
    anchors.leftMargin: Style.space(8)
    anchors.rightMargin: Style.space(8)
    clip: true

    Text {
      id: labelText
      anchors.verticalCenter: parent.verticalCenter
      anchors.left: parent.left
      width: root.lineWidth
      text: root.title
      textFormat: Text.PlainText
      color: root.bar ? root.bar.barForeground : Color.foreground
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
      maximumLineCount: 2
      elide: Text.ElideRight
      lineHeight: root.lineHeightScale
      lineHeightMode: Text.ProportionalHeight
      opacity: 0.85
    }
  }

  MouseArea {
    anchors.fill: parent
    hoverEnabled: true
    acceptedButtons: Qt.LeftButton | Qt.MiddleButton | Qt.RightButton
    cursorShape: Qt.PointingHandCursor

    onClicked: function(mouse) {
      if (!root.toplevel) return
      if (mouse.button === Qt.MiddleButton || mouse.button === Qt.RightButton) {
        root.toplevel.close()
      } else {
        root.toplevel.activate()
      }
    }
    onEntered: if (root.bar) root.bar.showTooltip(root, root.title)
    onExited: if (root.bar) root.bar.hideTooltip(root)
  }
}
