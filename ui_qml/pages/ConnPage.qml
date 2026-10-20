import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import ".."

Item {
    id: page
    signal backRequested
    Rectangle { anchors.fill: parent; color: Theme.bg }

    Item {
        id: header
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        anchors.leftMargin: 26; anchors.rightMargin: 26
        height: 62
        Text { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "← 返回大厅"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 13
            MouseArea { anchors.fill: parent; onClicked: page.backRequested() } }
        Text { anchors.left: parent.left; anchors.leftMargin: 104; anchors.verticalCenter: parent.verticalCenter; text: "连接设置"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 22; font.bold: true }
        Text { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; text: "独立页面"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 12 }
    }

    Item {
        id: footer
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.leftMargin: 26; anchors.rightMargin: 26; anchors.bottomMargin: 14
        height: 34
        Text { anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; text: "恢复默认"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 12 }
        Rectangle { id: cancel; anchors.right: save.left; anchors.rightMargin: 10; width: 88; height: 34; radius: 6; color: "transparent"; border.color: Theme.border
            Text { anchors.centerIn: parent; text: "取消"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 13 } }
        Rectangle { id: save; anchors.right: parent.right; width: 88; height: 34; radius: 6; color: Theme.amber
            Text { anchors.centerIn: parent; text: "保存"; color: "#17130a"; font.family: Theme.fontFamily; font.pixelSize: 13; font.bold: true } }
    }

    Rectangle {
        id: card
        anchors.horizontalCenter: parent.horizontalCenter; anchors.top: header.bottom; anchors.topMargin: 22
        width: 600; height: 410; radius: 8; color: Theme.panel; border.color: Theme.border
        Column {
            anchors.fill: parent; anchors.margins: 22; spacing: 9
            Text { text: "服务器连接"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.bold: true }
            Text { text: "连接配置保存到 %APPDATA%\\DeltaClient\\config.json"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 11 }
            Text { text: "HTTP(S) 服务器地址"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true }
            Rectangle { width: parent.width; height: 38; color: Theme.input; radius: 6; border.color: Theme.amber
                Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "https://deltachat.icu:8443"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 13 } }
            Text { text: "WebSocket 地址（留空则自动推导为 ws(s)://host/ws）"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 12; font.bold: true }
            Rectangle { width: parent.width; height: 38; color: Theme.input; radius: 6; border.color: Theme.border
                Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "留空 = 自动推导 ws://<host>:8000/ws"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 13 } }
            Row { spacing: 10
                Rectangle { width: 40; height: 22; radius: 11; color: Theme.panel2; border.color: Theme.border }
                Text { text: "使用内置 Mock 后端（不联网，用于后端未就绪时演示）"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 13 } }
            Row { spacing: 10
                Rectangle { width: 40; height: 22; radius: 11; color: Theme.amber; border.color: Theme.amberHover }
                Text { text: "登录后把 token 保存到本机（不保存密码）"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 13 } }
            Rectangle { width: 96; height: 38; radius: 6; color: "transparent"; border.color: Theme.border
                Text { anchors.centerIn: parent; text: "测试连接"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: 13 } }
            Text { width: parent.width; text: "「测试连接」会请求 /health 与 /api/v1/rooms?page=1，并用当前登录 token 验证鉴权。"; color: Theme.muted2; font.family: Theme.fontFamily; font.pixelSize: 11; wrapMode: Text.WordWrap }
        }
    }
}
