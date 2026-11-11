"""
Move list and notation table widget with interactive navigation.
"""
from __future__ import annotations
from typing import List, Optional, Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QLabel
)
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

        # Move table
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["#", "White", "Black"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectItems)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

        # Navigation Controls Row
        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)

        btn_start = QPushButton("⏮")
        btn_back = QPushButton("◀")
        btn_fwd = QPushButton("▶")
        btn_end = QPushButton("⏭")

        for b in [btn_start, btn_back, btn_fwd, btn_end]:
            b.setFixedWidth(36)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #1F2127;
                    color: #D1D5DB;
                    border: 1px solid #2B2D35;
                    border-radius: 4px;
                    padding: 4px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #2D303B;
                    color: #FFFFFF;
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

        for i in range(num_moves):
            # Move number
            num_item = QTableWidgetItem(f"{i+1}.")
            num_item.setTextAlignment(Qt.AlignCenter)
            num_item.setForeground(Qt.gray)
            self.table.setItem(i, 0, num_item)

            # White move
            white_idx = i * 2
            if white_idx < len(moves_san):
                w_item = QTableWidgetItem(moves_san[white_idx])
                w_item.setTextAlignment(Qt.AlignCenter)
                if current_ply == white_idx + 1:
                    w_item.setBackground(Qt.darkBlue)
                self.table.setItem(i, 1, w_item)

            # Black move
            black_idx = white_idx + 1
            if black_idx < len(moves_san):
                b_item = QTableWidgetItem(moves_san[black_idx])
                b_item.setTextAlignment(Qt.AlignCenter)
                if current_ply == black_idx + 1:
                    b_item.setBackground(Qt.darkBlue)
                self.table.setItem(i, 2, b_item)
            else:
                self.table.setItem(i, 2, QTableWidgetItem(""))

        # Auto-scroll to current ply
        if current_ply > 0:
            target_row = (current_ply - 1) // 2
            self.table.scrollToItem(self.table.item(target_row, 1))

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col == 1:
            ply = (row * 2) + 1
            if ply <= len(self._moves_san) and self._on_jump_to_ply:
                self._on_jump_to_ply(ply)
        elif col == 2:
            ply = (row * 2) + 2
            if ply <= len(self._moves_san) and self._on_jump_to_ply:
                self._on_jump_to_ply(ply)
