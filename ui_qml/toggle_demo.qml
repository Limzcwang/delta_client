import QtQuick
import "components"

Item {
    width: 280; height: 120
    Rectangle { anchors.fill: parent; color: "#0d1420" }
    Row {
        anchors.centerIn: parent; spacing: 40
        Column { spacing: 10
            Text { text: "OFF"; color: "#8b98ab"; font.family: "Microsoft YaHei"; font.pixelSize: 11; anchors.horizontalCenter: parent.horizontalCenter }
            ToggleSwitch { id: off; checked: false } }
        Column { spacing: 10
            Text { text: "ON"; color: "#f5a800"; font.family: "Microsoft YaHei"; font.pixelSize: 11; anchors.horizontalCenter: parent.horizontalCenter }
            ToggleSwitch { checked: true } }
    }
}
