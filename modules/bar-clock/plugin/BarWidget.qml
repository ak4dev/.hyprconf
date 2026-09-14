// hyprconf.clock — Omarchy's own clock widget, ticking seconds.
//
// A copy of Omarchy 4.0.2-1's shell/plugins/panels/clock/BarWidget.qml with
// exactly three deltas and nothing else, so it behaves as the stock widget
// does (the calendar on click, right-click cycles the format, middle-click
// the timezone picker, the same shell.json settings):
//   1. `precision: SystemClock.Seconds` — stock samples at Minutes, so a
//      seconds format would sit frozen 59 s of every minute (a `precision`
//      setting on omarchy.clock would delete this plugin).
//   2. the calendar panel is loaded from the RUNNING Omarchy's own
//      Panel.qml ($OMARCHY_PATH/shell/plugins/panels/clock/Panel.qml — the
//      way Omarchy's plugins find their tree, Clipboard.qml's omarchyPath)
//      instead of a copy beside this file: a QML document resolves an
//      `import "Model.js"` against its own directory, so that panel reads
//      Omarchy's Model.js and the copy beside THIS file (the static import
//      below) carries only the label-format functions this widget calls.
//   3. injectPanel() forwards this widget's moduleName to that panel, whose
//      own is the literal "omarchy.clock" (its line 19) — the id its
//      persistSettings() hands to updateEntryInline(). Omarchy 4.0.3-1
//      routes that call itself: the panel's `bar.shell` is a
//      PluginShellApi whose _updateSettings resolves the requested id
//      through resolveEnabledId (shell.qml:648-649,
//      PluginRegistry.qml:171-182), so "omarchy.clock" lands on the enabled
//      clone. The forward is kept as a back-compat shim for pre-4.0.3
//      installs, where the literal id matched no live entry and a week
//      start or birth year set from the calendar redrew but was never
//      written; onModuleNameChanged makes the ordering explicit for a
//      moduleName that arrives after the panel loads.
// manifest.json names it clonedFrom omarchy.clock, so the shell swaps it
// into the stock widget's slot and routes the stock IPC target here
// (shell/services/PluginRegistry.qml, setEnabled / resolveEnabledId).
//
// Refresh, when an Omarchy release changes the clock (the parity test in
// ../test_bar_clock.py turns red on a box with that release): copy the stock
// BarWidget.qml over this one and re-apply the three deltas above, and take
// Model.js's kept functions from the stock file again (its header names the
// subset). NOTICE carries Omarchy's MIT notice, which every copy of its code
// must.
import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

// Date/time label for the bar, and the host for the calendar popup.
//
// Left click reveals the calendar — asking "what is the date?" is what a
// click on a clock means — right click walks the common label formats, and
// middle click opens the timezone picker.
BarWidget {
  id: root
  moduleName: "omarchy.clock"

  property date displayDate: clock.date

  readonly property string configuredFormat: vertical
    ? setting("verticalFormat", "HH\n—\nmm")
    : setting("format", "dddd HH:mm")
  readonly property string configuredAltFormat: vertical
    ? setting("verticalFormatAlt", "dd\nMMM\n'W'ww\n''yy")
    : setting("formatAlt", "d MMMM 'W'ww yyyy")

  readonly property var formatRing: Model.clockFormatRing(configuredFormat, configuredAltFormat, Model.clockFormats(vertical))

  // What the bar shows is what shell.json stores, so a cycled format is the
  // format from then on rather than something that reverts on restart.
  readonly property string activeFormat: configuredFormat
  readonly property string displayText: formatted(displayDate)
  readonly property var verticalLines: displayText.split("\n")

  function refresh() {
    displayDate = new Date()
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function cycleFormat() {
    var current = String(configuredFormat)
    var next = Model.nextClockFormat(formatRing, current)
    if (next === "" || next === current) return

    var entry = { id: root.moduleName }
    for (var key in root.settings) if (key !== "id") entry[key] = root.settings[key]
    entry[vertical ? "verticalFormat" : "format"] = next

    // Applied locally first so the label changes on the click itself; the
    // shell.json write comes back through the bar as the same value.
    root.settings = entry
    if (root.bar && root.bar.shell && typeof root.bar.shell.updateEntryInline === "function")
      root.bar.shell.updateEntryInline(root.moduleName, entry)
  }

  function formatted(date) {
    return Qt.formatDateTime(date, activeFormat.replace(/ww/g, Model.isoWeekLiteral(date.getFullYear(), date.getMonth(), date.getDate())))
  }

  // ---- Calendar popup. Shape contract for shell.summon/hide/toggle
  //      routing: Bar.findPanelWidget requires open/close/opened on the
  //      bar-widget root.
  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false

  function open() {
    if (panelLoader.item) panelLoader.item.open()
  }

  function close() {
    if (panelLoader.item) panelLoader.item.close()
  }

  function togglePanel() {
    if (panelLoader.item) panelLoader.item.toggle()
  }

  function toggleWeekStart() {
    if (panelLoader.item) panelLoader.item.toggleWeekStart()
  }

  // The clock fills more slot than it paints a mark for, at both
  // orientations: horizontally it is a text label in a padded slot, so the
  // dot takes the label width; vertically it is a stack of icon-sized lines,
  // so the dot takes one line — the same mark every icon widget gets, rather
  // than a rule running the height of the whole stack.
  readonly property real openPanelIndicatorWidth: button.labelWidth
  readonly property real openPanelIndicatorHeight: Math.max(Style.space(10), Math.round(Style.bar.iconSlot * 0.55))

  // Forwarded so this widget can stand in for the panel as the bar's popout
  // identity: Bar.requestPopout prefers closeForPopoutSwitch over close, and
  // KeyboardPanel reads popoutSwitchClosing back off its owner.
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("moduleName" in target) target.moduleName = root.moduleName
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onModuleNameChanged: injectPanel()
  onSettingsChanged: injectPanel()

  SystemClock {
    id: clock
    precision: SystemClock.Seconds
    onDateChanged: root.displayDate = date
  }

  Loader {
    id: panelLoader
    active: true
    source: "file://" + Quickshell.env("OMARCHY_PATH") + "/shell/plugins/panels/clock/Panel.qml"
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  IpcHandler {
    target: "omarchy.clock"

    function refresh(): void { root.broadcast("refresh") }
    function cycleFormat(): void { root.cycleFormat() }
    function toggleWeekStart(): void { root.toggleWeekStart() }
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.togglePanel() }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.vertical ? "" : root.displayText
    labelVisible: !root.vertical
    hasVisualContent: root.vertical ? root.verticalLines.length > 0 : text !== ""
    fixedHeight: root.vertical ? root.verticalLines.length * Style.bar.iconSlot : -1
    horizontalMargin: 8.75
    verticalPadding: 8.75

    onPressed: function(b) {
      if (b === Qt.RightButton) root.cycleFormat()
      else if (b === Qt.MiddleButton) { if (root.bar) root.bar.run("omarchy-menu-timezone") }
      else root.togglePanel()
    }

    Column {
      visible: root.vertical
      anchors.fill: parent

      Repeater {
        model: root.verticalLines

        OpticalGlyph {
          required property string modelData
          width: button.width
          height: Style.bar.iconSlot
          text: modelData
          fontFamily: button.fontFamily
          fontSize: modelData.length > 3
            ? button.fontSize * 0.9
            : button.fontSize
          color: button.foreground
        }
      }
    }
  }
}
