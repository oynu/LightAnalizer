"""
Design system and styling tokens for LightAnalizer.
Premium Apple VisionOS Liquid Glass + Cyber Neon design system.
"""
from __future__ import annotations

# Core Liquid Glass + Neon Palette Tokens
COLORS = {
    # Liquid Glass Surfaces
    "bg_base": "#080B12",
    "bg_glass": "rgba(13, 18, 30, 185)",
    "surface_glass": "rgba(255, 255, 255, 14)",
    "surface_glass_hover": "rgba(255, 255, 255, 26)",
    "surface_glass_active": "rgba(0, 240, 255, 24)",
    "border_glass": "rgba(255, 255, 255, 38)",
    "border_subtle": "rgba(255, 255, 255, 16)",
    
    # Cyber Neon Accents
    "neon_cyan": "#00F0FF",
    "neon_violet": "#A855F7",
    "neon_emerald": "#00FF9D",
    "neon_amber": "#FFB800",
    "neon_rose": "#FF2A85",
    
    # Typography
    "text_primary": "#F8FAFC",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",

    # Backward compatibility aliases
    "bg_main": "#080B12",
    "bg_card": "rgba(13, 18, 30, 185)",
    "bg_sidebar": "rgba(10, 14, 24, 210)",
    "border": "rgba(255, 255, 255, 34)",
    "accent_blue": "#00F0FF",
    "accent_emerald": "#00FF9D",
    "accent_amber": "#FFB800",
    "accent_ruby": "#FF2A85",

    # Board squares
    "board_light": "#FFFFFF26",
    "board_dark": "#0F172AA5",
    "board_highlight": "#00F0FF50",
    "board_last_move": "#A855F74D",
    "board_arrow_best": "#00F0FFD0",
    "board_arrow_cand2": "#A855F7D0",
    "board_arrow_cand3": "#00FF9DD0",
    "board_arrow_threat": "#FF2A85D0",
}

LIQUID_GLASS_STYLESHEET = """
/* Global Application Reset */
QMainWindow, QDialog {
    background-color: #080B12;
    color: #F8FAFC;
    font-family: 'Segoe UI Variable Display', 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    font-size: 13px;
}

QWidget {
    color: #F8FAFC;
    font-family: 'Segoe UI Variable Display', 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Inter', sans-serif;
    outline: none;
}

/* Sidebar & Navigation Dock */
QFrame#Sidebar, QFrame#TopBar {
    background-color: rgba(13, 18, 30, 200);
    border: 1px solid rgba(255, 255, 255, 28);
    border-top: 1px solid rgba(255, 255, 255, 50);
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #94A3B8;
    text-align: left;
    padding: 8px 14px;
    border-radius: 9px;
    font-weight: 500;
    border: 1px solid transparent;
}

QPushButton.NavBtn:hover {
    background-color: rgba(255, 255, 255, 18);
    color: #F8FAFC;
    border: 1px solid rgba(255, 255, 255, 30);
}

QPushButton.NavBtn:checked {
    background-color: rgba(0, 240, 255, 24);
    color: #00F0FF;
    border: 1px solid #00F0FF;
    font-weight: 600;
}

/* Liquid Glass Panels, Cards & GroupBoxes */
QFrame.Card, QFrame#GlassPanel, QGroupBox {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255, 255, 255, 22),
        stop:1 rgba(255, 255, 255, 7)
    );
    border: 1px solid rgba(255, 255, 255, 34);
    border-top: 1px solid rgba(255, 255, 255, 58);
    border-left: 1px solid rgba(255, 255, 255, 48);
    border-radius: 16px;
    padding: 12px;
}

QGroupBox {
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #00F0FF;
}

/* Candidate Move Cards */
QFrame.CandidateCard {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255, 255, 255, 18),
        stop:1 rgba(255, 255, 255, 6)
    );
    border: 1px solid rgba(255, 255, 255, 28);
    border-top: 1px solid rgba(255, 255, 255, 52);
    border-radius: 14px;
    padding: 10px 14px;
}

QFrame.CandidateCardBest {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 240, 255, 28),
        stop:1 rgba(168, 85, 247, 18)
    );
    border: 1px solid rgba(0, 240, 255, 140);
    border-top: 1px solid rgba(0, 240, 255, 220);
    border-radius: 14px;
    padding: 10px 14px;
}

/* Typography Helpers */
QLabel.Title {
    font-size: 16px;
    font-weight: 700;
    color: #F8FAFC;
    letter-spacing: 0.3px;
}

QLabel.Subtitle {
    font-size: 12px;
    color: #94A3B8;
}

QLabel.SectionHeader {
    font-size: 11px;
    font-weight: 700;
    color: #00F0FF;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

/* Buttons */
QPushButton {
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 24),
        stop:1 rgba(255, 255, 255, 10)
    );
    border: 1px solid rgba(255, 255, 255, 38);
    border-top: 1px solid rgba(255, 255, 255, 65);
    border-radius: 11px;
    color: #F8FAFC;
    padding: 7px 16px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: rgba(0, 240, 255, 28);
    border: 1px solid #00F0FF;
    color: #FFFFFF;
}

QPushButton:pressed {
    background-color: rgba(0, 240, 255, 45);
}

QPushButton:checked, QPushButton#PrimaryButton, QPushButton.PrimaryBtn {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(0, 240, 255, 48),
        stop:1 rgba(168, 85, 247, 48)
    );
    border: 1px solid #00F0FF;
    color: #FFFFFF;
}

QPushButton.SecondaryBtn {
    background-color: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 18),
        stop:1 rgba(255, 255, 255, 8)
    );
    color: #94A3B8;
    border: 1px solid rgba(255, 255, 255, 28);
    border-radius: 10px;
    padding: 6px 12px;
}

QPushButton.SecondaryBtn:hover {
    background-color: rgba(255, 255, 255, 26);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 45);
}

/* Badges */
QLabel.BadgeBest {
    background-color: rgba(0, 255, 157, 26);
    color: #00FF9D;
    border: 1px solid rgba(0, 255, 157, 100);
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 700;
}

QLabel.BadgeEval {
    background-color: rgba(0, 240, 255, 24);
    color: #00F0FF;
    border: 1px solid rgba(0, 240, 255, 80);
    border-radius: 6px;
    padding: 2px 8px;
    font-family: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
    font-size: 12px;
    font-weight: 600;
}

QLabel.BadgeConfConfirmed {
    background-color: rgba(0, 255, 157, 24);
    color: #00FF9D;
    border: 1px solid rgba(0, 255, 157, 80);
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 600;
}

QLabel.BadgeConfEmerging {
    background-color: rgba(255, 184, 0, 24);
    color: #FFB800;
    border: 1px solid rgba(255, 184, 0, 80);
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 600;
}

QLabel.BadgeConfHypothesis {
    background-color: rgba(255, 255, 255, 14);
    color: #94A3B8;
    border: 1px solid rgba(255, 255, 255, 30);
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 600;
}

/* Input Fields & Combo Boxes */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {
    background-color: rgba(8, 11, 18, 180);
    border: 1px solid rgba(255, 255, 255, 30);
    border-top: 1px solid rgba(255, 255, 255, 45);
    border-radius: 10px;
    padding: 6px 10px;
    color: #F8FAFC;
    selection-background-color: rgba(0, 240, 255, 70);
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {
    border: 1px solid #00F0FF;
    background-color: rgba(0, 240, 255, 14);
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #0D121E;
    border: 1px solid rgba(255, 255, 255, 38);
    border-radius: 8px;
    selection-background-color: rgba(0, 240, 255, 45);
    color: #F8FAFC;
}

/* Tables, Move Lists & Trees */
QTableWidget, QListWidget, QTreeWidget, QScrollArea {
    background-color: rgba(255, 255, 255, 10);
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 14px;
    gridline-color: rgba(255, 255, 255, 12);
    outline: none;
}

QHeaderView::section {
    background-color: rgba(255, 255, 255, 14);
    color: #94A3B8;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 24);
    padding: 6px 10px;
    font-weight: 600;
}

QTableWidget::item:selected, QListWidget::item:selected {
    background-color: rgba(0, 240, 255, 32);
    color: #00F0FF;
    border-radius: 6px;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: rgba(255, 255, 255, 22);
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00F0FF, stop:1 #A855F7);
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #F8FAFC;
    border: 2px solid #00F0FF;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 9px;
}

/* Ultra-Minimal Glass Scrollbars */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 40);
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #00F0FF;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QProgressBar {
    background-color: rgba(255, 255, 255, 14);
    border: 1px solid rgba(255, 255, 255, 26);
    border-radius: 6px;
    text-align: center;
    color: #F8FAFC;
    font-weight: 600;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00F0FF, stop:1 #A855F7);
    border-radius: 5px;
}

QMenu {
    background-color: rgba(13, 18, 30, 240);
    color: #F8FAFC;
    border: 1px solid rgba(255, 255, 255, 38);
    border-radius: 12px;
    padding: 6px;
}

QMenu::item {
    padding: 7px 18px;
    border-radius: 6px;
}

QMenu::item:selected {
    background-color: rgba(0, 240, 255, 35);
    color: #00F0FF;
}
"""

DARK_THEME_QSS = LIQUID_GLASS_STYLESHEET
