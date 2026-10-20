import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import ".."

Item {
    id: page
    Rectangle { anchors.fill: parent; color: Theme.bg }

    Rectangle {
        anchors.centerIn: parent
        width: 420
        height: 430
        radius: Theme.radiusCard
        color: Theme.panel
        border.color: Theme.border
        border.width: 1

        Column {
            anchors.fill: parent
            anchors.margins: 28
            spacing: 10

            Text {
                text: loginApi.registerMode ? "创建账户" : "欢迎回来"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 22
                font.bold: true
            }
            Text {
                text: loginApi.registerMode ? "注册后即可登录并加入队友房间" : "使用账号登录，进入房间大厅"
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontSizeSmall
            }
            Item { width: 1; height: 8 }

            Text { text: "账号"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; font.bold: true }
            Rectangle {
                width: parent.width; height: 38
                color: Theme.input; radius: Theme.radiusControl
                border.color: accountInput.activeFocus ? Theme.amber : Theme.border
                TextInput {
                    id: accountInput
                    anchors.left: parent.left; anchors.right: historyButton.left
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 12; anchors.rightMargin: 4
                    text: loginApi.account
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                    selectByMouse: true
                    clip: true
                }
                Rectangle {
                    id: historyButton
                    anchors.right: parent.right; anchors.rightMargin: 1
                    anchors.top: parent.top; anchors.bottom: parent.bottom
                    width: 36; radius: Theme.radiusControl
                    color: historyMouse.containsMouse ? Theme.panel2 : "transparent"
                    Text { anchors.centerIn: parent; text: "▼"; color: Theme.muted; font.pixelSize: 12 }
                    MouseArea {
                        id: historyMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: loginApi.toggle_history()
                    }
                }
            }

            Text { visible: !loginApi.historyVisible; text: "密码"; color: "#c8d3e1"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall; font.bold: true }
            Rectangle {
                visible: !loginApi.historyVisible; width: parent.width; height: 38
                color: Theme.input; radius: Theme.radiusControl; border.color: passwordInput.activeFocus ? Theme.amber : Theme.border
                TextInput {
                    id: passwordInput
                    anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: 12
                    echoMode: TextInput.Password
                    text: loginApi.password
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontSizeBody
                    Keys.onReturnPressed: loginApi.submit(accountInput.text, text)
                }
            }

            Text {
                visible: loginApi.errorText.length > 0
                text: loginApi.errorText
                color: "#ff9b8f"; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
                wrapMode: Text.WordWrap; width: parent.width
            }

            Rectangle {
                visible: !loginApi.historyVisible; width: parent.width; height: 44; radius: Theme.radiusControl
                color: loginApi.loading ? "#5a5138" : Theme.amber
                Text {
                    anchors.centerIn: parent
                    text: loginApi.loading ? "请稍候…" : (loginApi.registerMode ? "注 册" : "登 录")
                    color: "#17130a"; font.family: Theme.fontFamily; font.pixelSize: 14; font.bold: true
                }
                MouseArea {
                    anchors.fill: parent
                    enabled: !loginApi.loading
                    onClicked: loginApi.submit(accountInput.text, passwordInput.text)
                }
            }
            Text {
                visible: !loginApi.historyVisible
                anchors.horizontalCenter: parent.horizontalCenter
                text: loginApi.registerMode ? "已有账号？返回登录" : "没有账号？创建账户"
                color: Theme.amber; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSizeSmall
                MouseArea { anchors.fill: parent; onClicked: loginApi.toggle_mode() }
            }
        }
    }

    // 历史账号顶层浮层（Popup，不被卡片裁剪/遮挡）
    Popup {
        id: historyPopup
        parent: Overlay.overlay
        width: accountInput.width
        height: Math.min(5, Math.max(1, loginApi.historyEntries.length)) * 38 + 36
        x: Math.round((parent.width - width) / 2)
        y: 330
        z: 1000
        padding: 0
        modal: false
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        visible: loginApi.historyVisible
        onClosed: loginApi.hide_history()

        background: Rectangle {
            color: Theme.panel2
            border.color: Theme.border
            border.width: 1
            radius: 8
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: "#000000"
                shadowOpacity: 0.55
                shadowVerticalOffset: 12
                shadowBlur: 0.7
            }
        }

        contentItem: Item {
            id: historyList
            property int currentIndex: 0
            focus: true
            Keys.onDownPressed: currentIndex = Math.min(Math.max(0, loginApi.historyEntries.length - 1), currentIndex + 1)
            Keys.onUpPressed: currentIndex = Math.max(0, currentIndex - 1)
            Keys.onReturnPressed: loginApi.select_history_index(currentIndex)

            Column {
                width: parent.width
                Repeater {
                    model: loginApi.historyEntries
                    delegate: Rectangle {
                        width: historyList.width; height: 38
                        color: index === historyList.currentIndex ? Qt.rgba(245,168,0,0.16) : "transparent"
                        Rectangle { anchors.left: parent.left; width: 3; height: parent.height; color: "#f5a800"; visible: index === historyList.currentIndex }
                        Text {
                            anchors.left: parent.left; anchors.leftMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 170
                            text: modelData.username
                            elide: Text.ElideMiddle
                            color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 13
                            MouseArea { anchors.fill: parent; onClicked: loginApi.select_history(modelData.username) }
                        }
                        Text {
                            anchors.right: parent.right; anchors.rightMargin: 34
                            anchors.verticalCenter: parent.verticalCenter
                            text: modelData.timeText + (modelData.hasPassword ? "  🔒" : "")
                            color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 10
                        }
                        Text {
                            anchors.right: parent.right; anchors.rightMargin: 10
                            anchors.verticalCenter: parent.verticalCenter
                            text: "✕"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 13
                            MouseArea { anchors.fill: parent; onClicked: loginApi.delete_history(modelData.username) }
                        }
                    }
                }
            }
            Rectangle {
                anchors.left: parent.left; anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 34; color: "transparent"
                Rectangle { anchors.top: parent.top; width: parent.width; height: 1; color: Theme.border }
                Text { anchors.left: parent.left; anchors.leftMargin: 12; anchors.verticalCenter: parent.verticalCenter; text: "清空历史"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: 11 }
                MouseArea { anchors.fill: parent; onClicked: loginApi.clear_history() }
            }
        }
    }
}


