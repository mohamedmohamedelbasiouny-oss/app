"""ستايل شبه Procreate: خلفية رمادي فحمي، أيقونات بيضا رفيعة، لوحات عائمة مدورة،
ولون مميز واحد هادي للأزرار المهمة."""
from __future__ import annotations

BG = "#161618"            # الخلفية (فحمي قريب من الأسود)
SURFACE = "#202023"       # اللوحات العائمة
SURFACE_2 = "#2A2A2E"     # عناصر جوه اللوحات
BORDER = "#34343A"
TEXT = "#F2F2F4"
TEXT_DIM = "#9C9CA6"
ACCENT = "#5AA9FF"        # اللون المميز الوحيد
ACCENT_DIM = "#2F5F92"
DANGER = "#FF6B6B"
OK = "#7ED6A5"

FONT_FAMILIES = ["Segoe UI", "Tahoma", "Noto Sans Arabic", "DejaVu Sans", "Arial"]

STYLESHEET = f"""
* {{
    color: {TEXT};
    font-size: 10.5pt;
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget#central {{ background: {BG}; }}
QToolTip {{
    background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 6px;
}}
QFrame#panel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 18px;
}}
QFrame#card {{
    background: {SURFACE_2};
    border-radius: 14px;
}}
QLabel#title {{ font-size: 15pt; font-weight: 600; }}
QLabel#big {{ font-size: 20pt; font-weight: 600; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#section {{ color: {TEXT_DIM}; font-size: 9.5pt; font-weight: 600; }}

QPushButton, QToolButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 7px 14px;
}}
QPushButton:hover, QToolButton:hover {{ background: #333338; }}
QPushButton:pressed, QToolButton:pressed {{ background: #3A3A40; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5d5d66; }}
QPushButton#accent, QToolButton#accent {{
    background: {ACCENT}; color: #0B1726; border: none; font-weight: 600;
}}
QPushButton#accent:hover, QToolButton#accent:hover {{ background: #7BBBFF; }}
QPushButton#accent:disabled {{ background: {ACCENT_DIM}; color: #8DA4BC; }}
QToolButton#icon {{
    background: transparent; border: none; border-radius: 10px; padding: 6px;
}}
QToolButton#icon:hover {{ background: {SURFACE_2}; }}
QToolButton#tab {{
    background: transparent; border: none; border-radius: 10px; padding: 7px 12px;
    color: {TEXT_DIM}; font-weight: 600;
}}
QToolButton#tab:checked {{ background: {SURFACE_2}; color: {TEXT}; }}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 7px 12px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px;
    selection-background-color: {ACCENT_DIM};
}}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 5px; border: 1px solid {BORDER};
    background: {SURFACE_2};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; }}

QSlider::groove:horizontal {{
    height: 4px; background: {SURFACE_2}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXT}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px;
}}
QProgressBar {{
    background: {SURFACE_2}; border: none; border-radius: 5px; height: 10px;
    text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 5px; }}

QTableView, QTableWidget, QListWidget {{
    background: transparent;
    border: none;
    gridline-color: {BORDER};
    alternate-background-color: #242428;
    selection-background-color: {ACCENT_DIM};
}}
QHeaderView::section {{
    background: {SURFACE}; color: {TEXT_DIM}; border: none;
    border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}
QListWidget::item {{ border-radius: 10px; padding: 8px; margin: 2px 0; }}
QListWidget::item:hover {{ background: {SURFACE_2}; }}
QListWidget::item:selected {{ background: {ACCENT_DIM}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3A3A40; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3A3A40; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QMessageBox {{ background: {SURFACE}; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {ACCENT_DIM}; }}
"""
