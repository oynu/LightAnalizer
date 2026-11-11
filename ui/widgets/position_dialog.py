"""
Interactive Position and Starting Side Setup Dialog.
Allows users to easily start matches as White, as Black, from popular openings,
or from custom FEN puzzle and study positions.
"""
from __future__ import annotations
from typing import Optional
import chess
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QButtonGroup, QFrame, QWidget,
    QApplication
)
from PySide6.QtCore import Qt
from core.game_state_manager import GameStateManager

class PositionSetupDialog(QDialog):
    """
    Modal dialog allowing the user to select starting player color,
    board orientation, or paste a custom FEN.
    """
    def __init__(
        self,
        game_state_mgr: GameStateManager,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.game_state_mgr = game_state_mgr
        self.setWindowTitle("Set Starting Position & Player Side")
        self.setFixedWidth(460)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet("""
            QDialog {
                background-color: #141518;
                color: #EDEDED;
            }
            QLabel {
                color: #D1D5DB;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #1E2127;
                color: #FFFFFF;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 8px 10px;
                font-family: monospace;
                font-size: 11px;
            }
            QLineEdit:focus {
                border-color: #3B82F6;
            }
            QPushButton {
                background-color: #1F2127;
                color: #D1D5DB;
                border: 1px solid #2B2D35;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #2D303B;
                color: #FFFFFF;
            }
            QRadioButton {
                color: #E5E7EB;
                font-size: 12px;
                font-weight: 600;
                spacing: 8px;
            }
            QRadioButton::indicator {
                width: 14px;
                height: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Title Header
        title = QLabel("⚡ Set Starting Position & Color")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #FFFFFF;")
        layout.addWidget(title)

        subtitle = QLabel("Choose your player side or paste a custom starting position.")
        subtitle.setStyleSheet("font-size: 11px; color: #9CA3AF; margin-bottom: 4px;")
        layout.addWidget(subtitle)

        # Presets Frame
        presets_label = QLabel("QUICK PRESETS")
        presets_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #60A5FA; letter-spacing: 0.5px;")
        layout.addWidget(presets_label)

        presets_grid = QVBoxLayout()
        presets_grid.setSpacing(6)

        self.btn_preset_white = QPushButton("♔ Play as White (Standard Start)")
        self.btn_preset_white.setToolTip("Start from move 1 as White. White at bottom.")
        self.btn_preset_white.clicked.connect(self._select_preset_white)
        presets_grid.addWidget(self.btn_preset_white)

        self.btn_preset_black = QPushButton("♚ Play as Black (Flipped Board)")
        self.btn_preset_black.setToolTip("Start from move 1 playing as Black. Black at bottom, awaiting White's move.")
        self.btn_preset_black.clicked.connect(self._select_preset_black)
        presets_grid.addWidget(self.btn_preset_black)

        row_openings = QHBoxLayout()
        row_openings.setSpacing(6)
        self.btn_preset_1e4 = QPushButton("1. e4 (Black to Move)")
        self.btn_preset_1e4.clicked.connect(self._select_preset_1e4)
        row_openings.addWidget(self.btn_preset_1e4)

        self.btn_preset_1d4 = QPushButton("1. d4 (Black to Move)")
        self.btn_preset_1d4.clicked.connect(self._select_preset_1d4)
        row_openings.addWidget(self.btn_preset_1d4)
        presets_grid.addLayout(row_openings)

        layout.addLayout(presets_grid)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("color: #23252B; background-color: #23252B; max-height: 1px;")
        layout.addWidget(divider)

        # Custom FEN Input
        fen_label = QLabel("CUSTOM FEN POSITION")
        fen_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #60A5FA; letter-spacing: 0.5px;")
        layout.addWidget(fen_label)

        fen_row = QHBoxLayout()
        fen_row.setSpacing(8)
        self.txt_fen = QLineEdit()
        self.txt_fen.setText(self.game_state_mgr.fen)
        self.txt_fen.textChanged.connect(self._on_fen_changed)
        fen_row.addWidget(self.txt_fen, stretch=1)

        self.btn_paste = QPushButton("📋 Paste")
        self.btn_paste.setToolTip("Paste FEN from clipboard")
        self.btn_paste.clicked.connect(self._paste_clipboard)
        fen_row.addWidget(self.btn_paste)
        layout.addLayout(fen_row)

        self.lbl_fen_status = QLabel("✓ Valid starting position")
        self.lbl_fen_status.setStyleSheet("font-size: 11px; color: #34D399; font-weight: 600;")
        layout.addWidget(self.lbl_fen_status)

        # Board Orientation Selection
        layout.addWidget(QLabel("Board Orientation:"))
        orient_row = QHBoxLayout()
        orient_row.setSpacing(16)

        self.radio_white = QRadioButton("♔ White at bottom")
        self.radio_black = QRadioButton("♚ Black at bottom")

        current_w_bottom = getattr(self.game_state_mgr, "orientation_white_bottom", True)
        if current_w_bottom:
            self.radio_white.setChecked(True)
        else:
            self.radio_black.setChecked(True)

        self.orient_group = QButtonGroup(self)
        self.orient_group.addButton(self.radio_white)
        self.orient_group.addButton(self.radio_black)

        orient_row.addWidget(self.radio_white)
        orient_row.addWidget(self.radio_black)
        orient_row.addStretch()
        layout.addLayout(orient_row)

        layout.addSpacing(6)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_apply = QPushButton("Apply Position")
        self.btn_apply.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: 1px solid #3B82F6;
                padding: 7px 18px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_apply.clicked.connect(self._apply_position)
        btn_box.addWidget(self.btn_apply)

        layout.addLayout(btn_box)

    def _select_preset_white(self) -> None:
        self.txt_fen.setText(chess.STARTING_FEN)
        self.radio_white.setChecked(True)

    def _select_preset_black(self) -> None:
        self.txt_fen.setText(chess.STARTING_FEN)
        self.radio_black.setChecked(True)

    def _select_preset_1e4(self) -> None:
        self.txt_fen.setText("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
        self.radio_black.setChecked(True)

    def _select_preset_1d4(self) -> None:
        self.txt_fen.setText("rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq d3 0 1")
        self.radio_black.setChecked(True)

    def _paste_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.txt_fen.setText(text)

    def _on_fen_changed(self, text: str) -> None:
        t = text.strip()
        try:
            b = chess.Board(t)
            turn_str = "White" if b.turn == chess.WHITE else "Black"
            self.lbl_fen_status.setText(f"✓ Valid position ({turn_str} to move)")
            self.lbl_fen_status.setStyleSheet("font-size: 11px; color: #34D399; font-weight: 600;")
            self.btn_apply.setEnabled(True)
        except Exception:
            self.lbl_fen_status.setText("✕ Invalid FEN format")
            self.lbl_fen_status.setStyleSheet("font-size: 11px; color: #F87171; font-weight: 600;")
            self.btn_apply.setEnabled(False)

    def _apply_position(self) -> None:
        fen = self.txt_fen.text().strip()
        w_bottom = self.radio_white.isChecked()
        success = self.game_state_mgr.set_starting_position(fen, orientation_white_bottom=w_bottom)
        if success:
            self.accept()
