pragma ComponentBehavior: Bound
import QtQuick
import QtTest
import Quickshell
import qs.Ui as Ui
import 'Model.js' as Model

ShellRoot {
    id: root
    Ui.PluginBarApi {
        id: fakeBar
        pluginId: 'nachfq.peek'
        moduleName: 'nachfq.peek'
        barSize: 32
        foreground: '#eeeeee'
        barForeground: '#eeeeee'
        fontFamily: 'monospace'
        _requestPopout: function(owner) {
            if (activePopout && activePopout !== owner) activePopout.closeForPopoutSwitch();
            activePopout = owner;
        }
        _releasePopout: function(owner) { if (activePopout === owner) activePopout = null; }
    }
    Component { id: temporaryPanel; Panel { bar: fakeBar } }
    FloatingWindow {
        implicitWidth: 160
        implicitHeight: 50
        visible: true
        BarWidget {
            id: widget
            bar: fakeBar
            width: implicitWidth
            height: implicitHeight
        }
        TestCase {
            name: 'PeekNativeInput'
            when: true
            property var panel: null
            property var content: null
            function ensure(condition, message) {
                if (!condition) console.warn('PEEK_UI_ASSERT ' + qtest_results.functionName + ': ' + message);
                verify(condition, message);
            }
            function equal(actual, expected) {
                if (actual !== expected) console.warn('PEEK_UI_ASSERT ' + qtest_results.functionName + ': actual=' + actual + ' expected=' + expected);
                compare(actual, expected);
            }
            function child(name) {
                var found = findChild(content, name);
                ensure(found !== null, 'Missing UI child: ' + name);
                return found;
            }
            function keySequence(text) { for (var i = 0; i < text.length; i++) keyClick(text[i]); }
            function click(item) { mouseClick(item, item.width / 2, item.height / 2); }
            function waitSnapshot() {
                tryCompare(panel.collector, 'loading', false, 5000);
                ensure(panel.collector.error === '', panel.collector.error);
                ensure(panel.collector.snapshot !== null, 'Expected snapshot');
            }
            function open() {
                click(findChild(widget, 'peekButton'));
                ensure(widget.opened);
                waitSnapshot();
            }
            function init() {
                panel = findChild(widget, 'peekPanel');
                content = findChild(panel, 'peekContent');
                widget.close();
                tryCompare(panel.collector, 'active', false);
                panel.selectedSection = 0;
                widget.settings = {repositoryRoots: ['/fixture/space and 日本語'], diskPaths: [], discoveryDepth: 2};
                wait(20);
            }
            function cleanup() {
                console.log('PEEK_UI_CASE ' + qtest_results.functionName + ' failed=' + qtest_results.failed);
                widget.close();
                tryCompare(panel.collector, 'active', false, 5000);
            }
            onCompletedChanged: if (completed)
                console.log('PEEK_UI_RESULT ' + JSON.stringify({passed: qtest_results.passCount, failed: qtest_results.failCount}))

            function test_barPointerAndOnDemand() {
                ensure(!widget.opened);
                ensure(!panel.collector.active);
                wait(150);
                ensure(!panel.collector.active);
                open();
                equal(panel.collector.snapshot.section, 'docker');
                equal(child('snapshotTimestamp').text, 'Collected 2026-01-01T12:00:00Z');
                var first = panel.collector.snapshot;
                wait(180);
                equal(panel.collector.snapshot, first); // No polling or spontaneous refresh.
                click(findChild(widget, 'peekButton'));
                ensure(!widget.opened);
            }
            function test_keyboardSectionRefreshAndEscape() {
                open();
                var services = child('section1');
                services.forceActiveFocus();
                keyClick(Qt.Key_Return);
                equal(panel.selectedSection, 1);
                waitSnapshot();
                ensure(child('snapshotStatus').text.indexOf('Partial') === 0);
                var refresh = child('refreshButton');
                refresh.forceActiveFocus();
                keyClick(Qt.Key_Space);
                ensure(panel.collector.loading);
                waitSnapshot();
                keyClick(Qt.Key_Escape);
                ensure(!widget.opened);
            }
            function test_allSectionsAndStates() {
                open();
                for (var index = 1; index < 4; index++) {
                    click(child('section' + index));
                    waitSnapshot();
                    equal(panel.collector.snapshot.section, Model.sections[index]);
                    if (index === 2) ensure(child('snapshotStatus').text.indexOf('Unavailable') === 0);
                    if (index === 3) ensure(content.displayRows.some(function(row) { return row.text === 'No entries.'; }));
                }
            }
            function test_localFilteringAndLiteralText() {
                open();
                var original = panel.collector.snapshot;
                var filter = child('localFilter');
                click(filter);
                keySequence('literal');
                equal(panel.collector.snapshot, original);
                equal(content.displayRows.filter(function(row) { return row.kind === 'row'; }).length, 1);
                var textRow = content.displayRows.filter(function(row) { return row.kind === 'row'; })[0];
                equal(textRow.cells[0], 'sample <b>literal</b>');
                ensure(textRow.cells[1].indexOf('日本語') >= 0);
                filter.selectAll();
                keySequence('no such fixture');
                ensure(content.displayRows.some(function(row) { return row.text === 'No matching rows.'; }));
                ensure(!panel.collector.active);
            }
            function test_nativeTabAndScroll() {
                open();
                child('section0').forceActiveFocus();
                keyClick(Qt.Key_Tab);
                ensure(child('section1').activeFocus);
                var list = child('snapshotRows');
                ensure(list.contentHeight > list.height);
                mouseWheel(list, list.width - 20, list.height / 2, 0, -480);
                tryVerify(function() { return list.contentY > 0; });
            }
            function test_cancelOnSwitchIgnoresStale() {
                open();
                click(child('section4'));
                tryCompare(panel.collector, 'active', true);
                wait(150); // The fake disk helper has installed its signal handler.
                click(child('section1'));
                ensure(panel.collector.loading);
                waitSnapshot();
                equal(panel.collector.snapshot.section, 'services');
                ensure(panel.collector.snapshot.summary.indexOf('Cancelled') < 0);
            }
            function test_closeAndImmediateReopen() {
                panel.selectedSection = 4;
                widget.open();
                tryCompare(panel.collector, 'active', true);
                wait(150);
                widget.close();
                ensure(!panel.collector.loading);
                panel.selectedSection = 0;
                widget.open();
                waitSnapshot();
                equal(panel.collector.snapshot.section, 'docker');
                ensure(!panel.collector.active);
            }
            function test_popoutSwitchCancels() {
                panel.selectedSection = 4;
                widget.open();
                wait(150);
                fakeBar.requestPopout({closeForPopoutSwitch: function() {}});
                ensure(!widget.opened);
                tryCompare(panel.collector, 'active', false);
                ensure(panel.collector.snapshot === null);
                fakeBar.activePopout = null;
            }
            function test_destroyCancels() {
                var instance = temporaryPanel.createObject(widget);
                instance.selectedSection = 4;
                instance.open();
                tryCompare(instance.collector, 'active', true);
                wait(150);
                instance.destroy();
                wait(400); // Python verifies fixture exit and all descendant PIDs.
                fakeBar.activePopout = null;
            }
            function test_malformedAndRetry() {
                widget.settings = {discoveryDepth: 0};
                widget.open();
                tryCompare(panel.collector, 'loading', false, 5000);
                ensure(panel.collector.error.indexOf('Invalid collector response') === 0);
                ensure(panel.collector.snapshot === null);
                widget.settings = {discoveryDepth: 2};
                click(child('refreshButton'));
                waitSnapshot();
            }
            function test_missingBackend() {
                var path = panel.collector.backendPath;
                panel.collector.backendPath = path + '.absent';
                widget.open();
                tryCompare(panel.collector, 'loading', false, 5000);
                ensure(panel.collector.error.indexOf('Collection failed') === 0);
                panel.collector.backendPath = path;
            }
            function test_protocolValidation() {
                var valid = {schemaVersion: 1, section: 'docker', status: 'ok', collectedAt: 'fixture', summary: '', tables: [], notes: []};
                equal(Model.parse(JSON.stringify(valid), 'docker').status, 'ok');
                var invalid = [Object.assign({}, valid, {schemaVersion: 2}), Object.assign({}, valid, {section: 'disk'}),
                    Object.assign({}, valid, {status: 'unknown'}), Object.assign({}, valid, {notes: [42]}),
                    Object.assign({}, valid, {tables: [{id: 'x', title: 'x', columns: [{key: 'n', label: 'N'}], rows: [{n: 42}]}]})];
                invalid.forEach(function(data) {
                    var failed = false;
                    try { Model.parse(JSON.stringify(data), 'docker'); } catch (_) { failed = true; }
                    ensure(failed);
                });
            }
            function test_refreshDisabledDuringRequest() {
                panel.selectedSection = 4;
                widget.open();
                wait(150);
                ensure(panel.collector.loading);
                ensure(!child('refreshButton').enabled);
                widget.refresh(); // Shell refresh supersedes without overlap, too.
                wait(100);
                widget.close();
                tryCompare(panel.collector, 'active', false);
                ensure(panel.collector.snapshot === null);
            }
            function test_responsiveAndPreview() {
                open();
                var window = findChild(panel, 'peekSurface');
                var originalWidth = window.testAvailableWidth;
                window.testAvailableWidth = 352;
                wait(60);
                ensure(child('section4').y > child('section0').y, 'Sections should wrap');
                ensure(child('snapshotRows').height > 0);
                window.testAvailableWidth = originalWidth;
                wait(150);
                var output = Quickshell.env('PEEK_PREVIEW_PATH');
                if (output) {
                    var saved = false;
                    // QtTest.grabImage crops high-DPI Quickshell windows to
                    // logical pixels. Item capture preserves the full surface.
                    ensure(content.parent.grabToImage(function(result) {
                        saved = result.saveToFile(output);
                    }), 'Preview capture started');
                    tryVerify(function() { return saved; }, 3000, 'Preview saved');
                }
            }
        }
    }
}
