import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import Qt.labs.platform 1.1
import Qt5Compat.GraphicalEffects
import QtMultimedia

ApplicationWindow {
    id: win
    width: 1200
    height: 800
    minimumWidth: 600
    minimumHeight: 400
    visible: true
    flags: Qt.Window | Qt.FramelessWindowHint
    title: "PinVault"
    property url  placeholderSource: Qt.resolvedUrl("placeholder.svg")
    property var  allItems:         []     // unfiltered master list
    property int  selectedIndex:    -1
    property var  selectedItem:     null
    property string filterText:     ""
    property bool imageLoaded:      false
    property bool hideUnthumbnailed: false
    property string mediaFilter:    "All"  // "All" | "Video" | "Images"
    // progress tracking — bound directly into the progress bar fill width
    property int  thumbTotal: 1
    property int  thumbCount: 0
    // multi-select: uid → item object
    property var  selectedUids:      ({})
    property int  selectedCount:     0
    property int  lastClickedIndex:  -1
    // selectedItem already declared above — used by context menu / preview

    // ── Helpers ───────────────────────────────────────────────────
    function isVideoItem(item) {
        var ext = (item.detectedExt && item.detectedExt.length) ? item.detectedExt.toLowerCase() : ""
        if (!ext && item.path) { var p = item.path.split('.'); ext = "." + p[p.length - 1].toLowerCase() }
        return [".jpg",".jpeg",".png",".gif",".bmp",".webp",".tiff",".svg"].indexOf(ext) === -1
    }

    function rebuildModel() {
        var q = filterText.toLowerCase()
        grid.model.clear()
        for (var i = 0; i < allItems.length; i++) {
            var it = allItems[i]
            if (win.hideUnthumbnailed && !it.thumbUrl) continue
            if (win.mediaFilter === "Video"  && !win.isVideoItem(it)) continue
            if (win.mediaFilter === "Images" &&  win.isVideoItem(it)) continue
            if (!q || it.title.toLowerCase().indexOf(q) !== -1)
                grid.model.append(it)
        }
    }

    // ── View size state (cycle button) ─────────────────────────────
    property int viewSizeIndex: 1
    property var viewSizes: ["Small", "Medium", "Large"]

    function applyViewSize(label) {
        if (label === "Small")  grid.targetCellW = 80
        if (label === "Medium") grid.targetCellW = 160
        if (label === "Large")  grid.targetCellW = 240
    }

    function selectItem(idx) {
        selectedIndex = idx
        selectedItem  = (idx >= 0 && idx < grid.model.count) ? grid.model.get(idx) : null
    }

    function toggleSelect(item) {
        var uid = item.uid
        var copy = Object.assign({}, win.selectedUids)  // new object so QML fires changed
        if (copy[uid] !== undefined) {
            delete copy[uid]
            win.selectedCount--
        } else {
            copy[uid] = item
            win.selectedCount++
        }
        win.selectedUids = copy
        win.selectedItem = item
    }

    function clearSelection() {
        win.selectedUids       = ({})
        win.selectedCount      = 0
        win.selectedItem       = null
        win.selectedIndex      = -1
        win.lastClickedIndex   = -1
        grid.currentIndex      = -1
    }

    function selectAll() {
        var copy = {}
        for (var i = 0; i < grid.model.count; i++) {
            var it = grid.model.get(i)
            copy[it.uid] = it
        }
        win.selectedUids  = copy
        win.selectedCount = Object.keys(copy).length
    }

    function selectByRubberBand() {
        var rxMin = Math.min(grid.rbStartX, grid.rbCurX)
        var ryMin = Math.min(grid.rbStartY, grid.rbCurY)
        var rxMax = Math.max(grid.rbStartX, grid.rbCurX)
        var ryMax = Math.max(grid.rbStartY, grid.rbCurY)
        if (rxMax - rxMin < 6 && ryMax - ryMin < 6) return
        var copy = Object.assign({}, win.selectedUids)
        var changed = false
        var cols = grid.columns
        for (var i = 0; i < grid.model.count; i++) {
            var col = i % cols
            var row = Math.floor(i / cols)
            var cx = col * grid.cellWidth  + grid.cellWidth  / 2
            var cy = row * grid.cellHeight + grid.cellHeight / 2 - grid.contentY
            if (cx >= rxMin && cx <= rxMax && cy >= ryMin && cy <= ryMax) {
                var it = grid.model.get(i)
                copy[it.uid] = it
                changed = true
            }
        }
        if (changed) {
            win.selectedUids  = copy
            win.selectedCount = Object.keys(copy).length
        }
    }

    // ── Keyboard shortcuts ────────────────────────────────────────
    Shortcut { sequence: "Escape"; onActivated: { previewPopup.close(); contextMenu.close() } }
    Shortcut { sequence: "Ctrl+A"; onActivated: { if (win.imageLoaded) win.selectAll() } }
    Shortcut { sequence: "Return"; onActivated: { if (selectedItem) backend.openAsset(JSON.stringify({ path: selectedItem.path, inode: selectedItem.inode, offset: selectedItem.offset })) } }
    Shortcut { sequence: "Right";  onActivated: selectItem(Math.min(selectedIndex + 1, grid.model.count - 1)) }
    Shortcut { sequence: "Left";   onActivated: selectItem(Math.max(selectedIndex - 1, 0)) }
    Shortcut { sequence: "Down";   onActivated: selectItem(Math.min(selectedIndex + grid.columns, grid.model.count - 1)) }
    Shortcut { sequence: "Up";     onActivated: selectItem(Math.max(selectedIndex - grid.columns, 0)) }

    // ── Edge / corner resize handles (frameless window) ───────────────────
    Repeater {
        model: [
            { ex: 0,              ey: 0,              ew: 6,            eh: 6,            edge: Qt.TopEdge    | Qt.LeftEdge  },
            { ex: win.width - 6,  ey: 0,              ew: 6,            eh: 6,            edge: Qt.TopEdge    | Qt.RightEdge },
            { ex: 0,              ey: win.height - 6, ew: 6,            eh: 6,            edge: Qt.BottomEdge | Qt.LeftEdge  },
            { ex: win.width - 6,  ey: win.height - 6, ew: 6,            eh: 6,            edge: Qt.BottomEdge | Qt.RightEdge },
            { ex: 6,              ey: 0,              ew: win.width-12, eh: 4,            edge: Qt.TopEdge    },
            { ex: 6,              ey: win.height - 4, ew: win.width-12, eh: 4,            edge: Qt.BottomEdge },
            { ex: 0,              ey: 6,              ew: 4,            eh: win.height-12, edge: Qt.LeftEdge   },
            { ex: win.width - 4,  ey: 6,              ew: 4,            eh: win.height-12, edge: Qt.RightEdge  }
        ]
        MouseArea {
            parent: win.contentItem
            x: modelData.ex; y: modelData.ey
            width: modelData.ew; height: modelData.eh
            cursorShape: {
                var e = modelData.edge
                var TL = Qt.TopEdge|Qt.LeftEdge, TR = Qt.TopEdge|Qt.RightEdge
                var BL = Qt.BottomEdge|Qt.LeftEdge, BR = Qt.BottomEdge|Qt.RightEdge
                if (e === TL || e === BR) return Qt.SizeFDiagCursor
                if (e === TR || e === BL) return Qt.SizeBDiagCursor
                if (e === Qt.LeftEdge || e === Qt.RightEdge) return Qt.SizeHorCursor
                return Qt.SizeVerCursor
            }
            onPressed: win.startSystemResize(modelData.edge)
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#0f0f10"

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // ── Custom title bar ────────────────────────────────────────
            Rectangle {
                id: titleBar
                Layout.fillWidth: true
                height: 38
                color: "#090909"

                // Drag the window by the title bar
                DragHandler {
                    onActiveChanged: if (active) win.startSystemMove()
                }

                RowLayout {
                    anchors { fill: parent; leftMargin: 14; rightMargin: 0 }
                    spacing: 0

                    // App icon + name
                    Row {
                        spacing: 8
                        Layout.alignment: Qt.AlignVCenter
                        Rectangle {
                            width: 14; height: 14; radius: 3
                            color: "#3b82f6"
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Label {
                            text: "PinVault"
                            color: "#d0d0d0"; font.pointSize: 9; font.weight: Font.Medium
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    Item { Layout.fillWidth: true }

                    // Window controls: minimise / maximise / close
                    Row {
                        spacing: 0
                        Repeater {
                            model: [
                                { lbl: "–",  act: "min",   hc: "#2a2a2a" },
                                { lbl: "□",  act: "max",   hc: "#2a2a2a" },
                                { lbl: "✕",  act: "close", hc: "#c0392b" }
                            ]
                            delegate: Rectangle {
                                id: wcBtn
                                width: 46; height: 38
                                color: wcHover ? modelData.hc : "transparent"
                                property bool wcHover: false
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.lbl; color: "#aaa"; font.pointSize: 9
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onEntered: wcBtn.wcHover = true
                                    onExited:  wcBtn.wcHover = false
                                    onClicked: {
                                        if      (modelData.act === "close") Qt.quit()
                                        else if (modelData.act === "min")   win.showMinimized()
                                        else if (modelData.act === "max")
                                            win.visibility === Window.Maximized ? win.showNormal() : win.showMaximized()
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ── Toolbar strip ──────────────────────────────────────────
            Rectangle {
                Layout.fillWidth: true
                height: 54
                color: "#111113"

                RowLayout {
                    anchors { fill: parent; leftMargin: 12; rightMargin: 12 }
                    spacing: 10

                    Component.onCompleted: {
                        win.applyViewSize(win.viewSizes[win.viewSizeIndex])
                        try {
                            var s = JSON.parse(backend.getSettings())
                            win.hideUnthumbnailed = !!s.hide_unthumbnailed_assets
                        } catch(e) {}
                    }

                    // Primary action — Open Image / Dismount toggle
                    Rectangle {
                        width: 130; height: 34; radius: 6
                        color: openBtnHover
                               ? (win.imageLoaded ? "#9b2334" : "#2563eb")
                               : (win.imageLoaded ? "#7f1d1d" : "#1d4ed8")
                        property bool openBtnHover: false
                        Text {
                            anchors.centerIn: parent
                            text: win.imageLoaded ? "Dismount" : "Open Image"
                            color: "#fff"; font.pointSize: 10; font.bold: true
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: parent.openBtnHover = true
                            onExited:  parent.openBtnHover = false
                            onClicked: {
                                if (win.imageLoaded) backend.dismountImage()
                                else fileDialog.open()
                            }
                        }
                    }

                    // View size cycle button — immediately right of Open/Dismount
                    Rectangle {
                        id: viewCycleBtn
                        width: 100; height: 34; radius: 6
                        color: vcHover ? "#2a2a2e" : "#1c1c20"
                        border.color: "#333"; border.width: 1
                        property bool vcHover: false
                        Row {
                            anchors.centerIn: parent
                            spacing: 5
                            Text { text: "◫"; color: "#aaa"; font.pointSize: 10; anchors.verticalCenter: parent.verticalCenter }
                            Text {
                                text: win.viewSizes[win.viewSizeIndex]
                                color: "#ccc"; font.pointSize: 9
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: viewCycleBtn.vcHover = true
                            onExited:  viewCycleBtn.vcHover = false
                            onClicked: {
                                win.viewSizeIndex = (win.viewSizeIndex + 1) % win.viewSizes.length
                                win.applyViewSize(win.viewSizes[win.viewSizeIndex])
                            }
                        }
                    }

                    // Export selected button
                    Rectangle {
                        id: exportSelBtn
                        width: 80; height: 34; radius: 6
                        property bool expHov: false
                        property bool enabled: win.selectedCount > 0
                        color: enabled ? (expHov ? "#2a2a2e" : "#1c1c20") : "#141416"
                        border.color: enabled ? "#444" : "#272727"; border.width: 1
                        Text {
                            anchors.centerIn: parent
                            text: win.selectedCount > 1 ? "Export (" + win.selectedCount + ")" : "Export"
                            color: exportSelBtn.enabled ? "#ccc" : "#444"
                            font.pointSize: 9
                        }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            cursorShape: Qt.PointingHandCursor
                            onEntered: exportSelBtn.expHov = true
                            onExited:  exportSelBtn.expHov = false
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.RightButton) { exportBtnMenu.open(); return }
                                if (exportSelBtn.enabled) exportDialog.open()
                            }
                        }
                        Menu {
                            id: exportBtnMenu
                            MenuItem {
                                text: win.selectedCount > 0 ? "Export Selected (" + win.selectedCount + ")" : "Export Selected"
                                enabled: win.selectedCount > 0
                                onTriggered: exportDialog.open()
                            }
                            MenuItem {
                                text: "Select All  (" + grid.model.count + " files)"
                                enabled: grid.model.count > 0
                                onTriggered: win.selectAll()
                            }
                            MenuSeparator {}
                            MenuItem {
                                text: "Deselect All"
                                enabled: win.selectedCount > 0
                                onTriggered: win.clearSelection()
                            }
                        }
                    }

                    // Progress / status slot — always fills remaining width; bar and
                    // label are mutually exclusive so they never overlap.
                    Item {
                        Layout.fillWidth: true
                        implicitHeight: 36
                        Layout.alignment: Qt.AlignVCenter

                        // Scanning phase: bar + small count text below
                        Column {
                            id: scanningProgress
                            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                            spacing: 3
                            visible: false

                            // Custom bar: fill width is a live binding so rapid signals don't stall rendering
                            Item {
                                id: progress
                                width: parent.width
                                height: 7
                                Rectangle {
                                    width: parent.width
                                    height: parent.height
                                    radius: 3
                                    color: "#2a2a2a"
                                }
                                Rectangle {
                                    width: win.thumbTotal > 0
                                           ? Math.max(6, Math.round(parent.width * win.thumbCount / win.thumbTotal))
                                           : 6
                                    height: parent.height
                                    radius: 3
                                    color: "#3b82f6"
                                    Behavior on width { NumberAnimation { duration: 80; easing.type: Easing.OutQuad } }
                                }
                            }
                            Label {
                                id: progressCountLabel
                                width: parent.width
                                text: ""
                                font.pointSize: 7.5; color: "#555"
                                elide: Text.ElideRight
                            }
                        }

                        // Done / error / export phase: plain text
                        Label {
                            id: progressLabel
                            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                            text: ""
                            visible: false
                            font.pointSize: 9; color: "#888"
                            elide: Text.ElideRight
                        }
                    }

                    // Settings gear
                    Rectangle {
                        width: 34; height: 34; radius: 6
                        color: settHover ? "#2a2a2a" : "transparent"
                        property bool settHover: false
                        Text { anchors.centerIn: parent; text: "⚙"; color: "#aaa"; font.pointSize: 14 }
                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: parent.settHover = true
                            onExited:  parent.settHover = false
                            onClicked: settingsPopup.open()
                        }
                    }
                }
            }

            // ── Grid area ───────────────────────────────────────────────
            Item {
                id: gridArea
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 12

            GridView {
                    id: grid
                    anchors.fill: parent
                    model: ListModel {}

                    property int targetCellW: 240
                    Behavior on targetCellW { NumberAnimation { duration: 180 } }

                property int gap:     14
                property int columns: Math.max(1, Math.floor((width + gap) / (targetCellW + gap)))
                cellWidth:  Math.floor((width - (columns - 1) * gap) / columns)
                cellHeight: Math.floor(cellWidth * 0.66)

                    clip: true
                    focus: true
                    highlight: null
                    highlightFollowsCurrentItem: false

                ScrollBar.vertical: ScrollBar {
                    width: 10
                    opacity: grid.sbOpacity
                    Behavior on opacity { NumberAnimation { duration: 220 } }
                }
                property real sbOpacity: 0.06
                Behavior on sbOpacity { NumberAnimation { duration: 220 } }

                // rubber-band state lives here so selectByRubberBand() can read it
                property real rbStartX:   0
                property real rbStartY:   0
                property real rbCurX:     0
                property real rbCurY:     0
                property bool rbDragging: false

                // ── Delegate ────────────────────────────────────────────
                delegate: Item {
                    id: delegateRoot
                    width:  grid.cellWidth
                    height: grid.cellHeight

                    property bool isSelected: win.selectedCount >= 0 && win.selectedUids[uid] !== undefined
                    property bool hovered:    false

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Math.floor(grid.gap / 2)
                        spacing: 0

                        // thumbnail container
                        Item {
                            id: thumbContainer
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.alignment: Qt.AlignHCenter
                            Item {
                                id: thumbWrapper
                                anchors.fill: parent

                                // Background / border card
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: "#111"
                                    border.color: "#222"
                                }

                                // Loading indicator — visible until thumbnail arrives
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: "#1a1a1f"
                                    visible: !thumbUrl || thumbUrl.length === 0

                                    Text {
                                        anchors.centerIn: parent
                                        color: "#666"
                                        font.pointSize: 9
                                        font.bold: true

                                        property int dotCount: 0
                                        text: "Loading" + Array(dotCount + 1).join(".")

                                        Timer {
                                            running: !thumbUrl || thumbUrl.length === 0
                                            repeat: true
                                            interval: 400
                                            onTriggered: parent.dotCount = (parent.dotCount + 1) % 4
                                        }
                                    }
                                }

                                // Selection ring — sits on the thumb itself, not the cell
                                Rectangle {
                                    anchors { fill: parent; margins: -2 }
                                    radius: 10
                                    color: "transparent"
                                    border.color: delegateRoot.isSelected ? "#44aaff" : "transparent"
                                    border.width: 2
                                    z: 20
                                    enabled: false
                                }

                                // The thumbnail image (clipped to the mask layer below)
                                Image {
                                    id: thumb
                                    anchors.fill: parent
                                    fillMode: Image.PreserveAspectCrop
                                    // Only load a real URL — don't fall back to placeholder here;
                                    // the pulse rectangle handles the "not loaded yet" state.
                                    source: thumbUrl && thumbUrl.length ? thumbUrl : ""
                                    cache: true
                                    asynchronous: true
                                    smooth: true
                                    visible: false   // hidden; OpacityMask will render it
                                }

                                // Rounded mask shape
                                Rectangle {
                                    id: thumbMask
                                    anchors.fill: parent
                                    radius: 8
                                    visible: false
                                }

                                // Apply the mask — rounds the thumbnail corners properly
                                OpacityMask {
                                    anchors.fill: thumb
                                    source: thumb
                                    maskSource: thumbMask
                                    // Only render when we actually have a thumbnail
                                    visible: thumbUrl && thumbUrl.length > 0
                                }

                                // Audio badge
                                Rectangle {
                                    anchors { right: parent.right; bottom: parent.bottom; margins: 5 }
                                    width: 22; height: 22; radius: 11
                                    color: "#cc000000"
                                    visible: hasAudio === true
                                    Text {
                                        anchors.centerIn: parent
                                        text: "♪"
                                        color: "#fff"
                                        font.pointSize: 9
                                    }
                                }

                                // Hover tint
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 8
                                    color: delegateRoot.hovered ? "#26ffffff" : "transparent"
                                    enabled: false
                                }

                                // MouseArea — single click toggles selection, double-click opens preview
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                    cursorShape: Qt.PointingHandCursor
                                    z: 100
                                    onEntered: { delegateRoot.hovered = true;  grid.sbOpacity = 0.6 }
                                    onExited:  { delegateRoot.hovered = false }

                                    onClicked: function(mouse) {
                                        var item = grid.model.get(index)
                                        if (mouse.button === Qt.RightButton) {
                                            win.selectedItem = item
                                            contextMenu.open()
                                            return
                                        }
                                        if ((mouse.modifiers & Qt.ShiftModifier) && win.lastClickedIndex >= 0) {
                                            // Shift+click: range select from last clicked to here
                                            var from = Math.min(win.lastClickedIndex, index)
                                            var to   = Math.max(win.lastClickedIndex, index)
                                            var copy = Object.assign({}, win.selectedUids)
                                            for (var i = from; i <= to; i++) {
                                                var it = grid.model.get(i)
                                                copy[it.uid] = it
                                            }
                                            win.selectedUids  = copy
                                            win.selectedCount = Object.keys(copy).length
                                        } else {
                                            // Normal or Ctrl+click: toggle individual
                                            win.toggleSelect(item)
                                            win.lastClickedIndex = index
                                        }
                                    }

                                    onDoubleClicked: function(mouse) {
                                        if (mouse.button !== Qt.LeftButton) return
                                        previewPopup.showItem(grid.model.get(index))
                                    }
                                }
                            }
                        }
                        // No filename label — clean thumbnail-only appearance
                    }

                }
                // area to detect hover for scrollbar reveal
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    acceptedButtons: Qt.NoButton
                    onEntered: grid.sbOpacity = 0.6
                    onExited:  grid.sbOpacity = 0.06
                }
                onContentYChanged: { sbOpacity = 0.6; _hideTimer.restart() }

                Timer {
                    id: _hideTimer
                    interval: 700
                    repeat: false
                    onTriggered: grid.sbOpacity = 0.06
                }
            }      // GridView

                // ── Rubber-band overlay ─ sibling of GridView so Flickable
                //    doesn't steal the drag gesture ─────────────────────
                MouseArea {
                    anchors.fill: parent
                    z: 10
                    propagateComposedEvents: true
                    hoverEnabled: false
                    preventStealing: grid.rbDragging

                    onPressed: function(mouse) {
                        // Ignore presses inside the scrollbar zone (right ~12 px)
                        if (mouse.x >= parent.width - 12) { mouse.accepted = false; return }
                        // Only start rubber-band when pressing on empty space
                        var cellUnder = grid.itemAt(mouse.x, mouse.y + grid.contentY)
                        if (cellUnder) { mouse.accepted = false; return }
                        grid.rbStartX   = mouse.x
                        grid.rbStartY   = mouse.y
                        grid.rbCurX     = mouse.x
                        grid.rbCurY     = mouse.y
                        grid.rbDragging = false
                        mouse.accepted  = true
                    }
                    onPositionChanged: function(mouse) {
                        if (!mouse.accepted) return
                        grid.rbCurX = mouse.x
                        grid.rbCurY = mouse.y
                        if (!grid.rbDragging &&
                                (Math.abs(mouse.x - grid.rbStartX) > 8 ||
                                 Math.abs(mouse.y - grid.rbStartY) > 8))
                            grid.rbDragging = true
                    }
                    onReleased: function(mouse) {
                        if (grid.rbDragging) win.selectByRubberBand()
                        grid.rbDragging = false
                    }
                    onCanceled: { grid.rbDragging = false }
                }

                Rectangle {
                    visible: grid.rbDragging
                    x:      Math.min(grid.rbStartX, grid.rbCurX)
                    y:      Math.min(grid.rbStartY, grid.rbCurY)
                    width:  Math.abs(grid.rbCurX - grid.rbStartX)
                    height: Math.abs(grid.rbCurY - grid.rbStartY)
                    color:  "#2044aaff"
                    border.color: "#44aaff"
                    border.width: 1
                    radius: 2
                    z: 20
                    enabled: false
                }

        }          // Item (grid area)
    }              // ColumnLayout
}                  // Rectangle (dark background)

    // ── Right-click context menu ─────────────────────────────────
    Menu {
        id: contextMenu

        MenuItem {
            text: win.selectedCount > 0 ? "Export Selected (" + win.selectedCount + ")" : "Export Selected"
            enabled: win.selectedCount > 0
            onTriggered: exportDialog.open()
        }
        MenuItem {
            text: "Select All (" + grid.model.count + " files)"
            enabled: grid.model.count > 0
            onTriggered: win.selectAll()
        }
        MenuSeparator {}
        MenuItem {
            text: "Deselect All"
            enabled: win.selectedCount > 0
            onTriggered: win.clearSelection()
        }
    }

    // ── Preview popup (embedded video player) ─────────────────
    Popup {
        id: previewPopup
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        x: parent.width  / 2 - width  / 2
        y: parent.height / 2 - height / 2
        width:  Math.min(parent.width  - 80, 1000)
        height: Math.min(parent.height - 80, 700)
        padding: 0

        property var    previewItem:      null
        property string previewLocalPath: ""
        property bool   extracting:       false

        // true for video/audio, false for still images (no play overlay needed)
        property bool isVideoItem: {
            var ext = (previewItem && previewItem.detectedExt) ? previewItem.detectedExt.toLowerCase() : ""
            if (!ext && previewItem && previewItem.path) {
                var parts = previewItem.path.split('.')
                ext = "." + parts[parts.length - 1].toLowerCase()
            }
            var imageExts = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg"]
            return imageExts.indexOf(ext) === -1
        }

        function showItem(it) {
            previewItem      = it
            previewLocalPath = ""
            extracting       = false
            mediaPlayer.stop()
            mediaPlayer.source = ""
            open()
        }

        onClosed: {
            mediaPlayer.pause()
            mediaPlayer.source = ""
            previewLocalPath   = ""
            extracting         = false
        }

        function triggerPlay() {
            if (previewLocalPath !== "") {
                if (mediaPlayer.source === "")
                    mediaPlayer.source = "file:///" + previewLocalPath.replace(/\\/g, "/")
                mediaPlayer.play()
            } else if (!extracting && previewItem !== null) {
                extracting = true
                backend.extractPreview(JSON.stringify({
                    path: previewItem.path, inode: previewItem.inode,
                    offset: previewItem.offset, uid: previewItem.uid,
                    detectedExt: previewItem.detectedExt || ""
                }))
            }
        }

        background: Rectangle { color: "#181818"; radius: 12 }

        MediaPlayer {
            id: mediaPlayer
            videoOutput: videoOut
            audioOutput: AudioOutput {}
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 10

            // Title bar
            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: previewPopup.previewItem ? previewPopup.previewItem.title : ""
                    color: "#fff"; font.pointSize: 12; font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Button {
                    text: "✕"; flat: true
                    onClicked: previewPopup.close()
                    implicitWidth: 32; implicitHeight: 32
                }
            }

            // Media area — fills all remaining space
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // Poster frame — visible before extraction/playback
                Image {
                    anchors.fill: parent
                    fillMode: Image.PreserveAspectFit
                    source: (previewPopup.previewItem && previewPopup.previewItem.thumbUrl
                             && previewPopup.previewItem.thumbUrl.length)
                            ? previewPopup.previewItem.thumbUrl : win.placeholderSource
                    smooth: true; asynchronous: true; cache: false
                    visible: mediaPlayer.playbackState === MediaPlayer.StoppedState
                             && previewPopup.previewLocalPath === ""
                }

                // Live video output
                VideoOutput {
                    id: videoOut
                    anchors.fill: parent
                    visible: previewPopup.previewLocalPath !== ""
                             || mediaPlayer.playbackState !== MediaPlayer.StoppedState
                }

                // Audio-only badge
                Rectangle {
                    anchors.centerIn: parent
                    width: 64; height: 64; radius: 32
                    color: "#aa000000"
                    visible: previewPopup.previewItem !== null
                             && previewPopup.previewItem.hasAudio === true
                             && !(previewPopup.previewItem.thumbUrl
                                  && previewPopup.previewItem.thumbUrl.length)
                    Text { anchors.centerIn: parent; text: "♪"; color: "#fff"; font.pointSize: 22 }
                }

                // Extracting spinner overlay
                Rectangle {
                    anchors.fill: parent; color: "#cc000000"
                    visible: previewPopup.extracting
                    Column {
                        anchors.centerIn: parent; spacing: 10
                        BusyIndicator {
                            running: previewPopup.extracting
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                        Label {
                            text: "Extracting…"; color: "#ccc"; font.pointSize: 10
                            anchors.horizontalCenter: parent.horizontalCenter
                        }
                    }
                }

                // Click-to-play overlay (when stopped and not extracting, video only)
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    visible: previewPopup.isVideoItem
                             && !previewPopup.extracting
                             && mediaPlayer.playbackState !== MediaPlayer.PlayingState
                    onClicked: previewPopup.triggerPlay()
                    Rectangle {
                        anchors.centerIn: parent
                        width: 64; height: 64; radius: 32; color: "#aa000000"
                        visible: !previewPopup.extracting
                        Text { anchors.centerIn: parent; text: "▶"; color: "#fff"; font.pointSize: 22 }
                    }
                }

                // Tap-to-pause overlay (while playing)
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    visible: mediaPlayer.playbackState === MediaPlayer.PlayingState
                    onClicked: mediaPlayer.pause()
                }
            }

            // ── Transport bar (video/audio only) ────────────────────────
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                visible: previewPopup.isVideoItem

                // Play / Pause
                Rectangle {
                    width: 32; height: 32; radius: 6
                    color: ppHov ? "#2a2a2e" : "#1c1c20"
                    border.color: "#444"; border.width: 1
                    property bool ppHov: false
                    Text {
                        anchors.centerIn: parent
                        text: mediaPlayer.playbackState === MediaPlayer.PlayingState ? "⏸" : "▶"
                        color: "#fff"; font.pointSize: 11
                    }
                    MouseArea {
                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onEntered: parent.ppHov = true; onExited: parent.ppHov = false
                        onClicked: {
                            if (mediaPlayer.playbackState === MediaPlayer.PlayingState) mediaPlayer.pause()
                            else previewPopup.triggerPlay()
                        }
                    }
                }

                // Stop
                Rectangle {
                    width: 32; height: 32; radius: 6
                    color: stHov ? "#2a2a2e" : "#1c1c20"
                    border.color: "#444"; border.width: 1
                    property bool stHov: false
                    Text { anchors.centerIn: parent; text: "⏹"; color: "#fff"; font.pointSize: 11 }
                    MouseArea {
                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onEntered: parent.stHov = true; onExited: parent.stHov = false
                        onClicked: mediaPlayer.stop()
                    }
                }

                // Seek slider
                Slider {
                    id: seekSlider
                    Layout.fillWidth: true
                    from: 0; to: Math.max(mediaPlayer.duration, 1)
                    value: mediaPlayer.position
                    onMoved: mediaPlayer.setPosition(value)
                }

                // Time
                Label {
                    function fmt(ms) {
                        var s = Math.floor(ms / 1000)
                        var m = Math.floor(s / 60); s = s % 60
                        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s
                    }
                    text: fmt(mediaPlayer.position) + " / " + fmt(mediaPlayer.duration)
                    color: "#888"; font.pointSize: 8; font.family: "Courier New"
                }

                // Export
                Rectangle {
                    width: 70; height: 32; radius: 6
                    color: expHov ? "#2a2a2e" : "#1c1c20"
                    border.color: "#444"; border.width: 1
                    property bool expHov: false
                    Text { anchors.centerIn: parent; text: "Export…"; color: "#ccc"; font.pointSize: 9 }
                    MouseArea {
                        anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onEntered: parent.expHov = true; onExited: parent.expHov = false
                        onClicked: { previewPopup.close(); exportDialog.open() }
                    }
                }
            }
        }
    }

    // ── Export folder dialog ──────────────────────────────────
    FolderDialog {
        id: exportDialog
        title: "Choose export folder"
        onAccepted: {
            var uids = Object.keys(win.selectedUids)
            if (uids.length === 0 && win.selectedItem) {
                // fallback: single item from preview popup or context menu
                backend.exportAsset(
                    JSON.stringify({ path: win.selectedItem.path, inode: win.selectedItem.inode,
                                     offset: win.selectedItem.offset, detectedExt: win.selectedItem.detectedExt || "" }),
                    folder)
                return
            }
            for (var i = 0; i < uids.length; i++) {
                var it = win.selectedUids[uids[i]]
                if (it) backend.exportAsset(
                    JSON.stringify({ path: it.path, inode: it.inode,
                                     offset: it.offset, detectedExt: it.detectedExt || "" }),
                    folder)
            }
            win.clearSelection()
        }
    }

    // ── Open image file dialog ────────────────────────────────
    FileDialog {
        id: fileDialog
        title: "Open forensic image"
        onAccepted: {
            win.allItems     = []
            win.selectedIndex = -1
            win.selectedItem  = null
            win.filterText   = ""
            grid.model.clear()
            backend.openImage(file)
        }
    }

    Popup {
        id: settingsPopup
        x: parent.width / 2 - width / 2
        y: parent.height / 2 - height / 2
        width: 420; height: 290
        modal: true
        background: Rectangle { color: "#121212"; radius: 8 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8
            Label { text: "Settings"; font.bold: true; color: "#fff" }
            RowLayout {
                spacing: 8
                CheckBox { id: hideAssets }
                Label { text: "Hide unthumbnailed .asset files"; color: "#ccc" }
            }
            RowLayout {
                spacing: 8
                CheckBox { id: saveAssetAsMp4 }
                Label { text: "Save .asset as .mp4 on export"; color: "#ccc" }
            }
            // Media type filter
            RowLayout {
                spacing: 4
                Layout.fillWidth: true
                Label { text: "Show:"; color: "#aaa"; rightPadding: 4 }
                ButtonGroup { id: mediaFilterGroup }
                Repeater {
                    model: ["All", "Video", "Images"]
                    RadioButton {
                        text: modelData
                        checked: win.mediaFilter === modelData
                        ButtonGroup.group: mediaFilterGroup
                        contentItem: Text {
                            text: parent.text
                            color: parent.checked ? "#fff" : "#888"
                            leftPadding: parent.indicator.width + 4
                            font.pointSize: 9
                            verticalAlignment: Text.AlignVCenter
                        }
                        onClicked: { win.mediaFilter = modelData; win.rebuildModel() }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                Button {
                    text: "Save"
                    onClicked: {
                        backend.setSetting('hide_unthumbnailed_assets', hideAssets.checked ? 'true' : 'false')
                        backend.setSetting('save_asset_as_mp4', saveAssetAsMp4.checked  ? 'true' : 'false')
                        win.hideUnthumbnailed = hideAssets.checked
                        if (hideAssets.checked) win.rebuildModel()
                        settingsPopup.close()
                    }
                }
            }
        }
        onOpened: {
            var s = JSON.parse(backend.getSettings())
            hideAssets.checked     = !!s.hide_unthumbnailed_assets
            saveAssetAsMp4.checked = !!s.save_asset_as_mp4
        }
    }

    // ── Backend connections ─────────────────────────────────────────
    Connections {
        target: backend

        function onAssetFound(assetJson) {
            var obj  = JSON.parse(assetJson)
            var item = {
                title:       obj.path.split('/').pop(),
                path:        obj.path,
                inode:       obj.inode,
                offset:      obj.offset,
                uid:         obj.uid || (obj.offset + "_" + obj.inode),
                thumbUrl:    "",
                hasAudio:    false,
                detectedExt: ""
            }
            win.allItems.push(item)
            if (!win.filterText) {
                grid.model.append(item)
            } else if (item.title.toLowerCase().indexOf(win.filterText) !== -1) {
                grid.model.append(item)
            }
            // show bar (not label) during discovery
            scanningProgress.visible = true
        }

        function onScanStarted(total) {
            win.imageLoaded      = true
            win.thumbTotal       = total > 0 ? total : 1
            win.thumbCount       = 0
            scanningProgress.visible = true
            progressLabel.visible    = false
            progressCountLabel.text  = "Thumbnailing 0/" + total
        }

        function onScanProgress(count) {
            win.thumbCount = count
            var total = win.thumbTotal
            var pct = total > 0 ? Math.floor((count / total) * 100) : 0
            progressCountLabel.text = "Thumbnailing " + count + "/" + total + " (" + pct + "%)"
        }

        function onThumbnailReady(uid, thumb, hasAudio, detectedExt) {
            var url = ""
            if (thumb) {
                if (thumb.indexOf("image://") === 0)
                    url = thumb + (thumb.indexOf("?") === -1 ? "?v=" : "&v=") + Date.now()
                else
                    url = "file:///" + thumb.replace(/\\/g, "/") + "?v=" + Date.now()
            }
            // Update master list (keyed by uid)
            for (var j = 0; j < win.allItems.length; j++) {
                if (win.allItems[j].uid === uid) {
                    win.allItems[j].thumbUrl    = url
                    win.allItems[j].hasAudio    = hasAudio
                    win.allItems[j].detectedExt = detectedExt
                    break
                }
            }
            // Update visible model (keyed by uid)
            for (var i = 0; i < grid.model.count; i++) {
                var it = grid.model.get(i)
                if (it.uid === uid) {
                    var shouldRemove = (url === "" && win.hideUnthumbnailed)
                    if (!shouldRemove && win.mediaFilter !== "All") {
                        var isVid = win.isVideoItem({ detectedExt: detectedExt, path: it.path })
                        shouldRemove = (win.mediaFilter === "Video" && !isVid) || (win.mediaFilter === "Images" && isVid)
                    }
                    if (shouldRemove) {
                        grid.model.remove(i, 1)
                    } else {
                        grid.model.set(i, {
                            title: it.title, path: it.path, inode: it.inode,
                            offset: it.offset, uid: it.uid,
                            thumbUrl: url, hasAudio: hasAudio, detectedExt: detectedExt
                        })
                    }
                    break
                }
            }
            // Keep preview popup live
            if (win.selectedItem && win.selectedItem.uid === uid) {
                win.selectedItem = {
                    path: win.selectedItem.path, title: win.selectedItem.title,
                    inode: win.selectedItem.inode, offset: win.selectedItem.offset,
                    uid: uid, thumbUrl: url, hasAudio: hasAudio, detectedExt: detectedExt
                }
                if (previewPopup.visible) previewPopup.previewItem = win.selectedItem
            }
        }

        function onScanFinished() {
            scanningProgress.visible = false
            progressLabel.visible    = true
            progressLabel.text = "Scan complete — " + win.allItems.length + " files"
            if (win.mediaFilter !== "All") win.rebuildModel()
        }

        function onScanError(msg) {
            scanningProgress.visible = false
            progressLabel.visible    = true
            progressLabel.text = "Error: " + msg
        }

        function onExportFinished(destPath) {
            progressLabel.text    = "Exported → " + destPath.replace(/\//g, "\\")
            progressLabel.visible = true
        }

        function onExportError(msg) {
            progressLabel.text    = "Export error: " + msg
            progressLabel.visible = true
        }

        function onPreviewReady(uid, localPath) {
            if (previewPopup.previewItem && previewPopup.previewItem.uid === uid) {
                previewPopup.extracting = false
                if (localPath !== "") {
                    previewPopup.previewLocalPath = localPath
                    mediaPlayer.source = "file:///" + localPath.replace(/\\/g, "/")
                    mediaPlayer.play()
                } else {
                    previewPopup.extracting = false
                }
            }
        }

        function onImageCleared() {
            win.imageLoaded   = false
            win.allItems      = []
            win.thumbCount    = 0
            win.thumbTotal    = 1
            win.clearSelection()
            win.filterText    = ""
            grid.model.clear()
            scanningProgress.visible = false
            progressLabel.visible    = false
            progressLabel.text       = ""
        }
    }

}
