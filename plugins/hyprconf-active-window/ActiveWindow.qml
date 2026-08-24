// The focused window's title on TWO lines — a replacement for Omarchy's own
// omarchy.active-window bar widget. manifest.json names it as clonedFrom that
// widget, so the shell swaps this copy into the stock widget's slot and routes
// the stock IPC here, exactly the way an `omarchy plugin clone` copy is
// treated (shell/services/PluginRegistry.qml, Omarchy 4.0.0-1). `omarchy
// plugin disable hyprconf.active-window` puts the stock widget back.
//
// Everything else is the stock widget's behaviour (shell/plugins/bar/widgets/
// ActiveWindow.qml): title or app id, hidden when nothing is focused or the
// bar is vertical, the full title as a tooltip, left-click focuses, middle-
// or right-click closes. The one difference: the same CHARACTER budget the
// stock widget spends on one body-size line (its `maxWidth` setting, 280 px
// by default) is laid out on two caption-size lines, so the widget takes
// about half the horizontal space. Two lines of caption text fit a 26 px bar
// only with the line box at the glyph box (lineHeight 1.0), the way the
// other two-line widgets in this overlay do it.
//
// moduleName stays "omarchy.active-window" on purpose: built-in ids inside
// plugin code are stable IPC targets, and the manifest's clonedFrom is what
// maps this copy onto them — the same rule omarchy-plugin-clone follows.
import QtQuick
import Quickshell.Wayland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.active-window"

  readonly property var toplevel: ToplevelManager.activeToplevel
  readonly property string title: toplevel ? (toplevel.title || toplevel.appId || "") : ""

  // The stock budget: `maxWidth` px of body-size text on one line, set with
  // `omarchy bar set hyprconf.active-window maxWidth N`. The same number of
  // characters at caption size over two lines needs maxWidth × caption/body
  // ÷ 2 px per line.
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
