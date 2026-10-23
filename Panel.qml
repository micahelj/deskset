import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

Panel {
  id: root
  moduleName: "sonic.apex"
  ipcTarget: "sonic.apex"
  manageIpc: true

  property var status: ({
    device: "Apex",
    short: "Apex",
    rgb: { mode: "theme", brightness: 80, speed: 45, solid: "#89b4fa" },
    oled: { page: "clock" },
    wheel: { mode: "volume" },
    openrgb: false,
    daemon: false
  })

  readonly property var rgbModes: ["theme", "solid", "gradient", "wave", "breathe", "rainbow", "reactive", "off"]
  readonly property var animatedModes: ["gradient", "wave", "breathe", "rainbow"]
  // Mirrors rgb.PROFILES, so each profile can be drawn as its gradient.
  readonly property var rgbProfiles: [
    { name: "sunset", colors: ["#f97316", "#ec4899", "#8b5cf6"] },
    { name: "ocean", colors: ["#0ea5e9", "#06b6d4", "#14b8a6"] },
    { name: "fire", colors: ["#facc15", "#f97316", "#dc2626"] },
    { name: "matrix", colors: ["#166534", "#22c55e", "#86efac"] },
    { name: "cyberpunk", colors: ["#22d3ee", "#e879f9", "#a21caf"] },
    { name: "aurora", colors: ["#34d399", "#22d3ee", "#818cf8"] },
    { name: "candy", colors: ["#f472b6", "#c084fc", "#60a5fa"] },
    { name: "ice", colors: ["#e0f2fe", "#7dd3fc", "#38bdf8"] },
    { name: "vaporwave", colors: ["#ff71ce", "#01cdfe", "#05ffa1"] },
    { name: "gold", colors: ["#fef08a", "#f59e0b", "#78350f"] }
  ]
  readonly property var rainbow: ["#ff0040", "#ffb000", "#40ff00", "#00e0ff", "#4040ff", "#ff00c0"]
  readonly property var oledPages: ["clock", "now-playing", "workspace", "logo", "text", "claude", "system", "gpu", "clear"]
  readonly property var wheelModes: ["volume", "app", "workspace", "brightness", "oled", "rgb"]
  readonly property var mouseModes: ["match", "solid", "breathe", "cycle", "off", "device"]
  readonly property var mouseModeLabels: ({ match: "match keyboard", device: "hands off" })
  // Saturated on purpose: LEDs wash pastels toward white.
  readonly property var colorPresets: [
    { label: "violet", color: "#4A1C90" },
    { label: "teal", color: "#00806A" },
    { label: "ice", color: "#7DD3FC" },
    { label: "green", color: "#00FF40" },
    { label: "magenta", color: "#FF00C8" },
    { label: "orange", color: "#FF3C00" },
    { label: "yellow", color: "#FFC800" },
    { label: "white", color: "#FFFFFF" }
  ]
  readonly property var tabs: [
    { value: "favorites", label: "Favorites", icon: "󰓎" },
    { value: "mouse", label: "Mouse", icon: "󰍽" },
    { value: "keyboard", label: "Keyboard", icon: "󰌌" }
  ]

  property string tab: "favorites"

  readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace("file://", "").replace(/\/$/, "")
  readonly property string scriptDir: pluginDir + "/bin"
  readonly property string apexctl: scriptDir + "/apexctl"

  readonly property var rgb: root.status.rgb || ({})
  readonly property var mouse: root.status.mouse || null
  readonly property bool mousePresent: !!(root.mouse && root.mouse.present)
  readonly property color ink: root.bar.foreground

  property var queue: []

  function apex(args) {
    // Commands run one at a time, in order, so no click is ever dropped (a
    // preset sends two).
    if (actionProc.running) {
      root.queue = root.queue.concat([args])
      return
    }
    actionProc.command = [root.apexctl].concat(args)
    actionProc.running = true
  }

  function refresh() {
    if (!statusProc.running) statusProc.running = true
  }

  // Unset mouse brightness follows the keyboard in match mode.
  function mouseBrightness() {
    var m = root.mouse || {}
    if (m.brightness !== null && m.brightness !== undefined) return Number(m.brightness)
    return m.mode === "match" ? Number(root.rgb.brightness || 80) : 100
  }

  function setBrightnessBoth(value) {
    root.apex(["rgb", "-b", String(value)])
    if (root.mouse && root.mouse.brightness !== null && root.mouse.brightness !== undefined)
      root.apex(["mouse", "-b", String(value)])
  }

  function applyPreset(hex) {
    root.apex(["rgb", "-c", hex])
    if (root.mouse && root.mouse.mode !== "match") root.apex(["mouse", "match"])
  }

  function setMouseColor(hex) {
    var mode = root.mouse && (root.mouse.mode === "breathe") ? "breathe" : "solid"
    root.apex(["mouse", mode, "-c", hex])
  }

  function sameColor(a, b) {
    return String(a || "").toUpperCase() === String(b || "").toUpperCase()
  }

  function pretty(value) {
    if (!value) return ""
    return String(value).replace(/-/g, " ")
  }

  function batteryText(b) {
    if (!b) return ""
    if (b.full) return "󰂅 " + b.percent + "%"
    if (b.charging) return "󰂄 " + b.percent + "%"
    var icons = ["󰂎", "󰁺", "󰁻", "󰁼", "󰁽", "󰁾", "󰁿", "󰂀", "󰂁", "󰂂", "󰁹"]
    return icons[Math.round(b.percent / 10)] + " " + b.percent + "%"
  }

  // Scroll the panel from a child that swallowed the wheel (sliders).
  function scrollPanel(dy) {
    var f = scrollArea.contentItem
    if (!f || f.contentHeight <= f.height) return
    f.contentY = Math.max(0, Math.min(f.contentHeight - f.height, f.contentY - dy))
  }

  // ── Favorites ──────────────────────────────────────────────────────
  property bool editingFavorites: false
  readonly property var defaultFavorites: ({
    sections: ["brightness", "lighting", "dpi", "oled", "wheel"],
    colors: ["theme", "#4A1C90", "#00806A", "#7DD3FC", "#00FF40", "#FF00C8", "#FF3C00", "#FFC800", "#FFFFFF", "rainbow"],
    dpi: [400, 800, 1600, 3200, 6400],
    oled: ["clock", "system", "claude", "now-playing"],
    wheel: ["volume", "app", "workspace"]
  })
  readonly property var fav: root.status.favorites || root.defaultFavorites
  readonly property var favoriteSections: [
    { value: "brightness", label: "brightness" },
    { value: "lighting", label: "lighting" },
    { value: "dpi", label: "mouse DPI" },
    { value: "oled", label: "OLED" },
    { value: "wheel", label: "wheel" }
  ]
  readonly property var dpiChoices: [400, 800, 1000, 1200, 1600, 2400, 3200, 4800, 6400, 12800]

  function favHas(key, value) {
    var list = root.fav[key] || []
    for (var i = 0; i < list.length; i++)
      if (String(list[i]).toUpperCase() === String(value).toUpperCase()) return true
    return false
  }

  // Switch a section back on (Sections, in edit mode) to edit what it offers.
  function favShows(section) {
    return root.favHas("sections", section)
  }

  function favSet(key, list) {
    root.apex(["favorites", "--" + key, list.join(",")])
  }

  function favToggle(key, value) {
    var list = (root.fav[key] || []).slice()
    if (root.favHas(key, value))
      list = list.filter(v => String(v).toUpperCase() !== String(value).toUpperCase())
    else
      list.push(value)
    root.favSet(key, list)
  }

  function colorCandidates() {
    var out = ["theme"].concat(root.colorPresets.map(p => p.color), ["rainbow"])
    var extra = (root.fav.colors || []).filter(c => out.every(o => String(o).toUpperCase() !== String(c).toUpperCase()))
    return out.concat(extra)
  }

  function dpiCandidates() {
    var all = root.dpiChoices.concat((root.fav.dpi || []).filter(d => root.dpiChoices.indexOf(d) < 0))
    return all.sort((a, b) => a - b)
  }

  function colorLabel(value) {
    if (value === "theme" || value === "rainbow") return value
    for (var i = 0; i < root.colorPresets.length; i++)
      if (root.sameColor(root.colorPresets[i].color, value)) return root.colorPresets[i].label
    return String(value).toLowerCase()
  }

  function colorIsCurrent(value) {
    if (value === "theme") return root.rgb.mode === "theme"
    if (value === "rainbow") return root.rgb.mode === "rainbow"
    return root.rgb.mode === "solid" && root.sameColor(root.rgb.solid, value)
  }

  function applyFavoriteColor(value) {
    if (value === "rainbow") {
      root.apex(["rgb", "rainbow"])
      return
    }
    if (value === "theme") root.apex(["rgb", "theme"])
    else root.apex(["rgb", "-c", value])
    if (root.mouse && root.mouse.mode !== "match") root.apex(["mouse", "match"])
  }

  function addFavoriteColor() {
    var text = newColor.text.trim()
    if (text.charAt(0) !== "#") text = "#" + text
    if (!/^#[0-9a-fA-F]{6}$/.test(text)) return
    if (!root.favHas("colors", text)) root.favSet("colors", (root.fav.colors || []).concat([text.toUpperCase()]))
    newColor.text = ""
  }

  function addFavoriteDpi() {
    var value = parseInt(newDpi.text, 10)
    if (!(value >= 50 && value <= 64000)) return
    if (!root.favHas("dpi", value)) root.favSet("dpi", (root.fav.dpi || []).concat([value]))
    newDpi.text = ""
  }

  // ── Mouse buttons ──────────────────────────────────────────────────
  property int hotSlot: -1  // hovered row or marker
  property bool identifyRequested: false
  readonly property var identify: root.mouse && root.mouse.identify || ({})
  readonly property bool identifyActive: root.identifyRequested || !!root.identify.active
  readonly property int identifiedSlot: root.identify.slot === null || root.identify.slot === undefined ? -1 : root.identify.slot

  function startIdentify() {
    root.identifyRequested = true
    identifyGiveUp.restart()
    root.apex(["mouse", "--identify-start"])
  }

  // Never stay on "Press a mouse button…" if the daemon could not start.
  Timer {
    id: identifyGiveUp
    interval: 12000
    onTriggered: root.identifyRequested = false
  }

  // Installing adds a user service, hooks and a ~/.local/bin link, so it only
  // runs when asked from the panel, never on load.
  function setup() {
    if (!installProc.running) installProc.running = true
  }

  // `quickshell ipc -p /usr/share/omarchy/shell call deskset tab mouse` opens a tab.
  IpcHandler {
    target: "deskset"
    function tab(name: string): void {
      if (root.tabs.some(t => t.value === name)) root.tab = name
      root.open()
    }
    function editFavorites(): void {
      root.tab = "favorites"
      root.editingFavorites = true
      root.open()
    }
  }

  Component.onCompleted: root.refresh()
  onOpenedChanged: if (opened) root.refresh()

  Timer {
    interval: 2500
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Timer {
    interval: 250
    running: root.opened && (root.identifyActive || root.identifiedSlot >= 0)
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: installProc
    command: ["bash", root.pluginDir + "/install", "--silent"]
    stdout: StdioCollector { waitForEnd: true }
    onRunningChanged: if (!running) root.refresh()
  }

  Process {
    id: statusProc
    command: [root.apexctl, "status", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var data = JSON.parse(String(text || "{}"))
          if (data && data.rgb) root.status = data
          if (data && data.mouse && data.mouse.identify && data.mouse.identify.active) root.identifyRequested = false
        } catch (e) { /* ignore */ }
      }
    }
  }

  Process {
    id: actionProc
    stdout: StdioCollector { waitForEnd: true }
    onRunningChanged: {
      if (running) return
      if (root.queue.length) {
        var args = root.queue[0]
        root.queue = root.queue.slice(1)
        root.apex(args)
      } else {
        root.refresh()
      }
    }
  }

  // ── Building blocks ─────────────────────────────────────────────────

  component Chip: Button {
    foreground: root.ink
    fontFamily: root.bar.fontFamily
    fontSize: Style.font.caption
    bordered: true
  }

  component Header: PanelSectionHeader {
    foreground: root.ink
    fontFamily: root.bar.fontFamily
  }

  component Note: Text {
    width: parent.width
    wrapMode: Text.WordWrap
    color: root.ink
    opacity: 0.6
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.caption
  }

  component Caption: Text {
    color: root.ink
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.caption
  }

  // A filled circle for a solid colour, a hue wheel for "cycle", a slashed
  // ring for "off".
  component ColorDot: Rectangle {
    id: dot
    property string value: ""
    width: Style.space(12)
    height: width
    radius: width / 2
    color: dot.value.charAt(0) === "#" ? dot.value : "transparent"
    border.width: 1
    border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.35)
    gradient: dot.value === "cycle" ? hues : null
    Gradient {
      id: hues
      orientation: Gradient.Horizontal
      GradientStop { position: 0.0; color: root.rainbow[0] }
      GradientStop { position: 0.33; color: root.rainbow[2] }
      GradientStop { position: 0.66; color: root.rainbow[4] }
      GradientStop { position: 1.0; color: root.rainbow[5] }
    }
    Rectangle {
      visible: dot.value === "off" || dot.value === ""
      anchors.centerIn: parent
      width: parent.width * 0.9
      height: 1
      rotation: -45
      color: dot.border.color
    }
  }

  // A round colour swatch with a label; ringed when it is the current one.
  // `stops` (2+ colours) draws a gradient instead of `fill`.
  component Swatch: Item {
    id: sw
    property color fill: "transparent"
    property var stops: null
    property string label: ""
    property bool active: false
    signal clicked()
    width: Style.space(48)
    height: ring.height + Style.space(4) + name.implicitHeight

    Rectangle {
      id: ring
      anchors.horizontalCenter: parent.horizontalCenter
      width: Style.space(34)
      height: width
      radius: width / 2
      color: "transparent"
      border.width: sw.active ? 2 : (hover.containsMouse ? 1 : 0)
      border.color: root.ink

      Rectangle {
        anchors.centerIn: parent
        width: parent.width - Style.space(8)
        height: width
        radius: width / 2
        color: sw.fill
        border.width: 1
        border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.25)
        gradient: sw.stops ? swatchGradient : null
        Gradient {
          id: swatchGradient
          orientation: Gradient.Horizontal
          GradientStop { position: 0.0; color: sw.stops ? sw.stops[0] : "black" }
          GradientStop { position: 0.5; color: sw.stops ? sw.stops[Math.floor(sw.stops.length / 2)] : "black" }
          GradientStop { position: 1.0; color: sw.stops ? sw.stops[sw.stops.length - 1] : "black" }
        }
      }
    }
    Caption {
      id: name
      anchors.top: ring.bottom
      anchors.topMargin: Style.space(4)
      anchors.horizontalCenter: parent.horizontalCenter
      text: sw.label
      opacity: sw.active ? 1 : 0.6
      font.bold: sw.active
    }
    MouseArea {
      id: hover
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: sw.clicked()
    }
  }

  component SwatchGrid: Grid {
    id: grid
    property int count: 0
    width: parent.width
    columns: grid.count > 8 ? Math.ceil(grid.count / 2) : Math.max(1, grid.count)
    rowSpacing: Style.space(10)
    readonly property real cell: (grid.width - grid.columnSpacing * (grid.columns - 1)) / grid.columns
  }

  // A wide gradient pill for a multi-colour profile.
  component GradientPill: Item {
    id: pill
    property var stops: []
    property string label: ""
    property bool active: false
    signal clicked()
    height: bar.height + Style.space(4) + pillName.implicitHeight

    Rectangle {
      id: bar
      width: parent.width
      height: Style.space(22)
      radius: height / 2
      border.width: pill.active ? 2 : (pillHover.containsMouse ? 1 : 0)
      border.color: root.ink
      gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0.0; color: pill.stops[0] || "black" }
        GradientStop { position: 0.5; color: pill.stops[1] || "black" }
        GradientStop { position: 1.0; color: pill.stops[2] || "black" }
      }
    }
    Caption {
      id: pillName
      anchors.top: bar.bottom
      anchors.topMargin: Style.space(4)
      anchors.horizontalCenter: parent.horizontalCenter
      text: pill.label
      opacity: pill.active ? 1 : 0.6
      font.bold: pill.active
    }
    MouseArea {
      id: pillHover
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: pill.clicked()
    }
  }

  // Label and live value above a slider. The slider never takes the scroll
  // wheel: scrolling the panel over it scrolls the panel.
  component LabeledSlider: Column {
    id: ls
    property string label: ""
    property string suffix: "%"
    property real value: 0
    property real minimum: 0
    property real maximum: 100
    property real step: 5
    signal committed(int value)
    width: parent.width
    spacing: Style.space(6)

    Item {
      width: parent.width
      height: lsLabel.implicitHeight
      Caption { id: lsLabel; text: ls.label; opacity: 0.75 }
      Caption {
        anchors.right: parent.right
        text: Math.round(lsSlider.liveValue) + ls.suffix
        font.bold: true
      }
    }
    Item {
      width: parent.width
      height: lsSlider.implicitHeight
      PanelSlider {
        id: lsSlider
        width: parent.width
        bar: root.bar
        minimum: ls.minimum
        maximum: ls.maximum
        step: ls.step
        integer: true
        value: ls.value
        onReleased: function(v) { ls.committed(Math.round(v)) }
      }
      MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: function(wheel) { root.scrollPanel(wheel.angleDelta.y) }
      }
    }
  }

  // A device summary in the header; clicking opens its tab.
  component StatusCard: Rectangle {
    id: card
    property string title: ""
    property string detail: ""
    property string colorValue: ""
    property string target: ""
    property bool dim: false
    height: cardColumn.implicitHeight + Style.space(16)
    radius: Style.cornerRadius
    color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, cardHover.containsMouse ? 0.10 : 0.05)
    border.width: root.tab === card.target ? 1 : 0
    border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.4)
    opacity: card.dim ? 0.55 : 1

    Column {
      id: cardColumn
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(3)
      Row {
        spacing: Style.space(6)
        width: parent.width
        ColorDot { value: card.colorValue; anchors.verticalCenter: parent.verticalCenter }
        Text {
          width: parent.width - Style.space(18)
          text: card.title
          elide: Text.ElideRight
          color: root.ink
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.body
          font.bold: true
        }
      }
      Caption {
        width: parent.width
        text: card.detail
        elide: Text.ElideRight
        opacity: 0.7
      }
    }
    MouseArea {
      id: cardHover
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: root.tab = card.target
    }
  }

  // Top view of a G502 (front up). Each remappable button gets a dot where it
  // sits and a leader line out to a numbered marker in a column beside the
  // mouse, so nothing covers the drawing. Positions were confirmed with the
  // mouse's button spy. A marker lights with root.hotSlot or the button
  // Identify last caught.
  component MouseDiagram: Item {
    id: md
    property var buttons: []
    // slot -> {at: [u, v] button centre in the body box, side, v: marker height}
    readonly property var spots: ({
      10: { at: [0.435, 0.19], side: "L", v: 0.08 },
      7: { at: [0.24, 0.20], side: "L", v: 0.20 },
      6: { at: [0.24, 0.31], side: "L", v: 0.32 },
      5: { at: [0.07, 0.37], side: "L", v: 0.44 },
      4: { at: [0.10, 0.47], side: "L", v: 0.56 },
      3: { at: [0.09, 0.575], side: "L", v: 0.68 },
      2: { at: [0.50, 0.10], side: "R", v: 0.05 },
      9: { at: [0.565, 0.19], side: "R", v: 0.19 },
      8: { at: [0.50, 0.36], side: "R", v: 0.36 }
    })
    readonly property real boxH: height - Style.space(8)
    readonly property real boxW: boxH * 0.62
    readonly property real boxX: (width - boxW) / 2
    readonly property real boxY: Style.space(4)
    readonly property real gutter: Style.space(46)
    width: parent.width
    height: Style.space(250)

    function px(u) { return md.boxX + u * md.boxW }
    function py(v) { return md.boxY + v * md.boxH }
    function markerX(spot) { return spot.side === "L" ? md.boxX - md.gutter : md.boxX + md.boxW + md.gutter }
    function lit(slot) { return root.hotSlot === slot || root.identifiedSlot === slot }

    Canvas {
      id: body
      anchors.fill: parent
      property color ink: root.ink
      property color accent: Color.accent
      property var litState: [root.hotSlot, root.identifiedSlot]
      onInkChanged: requestPaint()
      onLitStateChanged: requestPaint()
      onWidthChanged: requestPaint()
      onHeightChanged: requestPaint()
      onPaint: {
        var c = getContext("2d")
        c.reset()
        var X = md.px, Y = md.py
        c.lineWidth = 1.5
        c.strokeStyle = Qt.rgba(ink.r, ink.g, ink.b, 0.55)
        c.fillStyle = Qt.rgba(ink.r, ink.g, ink.b, 0.06)
        // Body: narrow front with the two click buttons, thumb rest flaring left.
        c.beginPath()
        c.moveTo(X(0.26), Y(0.06))
        c.bezierCurveTo(X(0.40), Y(0.00), X(0.60), Y(0.00), X(0.74), Y(0.06))
        c.bezierCurveTo(X(0.88), Y(0.16), X(0.94), Y(0.46), X(0.89), Y(0.70))
        c.bezierCurveTo(X(0.85), Y(0.90), X(0.70), Y(1.00), X(0.50), Y(1.00))
        c.bezierCurveTo(X(0.30), Y(1.00), X(0.12), Y(0.92), X(0.07), Y(0.78))
        c.bezierCurveTo(X(0.01), Y(0.66), X(0.03), Y(0.54), X(0.11), Y(0.47))
        c.bezierCurveTo(X(0.15), Y(0.36), X(0.16), Y(0.17), X(0.26), Y(0.06))
        c.closePath()
        c.fill()
        c.stroke()
        // Where the click buttons end, and the split between them.
        c.beginPath()
        c.moveTo(X(0.14), Y(0.43))
        c.bezierCurveTo(X(0.35), Y(0.47), X(0.65), Y(0.47), X(0.90), Y(0.42))
        c.moveTo(X(0.50), Y(0.03))
        c.lineTo(X(0.50), Y(0.08))
        c.moveTo(X(0.50), Y(0.28))
        c.lineTo(X(0.50), Y(0.45))
        c.stroke()
        // Wheel, the two buttons left of the left click, the one behind the wheel.
        c.beginPath()
        c.roundedRect(X(0.455), Y(0.08), X(0.545) - X(0.455), Y(0.27) - Y(0.08), 6, 6)
        c.roundedRect(X(0.20), Y(0.15), X(0.28) - X(0.20), Y(0.25) - Y(0.15), 4, 4)
        c.roundedRect(X(0.20), Y(0.27), X(0.28) - X(0.20), Y(0.35) - Y(0.27), 4, 4)
        c.ellipse(X(0.46), Y(0.33), X(0.54) - X(0.46), Y(0.39) - Y(0.33))
        // Side buttons along the left edge: sniper, thumb front, thumb rear.
        c.roundedRect(X(0.04), Y(0.33), X(0.10) - X(0.04), Y(0.41) - Y(0.33), 4, 4)
        c.roundedRect(X(0.07), Y(0.43), X(0.13) - X(0.07), Y(0.51) - Y(0.43), 4, 4)
        c.roundedRect(X(0.06), Y(0.53), X(0.12) - X(0.06), Y(0.62) - Y(0.53), 4, 4)
        c.stroke()
        // Leader lines and dots, the lit one in the accent colour.
        for (var i = 0; i < md.buttons.length; i++) {
          var slot = md.buttons[i].id
          var spot = md.spots[slot]
          if (!spot) continue
          var on = md.lit(slot)
          var ax = X(spot.at[0]), ay = Y(spot.at[1])
          var mx = md.markerX(spot), my = Y(spot.v)
          var elbow = spot.side === "L" ? Math.min(ax - 10, md.boxX - 8) : Math.max(ax + 10, md.boxX + md.boxW + 8)
          c.strokeStyle = on ? accent : Qt.rgba(ink.r, ink.g, ink.b, 0.28)
          c.lineWidth = on ? 2 : 1
          c.beginPath()
          c.moveTo(ax, ay)
          c.lineTo(elbow, my)
          c.lineTo(mx, my)
          c.stroke()
          c.fillStyle = on ? accent : Qt.rgba(ink.r, ink.g, ink.b, 0.7)
          c.beginPath()
          c.ellipse(ax - 2.5, ay - 2.5, 5, 5)
          c.fill()
        }
      }
    }

    Repeater {
      model: md.buttons
      Rectangle {
        id: marker
        required property var modelData
        required property int index
        readonly property var spot: md.spots[modelData.id] || null
        readonly property bool lit: md.lit(modelData.id)
        visible: !!spot
        x: spot ? md.markerX(spot) - width / 2 : 0
        y: spot ? md.py(spot.v) - height / 2 : 0
        width: Style.space(20)
        height: width
        radius: width / 2
        color: marker.lit ? Color.accent : Qt.rgba(root.bar.background.r, root.bar.background.g, root.bar.background.b, 0.95)
        border.width: 1
        border.color: marker.lit ? Color.accent : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.6)
        scale: marker.lit ? 1.2 : 1
        Behavior on scale { NumberAnimation { duration: 120 } }
        Text {
          anchors.centerIn: parent
          text: marker.index + 1
          color: marker.lit ? root.bar.background : root.ink
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          font.bold: true
        }
        MouseArea {
          anchors.fill: parent
          hoverEnabled: true
          onContainsMouseChanged: root.hotSlot = containsMouse ? marker.modelData.id : (root.hotSlot === marker.modelData.id ? -1 : root.hotSlot)
        }
      }
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰌏"
    iconComponent: Component {
      KeyboardGlyph {
        anchors.fill: parent
        ink: button.foreground
      }
    }
    onPressed: function(b) { root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    contentWidth: panel.fittedContentWidth(Style.space(440))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(640))

    ScrollView {
      id: scrollArea
      anchors.fill: parent
      clip: true
      ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
      ScrollBar.vertical.policy: panelColumn.implicitHeight > height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

      Column {
        id: panelColumn
        width: scrollArea.availableWidth
        spacing: Style.space(14)

        // ── Header ───────────────────────────────────────────────────
        Item {
          width: parent.width
          height: Math.max(heroIcon.height, heroText.implicitHeight)
          KeyboardGlyph {
            id: heroIcon
            width: Style.font.display
            height: Style.font.display
            ink: root.ink
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }
          Column {
            id: heroText
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(12)
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0
            Text {
              text: "Deskset"
              color: root.ink
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Caption {
              text: root.status.daemon === false ? "Background service offline" : "Keyboard and mouse"
              opacity: 0.6
            }
          }
        }

        Chip {
          visible: root.status.daemon === false
          text: installProc.running ? "Setting up…" : "Set up background service"
          onClicked: root.setup()
        }

        Row {
          width: parent.width
          spacing: Style.spacing.md
          StatusCard {
            width: (parent.width - parent.spacing) / 2
            target: "keyboard"
            title: root.status.short || "Keyboard"
            colorValue: root.status.rgb_preview || ""
            detail: root.pretty(root.rgb.mode) + "  ·  " + (root.rgb.brightness || 0) + "%"
          }
          StatusCard {
            width: (parent.width - parent.spacing) / 2
            target: "mouse"
            dim: !root.mousePresent
            title: root.mousePresent ? (root.mouse.name || "Mouse").replace(/ LIGHTSPEED.*$/, "") : "Mouse"
            colorValue: root.mousePresent && root.mouse.preview ? root.mouse.preview : ""
            detail: !root.mousePresent ? "not connected"
              : [root.mouse.dpi ? root.mouse.dpi + " DPI" : "",
                 root.batteryText(root.mouse.battery),
                 root.mouse.battery && (root.mouse.battery.charging || root.mouse.battery.full) ? "" : (root.mouse.connection || "")]
                .filter(s => s).join("  ·  ")
          }
        }

        Row {
          id: tabRow
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            model: root.tabs
            Chip {
              required property var modelData
              width: (tabRow.width - tabRow.spacing * (root.tabs.length - 1)) / root.tabs.length
              text: modelData.label
              iconText: modelData.icon
              fontSize: Style.font.body
              selected: root.tab === modelData.value
              onClicked: root.tab = modelData.value
            }
          }
        }

        PanelSeparator { foreground: root.ink }

        // ── Favorites ────────────────────────────────────────────────
        Column {
          visible: root.tab === "favorites"
          width: parent.width
          spacing: Style.space(14)

          Item {
            width: parent.width
            height: favEdit.implicitHeight
            Caption {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              text: root.editingFavorites ? "Tap to add or remove" : ""
              opacity: 0.6
            }
            Row {
              anchors.right: parent.right
              spacing: Style.spacing.xs
              Chip {
                visible: root.editingFavorites
                text: "Reset"
                onClicked: root.apex(["favorites", "--reset"])
              }
              Chip {
                id: favEdit
                text: root.editingFavorites ? "Done" : "Edit"
                iconText: root.editingFavorites ? "󰄬" : "󰏫"
                selected: root.editingFavorites
                onClicked: root.editingFavorites = !root.editingFavorites
              }
            }
          }

          // Sections on or off (edit mode only).
          Header { visible: root.editingFavorites; text: "SECTIONS" }
          Grid {
            id: favSections
            visible: root.editingFavorites
            width: parent.width
            columns: 3
            spacing: Style.spacing.xs
            Repeater {
              model: root.favoriteSections
              Chip {
                required property var modelData
                width: (favSections.width - favSections.spacing * 2) / 3
                text: modelData.label
                selected: root.favHas("sections", modelData.value)
                onClicked: root.favToggle("sections", modelData.value)
              }
            }
          }

          LabeledSlider {
            visible: !root.editingFavorites && root.favHas("sections", "brightness")
            label: "Brightness · keyboard and mouse"
            value: Number(root.rgb.brightness || 80)
            onCommitted: function(v) { root.setBrightnessBoth(v) }
          }

          Header { visible: root.favShows("lighting"); text: "LIGHTING" }
          SwatchGrid {
            id: favSwatches
            visible: root.favShows("lighting")
            readonly property var items: root.editingFavorites ? root.colorCandidates() : root.fav.colors
            count: items.length
            Repeater {
              model: favSwatches.items
              Swatch {
                required property var modelData
                width: favSwatches.cell
                label: root.colorLabel(modelData)
                fill: modelData.charAt(0) === "#" ? modelData : Color.accent
                stops: modelData === "rainbow" ? root.rainbow : null
                active: root.editingFavorites ? root.favHas("colors", modelData) : root.colorIsCurrent(modelData)
                opacity: root.editingFavorites && !active ? 0.45 : 1
                onClicked: root.editingFavorites ? root.favToggle("colors", modelData) : root.applyFavoriteColor(modelData)
              }
            }
          }
          Row {
            visible: root.editingFavorites && root.favHas("sections", "lighting")
            width: parent.width
            spacing: Style.spacing.xs
            TextField {
              id: newColor
              width: parent.width - addColor.width - parent.spacing
              placeholderText: "Add a colour: #RRGGBB"
              foreground: root.ink
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              onAccepted: root.addFavoriteColor()
            }
            Chip {
              id: addColor
              text: "Add"
              onClicked: root.addFavoriteColor()
            }
          }
          Note {
            visible: !root.editingFavorites && root.favHas("sections", "lighting")
            text: "The mouse follows the keyboard while it is set to match."
          }

          Header { visible: root.favShows("dpi") && root.mousePresent; text: "MOUSE DPI" }
          Grid {
            id: favDpi
            visible: root.favShows("dpi") && root.mousePresent
            readonly property var items: root.editingFavorites ? root.dpiCandidates() : root.fav.dpi
            width: parent.width
            columns: Math.max(1, Math.min(5, items.length))
            spacing: Style.spacing.xs
            Repeater {
              model: favDpi.items
              Chip {
                required property var modelData
                width: (favDpi.width - favDpi.spacing * (favDpi.columns - 1)) / favDpi.columns
                text: String(modelData)
                selected: root.editingFavorites ? root.favHas("dpi", modelData) : (root.mouse && root.mouse.dpi === modelData)
                onClicked: root.editingFavorites ? root.favToggle("dpi", modelData) : root.apex(["mouse", "--dpi", String(modelData)])
              }
            }
          }
          Row {
            visible: root.editingFavorites && root.favHas("sections", "dpi") && root.mousePresent
            width: parent.width
            spacing: Style.spacing.xs
            TextField {
              id: newDpi
              width: parent.width - addDpi.width - parent.spacing
              placeholderText: "Add a DPI value"
              inputMethodHints: Qt.ImhDigitsOnly
              validator: IntValidator { bottom: 50; top: 64000 }
              foreground: root.ink
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
              onAccepted: root.addFavoriteDpi()
            }
            Chip {
              id: addDpi
              text: "Add"
              onClicked: root.addFavoriteDpi()
            }
          }

          Header { visible: root.favShows("oled"); text: "OLED" }
          Grid {
            id: favOled
            visible: root.favShows("oled")
            readonly property var items: root.editingFavorites ? root.oledPages : root.fav.oled
            width: parent.width
            columns: Math.max(1, Math.min(root.editingFavorites ? 3 : 4, items.length))
            spacing: Style.spacing.xs
            Repeater {
              model: favOled.items
              Chip {
                required property string modelData
                width: (favOled.width - favOled.spacing * (favOled.columns - 1)) / favOled.columns
                text: root.pretty(modelData)
                selected: root.editingFavorites ? root.favHas("oled", modelData) : (root.status.oled && root.status.oled.page === modelData)
                onClicked: root.editingFavorites ? root.favToggle("oled", modelData) : root.apex(["oled", modelData])
              }
            }
          }

          Header { visible: root.favShows("wheel"); text: "WHEEL" }
          Grid {
            id: favWheel
            visible: root.favShows("wheel")
            readonly property var items: root.editingFavorites ? root.wheelModes : root.fav.wheel
            width: parent.width
            columns: Math.max(1, Math.min(3, items.length))
            spacing: Style.spacing.xs
            Repeater {
              model: favWheel.items
              Chip {
                required property string modelData
                width: (favWheel.width - favWheel.spacing * (favWheel.columns - 1)) / favWheel.columns
                text: root.pretty(modelData)
                selected: root.editingFavorites ? root.favHas("wheel", modelData) : (root.status.wheel && root.status.wheel.mode === modelData)
                onClicked: root.editingFavorites ? root.favToggle("wheel", modelData) : root.apex(["wheel", modelData])
              }
            }
          }

          Note {
            visible: !root.editingFavorites && root.fav.sections.length === 0
            text: "Nothing here yet. Press Edit to pick what Favorites shows."
          }
        }

        // ── Mouse ────────────────────────────────────────────────────
        Column {
          visible: root.tab === "mouse"
          width: parent.width
          spacing: Style.space(14)

          Note {
            visible: !root.mousePresent
            text: "No Logitech mouse reachable" + (root.mouse && root.mouse.error ? ": " + root.mouse.error : "") + "."
          }

          Header { text: "LIGHTING" }
          Grid {
            id: mouseModesGrid
            width: parent.width
            columns: 3
            spacing: Style.spacing.xs
            Repeater {
              model: root.mouseModes
              Chip {
                required property string modelData
                width: (mouseModesGrid.width - mouseModesGrid.spacing * 2) / 3
                text: root.mouseModeLabels[modelData] || root.pretty(modelData)
                selected: root.mouse && root.mouse.mode === modelData
                onClicked: root.apex(["mouse", modelData])
              }
            }
          }
          SwatchGrid {
            id: mouseSwatches
            visible: root.mouse && (root.mouse.mode === "solid" || root.mouse.mode === "breathe")
            count: root.colorPresets.length + 1
            Swatch {
              width: mouseSwatches.cell
              label: "theme"
              fill: Color.accent
              active: root.mouse && root.mouse.color === "accent"
              onClicked: root.setMouseColor("accent")
            }
            Repeater {
              model: root.colorPresets
              Swatch {
                required property var modelData
                width: mouseSwatches.cell
                label: modelData.label
                fill: modelData.color
                active: root.mouse && root.sameColor(root.mouse.color, modelData.color)
                onClicked: root.setMouseColor(modelData.color)
              }
            }
          }
          LabeledSlider {
            label: "Brightness"
            value: root.mouseBrightness()
            onCommitted: function(v) { root.apex(["mouse", "-b", String(v)]) }
          }
          Note {
            text: "Goes dark when you are away and breathes orange while Claude waits for you."
          }

          Header { visible: root.mousePresent && !!root.mouse.dpi; text: "DPI" }
          Item {
            visible: root.mousePresent && !!root.mouse.dpi
            width: parent.width
            height: dpiValue.implicitHeight
            Chip {
              id: dpiDown
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(44)
              text: "−"
              fontSize: Style.font.title
              onClicked: root.apex(["mouse", "--dpi", String(Math.max(root.mouse.dpi_min || 100, root.mouse.dpi - (root.mouse.dpi_step || 50)))])
            }
            Column {
              anchors.centerIn: parent
              Text {
                id: dpiValue
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.mouse && root.mouse.dpi ? root.mouse.dpi : ""
                color: root.ink
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.display
                font.bold: true
              }
            }
            Chip {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              width: Style.space(44)
              text: "+"
              fontSize: Style.font.title
              onClicked: root.apex(["mouse", "--dpi", String(Math.min(root.mouse.dpi_max || 25600, root.mouse.dpi + (root.mouse.dpi_step || 50)))])
            }
          }
          Row {
            id: mouseDpi
            visible: root.mousePresent && !!root.mouse.dpi_presets
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.mouse && root.mouse.dpi_presets || []
              Chip {
                required property var modelData
                width: (mouseDpi.width - mouseDpi.spacing * 4) / 5
                text: String(modelData)
                selected: root.mouse && root.mouse.dpi === modelData
                onClicked: root.apex(["mouse", "--dpi", String(modelData)])
              }
            }
          }

          Item {
            visible: root.mousePresent && !!(root.mouse.buttons && root.mouse.buttons.length)
            width: parent.width
            height: identifyChip.implicitHeight
            Header {
              anchors.left: parent.left
              anchors.verticalCenter: parent.verticalCenter
              text: "BUTTONS"
            }
            Chip {
              id: identifyChip
              anchors.right: parent.right
              iconText: "󰍽"
              text: root.identifyActive ? "Press a mouse button…" : "Identify"
              selected: root.identifyActive
              onClicked: root.startIdentify()
            }
          }
          MouseDiagram {
            visible: root.mousePresent && !!(root.mouse.buttons && root.mouse.buttons.length)
            buttons: root.mousePresent && root.mouse.buttons || []
          }
          Repeater {
            model: root.mousePresent && root.mouse.buttons || []
            Rectangle {
              id: buttonRow
              required property var modelData
              required property int index
              readonly property bool lit: root.hotSlot === modelData.id || root.identifiedSlot === modelData.id
              width: parent.width
              height: Math.max(buttonName.implicitHeight, buttonAction.implicitHeight) + Style.space(6)
              radius: Style.cornerRadius
              color: buttonRow.lit ? Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.08) : "transparent"
              HoverHandler {
                onHoveredChanged: root.hotSlot = hovered ? buttonRow.modelData.id : (root.hotSlot === buttonRow.modelData.id ? -1 : root.hotSlot)
              }
              Rectangle {
                id: badge
                anchors.left: parent.left
                anchors.leftMargin: Style.space(4)
                anchors.verticalCenter: parent.verticalCenter
                width: Style.space(18)
                height: width
                radius: width / 2
                color: buttonRow.lit ? Color.accent : "transparent"
                border.width: 1
                border.color: buttonRow.lit ? Color.accent : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.6)
                Text {
                  anchors.centerIn: parent
                  text: buttonRow.index + 1
                  color: buttonRow.lit ? root.bar.background : root.ink
                  font.family: root.bar.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }
              }
              Caption {
                id: buttonName
                anchors.left: badge.right
                anchors.leftMargin: Style.space(8)
                anchors.right: buttonAction.left
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.label
                elide: Text.ElideRight
                opacity: buttonRow.lit ? 1 : 0.85
                font.bold: buttonRow.lit
              }
              Dropdown {
                id: buttonAction
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.52
                showLabel: false
                value: modelData.action
                options: root.mouse.button_actions || []
                foreground: root.ink
                fontFamily: root.bar.fontFamily
                onChanged: function(value) { root.apex(["mouse", "--button", modelData.id + "=" + value]) }
              }
            }
          }
          Note {
            visible: root.mousePresent && !!(root.mouse.buttons && root.mouse.buttons.length)
            text: "Hover a row to find it on the mouse, or press Identify and then the button. Saved in the mouse itself; apexctl mouse --restore-buttons puts the originals back."
          }
        }

        // ── Keyboard ─────────────────────────────────────────────────
        Column {
          visible: root.tab === "keyboard"
          width: parent.width
          spacing: Style.space(14)

          Header { text: "EFFECT" }
          Grid {
            id: rgbGrid
            width: parent.width
            columns: 4
            spacing: Style.spacing.xs
            Repeater {
              // Reactive needs keystroke access, which the Gen 3 udev rule withholds.
              model: root.rgbModes.filter(m => !(m === "reactive" && root.status.rgb_backend === "hid"))
              Chip {
                required property string modelData
                width: (rgbGrid.width - rgbGrid.spacing * 3) / 4
                text: root.pretty(modelData)
                selected: root.rgb.mode === modelData
                onClicked: root.apex(["rgb", modelData])
              }
            }
          }

          Header { text: "COLOUR" }
          SwatchGrid {
            id: keySwatches
            count: root.colorPresets.length
            Repeater {
              model: root.colorPresets
              Swatch {
                required property var modelData
                width: keySwatches.cell
                label: modelData.label
                fill: modelData.color
                active: root.rgb.mode === "solid" && root.sameColor(root.rgb.solid, modelData.color)
                onClicked: root.apex(["rgb", "-c", modelData.color])
              }
            }
          }

          LabeledSlider {
            label: "Brightness"
            value: Number(root.rgb.brightness || 80)
            onCommitted: function(v) { root.apex(["rgb", "-b", String(v)]) }
          }
          LabeledSlider {
            visible: root.animatedModes.indexOf(root.rgb.mode) >= 0
            label: "Speed"
            suffix: ""
            minimum: 1
            value: Number(root.rgb.speed || 45)
            onCommitted: function(v) { root.apex(["rgb", "-s", String(v)]) }
          }

          Header { text: "GRADIENT PROFILES" }
          Grid {
            id: profileGrid
            width: parent.width
            columns: 5
            rowSpacing: Style.space(10)
            columnSpacing: Style.spacing.md
            Repeater {
              model: root.rgbProfiles
              GradientPill {
                required property var modelData
                width: (profileGrid.width - profileGrid.columnSpacing * 4) / 5
                stops: modelData.colors
                label: modelData.name
                active: root.rgb.mode === "gradient" && root.rgb.profile === modelData.name
                onClicked: root.apex(["rgb", "gradient", "-p", modelData.name])
              }
            }
          }

          PanelSeparator { foreground: root.ink }
          Header { text: "OLED" }
          Grid {
            id: oledGrid
            width: parent.width
            columns: 3
            spacing: Style.spacing.xs
            Repeater {
              model: root.oledPages
              Chip {
                required property string modelData
                width: (oledGrid.width - oledGrid.spacing * 2) / 3
                text: root.pretty(modelData)
                selected: root.status.oled && root.status.oled.page === modelData
                onClicked: root.apex(["oled", modelData])
              }
            }
          }

          Header { text: "WHEEL" }
          Grid {
            id: wheelGrid
            width: parent.width
            columns: 3
            spacing: Style.spacing.xs
            Repeater {
              model: root.wheelModes
              Chip {
                required property string modelData
                width: (wheelGrid.width - wheelGrid.spacing * 2) / 3
                text: root.pretty(modelData)
                selected: root.status.wheel && root.status.wheel.mode === modelData
                onClicked: root.apex(["wheel", modelData])
              }
            }
          }
          Note {
            text: "Click the wheel to mute or cycle. App mode follows the focused window."
          }
        }
      }
    }
  }
}
