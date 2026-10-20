import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import ".."

Item {
    id: page
    signal backRequested
    property bool passwordExpanded: false
    Rectangle { anchors.fill: parent; color: Theme.bg }
    Item {
        id: header
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.leftMargin: 26; anchors.rightMargin: 26; height: 62
        Text { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "← 返回大厅"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 13
            MouseArea { anchors.fill: parent; onClicked: page.backRequested() } }
        Text { anchors.left: parent.left; anchors.leftMargin: 104; anchors.verticalCenter: parent.verticalCenter; text: "个人资料"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 22; font.bold: true }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "仅自己可见"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 12 }
    }
    Item {
        id: footer
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.leftMargin: 26; anchors.rightMargin: 26; anchors.bottomMargin: 14; height: 34
        Text { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "退出登录"; color: "#ffb347"; font.family: Theme.fontFamily; font.pixelSize: 12 }
        Rectangle { anchors.right: parent.right; width: 88; height: 34; radius: 6; color: Theme.amber
            Text { anchors.centerIn: parent; text: "保存"; color: "#17130a"; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true } }
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter; anchors.top: header.bottom; anchors.topMargin: 22
        width: 600; height: page.passwordExpanded ? 620 : 430; radius: 8; color: Theme.panel; border.color: Theme.border
        Column {
            anchors.fill: parent; anchors.margins: 22; spacing: 9
            Text { text: "账号信息"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.bold: true }
            Text { text: "账号只在本人资料页可见；房间成员、聊天、加入/离开提示统一显示昵称。"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 11 }
            Text { text: "账号（仅自己可见）"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true }
            Rectangle { width: parent.width; height: 38; color: Theme.input; radius: 6; border.color: Theme.border
                Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "DeltaQA01"; color: "#8b98ab"; font.family: Theme.fontFamily; font.pixelSize: 13 } }
            Text { text: "昵称（1–20 字符，展示给队友）"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true }
            Row { width: parent.width; spacing: 10
                Rectangle { width: parent.width - 110; height: 38; color: Theme.input; radius: 6; border.color: Theme.border
                    Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "老王的队友"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 13 } }
                Rectangle { width: 96; height: 38; radius: 6; color: Theme.green
                    Text { anchors.centerIn: parent; text: "保存昵称"; color: "#f3fff8"; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true } }
            }
            Rectangle { width: parent.width; height: 1; color: Theme.border }
            Rectangle { visible: !page.passwordExpanded; width: 180; height: 32; anchors.horizontalCenter: parent.horizontalCenter; radius: 6; color: Theme.green
                Text { anchors.centerIn: parent; text: "修改密码"; color: "#f3fff8"; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true }
                MouseArea { anchors.fill: parent; onClicked: page.passwordExpanded = true } }
            Column {
                visible: page.passwordExpanded
                width: parent.width; spacing: 8
                Text { text: "修改密码"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true }
                Text { text: "新密码 8–32 位，成功后保持登录"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 11 }
                Rectangle { width: parent.width; height: 38; color: Theme.input; radius: 6; border.color: Theme.border
                    Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "旧密码"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 13 } }
                Rectangle { width: parent.width; height: 38; color: Theme.input; radius: 6; border.color: Theme.border
                    Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "新密码"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 13 } }
                Rectangle { width: parent.width; height: 38; color: Theme.input; radius: 6; border.color: Theme.border
                    Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "确认新密码"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 13 } }
                Row { spacing: 10
                    Rectangle { width: 96; height: 32; radius: 6; color: Theme.amber
                        Text { anchors.centerIn: parent; text: "修改密码"; color: "#17130a"; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true } }
                    Rectangle { width: 88; height: 32; radius: 6; color: "transparent"; border.color: Theme.border
                        Text { anchors.centerIn: parent; text: "取消"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 12 }
                        MouseArea { anchors.fill: parent; onClicked: page.passwordExpanded = false } }
                }
            }
        }
    }
}
