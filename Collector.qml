import QtQuick
import Quickshell
import 'Model.js' as Model

Item {
    id: root
    property string backendPath: decodeURIComponent(Qt.resolvedUrl('scripts/peek.py').toString().replace(/^file:\/\//, ''))
    property bool loading: false
    property var snapshot: null
    property string error: ''
    readonly property bool active: requestProcess !== null
    property Request requestProcess: null
    property int generation: 0
    property var pending: null
    property var queue: []
    property var snapshots: ({})
    property var errors: ({})
    property string currentSection: ''
    property var requestSettings: ({})

    function cancel() {
        generation++;
        pending = null;
        queue = [];
        loading = false;
        if (requestProcess) requestProcess.cancel();
    }

    function request(section, settings) {
        cancel();
        snapshot = null;
        error = '';
        loading = true;
        currentSection = section;
        pending = {section: section, options: JSON.stringify(Model.options(settings)), generation: generation};
        pump();
    }

    function overview(settings) {
        request('docker', settings);
        snapshots = ({});
        errors = ({});
        requestSettings = settings;
        queue = ['services', 'worktrees'];
    }

    function pump() {
        if (requestProcess || !pending) return;
        var next = pending;
        pending = null;
        requestProcess = requestFactory.createObject(Quickshell, {
            owner: root, generation: next.generation, section: next.section
        });
        requestProcess.completed.connect(root.complete);
        requestProcess.exec(['python3', backendPath, next.section, '--options', next.options]);
    }

    function complete(process, exitCode, output) {
        if (process.generation === generation) {
            loading = false;
            if (exitCode !== 0) {
                error = 'Collection failed. Press Refresh to retry.';
            } else {
                try { snapshot = Model.parse(output, process.section); }
                catch (_) { error = 'Invalid collector response. Press Refresh to retry.'; }
            }
        }
        requestProcess = null;
        if (process.generation === generation) {
            var saved = Object.assign({}, snapshots);
            var failures = Object.assign({}, errors);
            saved[process.section] = snapshot;
            failures[process.section] = error;
            snapshots = saved;
            errors = failures;
            if (queue.length) {
                var remaining = queue.slice();
                var section = remaining.shift();
                queue = remaining;
                loading = true;
                currentSection = section;
                error = '';
                snapshot = null;
                pending = {section: section, options: JSON.stringify(Model.options(requestSettings)), generation: generation};
            }
        }
        Qt.callLater(root.pump);
    }

    Component { id: requestFactory; Request {} }
    Component.onDestruction: {
        pending = null;
        if (requestProcess) {
            requestProcess.cancel();
            requestProcess.owner = null;
        }
    }
}
