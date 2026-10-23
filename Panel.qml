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

  readonly property string pluginDir: Qt.resolvedUrl(".").toString().replace("file://", "").replace(/\/$/, "")
  readonly property string scriptDir: pluginDir + "/bin"
  readonly property string apexctl: scriptDir + "/apexctl"

  property var queuedAction: null

  function apex(args) {
    if (actionProc.running) {
      // A previous command is still finishing; queue this one so no click is
      // ever dropped.
      root.queuedAction = args
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
    var m = root.status.mouse || {}
    if (m.brightness !== null && m.brightness !== undefined) return Number(m.brightness)
    return m.mode === "match" ? Number(root.status.rgb && root.status.rgb.brightness || 80) : 100
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
      if (root.queuedAction) {
        var args = root.queuedAction
        root.queuedAction = null
        root.apex(args)
      } else {
        root.refresh()
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
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(560))

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
              text: root.status.short || "Apex"
              color: root.bar.foreground
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Text {
              text: root.status.daemon === false ? "daemon offline" : root.pretty(root.status.rgb && root.status.rgb.mode)
              color: root.bar.foreground
              opacity: 0.7
              font.family: root.bar.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }

        Button {
          visible: root.status.daemon === false
          text: installProc.running ? "Setting up…" : "Set up background service"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          fontSize: Style.font.caption
          bordered: true
          onClicked: root.setup()
        }

        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "RGB"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }

        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            // Reactive needs keystroke access, which the Gen 3 udev rule withholds.
            model: root.rgbModes.filter(m => !(m === "reactive" && root.status.rgb_backend === "hid"))
            Button {
              required property string modelData
              text: root.pretty(modelData)
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              active: root.status.rgb && root.status.rgb.mode === modelData
              onClicked: root.apex(["rgb", modelData])
            }
          }
        }

        Row {
          width: parent.width
          spacing: Style.spacing.xs
          Button {
            text: "Dim"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            fontSize: Style.font.caption
            bordered: true
            onClicked: root.apex(["rgb", "-b", String(Math.max(10, Number(root.status.rgb && root.status.rgb.brightness || 80) - 15))])
          }
          Button {
            text: "Bright"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            fontSize: Style.font.caption
            bordered: true
            onClicked: root.apex(["rgb", "-b", String(Math.min(100, Number(root.status.rgb && root.status.rgb.brightness || 80) + 15))])
          }
          Button {
            text: "Theme colors"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            fontSize: Style.font.caption
            bordered: true
            onClicked: root.apex(["rgb", "theme"])
          }
        }

        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "GRADIENT PROFILES"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }

        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            model: root.rgbProfiles
            Button {
              required property string modelData
              text: root.pretty(modelData)
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              active: root.status.rgb && root.status.rgb.mode === "gradient" && root.status.rgb.profile === modelData
              onClicked: root.apex(["rgb", "gradient", "-p", modelData])
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "OLED"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }

        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            model: root.oledPages
            Button {
              required property string modelData
              text: root.pretty(modelData)
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              active: root.status.oled && root.status.oled.page === modelData
              onClicked: root.apex(["oled", modelData])
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "WHEEL"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }

        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            model: root.wheelModes
            Button {
              required property string modelData
              text: root.pretty(modelData)
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              active: root.status.wheel && root.status.wheel.mode === modelData
              onClicked: root.apex(["wheel", modelData])
            }
          }
        }

        Text {
          width: parent.width
          wrapMode: Text.WordWrap
          text: "Volume stays the default. Switch the wheel to workspaces, brightness, OLED pages, or RGB effects. Click the wheel to mute / cycle."
          color: root.bar.foreground
          opacity: 0.65
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
        }

        PanelSeparator { visible: !!root.status.mouse; foreground: root.bar.foreground }
        PanelSectionHeader {
          visible: !!root.status.mouse
          text: "MOUSE"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
        }

        Flow {
          visible: !!root.status.mouse
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            model: root.mouseModes
            Button {
              required property string modelData
              text: modelData === "match" ? "match keyboard" : root.pretty(modelData)
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              active: root.status.mouse && root.status.mouse.mode === modelData
              onClicked: root.apex(["mouse", modelData])
            }
          }
        }

        Row {
          visible: !!root.status.mouse
          width: parent.width
          spacing: Style.spacing.xs
          Button {
            text: "Dim"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            fontSize: Style.font.caption
            bordered: true
            onClicked: root.apex(["mouse", "-b", String(Math.max(10, root.mouseBrightness() - 15))])
          }
          Button {
            text: "Bright"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            fontSize: Style.font.caption
            bordered: true
            onClicked: root.apex(["mouse", "-b", String(Math.min(100, root.mouseBrightness() + 15))])
          }
        }

        Text {
          visible: !!root.status.mouse
          width: parent.width
          wrapMode: Text.WordWrap
          text: root.status.mouse && root.status.mouse.present
            ? (root.status.mouse.name || "Logitech mouse") + " follows the keyboard in match mode, goes dark when you are away, and breathes orange while Claude waits."
            : "No Logitech mouse reachable" + (root.status.mouse && root.status.mouse.error ? ": " + root.status.mouse.error : "") + "."
          color: root.bar.foreground
          opacity: 0.65
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
