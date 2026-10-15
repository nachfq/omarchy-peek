pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import qs.Ui as Ui
import qs.Commons
import 'Model.js' as Model

FocusScope {
    id: root
    readonly property var fonts: Style.font
    property int selectedSection: -1
    property var snapshot: null
    property var snapshots: ({})
    property var errors: ({})
    property string currentSection: ''
    property bool loading: false
    property string error: ''
    property bool showNotes: false
    property bool showRaw: false
    property string serviceScope: 'user'
    property bool allStates: false
    readonly property Item initialFocus: sectionButtons.count > selectedSection + 1 ? sectionButtons.itemAt(selectedSection + 1) : null
    readonly property var displayRows: Model.rows(snapshot, filter.text, {notes: showNotes, raw: showRaw, scope: serviceScope, allStates: allStates})
    readonly property var largest: Model.table(snapshots.worktrees, 'worktrees') && Model.coverage(snapshots.worktrees, Model.table(snapshots.worktrees, 'worktrees')) !== 'error' ? Model.sorted(Model.table(snapshots.worktrees, 'worktrees').rows, 'bytes').slice(0, 3) : []
    signal sectionRequested(int index)
    signal refreshRequested()
    signal closeRequested()
    function resetView() { filter.text = ''; showNotes = false; showRaw = false; serviceScope = 'user'; allStates = false; results.contentY = 0; results.contentX = 0; overview.contentY = 0; }
    Keys.onEscapePressed: root.closeRequested()
    Rectangle { anchors.fill: parent; color: Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 1) }
    Column {
        id: header
        width: parent.width
        spacing: Style.space(10)
        Row {
            width: parent.width
            Column {
                width: parent.width - refreshButton.width
                Text {
                    text: 'Peek'
                    color: Color.foreground
                    font.family: root.fonts.family
                    font.pixelSize: root.fonts.body * 1.6
                    font.bold: true
                }
                Text {
                    text: root.selectedSection === -1 ? 'Your resources, at a glance' : Model.labels[root.selectedSection]
                    color: Color.foreground
                    opacity: 0.65
                    font.family: root.fonts.family
                    font.pixelSize: root.fonts.bodySmall
                }
            }
            Ui.Button {
                id: refreshButton
                objectName: 'refreshButton'
                text: root.loading ? 'Collecting…' : 'Refresh'
                focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
                bordered: true
                enabled: !root.loading
                opacity: enabled ? 1 : 0.5
                onClicked: root.refreshRequested()
            }
        }
        Flow {
            width: parent.width
            spacing: Style.space(6)
            Repeater {
                id: sectionButtons
                model: ['Overview'].concat(Model.labels)
                Ui.Button {
                    required property string modelData
                    required property int index
                    objectName: 'section' + (index - 1)
                    text: modelData
                    focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
                    bordered: true
                    selected: root.selectedSection === index - 1
                    onClicked: root.sectionRequested(index - 1)
                }
            }
        }
        Text {
            objectName: 'snapshotStatus'
            width: parent.width
            visible: root.selectedSection !== -1
            text: root.loading ? 'Collecting…' : root.error ? root.error : root.snapshot
                ? (root.snapshot.status === 'partial' ? 'Partial · ' : root.snapshot.status === 'error' ? 'Unavailable · ' : '') + root.snapshot.summary : 'Open a section to collect a snapshot.'
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Color.foreground
            font.family: root.fonts.family
            font.pixelSize: root.fonts.body
        }
        Text {
            objectName: 'snapshotTimestamp'
            width: parent.width
            visible: root.selectedSection !== -1 && text !== ''
            text: root.snapshot ? 'Collected ' + root.snapshot.collectedAt : ''
            color: Color.foreground
            opacity: 0.6
            font.family: root.fonts.family
            font.pixelSize: root.fonts.bodySmall
        }
        Flow {
            visible: root.selectedSection === 1 && !root.showRaw
            width: parent.width
            spacing: Style.space(6)
            Repeater {
                model: ['user', 'system', 'all']
                Ui.Button {
                    required property string modelData
                    objectName: 'scope' + modelData
                    text: modelData === 'all' ? 'All scopes' : modelData === 'user' ? 'User' : 'System'
                    selected: root.serviceScope === modelData
                    bordered: true
                    focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
                    onClicked: root.serviceScope = modelData
                }
            }
            Ui.Button {
                objectName: 'allStates'
                text: root.allStates ? 'All states' : 'Running only'
                selected: root.allStates
                bordered: true
                focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
                onClicked: root.allStates = !root.allStates
            }
        }
        Ui.TextField {
            id: filter
            objectName: 'localFilter'
            width: parent.width
            visible: root.selectedSection !== -1
            placeholderText: 'Filter resources'
            enabled: !!root.snapshot
            onTextChanged: { results.contentY = 0; results.contentX = 0; }
            Accessible.name: 'Filter resources'
        }
        Flow {
            width: parent.width
            visible: root.selectedSection !== -1 && !!root.snapshot
            spacing: Style.space(8)
            Ui.Button {
                objectName: 'notesToggle'
                text: (root.showNotes ? '▾' : '▸') + ' Notes (' + (root.snapshot ? root.snapshot.notes.length : 0) + ')'
                focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
                onClicked: { root.showNotes = !root.showNotes; results.contentY = 0; }
            }
            Ui.Button {
                objectName: 'rawToggle'
                text: root.showRaw ? '▾ All data' : '▸ All data'
                focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
                onClicked: { root.showRaw = !root.showRaw; results.contentY = 0; results.contentX = 0; }
            }
        }
    }
    Flickable {
        id: overview
        objectName: 'overview'
        visible: root.selectedSection === -1
        anchors.top: header.bottom
        anchors.topMargin: Style.space(18)
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        contentHeight: overviewBody.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { }
        Column {
            id: overviewBody
            width: overview.width
            spacing: Style.space(16)
            Grid {
                id: cards
                width: parent.width
                columns: width >= Style.space(650) ? 3 : 1
                spacing: Style.space(12)
                Repeater {
                    model: ['docker', 'services', 'worktrees']
                    SummaryCard {
                        required property string modelData
                        height: Math.max(implicitHeight, Style.space(285))
                        width: (overviewBody.width - cards.spacing * (cards.columns - 1)) / cards.columns
                        summary: Model.overview(modelData, root.snapshots[modelData], root.errors[modelData] || '', root.loading && root.currentSection === modelData)
                        sectionIndex: Model.sections.indexOf(modelData)
                        onActivated: function(index) { root.sectionRequested(index); }
                    }
                }
            }
            Text {
                text: 'Largest worktrees · observed size'
                color: Color.foreground
                font.family: root.fonts.family
                font.pixelSize: root.fonts.body
                font.bold: true
            }
            Repeater {
                model: root.largest
                Row {
                    id: largestRow
                    required property var modelData
                    width: overviewBody.width
                    Column {
                        width: parent.width * 0.75
                        Text {
                            width: parent.width
                            text: Model.name(largestRow.modelData.path)
                            textFormat: Text.PlainText
                            color: Color.foreground
                            font.family: root.fonts.family
                            font.pixelSize: root.fonts.body
                            elide: Text.ElideMiddle
                        }
                        Text {
                            width: parent.width
                            text: largestRow.modelData.branch
                            textFormat: Text.PlainText
                            color: Color.foreground
                            opacity: 0.6
                            font.family: root.fonts.family
                            font.pixelSize: root.fonts.bodySmall
                            elide: Text.ElideMiddle
                        }
                    }
                    Text {
                        width: parent.width * 0.25
                        text: Model.bytes(largestRow.modelData.bytes, largestRow.modelData.measurement)
                        horizontalAlignment: Text.AlignRight
                        color: Color.foreground
                        font.family: root.fonts.family
                        font.pixelSize: root.fonts.body
                        wrapMode: Text.WordWrap
                    }
                }
            }
            Text {
                visible: !root.largest.length
                text: root.loading ? 'Waiting for worktrees…' : root.snapshots.worktrees && root.snapshots.worktrees.status === 'ok' ? 'No registered worktrees.' : 'Worktree sizes unavailable. Open Worktrees for details.'
                width: parent.width
                wrapMode: Text.WordWrap
                color: Color.foreground
                opacity: 0.65
                font.family: root.fonts.family
                font.pixelSize: root.fonts.bodySmall
            }
        }
    }
    ListView {
        id: results
        objectName: 'snapshotRows'
        visible: root.selectedSection !== -1
        anchors.top: header.bottom
        anchors.topMargin: Style.space(12)
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        spacing: Style.space(4)
        boundsBehavior: Flickable.StopAtBounds
        model: root.displayRows
        contentWidth: root.showRaw ? Math.max(width, Style.space(140) * maxColumns) : width
        readonly property int maxColumns: root.snapshot ? root.snapshot.tables.reduce(function(count, table) { return Math.max(count, table.columns.length); }, 1) : 1
        flickableDirection: Flickable.AutoFlickDirection
        ScrollBar.vertical: ScrollBar { }
        ScrollBar.horizontal: ScrollBar { }
        delegate: Item {
            id: entry
            required property var modelData
            width: results.contentWidth
            height: Math.max(copy.implicitHeight, cells.implicitHeight, value.implicitHeight) + Style.space(14)
            Rectangle {
                anchors.fill: parent
                color: Color.foreground
                opacity: entry.modelData.kind === 'header' ? 0.09 : ['row', 'entry'].indexOf(entry.modelData.kind) >= 0 ? 0.03 : 0
                radius: Style.space(5)
            }
            Column {
                id: copy
                width: results.width - Style.space(16) - (entry.modelData.value ? Math.min(results.width * 0.3, Style.space(150)) : 0)
                x: Style.space(8)
                y: Style.space(7)
                spacing: Style.space(4)
                visible: !entry.modelData.cells.length
                TextEdit {
                    width: parent.width
                    text: entry.modelData.text
                    textFormat: TextEdit.PlainText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.WrapAnywhere
                    color: Color.foreground
                    font.family: root.fonts.family
                    font.pixelSize: root.fonts.body
                    font.bold: ['title', 'entry'].indexOf(entry.modelData.kind) >= 0
                    opacity: entry.modelData.kind === 'empty' ? 0.65 : 1
                }
                TextEdit {
                    width: parent.width
                    visible: text !== ''
                    text: entry.modelData.secondary
                    textFormat: TextEdit.PlainText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.WrapAnywhere
                    color: Color.foreground
                    opacity: 0.65
                    font.family: root.fonts.family
                    font.pixelSize: root.fonts.bodySmall
                }
            }
            Text {
                id: value
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                y: Style.space(7)
                width: Math.min(results.width * 0.3, Style.space(150))
                text: entry.modelData.value
                textFormat: Text.PlainText
                horizontalAlignment: Text.AlignRight
                wrapMode: Text.WrapAnywhere
                color: Color.foreground
                font.family: root.fonts.family
                font.pixelSize: root.fonts.body
            }
            Row {
                id: cells
                width: parent.width
                y: Style.space(7)
                Repeater {
                    model: entry.modelData.cells
                    TextEdit {
                        required property string modelData
                        width: cells.width / entry.modelData.cells.length
                        leftPadding: Style.space(8)
                        rightPadding: Style.space(8)
                        text: modelData
                        textFormat: TextEdit.PlainText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.WrapAnywhere
                        color: Color.foreground
                        font.family: root.fonts.family
                        font.pixelSize: root.fonts.body
                        font.bold: entry.modelData.kind === 'header'
                    }
                }
            }
        }
    }
}
