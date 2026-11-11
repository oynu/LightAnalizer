"""
Move list and notation table widget with interactive navigation.
"""
from __future__ import annotations
from typing import List, Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QLabel
)
from PySide6.QtGui import QColor, QFont, QBrush
from PySide6.QtCore import Qt

class MoveListWidget(QWidget):
    """
    Renders the game move history table with navigation controls and current ply highlighting.
    """
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._on_jump_to_ply: Optional[Callable[[int], None]] = None
        self._on_step_back: Optional[Callable[[], None]] = None
        self._on_step_forward: Optional[Callable[[], None]] = None
        self._on_go_start: Optional[Callable[[], None]] = None
        self._on_go_end: Optional[Callable[[], None]] = None

        self._moves_san: List[str] = []
        self._current_ply = 0
        self._setup_ui()

    def set_callbacks(
        self,
        on_jump: Callable[[int], None],
        on_back: Callable[[], None],
        on_forward: Callable[[], None],
        on_start: Callable[[], None],
        on_end: Callable[[], None]
    ) -> None:
        self._on_jump_to_ply = on_jump
        self._on_step_back = on_back
        self._on_step_forward = on_forward
        self._on_go_start = on_start
        self._on_go_end = on_end

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Move table styled as subtle liquid glass
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "White", "Black"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                color: #F8FAFC;
                font-family: 'JetBrains Mono', 'Consolas', monospace;
                font-size: 12px;
                padding: 4px;
            }
            QTableWidget::item {
                border-radius: 6px;
                padding: 4px 6px;
            }
            QTableWidget::item:selected {
                background-color: rgba(0, 240, 255, 0.22);
                color: #00F0FF;
            }
            QHeaderView::section {
                background-color: rgba(255, 255, 255, 0.06);
                color: #94A3B8;
                border: none;
                border-bottom: 1px solid rgba(255, 255, 255, 0.10);
                padding: 6px;
                font-weight: 700;
                font-size: 11px;
            }
        """)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

        # Navigation Controls Row with liquid glass buttons
        nav_row = QHBoxLayout()
        nav_row.setSpacing(6)

        btn_start = QPushButton("⏮")
        btn_back = QPushButton("◀")
        btn_fwd = QPushButton("▶")
        btn_end = QPushButton("⏭")

        for b in [btn_start, btn_back, btn_fwd, btn_end]:
            b.setFixedWidth(38)
            b.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #F8FAFC;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                    padding: 5px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: rgba(0, 240, 255, 0.16);
                    border: 1px solid rgba(0, 240, 255, 0.40);
                    color: #00F0FF;
                }
                QPushButton:pressed {
                    background-color: rgba(0, 240, 255, 0.25);
                }
            """)

        btn_start.clicked.connect(lambda: self._on_go_start() if self._on_go_start else None)
        btn_back.clicked.connect(lambda: self._on_step_back() if self._on_step_back else None)
        btn_fwd.clicked.connect(lambda: self._on_step_forward() if self._on_step_forward else None)
        btn_end.clicked.connect(lambda: self._on_go_end() if self._on_go_end else None)

        nav_row.addWidget(btn_start)
        nav_row.addWidget(btn_back)
        nav_row.addWidget(btn_fwd)
        nav_row.addWidget(btn_end)
        layout.addLayout(nav_row)

    def set_moves(self, moves_san: List[str], current_ply: int) -> None:
        self._moves_san = moves_san
        self._current_ply = current_ply

        num_moves = (len(moves_san) + 1) // 2
        self.table.setRowCount(num_moves)

        active_bg = QColor(0, 240, 255, 45)
        active_fg = QColor("#00F0FF")
        muted_fg = QColor("#64748B")
        normal_fg = QColor("#F8FAFC")
        font_mono = QFont("JetBrains Mono", 10)
        font_mono_bold = QFont("JetBrains Mono", 10, QFont.Bold)

        for i in range(num_moves):
            # Move number
            num_item = QTableWidgetItem(f"{i+1}.")
            num_item.setTextAlignment(Qt.AlignCenter)
            num_item.setForeground(muted_fg)
            num_item.setFont(font_mono)
            self.table.setItem(i, 0, num_item)

            # White move
            white_idx = i * 2
            if white_idx < len(moves_san):
                w_item = QTableWidgetItem(moves_san[white_idx])
                w_item.setTextAlignment(Qt.AlignCenter)
                if current_ply == white_idx + 1:
                    w_item.setBackground(active_bg)
                    w_item.setForeground(active_fg)
                    w_item.setFont(font_mono_bold)
                else:
                    w_item.setForeground(normal_fg)
                    w_item.setFont(font_mono)
                self.table.setItem(i, 1, w_item)

            # Black move
            black_idx = white_idx + 1
            if black_idx < len(moves_san):
                b_item = QTableWidgetItem(moves_san[black_idx])
                b_item.setTextAlignment(Qt.AlignCenter)
                if current_ply == black_idx + 1:
                    b_item.setBackground(active_bg)
                    b_item.setForeground(active_fg)
                    b_item.setFont(font_mono_bold)
                else:
                    b_item.setForeground(normal_fg)
                    b_item.setFont(font_mono)
                self.table.setItem(i, 2, b_item)
            else:
                self.table.setItem(i, 2, QTableWidgetItem(""))

        # Auto-scroll to current ply
        if current_ply > 0:
            target_row = (current_ply - 1) // 2
            item = self.table.item(target_row, 1)
            if item:
                self.table.scrollToItem(item)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == 1:
            ply = (row * 2) + 1
            if ply <= len(self._moves_san) and self._on_jump_to_ply:
                self._on_jump_to_ply(ply)
        elif col == 2:
            ply = (row * 2) + 2
            if ply <= len(self._moves_san) and self._on_jump_to_ply:
                self._on_jump_to_ply(ply)
