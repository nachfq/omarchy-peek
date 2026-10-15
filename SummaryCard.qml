pragma ComponentBehavior: Bound
import QtQuick
import qs.Ui as Ui
import qs.Commons

Rectangle {
    id: root
    readonly property var fonts: Style.font
    required property var summary
    required property int sectionIndex
    signal activated(int index)
    color: Qt.tint(Color.background, Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.045))
    radius: Style.space(10)
    border.color: Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.14)
    implicitHeight: body.implicitHeight + Style.space(70)
    Column {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Style.space(14)
        spacing: Style.space(8)
        Row {
            width: parent.width
            Text {
                width: parent.width - state.width
                text: root.summary.title
                color: Color.foreground
                font.family: root.fonts.family
                font.pixelSize: root.fonts.body
                font.bold: true
            }
            Text {
                id: state
                text: root.summary.status
                color: Color.foreground
                opacity: 0.65
                font.family: root.fonts.family
                font.pixelSize: root.fonts.bodySmall
            }
        }
        Text {
            width: parent.width
            text: root.summary.metric
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: Color.foreground
            font.family: root.fonts.family
            font.pixelSize: root.fonts.body * (text.length > 10 ? 1.4 : 2.5)
            font.bold: true
        }
        Text {
            width: parent.width
            text: root.summary.label
            color: Color.foreground
            font.family: root.fonts.family
            font.pixelSize: root.fonts.bodySmall
            wrapMode: Text.WordWrap
        }
        Rectangle { width: parent.width; height: 1; color: Color.foreground; opacity: 0.12 }
        Repeater {
            model: root.summary.lines
            Row {
                required property var modelData
                width: parent.width
                Text {
                    width: parent.width * 0.57
                    text: parent.modelData.label
                    color: Color.foreground
                    opacity: 0.7
                    font.family: root.fonts.family
                    font.pixelSize: root.fonts.bodySmall
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width * 0.43
                    text: parent.modelData.value
                    textFormat: Text.PlainText
                    color: Color.foreground
                    horizontalAlignment: Text.AlignRight
                    font.family: root.fonts.family
                    font.pixelSize: root.fonts.bodySmall
                    wrapMode: Text.WordWrap
                }
            }
        }
        Text {
            width: parent.width
            text: root.summary.timestamp ? 'Collected ' + root.summary.timestamp.replace('T', ' ').replace('Z', ' UTC') : ''
            color: Color.foreground
            opacity: 0.55
            font.family: root.fonts.family
            font.pixelSize: root.fonts.bodySmall * 0.85
            wrapMode: Text.WordWrap
        }
    }
    Ui.Button {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: Style.space(14)
        objectName: 'openSummary' + root.sectionIndex
        text: root.sectionIndex === 1 ? 'View user services →' : 'View ' + root.summary.title.toLowerCase() + ' →'
        focusable: true
                Accessible.role: Accessible.Button
                Accessible.name: text
                Accessible.onPressAction: if (enabled) clicked()
        onClicked: root.activated(root.sectionIndex)
    }
}
