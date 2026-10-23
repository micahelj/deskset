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
    { label: "white", color: "#FFFFFF" }
  ]
  readonly property var favoritePages: ["clock", "system", "claude", "now-playing"]
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
  }

  Component.onCompleted: root.refresh()
  onOpenedChanged: if (opened) root.refresh()

  Timer {
    interval: 2500
    running: true
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

          LabeledSlider {
            label: "Brightness · keyboard and mouse"
            value: Number(root.rgb.brightness || 80)
            onCommitted: function(v) { root.setBrightnessBoth(v) }
          }

          Header { text: "LIGHTING" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Swatch {
              label: "theme"
              fill: Color.accent
              active: root.rgb.mode === "theme"
              onClicked: { root.apex(["rgb", "theme"]); if (root.mouse && root.mouse.mode !== "match") root.apex(["mouse", "match"]) }
            }
            Repeater {
              model: root.colorPresets
              Swatch {
                required property var modelData
                label: modelData.label
                fill: modelData.color
                active: root.rgb.mode === "solid" && root.sameColor(root.rgb.solid, modelData.color)
                onClicked: root.applyPreset(modelData.color)
              }
            }
            Swatch {
              label: "rainbow"
              stops: root.rainbow
              active: root.rgb.mode === "rainbow"
              onClicked: root.apex(["rgb", "rainbow"])
            }
          }
          Note { text: "The mouse follows the keyboard while it is set to match." }

          Header { visible: root.mousePresent && !!root.mouse.dpi_presets; text: "MOUSE DPI" }
          Row {
            id: favDpi
            visible: root.mousePresent && !!root.mouse.dpi_presets
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.mouse && root.mouse.dpi_presets || []
              Chip {
                required property var modelData
                width: (favDpi.width - favDpi.spacing * 4) / 5
                text: String(modelData)
                selected: root.mouse && root.mouse.dpi === modelData
                onClicked: root.apex(["mouse", "--dpi", String(modelData)])
              }
            }
          }

          Header { text: "OLED" }
          Row {
            id: favOled
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.favoritePages
              Chip {
                required property string modelData
                width: (favOled.width - favOled.spacing * 3) / 4
                text: root.pretty(modelData)
                selected: root.status.oled && root.status.oled.page === modelData
                onClicked: root.apex(["oled", modelData])
              }
            }
          }

          Header { text: "WHEEL" }
          Row {
            id: favWheel
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: ["volume", "app", "workspace"]
              Chip {
                required property string modelData
                width: (favWheel.width - favWheel.spacing * 2) / 3
                text: root.pretty(modelData)
                selected: root.status.wheel && root.status.wheel.mode === modelData
                onClicked: root.apex(["wheel", modelData])
              }
            }
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
          Flow {
            visible: root.mouse && (root.mouse.mode === "solid" || root.mouse.mode === "breathe")
            width: parent.width
            spacing: Style.spacing.xs
            Swatch {
              label: "theme"
              fill: Color.accent
              active: root.mouse && root.mouse.color === "accent"
              onClicked: root.setMouseColor("accent")
            }
            Repeater {
              model: root.colorPresets
              Swatch {
                required property var modelData
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

          Header { visible: root.mousePresent && !!(root.mouse.buttons && root.mouse.buttons.length); text: "BUTTONS" }
          Repeater {
            model: root.mousePresent && root.mouse.buttons || []
            Item {
              required property var modelData
              width: parent.width
              height: Math.max(buttonName.implicitHeight, buttonAction.implicitHeight)
              Caption {
                id: buttonName
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.4
                text: modelData.label
                elide: Text.ElideRight
                opacity: 0.85
              }
              Dropdown {
                id: buttonAction
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.6
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
            text: "Saved in the mouse itself. apexctl mouse --restore-buttons puts the originals back."
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
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.colorPresets
              Swatch {
                required property var modelData
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
