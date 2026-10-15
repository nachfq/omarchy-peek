import QtQuick
import qs.Ui as Ui

Ui.BarWidget {
    id: root
    moduleName: 'nachfq.peek'
    readonly property bool opened: panel.opened
    readonly property bool popoutSwitchClosing: panel.popoutSwitchClosing
    readonly property real openPanelIndicatorWidth: button.width

    function open() { panel.open(); }
    function close() { panel.close(); }
    function closeForPopoutSwitch() { panel.closeForPopoutSwitch(); }
    function refresh() { panel.refresh(); }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    Ui.BarIconButton {
        id: button
        objectName: 'peekButton'
        anchors.fill: parent
        bar: root.bar
        text: '󰍉'
        tooltipText: 'Peek'
        onPressed: function(mouseButton) {
            if (mouseButton === Qt.LeftButton) panel.toggle();
        }
        Accessible.role: Accessible.Button
        Accessible.name: 'Peek'
        Accessible.onPressAction: panel.toggle()
    }

    Panel {
        id: panel
        objectName: 'peekPanel'
        bar: root.bar
        settings: root.settings
        anchorItem: button
        hostWidget: root
    }
}
