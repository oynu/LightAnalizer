"""
Post-game review screen.
Displays move-by-move accuracy, blunder categorization, and critical moments.
"""
from __future__ import annotations
import threading
from typing import Optional, List, Tuple
import chess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QProgressBar, QMessageBox
)
from PySide6.QtCore import Qt, QMetaObject, Q_ARG, Slot
from core.board_state import BoardState
from core.review import GameReviewer, GameReviewReport, MoveReview

class ReviewView(QWidget):
    """
    Renders post-game analysis report, accuracy percentages, and critical turning points.
    """
    def __init__(self, board_state: BoardState, reviewer: GameReviewer, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.board_state = board_state
        self.reviewer = reviewer
        self._current_report: Optional[GameReviewReport] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Row
        header_row = QHBoxLayout()
        title = QLabel("Post-Game Performance Review")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF;")
        header_row.addWidget(title)
        header_row.addStretch()

        self.btn_run_review = QPushButton("▶ Run Game Review")
        self.btn_run_review.setStyleSheet("""
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
                padding: 8px 16px;
                border-radius: 6px;
                border: 1px solid #3B82F6;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
        """)
        self.btn_run_review.clicked.connect(self._run_review_async)
        header_row.addWidget(self.btn_run_review)
        layout.addLayout(header_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1E2025;
                border-radius: 3px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 3px;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Accuracy & Mistake Cards Row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        # White Card
        self.card_white = QFrame()
        self.card_white.setStyleSheet("background-color: #18191E; border: 1px solid #23252B; border-radius: 8px; padding: 12px;")
        cw_layout = QVBoxLayout(self.card_white)
        self.lbl_w_acc = QLabel("White Accuracy: --%")
        self.lbl_w_acc.setStyleSheet("font-size: 15px; font-weight: 700; color: #FFFFFF;")
        self.lbl_w_stats = QLabel("Blunders: 0 | Mistakes: 0 | Inaccuracies: 0")
        self.lbl_w_stats.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        cw_layout.addWidget(self.lbl_w_acc)
        cw_layout.addWidget(self.lbl_w_stats)
        cards_row.addWidget(self.card_white)

        # Black Card
        self.card_black = QFrame()
        self.card_black.setStyleSheet("background-color: #18191E; border: 1px solid #23252B; border-radius: 8px; padding: 12px;")
        cb_layout = QVBoxLayout(self.card_black)
        self.lbl_b_acc = QLabel("Black Accuracy: --%")
        self.lbl_b_acc.setStyleSheet("font-size: 15px; font-weight: 700; color: #FFFFFF;")
        self.lbl_b_stats = QLabel("Blunders: 0 | Mistakes: 0 | Inaccuracies: 0")
        self.lbl_b_stats.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        cb_layout.addWidget(self.lbl_b_acc)
        cb_layout.addWidget(self.lbl_b_stats)
        cards_row.addWidget(self.card_black)

        layout.addLayout(cards_row)

        # Review Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Ply", "Move", "Played", "Best Move", "Eval Loss", "Classification"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table, stretch=1)

    def _run_review_async(self) -> None:
        moves = []
        node = self.board_state.game
        curr_b = node.board()
        for idx in range(1, len(self.board_state._history_nodes)):
            target_node = self.board_state._history_nodes[idx]
            if target_node.move:
                moves.append((curr_b.copy(), target_node.move))
                curr_b.push(target_node.move)

        if not moves:
            QMessageBox.information(self, "No Moves", "The current game contains no played moves to review.")
            return

        self.btn_run_review.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        def worker():
            report = self.reviewer.review_game(
                moves,
                progress_cb=lambda cur, tot: self._update_progress_safe(cur, tot)
            )
            self._on_review_finished(report)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _update_progress_safe(self, cur: int, tot: int) -> None:
        pct = int((cur / tot) * 100)
        # Thread safe update
        QMetaObject.invokeMethod(self.progress_bar, "setValue", Qt.QueuedConnection, Q_ARG(int, pct))

    def _on_review_finished(self, report: GameReviewReport) -> None:
        self._current_report = report
        # Update UI on main thread
        QMetaObject.invokeMethod(self, "_render_report", Qt.QueuedConnection)

    @Slot()
    def _render_report(self) -> None:
        self.btn_run_review.setEnabled(True)
        self.progress_bar.setVisible(False)
        if not self._current_report:
            return

        r = self._current_report
        self.lbl_w_acc.setText(f"White Accuracy: {r.white_accuracy}%")
        self.lbl_w_stats.setText(f"Blunders: {r.white_blunders} | Mistakes: {r.white_mistakes} | Inaccuracies: {r.white_inaccuracies}")

        self.lbl_b_acc.setText(f"Black Accuracy: {r.black_accuracy}%")
        self.lbl_b_stats.setText(f"Blunders: {r.black_blunders} | Mistakes: {r.black_mistakes} | Inaccuracies: {r.black_inaccuracies}")

        self.table.setRowCount(len(r.move_reviews))
        for i, mr in enumerate(r.move_reviews):
            self.table.setItem(i, 0, QTableWidgetItem(str(mr.ply)))
            self.table.setItem(i, 1, QTableWidgetItem(f"{mr.move_number}. {'White' if mr.is_white else 'Black'}"))
            self.table.setItem(i, 2, QTableWidgetItem(mr.san))
            self.table.setItem(i, 3, QTableWidgetItem(mr.best_san))
            self.table.setItem(i, 4, QTableWidgetItem(f"{mr.eval_loss:.2f}"))

            class_item = QTableWidgetItem(mr.classification)
            if mr.classification == "Blunder":
                class_item.setForeground(Qt.red)
            elif mr.classification == "Mistake":
                class_item.setForeground(Qt.yellow)
            elif mr.classification == "Best":
                class_item.setForeground(Qt.green)
            self.table.setItem(i, 5, class_item)

    def _on_row_double_clicked(self, row: int, col: int) -> None:
        if self._current_report and row < len(self._current_report.move_reviews):
            mr = self._current_report.move_reviews[row]
            # Jump to ply before this move so user can see candidate moves
            target_ply = max(0, mr.ply - 1)
            self.board_state.go_to_ply(target_ply)
