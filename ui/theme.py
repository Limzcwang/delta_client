"""统一视觉主题（QSS）：深色 + 橙色强调，贴合“三角洲行动”风格。"""

from __future__ import annotations

from typing import Any

TOKENS = {
    "bg": "#0d1420",
    "panel": "#131c2b",
    "panel2": "#182235",
    "border": "#24334e",
    "border_soft": "#1c2940",
    "text": "#e8eef7",
    "muted": "#8b98ab",
    "muted2": "#5f6c80",
    "amber": "#f5a800",
    "amber_hover": "#ffb91f",
    "green": "#2ea36b",
    "green_hover": "#37b87c",
    "blue": "#3b82c4",
    "input": "#0f1725",
    "success": "#5fc98e",
}

APP_STYLESHEET = """
QWidget {
    background-color: #151a21;
    color: #e6edf5;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #151a21; }
QFrame#Card {
    background-color: #1b222c;
    border: 1px solid #2c3745;
    border-radius: 10px;
}
QFrame#BrandPanel {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #1f2733, stop:0.55 #1a212b, stop:1 #2b2117);
    border: none;
    border-right: 1px solid #2c3745;
}
QFrame#CanvasPlaceholder {
    background-color: #11161d;
    border: 2px dashed #3a4757;
    border-radius: 10px;
}
QLabel { background: transparent; }
QLabel#BrandTitle {
    color: #ffb61f;
    font-size: 40px;
    font-weight: 800;
    letter-spacing: 6px;
}
QLabel#BrandSubtitle { color: #aebbc9; font-size: 14px; }
QLabel#BrandBullet { color: #8b98a8; font-size: 12px; }
QLabel#PageTitle { color: #ffffff; font-size: 22px; font-weight: 700; }
QLabel#PageSubtitle { color: #8b98a8; font-size: 13px; }
QLabel#SectionTitle { color: #dbe5ef; font-size: 14px; font-weight: 700; }
QLabel#Muted { color: #8b98a8; }
QLabel#Hint { color: #778696; font-size: 12px; }
QLabel#ErrorBanner {
    color: #ff9b8f;
    background-color: #2a1a1a;
    border: 1px solid #6d2f2a;
    border-radius: 6px;
    padding: 8px 10px;
}
QLabel#SuccessBanner {
    color: #8be3a8;
    background-color: #16251b;
    border: 1px solid #2f5c3c;
    border-radius: 6px;
    padding: 8px 10px;
}
QLabel#BadgeMock {
    color: #1a1a1a;
    background-color: #f0a500;
    border-radius: 9px;
    padding: 2px 10px;
    font-weight: 700;
    font-size: 12px;
}
QLabel#BadgeLive {
    color: #cfe7ff;
    background-color: #1f3a52;
    border: 1px solid #2f5c7a;
    border-radius: 9px;
    padding: 2px 10px;
    font-weight: 700;
    font-size: 12px;
}
QLabel#ConnConnected { color: #6fdc8c; font-weight: 700; }
QLabel#ConnPending { color: #ffb61f; font-weight: 700; }
QLabel#ConnError { color: #ff7b6b; font-weight: 700; }
QLabel#ConnOffline { color: #8b98a8; font-weight: 700; }
QLineEdit, QSpinBox {
    background-color: #11161d;
    border: 1px solid #364252;
    border-radius: 6px;
    padding: 8px 10px;
    color: #e6edf5;
    selection-background-color: #f0a500;
    selection-color: #161616;
}
QLineEdit:focus { border: 1px solid #f0a500; }
QLineEdit:disabled { color: #64707f; background-color: #171d25; }
QLineEdit#CodeInput {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 8px;
    padding: 8px 12px;
}
QPushButton {
    background-color: #253040;
    border: 1px solid #38475a;
    border-radius: 6px;
    padding: 8px 16px;
    color: #e6edf5;
}
QPushButton:hover { background-color: #2f3c4e; border-color: #4a5c72; }
QPushButton:pressed { background-color: #202a37; }
QPushButton:disabled { color: #64707f; background-color: #1b222c; border-color: #2c3745; }
QPushButton#Primary {
    background-color: #f0a500;
    color: #1a1a1a;
    border: none;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 2px;
}
QPushButton#Primary:hover { background-color: #ffb61f; }
QPushButton#Primary:pressed { background-color: #d89300; }
QPushButton#Primary:disabled { background-color: #5a5138; color: #9a9070; }
QToolButton#CanvasTool {
    background-color: #222b36;
    border: 1px solid #2c3745;
    border-radius: 8px;
    padding: 4px;
}
QToolButton#CanvasTool:hover { background-color: #2f3c4e; border-color: #4a5c72; }
QToolButton#CanvasTool:checked {
    background-color: #3a2f18;
    border: 2px solid #ffb61f;
}
QPushButton#Danger {
    background-color: #3a1f1d;
    border: 1px solid #6d2f2a;
    color: #ff9b8f;
}
QPushButton#Danger:hover { background-color: #4d2724; }
QPushButton#Link {
    background: transparent;
    border: none;
    color: #f0a500;
    padding: 2px 4px;
    font-size: 13px;
}
QPushButton#Link:hover { color: #ffb61f; }
QPushButton#Link:disabled { color: #64707f; }
QTableWidget {
    background-color: #11161d;
    alternate-background-color: #151c25;
    border: 1px solid #2c3745;
    border-radius: 8px;
    gridline-color: #232d3a;
    selection-background-color: #3a2f18;
    selection-color: #ffd071;
    outline: none;
}
QTableWidget::item { padding: 6px; }
QHeaderView::section {
    background-color: #1b222c;
    color: #9fb0c3;
    border: none;
    border-bottom: 1px solid #2c3745;
    padding: 9px 8px;
    font-weight: 700;
}
QListWidget {
    background-color: #11161d;
    border: 1px solid #2c3745;
    border-radius: 6px;
    outline: none;
}
QListWidget::item { padding: 7px 9px; border-bottom: 1px solid #1a212b; }
QListWidget#MemberList::item { padding: 9px; min-height: 40px; }
QListWidget::item:selected { background-color: #3a2f18; color: #ffd071; }
QScrollBar:vertical {
    background-color: #151a21;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical { background-color: #364252; min-height: 24px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background-color: #4a5c72; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background-color: #151a21; height: 10px; }
QScrollBar::handle:horizontal { background-color: #364252; min-width: 24px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QSplitter::handle { background-color: #2c3745; }
QStatusBar { background-color: #1b222c; color: #8b98a8; border-top: 1px solid #2c3745; }
QStatusBar QLabel { color: #8b98a8; padding-right: 8px; }
QRadioButton, QCheckBox { background: transparent; spacing: 8px; }
QRadioButton::indicator, QCheckBox::indicator { width: 15px; height: 15px; }
QMessageBox { background-color: #1b222c; }
QToolTip {
    background-color: #1b222c;
    color: #e6edf5;
    border: 1px solid #364252;
    padding: 4px 6px;
}

/* 登录页历史账号下拉 */
QToolButton#HistoryArrow {
    background-color: #11161d;
    border: 1px solid #364252;
    border-left: none;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    color: #aebbc9;
    font-size: 14px;
    padding: 0;
}
QToolButton#HistoryArrow:hover { background-color: #253040; color: #ffb61f; border-color: #4a5c72; }
QToolButton#HistoryArrow:pressed { background-color: #202a37; }
QToolButton#HistoryArrow:disabled { color: #64707f; background-color: #171d25; }
QFrame#LoginHistoryPopup {
    background-color: #1b222c;
    border: 1px solid #3a4757;
    border-radius: 8px;
}
QListWidget#LoginHistoryList {
    background-color: #1b222c;
    border: none;
    outline: none;
    padding: 0;
}
QListWidget#LoginHistoryList::item {
    border: none;
    border-radius: 6px;
    padding: 0;
    margin: 1px 0;
}
QListWidget#LoginHistoryList::item:hover { background-color: #253040; }
QListWidget#LoginHistoryList::item:selected { background-color: #3a2f18; color: #ffd071; }
QWidget#HistoryRow { background: transparent; }
QLabel#HistoryAccount { color: #e6edf5; font-size: 13px; font-weight: 600; background: transparent; }
QLabel#HistoryTime { color: #778696; font-size: 11px; background: transparent; }
QLabel#HistoryLock { color: #ffd071; font-size: 12px; background: transparent; }
QToolButton#HistoryDelete {
    background: transparent;
    border: none;
    border-radius: 4px;
    color: #778696;
    font-size: 14px;
}
QToolButton#HistoryDelete:hover { background-color: #4a2323; color: #ff9b8f; }
QPushButton#HistoryClear {
    background-color: transparent;
    border: none;
    border-top: 1px solid #2c3745;
    border-radius: 0;
    color: #8b98a8;
    padding: 8px;
    text-align: left;
}
QPushButton#HistoryClear:hover { color: #ff9b8f; }
/* ===== UI-REDESIGN 0.2.0 P1 tokens/components ===== */
QWidget {
    background-color: #0d1420;
    color: #e8eef7;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #0d1420; }
QLabel { background: transparent; }
QFrame#Card {
    background-color: #131c2b;
    border: 1px solid #24334e;
    border-radius: 8px;
}
QLabel#PageTitle { color: #e8eef7; font-size: 22px; font-weight: 700; }
QLabel#PageSubtitle { color: #8b98ab; font-size: 12px; }
QLabel#Muted { color: #8b98ab; }
QLabel#Hint { color: #5f6c80; font-size: 11px; }
QLabel#BadgeMock {
    color: #1a1a1a; background-color: #f5a800; border-radius: 9px;
    padding: 2px 10px; font-weight: 700; font-size: 11px;
}
QLabel#BadgeLive {
    color: #d8ecff; background-color: #1b3650; border: 1px solid #3b82c4;
    border-radius: 9px; padding: 2px 10px; font-weight: 700; font-size: 11px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QKeySequenceEdit {
    background-color: #0f1725;
    border: 1px solid #24334e;
    border-radius: 6px;
    min-height: 36px;
    padding: 0 12px;
    color: #e8eef7;
    selection-background-color: #f5a800;
    selection-color: #161616;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QKeySequenceEdit:focus {
    border: 1px solid #f5a800;
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: #5f6c80; background-color: #131c2b; }
QPushButton {
    background-color: #182235;
    border: 1px solid #24334e;
    border-radius: 6px;
    min-height: 34px;
    padding: 0 16px;
    color: #e8eef7;
    font-weight: 600;
}
QPushButton:hover { background-color: #1e2b42; border-color: #3b82c4; }
QPushButton:pressed { background-color: #131c2b; }
QPushButton:disabled { color: #5f6c80; background-color: #131c2b; border-color: #1c2940; }
QPushButton#Primary {
    background-color: #f5a800; color: #17130a; border: none; font-weight: 700;
}
QPushButton#Primary:hover { background-color: #ffb91f; }
QPushButton#Primary:pressed { background-color: #d99400; }
QPushButton#Primary:disabled { background-color: #4d432c; color: #8b7d5e; }
QPushButton#Green {
    background-color: #2ea36b; color: #f3fff8; border: 1px solid #37b87c; font-weight: 700;
}
QPushButton#Green:hover { background-color: #37b87c; }
QPushButton#Green:pressed { background-color: #248454; }
QPushButton#Ghost { background: transparent; border: 1px solid #24334e; color: #c8d3e1; }
QPushButton#Ghost:hover { background-color: #182235; border-color: #3b82c4; }
QPushButton#Outline { background: transparent; border: 1px solid #3b82c4; color: #9ec9f2; }
QPushButton#Outline:hover { background-color: #16283c; }
QPushButton#Text, QPushButton#Link {
    background: transparent; border: none; color: #8b98ab; padding: 0 6px; font-weight: 500;
}
QPushButton#Text:hover, QPushButton#Link:hover { color: #ffb91f; }
QPushButton#Danger { background-color: #3a1f1d; border: 1px solid #6d2f2a; color: #ff9b8f; }
QCheckBox, QRadioButton { background: transparent; color: #c8d3e1; spacing: 10px; min-height: 26px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 40px; height: 22px; border-radius: 11px;
    background-color: #182235; border: 1px solid #24334e;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: #f5a800; border: 1px solid #ffb91f;
}
QCheckBox::indicator:disabled { background-color: #131c2b; border-color: #1c2940; }
QTabWidget::pane { border: 1px solid #24334e; border-radius: 0 8px 8px 8px; background: #131c2b; top: -1px; }
QTabBar::tab {
    background: transparent; color: #8b98ab;
    border: 1px solid transparent; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    padding: 10px 18px; margin-right: 2px; min-height: 24px;
}
QTabBar::tab:hover { color: #e8eef7; background: #131c2b; }
QTabBar::tab:selected {
    background: #131c2b; color: #e8eef7;
    border: 1px solid #24334e; border-bottom: none;
}
QTableWidget {
    background-color: #131c2b;
    alternate-background-color: #131c2b;
    border: 1px solid #24334e;
    border-radius: 8px;
    gridline-color: #1c2940;
    selection-background-color: #373224;
    selection-color: #e8eef7;
    outline: none;
}
QTableWidget::item { padding: 12px 14px; border-bottom: 1px solid #1c2940; }
QTableWidget::item:hover { background-color: #182235; }
QTableWidget::item:selected { background-color: #373224; color: #e8eef7; border: none; }
QTableWidget::item:focus { border: none; }
QHeaderView::section {
    background-color: #101827; color: #8b98ab; border: none;
    border-bottom: 1px solid #24334e; padding: 11px 14px;
    font-weight: 600; font-size: 11px;
}
QListWidget { background-color: #131c2b; border: 1px solid #24334e; border-radius: 6px; outline: none; }
QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #1c2940; }
QListWidget::item:selected { background-color: rgba(245, 168, 0, 0.16); color: #e8eef7; }
QStatusBar {
    background-color: #101827; color: #8b98ab;
    border-top: 1px solid #24334e; min-height: 30px;
}
QStatusBar QLabel { color: #8b98ab; padding-right: 10px; }
QToolTip { background-color: #182235; color: #e8eef7; border: 1px solid #24334e; padding: 4px 6px; }
QScrollBar:vertical { background: #0d1420; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #24334e; min-height: 24px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #3b82c4; }
QFrame#VSeparator { background: #24334e; max-width: 1px; min-width: 1px; }
"""


def apply_theme(app: Any) -> None:
    """给 QApplication 应用 Fusion 风格 + 统一 QSS。
QFrame#PageHeader { background: #101827; border-bottom: 1px solid #24334e; }
QFrame#PageFooter { background: #101827; border-top: 1px solid #24334e; }
QLabel#FieldLabel { color: #c8d3e1; font-size: 12px; font-weight: 600; }
QFrame#Divider { background: #24334e; border: none; max-height: 1px; }

QPushButton#LobbyTab {
    background: transparent; color: #8b98ab;
    border: 1px solid transparent; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    min-height: 34px; padding: 0 18px; font-weight: 600;
}
QPushButton#LobbyTab:hover { color: #e8eef7; background: #131c2b; }
QPushButton#LobbyTab:checked {
    background: #131c2b; color: #e8eef7;
    border: 1px solid #24334e; border-bottom: 1px solid #131c2b;
}
QPushButton#GreenCompact {
    background-color: #2ea36b; color: #f3fff8; border: 1px solid #37b87c;
    min-height: 32px; max-height: 32px; padding: 0 16px; font-weight: 700;
}
QPushButton#GreenCompact:hover { background-color: #37b87c; }
"""
    try:
        app.setStyle("Fusion")
    except Exception:  # pragma: no cover - 无显示环境时的兜底
        pass
    app.setStyleSheet(APP_STYLESHEET)
