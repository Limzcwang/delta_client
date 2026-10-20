import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Item {
    id: page

    property int selectedTab: 0
    property int selectedRow: 1

    ListModel {
        id: roomModel
        ListElement { code: "AB12C"; name: "零号大坝 · 常规"; members: "4"; kind: "公开" }
        ListElement { code: "K7M2P"; name: "航天基地 · 机密"; members: "3"; kind: "私有" }
        ListElement { code: "Q4W8E"; name: "长弓溪谷 · 绝密"; members: "2"; kind: "公开" }
        ListElement { code: "M9X2A"; name: "巴克什 · 常规"; members: "1"; kind: "公开" }
    }

    Rectangle { anchors.fill: parent; color: Theme.bg }

    // ---------- 表头 ----------
    Item {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 78
        anchors.leftMargin: Theme.pagePadding
        anchors.rightMargin: Theme.pagePadding

        Text {
            id: title
            x: 0; y: 16
            text: "房间大厅"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeTitle
            font.bold: true
        }
        Text {
            x: 0; y: 48
            text: "服务器：https://deltachat.icu:8443  ·  双击行可直接加入"
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontSizeSmall
        }

        Row {
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: 14
            spacing: 14

            Rectangle {
                width: 52; height: 24; radius: 12
                color: "#1b3650"; border.color: Theme.blue; border.width: 1
                Text { anchors.centerIn: parent; text: "LIVE"; color: "#d8ecff";
                       font.family: Theme.fontFamily; font.pixelSize: 11; font.bold: true }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "当前用户：DeltaQA01"; color: Theme.muted
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody
            }
            Rectangle { width: 1; height: 22; anchors.verticalCenter: parent.verticalCenter; color: Theme.border }
            Rectangle {
                width: 94; height: Theme.buttonHeight; radius: Theme.radiusControl
                color: "transparent"; border.color: Theme.border
                Text { anchors.centerIn: parent; text: "连接设置"; color: "#c8d3e1";
                       font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
            }
            Rectangle {
                width: 94; height: Theme.buttonHeight; radius: Theme.radiusControl
                color: "transparent"; border.color: Theme.blue
                Text { anchors.centerIn: parent; text: "个人资料"; color: "#9ec9f2";
                       font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall }
            }
        }
    }

    // ---------- 工具栏 ----------
    Row {
        id: toolbar
        anchors.left: parent.left
        anchors.top: header.bottom
        anchors.leftMargin: Theme.pagePadding
        spacing: 10

        Rectangle {
            width: 96; height: Theme.buttonHeight; radius: Theme.radiusControl
            color: "transparent"; border.color: Theme.border
            Text { anchors.centerIn: parent; text: "刷新列表"; color: "#c8d3e1";
                   font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody }
        }
        Rectangle {
            width: 104; height: Theme.buttonHeight; radius: Theme.radiusControl
            color: Theme.amber
            Text { anchors.centerIn: parent; text: "创建房间"; color: "#17130a";
                   font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody; font.bold: true }
        }
    }

    // ---------- 文件夹 Tab ----------
    Item {
        id: tabs
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: toolbar.bottom
        anchors.topMargin: 12
        anchors.leftMargin: Theme.pagePadding
        anchors.rightMargin: Theme.pagePadding
        height: 40

        Row {
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            spacing: 2
            Repeater {
                model: ["公共房间", "我的房间 (2)"]
                delegate: Rectangle {
                    width: index === 0 ? 92 : 108
                    height: 38
                    radius: Theme.radiusControl
                    color: page.selectedTab === index ? Theme.panel : "transparent"
                    border.color: page.selectedTab === index ? Theme.border : "transparent"
                    Text {
                        anchors.centerIn: parent; text: modelData
                        color: page.selectedTab === index ? Theme.text : Theme.muted
                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody
                        font.bold: page.selectedTab === index
                    }
                    MouseArea { anchors.fill: parent; onClicked: page.selectedTab = index }
                }
            }
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1; color: Theme.border
        }
    }

    // ---------- 表格 ----------
    Rectangle {
        id: table
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: tabs.bottom
        anchors.leftMargin: Theme.pagePadding
        anchors.rightMargin: Theme.pagePadding
        height: 380
        color: Theme.panel
        border.color: Theme.border
        radius: 6
        clip: true
        topLeftRadius: 0
        topRightRadius: 0

        Rectangle {
            id: tableHeader
            anchors.left: parent.left
            anchors.right: parent.right
            height: 42
            color: Theme.header
            radius: 0
            Text {
                x: 14; anchors.verticalCenter: parent.verticalCenter
                text: "房间号"; color: Theme.muted
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeHint
            }
            Text {
                x: 140; anchors.verticalCenter: parent.verticalCenter
                text: "房间名"; color: Theme.muted
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeHint
            }
            Text {
                x: parent.width - 190
                anchors.verticalCenter: parent.verticalCenter
                text: "人数"; color: Theme.muted
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeHint
            }
            Text {
                x: parent.width - 92
                anchors.verticalCenter: parent.verticalCenter
                text: "类型"; color: Theme.muted
                font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeHint
            }
        }

        ListView {
            id: roomList
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: tableHeader.bottom
            anchors.bottom: parent.bottom
            clip: true
            model: roomModel
            delegate: Item {
                width: roomList.width
                height: Theme.rowHeight
                Rectangle {
                    anchors.fill: parent
                    color: page.selectedRow === index ? Qt.rgba(245, 168, 0, 0.16) : "transparent"
                    Rectangle {
                        visible: page.selectedRow === index
                        width: 3; height: parent.height
                        anchors.left: parent.left
                        anchors.top: parent.top
                        color: Theme.amber
                    }
                }
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.borderSoft }
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.code; color: Theme.text
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody
                }
                Text {
                    anchors.left: parent.left; anchors.leftMargin: 140
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.name; color: Theme.text
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody
                }
                Text {
                    x: parent.width - 190
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.members; color: Theme.muted
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody
                }
                Text {
                    x: parent.width - 92
                    anchors.verticalCenter: parent.verticalCenter
                    text: model.kind; color: Theme.muted
                    font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeBody
                }
                MouseArea { anchors.fill: parent; onClicked: page.selectedRow = index }
            }
        }
    }

    // ---------- 状态栏 ----------
    Rectangle {
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: Theme.statusHeight
        color: Theme.header
        Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: Theme.border }
        Text {
            anchors.left: parent.left; anchors.leftMargin: Theme.pagePadding
            anchors.verticalCenter: parent.verticalCenter
            text: "✓ 登录成功：DeltaQA01"; color: Theme.muted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: Theme.pagePadding
            anchors.verticalCenter: parent.verticalCenter
            text: "服务器：https://deltachat.icu:8443 ・ 模式：LIVE"; color: Theme.muted
            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
        }
    }
}
