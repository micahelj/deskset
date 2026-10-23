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
  readonly property var rgbProfiles: ["sunset", "ocean", "fire", "matrix", "cyberpunk", "aurora", "candy", "ice", "vaporwave", "gold"]
  readonly property var oledPages: ["clock", "now-playing", "workspace", "logo", "text", "claude", "system", "gpu", "clear"]
  readonly property var wheelModes: ["volume", "app", "workspace", "brightness", "oled", "rgb"]
  readonly property var mouseModes: ["match", "solid", "breathe", "cycle", "off", "device"]
  // Keyboard colour presets for Favorites; the mouse follows in match mode.
  readonly property var lightPresets: [
    { label: "violet", color: "#4A1C90" },
    { label: "teal", color: "#00806A" },
    { label: "ice", color: "#7DD3FC" },
    { label: "white", color: "#FFFFFF" },
    { label: "orange", color: "#FF3C00" }
  ]
  readonly property var favoritePages: ["clock", "system", "claude", "now-playing"]
  readonly property var tabs: [
    { value: "favorites", label: "Favorites" },
    { value: "mouse", label: "Mouse" },
    { value: "keyboard", label: "Keyboard" }
  ]

  property string tab: "favorites"

  readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace("file://", "").replace(/\/$/, "")
  readonly property string scriptDir: pluginDir + "/bin"
  readonly property string apexctl: scriptDir + "/apexctl"

  readonly property var mouse: root.status.mouse || null
  readonly property bool mousePresent: !!(root.mouse && root.mouse.present)

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
    return m.mode === "match" ? Number(root.status.rgb && root.status.rgb.brightness || 80) : 100
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

  function pretty(value) {
    if (!value) return ""
    return String(value).replace(/-/g, " ")
  }

  // Installing adds a user service, hooks and a ~/.local/bin link, so it only
  // runs when asked from the panel, never on load.
  function setup() {
    if (!installProc.running) installProc.running = true
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

  component Chip: Button {
    foreground: root.bar.foreground
    fontFamily: root.bar.fontFamily
    fontSize: Style.font.caption
    bordered: true
  }

  component Header: PanelSectionHeader {
    foreground: root.bar.foreground
    fontFamily: root.bar.fontFamily
  }

  component Note: Text {
    width: parent.width
    wrapMode: Text.WordWrap
    color: root.bar.foreground
    opacity: 0.65
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.caption
  }

  component Caption: Text {
    color: root.bar.foreground
    font.family: root.bar.fontFamily
    font.pixelSize: Style.font.caption
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
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(600))

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

        Item {
          width: parent.width
          implicitHeight: heroIcon.implicitHeight
          KeyboardGlyph {
            id: heroIcon
            width: Style.font.display * 1.3
            height: Style.font.display * 1.3
            ink: root.bar.foreground
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }
          Column {
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.verticalCenter: parent.verticalCenter
            spacing: 0
            Text {
              text: (root.status.short || "Apex") + (root.mousePresent ? " + " + (root.mouse.short || "mouse") : "")
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Text {
              text: root.status.daemon === false ? "daemon offline"
                : root.pretty(root.status.rgb && root.status.rgb.mode)
                  + (root.mousePresent && root.mouse.dpi ? "  ·  " + root.mouse.dpi + " DPI" : "")
              color: root.bar.foreground
              opacity: 0.7
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }

        Chip {
          visible: root.status.daemon === false
          text: installProc.running ? "Setting up…" : "Set up background service"
          onClicked: root.setup()
        }

        ButtonGroup {
          options: root.tabs
          value: root.tab
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          fontSize: Style.font.caption
          focusable: false
          onChanged: function(value) { root.tab = value }
        }

        // ── Favorites ────────────────────────────────────────────────
        Column {
          visible: root.tab === "favorites"
          width: parent.width
          spacing: Style.space(14)

          Header { text: "BRIGHTNESS" }
          PanelSlider {
            width: parent.width
            bar: root.bar
            minimum: 0
            maximum: 100
            step: 5
            integer: true
            value: Number(root.status.rgb && root.status.rgb.brightness || 80)
            onReleased: function(value) { root.setBrightnessBoth(Math.round(value)) }
          }

          Header { text: "LIGHTING" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Chip {
              text: "theme"
              active: root.status.rgb && root.status.rgb.mode === "theme"
              onClicked: { root.apex(["rgb", "theme"]); if (root.mouse && root.mouse.mode !== "match") root.apex(["mouse", "match"]) }
            }
            Repeater {
              model: root.lightPresets
              Chip {
                required property var modelData
                text: modelData.label
                active: root.status.rgb && root.status.rgb.mode === "solid"
                  && String(root.status.rgb.solid).toUpperCase() === modelData.color
                onClicked: root.applyPreset(modelData.color)
              }
            }
            Chip {
              text: "rainbow"
              active: root.status.rgb && root.status.rgb.mode === "rainbow"
              onClicked: root.apex(["rgb", "rainbow"])
            }
          }

          Header { visible: root.mousePresent && !!root.mouse.dpi_presets; text: "MOUSE DPI" }
          Flow {
            visible: root.mousePresent && !!root.mouse.dpi_presets
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.mouse && root.mouse.dpi_presets || []
              Chip {
                required property var modelData
                text: String(modelData)
                active: root.mouse && root.mouse.dpi === modelData
                onClicked: root.apex(["mouse", "--dpi", String(modelData)])
              }
            }
          }

          Header { text: "OLED" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.favoritePages
              Chip {
                required property string modelData
                text: root.pretty(modelData)
                active: root.status.oled && root.status.oled.page === modelData
                onClicked: root.apex(["oled", modelData])
              }
            }
          }

          Header { text: "WHEEL" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: ["volume", "app", "workspace"]
              Chip {
                required property string modelData
                text: root.pretty(modelData)
                active: root.status.wheel && root.status.wheel.mode === modelData
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
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.mouseModes
              Chip {
                required property string modelData
                text: modelData === "match" ? "match keyboard" : root.pretty(modelData)
                active: root.mouse && root.mouse.mode === modelData
                onClicked: root.apex(["mouse", modelData])
              }
            }
          }
          PanelSlider {
            width: parent.width
            bar: root.bar
            minimum: 0
            maximum: 100
            step: 5
            integer: true
            value: root.mouseBrightness()
            onReleased: function(value) { root.apex(["mouse", "-b", String(Math.round(value))]) }
          }
          Note {
            text: "Match follows the keyboard's colour. The mouse goes dark when you are away and breathes orange while Claude waits."
          }

          Header { visible: root.mousePresent && !!root.mouse.dpi; text: "DPI" }
          Row {
            visible: root.mousePresent && !!root.mouse.dpi
            width: parent.width
            spacing: Style.spacing.md
            PanelSlider {
              id: dpiSlider
              width: parent.width - dpiLabel.width - parent.spacing
              anchors.verticalCenter: parent.verticalCenter
              bar: root.bar
              minimum: root.mouse && root.mouse.dpi_min || 100
              maximum: root.mouse && root.mouse.dpi_max || 25600
              step: root.mouse && root.mouse.dpi_step || 50
              integer: true
              value: root.mouse && root.mouse.dpi || 1600
              onReleased: function(value) { root.apex(["mouse", "--dpi", String(Math.round(value))]) }
            }
            Caption {
              id: dpiLabel
              width: Style.space(56)
              anchors.verticalCenter: parent.verticalCenter
              horizontalAlignment: Text.AlignRight
              text: Math.round(dpiSlider.liveValue)
            }
          }
          Flow {
            visible: root.mousePresent && !!root.mouse.dpi_presets
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.mouse && root.mouse.dpi_presets || []
              Chip {
                required property var modelData
                text: String(modelData)
                active: root.mouse && root.mouse.dpi === modelData
                onClicked: root.apex(["mouse", "--dpi", String(modelData)])
              }
            }
          }

          Header { visible: root.mousePresent && !!(root.mouse.buttons && root.mouse.buttons.length); text: "BUTTONS" }
          Repeater {
            model: root.mousePresent && root.mouse.buttons || []
            Dropdown {
              required property var modelData
              width: parent.width
              label: modelData.label
              value: modelData.action
              options: root.mouse.button_actions || []
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onChanged: function(value) { root.apex(["mouse", "--button", modelData.id + "=" + value]) }
            }
          }
        }

        // ── Keyboard ─────────────────────────────────────────────────
        Column {
          visible: root.tab === "keyboard"
          width: parent.width
          spacing: Style.space(14)

          Header { text: "RGB" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              // Reactive needs keystroke access, which the Gen 3 udev rule withholds.
              model: root.rgbModes.filter(m => !(m === "reactive" && root.status.rgb_backend === "hid"))
              Chip {
                required property string modelData
                text: root.pretty(modelData)
                active: root.status.rgb && root.status.rgb.mode === modelData
                onClicked: root.apex(["rgb", modelData])
              }
            }
          }
          PanelSlider {
            width: parent.width
            bar: root.bar
            minimum: 0
            maximum: 100
            step: 5
            integer: true
            value: Number(root.status.rgb && root.status.rgb.brightness || 80)
            onReleased: function(value) { root.apex(["rgb", "-b", String(Math.round(value))]) }
          }

          PanelSeparator { foreground: root.bar.foreground }
          Header { text: "GRADIENT PROFILES" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.rgbProfiles
              Chip {
                required property string modelData
                text: root.pretty(modelData)
                active: root.status.rgb && root.status.rgb.mode === "gradient" && root.status.rgb.profile === modelData
                onClicked: root.apex(["rgb", "gradient", "-p", modelData])
              }
            }
          }

          PanelSeparator { foreground: root.bar.foreground }
          Header { text: "OLED" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.oledPages
              Chip {
                required property string modelData
                text: root.pretty(modelData)
                active: root.status.oled && root.status.oled.page === modelData
                onClicked: root.apex(["oled", modelData])
              }
            }
          }

          PanelSeparator { foreground: root.bar.foreground }
          Header { text: "WHEEL" }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.wheelModes
              Chip {
                required property string modelData
                text: root.pretty(modelData)
                active: root.status.wheel && root.status.wheel.mode === modelData
                onClicked: root.apex(["wheel", modelData])
              }
            }
          }
          Note {
            text: "Volume stays the default. Switch the wheel to workspaces, brightness, OLED pages, or RGB effects. Click the wheel to mute / cycle."
          }
        }
      }
    }
  }
}
