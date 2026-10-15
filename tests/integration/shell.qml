import QtQuick
import QtTest
import Quickshell
import Quickshell.Io
import qs.Ui as Ui

ShellRoot {
    FileView {
        id: commandPid
        path: Quickshell.env('PEEK_CHILD_PID')
        watchChanges: true
        onFileChanged: reload()
    }
    Ui.PluginBarApi {
        id: fixtureBar
        pluginId: 'nachfq.peek'
        moduleName: 'nachfq.peek'
        barSize: 32
        foreground: '#eeeeee'
        barForeground: '#eeeeee'
        fontFamily: 'monospace'
        _requestPopout: function(owner) { activePopout = owner; }
        _releasePopout: function(owner) { if (activePopout === owner) activePopout = null; }
    }
    PanelWindow {
        anchors { top: true; left: true; right: true }
        implicitHeight: 32
        exclusionMode: ExclusionMode.Ignore
        color: 'transparent'
        visible: true
        BarWidget {
            id: widget
            bar: fixtureBar
            settings: JSON.parse(Quickshell.env('PEEK_TEST_OPTIONS'))
            anchors.horizontalCenter: parent.horizontalCenter
            width: implicitWidth
            height: implicitHeight
        }
        TestCase {
            name: 'PeekIntegratedRuntime'
            when: true
            function ensure(condition, message) {
                if (!condition) console.warn('PEEK_INTEGRATION_ASSERT ' + message);
                verify(condition, message);
            }
            function test_runtime() {
                try { exerciseRuntime(); }
                catch (error) { console.warn('PEEK_INTEGRATION_ERROR ' + error + ' ' + error.stack); throw error; }
            }
            function exerciseRuntime() {
                var panel = findChild(widget, 'peekPanel');
                var content = findChild(panel, 'peekContent');
                verify(panel !== null && content !== null);
                var cancelTest = Quickshell.env('PEEK_TEST_MODE') === 'cancel';
                var sections = ['docker', 'services', 'processes', 'worktrees', 'disk'];
                for (var index = 0; index < (cancelTest ? 1 : sections.length); index++) {
                    panel.selectedSection = index;
                    widget.open();
                    verify(widget.opened);
                    if (cancelTest) {
                        tryVerify(function() { return commandPid.text().trim() !== ''; }, 5000);
                        verify(panel.collector.loading);
                    } else {
                        tryCompare(panel.collector, 'loading', false, 65000);
                        ensure(widget.opened, 'Popup dismissed during manual check');
                        compare(panel.collector.error, '');
                        verify(panel.collector.snapshot !== null);
                        compare(panel.collector.snapshot.section, sections[index]);
                        console.log('PEEK_REAL_SECTION ' + sections[index] + ' ' + panel.collector.snapshot.status);
                    }
                    if (Quickshell.env('PEEK_TEST_WAYLAND') === '1') {
                        tryVerify(function() { return content.initialFocus !== null && content.initialFocus.activeFocus; }, 3000);
                        var surface = content.QsWindow.window;
                        ensure(surface.backingWindowVisible, 'native surface visible');
                        ensure(surface.cardOrigin.x >= 0 && surface.cardOrigin.y >= 0, 'card origin');
                        ensure(surface.cardOrigin.x + surface.contentWidth <= surface.screenW, 'card width');
                        ensure(surface.cardOrigin.y + surface.contentHeight <= surface.screenH, 'card height');
                        content.initialFocus.forceActiveFocus();
                        keyClick(Qt.Key_Escape);
                    } else widget.close();
                    tryCompare(widget, 'opened', false);
                    tryCompare(panel.collector, 'active', false, 5000);
                    wait(200);
                    verify(!panel.collector.active && !panel.collector.loading);
                }
            }
            function cleanupTestCase() {
                widget.close();
                console.log('PEEK_INTEGRATION_RESULT ' + JSON.stringify({passed: qtest_results.passCount, failed: qtest_results.failCount}));
            }
        }
    }
}
