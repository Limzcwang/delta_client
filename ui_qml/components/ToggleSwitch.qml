import QtQuick
import ".."

Item {
    id: control
    width: 40
    height: 22
    property bool checked: false
    signal toggled(bool checked)
    opacity: enabled ? 1.0 : 0.4

    Rectangle {
        id: track
        anchors.fill: parent
        radius: 11
        color: control.checked ? ((mouse.containsMouse && control.enabled) ? "#ffb91f" : "#f5a800")
                               : ((mouse.containsMouse && control.enabled) ? "#2c3d57" : "#26344d")
        ColorAnimation on color { duration: 150; easing.type: Easing.InOutQuad }
    }

    Rectangle {
        id: knob
        width: 16
        height: 16
        radius: 8
        y: 3
        x: control.checked ? 21 : 3
        color: control.checked ? "#10131a" : "#8b98ab"
        border.width: 1
        border.color: control.checked ? "rgba(0,0,0,0.35)" : "rgba(255,255,255,0.35)"
        NumberAnimation on x { duration: 150; easing.type: Easing.InOutQuad }
        ColorAnimation on color { duration: 150; easing.type: Easing.InOutQuad }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: control.enabled
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            control.checked = !control.checked
            control.toggled(control.checked)
        }
    }

    focus: true
    activeFocusOnTab: true
    Keys.onSpacePressed: {
        if (control.enabled) {
            control.checked = !control.checked
            control.toggled(control.checked)
        }
    }
    Keys.onReturnPressed: {
        if (control.enabled) {
            control.checked = !control.checked
            control.toggled(control.checked)
        }
    }
    Keys.onEnterPressed: {
        if (control.enabled) {
            control.checked = !control.checked
            control.toggled(control.checked)
        }
    }
}
