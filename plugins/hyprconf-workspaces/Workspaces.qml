// Workspace indicators, hyprconf style — a replacement for Omarchy's own
// omarchy.workspaces bar widget. manifest.json names it as clonedFrom that
// widget, so the shell swaps this copy into the stock widget's slot and
// routes the stock IPC here, exactly the way an `omarchy plugin clone` copy is
// treated (shell/services/PluginRegistry.qml, Omarchy 4.0.0-1). `omarchy
// plugin disable hyprconf.workspaces` puts the stock widget back.
//
// Three things differ from stock (shell/plugins/bar/widgets/Workspaces.qml):
//   * Only workspaces that EXIST are shown — occupied ones plus the focused
//     one, which Hyprland always keeps alive. Stock hardcodes pills 1-5
//     whether they exist or not, caps ids at 10, and reads no settings at all
//     (`omarchy bar set
//     omarchy.workspaces …` has no key that changes this), so a copy is the
//     only seam.
//   * Two stacked lines, like hyprconf.resources beside it: Omarchy's bar is
//     26px and one caption-size line uses about half of it, so the second
//     line is vertical space already paid for — spending it halves the width
//     the widget takes.
//   * The focused workspace is drawn as hyprconf's Pac-Man (nf-md-pac_man,
//     U+F0BAF) instead of stock's dot.
//
// moduleName stays "omarchy.workspaces" on purpose: built-in ids inside plugin
// code are stable IPC targets, and the manifest's clonedFrom is what maps this
// copy onto them — the same rule omarchy-plugin-clone itself follows.
import QtQuick
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.workspaces"

  // Every real workspace Hyprland currently has, ascending. id < 0 is a
  // special workspace (scratchpad) and is never listed, as in stock.
  function workspaceIds() {
    var ids = []
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 0 && ids.indexOf(id) === -1) ids.push(id)
    }
    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function focusWorkspace(id) {
    if (!root.bar) return
    root.bar.run("hyprctl dispatch " + Util.shellQuote("hl.dsp.focus({ workspace = \"" + id + "\" })"))
  }

  // Bound to a function that reads Hyprland.workspaces.values, so it
  // re-evaluates live as workspaces come and go (stock binds the same way).
  readonly property var ids: workspaceIds()

  // Two lines of text in a 26px bar only fit if the line box is the glyph box:
  // Qt's default proportional line height adds ~20% leading per line, which at
  // caption size overflows the bar and clips the second line.
  readonly property real lineHeightScale: 1.0
  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)

  // NEVER size this off `parent`: the bar's ModuleSlot takes its height from
  // the widget's implicit size, so `parent.height` closes a binding loop that
  // QML resolves by dropping the binding — a zero-height, invisible widget.
  implicitWidth: grid.implicitWidth + trailingGap
  implicitHeight: grid.implicitHeight

  Grid {
    id: grid
    anchors.verticalCenter: parent.verticalCenter
    // Row-major, two rows — "1 2 3" over "4 5 6" — so it reads like two lines
    // of text, the way hyprconf.resources does. A side rail (vertical bar)
    // stacks everything in one column instead, like the stock widget.
    columns: root.vertical ? 1 : Math.max(1, Math.ceil(root.ids.length / 2))
    rowSpacing: 0
    columnSpacing: Style.spacing.sm
    flow: Grid.LeftToRight
    horizontalItemAlignment: Grid.AlignHCenter

    Repeater {
      model: root.ids

      Text {
        id: pill
        required property int modelData
        readonly property bool focused: Hyprland.focusedWorkspace !== null && Hyprland.focusedWorkspace.id === modelData

        text: focused ? "\u{F0BAF}" : String(modelData)
        // The bar's own foreground and font, as every stock text widget uses
        // (WidgetButton binds the same two), so themes and `omarchy font set`
        // apply here too.
        color: root.bar ? root.bar.barForeground : Color.foreground
        font.family: root.bar ? root.bar.fontFamily : Style.fontFamily
        font.pixelSize: Style.font.caption
        lineHeight: root.lineHeightScale
        lineHeightMode: Text.ProportionalHeight
        horizontalAlignment: Text.AlignHCenter
        renderType: Text.NativeRendering

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: root.focusWorkspace(pill.modelData)
        }
      }
    }
  }
}
