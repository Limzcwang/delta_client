pragma Singleton
import QtQuick

QtObject {
    readonly property string fontFamily: "Microsoft YaHei"

    readonly property color bg: "#0d1420"
    readonly property color panel: "#131c2b"
    readonly property color panel2: "#182235"
    readonly property color border: "#24334e"
    readonly property color border_soft: "#1c2940"
    readonly property color text: "#e8eef7"
    readonly property color muted: "#8b98ab"
    readonly property color muted2: "#5f6c80"
    readonly property color amber: "#f5a800"
    readonly property color amber_hover: "#ffb91f"
    readonly property color green: "#2ea36b"
    readonly property color green_hover: "#37b87c"
    readonly property color blue: "#3b82c4"
    readonly property color input: "#0f1725"
    readonly property color success: "#5fc98e"
    readonly property color amberHover: "#ffb91f"
    readonly property color greenHover: "#37b87c"
    readonly property color header: "#0f1725"

    readonly property int fontSizeBody: 13
    readonly property int fontSizeSmall: 12
    readonly property int fontSizeHint: 11
    readonly property int fontSizeTitle: 22
    readonly property int fontSizeSection: 14
    readonly property int radiusCard: 8
    readonly property int radiusControl: 6
    readonly property int buttonHeight: 34
    readonly property int inputHeight: 38
    readonly property int switchWidth: 40
    readonly property int switchHeight: 22
    readonly property int rowHeight: 42
    readonly property int statusHeight: 30
    readonly property int pagePadding: 26
    readonly property int pagePaddingV: 14
    readonly property int gap: 12
}
