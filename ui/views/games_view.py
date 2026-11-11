"""
Games and PGN library explorer view.
Supports searching, importing, exporting, and loading saved games.
"""
from __future__ import annotations
import io
from typing import Optional, List, Callable
import chess.pgn
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from core.opponent.repository import OpponentRepository
from core.opponent.models import GameRecord
from core.board_state import BoardState

class GamesView(QWidget):
    """
    Renders the local game database and PGN library.
    """
    def __init__(
        self,
        repo: OpponentRepository,
        board_state: BoardState,
        on_game_loaded: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.repo = repo
        self.board_state = board_state
        self.on_game_loaded = on_game_loaded
        self._all_games: List[GameRecord] = []

        self._setup_ui()
        self._load_games()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Row
        header_row = QHBoxLayout()
        title = QLabel("Game History & PGN Library")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF;")
        header_row.addWidget(title)
        header_row.addStretch()

        self.btn_import_pgn = QPushButton("Import PGN...")
        self.btn_import_pgn.setStyleSheet("background-color: #2563EB; color: #FFFFFF; padding: 7px 14px; border-radius: 5px; font-weight: 500;")
        self.btn_import_pgn.clicked.connect(self._import_pgn_file)
        header_row.addWidget(self.btn_import_pgn)

        self.btn_export_curr = QPushButton("Export Active Game PGN")
        self.btn_export_curr.setStyleSheet("background-color: #1F2127; color: #EDEDED; border: 1px solid #2B2D35; padding: 7px 14px; border-radius: 5px;")
        self.btn_export_curr.clicked.connect(self._export_active_game)
        header_row.addWidget(self.btn_export_curr)

        layout.addLayout(header_row)

        # Filter bar
        filter_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter games by player, ECO, or opening...")
        self.search_input.textChanged.connect(self._filter_games)
        filter_row.addWidget(self.search_input)
        layout.addLayout(filter_row)

        # Games Table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Date", "White", "Black", "Result", "Opening / ECO"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)
        layout.addWidget(self.table, stretch=1)

        # Bottom Actions Row
        actions_row = QHBoxLayout()
        self.btn_load_game = QPushButton("Load Selected Game to Board")
        self.btn_load_game.setStyleSheet("background-color: #10B981; color: #FFFFFF; padding: 8px 16px; border-radius: 6px; font-weight: 600;")
        self.btn_load_game.clicked.connect(self._load_selected_game)
        actions_row.addWidget(self.btn_load_game)
        actions_row.addStretch()
        layout.addLayout(actions_row)

    def _load_games(self) -> None:
        # Fetch games across all opponents
        opps = self.repo.list_opponents()
        self._all_games = []
        for opp in opps:
            self._all_games.extend(self.repo.get_games_for_opponent(opp.id))
        self._filter_games()

    def _filter_games(self) -> None:
        query = self.search_input.text().lower().strip()
        filtered = [
            g for g in self._all_games
            if query in g.white.lower() or query in g.black.lower() or query in g.eco.lower() or query in g.opening_name.lower()
        ] if query else self._all_games

        self.table.setRowCount(len(filtered))
        for idx, g in enumerate(filtered):
            self.table.setItem(idx, 0, QTableWidgetItem(str(g.id)))
            self.table.setItem(idx, 1, QTableWidgetItem(g.date))
            self.table.setItem(idx, 2, QTableWidgetItem(g.white))
            self.table.setItem(idx, 3, QTableWidgetItem(g.black))
            self.table.setItem(idx, 4, QTableWidgetItem(g.result))
            self.table.setItem(idx, 5, QTableWidgetItem(f"{g.eco} {g.opening_name}"))

    def _on_row_double_clicked(self, row: int, col: int) -> None:
        self._load_selected_game()

    def _load_selected_game(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "Select Game", "Please select a game row first.")
            return

        row = selected_rows[0].row()
        game_id = int(self.table.item(row, 0).text())
        target_game = next((g for g in self._all_games if g.id == game_id), None)
        if target_game:
            if self.board_state.load_pgn(target_game.pgn):
                if self.on_game_loaded:
                    self.on_game_loaded()
                QMessageBox.information(self, "Loaded", f"Game between {target_game.white} and {target_game.black} loaded to analysis board.")

    def _import_pgn_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import PGN", "", "PGN Files (*.pgn);;All Files (*)")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            game = chess.pgn.read_game(io.StringIO(content))
            if not game:
                QMessageBox.warning(self, "Invalid PGN", "Could not parse chess game.")
                return

            opp_name = game.headers.get("Black", "Unknown Player")
            opp = self.repo.get_or_create_opponent(opp_name)
            
            g_rec = GameRecord(
                opponent_id=opp.id,
                white=game.headers.get("White", "Unknown"),
                black=opp_name,
                result=game.headers.get("Result", "*"),
                date=game.headers.get("Date", ""),
                eco=game.headers.get("ECO", ""),
                opening_name=game.headers.get("Opening", ""),
                pgn=content
            )
            self.repo.record_game(g_rec, [])
            self._load_games()
            QMessageBox.information(self, "Imported", "PGN imported successfully into local library.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import PGN: {e}")

    def _export_active_game(self) -> None:
        pgn = self.board_state.export_pgn()
        file_path, _ = QFileDialog.getSaveFileName(self, "Save PGN", "game.pgn", "PGN Files (*.pgn)")
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(pgn)
            QMessageBox.information(self, "Saved", f"Exported PGN saved to {file_path}.")
