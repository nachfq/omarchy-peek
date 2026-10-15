import QtQuick
import Quickshell

// Only the layer-shell surface is replaced offscreen. The plugin's actual
// Panel, request owner, content, and native Omarchy controls remain in use.
FloatingWindow {
    id: root
    objectName: 'peekSurface'
    property int testAvailableWidth: 900
    required property Item anchorItem
    required property QtObject bar
    property var owner: null
    property bool open: false
    property Item focusTarget: null
    property int contentWidth: 880
    property int contentHeight: 600
    property int padding: 16
    default property alias panelContent: holder.data
    function fittedContentWidth(desired) { return Math.min(desired, testAvailableWidth); }
    function fittedContentHeight(desired) { return Math.min(desired + padding * 2, 660); }
    implicitWidth: contentWidth
    implicitHeight: contentHeight
    visible: open
    color: '#181b20'
    onOpenChanged: {
        if (bar) {
            if (open) bar.requestPopout(owner);
            else bar.releasePopout(owner);
        }
        if (open) Qt.callLater(function() { if (root.open && root.focusTarget) root.focusTarget.forceActiveFocus(); });
    }
    Rectangle {
        id: holder
        color: root.color
        x: root.padding
        y: root.padding
        width: root.contentWidth - root.padding * 2
        height: root.contentHeight - root.padding * 2
    }
}
