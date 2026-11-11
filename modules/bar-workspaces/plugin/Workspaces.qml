// Workspace indicators, hyprconf style — a replacement for Omarchy's own
// omarchy.workspaces bar widget. moduleName stays the built-in id, and
// manifest.json's clonedFrom is what maps this widget onto the stock one's
// bar slot — the shell swaps it in on enable and puts the stock widget back
// on disable (shell/services/PluginRegistry.qml:561-566, :587 ->
// restoreCloneSource:460-484).
//
// Taken from stock (shell/plugins/bar/widgets/Workspaces.qml, Omarchy
// 4.5.0-3; NOTICE): which monitor this bar is on, that monitor's block of
// ten workspace ids, the click, and the refresh Quickshell needs — everything
// down to the Connections block, as upstream has it but for workspaceIds().
// Three things differ:
//   * Only workspaces that EXIST are shown — occupied ones plus the one the
//     monitor shows, which Hyprland always keeps alive. Stock always draws
//     pills 1-5 and reads no settings at all (`omarchy bar set
//     omarchy.workspaces …` has no key that changes this), so a replacement
//     is the only seam.
//   * Two stacked lines, like hyprconf.resources beside it: Omarchy's bar is
//     26px and one caption-size line uses about half of it, so the second
//     line is vertical space already paid for — spending it halves the width
//     the widget takes.
//   * The workspace the monitor shows is drawn as hyprconf's Pac-Man
//     (nf-md-pac_man, U+F0BAF) instead of stock's layout glyph, so nothing
//     here reads or cycles the layout, and the wheel does nothing.
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "omarchy.workspaces"

  // Every monitor has workspaces 1-10 of its own, which Hyprland numbers in a
  // block of ten per monitor: 1-10, 11-20, and so on (see
  // default/hypr/monitor-workspaces.lua). Each bar shows its own monitor's block,
  // numbered 1-10, and the one that monitor shows, whichever monitor has focus.
  readonly property int slots: 10

  readonly property var monitor: {
    var window = root.QsWindow.window
    var screen = window ? window.screen : null
    return screen ? Hyprland.monitorFor(screen) : Hyprland.focusedMonitor
  }
  readonly property string monitorName: root.monitor ? root.monitor.name : ""

  // Connector -> block, from the file Hyprland keeps them in.
  property var blocks: ({})

  function readBlocks(text) {
    var next = {}
    var lines = String(text || "").split("\n")
    for (var i = 0; i < lines.length; i++) {
      var fields = lines[i].split("\t")
      if (fields.length >= 3 && fields[1] !== "") next[fields[1]] = parseInt(fields[0], 10)
    }
    root.blocks = next
  }

  FileView {
    path: (Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state") + "/omarchy/monitor-workspaces"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.readBlocks(text())
    onLoadFailed: root.readBlocks("")
  }

  function blockOf(id) {
    return Math.floor((id - 1) / root.slots)
  }

  function slotOf(id) {
    return (id - 1) % root.slots + 1
  }

  function activeWorkspaceId() {
    return root.monitor && root.monitor.activeWorkspace ? root.monitor.activeWorkspace.id : -1
  }

  // Until Hyprland has written the file, the workspace a monitor shows is in
  // its own block.
  readonly property int block: {
    var block = root.blocks[root.monitorName]
    if (block !== undefined) return block
    var active = root.activeWorkspaceId()
    return active > 0 ? root.blockOf(active) : 0
  }

  // The monitor's own that exist, ascending. After them come workspaces that
  // are only visiting: those of a monitor that is unplugged, which had no room
  // to join this one's. id < 0 is a special workspace (scratchpad) and is
  // never listed, as in stock.
  function workspaceIds() {
    var ids = []
    var guests = []
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id <= 0) continue
      if (root.blockOf(id) === root.block) {
        if (ids.indexOf(id) === -1) ids.push(id)
      } else if (values[i].monitor && values[i].monitor.name === root.monitorName) {
        guests.push(id)
      }
    }

    ids.sort(function(left, right) { return left - right })
    guests.sort(function(left, right) { return left - right })
    return ids.concat(guests)
  }

  function dispatch(expression) {
    if (root.bar) root.bar.run("hyprctl dispatch " + Util.shellQuote(expression))
  }

  function focusWorkspace(id) {
    if (root.blockOf(id) === root.block) {
      root.dispatch("o.workspaces.focus(" + root.slotOf(id) + ", \"" + root.monitorName + "\")")
    } else {
      root.dispatch("hl.dsp.focus({ workspace = \"" + id + "\" })")
    }
  }

  Connections {
    target: Hyprland
    function onRawEvent(event) {
      var name = event ? String(event.name) : ""
      // Quickshell credits every workspace switch to the focused monitor, as
      // the event doesn't say which one switched, and misses the workspace a
      // monitor falls back to when its own is moved away. Moving workspaces
      // between monitors switches the others, so ask Hyprland for the truth.
      // A workspace that changes number is only learned by asking too. Every
      // bar shares what Hyprland answers, so one asks after a plain switch.
      var switched = name === "workspacev2" && root.monitor !== null && root.monitor.focused
      if (switched || name === "moveworkspacev2" || name === "changeworkspaceid") {
        Hyprland.refreshMonitors()
        Hyprland.refreshWorkspaces()
      }
    }
  }

  // Bound to a function that reads Hyprland.workspaces.values, so it
  // re-evaluates live as workspaces come and go (stock binds the same way).
  readonly property var ids: workspaceIds()

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
    columnSpacing: Style.spacing.sm
    horizontalItemAlignment: Grid.AlignHCenter

    Repeater {
      model: root.ids

      Text {
        id: pill
        required property int modelData

        text: root.activeWorkspaceId() === modelData ? "\u{F0BAF}" : String(root.slotOf(modelData))
        textFormat: Text.PlainText
        // The bar's own foreground and font, as every stock text widget uses
        // (WidgetButton binds the same two), so themes and `omarchy font set`
        // apply here too.
        color: root.bar ? root.bar.barForeground : Commons.Color.foreground
        font.family: root.bar ? root.bar.fontFamily : Style.fontFamily
        font.pixelSize: Style.font.caption
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
