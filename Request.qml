import QtQuick
import Quickshell.Io

// Parent this short-lived request to the shell singleton, not the visual panel.
// Quickshell kills a Process when its QObject is destroyed; keeping it alive
// until exited gives the collector time to terminate its own child commands.
Process {
    id: root
    property QtObject owner: null
    property int generation: -1
    property string section: ''
    property bool cancelled: false
    signal completed(var request, int exitCode, string output)

    function cancel() {
        cancelled = true;
        signal(15);
    }
    onOwnerChanged: if (!owner) cancel()
    onStarted: if (cancelled || !owner) signal(15)
    stdout: StdioCollector { id: output; waitForEnd: true }
    // Raw diagnostics do not cross the protocol's factual UI boundary.
    stderr: StdioCollector { waitForEnd: true }
    // Quickshell exposes an unregistered QProcess::ExitStatus parameter.
    // The exit code used here is available; the unused enum is not lintable.
    // qmllint disable signal-handler-parameters
    onExited: function(exitCode) {
        if (owner) completed(root, exitCode, output.text);
        root.destroy();
    }
    // qmllint enable signal-handler-parameters
}
