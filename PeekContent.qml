pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import qs.Ui as Ui
import qs.Commons
import 'Model.js' as Model

FocusScope {
    id: root
    readonly property var fonts: Style.font
    property int selectedSection: 0
    property var snapshot: null
    property bool loading: false
    property string error: ''
    readonly property Item initialFocus: sectionButtons.count > selectedSection
        ? sectionButtons.itemAt(selectedSection) : null
    readonly property var displayRows: Model.rows(snapshot, filter.text)
    signal sectionRequested(int index)
    signal refreshRequested()
    signal closeRequested()

    function resetView() { filter.text = ''; results.contentY = 0; results.contentX = 0; }
    Keys.onEscapePressed: root.closeRequested()

    Column {
        id: header
        width: parent.width
        spacing: Style.space(10)
        Row {
            width: parent.width
            Text {
                width: parent.width - refreshButton.width
                text: 'Peek'
                textFormat: Text.PlainText
                color: Color.foreground
                font.family: root.fonts.family
                font.pixelSize: root.fonts.body * 1.4
                font.bold: true
            }
            Ui.Button {
                id: refreshButton
                objectName: 'refreshButton'
                text: 'Refresh'
                focusable: true
                bordered: true
                enabled: !root.loading
                opacity: enabled ? 1 : 0.5
                onClicked: root.refreshRequested()
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
            }
        }
        Flow {
            width: parent.width
            spacing: Style.space(6)
            Repeater {
                id: sectionButtons
                model: Model.labels
                Ui.Button {
                    required property string modelData
                    required property int index
                    objectName: 'section' + index
                    text: modelData
                    focusable: true
                    bordered: true
                    selected: root.selectedSection === index
                    onClicked: root.sectionRequested(index)
                    Accessible.role: Accessible.Button
                    Accessible.name: text
                    Accessible.onPressAction: clicked()
                }
            }
        }
        Text {
            objectName: 'snapshotStatus'
            width: parent.width
            text: root.loading ? 'Collecting…' : root.error ? root.error : root.snapshot
                ? (root.snapshot.status === 'partial' ? 'Partial · ' : root.snapshot.status === 'error' ? 'Unavailable · ' : '') + root.snapshot.summary
                : 'Open a section to collect a snapshot.'
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Color.foreground
            font.family: root.fonts.family
            font.pixelSize: root.fonts.body
        }
        Text {
            objectName: 'snapshotTimestamp'
            width: parent.width
            visible: text !== ''
            text: root.snapshot ? 'Collected ' + root.snapshot.collectedAt : ''
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            color: Color.foreground
            opacity: 0.65
            font.family: root.fonts.family
            font.pixelSize: root.fonts.bodySmall
        }
        Ui.TextField {
            id: filter
            objectName: 'localFilter'
            width: parent.width
            placeholderText: 'Filter displayed rows'
            enabled: !!root.snapshot
            onTextChanged: { results.contentY = 0; results.contentX = 0; }
            Accessible.name: 'Filter displayed rows'
        }
    }
    ListView {
        id: results
        objectName: 'snapshotRows'
        anchors.top: header.bottom
        anchors.topMargin: Style.space(12)
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        spacing: Style.space(4)
        boundsBehavior: Flickable.StopAtBounds
        model: root.displayRows
        contentWidth: Math.max(width, Style.space(140) * maxColumns)
        readonly property int maxColumns: root.snapshot ? root.snapshot.tables.reduce(function(count, table) {
            return Math.max(count, table.columns.length);
        }, 1) : 1
        flickableDirection: Flickable.AutoFlickDirection
        ScrollBar.vertical: ScrollBar { }
        ScrollBar.horizontal: ScrollBar { }
        delegate: Item {
            id: entry
            required property var modelData
            width: results.contentWidth
            implicitHeight: Math.max(note.implicitHeight, cells.implicitHeight) + Style.space(10)
            height: implicitHeight
            Rectangle {
                anchors.fill: parent
                color: Color.foreground
                opacity: entry.modelData.kind === 'header' ? 0.09 : entry.modelData.kind === 'row' ? 0.025 : 0
            }
            TextEdit {
                id: note
                width: results.width - Style.space(16)
                x: Style.space(8)
                y: Style.space(5)
                visible: entry.modelData.cells.length === 0
                text: visible ? entry.modelData.text : ''
                textFormat: TextEdit.PlainText
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                color: Color.foreground
                font.family: root.fonts.family
                font.pixelSize: root.fonts.body
                font.bold: entry.modelData.kind === 'title'
                opacity: entry.modelData.kind === 'empty' ? 0.65 : 1
            }
            Row {
                id: cells
                width: parent.width
                y: Style.space(5)
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
