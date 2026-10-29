"""Tema Valkyrium · by Pinalo (morado abismo + azul P)."""

from .brand import (
    BG,
    BG_CARD,
    BG_ELEVATED,
    BLUE_DEEP,
    BLUE_P,
    BLUE_TP,
    BORDER,
    BORDER_GLOW,
    CSS_DISPLAY,
    CSS_MONO,
    CSS_UI,
    DANGER,
    OK,
    PURPLE,
    PURPLE_DEEP,
    TEXT,
    TEXT_MUTED,
    WARN,
)

DARK_QSS = f"""
QWidget {{
  background-color: {BG};
  color: {TEXT};
  font-family: {CSS_UI};
  font-size: 13px;
}}
QMainWindow, QDialog {{
  background-color: {BG};
}}
QLabel#title {{
  font-family: {CSS_DISPLAY};
  font-size: 22px;
  font-weight: 700;
  color: {PURPLE};
  letter-spacing: 0.5px;
}}
QLabel#brandMark {{
  font-family: {CSS_DISPLAY};
  font-size: 11px;
  font-weight: 600;
  color: {BLUE_P};
  letter-spacing: 1.2px;
}}
QLabel#subtitle {{
  font-family: {CSS_UI};
  color: {TEXT_MUTED};
  font-size: 12px;
}}
QFrame#card {{
  background-color: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 10px;
}}
QPushButton {{
  background-color: {BG_ELEVATED};
  border: 1px solid {BORDER};
  border-radius: 8px;
  padding: 8px 12px;
  font-family: {CSS_UI};
  color: {TEXT};
}}
QPushButton:hover {{
  background-color: #163044;
  border-color: {PURPLE_DEEP};
}}
QPushButton#primary {{
  background-color: {BLUE_DEEP};
  border-color: {BLUE_P};
  font-weight: 600;
}}
QPushButton#primary:hover {{
  background-color: #2a7fff;
}}
QPushButton#danger {{
  background-color: #5a2230;
  border-color: {DANGER};
}}
QPushButton#ok {{
  background-color: #1a4a32;
  border-color: {OK};
}}
QComboBox, QSpinBox, QLineEdit {{
  background-color: #0c1624;
  border: 1px solid {BORDER};
  border-radius: 6px;
  padding: 6px;
  font-family: {CSS_UI};
  selection-background-color: {PURPLE_DEEP};
}}
QComboBox:hover, QLineEdit:focus {{
  border-color: {PURPLE_DEEP};
}}
QTabWidget::pane {{
  border: 1px solid {BORDER};
  border-radius: 8px;
  background: {BG_CARD};
  top: -1px;
}}
QTabBar::tab {{
  background: {BG_ELEVATED};
  color: {TEXT_MUTED};
  border: 1px solid {BORDER};
  border-bottom: none;
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
  padding: 8px 14px;
  margin-right: 2px;
  font-family: {CSS_UI};
}}
QTabBar::tab:selected {{
  background: {BG_CARD};
  color: {PURPLE};
  border-color: {BORDER_GLOW};
  font-weight: 600;
}}
QTableWidget {{
  background-color: #0c1624;
  gridline-color: {BORDER};
  border: 1px solid {BORDER};
  border-radius: 8px;
  font-size: 14px;
  font-family: {CSS_UI};
  alternate-background-color: {BG_CARD};
}}
QHeaderView::section {{
  background-color: {BG_ELEVATED};
  color: {PURPLE};
  padding: 8px;
  border: none;
  border-bottom: 1px solid {BORDER};
  font-family: {CSS_DISPLAY};
  font-weight: 600;
  font-size: 12px;
}}
QLabel#nextTarget {{
  background-color: #122033;
  border: 1px solid {BORDER_GLOW};
  border-radius: 10px;
  padding: 12px 14px;
  font-size: 15px;
  color: {TEXT};
}}
QFrame#nextPanel {{
  background-color: #101c2c;
  border: 2px solid {PURPLE_DEEP};
  border-radius: 14px;
}}
QLabel#nextHead {{
  color: {PURPLE};
  font-size: 12px;
  font-weight: 800;
  font-family: {CSS_DISPLAY};
  letter-spacing: 1.5px;
}}
QLabel#nextEstado {{
  font-size: 22px;
  font-weight: 800;
  font-family: {CSS_MONO};
}}
QLabel#nextNombre {{
  font-size: 18px;
  font-weight: 700;
  font-family: {CSS_DISPLAY};
  color: {TEXT};
}}
QLabel#nextTp {{
  font-size: 28px;
  font-weight: 800;
  font-family: {CSS_MONO};
  color: {BLUE_TP};
}}
QLabel#nextTimer {{
  font-size: 16px;
  font-weight: 700;
  font-family: {CSS_MONO};
  color: {WARN};
}}
QLabel#nextRazon {{
  color: {TEXT_MUTED};
  font-size: 11px;
  font-family: {CSS_UI};
}}
QLabel#nextDespues {{
  color: {TEXT_MUTED};
  font-size: 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid {BORDER};
}}
QFrame#nextCompact {{
  background: rgba(10, 22, 38, 230);
  border: 2px solid {BLUE_P};
  border-radius: 12px;
  color: {TEXT};
}}
QTableWidget::item:selected {{
  background-color: #16486a;
  color: {TEXT};
}}
QTextEdit {{
  background-color: #0c1624;
  border: 1px solid {BORDER};
  border-radius: 8px;
  font-family: {CSS_UI};
}}
QCheckBox {{
  font-family: {CSS_UI};
  spacing: 8px;
}}
QCheckBox::indicator:checked {{
  background: {PURPLE_DEEP};
  border: 1px solid {PURPLE};
}}
QStatusBar {{
  background-color: #060c14;
  color: {TEXT_MUTED};
  font-family: {CSS_UI};
}}
QMenu {{
  background-color: {BG_CARD};
  color: {TEXT};
  border: 1px solid {BORDER};
  font-family: {CSS_UI};
}}
QMenu::item:selected {{
  background-color: #16486a;
  color: {PURPLE};
}}
QScrollBar:vertical {{
  background: {BG};
  width: 10px;
}}
QScrollBar::handle:vertical {{
  background: {BORDER_GLOW};
  border-radius: 4px;
  min-height: 24px;
}}
"""
