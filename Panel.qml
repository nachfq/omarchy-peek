pragma ComponentBehavior: Bound
import QtQuick
import qs.Ui as Ui
import qs.Commons
import 'Model.js' as Model

Ui.Panel {
    id: root
    moduleName: 'nachfq.peek'
    manageIpc: false
    property Item anchorItem: null
    property var hostWidget: null
    property int selectedSection: -1
    readonly property alias collector: collector

    function refresh() {
        if (!opened) return;
        if (selectedSection === -1) collector.overview(settings);
        else collector.request(Model.sections[selectedSection], settings);
    }
    function selectSection(index) {
        if (index === selectedSection) return;
        selectedSection = index;
        content.resetView();
        refresh();
    }
    onOpenedChanged: {
        if (opened) { content.resetView(); refresh(); }
        else collector.cancel();
    }
    Collector { id: collector }

    Ui.KeyboardPanel {
        id: popup
        anchorItem: root.anchorItem
        owner: root.hostWidget || root
        bar: root.bar
        open: root.opened
        focusTarget: content.initialFocus
        contentWidth: fittedContentWidth(Style.space(880))
        contentHeight: fittedContentHeight(Style.space(580))

        PeekContent {
            id: content
            objectName: 'peekContent'
            anchors.fill: parent
            selectedSection: root.selectedSection
            snapshots: collector.snapshots
            errors: collector.errors
            currentSection: collector.currentSection
            snapshot: collector.snapshot
            loading: collector.loading
            error: collector.error
            onSectionRequested: function(index) { root.selectSection(index); }
            onRefreshRequested: root.refresh()
            onCloseRequested: root.close()
        }
    }
}
