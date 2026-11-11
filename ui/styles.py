"""
Design system and styling tokens for LightAnalizer.
Refined dark theme inspired by Linear and Raycast desktop applications.
"""
from __future__ import annotations

DARK_THEME_QSS = """
/* Global Application Reset */
QWidget {
    background-color: #121316;
    color: #EDEDED;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
    selection-background-color: #2563EB;
    selection-color: #FFFFFF;
    outline: none;
}

/* Main Window & Central View */
QMainWindow {
    background-color: #121316;
}

/* Sidebar Navigation */
QFrame#Sidebar {
    background-color: #16171B;
    border-right: 1px solid #23252B;
    min-width: 200px;
    max-width: 220px;
}

QPushButton.NavBtn {
    background-color: transparent;
    color: #9CA3AF;
    text-align: left;
    padding: 9px 14px;
    border-radius: 6px;
    font-weight: 500;
    border: none;
}

QPushButton.NavBtn:hover {
    background-color: #1F2127;
    color: #FFFFFF;
}

QPushButton.NavBtn:checked {
    background-color: #23262F;
    color: #60A5FA;
    font-weight: 600;
}

/* Panels & Cards */
QFrame.Card {
    background-color: #18191E;
    border: 1px solid #23252B;
    border-radius: 8px;
    padding: 12px;
}

QFrame.CandidateCard {
    background-color: #18191E;
    border: 1px solid #262830;
    border-radius: 8px;
    padding: 10px 14px;
}

QFrame.CandidateCardBest {
    background-color: #161B26;
    border: 1px solid #1E3A8A;
    border-radius: 8px;
    padding: 10px 14px;
}

/* Typography Helpers */
QLabel.Title {
    font-size: 15px;
    font-weight: 600;
    color: #FFFFFF;
}

QLabel.Subtitle {
    font-size: 12px;
    color: #9CA3AF;
}

QLabel.SectionHeader {
    font-size: 11px;
    font-weight: 600;
    color: #6B7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Buttons */
QPushButton.PrimaryBtn {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 500;
    padding: 7px 14px;
    border-radius: 6px;
    border: 1px solid #3B82F6;
}

QPushButton.PrimaryBtn:hover {
    background-color: #1D4ED8;
}

QPushButton.SecondaryBtn {
    background-color: #1F2127;
    color: #D1D5DB;
    padding: 7px 12px;
    border-radius: 6px;
    border: 1px solid #2B2D35;
}

QPushButton.SecondaryBtn:hover {
    background-color: #282B33;
    color: #FFFFFF;
}

/* Badges */
QLabel.BadgeBest {
    background-color: #064E3B;
    color: #34D399;
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-weight: 600;
}

QLabel.BadgeEval {
    background-color: #1E293B;
    color: #93C5FD;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    font-weight: 600;
}

QLabel.BadgeConfConfirmed {
    background-color: #064E3B;
    color: #6EE7B7;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 600;
}

QLabel.BadgeConfEmerging {
    background-color: #451A03;
    color: #FCD34D;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 600;
}

QLabel.BadgeConfHypothesis {
    background-color: #262626;
    color: #A3A3A3;
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 10px;
    font-weight: 600;
}

/* Input Fields & Combo Boxes */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #16171B;
    border: 1px solid #282A32;
    border-radius: 6px;
    padding: 7px 10px;
    color: #EDEDED;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #3B82F6;
}

QComboBox {
    background-color: #18191E;
    border: 1px solid #282A32;
    border-radius: 6px;
    padding: 6px 10px;
    color: #EDEDED;
}

QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #18191E;
    border: 1px solid #2B2D35;
    selection-background-color: #2563EB;
}

/* Tables & Lists */
QTableWidget, QListView, QTreeView {
    background-color: #141518;
    border: 1px solid #23252B;
    border-radius: 6px;
    gridline-color: #1F2127;
}

QHeaderView::section {
    background-color: #18191E;
    color: #9CA3AF;
    padding: 6px;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid #23252B;
}

/* Scrollbars */
QScrollBar:vertical {
    background: #141518;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #2B2D35;
    min-height: 20px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #3F424D;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

COLORS = {
    "bg_main": "#121316",
    "bg_card": "#18191E",
    "bg_sidebar": "#16171B",
    "border": "#23252B",
    "text_primary": "#EDEDED",
    "text_secondary": "#9CA3AF",
    "accent_blue": "#2563EB",
    "accent_emerald": "#10B981",
    "accent_amber": "#F59E0B",
    "accent_ruby": "#EF4444",
    # Board squares
    "board_light": "#E2E8F0",
    "board_dark": "#64748B",
    "board_highlight": "#38BDF866",
    "board_last_move": "#FDE0474D",
    "board_arrow_best": "#10B981D0",
    "board_arrow_cand2": "#3B82F6D0",
    "board_arrow_cand3": "#F59E0BD0",
    "board_arrow_threat": "#EF4444D0",
}
