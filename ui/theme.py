"""统一视觉主题（QSS）：深色 + 橙色强调，贴合“三角洲行动”风格。"""

from __future__ import annotations

from typing import Any

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
"""


def apply_theme(app: Any) -> None:
    """给 QApplication 应用 Fusion 风格 + 统一 QSS。"""
    try:
        app.setStyle("Fusion")
    except Exception:  # pragma: no cover - 无显示环境时的兜底
        pass
    app.setStyleSheet(APP_STYLESHEET)
